"""Command-line entry point and compatibility imports for the console calculator."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from calcterm.app import ConsoleApp, clip, display_width, insert_text_at_cursor, menu_panel
from calcterm.core import (BASE_NAMES, BITWISE, COMPARISONS, ZERO, CalcError, Quantity,
                           Unit, UnitRegistry, approximate_value, combine_dims,
                           dimension, expression_text, unit_key)
from calcterm.engine import (BASE_LITERAL, BASES, DIGITS, EQUATION_NAMES, FUNCTIONS,
                             RESERVED, TOKEN, TRANSLATE, Calculator, HistoryEntry,
                             Parser, decimal_literals, normalize_input)
from calcterm.menus import (HELP_LINES, SYMBOLS, catalog_items, categorize_unit_items,
                            cleanup_menu, command_item, default_menus, filter_menu_items,
                            insert_item, output_options, problem_menu, validate_menus)
from calcterm.syntax import SYNTAX_COLORS, SYNTAX_TOKEN, colorize_line, expression_highlights
from calcterm.terminal import (ANSI_KEYS, CONTROL_KEYS, WINDOWS_KEYS, Terminal,
                               modified_terminal_key, windows_shift_pressed)


# Entry point: the same calculator supports batch, line-oriented, and full-screen use.
def main(argv=None):
    parser = argparse.ArgumentParser(description="Exact symbolic console math, units, and configurable F1-F6 menus.")
    parser.add_argument("--config", type=Path, help="JSON configuration path (default: beside calc_term.py)")
    parser.add_argument("--plain", action="store_true", help="line-oriented mode for pipes or basic terminals")
    parser.add_argument("--eval", dest="expressions", action="append", help="evaluate an expression and exit; may be repeated")
    options = parser.parse_args(argv)
    # Windows redirected output otherwise often uses a legacy encoding without Greek.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")
    app = ConsoleApp(config_path=options.config)
    # Repeated --eval options share one session, including variables and ans.
    if options.expressions:
        status = 0
        for text in options.expressions:
            try:
                print(text + " = " + app.calculator.calculate(text))
                app.message = app.calculator.history[-1].line
                if not app.save_history():
                    print(app.message, file=sys.stderr)
                    status = 1
            except CalcError as exc:
                print("Error: " + str(exc), file=sys.stderr)
                status = 1
                if not app.save_history():
                    print(app.message, file=sys.stderr)
        return status
    if options.plain or not (sys.stdin.isatty() and sys.stdout.isatty()):
        # Pipes and basic terminals use complete input lines instead of raw key handling.
        if sys.stdin.isatty():
            print("Exact console calculator; :help for commands; :quit to exit.")
        while app.running:
            try:
                text = input("> " if sys.stdin.isatty() else "")
            except (EOFError, KeyboardInterrupt):
                break
            app.text, app.cursor = text, len(text)
            app.submit()
            if app.help_open:
                print("\n".join(HELP_LINES))
                app.help_open = False
            elif text.strip() and app.running:
                print(app.message)
        if not app.save_session():
            print(app.message, file=sys.stderr)
            return 1
        return 0
    status = 0
    try:
        # The context manager restores terminal state before errors are printed.
        with Terminal() as terminal:
            terminal.run(app)
    except KeyboardInterrupt:
        pass
    except CalcError as exc:
        print(str(exc), file=sys.stderr)
        status = 1
    finally:
        if not app.save_session():
            print(app.message, file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
