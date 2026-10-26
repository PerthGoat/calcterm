"""Configuration, numbered backups, history, and saved Problem lifecycle."""

from __future__ import annotations

from collections import deque
import json

from .core import CalcError
from .engine import Calculator, EQUATION_NAMES, HistoryEntry
from .menus import (categorize_unit_items, command_item, default_menus,
                    output_options, problem_menu, validate_menus)


class SessionStorage:
    """Persistence methods for ConsoleApp and its live session state."""

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
        config_saved = True
        if self._config_dirty:
            try:
                self.save_config(announce=False)
            except CalcError as exc:
                self.message = "Error: " + str(exc)
                config_saved = False
        history_saved = self.save_history()
        if self.forth.pending is not None:
            self.message = "Error: Unfinished Forth definition; expected ';'."
            return False
        return config_saved and history_saved

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
            syntax_colors = data.get("syntax_colors", True)
            if not isinstance(syntax_colors, bool):
                raise CalcError("syntax_colors must be true or false.")
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
            if not any(item.get("command") == ":colors toggle" for item in menus[4]["items"]):
                menus[4]["items"].append(command_item("Syntax colors: On", ":colors toggle"))
            if not any(item.get("command") == ":backupconfig" for item in menus[4]["items"]):
                menus[4]["items"].append(command_item("Create backup config", ":backupconfig"))
            # Older settings included the built-in history action under Options.
            menus[4]["items"] = [item for item in menus[4]["items"] if item.get("command") != ":clear"]
            if not any(item.get("command") == ":catalog" for item in menus[5]["items"]):
                menus[5]["items"].append(command_item("Catalog", ":catalog"))
            if not any(item.get("command") == ":words" for item in menus[5]["items"]):
                menus[5]["items"].append(command_item("Forth words", ":words"))
            self.forth.load_definitions(data.get("forth_words", {}))
            self.calculator = calculator
            self.history_insert = recall
            self.menus = menus
            self.syntax_colors = syntax_colors
            self.refresh_color_option()
            self.table_start, self.table_step = start, step
        except (OSError, ValueError, TypeError) as exc:
            # Invalid files never partially replace the live state.
            self.message = f"Config error: {exc} (using defaults; original file preserved)"

    def save_config(self, announce=True):
        # Write beside the destination and replace it only after serialization succeeds.
        # General settings stay separate from the automatically saved Problems file.
        data = {"mode": self.calculator.mode, "precision": self.calculator.precision,
                "output_mode": self.calculator.output_mode,
                "syntax_colors": self.syntax_colors,
                "history_insert": self.history_insert, "units": self.calculator.unit_definitions,
                "equations": self.calculator.equations,
                "unchecked_equations": sorted(self.calculator.unchecked_equations,
                                              key=EQUATION_NAMES.index),
                "table": {"start": self.table_start, "step": self.table_step},
                "menus": self.menus, "forth_words": self.forth.definitions}
        temporary = self.config_path.with_name(self.config_path.name + ".tmp")
        try:
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.config_path)
        except OSError as exc:
            raise CalcError(f"Cannot save configuration: {exc}") from None
        self._config_dirty = False
        if announce:
            self.message = "Saved configuration to " + str(self.config_path)
        self.save_problems()

    def backup_config(self):
        if self._config_dirty or not self.config_path.exists():
            self.save_config(announce=False)
        try:
            contents = self.config_path.read_bytes()
            number = 1
            while True:
                backup = self.config_path.with_name(
                    f"{self.config_path.stem}.backup{number}{self.config_path.suffix}")
                try:
                    # Exclusive creation also protects backups made by another instance.
                    with backup.open("xb") as destination:
                        destination.write(contents)
                    break
                except FileExistsError:
                    number += 1
        except OSError as exc:
            raise CalcError(f"Cannot back up configuration: {exc}") from None
        self.message = "Backed up configuration to " + str(backup)
