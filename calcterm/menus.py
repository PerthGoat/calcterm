"""Menu definitions, validation, catalog entries, and keyboard help."""

from __future__ import annotations

import unicodedata

from .core import CalcError, unit_key
from .engine import EQUATION_NAMES, FUNCTIONS, RESERVED, TRANSLATE


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
            command_item("Clear history", ":clear"), command_item("Reset configuration", ":resetconfig")]}


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
         command_item("Syntax colors: On", ":colors toggle"),
         problem_menu(),
         command_item("Select result first", ":recall result"), command_item("Select expression first", ":recall expression"),
         insert_item("Set precision", ":precision 100"), insert_item("Rename a menu", ":menu 1 Math"),
         insert_item("Add menu item", ":menuadd 1 Square | ^2"), command_item("Save configuration", ":save"),
         command_item("Create backup config", ":backupconfig"),
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
    "Backspace with history selected: delete the whole entry and save history.",
    "Shift+Enter in input: approximate this result; the configured output mode stays unchanged.",
    "After calculation: input stays selected; type to replace; Backspace/Delete clears.",
    "Left/Right on selected input: move to the beginning/end for editing.",
    "Shift+Left/Right: select part of the input; type or Backspace/Delete replaces it.",
    "Insert: toggle overwrite typing; INS appears beside the Shift indicator when on.",
    "Left/Right: move cursor; Home/End: line ends; Tab: input/history focus.",
    "Esc: close menu or return to input; Ctrl+C / Ctrl+D: quit; Ctrl+L: redraw.",
    "F1-F6: menus; Up/Down or PageUp/PageDown: select; Enter: choose.",
    "F7: equations y1-y99; Enter saves; Up/Down selects; Esc cancels current edit.",
    "Enter 4x for y1(x); return with F7 and calculate y1(3) to get 12.",
    "Ctrl+T in F7: check/uncheck a formula for the F8 table; new formulas are checked.",
    "F8: table; Tab: set start/step; Enter: apply; arrows/PageUp/PageDown: scroll.",
    "F9 Clean Up: clear set variables/history, or reset configuration to defaults.",
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
    "Settings, custom units, and menus save automatically; :resetconfig restores defaults.",
    "F5 > Create backup config or :backupconfig: save a numbered config copy beside the original.",
]
