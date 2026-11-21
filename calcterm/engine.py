"""Calculator grammar, expression parser, and evaluation sessions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from functools import cached_property
import json
from random import Random
import re
from typing import cast

from sympy.core.relational import Relational
from sympy.logic.boolalg import BooleanFunction
from sympy.matrices.exceptions import MatrixError

from .core import (BITWISE, COMPARISONS, ZERO, CalcError, Quantity, Str, Unit,
                   UnitRegistry, is_scalar, sp, unit_key)
from .math_functions import (ALIASES, ANGLE_SUFFIXES, ARITIES, CONVERSIONS, ELEMENTWISE, HYPERBOLIC,
                             INVERSE_TRIG, RELATION_ARGUMENTS, TRIG, angle_scale, convert, extended_function,
                             map_values, minmax, scalar, solve)
from .math_statistics import COMMANDS, STAT_FUNCTIONS, CommandResult, math_command, stat_function


# Input grammar: recognize only calculator tokens, never Python source code.
# Unit tokens deliberately keep case; the registry alone ignores it.
DIGITS = r"\d+(?:_\d+)*"
BASES = {"b": 2, "h": 16, "o": 8}
BASE_LITERAL = re.compile(r"(?<!\w)0([bBhHoO])([^\W_]*(?:_[^\W_]+)*)", re.UNICODE)
STRING_LITERAL = r'"(?:[^"\\\x00-\x1f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"'
QUOTED_TEXT = re.compile(f"({STRING_LITERAL})")
LETTERS = r"(?:(?![ʳᵍᵀ])[^\W_])"
NAME = r"(?:(?![ʳᵍᵀ])[^\W\d_])" + LETTERS + "*"
MATH_WORD_OPERATORS = {"and": "&", "or": "|", "xor": "xor", "not": "~"}
LOGICAL_PRECEDENCE = {"or": 2, "xor": 3, "and": 4}
CONVERSION_TOKEN = "|".join(sorted(CONVERSIONS, key=len, reverse=True))
TOKEN = re.compile(rf"(?P<dms>{DIGITS}°{DIGITS}′(?:{DIGITS}(?:[/\.]{DIGITS})?)″)|"
                   rf"(?P<number>{DIGITS}/{DIGITS}(?=_°?[^\W\d_])|"
                   rf"(?:{DIGITS}(?:\.(?![+\-−*/^])(?:{DIGITS})?)?|\.{DIGITS})(?:[eE][+-]?{DIGITS})?)|"
                   rf"(?P<string>{STRING_LITERAL})|(?P<unit>_°?{NAME})|"
                   rf"(?P<name>P▶R[xy]|R▶P[rθ]|list▶mat|mat▶list|Data▶Mat|Mat▶Data|{NAME}(?:⁻¹)?|∫)|(?P<root>√)|"
                   rf"(?P<op>{CONVERSION_TOKEN}|\.\+|\.[−\-*/^]|\*\*|<<|>>|<=|>=|==|!=|"
                   r"[°ʳᵍᵀ∠∞'′″&|~<>=+\-*/^%(),!\[\]])", re.UNICODE)
RESERVED = {"pi": sp.pi, "π": sp.pi, "e": sp.E, "E": sp.E, "i": sp.I, "I": sp.I,
            "True": sp.true, "False": sp.false}
LEGACY_FUNCTIONS = {"sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "sqrt", "cbrt",
                    "exp", "ln", "log", "abs", "floor", "ceil", "factorial", "simplify", "expand", "factor",
                    "diff", "integrate", "solve", "subs", "approx", "min", "max"}
FUNCTIONS = (LEGACY_FUNCTIONS | ARITIES.keys() | STAT_FUNCTIONS.keys() | ALIASES.keys() | TRIG | INVERSE_TRIG
             | HYPERBOLIC | {"a" + name for name in HYPERBOLIC} | {"nPr", "nCr"})
EQUATION_NAMES = tuple(f"y{i}" for i in range(1, 100))
PRECEDENCE = {"or": 6, "xor": 7, "and": 8, "|": 6, "&": 8, "<<": 9, ">>": 9,
              "+": 10, "-": 10, "∠": 15, "*": 20, "/": 20, "%": 20, "^": 30, "**": 30,
              ".+": 10, ".-": 10, ".*": 20, "./": 20, ".^": 30}
FUNCTION_ARITIES = {"log": (1, 2), "diff": (2, 3), "integrate": (2, 4), "solve": (2,),
                    "subs": (3,), "approx": (1, 2), "min": None, "max": None,
                    "factor": (1, 2), "expand": (1, 2), "nPr": (2,), "nCr": (2,), **ARITIES, **STAT_FUNCTIONS}
TRANSLATE = str.maketrans({"→": "->", "⇒": "=>", "×": "*", "÷": "/", "−": "-", "²": "^2", "³": "^3",
                           "≤": "<=", "≥": ">=", "≠": "!="})
HISTORY_OPERATORS = {operator: chr(symbol) for symbol, operator in TRANSLATE.items()
                     if operator in ("->", "=>", "*", "-", "<=", ">=", "!=")}
HISTORY_TOKEN = re.compile(r"(?P<arrow>->|=>)|" + TOKEN.pattern)
OPEN_PAREN = re.compile(r"\s*\(")


def is_boolean(value):
    return value in (sp.true, sp.false) or isinstance(value, (Relational, BooleanFunction))


def normalize_input(text):
    # Translate supported mathematical symbols into the parser's operator spellings.
    return "".join(piece if index % 2 else piece.translate(TRANSLATE)
                   for index, piece in enumerate(QUOTED_TEXT.split(text))).strip()


def split_calculation(text, delimiter, *, arguments=False):
    """Split outside quoted strings and, for command arguments, outside brackets."""
    parts = []
    start = depth = 0
    pattern = re.compile(STRING_LITERAL + "|" + re.escape(delimiter) + r"|[()\[\]]")
    for match in pattern.finditer(text):
        token = match.group()
        if token == delimiter and not depth:
            parts.append(text[start:match.start()].strip())
            start = match.end()
        elif arguments:
            if token in ("(", "["):
                depth += 1
            elif token in (")", "]"):
                depth -= 1
    return [*parts, text[start:].strip()]


def _expand_base_literals(text: str, registry: UnitRegistry) -> str:
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

    return "".join(piece if index % 2 else BASE_LITERAL.sub(convert, piece)
                   for index, piece in enumerate(QUOTED_TEXT.split(text)))


def decimal_literals(text: str, registry: UnitRegistry) -> str:
    """Normalize integer bases and digit separators, preserving names and units."""
    text = _expand_base_literals(text, registry)
    # Remove grouping underscores only from numbers; unit suffixes must keep theirs.
    if "_" not in text:
        return text
    return TOKEN.sub(lambda match: match.group().replace("_", "")
                     if match.lastgroup in ("number", "dms") else match.group(), text)


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
        self.preserve_relation = False
        self.dependent_functions = {}
        text = _expand_base_literals(text, calculator.registry)
        self.tokens = []
        position = 0
        while position < len(text):
            if text[position].isspace():
                position += 1
                continue
            match = TOKEN.match(text, position)
            if not match:
                raise CalcError(f"Unexpected character at column {position + 1}: {text[position]!r}")
            token = match.group().replace("_", "") if match.lastgroup in ("number", "dms") else match.group()
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

    def function_arguments(self, name):
        self.expect("(")
        args = []
        outer_relation = self.preserve_relation
        outer_functions = self.dependent_functions
        if name == "deSolve":
            # Its last two arguments declare the independent and dependent variables.
            # Recognize the named dependent function while reading the ODE itself.
            depth, tail = 0, []
            for kind, token in self.tokens[self.index:]:
                if token == ")" and depth == 0:
                    break
                if token in ("(", "["):
                    depth += 1
                elif token in (")", "]"):
                    depth -= 1
                elif depth == 0:
                    tail.append((kind, token))
            if len(tail) >= 4 and tail[-4][1] == tail[-2][1] == "," and tail[-3][0] == tail[-1][0] == "name":
                self.dependent_functions = {**outer_functions, tail[-1][1]: sp.Symbol(tail[-3][1])}
        if self.peek()[1] != ")":
            while True:
                index = len(args)
                self.preserve_relation = index in RELATION_ARGUMENTS.get(name, ())
                if name == "deSolve" and index:
                    self.dependent_functions = outer_functions
                if name in ("limit", "Σ", "Π") and index >= 2 and (
                        self.peek()[1] in ("∞", "inf") or (self.peek()[1] in ("-", "+")
                        and self.tokens[self.index + 1][1] in ("∞", "inf"))):
                    sign = -1 if self.peek()[1] == "-" else 1
                    if self.peek()[1] in ("-", "+"):
                        self.take()
                    self.take()
                    args.append(Quantity(sign * sp.oo))
                else:
                    args.append(self.expression())
                if self.peek()[1] != ",":
                    break
                self.take()
        self.expect(")")
        self.preserve_relation = outer_relation
        self.dependent_functions = outer_functions
        return args

    def expression(self, minimum=0):
        # First read an operand: a literal, prefix sign, group, unit, or named value.
        # minimum is the weakest operator precedence this recursive call may consume.
        kind, token = self.take()
        if kind == "number":
            try:
                left = Quantity(sp.Rational(token)).checked()
            except (ValueError, ZeroDivisionError):
                raise CalcError("Invalid number or zero denominator.") from None
        elif kind == "dms" and not self.unit_only:
            degrees, minutes, seconds, _ = re.split("[°′″]", token)
            minutes, seconds = sp.Rational(minutes), sp.Rational(seconds)
            if minutes >= 60 or seconds >= 60:
                raise CalcError("Angle minutes and seconds must be less than 60.")
            angle = sp.Integer(degrees) + minutes / 60 + seconds / 3600
            left = Quantity(angle * ANGLE_SUFFIXES["°"] / angle_scale(self.calculator.mode))
        elif kind == "string" and not self.unit_only:
            left = Quantity(Str(json.loads(token)))
        elif token in ("+", "-"):
            # Powers bind more tightly than a leading sign: -2^2 means -(2^2).
            left = self.expression(25)
            if token == "-":
                left = left.negate()
        elif token == "~" and not self.unit_only:
            # NOT has the same precedence as unary signs, below exponentiation.
            left = self.expression(25).bitwise("~")
        elif token == "not" and not self.unit_only:
            left = self.expression(5)
            left = Quantity(sp.Not(left.value)) if is_boolean(left.value) else left.bitwise("~")
        elif kind == "root" and not self.unit_only:
            if self.peek()[1] == "(":
                self.take()
                argument = self.expression()
                self.expect(")")
            else:
                # An unparenthesized operand includes suffixes and stops before infix powers.
                argument = self.expression(PRECEDENCE["^"] + 1)
            left = self.calculator.function("sqrt", [argument])
        elif token == "(":
            left = self.expression()
            self.expect(")")
        elif token == "[" and not self.unit_only:
            elements = []
            if self.peek()[1] != "]":
                while True:
                    element = self.expression()
                    if element.dims != ZERO or isinstance(element.value, sp.MatrixBase):
                        raise CalcError("Lists must contain dimensionless values or matrix rows.")
                    elements.append(element.value)
                    if self.peek()[1] != ",":
                        break
                    self.take()
            self.expect("]")
            if elements and all(isinstance(row, sp.Tuple) for row in elements):
                if any(len(row) != len(elements[0]) or any(not is_scalar(item) for item in row)
                       for row in elements):
                    raise CalcError("A matrix needs equal-length rows of scalar expressions.")
                left = Quantity(sp.ImmutableMatrix([list(row) for row in elements]))
            else:
                left = Quantity(sp.Tuple(*elements))
        elif kind == "unit":
            unit = self.calculator.registry.get(token)
            if self.unit_only and unit.constant:
                raise CalcError("A physical constant is not a conversion target.")
            left = Quantity(unit.scale + (0 if self.unit_only else unit.offset), unit.dims, unit)
        elif kind == "name" and not self.unit_only and token not in MATH_WORD_OPERATORS:
            if self.peek()[1] == "(" and (token in FUNCTIONS or token in EQUATION_NAMES):
                args = self.function_arguments(token)
                if token in EQUATION_NAMES:
                    left = self.calculator.equation(token, args, self.equation_stack,
                                                    self.validating_equation)
                else:
                    left = self.calculator.function(token, args)
            elif token in self.dependent_functions:
                variable = self.dependent_functions[token]
                value = sp.Function(token)(variable)
                order = 0
                while self.peek()[1] in ("'", "′", "″"):
                    order += 2 if self.take()[1] == "″" else 1
                if order:
                    value = sp.diff(value, variable, order)
                if self.peek()[1] == "(":
                    args = self.function_arguments(token)
                    if len(args) != 1 or args[0].dims != ZERO:
                        raise CalcError("The dependent function needs one dimensionless argument.")
                    value = value.subs(variable, scalar(args[0].value))
                left = Quantity(value)
            elif token in EQUATION_NAMES:
                raise CalcError(f"Use {token}(expression) to call an equation.")
            elif token in RESERVED:
                left = Quantity(RESERVED[token])
            elif token == "ans":
                left = Quantity(sp.Symbol("ans")) if self.validating_equation else self.calculator.answer
            else:
                # Unassigned names remain symbolic rather than being treated as errors.
                left = self.local_variables.get(token) or self.calculator.variables.get(token)
                if left is None:
                    left = Quantity(sp.Symbol(token))
        else:
            raise CalcError(f"Expected a number, variable, unit, or parenthesis; found '{token or 'end of input'}'.")

        # Extend the operand with suffixes and operators until a weaker operator
        # or a delimiter belongs to the enclosing expression.
        while True:
            kind, token = self.peek()
            if kind == "unit" and minimum <= 40:
                self.take()
                unit = self.calculator.registry.get(token)
                if not is_scalar(left.value):
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
            if not self.unit_only and token in ANGLE_SUFFIXES and minimum <= 40:
                self.take()
                if left.dims != ZERO:
                    raise CalcError("An angle suffix requires a dimensionless expression.")
                left = Quantity(scalar(left.value) * ANGLE_SUFFIXES[token] / angle_scale(self.calculator.mode))
                continue
            if not self.unit_only and token == "ᵀ" and minimum <= 40:
                self.take()
                if not isinstance(left.value, sp.MatrixBase):
                    raise CalcError("Transpose requires a matrix.")
                left = Quantity(left.value.T)
                continue
            if not self.unit_only and token in CONVERSIONS and minimum <= 1:
                self.take()
                if left.dims != ZERO:
                    raise CalcError("This conversion requires a dimensionless value.")
                base = None
                if token == "▶logbase":
                    self.expect("(")
                    argument = self.expression()
                    self.expect(")")
                    if argument.dims != ZERO:
                        raise CalcError("A logarithm base must be dimensionless.")
                    base = argument.value
                left = convert(token, left, self.calculator.mode, base).checked()
                continue
            if token in COMPARISONS and minimum <= 5 and not self.unit_only:
                # Compare adjacent operands in a chain, after all arithmetic.
                previous = left
                result = True
                while self.peek()[1] in COMPARISONS:
                    op = self.take()[1]
                    right = self.expression(6)
                    # Evaluate every pair, even after False, to keep reporting bad operands.
                    if self.preserve_relation:
                        if previous.dims != right.dims:
                            raise CalcError("Cannot compare quantities with different dimensions.")
                        result = sp.And(result, COMPARISONS[op](scalar(previous.value), scalar(right.value), evaluate=False),
                                        evaluate=False)
                    else:
                        comparison = previous.compare(op, right)
                        result = result and comparison.value is sp.true
                    previous = right
                left = Quantity(result if self.preserve_relation else sp.true if result else sp.false)
                continue
            # Arithmetic binds before shifts, AND, XOR, and OR; all bind before
            # comparisons. Infix xor is recognized before implicit multiplication.
            precedence = PRECEDENCE.get(token)
            if token in LOGICAL_PRECEDENCE and (is_boolean(left.value) or (
                    minimum == 6 and (token != "xor" or self.xor_right_is_boolean()))):
                precedence = LOGICAL_PRECEDENCE[token]
            implicit = False
            if precedence is None and (kind in ("number", "name", "root") or token == "(") and not self.unit_only:
                # Adjacent operands such as 2(x+1) imply multiplication.
                precedence, token, implicit = 20, "*", True
            if precedence is None or precedence < minimum:
                break
            if self.unit_only and (token in BITWISE or token in MATH_WORD_OPERATORS or token in ELEMENTWISE or token == "∠"):
                raise CalcError("This operator cannot be used in conversion targets.")
            if not implicit:
                self.take()
            # Equal precedence on the right makes powers associate right to left.
            # Other operators use a higher threshold so they associate left to right.
            right = self.expression(precedence if token in ("^", "**", ".^") else precedence + 1)
            left = self.binary(token, left, right)
        return left.checked()

    def xor_right_is_boolean(self):
        depth = 0
        for kind, token in self.tokens[self.index + 1:]:
            if token in ("(", "["):
                depth += 1
            elif token in (")", "]"):
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and token in (",", "and", "or", "xor"):
                break
            elif token in COMPARISONS or (kind == "name" and token in ("True", "False", "not", "isPrime")):
                return True
        return False

    def binary(self, token, left, right):
        lhs, rhs = left.value, right.value
        if token == "&" and isinstance(lhs, Str) and isinstance(rhs, Str):
            return Quantity(Str(lhs.name + rhs.name))
        if token in MATH_WORD_OPERATORS and is_boolean(lhs) and is_boolean(rhs):
            return Quantity({"and": sp.And, "or": sp.Or, "xor": sp.Xor}[token](lhs, rhs))
        if token in BITWISE or token in MATH_WORD_OPERATORS:
            return left.bitwise(MATH_WORD_OPERATORS.get(token, token), right)
        if token in ELEMENTWISE or token == "∠" or any(isinstance(value, sp.MatrixBase) for value in (lhs, rhs)):
            if left.dims != ZERO or right.dims != ZERO:
                raise CalcError("This operator requires dimensionless operands.")
            if token == "∠":
                return Quantity(sp.expand_complex(scalar(lhs) * sp.exp(sp.I * scalar(rhs) * angle_scale(self.calculator.mode))))
            if token in ELEMENTWISE:
                operator = ELEMENTWISE[token]
                return Quantity(map_values(lambda a, b: Quantity(a).arithmetic(operator, Quantity(b)).value, lhs, rhs))
            if token in ("+", "-", "*", "/", "^", "**"):
                operation = {"+": lambda: lhs + rhs, "-": lambda: lhs - rhs, "*": lambda: lhs * rhs,
                             "/": lambda: lhs / rhs, "^": lambda: lhs ** rhs, "**": lambda: lhs ** rhs}
                if token == "/" and isinstance(rhs, sp.MatrixBase):
                    raise CalcError("Use multiplication by the inverse to divide by a matrix.")
                return Quantity(operation[token]())
        return left.arithmetic("^" if token == "**" else token, right)


@dataclass(frozen=True)
class HistoryEntry:
    # Store display strings so history can be restored without executing expressions.
    source: str
    result: str
    is_error: bool = False

    @property
    def line(self):
        return self.display_line()[1]

    def display_line(self, symbols=False) -> tuple[str, str]:
        source, result = self.display_parts(symbols)
        return source, f"{source} = {'Error: ' if self.is_error else ''}{result}"

    def display_parts(self, symbols=False) -> tuple[str, str]:
        return self._symbolic_parts if symbols else (self.source, self.result)

    @cached_property
    def _symbolic_parts(self) -> tuple[str, str]:
        # Forth continuations that produce output end their definition with a semicolon.
        if self.is_error or self.source.lstrip().startswith(":") or ";" in self.source:
            return self.source, self.result
        return symbolize_expression(self.source), symbolize_expression(self.result)


def symbolize_expression(text: str) -> str:
    """Use Unicode spellings for math tokens while keeping fraction notation."""
    def substitute(match: re.Match[str]) -> str:
        token = match.group()
        if token == "pi":
            return "π"
        if token == "sqrt" and OPEN_PAREN.match(text, match.end()):
            return "√"
        return HISTORY_OPERATORS.get(token, token)

    return HISTORY_TOKEN.sub(substitute, text)


# Calculation engine: session variables, exact answers, and evaluation settings.
class Calculator:
    def __init__(self, mode="radian", precision=50, output_mode="exact", *, registry: UnitRegistry | None = None):
        self.registry = registry if registry is not None else UnitRegistry()
        self.variables = {}
        self.equations = {}
        self.unchecked_equations: set[str] = set()
        self.history = deque(maxlen=30)
        self.answer = Quantity(sp.S.Zero)
        self.random = Random(0)
        self.statistics = {}
        self.unit_definitions = {}
        self.set_mode(mode)
        self.set_precision(precision)
        self.set_output_mode(output_mode)

    def set_mode(self, mode):
        if mode == "rad":
            mode = "radian"
        elif mode == "deg":
            mode = "degree"
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
        except (ValueError, TypeError, ZeroDivisionError, RecursionError, OverflowError, NotImplementedError,
                MatrixError, IndexError) as exc:
            raise CalcError(f"Cannot evaluate this expression: {exc}") from None

    def evaluate(self, text, record=True, *, approximate=False):
        return self._evaluate(text, record, approximate)[0]

    def calculate(self, text, *, approximate=False, record=True):
        return self._evaluate(text, record, approximate, format_result=True)[1]

    def _evaluate(self, text, record, approximate, *, format_result=False) -> tuple[Quantity, str]:
        # Failed input is recorded here; only successful evaluation updates ans.
        source = text.strip()
        try:
            evaluated = self._evaluate_source(source)
            value = evaluated.value
            result = self.format(value, approximate=approximate) if record or format_result else ""
            if record:
                self.history.append(HistoryEntry(decimal_literals(source, self.registry), result))
        except CalcError as exc:
            if record and source:
                # Keep invalid input verbatim, including malformed numeric literals.
                self.history.append(HistoryEntry(source, str(exc), is_error=True))
            raise
        self.variables.update(evaluated.variables)
        if evaluated.statistics is not None:
            self.statistics = evaluated.statistics
        self.answer = value
        return value, result

    def _evaluate_source(self, source):
        # Peel off assignment and conversion arrows before parsing the expression.
        # This also permits a conversion followed by assignment, such as 3_in=>_ft->x.
        text = normalize_input(source)
        if not text:
            raise CalcError("Enter an expression.")
        command, *command_text = text.split(maxsplit=1)
        if command in COMMANDS:
            try:
                args = split_calculation(command_text[0], ",", arguments=True) if command_text else []
                return math_command(self, command, args)
            except (ValueError, TypeError, ZeroDivisionError, RecursionError, OverflowError, NotImplementedError,
                    MatrixError, IndexError) as exc:
                if isinstance(exc, CalcError):
                    raise
                raise CalcError(f"Cannot run {command}: {exc}") from None
        assignment = None
        parts = split_calculation(text, "->")
        if len(parts) > 2:
            raise CalcError("Use one assignment arrow per calculation.")
        text = parts[0]
        if len(parts) == 2:
            assignment = self.variable_name(parts[1])
        parts = split_calculation(text, "=>")
        if len(parts) > 2:
            raise CalcError("Use one conversion arrow per calculation.")
        if len(parts) == 2:
            expression, target_text = parts
            value = self.parse(expression)
            if not is_scalar(value.value):
                raise CalcError("Unit conversion requires a scalar expression.")
            # A simple offset target must be handled before compound-unit parsing.
            if re.fullmatch(r"_°?[^\W\d_][^\W_]*", target_text):
                target = self.registry.get(target_text)
                if target.constant:
                    raise CalcError("A physical constant is not a conversion target.")
            else:
                parsed = self.parse(target_text, unit_only=True)
                if parsed.affine:
                    raise CalcError("Offset temperature units cannot appear in compound targets.")
                if (not is_scalar(parsed.value) or parsed.value.is_number is not True
                        or parsed.value.is_positive is not True):
                    raise CalcError("A conversion target must have a positive numeric scale.")
                target = Unit(target_text, "compound unit", "Compound", parsed.value, parsed.dims)
            if value.dims != target.dims:
                raise CalcError("The source and target units have different dimensions.")
            # Converting changes the display unit; the underlying SI value stays exact.
            value = replace(value, display=target)
        else:
            value = self.parse(text)
        return CommandResult(value, {assignment: value} if assignment is not None else {})

    @staticmethod
    def variable_name(name):
        if not re.fullmatch(NAME, name, re.UNICODE):
            raise CalcError("A variable name starts with a letter and contains letters or digits.")
        if (name in RESERVED or name in LEGACY_FUNCTIONS or name in MATH_WORD_OPERATORS or name in COMMANDS
                or name in EQUATION_NAMES or name == "ans"):
            raise CalcError(f"'{name}' is reserved.")
        return name

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
        if not is_scalar(value.value):
            raise CalcError("An equation must produce a scalar expression.")
        if self.equations.get(name) != expression:
            self.unchecked_equations.discard(name)
        self.equations[name] = expression

    def equation(self, name, args, stack=(), validating=False):
        if len(args) != 1:
            raise CalcError(f"Wrong number of arguments for {name}; use {name}(x).")
        argument = args[0]
        if not is_scalar(argument.value) or argument.dims != ZERO:
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
        if (not is_scalar(value.value) or value.affine or value.value.free_symbols
                or value.value.is_positive is not True):
            raise CalcError("Define a unit using a positive, finite, numeric quantity without a temperature offset.")
        # Store the evaluated scale, so saved units do not depend on session variables.
        definition = self.registry.format(replace(value, display=None))
        self.registry.add(name, "user-defined: " + expression, "Custom", value.value, value.dims)
        self.unit_definitions[name] = definition

    def function(self, name, args):
        # Validate argument counts and types before dispatching allowed SymPy operations.
        name = ALIASES.get(name, name)
        accepted = FUNCTION_ARITIES.get(name, (1,))
        if (accepted is None and not args) or (accepted is not None and len(args) not in accepted):
            raise CalcError(f"Wrong number of arguments for {name}.")
        if name in ARITIES:
            return extended_function(self, name, args)
        if name in STAT_FUNCTIONS:
            return stat_function(name, args, self)
        first = args[0]
        if name in ("min", "max"):
            if any(a.dims != first.dims for a in args):
                raise CalcError("min/max arguments must have the same dimensions.")
            return replace(first, value=minmax(name, *(a.value for a in args)), presentation=None).checked()
        if name == "solve":
            if args[1].dims != ZERO:
                raise CalcError("Solving requires a dimensionless variable.")
            return Quantity(solve([a.value for a in args])).checked()
        if name in ("abs", "floor", "ceil") and isinstance(first.value, (sp.Tuple, sp.MatrixBase)):
            fn = {"abs": sp.Abs, "floor": sp.floor, "ceil": sp.ceiling}[name]
            return Quantity(map_values(lambda item: fn(scalar(item)), first.value)).checked()
        if any(not is_scalar(a.value) for a in args):
            raise CalcError(f"{name} requires scalar arguments.")
        if name in ("simplify", "expand", "factor", "abs"):
            value = first.value
            if len(args) == 2:
                if not isinstance(args[1].value, sp.Symbol) or args[1].dims != ZERO:
                    raise CalcError("The second argument must be an unassigned symbolic variable.")
                variable = args[1].value
                value = sp.factor(value, variable) if name == "factor" else sp.collect(sp.expand(value), variable)
            else:
                fn = sp.Abs if name == "abs" else getattr(sp, name)
                value = fn(value)
            return replace(first, value=value, presentation=None).checked()
        if name == "approx":
            digits = self.precision
            if len(args) == 2:
                if args[1].dims != ZERO or args[1].value.is_Integer is not True or args[1].value < 2:
                    raise CalcError("approx precision must be an integer of at least 2.")
                digits = int(args[1].value)
            # Only this explicit operation introduces arbitrary-precision Float values.
            return replace(first, value=sp.N(first.value, digits), presentation=None).checked()
        if name in ("sqrt", "cbrt"):
            result = first.arithmetic("^", Quantity(sp.Rational(1, 2 if name == "sqrt" else 3)))
            if name == "cbrt" and first.value.is_real is True:
                result = replace(result, value=sp.real_root(first.value, 3))
            return result
        if name == "subs":
            if not isinstance(args[1].value, sp.Symbol) or args[1].dims != ZERO or args[2].dims != ZERO:
                raise CalcError("Use subs(expression, unassigned_variable, dimensionless_value).")
            return replace(first, value=first.value.subs(args[1].value, args[2].value), presentation=None).checked()
        # Calculus and solving require a symbolic variable, rather than its assigned value.
        if name in ("diff", "integrate"):
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
            else:
                if len(args) == 4:
                    if any(a.dims != ZERO for a in args[2:]):
                        raise CalcError("Integration bounds must be dimensionless.")
                    value = sp.integrate(first.value, (symbol, args[2].value, args[3].value))
                else:
                    value = sp.integrate(first.value, symbol)
            return replace(first, value=value, presentation=None).checked()
        if any(a.dims != ZERO for a in args):
            raise CalcError(f"{name} requires dimensionless arguments.")
        value = first.value
        # SymPy uses radians, so degree mode converts inputs and inverse-trig outputs.
        if name in TRIG and self.mode == "degree":
            value *= sp.pi / 180
        if name == "factorial":
            if value.is_Integer is not True or value < 0:
                raise CalcError("Factorial requires a nonnegative integer.")
            result = sp.factorial(value)
        elif name in ("nPr", "nCr"):
            n, r = (a.value for a in args)
            if not all(v.is_Integer and v >= 0 for v in (n, r)):
                raise CalcError(f"{name} requires nonnegative integers.")
            result = sp.binomial(n, r) * (sp.factorial(r) if name == "nPr" else 1)
        elif name == "log":
            result = sp.log(value, args[1].value) if len(args) == 2 else sp.log(value, 10)
        else:
            fn = {"ln": sp.log, "ceil": sp.ceiling}.get(name, getattr(sp, name, None))
            if fn is None:
                raise CalcError(f"Unknown function: {name}")
            result = fn(value)
        if name in INVERSE_TRIG and self.mode == "degree":
            result *= 180 / sp.pi
        if not is_scalar(result):
            raise CalcError(f"{name} did not produce a scalar result.")
        return Quantity(result).checked()
