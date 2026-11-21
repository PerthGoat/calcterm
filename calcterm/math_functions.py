"""Calculator math functions and operators that work on extended value types."""

from decimal import Decimal
from itertools import accumulate
import re

from sympy.core.relational import Relational
from sympy.logic.boolalg import BooleanFunction

from .core import CalcError, Quantity, Str, ZERO, expression_text, is_scalar, sp


ALIASES = {"d": "diff", "∫": "integrate", "ceiling": "ceil"}
TRIG = {"sin", "cos", "tan", "csc", "sec", "cot"}
INVERSE_TRIG = {"a" + name for name in TRIG}
HYPERBOLIC = {name + "h" for name in TRIG}
ALIASES.update({name + "⁻¹": "a" + name for name in TRIG | HYPERBOLIC})
DIRECT = {"conj": sp.conjugate, "real": sp.re, "imag": sp.im}
NUMBER_ARITIES = {"exact": (1, 2), "round": (1, 2), "iPart": (1,), "fPart": (1,),
                  "sign": (1,), "mod": (2,), "remain": (2,), "lcm": (2,), "gcd": (2,), "root": (2,)}
LIST_ARITIES = {"seq": (4, 5), "sum": (1, 2, 3), "product": (1, 2, 3), "cumSum": (1,),
                "left": (1, 2), "mid": (2, 3), "right": (1, 2), "Δlist": (1,), "polyEval": (2,),
                "list▶mat": (1, 2), "mat▶list": (1,), "dim": (1,)}
MATRIX_ARITIES = {"det": (1, 2), "ref": (1, 2), "rref": (1, 2), "simult": (2, 3), "identity": (1,),
                  "augment": (2,), "diag": (1,), "eigVl": (1,), "eigVc": (1,), "randMat": (2,), "newMat": (2,),
                  "subMat": (3, 4, 5), "norm": (1,), "rowNorm": (1,), "colNorm": (1,), "rowDim": (1,),
                  "colDim": (1,), "rowSwap": (3,), "rowAdd": (3,), "mRow": (3,), "mRowAdd": (4,),
                  "unitV": (1,), "crossP": (2,), "dotP": (2,)}
ANGLE_ARITIES = {"angle": (1,), "P▶Rx": (2,), "P▶Ry": (2,), "R▶Pr": (2,), "R▶Pθ": (2,)}
ALGEBRA_ARITIES = {"zeros": (2,), "comDenom": (1, 2), "propFrac": (1, 2), "nSolve": (2,), "tExpand": (1,),
                   "tCollect": (1,), "cSolve": (2,), "cFactor": (1, 2), "cZeros": (2,),
                   "getNum": (1,), "getDenom": (1,)}
CALCULUS_ARITIES = {"limit": (3, 4), "Σ": (4,), "Π": (4,), "fMin": (2,), "fMax": (2,), "arcLen": (4,),
                    "taylor": (3, 4), "nDeriv": (2, 3), "nInt": (4,), "deSolve": (3,), "impDif": (3,)}
STRING_ARITIES = {"string": (1,), "expr": (1,), "inString": (2, 3), "format": (1, 2), "char": (1,), "ord": (1,)}
BASE_ARITIES = {"shift": (1, 2), "rotate": (1, 2), "isPrime": (1,)}
ARITIES = {**NUMBER_ARITIES, **LIST_ARITIES, **MATRIX_ARITIES, **ANGLE_ARITIES, **ALGEBRA_ARITIES,
           **CALCULUS_ARITIES, **STRING_ARITIES, **BASE_ARITIES, **dict.fromkeys(DIRECT, (1,))}
ELEMENTWISE = {".+": "+", ".-": "-", ".*": "*", "./": "/", ".^": "^"}
ANGLE_SUFFIXES = {"°": sp.pi / 180, "ʳ": sp.S.One, "ᵍ": sp.pi / 200}
CONVERSIONS = {"▶DMS", "▶DD", "▶Grad", "▶Rad", "▶Polar", "▶Rect", "▶Cylind", "▶Sphere",
               "▶ln", "▶logbase", "▶Hex", "▶Bin", "▶Dec"}
RELATION_ARGUMENTS = {"solve": (0,), "cSolve": (0,), "nSolve": (0, 1), "left": (0,), "right": (0,),
                      "impDif": (0,), "deSolve": (0,)}


def integer(value, label="Argument", minimum=None):
    if not isinstance(value, sp.Integer) or (minimum is not None and value < minimum):
        limit = f" of at least {minimum}" if minimum is not None else ""
        raise CalcError(f"{label} must be an integer{limit}.")
    return int(value)


def scalar(value):
    if not is_scalar(value):
        raise CalcError("Expected a scalar expression.")
    return value


def symbol(value):
    if not isinstance(value, sp.Symbol):
        raise CalcError("Expected an unassigned symbolic variable.")
    return value


def sequence(value):
    if not isinstance(value, sp.Tuple):
        raise CalcError("Expected a list.")
    return value


def matrix(value):
    if not isinstance(value, sp.MatrixBase):
        raise CalcError("Expected a matrix such as [[1, 2], [3, 4]].")
    return value


def vector(value):
    if isinstance(value, sp.Tuple):
        return sp.ImmutableMatrix(list(value))
    if 1 not in matrix(value).shape:
        raise CalcError("Expected a row or column vector.")
    return value


def map_values(operation, *values):
    """Apply an operation to equal-sized containers, broadcasting scalar operands."""
    container = next((value for value in values if isinstance(value, (sp.Tuple, sp.MatrixBase))), None)
    if container is None:
        return operation(*values)
    if isinstance(container, sp.MatrixBase):
        if any(isinstance(value, sp.Tuple) or (isinstance(value, sp.MatrixBase) and value.shape != container.shape)
               for value in values):
            raise CalcError("Matrix dimensions must match.")
        return sp.ImmutableMatrix(*container.shape, lambda row, col: operation(*(
            value[row, col] if isinstance(value, sp.MatrixBase) else value for value in values)))
    if any(isinstance(value, sp.MatrixBase) or (isinstance(value, sp.Tuple) and len(value) != len(container))
           for value in values):
        raise CalcError("List lengths must match.")
    return sp.Tuple(*(operation(*(value[i] if isinstance(value, sp.Tuple) else value for value in values))
                      for i in range(len(container))))


def numeric(name, values):
    value, *rest = map(scalar, values)
    if name == "exact":
        tolerance = rest[0] if rest else None
        if tolerance is not None and tolerance.is_positive is not True:
            raise CalcError("Tolerance must be positive.")
        return (sp.nsimplify(value, [sp.pi, sp.E], tolerance=float(tolerance) if tolerance is not None else None)
                if value.has(sp.Float) else value)
    if name == "round":
        if not rest and (not value.is_number or value.is_real is not True or value.is_zero):
            return sp.N(value, 12)
        digits = integer(rest[0], "Digits") if rest else 11 - sp.floor(sp.log(sp.Abs(value), 10))
        scale = sp.Integer(10) ** digits
        return sp.sign(value) * sp.floor(sp.Abs(value) * scale + sp.S.Half) / scale
    if name in ("iPart", "fPart"):
        integral = sp.sign(value) * sp.floor(sp.Abs(value))
        return integral if name == "iPart" else value - integral
    if name == "sign":
        return sp.sign(value) if value.is_real is not False else sp.simplify(value / sp.Abs(value))
    other = rest[0]
    if name == "mod":
        return sp.Mod(value, other)
    if name == "remain":
        quotient = value / other
        return value - other * sp.sign(quotient) * sp.floor(sp.Abs(quotient))
    if name in ("lcm", "gcd"):
        return getattr(sp, name)(integer(value), integer(other))
    index = integer(other, "Root index", 1)
    return sp.real_root(value, index) if value.is_real is True and index % 2 else sp.root(value, index)


def minmax(name, *values):
    compare = sp.Min if name == "min" else sp.Max
    if len(values) == 1 and isinstance(values[0], (sp.Tuple, sp.MatrixBase)):
        if not len(values[0]):
            raise CalcError(f"{name} requires at least one value.")
        return compare(*values[0])
    return map_values(compare, *values)


def list_function(name, values):
    value, *rest = values
    if name == "dim":
        if isinstance(value, sp.MatrixBase):
            return sp.Tuple(*value.shape)
        return sp.Integer(len(value.name if isinstance(value, Str) else sequence(value)))
    if name in ("left", "right") and isinstance(value, Relational):
        if rest:
            raise CalcError("An equation or inequality does not take a count.")
        return value.lhs if name == "left" else value.rhs
    if name in ("left", "mid", "right"):
        data = value.name if isinstance(value, Str) else sequence(value)
        if name == "mid":
            start = integer(rest[0], "Start", 1) - 1
            count = integer(rest[1], "Count", 0) if len(rest) == 2 else len(data)
        else:
            count = integer(rest[0], "Count", 0) if rest else 1
            start = 0 if name == "left" else max(0, len(data) - count)
        part = data[start:start + count]
        return Str(part) if isinstance(value, Str) else sp.Tuple(*part)
    if name == "seq":
        variable, first, last, *step = rest
        variable = symbol(variable)
        step = step[0] if step else sp.S.One
        count = sp.floor((last - first) / step)
        return sp.Tuple(*(scalar(value).subs(variable, first + i * step) for i in range(integer(count) + 1)))
    if name == "mat▶list":
        return sp.Tuple(*matrix(value))
    if name == "cumSum" and isinstance(value, sp.MatrixBase):
        return sp.ImmutableMatrix(*value.shape, lambda row, col: sp.Add(*(value[i, col] for i in range(row + 1))))
    data = sequence(value)
    if name in ("sum", "product"):
        start = integer(rest[0], "Start", 1) - 1 if rest else 0
        end = integer(rest[1], "End", 1) if len(rest) == 2 else len(data)
        return (sp.Add if name == "sum" else sp.Mul)(*data[start:end])
    if name == "cumSum":
        return sp.Tuple(*accumulate(data))
    if name == "Δlist":
        return sp.Tuple(*(right - left for left, right in zip(data, data[1:])))
    if name == "polyEval":
        result = sp.S.Zero
        for coefficient in data:
            result = result * scalar(rest[0]) + scalar(coefficient)
        return result
    columns = integer(rest[0], "Columns", 1) if rest else 1
    rows = (len(data) + columns - 1) // columns
    return sp.ImmutableMatrix(rows, columns, [*data, *([0] * (rows * columns - len(data)))])


def tolerance_test(tolerance):
    if tolerance is None:
        return lambda value: value.is_zero
    if scalar(tolerance).is_nonnegative is not True:
        raise CalcError("Tolerance must be nonnegative.")
    return lambda value: (sp.Abs(value) <= tolerance) if value.is_number else value.is_zero


def submatrix(value, start_row=sp.S.One, start_col=sp.S.One, end_row=None, end_col=None):
    row = integer(start_row, "Start row", 1) - 1
    col = integer(start_col, "Start column", 1) - 1
    bottom = value.rows if end_row is None else integer(end_row, "End row", 1)
    right = value.cols if end_col is None else integer(end_col, "End column", 1)
    if not (row < bottom <= value.rows and col < right <= value.cols):
        raise CalcError("Submatrix indices are out of range.")
    return value[row:bottom, col:right]


def matrix_function(name, values, random):
    value, *rest = values
    if name == "identity":
        return sp.ImmutableMatrix.eye(integer(value, "Size", 1))
    if name in ("newMat", "randMat"):
        rows, cols = (integer(item, "Dimension", 1) for item in values)
        return (sp.ImmutableMatrix.zeros(rows, cols) if name == "newMat"
                else sp.ImmutableMatrix(rows, cols, lambda *_: random.randint(-9, 9)))
    if name == "diag":
        if isinstance(value, sp.MatrixBase) and value.is_square:
            return sp.Tuple(*value.diagonal())
        return sp.ImmutableMatrix.diag(*vector(value))
    if name == "augment" and isinstance(value, sp.Tuple):
        return sp.Tuple(*value, *sequence(rest[0]))
    if name in ("unitV", "crossP", "dotP"):
        first = vector(value)
        if name == "unitV":
            return first / first.norm()
        second = vector(rest[0])
        if name == "dotP":
            return first.dot(second)
        if len(first) == len(second) == 2:
            result = sp.ImmutableMatrix([0, 0, first[0] * second[1] - first[1] * second[0]])
            return result.T if first.rows == 1 else result
        return first.cross(second)
    if name == "simult" and isinstance(rest[0], sp.Tuple):
        rest[0] = vector(rest[0])
    value = matrix(value)
    if name in ("det", "eigVl", "eigVc") and not value.is_square:
        raise CalcError(f"{name} requires a square matrix.")
    if name in ("det", "ref", "rref", "simult"):
        tolerance = rest[-1] if len(rest) == (2 if name == "simult" else 1) else None
        zero = tolerance_test(tolerance)
        if name == "det":
            if tolerance is None:
                return value.det()
            _, upper, swaps = value.LUdecomposition(iszerofunc=zero)
            return (-1) ** len(swaps) * sp.prod(item if not zero(item) else 0 for item in upper.diagonal())
        if name == "ref":
            return value.echelon_form(iszerofunc=zero)
        if name == "rref":
            return value.rref(iszerofunc=zero)[0]
        return value.LUsolve(matrix(rest[0]), iszerofunc=zero)
    if name == "augment":
        return value.row_join(matrix(rest[0]))
    if name == "eigVl":
        return sp.Tuple(*value.eigenvals(multiple=True))
    if name == "eigVc":
        return sp.ImmutableMatrix.hstack(*(v for _, _, vectors in value.eigenvects() for v in vectors))
    if name == "subMat":
        return submatrix(value, *rest)
    if name == "norm":
        return value.norm()
    if name == "rowNorm":
        return sp.Max(*(sp.Add(*(sp.Abs(v) for v in value.row(i))) for i in range(value.rows)))
    if name == "colNorm":
        return matrix_function("rowNorm", [value.T], random)
    if name == "rowDim":
        return sp.Integer(value.rows)
    if name == "colDim":
        return sp.Integer(value.cols)
    return row_operation(name, value, rest, sp.S.One)


def row_operation(name, value, indices, multiplier):
    result = matrix(value).as_mutable()
    rows = [integer(item, "Row", 1) - 1 for item in indices]
    if any(row >= result.rows for row in rows):
        raise CalcError("Row index is out of range.")
    if name == "rowSwap":
        result.row_swap(*rows)
    elif name == "mRow":
        result.row_op(rows[0], lambda entry, _: multiplier * entry)
    else:
        source, target = rows
        result.row_op(target, lambda entry, col: entry + multiplier * result[source, col])
    return result.as_immutable()


def angle_scale(mode):
    return ANGLE_SUFFIXES["°" if mode == "degree" else "ʳ"]


def angle_function(name, values, mode):
    value, *rest = map(scalar, values)
    scale = angle_scale(mode)
    if name == "angle":
        return sp.arg(value) / scale
    other = rest[0]
    if name == "P▶Rx":
        return value * sp.cos(other * scale)
    if name == "P▶Ry":
        return value * sp.sin(other * scale)
    if name == "R▶Pr":
        return sp.sqrt(value ** 2 + other ** 2)
    return sp.atan2(other, value) / scale


def convert(token, quantity, mode, base=None):
    value = quantity.value
    if token in ("▶Hex", "▶Bin", "▶Dec"):
        number = integer(value)
        if token == "▶Dec":
            return Quantity(sp.Integer(number))
        prefix, code = ("0h", "X") if token == "▶Hex" else ("0b", "b")
        return Quantity(sp.Integer(number), presentation=("-" if number < 0 else "") + prefix + format(abs(number), code))
    if token in ("▶DD", "▶DMS", "▶Grad", "▶Rad"):
        suffix = {"▶DD": "°", "▶DMS": "°", "▶Grad": "ᵍ", "▶Rad": "ʳ"}[token]
        radians = scalar(value) * angle_scale(mode)
        converted = sp.simplify(radians / ANGLE_SUFFIXES[suffix])
        if token == "▶DMS":
            if converted.is_real is not True or not converted.is_number:
                raise CalcError("DMS notation requires a real numeric angle.")
            absolute = sp.Abs(converted)
            degrees = sp.floor(absolute)
            minutes = sp.floor(60 * (absolute - degrees))
            seconds = sp.simplify(3600 * (absolute - degrees) - 60 * minutes)
            sign = "-" if converted.is_negative else ""
            return Quantity(value, presentation=f"{sign}{degrees}°{minutes}′{seconds}″")
        text = expression_text(converted)
        if not isinstance(converted, (sp.Number, sp.NumberSymbol)):
            text = f"({text})"
        return Quantity(value, presentation=text + suffix)
    if token in ("▶ln", "▶logbase"):
        value = scalar(value)
        if token == "▶ln":
            return Quantity(value, presentation=expression_text(value))
        base = scalar(base)
        if base.is_positive is False or base == 1:
            raise CalcError("A logarithm base must be positive and different from 1.")
        logarithm = lambda argument: sp.log(argument, base, evaluate=False)
        result = value.replace(lambda item: item.func == sp.log,
                               lambda item: logarithm(item.args[0]) / logarithm(sp.E))
        return Quantity(value, presentation=expression_text(result))
    scale = angle_scale(mode)
    if is_scalar(value):
        if token == "▶Polar":
            radius, theta = sp.Abs(value), sp.arg(value) / scale
            return Quantity(value, presentation=f"({expression_text(radius)})∠({expression_text(theta)})")
        if token == "▶Rect":
            return Quantity(sp.expand_complex(value))
    coords = list(vector(value))
    if quantity.coordinates:
        coordinate_system, original_scale = quantity.coordinates
        radius, theta, *height = coords
        if coordinate_system == "▶Sphere":
            phi = height[0] * original_scale
            height = [radius * sp.cos(phi)]
            radius *= sp.sin(phi)
        coords = [radius * sp.cos(theta * original_scale), radius * sp.sin(theta * original_scale), *height]
    if token == "▶Rect":
        return Quantity(sp.Tuple(*coords))
    if len(coords) != (2 if token == "▶Polar" else 3):
        raise CalcError("Wrong number of coordinates for this conversion.")
    x, y, *height = coords
    radius = sp.sqrt(x ** 2 + y ** 2)
    theta = sp.S.Zero if radius.is_zero else sp.atan2(y, x) / scale
    if token == "▶Sphere":
        z = height[0]
        return Quantity(sp.Tuple(sp.sqrt(radius ** 2 + z ** 2), theta, sp.atan2(radius, z) / scale),
                        coordinates=(token, scale))
    return Quantity(sp.Tuple(radius, theta, *height), coordinates=(token, scale))


def equation_expression(value):
    if isinstance(value, sp.Equality):
        return value.lhs - value.rhs
    return value if isinstance(value, (Relational, BooleanFunction)) else scalar(value)


def solve(values, real=True):
    expression, variable = values
    variables = tuple(map(symbol, variable)) if isinstance(variable, sp.Tuple) else (symbol(variable),)
    equations = list(expression) if isinstance(expression, sp.Tuple) else [expression]
    equations = [item for equation in equations for item in (equation.args if equation.func is sp.And else (equation,))]
    if any(isinstance(item, Relational) and not isinstance(item, sp.Equality) for item in equations):
        result = sp.reduce_inequalities([item if isinstance(item, Relational) else sp.Eq(item, 0)
                                         for item in equations], variables)
        if result.func is sp.And:
            result = sp.And(*(constraint for constraint in result.args if not constraint.has(sp.oo, -sp.oo)))
        return result
    equations = [equation_expression(item) for item in equations]
    solutions = sp.solve(equations, variables, dict=True)
    rows = [tuple(solution.get(variable, variable) for variable in variables) for solution in solutions]
    if real:
        rows = [row for row in rows if all(value.is_real is not False for value in row)]
    return sp.Tuple(*(row[0] if len(variables) == 1 else sp.Tuple(*row) for row in rows))


def algebra(name, values, precision):
    value, *rest = values
    if name in ("zeros", "cZeros", "cSolve"):
        return solve(values, real=name == "zeros")
    if name == "nSolve":
        target = rest[0]
        variable, guess = (symbol(target.lhs), scalar(target.rhs)) if isinstance(target, sp.Equality) else (symbol(target), 0)
        return sp.nsolve(equation_expression(value), variable, guess, prec=precision)
    expression = scalar(value)
    variable = [symbol(rest[0])] if rest else []
    if name == "comDenom":
        result = sp.together(expression)
        return sp.collect(result, variable[0]) if variable else result
    if name == "propFrac":
        return sp.apart(expression, *variable)
    if name == "cFactor":
        return sp.factor(expression, *variable, extension=sp.I)
    if name in ("getNum", "getDenom"):
        return sp.fraction(sp.cancel(expression))[name == "getDenom"]
    if name == "tExpand":
        return sp.expand_trig(expression)
    return sp.trigsimp(expression, method="fu")


def calculus(name, values, precision):
    value, variable, *rest = values
    variable = symbol(variable)
    if name == "deSolve":
        return solve_ode(value, variable, symbol(rest[0]))
    expression = equation_expression(value)
    if name == "limit":
        point, *direction = rest
        sides = {sp.S.NegativeOne: "-", sp.S.Zero: "+-", sp.S.One: "+", Str("-"): "-",
                 Str("+"): "+", Str("+-"): "+-"}
        if direction and direction[0] not in sides:
            raise CalcError("Limit direction must be -1, 0, or 1.")
        return sp.limit(expression, variable, point, dir=sides[direction[0]] if direction else "+-")
    if name in ("Σ", "Π"):
        operation = sp.summation if name == "Σ" else sp.product
        return operation(expression, (variable, *rest))
    if name in ("fMin", "fMax"):
        from sympy.calculus.util import maximum, minimum
        extreme = (minimum if name == "fMin" else maximum)(expression, variable)
        return solve([expression - extreme, variable])
    if name == "arcLen":
        return sp.integrate(sp.sqrt(1 + sp.diff(expression, variable) ** 2), (variable, *rest))
    if name == "nInt":
        return sp.Integral(expression, (variable, *rest)).evalf(precision)
    if name == "taylor":
        order = integer(rest[0], "Order", 0)
        return sp.series(expression, variable, rest[1] if len(rest) == 2 else 0, order + 1).removeO()
    if name == "nDeriv":
        step = scalar(rest[0]) if rest else sp.Rational(1, 1000)
        return sp.expand((expression.subs(variable, variable + step) - expression.subs(variable, variable - step)) / (2 * step))
    return sp.idiff(expression, symbol(rest[0]), variable)


def solve_ode(value, variable, dependent):
    function = sp.Function(dependent.name)(variable)
    equations = list(value.args) if value.func is sp.And else [value]
    differential = [equation for equation in equations if variable in equation.free_symbols and equation.has(sp.Derivative)]
    if len(differential) != 1:
        raise CalcError("deSolve requires one differential equation in the independent variable.")
    conditions = {}
    for equation in equations:
        if equation == differential[0]:
            continue
        if not isinstance(equation, sp.Equality):
            raise CalcError("Initial conditions must be equations.")
        lhs, rhs = equation.lhs, equation.rhs
        if lhs.func != function.func and not (isinstance(lhs, sp.Subs) and lhs.has(function)):
            raise CalcError("Put the dependent function or its derivative on the left of an initial condition.")
        conditions[lhs] = rhs
    result = sp.dsolve(equation_expression(differential[0]), function, ics=conditions or None)
    if isinstance(result, list):
        return sp.Tuple(*(item.rhs if item.lhs == function else item for item in result))
    return result.rhs if result.lhs == function else result


def text_value(value):
    if not isinstance(value, Str):
        raise CalcError('Expected text in double quotes.')
    return value.name


def string_function(name, args, calculator):
    first, *rest = args
    if name == "string":
        return Quantity(Str(calculator.format(first)))
    value = first.value
    if name == "expr":
        return calculator.parse(text_value(value))
    if name == "char":
        code = integer(value, "Character code", 0)
        if code > 255:
            raise CalcError("Character code must be between 0 and 255.")
        return Quantity(Str(chr(code)))
    if name == "ord":
        text = text_value(value)
        if not text:
            raise CalcError("ord requires nonempty text.")
        return Quantity(sp.Integer(ord(text[0])))
    if name == "inString":
        start = integer(rest[1].value, "Start", 1) - 1 if len(rest) == 2 else 0
        return Quantity(sp.Integer(text_value(value).find(text_value(rest[0].value), start) + 1))
    if not rest:
        return Quantity(Str(calculator.format(first)))
    spec = text_value(rest[0].value)
    if spec in ("h", "b", "d"):
        text = convert({"h": "▶Hex", "b": "▶Bin", "d": "▶Dec"}[spec], first, calculator.mode)
        return Quantity(Str(calculator.format(text)))
    # Accept calculator precision codes such as F2, E3 and G6, plus Python numeric specs.
    if spec[:1] in ("F", "E", "G") and spec[1:].isdigit():
        spec = "." + spec[1:] + spec[0].lower()
    value = scalar(value)
    if not value.is_number or value.is_real is not True:
        raise CalcError("A numeric format requires a real number.")
    digits = max(calculator.precision, 20, *(int(item) + 5 for item in re.findall(r"\.([0-9]+)", spec)))
    decimal = Decimal(str(sp.N(value, digits)))
    return Quantity(Str(format(decimal, spec)))


def base_function(name, values):
    value, *rest = values
    number = integer(value)
    if name == "isPrime":
        return sp.true if sp.isprime(number) else sp.false
    bits = integer(rest[0], "Bit count") if rest else -1
    mask = (1 << 32) - 1
    number &= mask
    signed = lambda number: number - (1 << 32) if number & (1 << 31) else number
    if name == "rotate":
        bits %= 32
        number = ((number << bits) | (number >> (32 - bits))) & mask
    elif bits < 0:
        number = (signed(number) >> min(-bits, 32)) & mask
    else:
        number = (number << min(bits, 32)) & mask
    return sp.Integer(signed(number))


def extended_function(calculator, name, args):
    if name in STRING_ARITIES:
        return string_function(name, args, calculator).checked()
    if any(arg.dims != ZERO for arg in args):
        raise CalcError(f"{name} requires dimensionless arguments.")
    values = [arg.value for arg in args]
    if name in DIRECT:
        result = map_values(lambda value: DIRECT[name](scalar(value)), *values)
    elif name in NUMBER_ARITIES:
        result = map_values(lambda *items: numeric(name, items), *values)
    elif name in LIST_ARITIES:
        result = list_function(name, values)
    elif name in MATRIX_ARITIES:
        if name in ("mRow", "mRowAdd"):
            result = row_operation(name, values[1], values[2:], scalar(values[0]))
        else:
            result = matrix_function(name, values, calculator.random)
    elif name in ANGLE_ARITIES:
        result = angle_function(name, values, calculator.mode)
    elif name in ALGEBRA_ARITIES:
        result = algebra(name, values, calculator.precision)
    elif name in CALCULUS_ARITIES:
        result = calculus(name, values, calculator.precision)
    else:
        result = base_function(name, values)
    return Quantity(result).checked()
