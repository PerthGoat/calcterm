"""Quantities, unit definitions, arithmetic, and exact result formatting."""

from __future__ import annotations

from dataclasses import dataclass, replace
import operator
import sys
import unicodedata

# Exact integers should not be truncated by Python's decimal string limit.
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

try:
    import sympy as sp
except ImportError:
    raise SystemExit("SymPy is required. Run: python -m pip install -r requirements.txt")


class CalcError(ValueError):
    """An input or configuration error suitable for displaying in the UI."""


# Comparison and bitwise operations are shared with the expression parser.
COMPARISONS = {"<": sp.Lt, ">": sp.Gt, "<=": sp.Le, ">=": sp.Ge,
               "=": sp.Eq, "==": sp.Eq, "!=": sp.Ne}
# Keep ^ as exponentiation; the word xor supplies bitwise exclusive OR instead.
BITWISE = {"&": operator.and_, "|": operator.or_, "xor": operator.xor,
           "<<": operator.lshift, ">>": operator.rshift}


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
