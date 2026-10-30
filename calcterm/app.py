"""Console UI state, editing, dialogs, and terminal-cell frame layout."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import re
import unicodedata

from .commands import CommandProcessor
from .core import CalcError, Quantity, ZERO, expression_text, sp
from .engine import Calculator, EQUATION_NAMES, HistoryEntry
from .io import IOTranscript
from .menus import HELP_LINES, catalog_items, cleanup_menu, default_menus, filter_menu_items
from .storage import SessionStorage
from .syntax import expression_highlights


def insert_text_at_cursor(text, cursor, inserted, overwrite=False):
    end = cursor + len(inserted) if overwrite else cursor
    return text[:cursor] + inserted + text[end:], cursor + len(inserted)


class ConsoleApp(SessionStorage):
    """UI state and input handling, independent of the terminal for unit testing."""

    def __init__(self, calculator=None, config_path=None):
        self.calculator = calculator or Calculator()
        self.config_path = (Path(config_path) if config_path else
                            Path(__file__).resolve().parent.parent / "calc_term_config.json")
        self._config_dirty = False
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
        self.syntax_highlights: dict[int, list[tuple[int, int, str]]] = {}
        self.syntax_colors = True
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
        self.io_open = False
        self.io = IOTranscript()
        self.io_focus_input = True
        self.io_width, self.io_rows = 100, 17
        self.table_start = "0"
        self.table_step = "1"
        self.table_row = 0
        self.table_column = 0
        self.table_edit_field: int | None = None
        self.table_fields = ["0", "1"]
        self.table_cursor = 0
        self.shift_pressed = False
        self.insert_mode = False
        self.message = "F7: equations | F8: table | F6: help | Enter: calculate | :quit: exit"
        self.help_open = False
        self.running = True
        self.commands = CommandProcessor(self)
        self.forth = self.commands.vm
        self._load_config()
        self._load_history()
        self._load_problems()

    def reset_config(self):
        # Reset preferences and menus while retaining calculation data and custom units.
        self.calculator.set_mode("radian")
        self.calculator.set_precision(50)
        self.calculator.set_output_mode("exact")
        self.history_insert = "result"
        self.syntax_colors = True
        self.insert_mode = False
        self.forth.load_definitions({})
        self.forth.stack.clear()
        self.menus = default_menus(self.calculator.registry)
        self.open_menu = None
        self.menu_stack.clear()
        self.menu_index, self.menu_filter = 0, ""
        self.message = "Configuration reset to defaults."

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

    def insert(self, text, overwrite=False):
        replaced_selection = self.delete_input_selection()
        self.clear_input_selection()
        self.text, self.cursor = insert_text_at_cursor(self.text, self.cursor, text,
                                                      overwrite=overwrite and not replaced_selection)
        self.history_index = None

    def delete_history_entry(self):
        history = self.calculator.history
        index = self.history_index
        if index is None or not 0 <= index < len(history):
            return
        del history[index]
        self.history_index = min(index, len(history) - 1) if history else None
        if self.history_index is not None and history[self.history_index].is_error:
            self.history_part = "expression"
        self.history_start = min(self.history_start, max(0, len(history) - self.history_rows))
        self.message = "Deleted history entry."
        self.save_history(force=True)

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

    def refresh_color_option(self):
        for item in self.menus[4]["items"]:
            if item.get("command") == ":colors toggle":
                item["label"] = "Syntax colors: " + ("On" if self.syntax_colors else "Off")

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
        self.io.append("> " + text)
        try:
            self.commands.execute(text)
        except (CalcError, OSError) as exc:
            if self.forth.output:
                self.io.append("".join(self.forth.output))
            self.io.append("Error: " + str(exc))
            raise
        self.io.append("".join(self.forth.output) or self.message)

    def is_command_input(self, text):
        return self.forth.pending is not None or text.lstrip().startswith(":")

    def submit(self, approximate=False):
        # Both interactive and plain mode share this command/calculation path.
        if not self.text.strip():
            return
        command_input = self.is_command_input(self.text)
        try:
            if command_input:
                command = self.text.strip()
                self.clear_input()
                try:
                    self.command(command)
                except (CalcError, OSError):
                    self.text, self.cursor = command, len(command)
                    raise
            else:
                self.io.append("> " + self.text)
                self.calculator.evaluate(self.text, approximate=approximate)
                self.message = self.calculator.history[-1].line
                self.io.append(self.calculator.history[-1].result)
                self.save_history()
                self.select_all_input()
            self.history_index = None
        except (CalcError, OSError) as exc:
            # Keep failed input in the editor for correction and persist any error entry.
            self.message = "Error: " + str(exc)
            if not command_input:
                self.io.append(self.message)
            self.history_index = None
            if self.is_command_input(self.text):
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
        if key == "INSERT":
            self.insert_mode = not self.insert_mode
            return
        if self.problem_dialog is not None:
            self.handle_problem_key(key)
            return
        if self.catalog_open:
            self.handle_catalog_key(key)
            return
        if key == "F10":
            if self.equation_open and not self.commit_equation():
                return
            if self.table_edit_field is not None and not self.commit_table_settings():
                return
            self.equation_open = self.table_open = self.help_open = False
            self.open_menu = None
            self.menu_stack.clear()
            self.io_open = not self.io_open
            self.io_focus_input = True
            if self.io_open:
                self.history_index = None
            return
        if key == "F8":
            if self.equation_open and not self.commit_equation():
                return
            if self.table_edit_field is not None and not self.commit_table_settings():
                return
            self.equation_open = False
            self.io_open = False
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
            self.io_open = False
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
            self.io_open = False
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
        if self.io_open and not self.help_open:
            if key == "ESC":
                self.io_open = False
                return
            if key == "TAB":
                self.io_focus_input = not self.io_focus_input
                return
            if key in ("UP", "DOWN", "PAGEUP", "PAGEDOWN") or (
                    not self.io_focus_input and key in ("HOME", "END")):
                self.io.scroll(key, self.io_width, self.io_rows, display_width)
                return
            if key in ("ENTER", "SHIFT_ENTER") and not self.io_focus_input:
                self.io_focus_input = True
                return
            if (len(key) == 1 and key.isprintable()) or key in (
                    "LEFT", "RIGHT", "SHIFT_LEFT", "SHIFT_RIGHT", "BACKSPACE", "DELETE", "CTRL_U"):
                self.io_focus_input = True
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
        if key == "BACKSPACE" and self.history_index is not None:
            self.delete_history_entry()
        elif key in ("UP", "PAGEUP") and history:
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
            self.insert(key, overwrite=self.insert_mode)

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
            self.equation_text, self.equation_cursor = insert_text_at_cursor(
                self.equation_text, position, key, overwrite=self.insert_mode)

    def highlight_expression(self, row, text, column=0, offset=0):
        if not self.syntax_colors:
            return
        spans = self.syntax_highlights.setdefault(row, [])
        for first, last, kind in expression_highlights(text):
            if last > offset:
                spans.append((column + max(first, offset) - offset, column + last - offset, kind))

    def mask_syntax_highlights(self, row, first, last):
        spans = []
        for begin, end, kind in self.syntax_highlights.get(row, []):
            if begin < first:
                spans.append((begin, min(end, first), kind))
            if end > last:
                spans.append((max(begin, last), end, kind))
        self.syntax_highlights[row] = spans

    def status_with_indicators(self, text, width):
        indicator = "↑" if self.shift_pressed else " "
        insertion = "INS" if self.insert_mode else "   "
        return clip(f" {self.problem_name} | {indicator} | {insertion} | {text.lstrip()}", width)

    def overwrite_span(self, text, position, column=0, offset=0) -> tuple[int, int] | None:
        if self.insert_mode and 0 <= position < len(text):
            first = column + position - offset
            return first, first + 1
        return None

    def edit_window_start(self, text, position, available):
        focus = position + (1 if self.insert_mode and position < len(text) else 0)
        start = max(0, focus - available + 1)
        while display_width(text[start:focus]) >= available:
            start += 1
        return start

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
            self.highlight_expression(len(lines), f"{name}=" + expression, column=6)
            if active:
                selected[len(lines)] = (0, len(line))
            lines.append(line)
        prefix = f"{EQUATION_NAMES[self.equation_index]}(x)="
        available = width - display_width(prefix) - 1
        start = self.edit_window_start(self.equation_text, self.equation_cursor, available)
        lines += ["-" * width, prefix + self.equation_text[start:], "-" * width]
        self.highlight_expression(len(lines) - 2, prefix)
        self.highlight_expression(len(lines) - 2, self.equation_text, column=len(prefix), offset=start)
        cursor = (height - 3, display_width(prefix + self.equation_text[start:self.equation_cursor]) + 1)
        preview = self.overwrite_span(self.equation_text, self.equation_cursor, column=len(prefix), offset=start)
        if preview is not None:
            selected[len(lines) - 2] = preview
            cursor = None
        lines += [f" Equation {self.equation_index + 1}/99 | Ctrl+T: check/uncheck | F8: table",
                  self.message]
        lines[-2] = self.status_with_indicators(lines[-2], width)
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
            self.table_fields[field], self.table_cursor = insert_text_at_cursor(
                text, position, key, overwrite=self.insert_mode)

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
            content = row(cells)
            for cell in re.finditer(r"[^|]+", content):
                self.highlight_expression(len(lines), cell.group(), column=cell.start())
            lines.append(content)
        lines.append("-" * width)
        cursor = None
        selected = {}
        field = self.table_edit_field
        if field is not None:
            prefix = ("Start", "Step")[field] + "="
            text = self.table_fields[field]
            available = width - len(prefix) - 1
            first = self.edit_window_start(text, self.table_cursor, available)
            lines.append(prefix + text[first:])
            self.highlight_expression(len(lines) - 1, text, column=len(prefix), offset=first)
            cursor = (height - 3, len(prefix) + display_width(text[first:self.table_cursor]) + 1)
            preview = self.overwrite_span(text, self.table_cursor, column=len(prefix), offset=first)
            if preview is not None:
                selected[len(lines) - 1] = preview
                cursor = None
        else:
            lines.append("Tab: start/step | F7: equations | F8: close")
        first_column = self.table_column + 1 if names else 0
        lines += ["-" * width,
                  f" Row {self.table_row} | equations {first_column}-{self.table_column + len(visible)}/{len(names)} | arrows: scroll | Home: reset",
                  self.message]
        lines[-2] = self.status_with_indicators(lines[-2], width)
        return [clip(line, width) for line in lines], selected, cursor

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
            self.mask_syntax_highlights(index, left, left + box_width)
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
            self.problem_dialog_text, self.problem_dialog_cursor = insert_text_at_cursor(
                text, position, key, overwrite=self.insert_mode)

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
                start = self.edit_window_start(self.problem_dialog_text, self.problem_dialog_cursor, inside)
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
                preview = self.overwrite_span(self.problem_dialog_text, self.problem_dialog_cursor,
                                              column=left + 2, offset=start)
                if preview is not None:
                    selected[top + 3] = preview
                    cursor = None
            else:
                begin = left + 2 + (9 if self.problem_delete_confirm else 0)
                selected[top + 4] = (begin, begin + 6)
        for row, content in enumerate(panel, top):
            background = lines[row].ljust(width)
            lines[row] = background[:left] + content + background[left + display_width(content):]
            self.mask_syntax_highlights(row, left, left + display_width(content))
        return lines, selected, cursor

    def frame(self, width=100, height=24):
        """Return plain text lines, selected character spans by row, and input cursor."""
        width, height = max(1, width), max(1, height)
        self.syntax_highlights = {}
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
        fixed_titles = ["F7 Equations", "F8 Table", "F9 Clean Up", "F10 IO"]
        prefixes = [f"F{i + 1} " for i in range(len(self.menus))]
        fixed_width = display_width("  ".join(fixed_titles)) + sum(map(display_width, prefixes)) + 2 * len(prefixes)
        label_width = max(1, (width - fixed_width) // len(prefixes))
        menu_titles = [prefix + menu["label"] for prefix, menu in zip(prefixes, self.menus)] + fixed_titles
        if display_width("  ".join(menu_titles)) > width:
            menu_titles = [prefix + clip(menu["label"], label_width)
                           for prefix, menu in zip(prefixes, self.menus)] + fixed_titles
        if display_width("  ".join(menu_titles)) > width:
            menu_titles = [f"F{i}" for i in range(1, 11)]
        if self.equation_open:
            return self.equation_frame(width, height, "  ".join(menu_titles))
        if self.table_open:
            return self.table_frame(width, height, "  ".join(menu_titles))
        lines = ["  ".join(menu_titles), "-" * width]
        selected: dict[int, tuple[int, int]] = {}
        # Choose a visible history window that follows either the newest result
        # or the older entry currently selected with the navigation keys.
        index = None if self.io_open else self.history_index
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
                offset = 0
                if j == index:
                    first = 0 if self.history_part == "expression" else len(history[j].source) + 3
                    last = len(history[j].source) if self.history_part == "expression" else len(content)
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
                expression = history[j].source if history[j].is_error else history[j].line
                self.highlight_expression(len(lines), expression, column=len(prefix), offset=offset)
            else:
                line = "  (history is empty)" if i == 0 else ""
            lines.append(line)
        lines += ["-" * width]
        # Keep the cursor visible, including on very long arbitrary-precision inputs.
        available = width - 3
        input_selection = self.input_selection
        focus = self.cursor
        if input_selection is None and index is None and self.insert_mode and self.cursor < len(self.text):
            focus += 1
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
        self.highlight_expression(input_row, self.text, column=2, offset=start_text)
        cursor = (input_row + 1, 3 + display_width(self.text[start_text:self.cursor]))
        if input_selection is not None and index is None:
            first, last = input_selection
            first = max(first, start_text)
            last = min(last, start_text + len(lines[input_row]) - 2)
            if first < last:
                selected[input_row] = (2 + first - start_text, 2 + last - start_text)
            cursor = None
        elif index is None:
            preview = self.overwrite_span(self.text, self.cursor, column=2, offset=start_text)
            if preview is not None:
                selected[input_row] = preview
                cursor = None
        c = self.calculator
        selection = ("selected " + self.history_part if index is not None else
                     "selected input" if self.input_selected else "recall " + self.history_insert)
        lines.append("-" * width)
        lines.append(f" {c.mode.upper()} | history {len(c.history)}/{c.history.maxlen} | {c.output_mode} | approx {c.precision} digits | {selection}")
        lines.append(self.message)
        lines += [""] * (height - len(lines))
        if self.io_open:
            self.io_width, self.io_rows = width, self.history_rows
            output, first, total = self.io.window(width, self.io_rows, display_width)
            lines[1] = "IO | Up/Down/Page: scroll | Tab: input/output | F10/Esc: close"
            lines[2:2 + self.io_rows] = output + [""] * (self.io_rows - len(output))
            if not total:
                lines[2] = "Run :words or another command to see its complete output here."
            self.syntax_highlights = {row: spans for row, spans in self.syntax_highlights.items() if row == input_row}
            selected = {row: span for row, span in selected.items() if row == input_row}
            if not self.io_focus_input:
                cursor = None
                selected = {}
            focus = "input" if self.io_focus_input else "output"
            lines[-2] = f" IO lines {first + 1 if total else 0}-{min(total, first + self.io_rows)}/{total} | {focus} | Tab: switch"
        elif (self.io.entries and self.io.entries[-1].rstrip() == self.message.rstrip()
              and ("\n" in self.message or display_width(self.message) > width)):
            lines[-1] = "F10 IO: full output | " + self.message
        if self.help_open:
            # Overlays replace the relevant frame rows and hide the editing cursor.
            selected = {}
            self.syntax_highlights = {}
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
                    self.mask_syntax_highlights(row, anchor, anchor + box_width)
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
        lines[-2] = self.status_with_indicators(lines[-2], width)
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
