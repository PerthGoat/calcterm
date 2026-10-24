import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from calc_term import CalcError, ConsoleApp, Terminal, colorize_line, expression_highlights


ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class SyntaxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = ConsoleApp(config_path=Path(self.directory.name) / "settings.json")

    def test_numbers_functions_units_and_values_use_their_actual_token_boundaries(self):
        source = "sqrt(1_000.5e-2)+y99(0hFF)+3_in=>_ft+ans+π+sinus+value0hFF"
        tokens = [(source[first:last], kind) for first, last, kind in expression_highlights(source)]
        for token in (("sqrt", "function"), ("y99", "function"), ("1_000.5e-2", "number"),
                      ("0hFF", "number"), ("_in", "unit"), ("_ft", "unit"),
                      ("ans", "constant"), ("π", "constant")):
            self.assertIn(token, tokens)
        self.assertFalse(any(token in ("sinus", "value0hFF") for token, _ in tokens))

    def test_incomplete_input_and_unicode_operators_can_be_colored_without_evaluating(self):
        for source in ("sin(12. + sqrt(", "2×π≤3→x", "0b1010_0011+0o7_7", ":precision 12"):
            with self.subTest(source=source):
                spans = expression_highlights(source)
                colored = colorize_line(source, spans)
                self.assertEqual(ANSI.sub("", colored), source)
                self.assertTrue(all(0 <= first < last <= len(source) for first, last, _ in spans))
        colored = colorize_line(":precision 12", expression_highlights(":precision 12"))
        self.assertIn("\x1b[94m:precision\x1b[0m", colored)
        self.assertIn("\x1b[38;2;184;134;11m12\x1b[0m", colored)
        self.assertFalse(self.app.calculator.history)

    def test_selection_stays_one_readable_inverse_span_across_colored_tokens(self):
        source = "sqrt(123)+pi"
        colored = colorize_line(source, expression_highlights(source), selected=(1, 8))
        self.assertIn("\x1b[7mqrt(123\x1b[0m", colored)
        self.assertEqual(colored.count("\x1b[7m"), 1)
        self.assertIn("\x1b[96ms\x1b[0m", colored)
        self.assertIn("\x1b[95mpi\x1b[0m", colored)
        self.assertEqual(ANSI.sub("", colored), source)

    def test_terminal_renders_colors_without_altering_frame_input_or_saved_history(self):
        self.app.calculator.calculate("1/3")
        self.app.save_history()
        self.app.text = "sqrt(2)+pi+3_m"
        self.app.cursor = len(self.app.text)
        lines, _, _ = self.app.frame(99, 24)
        self.assertFalse(any("\x1b" in line for line in lines))
        with patch("sys.stdout", new_callable=io.StringIO) as output, \
                patch("shutil.get_terminal_size", return_value=(100, 24)):
            Terminal().render(self.app)
        colored = output.getvalue()
        for fragment in ("\x1b[96msqrt\x1b[0m", "\x1b[38;2;184;134;11m2\x1b[0m",
                         "\x1b[95mpi\x1b[0m", "\x1b[92m_m\x1b[0m"):
            self.assertIn(fragment, colored)
        self.assertEqual(ANSI.sub("", colored), "".join(lines))
        self.assertEqual(self.app.text, "sqrt(2)+pi+3_m")
        self.assertEqual(self.app.calculator.history[-1].result, "1/3")
        self.assertNotIn("\\u001b", self.app.problems_path.read_text(encoding="utf-8"))

    def test_scrolling_into_the_middle_of_a_function_preserves_its_color(self):
        self.app.text = "a" * 50 + "+sqrt(" + "1" * 100 + ")"
        self.app.cursor = 90
        lines, selected, _ = self.app.frame(40, 24)
        input_row = len(lines) - 4
        self.assertTrue(lines[input_row].startswith("> t("))
        colored = colorize_line(lines[input_row], self.app.syntax_highlights[input_row], selected.get(input_row))
        self.assertTrue(colored.startswith("> \x1b[96mt\x1b[0m"))
        self.assertEqual(ANSI.sub("", colored), lines[input_row])

    def test_equation_definitions_and_table_cells_have_colors_without_coloring_grid_lines(self):
        self.app.calculator.define_equation("y1", "4x")
        self.app.handle_key("F7")
        lines, _, _ = self.app.frame()
        input_row = len(lines) - 4
        colored = colorize_line(lines[input_row], self.app.syntax_highlights[input_row])
        self.assertIn("\x1b[96my1\x1b[0m", colored)
        self.assertIn("\x1b[38;2;184;134;11m4\x1b[0m", colored)
        self.app.handle_key("F8")
        lines, _, _ = self.app.frame()
        colored = colorize_line(lines[5], self.app.syntax_highlights[5])
        self.assertIn("\x1b[38;2;184;134;11m1\x1b[0m", colored)
        self.assertIn("\x1b[38;2;184;134;11m4\x1b[0m", colored)
        for first, last, _ in self.app.syntax_highlights[5]:
            self.assertNotIn("|", lines[5][first:last])

    def test_popups_and_menus_mask_underlying_expression_colors(self):
        for _ in range(20):
            self.app.calculator.calculate("123456789+sqrt(2)+pi")
        for mode in ("menu", "catalog", "problem"):
            with self.subTest(mode=mode):
                self.app.open_menu = None
                self.app.catalog_open = False
                self.app.problem_dialog = None
                if mode == "menu":
                    self.app.handle_key("F1")
                    top = 1
                elif mode == "catalog":
                    self.app.open_catalog()
                    top = 2
                else:
                    self.app.begin_problem_dialog("new")
                    top = 8
                lines, _, _ = self.app.frame(100, 24)
                border = re.search(r"\+-{2,}\+", lines[top])
                self.assertIsNotNone(border)
                assert border is not None
                left, right = border.span()
                bottom = next(row for row in range(top + 1, len(lines))
                              if lines[row][left:right] == lines[top][left:right])
                for row in range(top, bottom + 1):
                    for first, last, _ in self.app.syntax_highlights.get(row, []):
                        self.assertTrue(last <= left or first >= right)

    def test_options_toggle_colors_on_and_off_with_current_state_in_label(self):
        self.assertTrue(self.app.syntax_colors)
        for current, following in (("On", False), ("Off", True)):
            self.app.handle_key("F5")
            for char in "Syntax colors":
                self.app.handle_key(char)
            self.assertEqual([item["label"] for item in self.app.menu_items()], ["Syntax colors: " + current])
            self.app.handle_key("ENTER")
            self.assertEqual(self.app.syntax_colors, following)
            self.assertIsNone(self.app.open_menu)

    def test_colors_off_preserves_selection_and_applies_to_each_view(self):
        self.app.text, self.app.cursor = "sqrt(2)+pi", 10
        self.app.select_all_input()
        self.app.command(":colors off")
        with patch("sys.stdout", new_callable=io.StringIO) as output, \
                patch("shutil.get_terminal_size", return_value=(100, 24)):
            Terminal().render(self.app)
        self.assertNotRegex(output.getvalue(), r"\x1b\[(?:3[0-7]|9[0-7]|38;[0-9;]+)m")
        self.assertIn("\x1b[7msqrt(2)+pi\x1b[0m", output.getvalue())
        self.app.calculator.define_equation("y1", "4x")
        for key in ("F7", "F8"):
            self.app.handle_key(key)
            self.app.frame()
            self.assertFalse(self.app.syntax_highlights)
        self.app.command(":colors on")
        self.app.frame()
        self.assertTrue(self.app.syntax_highlights)

    def test_color_preference_persists_and_is_shared_between_problems(self):
        self.app.command(":colors off")
        restored = ConsoleApp(config_path=self.app.config_path)
        self.assertFalse(restored.syntax_colors)
        self.assertIn("Syntax colors: Off", [item["label"] for item in restored.menus[4]["items"]])
        restored.new_problem("Algebra")
        self.assertFalse(restored.syntax_colors)
        restored.open_problem("Default")
        self.assertFalse(restored.syntax_colors)
        restored.command(":colors toggle")
        self.assertTrue(ConsoleApp(config_path=self.app.config_path).syntax_colors)

    def test_older_custom_options_gain_color_toggle_and_default_to_enabled(self):
        menus = self.app.menus
        menus[4]["label"] = "Custom Options"
        menus[4]["items"] = [item for item in menus[4]["items"] if item.get("command") != ":colors toggle"]
        document = json.dumps({"menus": menus})
        self.app.config_path.write_text(document, encoding="utf-8")
        restored = ConsoleApp(config_path=self.app.config_path)
        self.assertTrue(restored.syntax_colors)
        self.assertEqual(restored.menus[4]["label"], "Custom Options")
        self.assertIn("Syntax colors: On", [item["label"] for item in restored.menus[4]["items"]])
        self.assertEqual(restored.config_path.read_text(encoding="utf-8"), document)

    def test_invalid_color_settings_are_preserved_and_commands_do_not_change_state(self):
        for value in (0, 1, "off", None):
            with self.subTest(value=value):
                document = json.dumps({"mode": "degree", "syntax_colors": value})
                self.app.config_path.write_text(document, encoding="utf-8")
                restored = ConsoleApp(config_path=self.app.config_path)
                self.assertIn("Config error:", restored.message)
                self.assertTrue(restored.syntax_colors)
                self.assertEqual(restored.calculator.mode, "radian")
                self.assertEqual(restored.config_path.read_text(encoding="utf-8"), document)
        with self.assertRaises(CalcError):
            self.app.command(":colors invalid")
        self.assertTrue(self.app.syntax_colors)


if __name__ == "__main__":
    unittest.main()
