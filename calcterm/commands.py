"""Application Forth words and the existing colon-command syntax adapter."""

from __future__ import annotations

import json

from .core import CalcError
from .forth import ForthInterpreter
from .menus import categorize_unit_items, command_item, insert_item


class CommandProcessor:
    def __init__(self, app):
        self.app = app
        self.vm = ForthInterpreter(on_define=self._defined, on_undefine=self._undefined)
        self.adapters = {}
        self._install_words()

    def _saved(self):
        self.app._config_dirty = True
        self.app.save_config(announce=False)

    def _defined(self, name):
        self._activity = True
        self.app.message = "Defined Forth word: " + name
        self._saved()

    def _undefined(self, name):
        self._activity = True
        self.app.message = "Undefined Forth word: " + name
        self._saved()

    def _register(self, name, action, adapter=None, saves=False):
        def run(vm):
            self._activity = True
            action(vm)
            if saves:
                self._saved()
        self.vm.register(name, run)
        self.adapters[name] = adapter or (lambda arg: [])

    @staticmethod
    def _number(arg):
        try:
            return int(arg)
        except ValueError:
            raise CalcError("Precision must be an integer of at least 2.") from None

    @staticmethod
    def _menu_args(arg):
        number, _, rest = arg.partition(" ")
        if number not in {"1", "2", "3", "4", "5", "6"}:
            raise CalcError("Menu number must be 1 through 6.")
        return int(number), rest.strip()

    def _unit_args(self, arg):
        name, separator, expression = arg.partition("=")
        if not separator:
            raise CalcError("Use :unit name = expression, for example :unit smoot = 1.7018_m.")
        return [name.strip().removeprefix("_"), expression.strip()]

    def _menuadd_args(self, arg):
        number, rest = self._menu_args(arg)
        label, separator, action = rest.partition("|")
        if not separator or not label.strip():
            raise CalcError("Use :menuadd NUMBER LABEL | TEXT (or a :command).")
        return [number, label.strip(), action.strip()]

    @staticmethod
    def _problem_args(arg):
        action, _, name = arg.partition(" ")
        return [action, name]

    def _install_words(self):
        app = self.app
        self._register("mode", self._mode, lambda arg: [arg], saves=True)
        self._register("format", self._format, lambda arg: [arg], saves=True)
        self._register("precision", self._precision, lambda arg: [self._number(arg)], saves=True)
        self._register("colors", self._colors, lambda arg: [arg or "toggle"], saves=True)
        self._register("recall", self._recall, lambda arg: [arg], saves=True)
        self._register("unit", self._unit, self._unit_args, saves=True)
        self._register("menu", self._menu, lambda arg: list(self._menu_args(arg)), saves=True)
        self._register("menuadd", self._menuadd, self._menuadd_args, saves=True)
        self._register("menuclear", self._menuclear, lambda arg: [self._menu_args(arg)[0]], saves=True)
        self._register("problem", self._problem, self._problem_args)
        self._register("unset", self._unset, lambda arg: [arg])
        self._register("vars", self._variables)
        self._register("clearvars", self._clearvars)
        self._register("clear", self._clear)
        self._register("resetconfig", lambda vm: app.reset_config(), saves=True)
        self._register("save", lambda vm: app.save_config())
        self._register("backupconfig", lambda vm: app.backup_config())
        self._register("quit", lambda vm: setattr(app, "running", False))
        self._register("help", lambda vm: setattr(app, "help_open", True))
        self._register("catalog", lambda vm: app.open_catalog())
        self.vm.register("calc", self._calc)
        self.vm.register("insert", lambda vm: app.insert(vm.string()))
        self.adapters["def"] = lambda arg: [arg]
        self.adapters["undefine"] = lambda arg: [arg]

    def _mode(self, vm):
        self.app.calculator.set_mode(vm.string())
        self.app.message = "Angle mode: " + self.app.calculator.mode

    def _format(self, vm):
        self.app.calculator.set_output_mode(vm.string())
        self.app.message = "Output mode: " + self.app.calculator.output_mode

    def _precision(self, vm):
        self.app.calculator.set_precision(vm.integer())
        self.app.message = (f"Approximation precision: {self.app.calculator.precision} digits; "
                            "exact math is unchanged.")

    def _colors(self, vm):
        arg = vm.string()
        if arg not in ("on", "off", "toggle"):
            raise CalcError("Use :colors on, :colors off, or :colors toggle.")
        self.app.syntax_colors = {"on": True, "off": False, "toggle": not self.app.syntax_colors}[arg]
        self.app.refresh_color_option()
        self.app.message = "Syntax colors: " + ("On" if self.app.syntax_colors else "Off")

    def _recall(self, vm):
        arg = vm.string()
        if arg not in ("result", "expression"):
            raise CalcError("Use :recall result or :recall expression.")
        self.app.history_insert = arg
        self.app.message = "History browsing starts with the " + arg + "; Up/Down selects either part."

    def _unit(self, vm):
        expression, name = vm.string(), vm.string()
        name = name.removeprefix("_")
        self.app.calculator.define_unit(name, expression)
        unit = self.app.calculator.registry.get(name)
        self.app.menus[1]["items"] = categorize_unit_items(self.app.calculator.registry,
            self.app.menus[1]["items"] + [insert_item(unit.notation + " " + unit.label, unit.notation)])
        self.app.message = "Added " + unit.notation

    def _menu_target(self, vm):
        number = vm.integer()
        if number not in range(1, 7):
            raise CalcError("Menu number must be 1 through 6.")
        self.app.message = f"Updated F{number} menu."
        return self.app.menus[number - 1]

    def _menu(self, vm):
        label = vm.string()
        if not label.strip():
            raise CalcError("Use :menu NUMBER LABEL.")
        self._menu_target(vm)["label"] = label.strip()

    def _menuadd(self, vm):
        action, label = vm.string(), vm.string()
        if not label.strip():
            raise CalcError("Menu items need a nonempty label.")
        action = action.strip()
        self._menu_target(vm)["items"].append(
            command_item(label.strip(), action) if action.startswith(":") else insert_item(label.strip(), action))

    def _menuclear(self, vm):
        self._menu_target(vm)["items"] = []

    def _problem(self, vm):
        name, action = vm.string(), vm.string()
        if action not in ("new", "open", "delete"):
            raise CalcError("Use :problem new/open/delete [NAME].")
        if name and action in ("new", "open"):
            (self.app.new_problem if action == "new" else self.app.open_problem)(name)
        else:
            self.app.begin_problem_dialog(action, name)

    def _unset(self, vm):
        name = vm.string()
        if name not in self.app.calculator.variables:
            raise CalcError("No assigned variable named " + name)
        del self.app.calculator.variables[name]
        self.app.message = name + " is symbolic again."

    def _variables(self, vm):
        calculator = self.app.calculator
        self.app.message = "; ".join(f"{key} = {calculator.format(value)}"
                                     for key, value in calculator.variables.items()) or "No assigned variables."

    def _clearvars(self, vm):
        self.app.calculator.variables.clear()
        self.app.message = "Set variables cleared."

    def _clear(self, vm):
        self.app.calculator.history.clear()
        self.app.history_index = None
        self.app.message = "History cleared."
        self.app.save_history(force=True)

    def _calc(self, vm):
        result = self.app.calculator.calculate(vm.string())
        self.app.save_history()
        vm.push(result)

    def execute(self, text):
        self._activity = False
        self.vm.output = []
        if text.strip().lower() == ":abort":
            self.vm.pending = None
            self.app.message = "Forth definition canceled."
            return
        if self.vm.pending is not None:
            source = text
        else:
            parts = text.strip().split(None, 1)
            if not parts:
                raise CalcError("Use :forth PROGRAM or :name.")
            first, arg = parts[0], parts[1].strip() if len(parts) > 1 else ""
            name = first.removeprefix(":").lower()
            if first == ":":
                source = text
            elif name == "forth":
                source = arg
            elif name in self.adapters:
                arguments = self.adapters[name](arg)
                source = " ".join([*(json.dumps(value, ensure_ascii=False) for value in arguments), name])
            else:
                source = arg + " " + name
        output = self.vm.execute(source)
        if self.vm.pending is not None:
            self.app.message = f"Compiling Forth word {self.vm.pending[0]}; finish with ; (:abort cancels)."
        elif output:
            self.app.message = output.rstrip()
        elif not self._activity:
            self.app.message = "Forth stack: " + self.vm.stack_text()
