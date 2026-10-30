"""Validated graph windows and sampled, terminal-cell equation plots."""

from dataclasses import dataclass
import math
import sys

from .core import CalcError, Quantity, ZERO, expression_text, sp


DEFAULT_GRAPH = {"x_min": "-10", "x_max": "10", "y_mode": "auto", "y_min": "-10", "y_max": "10"}
GRAPH_MARKERS = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@#%&*o"
GRAPH_COLORS = ("91", "92", "94", "95", "96", "93", "97")


def graph_number(calculator, source, label):
    if not isinstance(source, str):
        raise CalcError(f"Graph {label} must be a numeric expression.")
    value = calculator.parse(source)
    if (not isinstance(value.value, sp.Expr) or value.dims != ZERO
            or value.value.is_number is not True or value.value.is_real is not True):
        raise CalcError(f"Graph {label} must be a finite real number without units.")
    try:
        number = float(value.value)
    except (TypeError, ValueError, OverflowError):
        number = math.inf
    if not math.isfinite(number):
        raise CalcError(f"Graph {label} must fit a finite numeric range.")
    return expression_text(value.value), number


def validate_graph_settings(calculator, data):
    if not isinstance(data, dict):
        raise CalcError("Graph settings must be an object.")
    settings = {key: data.get(key, default) for key, default in DEFAULT_GRAPH.items()}
    if settings["y_mode"] not in ("auto", "manual"):
        raise CalcError("Graph y_mode must be auto or manual.")
    numbers = {}
    for key in ("x_min", "x_max", "y_min", "y_max"):
        settings[key], numbers[key] = graph_number(calculator, settings[key], key.replace("_", " "))
    for axis in ("x", "y"):
        lower, upper = numbers[axis + "_min"], numbers[axis + "_max"]
        if lower >= upper or not math.isfinite(upper - lower):
            raise CalcError(f"Graph {axis} lower bound must be less than its upper bound, with a finite span.")
    return settings


@dataclass
class GraphPlot:
    cells: list[list[str]]
    colors: dict[tuple[int, int], int]
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    invalid: list[str]


class GraphView:
    def __init__(self):
        self.settings = dict(DEFAULT_GRAPH)
        self.edit_field = None
        self.fields = []
        self.cursor = 0
        self.legend_offset = 0
        self._sample_cache = None
        self._plot_cache = None

    def begin_edit(self):
        self.fields = [self.settings[key] for key in DEFAULT_GRAPH]
        self.edit_field, self.cursor = 0, len(self.fields[0])

    def edit(self, key, overwrite=False):
        field = self.edit_field
        text, position = self.fields[field], self.cursor
        if key == "ESC":
            self.edit_field = None
        elif key in ("TAB", "UP", "DOWN"):
            enabled = [0, 1, 2] if self.fields[2] == "auto" else [0, 1, 2, 3, 4]
            self.edit_field = enabled[(enabled.index(field) + (-1 if key == "UP" else 1)) % len(enabled)]
            self.cursor = len(self.fields[self.edit_field])
        elif field == 2:
            if key in (" ", "LEFT", "RIGHT"):
                self.fields[2] = "manual" if text == "auto" else "auto"
            elif key.lower() in ("a", "m"):
                self.fields[2] = "auto" if key.lower() == "a" else "manual"
            self.cursor = len(self.fields[2])
        elif key == "LEFT":
            self.cursor = max(0, position - 1)
        elif key == "RIGHT":
            self.cursor = min(len(text), position + 1)
        elif key == "HOME":
            self.cursor = 0
        elif key == "END":
            self.cursor = len(text)
        elif key == "CTRL_U":
            self.fields[field], self.cursor = "", 0
        elif key == "BACKSPACE" and position:
            self.fields[field] = text[:position - 1] + text[position:]
            self.cursor -= 1
        elif key == "DELETE":
            self.fields[field] = text[:position] + text[position + 1:]
        elif len(key) == 1 and key.isprintable():
            end = position + 1 if overwrite else position
            self.fields[field] = text[:position] + key + text[end:]
            self.cursor += 1

    def apply(self, calculator):
        draft = dict(zip(DEFAULT_GRAPH, self.fields))
        if draft["y_mode"] == "auto":
            # Disabled manual fields keep their last valid values.
            draft.update({key: self.settings[key] for key in ("y_min", "y_max")})
        self.settings = validate_graph_settings(calculator, draft)
        self.edit_field = None

    @staticmethod
    def _value(calculator, name, x):
        try:
            result = calculator.equation(name, [Quantity(sp.Float(x, 17))])
            if result.dims != ZERO or not isinstance(result.value, sp.Expr):
                return None
            value = float(result.value)
            return value if math.isfinite(value) else None
        except (CalcError, TypeError, ValueError, OverflowError, ZeroDivisionError):
            return None

    def _samples(self, calculator, names, columns):
        key = (id(calculator), columns, tuple(self.settings.items()), tuple(names),
               tuple(calculator.equations.items()), tuple(calculator.variables.items()),
               calculator.answer, calculator.mode, calculator.precision, tuple(calculator.unit_definitions.items()))
        if self._sample_cache is not None and self._sample_cache[0] == key:
            return self._sample_cache[1]
        lower = graph_number(calculator, self.settings["x_min"], "x min")[1]
        upper = graph_number(calculator, self.settings["x_max"], "x max")[1]
        xs = [lower * (1 - column / (columns - 1)) + upper * (column / (columns - 1))
              for column in range(columns)]
        curves = [[self._value(calculator, name, x) for x in xs] for name in names]
        samples = xs, curves
        self._sample_cache = key, samples
        return samples

    @staticmethod
    def _auto_bounds(curves):
        values = [value for curve in curves for value in curve if value is not None]
        if not values:
            return -1.0, 1.0
        lower, upper = min(values), max(values)
        scale = max(abs(lower), abs(upper), 1.0)
        padding = scale * (0.1 if lower == upper else (upper / scale - lower / scale) * 0.05)
        return max(-sys.float_info.max, lower - padding), min(sys.float_info.max, upper + padding)

    def plot(self, calculator, names, columns, rows):
        xs, curves = self._samples(calculator, names, columns)
        key = self._sample_cache[0], rows
        if self._plot_cache is not None and self._plot_cache[0] == key:
            return self._plot_cache[1]
        if self.settings["y_mode"] == "auto":
            lower, upper = self._auto_bounds(curves)
        else:
            lower = graph_number(calculator, self.settings["y_min"], "y min")[1]
            upper = graph_number(calculator, self.settings["y_max"], "y max")[1]
        cells = [[" "] * columns for _ in range(rows)]
        colors = {}
        scale = max(abs(lower), abs(upper), 1.0)
        y_span = upper / scale - lower / scale

        def y_position(value):
            return (upper / scale - value / scale) / y_span * (rows - 1)

        if xs[0] <= 0 <= xs[-1]:
            axis = round(-xs[0] / (xs[-1] - xs[0]) * (columns - 1))
            for row in cells:
                row[axis] = "|"
        if lower <= 0 <= upper:
            axis = round(y_position(0))
            cells[axis] = ["+" if char == "|" else "-" for char in cells[axis]]

        owners = {}

        def mark(row, column, curve):
            if 0 <= row < rows:
                owner = owners.get((row, column), curve)
                owners[row, column] = curve if owner == curve else -1
                cells[row][column] = GRAPH_MARKERS[curve % len(GRAPH_MARKERS)] if owner == curve else "*"
                colors[row, column] = curve % len(GRAPH_COLORS) if owner == curve else len(GRAPH_COLORS) - 1

        for index, (name, values) in enumerate(zip(names, curves)):
            for column, value in enumerate(values):
                if value is None:
                    continue
                position = y_position(value)
                if lower <= value <= upper:
                    mark(round(position), column, index)
                if column == 0 or values[column - 1] is None:
                    continue
                previous = y_position(values[column - 1])
                if not math.isfinite(position) or not math.isfinite(previous):
                    continue
                if abs(position - previous) > 2:
                    middle = self._value(calculator, name, xs[column - 1] / 2 + xs[column] / 2)
                    if middle is None:
                        continue
                    midpoint = y_position(middle)
                    if abs(midpoint - (position + previous) / 2) > max(1.0, abs(position - previous) / 4):
                        continue  # Avoid connecting sampled branches across poles/jumps.
                first = max(0, math.ceil(min(position, previous)))
                last = min(rows - 1, math.floor(max(position, previous)))
                for row in range(first, last + 1):
                    mark(row, column, index)
        invalid = [name for name, values in zip(names, curves) if all(value is None for value in values)]
        plot = GraphPlot(cells, colors, xs[0], xs[-1], lower, upper, invalid)
        self._plot_cache = key, plot
        return plot
