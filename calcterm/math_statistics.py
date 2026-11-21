"""List statistics, regression models, and stateful Math menu commands."""

from dataclasses import dataclass

from mpmath import mp

from .core import CalcError, Quantity, ZERO, expression_text, is_scalar, sp
from .math_functions import integer, matrix, scalar, sequence, submatrix, symbol, tolerance_test


STAT_FUNCTIONS = {"mean": (1, 2), "variance": (1, 2), "stdDev": (1, 2), "stDevPop": (1, 2), "median": (1, 2),
                  "rand": (0, 1), "randNorm": (2,), "randPoly": (2,)}
REGRESSIONS = {"LinReg", "ExpReg", "QuadReg", "PowerReg", "LnReg", "MedMed", "CubicReg", "QuartReg",
               "SinReg", "Logistic"}
COMMANDS = {"SortA", "SortD", "LU", "QR", "Fill", "Data▶Mat", "Mat▶Data", "OneVar", "TwoVar", "ShowStat",
            "RandSeed"} | REGRESSIONS


@dataclass(frozen=True)
class CommandResult:
    value: Quantity
    variables: dict
    statistics: dict | None = None


def numeric_list(value):
    data = sequence(value)
    if not all(is_scalar(item) and item.is_real is True and item.is_number for item in data):
        raise CalcError("Expected a list of real numbers.")
    return data


def weighted_rows(values, size):
    columns = [numeric_list(value) for value in values[:size]]
    length = len(columns[0])
    frequencies = numeric_list(values[size]) if len(values) > size else [sp.S.One] * length
    if len(frequencies) != length or any(len(column) != length for column in columns):
        raise CalcError("Data and frequency list lengths must match.")
    if any(weight < 0 for weight in frequencies):
        raise CalcError("Frequencies must be nonnegative.")
    categories = sequence(values[size + 1]) if len(values) > size + 1 else [None] * length
    if len(categories) != length:
        raise CalcError("Data and category list lengths must match.")
    included = sequence(values[size + 2]) if len(values) > size + 2 else categories
    rows = [(*row, weight) for *row, weight, category in zip(*columns, frequencies, categories)
            if weight > 0 and category in included]
    if not rows:
        raise CalcError("At least one observation must have a positive frequency.")
    return rows


def weighted_mean(rows):
    return sum(value * weight for value, weight in rows) / sum(weight for _, weight in rows)


def weighted_median(rows):
    rows = sorted(rows)
    half = sum(weight for _, weight in rows) / 2
    cumulative = 0
    for index, (value, weight) in enumerate(rows):
        cumulative += weight
        if cumulative > half:
            return value
        if cumulative == half:
            return (value + rows[index + 1][0]) / 2


def stat_function(name, args, calculator):
    if any(arg.dims != ZERO for arg in args):
        raise CalcError(f"{name} requires dimensionless arguments.")
    values = [arg.value for arg in args]
    rng = calculator.random
    if name == "rand":
        if values:
            bound = integer(values[0], "Bound")
            if not bound:
                raise CalcError("Random integer bound must be nonzero.")
            result = sp.Integer(rng.randint(1, bound) if bound > 0 else rng.randint(bound, -1))
        else:
            result = sp.Float(rng.random())
    elif name == "randNorm":
        mean, deviation = map(scalar, values)
        if deviation.is_positive is not True:
            raise CalcError("Standard deviation must be positive.")
        result = sp.Float(rng.gauss(float(mean), float(deviation)))
    elif name == "randPoly":
        variable, degree = symbol(values[0]), integer(values[1], "Degree", 0)
        leading = rng.choice(tuple(range(-9, 0)) + tuple(range(1, 10)))
        result = leading * variable ** degree + sum(rng.randint(-9, 9) * variable ** i for i in range(degree))
    else:
        rows = weighted_rows(values, 1)
        mean = weighted_mean(rows)
        if name == "median":
            result = weighted_median(rows)
        elif name == "mean":
            result = mean
        else:
            divisor = sum(weight for _, weight in rows) - (name != "stDevPop")
            if divisor <= 0:
                raise CalcError("Sample variance requires a total frequency greater than one.")
            variance = sum(weight * (value - mean) ** 2 for value, weight in rows) / divisor
            result = variance if name == "variance" else sp.sqrt(variance)
    return Quantity(result).checked()


def summary(rows, axis):
    count = sum(weight for _, weight in rows)
    mean = weighted_mean(rows)
    variance = sum(weight * (value - mean) ** 2 for value, weight in rows)
    return {"n": count, f"mean{axis}": mean, f"sum{axis}": sum(value * weight for value, weight in rows),
            f"sum{axis}2": sum(value ** 2 * weight for value, weight in rows),
            f"min{axis}": min(value for value, _ in rows), f"max{axis}": max(value for value, _ in rows),
            f"median{axis}": weighted_median(rows), f"popDev{axis}": sp.sqrt(variance / count),
            **({f"sampleDev{axis}": sp.sqrt(variance / (count - 1))} if count > 1 else {})}


def polynomial_fit(rows, order):
    design = sp.Matrix([[x ** power * sp.sqrt(w) for power in range(order, -1, -1)] for x, _, w in rows])
    if len(rows) <= order or design.rank() <= order:
        raise CalcError("The data do not uniquely determine regression coefficients.")
    response = sp.Matrix([y * sp.sqrt(w) for _, y, w in rows])
    return list(design.solve_least_squares(response))


def nonlinear_fit(name, rows, precision):
    # Levenberg–Marquardt with a few data-derived starting points. Work in a
    # rescaled x coordinate to keep the least-squares system well conditioned.
    with mp.workdps(max(precision, 20)):
        points = sorted(tuple(mp.mpf(str(sp.N(v, mp.dps))) for v in row) for row in rows)
        xmin, xmax = points[0][0], points[-1][0]
        width = xmax - xmin
        if not width:
            raise CalcError("Regression requires distinct x values.")
        points = [((x - xmin) / width, y, mp.sqrt(w)) for x, y, w in points]
        ymin, ymax = min(y for _, y, _ in points), max(y for _, y, _ in points)
        if name == "SinReg":
            def model(x, a, b, c, d):
                s, k = mp.sin(b*x + c), mp.cos(b*x + c)
                return a*s + d, (s, a*x*k, a*k, 1)

            starts = [((ymax-ymin)/2, periods*2*mp.pi, phase, (ymax+ymin)/2)
                      for periods in (0.5, 1, 2, 3) for phase in (0, mp.pi/2)]
        else:
            def model(x, a, b, c):
                f = 1 / (1 + mp.exp(b - c*x))
                return a*f, (f, -a*f*(1-f), a*x*f*(1-f))

            starts = [(2*ymax, steepness/2, steepness) for steepness in (-8, -2, 2, 8)]

        def residuals(params):
            fitted = [model(x, *params) for x, _, _ in points]
            residual = mp.matrix([(y - fit) * w for (_, y, w), (fit, _) in zip(points, fitted)])
            jacobian = mp.matrix([[derivative*w for derivative in gradient]
                                  for (_, _, w), (_, gradient) in zip(points, fitted)])
            return residual, jacobian, mp.fdot(residual, residual)

        best = None
        for start in starts:
            params = mp.matrix(start)
            residual, jacobian, error = residuals(params)
            damping = mp.mpf("0.01")
            for _ in range(100):
                transpose = jacobian.T
                step = mp.lu_solve(transpose*jacobian + damping*mp.eye(len(params)), transpose*residual)
                next_residual, next_jacobian, next_error = residuals(params + step)
                if next_error < error:
                    params += step
                    residual, jacobian, error = next_residual, next_jacobian, next_error
                    damping = max(damping/3, mp.eps)
                    if mp.norm(step) <= mp.sqrt(mp.eps) * max(1, mp.norm(params)):
                        break
                else:
                    damping *= 4
                    if damping > 1/mp.eps:
                        break
            if best is None or error < best[0]:
                best = error, params
        if name == "SinReg":
            a, b, c, d = best[1]
            coefficients = (a, b/width, c - b*xmin/width, d)
        else:
            a, b, c = best[1]
            coefficients = (a, mp.exp(b + c*xmin/width), c/width)
        return [sp.Float(str(value), precision) for value in coefficients]


def regress(name, rows, precision):
    x = sp.Symbol("x")
    orders = {"LinReg": 1, "QuadReg": 2, "CubicReg": 3, "QuartReg": 4}
    if name in orders:
        coefficients = polynomial_fit(rows, orders[name])
        model = sum(value * x ** power for power, value in enumerate(reversed(coefficients)))
    elif name in ("ExpReg", "PowerReg", "LnReg"):
        log_x, log_y = name != "ExpReg", name != "LnReg"
        if any((log_x and x <= 0) or (log_y and y <= 0) for x, y, _ in rows):
            raise CalcError("Logarithmic regression inputs must be positive.")
        transformed = [(sp.log(x).evalf(precision) if log_x else x, sp.log(y).evalf(precision) if log_y else y, w)
                       for x, y, w in rows]
        mean_x = weighted_mean([(x, w) for x, _, w in transformed])
        mean_y = weighted_mean([(y, w) for _, y, w in transformed])
        variance = sum(w * (x - mean_x) ** 2 for x, _, w in transformed)
        if variance.is_zero:
            raise CalcError("Regression requires distinct x values.")
        slope = sum(w * (x - mean_x) * (y - mean_y) for x, y, w in transformed) / variance
        intercept = mean_y - slope * mean_x
        if name == "ExpReg":
            coefficients = [sp.exp(intercept), sp.exp(slope)]
            model = coefficients[0] * coefficients[1] ** x
        elif name == "PowerReg":
            coefficients = [sp.exp(intercept), slope]
            model = coefficients[0] * x ** slope
        else:
            coefficients = [intercept, slope]
            model = intercept + slope * sp.log(x)
    elif name == "MedMed":
        rows = sorted(rows)
        size, remainder = divmod(len(rows), 3)
        if not size:
            raise CalcError("Median-median regression requires three or more observations.")
        edge = size + (remainder == 2)
        groups = (rows[:edge], rows[edge:-edge], rows[-edge:])
        points = [(weighted_median([(x, w) for x, _, w in group]),
                   weighted_median([(y, w) for _, y, w in group])) for group in groups]
        if points[0][0] == points[-1][0]:
            raise CalcError("Median-median regression requires distinct median x values.")
        slope = (points[-1][1] - points[0][1]) / (points[-1][0] - points[0][0])
        intercept = sum(y - slope*x for x, y in points) / 3
        coefficients, model = [slope, intercept], slope*x + intercept
    else:
        if len(rows) < (4 if name == "SinReg" else 3):
            raise CalcError("The data do not uniquely determine regression coefficients.")
        coefficients = nonlinear_fit(name, rows, precision)
        if name == "SinReg":
            a, b, c, d = coefficients
            model = a*sp.sin(b*x + c) + d
        else:
            a, b, c = coefficients
            model = a/(1 + b*sp.exp(-c*x))
    return {**dict(zip("abcde", coefficients)), "regEq": model}


def math_command(calculator, name, args):
    def count(minimum, maximum=None):
        if not minimum <= len(args) <= (minimum if maximum is None else maximum):
            raise CalcError(f"Wrong number of arguments for {name}.")

    def arg(index):
        value = calculator.parse(args[index])
        if value.dims != ZERO:
            raise CalcError(f"{name} requires dimensionless arguments.")
        return value.value

    def variable(index):
        return calculator.variable_name(args[index].strip())

    def stored(index):
        key = variable(index)
        if key not in calculator.variables:
            raise CalcError(f"Variable {key} has not been assigned.")
        return key, calculator.variables[key].value

    updates = {}
    statistics = None
    if name == "RandSeed":
        count(1)
        seed = integer(arg(0), "Seed")
        calculator.random.seed(seed)
        result = sp.Integer(seed)
    elif name in ("SortA", "SortD"):
        count(1, len(args))
        variables, columns = zip(*(stored(index) for index in range(len(args))))
        columns = [sequence(column) for column in columns]
        if any(len(column) != len(columns[0]) for column in columns):
            raise CalcError("Companion lists must have the same length.")
        if not all(is_scalar(item) and item.is_number and item.is_real is True for item in columns[0]):
            raise CalcError("The first sort list must contain real numbers.")
        order = sorted(range(len(columns[0])), key=columns[0].__getitem__, reverse=name == "SortD")
        updates = {key: sp.Tuple(*(column[index] for index in order)) for key, column in zip(variables, columns)}
        result = updates[variables[0]]
    elif name in ("LU", "QR"):
        outputs = 3 if name == "LU" else 2
        count(outputs + 1, outputs + 2)
        value = matrix(arg(0))
        keys = [variable(index) for index in range(1, outputs + 1)]
        if len(set(keys)) != outputs:
            raise CalcError("Output variables must be distinct.")
        tolerance = arg(outputs + 1) if len(args) == outputs + 2 else None
        zero = tolerance_test(tolerance)
        if name == "LU":
            lower, upper, swaps = value.LUdecomposition(iszerofunc=zero)
            parts = (lower, upper, sp.ImmutableMatrix.eye(value.rows).permuteFwd(swaps))
        else:
            if tolerance is not None:
                value = value.applyfunc(lambda item: sp.S.Zero if zero(item) else item)
            parts = value.QRdecomposition()
        updates = dict(zip(keys, parts))
        result = parts[0]
    elif name == "Fill":
        count(2)
        fill = scalar(arg(0))
        key, existing = stored(1)
        result = (existing.applyfunc(lambda _: fill) if isinstance(existing, sp.MatrixBase)
                  else sp.Tuple(*([fill] * len(sequence(existing)))))
        updates[key] = result
    elif name in ("Data▶Mat", "Mat▶Data"):
        count(2, 6)
        value = arg(0)
        if name == "Data▶Mat" and isinstance(value, sp.Tuple):
            value = sp.ImmutableMatrix(list(value))
        result = submatrix(matrix(value), *(arg(index) for index in range(2, len(args))))
        updates[variable(1)] = result
    else:
        if name == "ShowStat":
            count(0)
            if not calculator.statistics:
                raise CalcError("Run a statistics or regression command first.")
            statistics = calculator.statistics
        else:
            columns = 1 if name == "OneVar" else 2
            count(columns, columns + 3)
            rows = weighted_rows([arg(index) for index in range(len(args))], columns)
            statistics = summary([(row[0], row[-1]) for row in rows], "X")
            if columns == 2:
                statistics.update(summary([(y, w) for _, y, w in rows], "Y"))
                statistics["sumXY"] = sum(x*y*w for x, y, w in rows)
            if name in REGRESSIONS:
                statistics.update(regress(name, rows, calculator.precision))
            updates = {"stat" + key[0].upper() + key[1:]: value for key, value in statistics.items()}
        display = ", ".join(f"{key} = {expression_text(value, full_prec=False)}" for key, value in statistics.items())
        return CommandResult(Quantity(sp.Tuple(*statistics.values()), presentation=display),
                             {key: Quantity(value).checked() for key, value in updates.items()}, statistics)
    return CommandResult(Quantity(result).checked(), {key: Quantity(value).checked() for key, value in updates.items()})
