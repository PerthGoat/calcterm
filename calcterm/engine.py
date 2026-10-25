"""Calculator grammar, expression parser, and evaluation sessions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import re
from typing import cast

from .core import (BITWISE, COMPARISONS, ZERO, CalcError, Quantity, Unit,
                   UnitRegistry, sp, unit_key)


# Input grammar: recognize only calculator tokens, never Python source code.
# Unit tokens deliberately keep case; the registry alone ignores it.
DIGITS = r"\d+(?:_\d+)*"
BASES = {"b": 2, "h": 16, "o": 8}
BASE_LITERAL = re.compile(r"(?<!\w)0([bBhHoO])([^\W_]*(?:_[^\W_]+)*)", re.UNICODE)
TOKEN = re.compile(rf"(?P<number>{DIGITS}/{DIGITS}(?=_°?[^\W\d_])|"
                   rf"(?:{DIGITS}(?:\.(?:{DIGITS})?)?|\.{DIGITS})(?:[eE][+-]?{DIGITS})?)|"
                   r"(?P<unit>_°?[^\W\d_][^\W_]*)|(?P<name>[^\W\d_][^\W_]*)|"
                   r"(?P<op>\*\*|<<|>>|<=|>=|==|!=|[&|~<>=+\-*/^%(),!\[\]])", re.UNICODE)
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
