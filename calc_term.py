"""Exact, symbolic terminal calculator. Run with Python 3.10+ and SymPy.

The parser is a small arithmetic grammar: it never evals Python or configuration.
The terminal UI uses msvcrt on Windows and termios on POSIX, without curses.
See README.md for keys, commands, and the JSON menu configuration.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, replace
import json
import operator
import os
from pathlib import Path
import re
import shutil
import sys
import time
from typing import cast
import unicodedata

# Python's default decimal string limit would truncate the usefulness of exact
# integers. This calculator intentionally accepts and prints arbitrarily long ones.
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

try:
    import sympy as sp
except ImportError:
    raise SystemExit("SymPy is required. Run: python -m pip install -r requirements.txt")


class CalcError(ValueError):
    """An input or configuration error suitable for displaying in the UI."""


# Quantities track powers of the seven SI base dimensions in a fixed order:
# length, mass, time, current, temperature, amount of substance, and luminous intensity.
# A tuple of zeros represents a dimensionless value, such as a plain number.
ZERO = (sp.S.Zero,) * 7
BASE_NAMES = ("m", "kg", "s", "A", "°K", "mol", "cd")


def dimension(**powers):
    # Named powers make definitions readable, e.g. velocity is dimension(L=1, T=-1).
    return tuple(sp.Rational(powers.get(k, 0)) for k in ("L", "M", "T", "I", "K", "N", "J"))


def combine_dims(left, right, sign=1):
    # Multiplication adds dimension powers; division subtracts them.
    return tuple(a + sign * b for a, b in zip(left, right))


def unit_key(name):
    # Normalize equivalent Unicode spellings and case without changing variable names.
    return unicodedata.normalize("NFKC", name.removeprefix("_")).casefold()


@dataclass(frozen=True)
class Unit:
    # Convert a coordinate in this unit to SI with: value * scale + offset.
    # Constants use the same representation but cannot be conversion targets.
    name: str
    label: str
    category: str
    scale: sp.Expr
    dims: tuple
    offset: sp.Expr = sp.S.Zero
    constant: bool = False

    @property
    def notation(self):
        return self.name if self.name.startswith(("_", "(")) else "_" + self.name


@dataclass(frozen=True)
class Quantity:
    # value is stored in SI base units; display only records a preferred output unit.
    # SymPy values also let dimensionless results hold symbols, lists, or booleans.
    value: sp.Basic
    dims: tuple = ZERO
    display: Unit | None = None

    def checked(self):
        # Check intermediate results too, so undefined values cannot cancel away later.
        if self.value.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
            raise CalcError("The result is undefined or infinite (check division by zero and domains).")
        return self

    @property
    def affine(self):
        # Celsius and Fahrenheit have an offset from the SI origin (absolute zero).
        return self.display is not None and self.display.offset != 0

    def negate(self):
        if not isinstance(self.value, sp.Expr):
            raise CalcError("Negation requires a scalar expression.")
        # A leading minus on -40_°C refers to its temperature coordinate.
        if self.display is not None and self.affine:
            return replace(self, value=sp.Add(sp.Mul(2, self.display.offset), sp.Mul(-1, self.value)))
        return replace(self, value=sp.Mul(-1, self.value))

    def arithmetic(self, op, other):
        # Binary arithmetic operators keep values and dimensions aligned here.
        if not isinstance(self.value, sp.Expr) or not isinstance(other.value, sp.Expr):
            raise CalcError("Arithmetic requires scalar expressions.")
        if op in ("+", "-"):
            if self.dims != other.dims:
                raise CalcError("Cannot add or subtract quantities with different dimensions.")
            if op == "+" and self.affine and other.affine:
                raise CalcError("Use Kelvin or deltaC/deltaF for temperature arithmetic.")
            display = self.display if self.affine else other.display if other.affine else self.display or other.display
            if op == "-" and self.affine and other.affine:
                # Subtracting absolute temperatures yields a difference with no offset.
                display = Unit("deltaK", "kelvin difference", "Temperature", sp.S.One, self.dims)
            value = sp.Add(self.value, other.value if op == "+" else sp.Mul(-1, other.value))
            return Quantity(value, self.dims, display).checked()
        if self.affine or other.affine:
            raise CalcError("Convert offset temperatures to _°K before multiplying or dividing.")
        if op in ("*", "/"):
            if op == "/" and other.value == 0:
                raise CalcError("Division by zero.")
            dims = combine_dims(self.dims, other.dims, 1 if op == "*" else -1)
            value = sp.Mul(self.value, other.value if op == "*" else sp.Pow(other.value, -1))
            display = self.display if other.dims == ZERO else None
            if op == "*" and self.dims == ZERO:
                display = other.display
            if dims == ZERO:
                display = None
            return Quantity(value, dims, display).checked()
        if op == "^":
            # Apply the exponent to both the number and each physical dimension.
            if other.dims != ZERO:
                raise CalcError("An exponent must be dimensionless.")
            if self.dims != ZERO and not isinstance(other.value, sp.Rational):
                raise CalcError("A dimensioned base requires an exact rational exponent.")
            dims = tuple(d * other.value for d in self.dims)
            display = None
            if self.display and other.value.is_Rational and other.value != 0:
                notation = self.display.notation
                display = Unit(f"({notation})^({expression_text(other.value)})", "compound unit", "Compound",
                               self.display.scale ** other.value, dims)
            return Quantity(self.value ** other.value, dims, display).checked()
        if op == "%":
            if self.dims != ZERO or other.dims != ZERO:
                raise CalcError("Remainder requires dimensionless arguments.")
            if other.value == 0:
                raise CalcError("Division by zero.")
            value = sp.Mod(self.value, other.value)
            if not isinstance(value, sp.Expr):
                raise CalcError("Remainder did not produce a scalar result.")
            return Quantity(value).checked()
        raise CalcError(f"Unknown operator: {op}")

    def bitwise(self, op, other=None):
        # Python integers provide arbitrary-width signed bit operations; converting
        # back to SymPy keeps their results compatible with the rest of the engine.
        if self.dims != ZERO or not isinstance(self.value, sp.Integer):
            raise CalcError("Bitwise operators require dimensionless exact integers.")
        left = int(self.value)
        if op == "~":
            return Quantity(sp.Integer(~left))
        if other is None or other.dims != ZERO or not isinstance(other.value, sp.Integer):
            raise CalcError("Bitwise operators require dimensionless exact integers.")
        right = int(other.value)
        if op in ("<<", ">>") and right < 0:
            raise CalcError("A shift count must be a nonnegative integer.")
        return Quantity(sp.Integer(BITWISE[op](left, right)))

    def compare(self, op, other):
        # Values already share SI coordinates, so compatible units compare directly.
        equality = op in ("=", "==", "!=")
        for value in (self.value, other.value):
            if not isinstance(value, sp.Expr) and not (equality and value in (sp.true, sp.false)):
                raise CalcError("Comparisons require scalar expressions (or booleans for equality).")
        if self.dims != other.dims:
            raise CalcError("Cannot compare quantities with different dimensions.")
        result = COMPARISONS[op](self.value, other.value)
        # A symbolic relation can sometimes simplify to a definite truth value.
        # Otherwise report an error instead of guessing whether it is True or False.
        if result not in (sp.true, sp.false):
            result = sp.simplify(result)
        if result not in (sp.true, sp.false):
            raise CalcError("Cannot determine True or False; assign values to symbolic variables first.")
        return Quantity(result)


# Result formatting preserves exact values unless approximation was requested.
def expression_text(value, full_prec: bool | str = "auto"):
    # Use calculator syntax for powers and solution lists so results can be recalled.
    if isinstance(value, sp.Tuple):
        return "[" + ", ".join(expression_text(x, full_prec) for x in value) + "]"
    return sp.sstr(value, full_prec=full_prec).replace("**", "^")


def approximate_value(value, precision):
    # Approximate a copy for output; stored quantities and variables remain unchanged.
    if isinstance(value, sp.Tuple):
        return sp.Tuple(*(approximate_value(item, precision) for item in value))
    if value in (sp.true, sp.false):
        return value
    # Keep integers intact and respect the precision of explicit approx(...) values.
    if isinstance(value, (sp.Integer, sp.Float)) or value is sp.I:
        return value
    if value.has(sp.Float):
        return value.func(*(approximate_value(arg, precision) for arg in value.args))
    return sp.N(value, precision)


class UnitRegistry:
    """Case-insensitive units with exact SI scale factors and seven dimensions."""

    def __init__(self):
        self.units = {}
        self._builtins()

    def add(self, name: str, label: str, category: str, scale: str | int | sp.Expr,
            dims: tuple, offset: str | int | sp.Expr = 0, constant: bool = False):
        key = unit_key(name)
        if key in self.units:
            raise CalcError(f"Unit _{name} already exists (unit names ignore case).")
        scale = sp.Rational(scale) if isinstance(scale, (str, int)) else scale
        offset = sp.Rational(offset) if isinstance(offset, (str, int)) else offset
        self.units[key] = Unit(name.removeprefix("_"), label, category, scale, dims, offset, constant)

    def get(self, name):
        try:
            return self.units[unit_key(name)]
        except KeyError:
            raise CalcError(f"Unknown unit {name}. Use F2 or :unit NAME = expression.") from None

    def _builtins(self):
        # Reuse dimension definitions across the unit tables below. Scale factors
        # are relative to SI and decimal strings become exact rational numbers.
        L, M, T = dimension(L=1), dimension(M=1), dimension(T=1)
        force = dimension(L=1, M=1, T=-2)
        energy = dimension(L=2, M=1, T=-2)
        power = dimension(L=2, M=1, T=-3)
        pressure = dimension(L=-1, M=1, T=-2)
        charge = dimension(T=1, I=1)
        voltage = dimension(L=2, M=1, T=-3, I=-1)
        resistance = dimension(L=2, M=1, T=-3, I=-2)
        capacitance = dimension(L=-2, M=-1, T=4, I=2)
        flux = dimension(L=2, M=1, T=-2, I=-1)
        tesla = dimension(M=1, T=-2, I=-1)
        inductance = dimension(L=2, M=1, T=-2, I=-2)

        def group(category, dims, rows):
            # Each compact table row contains a unit name, menu label, and SI scale.
            for row in rows.strip().splitlines():
                name, label, scale = row.strip().split("|")
                self.add(name, label, category, scale, dims)

        group("Length", L, """
        Ang|angstrom|1e-10
        Å|angstrom|1e-10
        au|astronomical unit|149597870700
        cm|centimeter|0.01
        fath|fathom|1.8288
        fm|femtometer|1e-15
        ft|foot|0.3048
        in|inch|0.0254
        km|kilometer|1000
        ltyr|light year (Julian)|9460730472580800
        m|meter|1
        mi|statute mile|1609.344
        mil|thousandth of an inch|0.0000254
        mm|millimeter|0.001
        Nmi|nautical mile|1852
        rod|rod|5.0292
        yd|yard|0.9144
        μ|micron|1e-6
        """)
        self.add("pc", "parsec", "Length", 648000 * sp.Integer(149597870700) / sp.pi, L)
        group("Area", dimension(L=2), "acre|acre|4046.8564224\nha|hectare|10000")
        group("Volume", dimension(L=3), """
        cup|US cup|0.0002365882365
        floz|US fluid ounce|0.0000295735295625
        flozUK|UK fluid ounce|0.0000284130625
        gal|US gallon|0.003785411784
        galUK|UK gallon|0.00454609
        l|liter|0.001
        ml|milliliter|1e-6
        pt|US pint|0.000473176473
        qt|US quart|0.000946352946
        tbsp|US tablespoon|0.00001478676478125
        tsp|US teaspoon|0.00000492892159375
        """)
        group("Time", T, """
        day|day|86400
        hr|hour|3600
        min|minute|60
        ms|millisecond|0.001
        ns|nanosecond|1e-9
        s|second|1
        week|week|604800
        yr|Julian year (365.25 days)|31557600
        μs|microsecond|1e-6
        """)
        group("Velocity", dimension(L=1, T=-1), "knot|knot|463/900\nkph|kilometer per hour|5/18\nmph|mile per hour|0.44704")
        self.add("mps2", "meter per second squared", "Acceleration", 1, dimension(L=1, T=-2))
        temp = dimension(K=1)
        for name, label, scale, offset in (
            ("°C", "Celsius", 1, "273.15"), ("°F", "Fahrenheit", "5/9", "45967/180"),
            ("°K", "Kelvin", 1, 0), ("°R", "Rankine", "5/9", 0),
            ("deltaC", "Celsius difference", 1, 0), ("deltaF", "Fahrenheit difference", "5/9", 0),
            ("deltaK", "kelvin difference", 1, 0),
        ):
            self.add(name, label, "Temperature", scale, temp, offset)
        self.add("cd", "candela", "Luminous Intensity", 1, dimension(J=1))
        self.add("mol", "mole", "Amount of Substance", 1, dimension(N=1))
        group("Mass", M, """
        amu|atomic mass unit (CODATA 2022)|1.66053906892e-27
        gm|gram|0.001
        kg|kilogram|1
        lb|avoirdupois pound|0.45359237
        mg|milligram|1e-6
        mton|metric ton|1000
        oz|avoirdupois ounce|0.028349523125
        ton|US short ton|907.18474
        tonne|metric tonne|1000
        tonUK|UK long ton|1016.0469088
        """)
        self.add("slug", "slug", "Mass", sp.Mul(sp.Rational("4.4482216152605"), sp.Pow(sp.Rational("0.3048"), -1)), M)
        group("Force", force, """
        dyne|dyne|1e-5
        kgf|kilogram-force|9.80665
        lbf|pound-force|4.4482216152605
        N|newton|1
        tonf|US short ton-force|8896.443230521
        """)
        group("Energy", energy, """
        Btu|British thermal unit (IT)|1055.05585262
        cal|thermochemical calorie|4.184
        erg|erg|1e-7
        eV|electronvolt|1.602176634e-19
        ftlb|foot-pound-force|1.3558179483314004
        J|joule|1
        kcal|thermochemical kilocalorie|4184
        kWh|kilowatt-hour|3600000
        latm|liter-atmosphere|101.325
        """)
        group("Power", power, "hp|mechanical horsepower|745.69987158227022\nkW|kilowatt|1000\nW|watt|1")
        group("Pressure", pressure, """
        atm|standard atmosphere|101325
        bar|bar|100000
        inH2O|inch of water (conventional)|249.08891
        inHg|inch of mercury (conventional)|3386.388640341
        mmH2O|millimeter of water (conventional)|9.80665
        mmHg|millimeter of mercury (conventional)|133.322387415
        Pa|pascal|1
        torr|torr|101325/760
        """)
        self.add("psi", "pound-force per square inch", "Pressure", sp.Mul(sp.Rational("4.4482216152605"), sp.Pow(sp.Rational("0.0254"), -2)), pressure)
        self.add("St", "stokes", "Kinematic Viscosity", "0.0001", dimension(L=2, T=-1))
        self.add("P", "poise", "Dynamic Viscosity", "0.1", dimension(L=-1, M=1, T=-1))
        group("Frequency", dimension(T=-1), "GHz|gigahertz|1e9\nHz|hertz|1\nkHz|kilohertz|1000\nMHz|megahertz|1e6")
        group("Electric Current", dimension(I=1), "A|ampere|1\nkA|kiloampere|1000\nmA|milliampere|0.001\nμA|microampere|1e-6")
        self.add("coul", "coulomb", "Charge", 1, charge)
        group("Potential", voltage, "kV|kilovolt|1000\nmV|millivolt|0.001\nV|volt|1\nvolt|volt|1")
        group("Resistance", resistance, "kΩ|kiloohm|1000\nMΩ|megaohm|1e6\nohm|ohm|1\nΩ|ohm|1")
        group("Conductance", tuple(-d for d in resistance), "mho|mho|1\nmmho|millimho|0.001\nsiemens|siemens|1\nμmho|micromho|1e-6")
        group("Capacitance", capacitance, "F|farad|1\nnF|nanofarad|1e-9\npF|picofarad|1e-12\nμF|microfarad|1e-6")
        self.add("Oe", "oersted", "Mag Field Strength", 250 / sp.pi, dimension(L=-1, I=1))
        group("Mag Flux Density", tesla, "Gs|gauss|0.0001\nT|tesla|1")
        self.add("Wb", "weber", "Magnetic Flux", 1, flux)
        group("Inductance", inductance, "henry|henry|1\nmH|millihenry|0.001\nnH|nanohenry|1e-9\nμH|microhenry|1e-6")

        # Physical constants carry dimensions just like units. Derived constants
        # stay symbolic; measured values retain the published precision of the table.
        c, h, k, q, na = map(sp.Rational, ("299792458", "6.62607015e-34", "1.380649e-23", "1.602176634e-19", "6.02214076e23"))
        epsilon = sp.Rational("8.8541878188e-12")
        constants = (
            ("c", "speed of light", c, dimension(L=1, T=-1)),
            ("Cc", "Coulomb constant (derived from ε0)", 1 / (4 * sp.pi * epsilon), dimension(L=3, M=1, T=-4, I=-2)),
            ("g", "standard gravity", "9.80665", dimension(L=1, T=-2)),
            ("Gc", "gravitational constant", "6.67430e-11", dimension(L=3, M=-1, T=-2)),
            ("h", "Planck constant", h, dimension(L=2, M=1, T=-1)),
            ("k", "Boltzmann constant", k, dimension(L=2, M=1, T=-2, K=-1)),
            ("Me", "electron rest mass", "9.1093837139e-31", M),
            ("Mn", "neutron rest mass", "1.67492750056e-27", M),
            ("Mp", "proton rest mass", "1.67262192595e-27", M),
            ("Na", "Avogadro constant", na, dimension(N=-1)),
            ("q", "positive elementary charge", q, charge),
            ("Rb", "Bohr radius", "5.29177210544e-11", L),
            ("Rc", "universal gas constant", sp.Mul(na, k), dimension(L=2, M=1, T=-2, K=-1, N=-1)),
            ("Rdb", "Rydberg constant", "10973731.568157", dimension(L=-1)),
            ("Vm", "ideal gas molar volume (273.15 K, 1 atm)", sp.Mul(na, k, sp.Rational("273.15"), sp.Rational(1, 101325)), dimension(L=3, N=-1)),
            ("ε0", "vacuum permittivity", epsilon, dimension(L=-3, M=-1, T=4, I=2)),
            ("σ", "Stefan-Boltzmann constant", sp.Mul(2, sp.pi ** 5, k ** 4, sp.Pow(sp.Mul(15, h ** 3, c ** 2), -1)), dimension(M=1, T=-3, K=-4)),
            ("φ0", "magnetic flux quantum", sp.Mul(h, sp.Pow(sp.Mul(2, q), -1)), flux),
            ("μ0", "vacuum magnetic permeability", "1.25663706127e-6", dimension(L=1, M=1, T=-2, I=-2)),
            ("μb", "Bohr magneton", "9.2740100657e-24", dimension(L=2, I=1)),
        )
        for name, label, value, dims in constants:
            self.add(name, label, "Constants", value, dims, constant=True)

    def format(self, quantity, precision=None):
        # Prefer the requested display unit, then a matching SI unit if one exists.
        unit = quantity.display
        if unit and unit.constant:
            unit = None
        if unit is None and quantity.dims != ZERO:
            unit = next((u for u in self.units.values() if not u.constant and u.dims == quantity.dims and u.scale == 1 and u.offset == 0), None)
        if unit:
            # Reverse the SI transformation before rounding, especially for temperatures.
            value = sp.simplify((quantity.value - unit.offset) / unit.scale)
            if precision is not None:
                value = approximate_value(value, precision)
            text = expression_text(value, full_prec="auto" if precision is None else False)
            # A simple fraction followed by a unit is also a supported input literal.
            if not isinstance(value, (sp.Integer, sp.Rational, sp.Float, sp.Symbol)):
                text = "(" + text + ")"
            if any(c in unit.name for c in "*/^"):
                return text + "*(" + unit.notation + ")"
            return text + unit.notation
        value = quantity.value if precision is None else approximate_value(quantity.value, precision)
        text = expression_text(value, full_prec="auto" if precision is None else False)
        if quantity.dims == ZERO:
            return text
        # Without a named display unit, build a parseable product of SI base units.
        numerator, denominator = [], []
        for name, exponent in zip(BASE_NAMES, quantity.dims):
            if exponent:
                power = abs(exponent)
                token = "_" + name
                if power != 1:
                    token += "^(" + expression_text(power) + ")"
                (numerator if exponent > 0 else denominator).append(token)
        units = "*".join(numerator) or "1"
        if denominator:
            units += "/(" + "*".join(denominator) + ")"
        return "(" + text + ")*(" + units + ")"


# Input grammar: recognize only calculator tokens, never Python source code.
# Unit tokens deliberately keep case; the registry alone ignores it.
DIGITS = r"\d+(?:_\d+)*"
BASES = {"b": 2, "h": 16, "o": 8}
BASE_LITERAL = re.compile(r"(?<!\w)0([bBhHoO])([^\W_]*(?:_[^\W_]+)*)", re.UNICODE)
TOKEN = re.compile(rf"(?P<number>{DIGITS}/{DIGITS}(?=_°?[^\W\d_])|"
                   rf"(?:{DIGITS}(?:\.(?:{DIGITS})?)?|\.{DIGITS})(?:[eE][+-]?{DIGITS})?)|"
                   r"(?P<unit>_°?[^\W\d_][^\W_]*)|(?P<name>[^\W\d_][^\W_]*)|"
                   r"(?P<op>\*\*|<<|>>|<=|>=|==|!=|[&|~<>=+\-*/^%(),!\[\]])", re.UNICODE)
# Explicit tables define the supported comparisons, reserved values, and functions.
COMPARISONS = {"<": sp.Lt, ">": sp.Gt, "<=": sp.Le, ">=": sp.Ge,
               "=": sp.Eq, "==": sp.Eq, "!=": sp.Ne}
# Keep ^ as exponentiation; the word xor supplies bitwise exclusive OR instead.
BITWISE = {"&": operator.and_, "|": operator.or_, "xor": operator.xor,
           "<<": operator.lshift, ">>": operator.rshift}
RESERVED = {"pi": sp.pi, "π": sp.pi, "e": sp.E, "E": sp.E, "i": sp.I, "I": sp.I,
            "True": sp.true, "False": sp.false}
FUNCTIONS = {"sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "sqrt", "cbrt",
             "exp", "ln", "log", "abs", "floor", "ceil", "factorial", "simplify", "expand", "factor",
             "diff", "integrate", "solve", "subs", "approx", "min", "max"}
EQUATION_NAMES = tuple(f"y{i}" for i in range(1, 100))
TRANSLATE = str.maketrans({"→": "->", "⇒": "=>", "×": "*", "÷": "/", "−": "-", "²": "^2", "³": "^3",
                           "≤": "<=", "≥": ">=", "≠": "!="})


def normalize_input(text):
    # Translate supported mathematical symbols into the parser's operator spellings.
    return text.translate(TRANSLATE).strip()


def decimal_literals(text: str, registry: UnitRegistry) -> str:
    """Normalize integer bases and digit separators, preserving names and units."""
    def convert(match: re.Match[str]) -> str:
        prefix, digits = match.groups()
        if (match.start() and text[match.start() - 1] == ".") or text[match.end():match.end() + 1] == ".":
            raise CalcError("Base-prefixed numbers must be integers.")
        parts = digits.split("_")
        number, suffix = parts[0], ""
        if not number:
            raise CalcError(f"Enter digits after 0{prefix}.")
        for index, part in enumerate(parts[1:], start=1):
            # _F and _cd, for example, are units as well as valid hex digits.
            # Existing unit names keep their meaning; other groups are separators.
            if unit_key(part) in registry.units:
                suffix = "_" + "_".join(parts[index:])
                break
            number += "_" + part
        try:
            value = int(number.replace("_", ""), BASES[prefix.lower()])
        except ValueError:
            raise CalcError(f"Invalid digits in base-{BASES[prefix.lower()]} literal 0{prefix}{number}.") from None
        return str(value) + suffix

    text = BASE_LITERAL.sub(convert, text)
    # Remove grouping underscores only from numbers; unit suffixes must keep theirs.
    return TOKEN.sub(lambda match: match.group().replace("_", "")
                     if match.lastgroup == "number" else match.group(), text)


class Parser:
    """Pratt parser with a strict function allowlist and exact numeric tokens."""

    def __init__(self, calculator, text, unit_only=False, local_variables=None,
                 equation_stack=(), validating_equation=False):
        # Conversion targets use a restricted grammar without variables or functions.
        self.calculator = calculator
        self.unit_only = unit_only
        self.local_variables = local_variables or {}
        self.equation_stack = equation_stack
        self.validating_equation = validating_equation
        text = decimal_literals(text, calculator.registry)
        self.tokens = []
        position = 0
        while position < len(text):
            if text[position].isspace():
                position += 1
                continue
            match = TOKEN.match(text, position)
            if not match:
                raise CalcError(f"Unexpected character at column {position + 1}: {text[position]!r}")
            token = match.group().replace("_", "") if match.lastgroup == "number" else match.group()
            self.tokens.append((match.lastgroup, token))
            position = match.end()
        # An explicit end token lets parsing report incomplete input consistently.
        self.tokens.append(("end", ""))
        self.index = 0

    def peek(self):
        return self.tokens[self.index]

    def take(self):
        token = self.peek()
        self.index += 1
        return token

    def expect(self, text):
        if self.peek()[1] != text:
            raise CalcError(f"Expected '{text}', found '{self.peek()[1] or 'end of input'}'.")
        self.take()

    def parse(self):
        # A successful parse must consume the whole input, not just a valid prefix.
        value = self.expression()
        if self.peek()[0] != "end":
            raise CalcError(f"Unexpected token '{self.peek()[1]}'.")
        return value.checked()

    def expression(self, minimum=0):
        # First read an operand: a literal, prefix sign, group, unit, or named value.
        # minimum is the weakest operator precedence this recursive call may consume.
        kind, token = self.take()
        if kind == "number":
            try:
                left = Quantity(sp.Rational(token)).checked()
            except (ValueError, ZeroDivisionError):
                raise CalcError("Invalid number or zero denominator.") from None
        elif token in ("+", "-"):
            # Powers bind more tightly than a leading sign: -2^2 means -(2^2).
            left = self.expression(25)
            if token == "-":
                left = left.negate()
        elif token == "~" and not self.unit_only:
            # NOT has the same precedence as unary signs, below exponentiation.
            left = self.expression(25).bitwise("~")
        elif token == "(":
            left = self.expression()
            self.expect(")")
        elif token == "[" and not self.unit_only:
            elements = []
            if self.peek()[1] != "]":
                while True:
                    element = self.expression()
                    if element.dims != ZERO or not isinstance(element.value, sp.Expr):
                        raise CalcError("Solution lists must contain dimensionless scalar expressions.")
                    elements.append(element.value)
                    if self.peek()[1] != ",":
                        break
                    self.take()
            self.expect("]")
            left = Quantity(sp.Tuple(*elements))
        elif kind == "unit":
            unit = self.calculator.registry.get(token)
            if self.unit_only and unit.constant:
                raise CalcError("A physical constant is not a conversion target.")
            left = Quantity(unit.scale + (0 if self.unit_only else unit.offset), unit.dims, unit)
        elif kind == "name" and not self.unit_only and token not in BITWISE:
            if self.peek()[1] == "(" and (token in FUNCTIONS or token in EQUATION_NAMES):
                self.take()
                args = []
                if self.peek()[1] != ")":
                    while True:
                        args.append(self.expression())
                        if self.peek()[1] != ",":
                            break
                        self.take()
                self.expect(")")
                if token in EQUATION_NAMES:
                    left = self.calculator.equation(token, args, self.equation_stack,
                                                    self.validating_equation)
                else:
                    left = self.calculator.function(token, args)
            elif token in EQUATION_NAMES:
                raise CalcError(f"Use {token}(expression) to call an equation.")
            elif token in RESERVED:
                left = Quantity(RESERVED[token])
            elif token == "ans":
                left = Quantity(sp.Symbol("ans")) if self.validating_equation else self.calculator.answer
            else:
                # Unassigned names remain symbolic rather than being treated as errors.
                left = self.local_variables.get(token,
                    self.calculator.variables.get(token, Quantity(sp.Symbol(token))))
        else:
            raise CalcError(f"Expected a number, variable, unit, or parenthesis; found '{token or 'end of input'}'.")

        # Extend the operand with suffixes and operators until a weaker operator
        # or a delimiter belongs to the enclosing expression.
        while True:
            kind, token = self.peek()
            if kind == "unit" and minimum <= 40:
                self.take()
                unit = self.calculator.registry.get(token)
                if not isinstance(left.value, sp.Expr):
                    raise CalcError("A unit suffix requires a scalar expression.")
                if left.dims != ZERO:
                    raise CalcError("Use * or / between units, for example 3_m/_s.")
                if self.peek()[1] in ("^", "**"):
                    # In 2_m^2, only the unit is squared; (2_m)^2 squares the value too.
                    if unit.offset:
                        raise CalcError("Offset temperature units cannot be raised to powers.")
                    self.take()
                    exponent = self.expression(29)
                    unit_value = Quantity(unit.scale, unit.dims, unit).arithmetic("^", exponent)
                    left = Quantity(left.value * unit_value.value, unit_value.dims, unit_value.display)
                else:
                    left = Quantity(left.value * unit.scale + unit.offset, unit.dims, unit)
                continue
            if token == "!" and minimum <= 40:
                self.take()
                left = self.calculator.function("factorial", [left])
                continue
            if token in COMPARISONS and minimum <= 5 and not self.unit_only:
                # Compare adjacent operands in a chain, after all arithmetic.
                previous = left
                result = True
                while self.peek()[1] in COMPARISONS:
                    op = self.take()[1]
                    right = self.expression(6)
                    # Evaluate every pair, even after False, to keep reporting bad operands.
                    comparison = previous.compare(op, right)
                    result = result and comparison.value is sp.true
                    previous = right
                left = Quantity(sp.true if result else sp.false)
                continue
            # Arithmetic binds before shifts, AND, XOR, and OR; all bind before
            # comparisons. Infix xor is recognized before implicit multiplication.
            precedence = {"|": 6, "xor": 7, "&": 8, "<<": 9, ">>": 9,
                          "+": 10, "-": 10, "*": 20, "/": 20, "%": 20, "^": 30, "**": 30}.get(token)
            implicit = False
            if precedence is None and (kind in ("number", "name") or token == "(") and not self.unit_only:
                # Adjacent operands such as 2(x+1) imply multiplication.
                precedence, token, implicit = 20, "*", True
            if precedence is None or precedence < minimum:
                break
            if token in BITWISE and self.unit_only:
                raise CalcError("Bitwise operators cannot be used in conversion targets.")
            if not implicit:
                self.take()
            # Equal precedence on the right makes powers associate right to left.
            # Other operators use a higher threshold so they associate left to right.
            right = self.expression(precedence if token in ("^", "**") else precedence + 1)
            left = left.bitwise(token, right) if token in BITWISE else left.arithmetic("^" if token == "**" else token, right)
        return left.checked()


@dataclass(frozen=True)
class HistoryEntry:
    # Store display strings so history can be restored without executing expressions.
    source: str
    result: str
    is_error: bool = False

    @property
    def line(self):
        return f"{self.source} = {'Error: ' if self.is_error else ''}{self.result}"


# Calculation engine: session variables, exact answers, and evaluation settings.
class Calculator:
    def __init__(self, mode="radian", precision=50, output_mode="exact"):
        self.registry = UnitRegistry()
        self.variables = {}
        self.equations = {}
        self.unchecked_equations: set[str] = set()
        self.history = deque(maxlen=30)
        self.answer = Quantity(sp.S.Zero)
        self.unit_definitions = {}
        self.set_mode(mode)
        self.set_precision(precision)
        self.set_output_mode(output_mode)

    def set_mode(self, mode):
        mode = {"rad": "radian", "deg": "degree"}.get(mode, mode)
        if mode not in ("radian", "degree"):
            raise CalcError("Mode must be radian or degree.")
        self.mode = mode

    def set_precision(self, precision):
        if isinstance(precision, bool) or not isinstance(precision, int) or precision < 2:
            raise CalcError("Precision must be an integer of at least 2 significant digits.")
        self.precision = precision

    def set_output_mode(self, mode):
        mode = "approximate" if mode == "approx" else mode
        if mode not in ("exact", "approximate"):
            raise CalcError("Output mode must be exact or approximate.")
        self.output_mode = mode

    def format(self, quantity, approximate=False):
        # The output preference affects presentation rather than stored precision.
        precision = self.precision if approximate or self.output_mode == "approximate" else None
        return self.registry.format(quantity, precision=precision)

    def parse(self, text, **context):
        # Translate library/parser failures into errors suitable for all UI modes.
        try:
            return Parser(self, normalize_input(text), **context).parse()
        except CalcError:
            raise
        except (ValueError, TypeError, ZeroDivisionError, RecursionError, OverflowError, NotImplementedError) as exc:
            raise CalcError(f"Cannot evaluate this expression: {exc}") from None

    def evaluate(self, text, record=True, *, approximate=False):
        # Failed input is recorded here; only successful evaluation updates ans.
        source = text.strip()
        try:
            return self._evaluate(source, record, approximate)
        except CalcError as exc:
            if record and source:
                # Keep invalid input verbatim, including malformed numeric literals.
                self.history.append(HistoryEntry(source, str(exc), is_error=True))
            raise

    def _evaluate(self, source, record, approximate=False):
        # Peel off assignment and conversion arrows before parsing the expression.
        # This also permits a conversion followed by assignment, such as 3_in=>_ft->x.
        text = normalize_input(source)
        if not text:
            raise CalcError("Enter an expression.")
        assignment = None
        if "->" in text:
            if text.count("->") != 1:
                raise CalcError("Use one assignment arrow per calculation.")
            text, assignment = (part.strip() for part in text.split("->"))
            if not re.fullmatch(r"[^\W\d_][^\W_]*", assignment, re.UNICODE):
                raise CalcError("A variable name starts with a letter and contains letters or digits.")
            if (assignment in RESERVED or assignment in FUNCTIONS or assignment in BITWISE
                    or assignment in EQUATION_NAMES or assignment == "ans"):
                raise CalcError(f"'{assignment}' is reserved.")
        if "=>" in text:
            if text.count("=>") != 1:
                raise CalcError("Use one conversion arrow per calculation.")
            expression, target_text = (part.strip() for part in text.split("=>"))
            value = self.parse(expression)
            if not isinstance(value.value, sp.Expr):
                raise CalcError("Unit conversion requires a scalar expression.")
            # A simple offset target must be handled before compound-unit parsing.
            if re.fullmatch(r"_°?[^\W\d_][^\W_]*", target_text):
                target = self.registry.get(target_text)
                if target.constant:
                    raise CalcError("A physical constant is not a conversion target.")
            else:
                try:
                    parsed = Parser(self, target_text, unit_only=True).parse()
                except (ValueError, TypeError, RecursionError) as exc:
                    raise CalcError(str(exc)) from None
                if parsed.affine:
                    raise CalcError("Offset temperature units cannot appear in compound targets.")
                if parsed.value.is_number is not True or parsed.value.is_positive is not True:
                    raise CalcError("A conversion target must have a positive numeric scale.")
                target = Unit(target_text, "compound unit", "Compound", parsed.value, parsed.dims)
            if value.dims != target.dims:
                raise CalcError("The source and target units have different dimensions.")
            # Converting changes the display unit; the underlying SI value stays exact.
            value = replace(value, display=target)
        else:
            value = self.parse(text)
        value.checked()
        # Finish preparing history before committing the result to ans or a variable.
        entry = HistoryEntry(decimal_literals(source, self.registry), self.format(value, approximate=approximate)) if record else None
        if assignment:
            self.variables[assignment] = value
        self.answer = value
        if entry is not None:
            self.history.append(entry)
        return value

    def calculate(self, text, *, approximate=False):
        return self.format(self.evaluate(text, approximate=approximate), approximate=approximate)

    def define_equation(self, name, expression):
        """Validate a formula without changing ans, history, or session variables."""
        if name not in EQUATION_NAMES:
            raise CalcError("Equation names must be y1 through y99.")
        if not isinstance(expression, str):
            raise CalcError("Equation definitions must be strings.")
        expression = expression.strip()
        if not expression:
            self.equations.pop(name, None)
            self.unchecked_equations.discard(name)
            return
        value = self.parse(expression, local_variables={"x": Quantity(sp.Symbol("x"))},
                           validating_equation=True)
        if not isinstance(value.value, sp.Expr):
            raise CalcError("An equation must produce a scalar expression.")
        if self.equations.get(name) != expression:
            self.unchecked_equations.discard(name)
        self.equations[name] = expression

    def equation(self, name, args, stack=(), validating=False):
        if len(args) != 1:
            raise CalcError(f"Wrong number of arguments for {name}; use {name}(x).")
        argument = args[0]
        if not isinstance(argument.value, sp.Expr) or argument.dims != ZERO:
            raise CalcError(f"{name} requires a dimensionless scalar argument.")
        if validating:
            # Forward references are allowed; resolve formulas when called.
            # SymPy's dynamic function factory produces an applied expression here.
            return Quantity(cast(sp.Expr, sp.Function(name)(argument.value)))
        if name not in self.equations:
            raise CalcError(f"{name}(x) is not defined. Use F7 to enter an equation.")
        if name in stack:
            raise CalcError("Circular equation reference: " + " -> ".join((*stack, name)))
        return self.parse(self.equations[name], local_variables={"x": argument},
                          equation_stack=(*stack, name))

    def define_unit(self, name, expression):
        # A custom unit supplies an SI scale and dimensions from a numeric expression.
        name = name.removeprefix("_")
        if not re.fullmatch(r"°?[^\W\d_][^\W_]*", name, re.UNICODE):
            raise CalcError("A unit name starts with a letter (optionally °) and contains letters or digits.")
        if unit_key(name) in self.registry.units:
            raise CalcError(f"Unit _{name} already exists (unit names ignore case).")
        value = self.parse(expression)
        if value.affine or value.value.free_symbols or value.value.is_positive is not True:
            raise CalcError("Define a unit using a positive, finite, numeric quantity without a temperature offset.")
        self.registry.add(name, "user-defined: " + expression, "Custom", value.value, value.dims)
        # Store the evaluated scale, so saved units do not depend on session variables.
        definition = self.registry.format(replace(value, display=None))
        self.unit_definitions[name] = definition

    def function(self, name, args):
        # Validate argument counts and types before dispatching allowed SymPy operations.
        arities = {"log": (1, 2), "diff": (2, 3), "integrate": (2, 4), "solve": (2,), "subs": (3,), "approx": (1, 2), "min": None, "max": None}
        accepted = arities.get(name, (1,))
        if (accepted is None and not args) or (accepted is not None and len(args) not in accepted):
            raise CalcError(f"Wrong number of arguments for {name}.")
        if any(not isinstance(a.value, sp.Expr) for a in args):
            raise CalcError(f"{name} requires scalar arguments.")
        first = args[0]
        if name in ("simplify", "expand", "factor", "abs"):
            fn = sp.Abs if name == "abs" else getattr(sp, name)
            return replace(first, value=fn(first.value)).checked()
        if name == "approx":
            digits = self.precision
            if len(args) == 2:
                if args[1].dims != ZERO or args[1].value.is_Integer is not True or args[1].value < 2:
                    raise CalcError("approx precision must be an integer of at least 2.")
                digits = int(args[1].value)
            # Only this explicit operation introduces arbitrary-precision Float values.
            return replace(first, value=sp.N(first.value, digits)).checked()
        if name in ("sqrt", "cbrt"):
            result = first.arithmetic("^", Quantity(sp.Rational(1, 2 if name == "sqrt" else 3)))
            if name == "cbrt" and first.value.is_real is True:
                result = replace(result, value=sp.real_root(first.value, 3))
            return result
        if name in ("min", "max"):
            if any(a.dims != first.dims for a in args):
                raise CalcError("min/max arguments must have the same dimensions.")
            return replace(first, value=(sp.Min if name == "min" else sp.Max)(*(a.value for a in args))).checked()
        if name == "subs":
            if not isinstance(args[1].value, sp.Symbol) or args[1].dims != ZERO or args[2].dims != ZERO:
                raise CalcError("Use subs(expression, unassigned_variable, dimensionless_value).")
            return replace(first, value=first.value.subs(args[1].value, args[2].value)).checked()
        # Calculus and solving require a symbolic variable, rather than its assigned value.
        if name in ("diff", "integrate", "solve"):
            if args[1].dims != ZERO or not isinstance(args[1].value, sp.Symbol):
                raise CalcError("The second argument must be an unassigned symbolic variable.")
            symbol = args[1].value
            if name == "diff":
                order = 1
                if len(args) == 3:
                    if args[2].dims != ZERO or args[2].value.is_Integer is not True or args[2].value < 0:
                        raise CalcError("Derivative order must be a nonnegative integer.")
                    order = int(args[2].value)
                value = sp.diff(first.value, symbol, order)
            elif name == "integrate":
                if len(args) == 4:
                    if any(a.dims != ZERO for a in args[2:]):
                        raise CalcError("Integration bounds must be dimensionless.")
                    value = sp.integrate(first.value, (symbol, args[2].value, args[3].value))
                else:
                    value = sp.integrate(first.value, symbol)
            else:
                return Quantity(sp.Tuple(*sp.solve(first.value, symbol))).checked()
            return replace(first, value=value).checked()
        if any(a.dims != ZERO for a in args):
            raise CalcError(f"{name} requires dimensionless arguments.")
        value = first.value
        # SymPy uses radians, so degree mode converts inputs and inverse-trig outputs.
        if name in ("sin", "cos", "tan") and self.mode == "degree":
            value *= sp.pi / 180
        if name == "factorial":
            if value.is_Integer is not True or value < 0:
                raise CalcError("Factorial requires a nonnegative integer.")
            result = sp.factorial(value)
        elif name == "log":
            result = sp.log(value, args[1].value) if len(args) == 2 else sp.log(value, 10)
        else:
            fn = {"ln": sp.log, "ceil": sp.ceiling}.get(name, getattr(sp, name, None))
            if fn is None:
                raise CalcError(f"Unknown function: {name}")
            result = fn(value)
        if name in ("asin", "acos", "atan") and self.mode == "degree":
            result *= 180 / sp.pi
        if not isinstance(result, sp.Expr):
            raise CalcError(f"{name} did not produce a scalar result.")
        return Quantity(result).checked()


# Menus are plain data: an item inserts text, runs a ':' command, or has child items.
# The same structure is used for built-in menus and saved JSON configuration.
SYMBOLS = [
    ("ε", "epsilon"), ("μ", "mu"), ("Ω", "omega (uppercase)"), ("π", "pi"),
    ("θ", "theta"), ("α", "alpha"), ("β", "beta"), ("γ", "gamma"),
    ("δ", "delta"), ("λ", "lambda"), ("σ", "sigma"), ("φ", "phi"),
    ("τ", "tau"), ("ω", "omega"), ("Δ", "delta (uppercase)"), ("Σ", "sigma (uppercase)"),
    ("Φ", "phi (uppercase)"), ("°", "degree sign"), ("Å", "angstrom"),
    ("→", "assignment arrow"), ("⇒", "conversion arrow"), ("×", "multiply"), ("÷", "divide"),
]


def insert_item(label, text):
    return {"label": label, "insert": text}


def command_item(label, command):
    return {"label": label, "command": command}


def output_options():
    return [command_item("Exact output", ":format exact"), command_item("Approximate output", ":format approximate")]


def categorize_unit_items(registry, items):
    """Group unit insertion items, preserving other actions and existing submenus."""
    result = []
    categories = {item["label"]: item for item in items if "items" in item}
    for item in items:
        text = item.get("insert", "")
        unit = registry.units.get(unit_key(text)) if text.startswith("_") else None
        if "items" in item or unit is None or unit.constant:
            result.append(item)
            continue
        if unit.category not in categories:
            category = {"label": unit.category, "items": []}
            categories[unit.category] = category
            result.append(category)
        # Older configurations included the category in each unit's label.
        child = dict(item)
        child["label"] = child["label"].removeprefix(unit.category + ": ")
        categories[unit.category]["items"].append(child)
    return result


def filter_menu_items(items, query):
    """Keep matching categories, or only matching descendants within a category."""
    result = []
    for item in items:
        if query in item["label"].casefold():
            result.append(item)
        elif "items" in item:
            children = filter_menu_items(item["items"], query)
            if children:
                result.append({**item, "items": children})
    return result


def problem_menu():
    return {"label": "Problems", "items": [command_item("New Problem", ":problem new"),
            command_item("Open Problem", ":problem open"), command_item("Delete Problem", ":problem delete")]}


def cleanup_menu():
    return {"label": "Clean Up", "items": [command_item("Clear set variables", ":clearvars"),
            command_item("Clear history", ":clear")]}


def catalog_items(calculator, menus):
    """Build insertion choices from the parser's allowlists and current registry."""
    signatures = {"approx": "expression[, digits]", "diff": "expression, variable[, order]",
                  "integrate": "expression, variable[, lower, upper]", "solve": "expression, variable",
                  "subs": "expression, variable, value", "log": "x[, base]", "min": "x, ...", "max": "x, ..."}
    entries = {name + "(": insert_item(f"{name}({signatures.get(name, 'x')}) - function", name + "(")
               for name in FUNCTIONS}
    for name in EQUATION_NAMES:
        description = calculator.equations.get(name, "undefined; set in F7")
        entries[name + "("] = insert_item(f"{name}(x) - {description}", name + "(")
    for symbol, label in SYMBOLS:
        entries[symbol] = insert_item(f"{label} ({symbol}) - symbol", symbol)
    for symbol in map(chr, TRANSLATE):
        entries.setdefault(symbol, insert_item(f"{unicodedata.name(symbol).lower()} ({symbol}) - symbol", symbol))
    for name in (*RESERVED, "ans"):
        entries.setdefault(name, insert_item(name + " - built-in value", name))
    operators = {"+": "addition", "-": "subtraction", "*": "multiplication", "/": "division",
                 "^": "power", "**": "power (alternate)", "%": "remainder", "!": "factorial suffix",
                 "&": "bitwise AND", "|": "bitwise OR", "xor": "bitwise XOR", "~": "bitwise NOT",
                 "<<": "shift left", ">>": "shift right", "<": "less than", ">": "greater than",
                 "<=": "less than or equal", ">=": "greater than or equal", "=": "equality",
                 "==": "equality (alternate)", "!=": "not equal", "->": "assignment", "=>": "conversion",
                 "(": "parenthesis open", ")": "parenthesis close", "[": "list open", "]": "list close",
                 ",": "argument separator"}
    for symbol, label in operators.items():
        entries[symbol] = insert_item(f"{label} ({symbol}) - operator", symbol)
    for unit in calculator.registry.units.values():
        kind = "constant" if unit.constant else "unit"
        entries[unit.notation] = insert_item(f"{unit.label} ({unit.notation}) - {kind}", unit.notation)

    def custom_symbols(items):
        for item in items:
            if "items" in item:
                custom_symbols(item["items"])
            symbol = item.get("insert", "")
            if len(symbol) == 1 and symbol.isprintable() and not symbol.isspace():
                entries.setdefault(symbol, insert_item(item["label"] + " - symbol", symbol))

    for menu in menus:
        custom_symbols(menu["items"])
    return sorted(entries.values(), key=lambda item: (item["label"].casefold(), item["label"]))


def default_menus(registry):
    # Build F1-F6 from the current registry, including any loaded custom units.
    units = sorted((u for u in registry.units.values() if not u.constant), key=lambda u: (u.category, u.name))
    constants = [u for u in registry.units.values() if u.constant]
    return [
        {"label": "Math", "items": [insert_item(n, n + "(") for n in
         ("sqrt", "sin", "cos", "tan", "ln", "log", "abs", "simplify", "expand", "factor", "diff", "integrate", "solve", "subs", "approx")]
         + [insert_item("pi", "π"), insert_item("Assign ->", "->"), insert_item("Convert =>", "=>")]},
        {"label": "Units", "items": categorize_unit_items(registry, [insert_item(f"{u.notation} {u.label}", u.notation) for u in units])
         + [insert_item("Define a unit", ":unit smoot = 1.7018_m")]},
        {"label": "Constants", "items": [insert_item(u.notation + " " + u.label, u.notation) for u in constants]},
        {"label": "Symbols", "items": [insert_item(s + " " + label, s) for s, label in SYMBOLS]},
        {"label": "Options", "items": [command_item("Radian mode", ":mode radian"), command_item("Degree mode", ":mode degree"),
         *output_options(),
         problem_menu(),
         command_item("Select result first", ":recall result"), command_item("Select expression first", ":recall expression"),
         insert_item("Set precision", ":precision 100"), insert_item("Rename a menu", ":menu 1 Math"),
         insert_item("Add menu item", ":menuadd 1 Square | ^2"), command_item("Save configuration", ":save"),
         command_item("Quit", ":quit")]},
        {"label": "Help", "items": [command_item("Keyboard help", ":help"), command_item("Catalog", ":catalog"),
         insert_item("Exact decimal example", "0.1 + 0.2"), insert_item("Conversion example", "3_in=>_ft"),
         insert_item("Assignment example", "3->x"), insert_item("Symbolic example", "expand((y+1)^2)"),
         insert_item("Derivative example", "diff(y^3,y)"), insert_item("Custom unit example", ":unit smoot = 1.7018_m")]},
    ]


def validate_menus(menus):
    # Validate the full tree before installing it; cap nesting to prevent runaway recursion.
    if not isinstance(menus, list) or len(menus) != 6:
        raise CalcError("Configuration must contain exactly six menus (F1 to F6).")
    def validate_items(entries, depth=0):
        if not isinstance(entries, list):
            raise CalcError("Each menu or submenu needs an items list.")
        if depth > 8:
            raise CalcError("Menus can nest at most eight submenus deep.")
        items = []
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get("label"), str) or not item["label"].strip():
                raise CalcError("Each menu item needs a nonempty label.")
            actions = [key for key in ("insert", "command", "items") if key in item]
            if len(actions) != 1:
                raise CalcError("Each item needs exactly one action: insert, command, or submenu items.")
            action = actions[0]
            if action == "items":
                items.append({"label": item["label"], "items": validate_items(item["items"], depth + 1)})
                continue
            if not isinstance(item[action], str):
                raise CalcError("Insert and command actions must be strings.")
            if action == "command" and not item["command"].startswith(":"):
                raise CalcError("Menu commands must start with ':'.")
            items.append(dict(item))
        return items

    result = []
    for menu in menus:
        if not isinstance(menu, dict) or not isinstance(menu.get("label"), str) or not menu["label"].strip():
            raise CalcError("Each menu needs a nonempty label.")
        result.append({"label": menu["label"], "items": validate_items(menu.get("items"))})
    return result


HELP_LINES = [
    "Up/Down: select history results/expressions; Enter: insert the highlighted part.",
    "Shift+Enter in input: approximate this result; the configured output mode stays unchanged.",
    "After calculation: input stays selected; type to replace; Backspace/Delete clears.",
    "Left/Right on selected input: move to the beginning/end for editing.",
    "Shift+Left/Right: select part of the input; type or Backspace/Delete replaces it.",
    "Left/Right: move cursor; Home/End: line ends; Tab: input/history focus.",
    "Esc: close menu or return to input; Ctrl+C / Ctrl+D: quit; Ctrl+L: redraw.",
    "F1-F6: menus; Up/Down or PageUp/PageDown: select; Enter: choose.",
    "F7: equations y1-y99; Enter saves; Up/Down selects; Esc cancels current edit.",
    "Enter 4x for y1(x); return with F7 and calculate y1(3) to get 12.",
    "Ctrl+T in F7: check/uncheck a formula for the F8 table; new formulas are checked.",
    "F8: table; Tab: set start/step; Enter: apply; arrows/PageUp/PageDown: scroll.",
    "F9 Clean Up: clear set variables or the current Problem's history.",
    "F6 > Catalog: all functions/symbols; type to filter; Enter inserts; Esc closes.",
    "Type in a menu to filter; Backspace removes a filter character.",
    "Submenus: Enter/Right opens; Right on a leaf switches menus; Left/Esc goes back.",
    "3->x assigns x; x/X differ; _ft/_FT are the same unit.",
    "Comparisons: < > <= >= = == != return True or False; 3>6 is False.",
    "Bitwise integers: & | xor ~ << >>; 5 xor 3 is 6; ^ remains exponentiation.",
    "3_in=>_ft converts; 3_m/_s=>_kph; 2_m^2 is 2 square meters.",
    ":unit smoot = 1.7018_m    :mode degree    :precision 100",
    ":format exact|approximate sets default output; :precision sets decimal digits.",
    ":menu 1 Favorites    :menuadd 1 Square | ^2    :menuclear 1",
    ":recall result|expression    :unset x    :vars    :clearvars    :clear    :save    :quit",
    "Decimals/fractions stay exact; approx(pi,100) requests a decimal approximation.",
    "Equations and Problems save automatically; F5 > Problems: new/open/delete.",
    "Settings, custom units, and six menus are saved using :save.",
]


class ConsoleApp:
    """UI state and input handling, independent of the terminal for unit testing."""

    def __init__(self, calculator=None, config_path=None):
        self.calculator = calculator or Calculator()
        self.config_path = Path(config_path) if config_path else Path(__file__).with_name("calc_term_config.json")
        self.history_path = self.config_path.with_suffix(".history.json")
        self.problems_path = self.config_path.with_suffix(".problems.json")
        self.problem_name = "Default"
        self.problems: dict[str, dict] = {}
        self._saved_problems = ""
        self._problems_load_failed = False
        self.problem_dialog: str | None = None
        self.problem_dialog_text = ""
        self.problem_dialog_cursor = 0
        self.problem_dialog_index = 0
        self.problem_delete_name = ""
        self.problem_delete_confirm = False
        self.catalog_open = False
        self.catalog_entries: list[dict[str, str]] = []
        self.catalog_filter = ""
        self.catalog_index = 0
        self.catalog_rows = 15
        self._saved_history: tuple[HistoryEntry, ...] = ()
        self.menus = default_menus(self.calculator.registry)
        # Editing and history selection are separate: browsing must not move the cursor.
        self.text = ""
        self.cursor = 0
        self._selected_input: str | None = None
        self._selection_anchor: int | None = None
        self.history_index = None
        self.history_rows = 17  # Default 24-row terminal, minus menus and footer.
        self.history_start = 0
        self.history_part = "result"
        self.history_insert = "result"
        # open_menu selects F1-F6 or F9 (index 8); the stack remembers parent selection
        # and filter so Left/Esc can restore the exact navigation state.
        self.open_menu = None
        self.menu_index = 0
        self.menu_filter = ""
        self.menu_stack: list[tuple[dict, int, str]] = []
        self.equation_open = False
        self.equation_index = 0
        self.equation_text = ""
        self.equation_cursor = 0
        self.table_open = False
        self.table_start = "0"
        self.table_step = "1"
        self.table_row = 0
        self.table_column = 0
        self.table_edit_field: int | None = None
        self.table_fields = ["0", "1"]
        self.table_cursor = 0
        self.shift_pressed = False
        self.message = "F7: equations | F8: table | F6: help | Enter: calculate | :quit: exit"
        self.help_open = False
        self.running = True
        self._load_config()
        self._load_history()
        self._load_problems()

    @staticmethod
    def history_entries(data) -> list[HistoryEntry]:
        if not isinstance(data, list):
            raise CalcError("History must be a list of calculations.")
        entries = []
        for item in data:
            if not isinstance(item, dict) or any(
                not isinstance(item.get(key), str) or not item[key].strip()
                for key in ("source", "result")
            ):
                raise CalcError("Each history entry needs source and result strings.")
            if not isinstance(item.get("is_error", False), bool):
                raise CalcError("History is_error must be true or false.")
            entries.append(HistoryEntry(item["source"], item["result"], item.get("is_error", False)))
        return entries

    def problem_snapshot(self):
        return {"equations": dict(self.calculator.equations),
                "unchecked_equations": sorted(self.calculator.unchecked_equations, key=EQUATION_NAMES.index),
                "table": {"start": self.table_start, "step": self.table_step},
                "history": [{"source": entry.source, "result": entry.result,
                             **({"is_error": True} if entry.is_error else {})}
                            for entry in self.calculator.history]}

    @staticmethod
    def validate_problem_name(name):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80 or not name.isprintable():
            raise CalcError("Use a Problem name of 1 to 80 printable characters.")
        return name.strip()

    def prepare_problem(self, data):
        if not isinstance(data, dict):
            raise CalcError("Each Problem must be an object.")
        # Restore definitions, not old calculations or session variable assignments.
        calculator = Calculator(self.calculator.mode, self.calculator.precision, self.calculator.output_mode)
        calculator.registry = self.calculator.registry
        calculator.unit_definitions = dict(self.calculator.unit_definitions)
        equations = data.get("equations", {})
        if not isinstance(equations, dict):
            raise CalcError("Problem equations must map names to expressions.")
        for name, expression in equations.items():
            calculator.define_equation(name, expression)
        unchecked = data.get("unchecked_equations", [])
        if not isinstance(unchecked, list) or any(
            not isinstance(name, str) or name not in calculator.equations for name in unchecked
        ):
            raise CalcError("Problem unchecked_equations must list defined equations.")
        calculator.unchecked_equations = set(unchecked)
        entries = self.history_entries(data.get("history", []))
        calculator.history = deque(entries, maxlen=max(30, len(entries)))
        table = data.get("table", {})
        if not isinstance(table, dict):
            raise CalcError("Problem table must be an object.")
        start, step = self.validate_table_settings(calculator, table.get("start", "0"), table.get("step", "1"))
        return calculator, start, step

    @staticmethod
    def problems_document(problems, active):
        return json.dumps({"version": 1, "active": active, "problems": problems},
                          indent=2, ensure_ascii=False) + "\n"

    def _load_problems(self):
        self.problems = {"Default": self.problem_snapshot()}
        self._saved_problems = self.problems_document(self.problems, self.problem_name)
        try:
            data = json.loads(self.problems_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise CalcError("Unsupported Problems file format.")
            problems, active = data.get("problems"), data.get("active")
            if not isinstance(problems, dict) or "Default" not in problems:
                raise CalcError("Problems must include the Default Problem.")
            if not isinstance(active, str) or active not in problems:
                raise CalcError("The active Problem does not exist.")
            names = set()
            prepared = {}
            for name, state in problems.items():
                if self.validate_problem_name(name) != name or name.casefold() in names:
                    raise CalcError("Problem names must be unique and have no surrounding spaces.")
                names.add(name.casefold())
                prepared[name] = self.prepare_problem(state)
            self.problems = problems
            self._apply_problem(active, prepared[active])
            self._saved_problems = self.problems_document(problems, active)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as exc:
            self._problems_load_failed = True
            self.message += f" | Problems load error: {exc} (original file preserved)"

    def _write_problems(self, problems, active):
        if self._problems_load_failed:
            raise CalcError("Cannot save Problems while their file has a load error; original file preserved.")
        document = self.problems_document(problems, active)
        if document != self._saved_problems:
            temporary = self.problems_path.with_name(self.problems_path.name + ".tmp")
            try:
                temporary.write_text(document, encoding="utf-8")
                temporary.replace(self.problems_path)
            except OSError as exc:
                raise CalcError(f"Cannot save Problems: {exc}") from None
        self.problems = problems
        self._saved_problems = document

    def save_problems(self):
        try:
            self._write_problems({**self.problems, self.problem_name: self.problem_snapshot()}, self.problem_name)
        except CalcError as exc:
            self.message = self.message.split(" | Problem save error:", 1)[0] + f" | Problem save error: {exc}"
            return False
        self.message = self.message.split(" | Problem save error:", 1)[0]
        return True

    def _apply_problem(self, name, prepared):
        self.calculator, self.table_start, self.table_step = prepared
        self.problem_name = name
        self._saved_history = tuple(self.calculator.history)
        self.clear_input()
        self.history_index, self.history_start = None, 0
        self.equation_open, self.table_open, self.help_open = False, False, False
        self.catalog_open = False
        self.equation_index, self.table_row, self.table_column = 0, 0, 0
        self.table_edit_field = None
        self.open_menu = None
        self.menu_stack.clear()

    def new_problem(self, name):
        name = self.validate_problem_name(name)
        if any(existing.casefold() == name.casefold() for existing in self.problems):
            raise CalcError("A Problem with that name already exists.")
        prepared = self.prepare_problem({})
        if not self.save_history():
            raise CalcError("Current Problem could not be saved; staying in it.")
        state = {"equations": {}, "history": [], "unchecked_equations": [], "table": {"start": "0", "step": "1"}}
        self._write_problems({**self.problems, name: state}, name)
        self._apply_problem(name, prepared)
        self.message = "Created Problem: " + name

    def open_problem(self, name):
        if name not in self.problems:
            raise CalcError("No Problem named " + name)
        if not self.save_history():
            raise CalcError("Current Problem could not be saved; staying in it.")
        prepared = self.prepare_problem(self.problems[name])
        self._write_problems(self.problems, name)
        self._apply_problem(name, prepared)
        self.message = "Opened Problem: " + name

    def _delete_confirmed_problem(self):
        name = self.problem_delete_name
        if name == "Default" or name not in self.problems:
            raise CalcError("Choose a saved Problem to delete; Default is kept.")
        if not self.save_history():
            raise CalcError("Current Problem could not be saved; deletion canceled.")
        active = "Default" if name == self.problem_name else self.problem_name
        prepared = self.prepare_problem(self.problems[active]) if name == self.problem_name else None
        remaining = {key: state for key, state in self.problems.items() if key != name}
        self._write_problems(remaining, active)
        if prepared is not None:
            self._apply_problem(active, prepared)
        self.message = "Deleted Problem: " + name

    def save_session(self):
        # A valid formula still being edited should survive a normal app exit.
        if self.equation_open:
            self.commit_equation()
        if self.table_edit_field is not None:
            self.commit_table_settings()
        return self.save_history()

    def _load_history(self):
        # History is display-only data; restoring it does not recreate variables or ans.
        try:
            data = json.loads(self.history_path.read_text(encoding="utf-8"))
            entries = self.history_entries(data)
            # Keep all saved entries until the first frame applies the terminal's limit.
            self.calculator.history = deque(entries, maxlen=max(30, len(entries)))
            self._saved_history = tuple(entries)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as exc:
            self.message += f" | History load error: {exc} (original file preserved)"

    def save_history(self, force=False):
        """Save changed history atomically; a write error must not undo a calculation."""
        entries = tuple(self.calculator.history)
        if not force and entries == self._saved_history:
            return self.save_problems()
        if self.problem_name != "Default":
            if not self.save_problems():
                return False
            self._saved_history = entries
            return True
        temporary = self.history_path.with_name(self.history_path.name + ".tmp")
        try:
            data = [{"source": entry.source, "result": entry.result,
                     **({"is_error": True} if entry.is_error else {})} for entry in entries]
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.history_path)
        except OSError as exc:
            self.message = self.message.split(" | History save error:", 1)[0] + f" | History save error: {exc}"
            return False
        self._saved_history = entries
        self.message = self.message.split(" | History save error:", 1)[0]
        return self.save_problems()

    def _load_config(self):
        # Prepare a separate calculator and menu tree, committing them only when valid.
        if not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise CalcError("Configuration must be a JSON object.")
            calculator = Calculator(data.get("mode", "radian"), data.get("precision", 50), data.get("output_mode", "exact"))
            recall = data.get("history_insert", "result")
            if recall not in ("result", "expression"):
                raise CalcError("history_insert must be result or expression.")
            definitions = data.get("units", {})
            if not isinstance(definitions, dict):
                raise CalcError("units must be an object mapping names to expressions.")
            # Resolve custom units even if a hand-edited JSON file lists dependencies later.
            pending = dict(definitions)
            while pending:
                progress = False
                for name, expression in list(pending.items()):
                    if not isinstance(expression, str):
                        raise CalcError("Custom unit definitions must be strings.")
                    try:
                        calculator.define_unit(name, expression)
                    except CalcError:
                        continue
                    del pending[name]
                    progress = True
                if not progress:
                    raise CalcError("Invalid or circular custom unit definitions: " + ", ".join(pending))
            equations = data.get("equations", {})
            if not isinstance(equations, dict):
                raise CalcError("equations must be an object mapping y1-y99 to expressions.")
            for name, expression in equations.items():
                calculator.define_equation(name, expression)
            unchecked = data.get("unchecked_equations", [])
            if not isinstance(unchecked, list) or any(
                not isinstance(name, str) or name not in calculator.equations for name in unchecked
            ):
                raise CalcError("unchecked_equations must list defined equation names.")
            calculator.unchecked_equations = set(unchecked)
            table = data.get("table", {})
            if not isinstance(table, dict):
                raise CalcError("table must be an object with start and step expressions.")
            start, step = self.validate_table_settings(calculator, table.get("start", "0"), table.get("step", "1"))
            menus = validate_menus(data["menus"]) if "menus" in data else default_menus(calculator.registry)
            if "menus" in data and not any("items" in item for item in menus[1]["items"]):
                menus[1]["items"] = categorize_unit_items(calculator.registry, menus[1]["items"])
            if menus[4]["label"] == "Options":
                for option in output_options():
                    if not any(item.get("command") == option["command"] for item in menus[4]["items"]):
                        menus[4]["items"].append(option)
            if not any(item.get("label") == "Problems" and "items" in item for item in menus[4]["items"]):
                menus[4]["items"].append(problem_menu())
            # Older settings included the built-in history action under Options.
            menus[4]["items"] = [item for item in menus[4]["items"] if item.get("command") != ":clear"]
            if not any(item.get("command") == ":catalog" for item in menus[5]["items"]):
                menus[5]["items"].append(command_item("Catalog", ":catalog"))
            self.calculator = calculator
            self.history_insert = recall
            self.menus = menus
            self.table_start, self.table_step = start, step
        except (OSError, ValueError, TypeError) as exc:
            # Invalid files never partially replace the live state.
            self.message = f"Config error: {exc} (using defaults; original file preserved)"

    def save_config(self):
        # Write beside the destination and replace it only after serialization succeeds.
        # General settings stay separate from the automatically saved Problems file.
        data = {"mode": self.calculator.mode, "precision": self.calculator.precision,
                "output_mode": self.calculator.output_mode,
                "history_insert": self.history_insert, "units": self.calculator.unit_definitions,
                "equations": self.calculator.equations,
                "unchecked_equations": sorted(self.calculator.unchecked_equations,
                                              key=EQUATION_NAMES.index),
                "table": {"start": self.table_start, "step": self.table_step},
                "menus": self.menus}
        temporary = self.config_path.with_name(self.config_path.name + ".tmp")
        try:
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.config_path)
        except OSError as exc:
            raise CalcError(f"Cannot save configuration: {exc}") from None
        self.message = "Saved configuration to " + str(self.config_path)
        self.save_problems()

    @property
    def input_selection(self) -> tuple[int, int] | None:
        # Keep selection tied to its text if a caller replaces the input buffer.
        anchor = self._selection_anchor
        if (self._selected_input != self.text or anchor is None or anchor == self.cursor
                or not 0 <= anchor <= len(self.text) or not 0 <= self.cursor <= len(self.text)):
            return None
        return min(anchor, self.cursor), max(anchor, self.cursor)

    @property
    def input_selected(self):
        return self.input_selection is not None

    def clear_input_selection(self):
        self._selected_input, self._selection_anchor = None, None

    def select_all_input(self):
        self.cursor = len(self.text)
        self._selected_input, self._selection_anchor = self.text, 0

    def delete_input_selection(self):
        selection = self.input_selection
        if selection is None:
            return False
        first, last = selection
        self.text = self.text[:first] + self.text[last:]
        self.cursor, self.history_index = first, None
        self.clear_input_selection()
        return True

    def clear_input(self):
        self.text, self.cursor, self.history_index = "", 0, None
        self.clear_input_selection()

    def insert(self, text):
        self.delete_input_selection()
        self.clear_input_selection()
        self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
        self.cursor += len(text)
        self.history_index = None

    def browse_history(self, direction: int, page: bool = False):
        # Each successful row has two selectable parts; error rows expose only the input.
        history = self.calculator.history
        if not history:
            return
        if self.history_index is None:
            if direction < 0:
                self.history_index = len(history) - 1
                self.history_part = "expression" if history[-1].is_error else self.history_insert
            return
        if page:
            index = self.history_index + direction * self.history_rows
            self.history_index = max(0, index) if index < len(history) else None
            if self.history_index is not None and history[self.history_index].is_error:
                self.history_part = "expression"
            return
        # Reading order is expression, result; Up traverses that order backwards.
        parts = [(i, part) for i, entry in enumerate(history)
                 for part in (("expression",) if entry.is_error else ("expression", "result"))]
        position = max(0, parts.index((self.history_index, self.history_part)) + direction)
        if position >= len(parts):
            self.history_index = None
        else:
            self.history_index, self.history_part = parts[position]

    def menu_root(self):
        if self.open_menu is None:
            raise CalcError("No menu is open.")
        return cleanup_menu() if self.open_menu == 8 else self.menus[self.open_menu]

    def menu_items(self):
        # Filtering applies to the active submenu, or the root when no submenu is open.
        if self.open_menu is None:
            return []
        menu = self.menu_stack[-1][0] if self.menu_stack else self.menu_root()
        return filter_menu_items(menu["items"], self.menu_filter.casefold())

    def open_submenu(self, item):
        # Save the parent position while the child starts with a fresh selection/filter.
        self.menu_stack.append((item, self.menu_index, self.menu_filter))
        self.menu_index = 0
        self.menu_filter = ""

    def close_submenu(self):
        _, self.menu_index, self.menu_filter = self.menu_stack.pop()

    def command(self, text):
        # Colon commands change application state instead of entering the math parser.
        name, _, arg = text.partition(" ")
        arg = arg.strip()
        if name == ":quit":
            self.running = False
        elif name == ":help":
            self.help_open = True
        elif name == ":catalog":
            self.open_catalog()
        elif name == ":problem":
            action, _, problem_name = arg.partition(" ")
            if action not in ("new", "open", "delete"):
                raise CalcError("Use :problem new/open/delete [NAME].")
            if problem_name and action in ("new", "open"):
                (self.new_problem if action == "new" else self.open_problem)(problem_name)
            else:
                self.begin_problem_dialog(action, problem_name)
        elif name == ":mode":
            self.calculator.set_mode(arg)
            self.message = "Angle mode: " + self.calculator.mode + "; :save to keep settings."
        elif name == ":format":
            self.calculator.set_output_mode(arg)
            self.message = "Output mode: " + self.calculator.output_mode + "; :save to keep settings."
        elif name == ":precision":
            try:
                self.calculator.set_precision(int(arg))
            except ValueError as exc:
                raise CalcError("Precision must be an integer of at least 2.") from exc
            self.message = f"Approximation precision: {self.calculator.precision} digits; exact math is unchanged."
        elif name == ":recall":
            if arg not in ("result", "expression"):
                raise CalcError("Use :recall result or :recall expression.")
            self.history_insert = arg
            self.message = "History browsing starts with the " + arg + "; Up/Down selects either part."
        elif name == ":clear":
            self.calculator.history.clear()
            self.history_index = None
            self.message = "History cleared."
            self.save_history(force=True)
        elif name == ":clearvars":
            self.calculator.variables.clear()
            self.message = "Set variables cleared."
        elif name == ":vars":
            self.message = "; ".join(f"{k} = {self.calculator.format(v)}" for k, v in self.calculator.variables.items()) or "No assigned variables."
        elif name == ":unset":
            if arg not in self.calculator.variables:
                raise CalcError("No assigned variable named " + arg)
            del self.calculator.variables[arg]
            self.message = arg + " is symbolic again."
        elif name == ":unit":
            unit_name, separator, expression = arg.partition("=")
            if not separator:
                raise CalcError("Use :unit name = expression, for example :unit smoot = 1.7018_m.")
            unit_name = unit_name.strip().removeprefix("_")
            self.calculator.define_unit(unit_name, expression.strip())
            unit = self.calculator.registry.get(unit_name)
            self.menus[1]["items"] = categorize_unit_items(self.calculator.registry,
                self.menus[1]["items"] + [insert_item(unit.notation + " " + unit.label, unit.notation)])
            self.message = "Added " + unit.notation + "; :save to keep it."
        elif name in (":menu", ":menuadd", ":menuclear"):
            number, _, rest = arg.partition(" ")
            if number not in {"1", "2", "3", "4", "5", "6"}:
                raise CalcError("Menu number must be 1 through 6.")
            menu = self.menus[int(number) - 1]
            if name == ":menu":
                if not rest.strip():
                    raise CalcError("Use :menu NUMBER LABEL.")
                menu["label"] = rest.strip()
            elif name == ":menuclear":
                menu["items"] = []
            else:
                label, separator, action = rest.partition("|")
                if not separator or not label.strip():
                    raise CalcError("Use :menuadd NUMBER LABEL | TEXT (or a :command).")
                action = action.strip()
                menu["items"].append(command_item(label.strip(), action) if action.startswith(":") else insert_item(label.strip(), action))
            self.message = "Updated F" + number + " menu; :save to keep it."
        elif name == ":save":
            self.save_config()
        else:
            raise CalcError("Unknown command. Use :help for commands.")

    def submit(self, approximate=False):
        # Both interactive and plain mode share this command/calculation path.
        if not self.text.strip():
            return
        try:
            if self.text.lstrip().startswith(":"):
                self.command(self.text.strip())
                self.clear_input()
            else:
                self.calculator.evaluate(self.text, approximate=approximate)
                self.message = self.calculator.history[-1].line
                self.save_history()
                self.select_all_input()
            self.history_index = None
        except (CalcError, OSError) as exc:
            # Keep failed input in the editor for correction and persist any error entry.
            self.message = "Error: " + str(exc)
            self.history_index = None
            if self.text.lstrip().startswith(":"):
                self.clear_input_selection()
            else:
                self.select_all_input()
            self.save_history()

    def handle_key(self, key):
        # Dispatch global shortcuts first, then route keys to help, menus, or the editor.
        # Terminal-specific key encodings have already been converted to names here.
        if key in ("CTRL_C", "CTRL_D"):
            self.running = False
            return
        if self.problem_dialog is not None:
            self.handle_problem_key(key)
            return
        if self.catalog_open:
            self.handle_catalog_key(key)
            return
        if key == "F8":
            if self.equation_open and not self.commit_equation():
                return
            if self.table_edit_field is not None and not self.commit_table_settings():
                return
            self.equation_open = False
            self.open_menu = None
            self.menu_stack.clear()
            self.help_open = False
            self.table_open = not self.table_open
            self.message = "Tab: start/step | Arrows: scroll | F7: equations | F8/Esc: close | Settings save automatically"
            return
        if key == "F7":
            if self.table_edit_field is not None and not self.commit_table_settings():
                return
            self.table_open = False
            if self.equation_open:
                if self.commit_equation():
                    self.equation_open = False
            else:
                self.open_menu = None
                self.menu_stack.clear()
                self.help_open = False
                self.equation_open = True
                self.load_equation()
            return
        if key in ("F1", "F2", "F3", "F4", "F5", "F6", "F9"):
            if self.table_edit_field is not None and not self.commit_table_settings():
                return
            self.table_open = False
            if self.equation_open:
                if not self.commit_equation():
                    return
                self.equation_open = False
            number = int(key[1:]) - 1
            self.open_menu = None if self.open_menu == number else number
            self.menu_index = 0
            self.menu_filter = ""
            self.menu_stack.clear()
            self.help_open = False
            return
        if self.equation_open:
            self.handle_equation_key(key)
            return
        if self.table_open:
            self.handle_table_key(key)
            return
        if self.help_open:
            if key in ("ESC", "ENTER", "TAB"):
                self.help_open = False
            return
        if self.open_menu is not None:
            items = self.menu_items()
            if key in ("ESC", "LEFT") and self.menu_stack:
                self.close_submenu()
            elif key == "ESC":
                self.open_menu = None
            elif key == "RIGHT" and items and "items" in items[self.menu_index]:
                self.open_submenu(items[self.menu_index])
            elif key in ("LEFT", "RIGHT"):
                # Right on a leaf (or empty filter) advances to the next top menu.
                # Left inside a submenu was handled above by returning to its parent.
                menus = (0, 1, 2, 3, 4, 5, 8)
                self.open_menu = menus[(menus.index(self.open_menu) + (1 if key == "RIGHT" else -1)) % len(menus)]
                self.menu_index = 0
                self.menu_filter = ""
                self.menu_stack.clear()
            elif key in ("UP", "DOWN", "PAGEUP", "PAGEDOWN", "HOME", "END"):
                if key in ("HOME", "END"):
                    self.menu_index = 0 if key == "HOME" else max(0, len(items) - 1)
                else:
                    delta = {"UP": -1, "DOWN": 1, "PAGEUP": -8, "PAGEDOWN": 8}[key]
                    self.menu_index = max(0, min(len(items) - 1, self.menu_index + delta))
            elif key == "ENTER" and items:
                item = items[self.menu_index]
                if "items" in item:
                    self.open_submenu(item)
                    return
                self.open_menu = None
                self.menu_stack.clear()
                if "insert" in item:
                    self.insert(item["insert"])
                else:
                    try:
                        self.command(item["command"])
                    except CalcError as exc:
                        self.message = "Error: " + str(exc)
            elif key == "BACKSPACE":
                self.menu_filter = self.menu_filter[:-1]
                self.menu_index = 0
            elif len(key) == 1 and key.isprintable():
                self.menu_filter += key
                self.menu_index = 0
            return
        history = self.calculator.history
        if key in ("UP", "PAGEUP") and history:
            self.browse_history(-1, page=key == "PAGEUP")
        elif key in ("DOWN", "PAGEDOWN") and self.history_index is not None:
            self.browse_history(1, page=key == "PAGEDOWN")
        elif key in ("ESC", "TAB"):
            if key == "TAB" and self.history_index is None and history:
                self.browse_history(-1)
            else:
                self.history_index = None
        elif key in ("ENTER", "SHIFT_ENTER"):
            if self.history_index is not None:
                entry = history[self.history_index]
                part = self.history_part
                recalled = entry.result if part == "result" else entry.source
                # Parenthesize composite results so insertion preserves their meaning.
                if part == "result" and any(c in recalled for c in "+-*/^"):
                    recalled = "(" + recalled + ")"
                self.insert(recalled)
                self.message = "Inserted history " + part + " at the cursor."
            else:
                self.submit(approximate=key == "SHIFT_ENTER")
        elif key in ("SHIFT_LEFT", "SHIFT_RIGHT"):
            self.history_index = None
            if self._selected_input != self.text or self._selection_anchor is None:
                self._selected_input, self._selection_anchor = self.text, self.cursor
            self.cursor = max(0, min(len(self.text), self.cursor + (-1 if key == "SHIFT_LEFT" else 1)))
        elif key == "LEFT":
            self.history_index = None
            selection = self.input_selection
            self.cursor = selection[0] if selection is not None else max(0, self.cursor - 1)
            self.clear_input_selection()
        elif key == "RIGHT":
            self.history_index = None
            selection = self.input_selection
            self.cursor = selection[1] if selection is not None else min(len(self.text), self.cursor + 1)
            self.clear_input_selection()
        elif key == "HOME":
            self.history_index = None
            self.cursor = 0
            self.clear_input_selection()
        elif key == "END":
            self.history_index = None
            self.cursor = len(self.text)
            self.clear_input_selection()
        elif key in ("BACKSPACE", "DELETE") and self.input_selected:
            self.delete_input_selection()
        elif key == "BACKSPACE" and self.cursor:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
            self.cursor -= 1
            self.history_index = None
            self.clear_input_selection()
        elif key == "DELETE":
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
            self.history_index = None
            self.clear_input_selection()
        elif key == "CTRL_U":
            self.clear_input()
        elif len(key) == 1 and key.isprintable():
            self.insert(key)

    def load_equation(self):
        name = EQUATION_NAMES[self.equation_index]
        self.equation_text = self.calculator.equations.get(name, "")
        self.equation_cursor = len(self.equation_text)
        self.message = "Ctrl+T: check/uncheck | F8: table | Enter: save/next | F7: save/close | Esc: cancel"

    def commit_equation(self):
        name = EQUATION_NAMES[self.equation_index]
        try:
            self.calculator.define_equation(name, self.equation_text)
        except CalcError as exc:
            self.message = "Error: " + str(exc)
            return False
        self.message = f"{name}(x)=" + self.equation_text.strip() + " | Equations saved automatically."
        return self.save_problems()

    def handle_equation_key(self, key):
        if key == "CTRL_T":
            if self.commit_equation():
                name = EQUATION_NAMES[self.equation_index]
                if name in self.calculator.equations:
                    unchecked = self.calculator.unchecked_equations
                    if name in unchecked:
                        unchecked.remove(name)
                    else:
                        unchecked.add(name)
                    self.message = f"{name}: {'unchecked' if name in unchecked else 'checked'} for F8 table"
                    self.save_problems()
                else:
                    self.message = "Enter an equation before checking it for the table."
        elif key == "ESC":
            self.equation_open = False
            self.message = "Equation editor closed; current edit canceled. Saved equations are remembered automatically."
        elif key in ("UP", "DOWN", "PAGEUP", "PAGEDOWN", "ENTER", "TAB"):
            if self.commit_equation():
                delta = {"UP": -1, "DOWN": 1, "PAGEUP": -self.history_rows,
                         "PAGEDOWN": self.history_rows, "ENTER": 1, "TAB": 1}[key]
                self.equation_index = max(0, min(98, self.equation_index + delta))
                self.load_equation()
        elif key == "LEFT":
            self.equation_cursor = max(0, self.equation_cursor - 1)
        elif key == "RIGHT":
            self.equation_cursor = min(len(self.equation_text), self.equation_cursor + 1)
        elif key == "HOME":
            self.equation_cursor = 0
        elif key == "END":
            self.equation_cursor = len(self.equation_text)
        elif key == "CTRL_U":
            self.equation_text, self.equation_cursor = "", 0
        elif key == "BACKSPACE" and self.equation_cursor:
            position = self.equation_cursor
            self.equation_text = self.equation_text[:position - 1] + self.equation_text[position:]
            self.equation_cursor -= 1
        elif key == "DELETE":
            position = self.equation_cursor
            self.equation_text = self.equation_text[:position] + self.equation_text[position + 1:]
        elif len(key) == 1 and key.isprintable():
            position = self.equation_cursor
            self.equation_text = self.equation_text[:position] + key + self.equation_text[position:]
            self.equation_cursor += 1

    def status_with_shift(self, text, width):
        indicator = "↑" if self.shift_pressed else " "
        return clip(f" {self.problem_name} | {indicator} | {text.lstrip()}", width)

    def equation_frame(self, width, height, menu_title):
        rows = height - 7
        first = min(max(0, self.equation_index - rows + 1), max(0, 99 - rows))
        lines = [menu_title, "Equations y1-y99 | F7: close | Enter: save"]
        selected = {}
        for offset in range(rows):
            index = first + offset
            if index >= 99:
                lines.append("")
                continue
            name = EQUATION_NAMES[index]
            active = index == self.equation_index
            expression = self.equation_text if active else self.calculator.equations.get(name, "")
            changed = active and expression.strip() != self.calculator.equations.get(name, "")
            checked = bool(expression.strip()) and (changed or name not in self.calculator.unchecked_equations)
            line = ("> " if active else "  ") + ("[✓] " if checked else "[ ] ") + f"{name}=" + expression
            if active:
                selected[len(lines)] = (0, len(line))
            lines.append(line)
        prefix = f"{EQUATION_NAMES[self.equation_index]}(x)="
        available = width - display_width(prefix) - 1
        start = max(0, self.equation_cursor - available + 1)
        while display_width(self.equation_text[start:self.equation_cursor]) >= available:
            start += 1
        lines += ["-" * width, prefix + self.equation_text[start:], "-" * width]
        cursor = (height - 3, display_width(prefix + self.equation_text[start:self.equation_cursor]) + 1)
        lines += [f" Equation {self.equation_index + 1}/99 | Ctrl+T: check/uncheck | F8: table",
                  self.message]
        lines[-2] = self.status_with_shift(lines[-2], width)
        lines = [clip(line, width) for line in lines]
        selected = {row: (begin, min(end, len(lines[row]))) for row, (begin, end) in selected.items()}
        return lines, selected, cursor

    @staticmethod
    def validate_table_settings(calculator, start, step) -> tuple[str, str]:
        values = []
        for label, source in (("Start", start), ("Step", step)):
            if not isinstance(source, str):
                raise CalcError(f"Table {label.lower()} must be a numeric expression.")
            value = calculator.parse(source)
            if (not isinstance(value.value, sp.Expr) or value.dims != ZERO
                    or value.value.is_number is not True or value.value.is_real is not True
                    or sp.ask(sp.Q.finite(value.value)) is not True):
                raise CalcError(f"Table {label.lower()} must be a finite real number without units.")
            if label == "Step" and value.value == 0:
                raise CalcError("Table step cannot be zero.")
            values.append(expression_text(value.value))
        return values[0], values[1]

    def commit_table_settings(self):
        try:
            start, step = self.validate_table_settings(self.calculator, *self.table_fields)
        except CalcError as exc:
            self.message = "Error: " + str(exc)
            return False
        self.table_start, self.table_step = start, step
        self.table_row = 0
        self.table_edit_field = None
        self.message = "Table settings saved automatically | Tab: start/step"
        return self.save_problems()

    def table_equation_names(self) -> list[str]:
        return [name for name in EQUATION_NAMES if name in self.calculator.equations
                and name not in self.calculator.unchecked_equations]

    def handle_table_key(self, key):
        field = self.table_edit_field
        if field is None:
            if key == "ESC":
                self.table_open = False
            elif key == "TAB":
                self.table_fields = [self.table_start, self.table_step]
                self.table_edit_field = 0
                self.table_cursor = len(self.table_fields[0])
                self.message = "Start/Step: Tab switches fields | Enter: apply | Esc: cancel | Ctrl+U: clear"
            elif key in ("UP", "DOWN", "PAGEUP", "PAGEDOWN"):
                self.table_row += {"UP": -1, "DOWN": 1, "PAGEUP": -max(1, self.history_rows - 2),
                                   "PAGEDOWN": max(1, self.history_rows - 2)}[key]
            elif key in ("LEFT", "RIGHT"):
                self.table_column = max(0, min(max(0, len(self.table_equation_names()) - 1),
                                              self.table_column + (-1 if key == "LEFT" else 1)))
            elif key == "HOME":
                self.table_row, self.table_column = 0, 0
            return
        text, position = self.table_fields[field], self.table_cursor
        if key == "ESC":
            self.table_edit_field = None
            self.message = "Table setup canceled | Tab: start/step | F8/Esc: close"
        elif key == "ENTER":
            self.commit_table_settings()
        elif key in ("TAB", "UP", "DOWN"):
            self.table_edit_field = 1 - field
            self.table_cursor = len(self.table_fields[1 - field])
        elif key == "LEFT":
            self.table_cursor = max(0, position - 1)
        elif key == "RIGHT":
            self.table_cursor = min(len(text), position + 1)
        elif key == "HOME":
            self.table_cursor = 0
        elif key == "END":
            self.table_cursor = len(text)
        elif key == "CTRL_U":
            self.table_fields[field], self.table_cursor = "", 0
        elif key == "BACKSPACE" and position:
            self.table_fields[field] = text[:position - 1] + text[position:]
            self.table_cursor -= 1
        elif key == "DELETE":
            self.table_fields[field] = text[:position] + text[position + 1:]
        elif len(key) == 1 and key.isprintable():
            self.table_fields[field] = text[:position] + key + text[position:]
            self.table_cursor += 1

    def table_frame(self, width, height, menu_title):
        column_width = min(18, max(10, (width - 12) // 5))
        capacity = max(1, (width + 3) // (column_width + 3) - 1)
        names = self.table_equation_names()
        self.table_column = min(self.table_column, max(0, len(names) - capacity))
        visible = names[self.table_column:self.table_column + capacity]

        def row(cells):
            clipped = [clip(cell, column_width) for cell in cells]
            return " | ".join(cell + " " * (column_width - display_width(cell)) for cell in clipped)

        lines = [menu_title, f"Table | Start={self.table_start} | Step={self.table_step}",
                 row(["x"] + visible), "-" * width]
        start = self.calculator.parse(self.table_start)
        step = self.calculator.parse(self.table_step)
        for offset in range(height - 9):
            if not names:
                lines.append("Check equations in F7 (Ctrl+T)." if offset == 0 else "")
                continue
            argument = start.arithmetic("+", step.arithmetic("*", Quantity(sp.Integer(self.table_row + offset))))
            cells = [self.calculator.format(argument)]
            for name in visible:
                try:
                    cells.append(self.calculator.format(self.calculator.equation(name, [argument])))
                except CalcError:
                    cells.append("Error")
            lines.append(row(cells))
        lines.append("-" * width)
        cursor = None
        field = self.table_edit_field
        if field is not None:
            prefix = ("Start", "Step")[field] + "="
            text = self.table_fields[field]
            available = width - len(prefix) - 1
            first = max(0, self.table_cursor - available + 1)
            while display_width(text[first:self.table_cursor]) >= available:
                first += 1
            lines.append(prefix + text[first:])
            cursor = (height - 3, len(prefix) + display_width(text[first:self.table_cursor]) + 1)
        else:
            lines.append("Tab: start/step | F7: equations | F8: close")
        first_column = self.table_column + 1 if names else 0
        lines += ["-" * width,
                  f" Row {self.table_row} | equations {first_column}-{self.table_column + len(visible)}/{len(names)} | arrows: scroll | Home: reset",
                  self.message]
        lines[-2] = self.status_with_shift(lines[-2], width)
        return [clip(line, width) for line in lines], {}, cursor

    def open_catalog(self):
        if self.equation_open and not self.commit_equation():
            return
        if self.table_edit_field is not None and not self.commit_table_settings():
            return
        self.catalog_entries = catalog_items(self.calculator, self.menus)
        self.catalog_filter, self.catalog_index = "", 0
        self.catalog_open = True
        self.open_menu = None
        self.menu_stack.clear()
        self.equation_open, self.table_open, self.help_open = False, False, False
        self.message = "Catalog | Type: filter | Up/Down or PageUp/PageDown: scroll | Enter: insert | Esc: close"

    def catalog_matches(self) -> list[dict[str, str]]:
        query = self.catalog_filter.casefold()
        return [item for item in self.catalog_entries
                if query in item["label"].casefold() or query in item["insert"].casefold()]

    def handle_catalog_key(self, key):
        items = self.catalog_matches()
        if key in ("ESC", "F6"):
            self.catalog_open = False
            self.message = "Catalog closed."
        elif key in ("UP", "DOWN", "PAGEUP", "PAGEDOWN", "HOME", "END"):
            if key in ("HOME", "END"):
                self.catalog_index = 0 if key == "HOME" else max(0, len(items) - 1)
            else:
                delta = {"UP": -1, "DOWN": 1, "PAGEUP": -self.catalog_rows, "PAGEDOWN": self.catalog_rows}[key]
                self.catalog_index = max(0, min(len(items) - 1, self.catalog_index + delta))
        elif key == "ENTER" and items:
            item = items[min(self.catalog_index, len(items) - 1)]
            self.insert(item["insert"])
            self.catalog_open = False
            self.message = "Inserted " + item["insert"] + " from Catalog."
        elif key in ("BACKSPACE", "CTRL_U"):
            self.catalog_filter = self.catalog_filter[:-1] if key == "BACKSPACE" else ""
            self.catalog_index = 0
        elif len(key) == 1 and key.isprintable():
            self.catalog_filter += key
            self.catalog_index = 0

    def catalog_frame(self, lines, width, height):
        # Use nearly the whole terminal while retaining a centered modal border.
        box_width = min(width - 4, 100, max(36, width * 4 // 5))
        self.catalog_rows = max(1, height - 9)
        items = self.catalog_matches()
        self.catalog_index = min(self.catalog_index, max(0, len(items) - 1))
        first = max(0, self.catalog_index - self.catalog_rows + 1)

        def row(text):
            text = clip(text, box_width - 2)
            return "|" + text + " " * (box_width - 2 - display_width(text)) + "|"

        border = "+" + "-" * (box_width - 2) + "+"
        panel = [border, row(" Catalog"), row(" Find: " + self.catalog_filter)]
        for offset in range(self.catalog_rows):
            index = first + offset
            if index < len(items):
                panel.append(row(("> " if index == self.catalog_index else "  ") + items[index]["label"]))
            else:
                panel.append(row("  (no matches)" if not items and offset == 0 else ""))
        position = self.catalog_index + 1 if items else 0
        panel += [row(f" {position}/{len(items)} | Enter: insert | Esc: close"), border]
        top, left = (height - len(panel)) // 2, (width - box_width) // 2
        for index, content in enumerate(panel, top):
            background = lines[index].ljust(width)
            lines[index] = background[:left] + content + background[left + box_width:]
        selected = {top + 3 + self.catalog_index - first: (left + 1, left + box_width - 1)} if items else {}
        return lines, selected, None

    def begin_problem_dialog(self, action, name=""):
        if action == "delete" and name:
            if name == "Default" or name not in self.problems:
                raise CalcError("Choose a saved Problem to delete; Default is kept.")
            self.problem_dialog = "confirm"
            self.problem_delete_name = name
        else:
            self.problem_dialog = action
        self.problem_dialog_text, self.problem_dialog_cursor = "", 0
        self.problem_dialog_index = 0
        self.problem_delete_confirm = False
        self.open_menu = None
        self.menu_stack.clear()
        self.equation_open, self.table_open, self.help_open = False, False, False
        self.catalog_open = False
        self.message = "Enter: choose | Esc: cancel"

    def problem_choices(self) -> list[str]:
        return [name for name in sorted(self.problems, key=lambda name: (name != "Default", name.casefold()))
                if (self.problem_dialog != "delete" or name != "Default")
                and self.problem_dialog_text.casefold() in name.casefold()]

    def handle_problem_key(self, key):
        if key == "ESC":
            self.problem_dialog = None
            self.message = "Problem dialog canceled."
            return
        if self.problem_dialog == "confirm":
            if key in ("LEFT", "RIGHT", "UP", "DOWN", "TAB"):
                self.problem_delete_confirm = not self.problem_delete_confirm
            elif key.lower() == "y":
                self.problem_delete_confirm = True
            elif key.lower() == "n":
                self.problem_delete_confirm = False
            elif key == "ENTER":
                try:
                    if self.problem_delete_confirm:
                        self._delete_confirmed_problem()
                    else:
                        self.message = "Deletion canceled."
                    self.problem_dialog = None
                except CalcError as exc:
                    self.message = "Error: " + str(exc)
            return
        if self.problem_dialog in ("open", "delete"):
            names = self.problem_choices()
            if key in ("UP", "DOWN", "PAGEUP", "PAGEDOWN", "HOME", "END"):
                if key in ("HOME", "END"):
                    self.problem_dialog_index = 0 if key == "HOME" else max(0, len(names) - 1)
                else:
                    delta = {"UP": -1, "DOWN": 1, "PAGEUP": -8, "PAGEDOWN": 8}[key]
                    self.problem_dialog_index = max(0, min(len(names) - 1, self.problem_dialog_index + delta))
            elif key == "ENTER" and names:
                name = names[min(self.problem_dialog_index, len(names) - 1)]
                if self.problem_dialog == "delete":
                    self.problem_delete_name = name
                    self.problem_delete_confirm = False
                    self.problem_dialog = "confirm"
                else:
                    try:
                        self.open_problem(name)
                        self.problem_dialog = None
                    except CalcError as exc:
                        self.message = "Error: " + str(exc)
            elif key == "BACKSPACE":
                self.problem_dialog_text = self.problem_dialog_text[:-1]
                self.problem_dialog_index = 0
            elif len(key) == 1 and key.isprintable():
                self.problem_dialog_text += key
                self.problem_dialog_index = 0
            return
        text, position = self.problem_dialog_text, self.problem_dialog_cursor
        if key == "ENTER":
            try:
                self.new_problem(text)
                self.problem_dialog = None
            except CalcError as exc:
                self.message = "Error: " + str(exc)
        elif key == "LEFT":
            self.problem_dialog_cursor = max(0, position - 1)
        elif key == "RIGHT":
            self.problem_dialog_cursor = min(len(text), position + 1)
        elif key == "HOME":
            self.problem_dialog_cursor = 0
        elif key == "END":
            self.problem_dialog_cursor = len(text)
        elif key == "CTRL_U":
            self.problem_dialog_text, self.problem_dialog_cursor = "", 0
        elif key == "BACKSPACE" and position:
            self.problem_dialog_text = text[:position - 1] + text[position:]
            self.problem_dialog_cursor -= 1
        elif key == "DELETE":
            self.problem_dialog_text = text[:position] + text[position + 1:]
        elif len(key) == 1 and key.isprintable():
            self.problem_dialog_text = text[:position] + key + text[position:]
            self.problem_dialog_cursor += 1

    def problem_dialog_frame(self, lines, width, height):
        selected = {}
        cursor = None
        start = 0
        if self.problem_dialog in ("open", "delete"):
            names = self.problem_choices()
            title = "Open Problem" if self.problem_dialog == "open" else "Delete Problem"
            if self.problem_dialog_text:
                title += " | " + self.problem_dialog_text
            items = [{"label": name + (" (current)" if name == self.problem_name else "")} for name in names]
            self.problem_dialog_index = min(self.problem_dialog_index, max(0, len(names) - 1))
            panel, first = menu_panel(items, title, self.problem_dialog_index, min(width - 2, 64), height)
            top, left = (height - len(panel)) // 2, (width - display_width(panel[0])) // 2
            if names:
                selected[top + 2 + self.problem_dialog_index - first] = (left + 1, left + display_width(panel[0]) - 1)
        else:
            box_width = min(width - 2, 64)
            inside = box_width - 4
            if self.problem_dialog == "new":
                start = max(0, self.problem_dialog_cursor - inside + 1)
                while display_width(self.problem_dialog_text[start:self.problem_dialog_cursor]) >= inside:
                    start += 1
                content = ["New Problem", "Name:", self.problem_dialog_text[start:], "",
                           "Enter: create | Esc: cancel"]
            else:
                content = ["Delete Problem?", self.problem_delete_name,
                           "Its history and equations will be deleted.", "Cancel   Delete", "Enter: confirm | Esc: cancel"]
            border = "+" + "-" * (box_width - 2) + "+"
            panel = [border]
            for text in content:
                text = clip(text, inside)
                panel.append("| " + text + " " * (box_width - 3 - display_width(text)) + "|")
            panel.append(border)
            top, left = (height - len(panel)) // 2, (width - box_width) // 2
            if self.problem_dialog == "new":
                cursor = (top + 4, left + 3 + display_width(self.problem_dialog_text[start:self.problem_dialog_cursor]))
            else:
                begin = left + 2 + (9 if self.problem_delete_confirm else 0)
                selected[top + 4] = (begin, begin + 6)
        for row, content in enumerate(panel, top):
            background = lines[row].ljust(width)
            lines[row] = background[:left] + content + background[left + display_width(content):]
        return lines, selected, cursor

    def frame(self, width=100, height=24):
        """Return plain text lines, selected character spans by row, and input cursor."""
        width, height = max(1, width), max(1, height)
        # Reserve two menu rows and five for the input's two rules, input, status, and message.
        self.history_rows = max(1, height - 7)
        history_limit = max(30, self.history_rows)
        history = self.calculator.history
        if history.maxlen != history_limit:
            removed = max(0, len(history) - history_limit)
            self.calculator.history = deque(history, maxlen=history_limit)
            self.history_start = max(0, self.history_start - removed)
            if self.history_index is not None:
                index = self.history_index - removed
                self.history_index = index if index >= 0 else None
            if removed:
                self.save_history()
        if width < 40 or height < 12:
            lines = ["Please resize the terminal to at least 40 columns and 12 rows.", self.message]
            return [clip(line, width) for line in lines[:height]], {}, None
        label_width = max(1, (width - 43) // 9)
        menu_titles = [f"F{i + 1} {menu['label']}" for i, menu in enumerate(self.menus)]
        menu_titles.append("F7 Equations")
        menu_titles.append("F8 Table")
        menu_titles.append("F9 Clean Up")
        if display_width("  ".join(menu_titles)) > width:
            menu_titles = [f"F{i + 1} {clip(menu['label'], label_width)}" for i, menu in enumerate(self.menus)]
            menu_titles.append("F7 Equations")
            menu_titles.append("F8 " + clip("Table", label_width))
            menu_titles.append("F9 Clean Up")
        if display_width("  ".join(menu_titles)) > width:
            menu_titles = [f"F{i}" for i in range(1, 10)]
        if self.equation_open:
            return self.equation_frame(width, height, "  ".join(menu_titles))
        if self.table_open:
            return self.table_frame(width, height, "  ".join(menu_titles))
        lines = ["  ".join(menu_titles), "-" * width]
        selected: dict[int, tuple[int, int]] = {}
        # Choose a visible history window that follows either the newest result
        # or the older entry currently selected with the navigation keys.
        index = self.history_index
        history = list(self.calculator.history)
        last_start = max(0, len(history) - self.history_rows)
        if index is None:
            self.history_start = last_start
        else:
            self.history_start = min(self.history_start, last_start)
            if index < self.history_start:
                self.history_start = index
            elif index >= self.history_start + self.history_rows:
                self.history_start = index - self.history_rows + 1
        for i in range(self.history_rows):
            j = self.history_start + i
            marker = "> " if j == index else "  "
            if j < len(history):
                prefix = marker + f"{j + 1:2}. "
                content = history[j].line
                if j == index:
                    first = 0 if self.history_part == "expression" else len(history[j].source) + 3
                    last = len(history[j].source) if self.history_part == "expression" else len(content)
                    offset = 0
                    available = width - display_width(prefix)
                    if first and display_width(content[:last]) > available:
                        # Scroll the selected row so a result after a long expression is visible.
                        remaining = display_width(content[:last])
                        while offset < first and remaining > available - 1:
                            remaining -= display_width(content[offset])
                            offset += 1
                        prefix += "…"
                    selected[len(lines)] = (len(prefix) + first - offset, len(prefix) + last - offset)
                    content = content[offset:]
                line = prefix + content
            else:
                line = "  (history is empty)" if i == 0 else ""
            lines.append(line)
        lines += ["-" * width]
        # Keep the cursor visible, including on very long arbitrary-precision inputs.
        available = width - 3
        input_selection = self.input_selection
        focus = self.cursor
        if input_selection is not None and self.cursor == input_selection[0]:
            # Show selected text to the right of a selection moving left, too.
            cells = 0
            for char in self.text[self.cursor:input_selection[1]]:
                cells += display_width(char)
                if cells >= available:
                    break
                focus += 1
        start_text = min(self.cursor, max(0, focus - available + 1))
        while display_width(self.text[start_text:focus]) >= available:
            start_text += 1
        input_row = len(lines)
        lines.append("> " + self.text[start_text:start_text + available])
        cursor = (input_row + 1, 3 + display_width(self.text[start_text:self.cursor]))
        if input_selection is not None and index is None:
            first, last = input_selection
            first = max(first, start_text)
            last = min(last, start_text + len(lines[input_row]) - 2)
            if first < last:
                selected[input_row] = (2 + first - start_text, 2 + last - start_text)
            cursor = None
        c = self.calculator
        selection = ("selected " + self.history_part if index is not None else
                     "selected input" if self.input_selected else "recall " + self.history_insert)
        lines.append("-" * width)
        lines.append(f" {c.mode.upper()} | history {len(c.history)}/{c.history.maxlen} | {c.output_mode} | approx {c.precision} digits | {selection}")
        lines.append(self.message)
        lines += [""] * (height - len(lines))
        if self.help_open:
            # Overlays replace the relevant frame rows and hide the editing cursor.
            selected = {}
            for row, text in enumerate(["HELP (Esc to close)"] + HELP_LINES, start=2):
                if row >= height:
                    break
                lines[row] = text
            cursor = None
        elif self.open_menu is not None:
            # Rebuild each level from the saved navigation stack, placing child panels
            # beside their parents where space allows. Only the active level is selected.
            root = self.menu_root()
            levels = [root] + [item for item, _, _ in self.menu_stack]
            indices = [parent_index for _, parent_index, _ in self.menu_stack] + [self.menu_index]
            filters = [parent_filter for _, _, parent_filter in self.menu_stack] + [self.menu_filter]
            anchor = sum(display_width(t) + 2 for t in menu_titles[:self.open_menu])
            top, previous_width, previous_first = 1, 0, 0
            selected = {}
            for depth, (menu, menu_index, menu_filter) in enumerate(zip(levels, indices, filters)):
                items = filter_menu_items(menu["items"], menu_filter.casefold())
                heading = " > ".join(level["label"] for level in levels[:depth + 1])
                if menu_filter:
                    heading += " | filter: " + menu_filter
                panel, first = menu_panel(items, heading, menu_index, width, height, depth > 0)
                box_width = display_width(panel[0])
                if depth:
                    if anchor + previous_width - 1 + box_width <= width:
                        anchor += previous_width - 1
                    elif anchor - box_width + 1 >= 0:
                        anchor -= box_width - 1
                    else:
                        # Narrow terminals show the child over its parent, with a breadcrumb.
                        anchor = min(anchor, width - box_width)
                    top = min(top + 2 + indices[depth - 1] - previous_first, height - 4 - len(panel))
                else:
                    anchor = min(anchor, width - box_width)
                for row, content in enumerate(panel, start=top):
                    background = lines[row].ljust(width)
                    lines[row] = background[:anchor] + content + background[anchor + box_width:]
                if depth == len(levels) - 1 and items:
                    selected[top + 2 + menu_index - first] = (anchor + 1, anchor + box_width - 1)
                previous_width, previous_first = box_width, first
            cursor = None
        elif index is not None:
            cursor = None
        if self.problem_dialog is not None:
            lines, selected, cursor = self.problem_dialog_frame(lines, width, height)
        elif self.catalog_open:
            lines, selected, cursor = self.catalog_frame(lines, width, height)
        lines[-2] = self.status_with_shift(lines[-2], width)
        lines = [clip(line, width) for line in lines]
        selected = {row: (first, min(last, len(lines[row]))) for row, (first, last) in selected.items()
                    if first < len(lines[row])}
        return lines, selected, cursor


# Layout helpers measure terminal cells, which differ from Python string indices
# for combining marks and wide Unicode characters.
def display_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def clip(text, width):
    """Truncate by terminal cells and strip controls supplied through config/input."""
    safe = "".join(c if c.isprintable() else " " for c in text)
    if display_width(safe) <= width:
        return safe
    result, used = [], 0
    for c in safe:
        cells = display_width(c)
        if used + cells > max(0, width - 1):
            break
        result.append(c)
        used += cells
    return "".join(result) + "…"


def menu_panel(items, heading, index, width, height, submenu=False):
    # Return one bounded dropdown and its first visible item for scrolling/highlighting.
    labels = [item["label"] + (" >" if "items" in item else "") for item in items]
    box_width = min(width, max(26, min(68, max([display_width(heading)] + [display_width(label) for label in labels]) + 4)))
    room = min(max(1, len(items)), max(1, height - 9))
    first = max(0, index - room + 1)

    def row(text):
        content = clip(text, box_width - 2)
        return "|" + content + " " * (box_width - 2 - display_width(content)) + "|"

    border = "+" + "-" * (box_width - 2) + "+"
    panel = [border, row(heading)]
    for offset in range(room):
        item_index = first + offset
        if item_index < len(items):
            marker = "> " if item_index == index else "  "
            panel.append(row(marker + labels[item_index]))
        else:
            panel.append(row("  (no matching items)"))
    panel += [row(f" {len(items)} items | Esc: {'back' if submenu else 'close'}"), border]
    return panel, first


# Map Windows extended keys and POSIX escape sequences to shared UI key names.
WINDOWS_KEYS = {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT", "G": "HOME", "O": "END",
                "I": "PAGEUP", "Q": "PAGEDOWN", "S": "DELETE", ";": "F1", "<": "F2", "=": "F3",
                ">": "F4", "?": "F5", "@": "F6", "A": "F7", "B": "F8", "C": "F9"}
ANSI_KEYS = {"\x1b[A": "UP", "\x1b[B": "DOWN", "\x1b[C": "RIGHT", "\x1b[D": "LEFT",
             "\x1b[1;2D": "SHIFT_LEFT", "\x1b[1;2C": "SHIFT_RIGHT",
             "\x1b[H": "HOME", "\x1b[F": "END", "\x1b[1~": "HOME", "\x1b[4~": "END",
             "\x1b[7~": "HOME", "\x1b[8~": "END", "\x1b[3~": "DELETE", "\x1b[5~": "PAGEUP",
             "\x1b[6~": "PAGEDOWN", "\x1bOP": "F1", "\x1bOQ": "F2", "\x1bOR": "F3",
             "\x1bOS": "F4", "\x1b[11~": "F1", "\x1b[12~": "F2", "\x1b[13~": "F3",
             "\x1b[14~": "F4", "\x1b[15~": "F5", "\x1b[17~": "F6", "\x1b[18~": "F7", "\x1b[19~": "F8", "\x1b[20~": "F9",
             "\x1bOH": "HOME", "\x1bOF": "END"}
CONTROL_KEYS = {"\r": "ENTER", "\n": "ENTER", "\x1b": "ESC", "\t": "TAB", "\x08": "BACKSPACE",
                "\x7f": "BACKSPACE", "\x03": "CTRL_C", "\x04": "CTRL_D", "\x15": "CTRL_U", "\x0c": "CTRL_L",
                "\x14": "CTRL_T"}


def windows_shift_pressed():
    # msvcrt uses the same arrow/Enter codes with and without Shift.
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    return bool(user32.GetAsyncKeyState(0x10) & 0x8000)


def modified_terminal_key(sequence):
    """Decode CSI-u or xterm modifyOtherKeys reports for character keys."""
    match = re.fullmatch(r"\x1b\[(\d+);(\d+)u", sequence)
    if match:
        codepoint, modifiers = map(int, match.groups())
    else:
        match = re.fullmatch(r"\x1b\[27;(\d+);(\d+)~", sequence)
        if not match:
            return "UNKNOWN"
        modifiers, codepoint = map(int, match.groups())
    if not 0 <= codepoint <= 0x10ffff or modifiers < 1:
        return "UNKNOWN"
    modifiers = (modifiers - 1) & 63  # Ignore Caps Lock / Num Lock flags.
    if codepoint in (10, 13) and modifiers in (0, 1, 4, 5):
        return "SHIFT_ENTER" if modifiers & 1 else "ENTER"
    if modifiers in (4, 5) and 65 <= codepoint <= 122:
        return CONTROL_KEYS.get(chr(codepoint & 31), "UNKNOWN")
    if modifiers in (0, 1):
        char = chr(codepoint)
        return CONTROL_KEYS.get(char, char if char.isprintable() else "UNKNOWN")
    return "UNKNOWN"


class Terminal:
    """Raw key input plus ANSI output, restoring console state on every exit."""

    def __init__(self):
        self.size = None

    def __enter__(self):
        # Save the host console settings before enabling interactive terminal behavior.
        self.old_mode = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.GetStdHandle.argtypes = [wintypes.DWORD]
            self.kernel.GetStdHandle.restype = wintypes.HANDLE
            self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.handle = self.kernel.GetStdHandle(-11 & 0xffffffff)
            # Windows needs virtual terminal processing (0x0004) for ANSI output.
            mode = wintypes.DWORD()
            if not self.kernel.GetConsoleMode(self.handle, ctypes.byref(mode)):
                raise CalcError("Interactive mode needs a Windows console. Use --plain in redirected shells.")
            if not self.kernel.SetConsoleMode(self.handle, mode.value | 0x0004):
                raise CalcError("This console does not support ANSI output. Use --plain.")
            self.old_mode = mode.value
        else:
            import termios
            import tty
            self.old_mode = termios.tcgetattr(sys.stdin.fileno())
            # Raw mode delivers individual keys without waiting for Enter or echoing them.
            tty.setraw(sys.stdin.fileno())
        # Use the alternate screen so the user's previous terminal contents survive exit.
        sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H")
        if os.name != "nt":
            # Ask supporting terminals to distinguish Shift+Enter from Enter.
            sys.stdout.write("\x1b[>4;2m")
        sys.stdout.flush()
        return self

    def __exit__(self, *args):
        # Restore the cursor, screen, and console settings even when the app raises.
        try:
            if os.name != "nt":
                sys.stdout.write("\x1b[>4m")
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        finally:
            if self.old_mode is not None:
                if os.name == "nt":
                    self.kernel.SetConsoleMode(self.handle, self.old_mode)
                else:
                    import termios
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_mode)

    def read_key(self, timeout: float | None = None) -> str | None:
        """Read one key, returning None on timeout so idle resizes can be handled."""
        if os.name == "nt":
            import msvcrt
            if timeout is not None:
                deadline = time.monotonic() + timeout
                while not msvcrt.kbhit():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    time.sleep(min(0.01, remaining))
            char = msvcrt.getwch()
            if char in ("\x00", "\xe0"):
                # Windows extended keys arrive as a prefix followed by a key code.
                key = WINDOWS_KEYS.get(msvcrt.getwch(), "UNKNOWN")
                if key in ("LEFT", "RIGHT") and windows_shift_pressed():
                    return "SHIFT_" + key
                return key
            if 0xd800 <= ord(char) <= 0xdbff:
                # Join UTF-16 surrogate pairs into one Unicode character.
                following = msvcrt.getwch()
                return (char + following).encode("utf-16", "surrogatepass").decode("utf-16")
            if char in ("\r", "\n") and windows_shift_pressed():
                return "SHIFT_ENTER"
        else:
            # Read bytes directly: TextIO buffering can otherwise swallow pasted keys.
            import select
            if timeout is not None and not select.select([sys.stdin], [], [], timeout)[0]:
                return None
            char = os.read(sys.stdin.fileno(), 1)
            if not char:
                return "CTRL_D"
            if char == b"\x1b":
                # A short lookahead distinguishes Esc alone from a multi-byte key sequence.
                sequence = char
                while select.select([sys.stdin], [], [], 0.04)[0]:
                    sequence += os.read(sys.stdin.fileno(), 1)
                    text = sequence.decode("ascii", "ignore")
                    if text in ANSI_KEYS:
                        return ANSI_KEYS[text]
                    modified = modified_terminal_key(text)
                    if modified != "UNKNOWN":
                        return modified
                    if len(sequence) > 2 and sequence[-1:] in b"~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
                        break
                return "ESC" if sequence == b"\x1b" else "UNKNOWN"
            required = 1 if char[0] < 0x80 else 2 if char[0] < 0xe0 else 3 if char[0] < 0xf0 else 4
            # Read the rest of a UTF-8 character before passing it to the editor.
            while len(char) < required:
                char += os.read(sys.stdin.fileno(), 1)
            char = char.decode("utf-8", "replace")
        return CONTROL_KEYS.get(char, char)

    def render(self, app):
        width, height = shutil.get_terminal_size((100, 24))
        # Leave the last column unused so writing a full row cannot trigger scrolling.
        lines, selected, cursor = app.frame(max(1, width - 1), height)
        output = ["\x1b[?25l\x1b[H"]
        if self.size != (width, height):
            output.append("\x1b[2J")
        self.size = (width, height)
        # Apply ANSI highlighting to the plain frame, then write the completed redraw
        # in one batch. Frame coordinates for the cursor are already one-based.
        for row, line in enumerate(lines):
            output.append(f"\x1b[{row + 1};1H\x1b[2K")
            if row in selected:
                first, last = selected[row]
                output.append(line[:first] + "\x1b[7m" + line[first:last] + "\x1b[0m" + line[last:])
            else:
                output.append(line)
        if cursor:
            output.append(f"\x1b[{cursor[0]};{cursor[1]}H\x1b[?25h")
        sys.stdout.write("".join(output))
        sys.stdout.flush()

    def run(self, app):
        # Poll modifiers as well as input so a bare Shift press/release can redraw.
        app.shift_pressed = self.read_shift_state()
        self.render(app)
        while app.running:
            key = self.read_key(timeout=0.1)
            if key is not None:
                app.handle_key(key)
            if not app.running:
                break
            shift_pressed = self.read_shift_state()
            shift_changed = shift_pressed != app.shift_pressed
            app.shift_pressed = shift_pressed
            if key is not None or shift_changed or shutil.get_terminal_size((100, 24)) != self.size:
                self.render(app)

    def read_shift_state(self):
        # POSIX character reports do not provide reliable standalone modifier releases.
        # Do not infer a held key from the last Shift shortcut, which could stick on.
        return windows_shift_pressed() if os.name == "nt" else False


# Entry point: the same calculator supports batch, line-oriented, and full-screen use.
def main(argv=None):
    parser = argparse.ArgumentParser(description="Exact symbolic console math, units, and configurable F1-F6 menus.")
    parser.add_argument("--config", type=Path, help="JSON configuration path (default: beside calc_term.py)")
    parser.add_argument("--plain", action="store_true", help="line-oriented mode for pipes or basic terminals")
    parser.add_argument("--eval", dest="expressions", action="append", help="evaluate an expression and exit; may be repeated")
    options = parser.parse_args(argv)
    # Windows redirected output otherwise often uses a legacy encoding without Greek.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")
    app = ConsoleApp(config_path=options.config)
    # Repeated --eval options share one session, including variables and ans.
    if options.expressions:
        status = 0
        for text in options.expressions:
            try:
                print(text + " = " + app.calculator.calculate(text))
                app.message = app.calculator.history[-1].line
                if not app.save_history():
                    print(app.message, file=sys.stderr)
                    status = 1
            except CalcError as exc:
                print("Error: " + str(exc), file=sys.stderr)
                status = 1
                if not app.save_history():
                    print(app.message, file=sys.stderr)
        return status
    if options.plain or not (sys.stdin.isatty() and sys.stdout.isatty()):
        # Pipes and basic terminals use complete input lines instead of raw key handling.
        if sys.stdin.isatty():
            print("Exact console calculator; :help for commands; :quit to exit.")
        while app.running:
            try:
                text = input("> " if sys.stdin.isatty() else "")
            except (EOFError, KeyboardInterrupt):
                break
            app.text, app.cursor = text, len(text)
            app.submit()
            if app.help_open:
                print("\n".join(HELP_LINES))
                app.help_open = False
            elif text.strip() and app.running:
                print(app.message)
        if not app.save_session():
            print(app.message, file=sys.stderr)
            return 1
        return 0
    status = 0
    try:
        # The context manager restores terminal state before errors are printed.
        with Terminal() as terminal:
            terminal.run(app)
    except KeyboardInterrupt:
        pass
    except CalcError as exc:
        print(str(exc), file=sys.stderr)
        status = 1
    finally:
        if not app.save_session():
            print(app.message, file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
