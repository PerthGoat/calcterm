import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from calc_term import CalcError, Calculator, ConsoleApp, Terminal, display_width
from calcterm.graph import DEFAULT_GRAPH, GraphView, validate_graph_settings


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.calculator = Calculator()
        self.graph = GraphView()

    def test_auto_fit_tracks_range_and_constant_functions(self):
        self.calculator.define_equation("y1", "x^2")
        self.graph.settings.update(x_min="-2", x_max="2")
        plot = self.graph.plot(self.calculator, ["y1"], 41, 15)
        self.assertLess(plot.y_min, 0)
        self.assertGreater(plot.y_max, 4)
        self.assertTrue(plot.colors)
        self.graph.settings.update(x_min="-1", x_max="1")
        closer = self.graph.plot(self.calculator, ["y1"], 41, 15)
        self.assertLess(closer.y_max, plot.y_max)
        self.calculator.define_equation("y1", "1000000000+x")
        offset = self.graph.plot(self.calculator, ["y1"], 41, 15)
        self.assertLess(offset.y_max - offset.y_min, 3)
        for constant in ("0", "7", "-5"):
            self.calculator.define_equation("y1", constant)
            flat = self.graph.plot(self.calculator, ["y1"], 41, 15)
            self.assertLess(flat.y_min, float(constant))
            self.assertGreater(flat.y_max, float(constant))
            self.assertEqual(len(flat.colors), 41)

    def test_manual_bounds_clip_and_discontinuities_leave_gaps(self):
        self.calculator.define_equation("y1", "1/x")
        self.graph.settings.update(x_min="-2", x_max="2", y_mode="manual", y_min="-3", y_max="3")
        plot = self.graph.plot(self.calculator, ["y1"], 49, 13)
        self.assertEqual((plot.y_min, plot.y_max), (-3, 3))
        self.assertFalse(any(column == 24 for row, column in plot.colors))
        # At the pole the vertical axis must not become a connected curve.
        self.assertEqual(plot.cells[6][24], "+")
        self.calculator.define_equation("y1", "100")
        self.assertFalse(self.graph.plot(self.calculator, ["y1"], 49, 13).colors)

    def test_nonreal_undefined_and_symbolic_values_do_not_break_other_curves(self):
        for name, body in (("y1", "sqrt(x)"), ("y2", "sqrt(-1)"), ("y3", "y99(x)"),
                           ("y4", "t+x"), ("y5", "x_m")):
            self.calculator.define_equation(name, body)
        plot = self.graph.plot(self.calculator, list(self.calculator.equations), 41, 15)
        self.assertEqual(plot.invalid, ["y2", "y3", "y4", "y5"])
        self.assertTrue(plot.colors)
        self.assertTrue(all(column >= 20 for row, column in plot.colors))
        empty = self.graph.plot(self.calculator, ["y2", "y3"], 41, 15)
        self.assertEqual((empty.y_min, empty.y_max), (-1, 1))

    def test_bounds_validation_and_exact_expressions(self):
        settings = validate_graph_settings(self.calculator, {"x_min": "-pi", "x_max": "pi", "y_mode": "manual"})
        self.assertEqual((settings["x_min"], settings["x_max"]), ("-pi", "pi"))
        for data in ([], {"x_min": 1}, {"x_min": "t"}, {"x_min": "1_m"}, {"x_min": "i"},
                     {"x_min": "True"}, {"x_min": "1/0"}, {"x_min": "10"}, {"x_max": "-11"},
                     {"y_mode": "bad"}, {"y_min": "10"}, {"x_max": "10^1000"}):
            with self.subTest(data=data), self.assertRaises(CalcError):
                validate_graph_settings(self.calculator, data)

    def test_cache_reuses_samples_and_tracks_equations_mode_variables_and_ans(self):
        self.calculator.calculate("2->a")
        self.calculator.define_equation("y1", "sin(x)+a+ans")
        with patch.object(self.calculator, "equation", wraps=self.calculator.equation) as equation:
            self.graph.plot(self.calculator, ["y1"], 41, 15)
            calls = equation.call_count
            self.graph.plot(self.calculator, ["y1"], 41, 15)
            self.assertEqual(equation.call_count, calls)
            for change in (lambda: self.calculator.set_mode("degree"),
                           lambda: self.calculator.calculate("3->a"),
                           lambda: self.calculator.calculate("8"),
                           lambda: self.calculator.define_equation("y1", "x+a")):
                change()
                self.graph.plot(self.calculator, ["y1"], 41, 15)
                self.assertGreater(equation.call_count, calls)
                calls = equation.call_count


class GraphAppTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "settings.json"
        self.app = ConsoleApp(config_path=self.path)

    def type_keys(self, text):
        for char in text:
            self.app.handle_key(char)

    def replace_field(self, text):
        self.app.handle_key("CTRL_U")
        self.type_keys(text)

    def set_window(self):
        self.app.handle_key("TAB")
        self.replace_field("-pi")
        self.app.handle_key("TAB")
        self.replace_field("pi")
        self.app.handle_key("TAB")
        self.app.handle_key(" ")
        self.app.handle_key("TAB")
        self.replace_field("-2")
        self.app.handle_key("TAB")
        self.replace_field("2")
        self.app.handle_key("ENTER")

    def test_graph_uses_checked_equations_and_preserves_calculator_state(self):
        self.app.calculator.define_equation("y1", "x^2")
        self.app.calculator.define_equation("y2", "x+1000")
        self.app.calculator.unchecked_equations.add("y2")
        self.app.calculator.calculate("7->x")
        self.app.text, self.app.cursor = "2+", 2
        history, answer = list(self.app.calculator.history), self.app.calculator.answer
        self.app.handle_key("SHIFT_F7")
        lines, selected, cursor = self.app.frame(100, 24)
        self.assertIn("F7 Equations", lines[0])
        self.assertEqual(lines[2], "1:y1")
        self.assertFalse(selected)
        self.assertIsNone(cursor)
        self.assertEqual(list(self.app.calculator.history), history)
        self.assertEqual(self.app.calculator.answer, answer)
        self.assertEqual(self.app.calculator.variables["x"].value, 7)
        self.app.handle_key("SHIFT_F7")
        self.assertEqual((self.app.text, self.app.cursor), ("2+", 2))
        self.app.handle_key("F7")
        self.app.handle_key("CTRL_T")
        self.app.handle_key("SHIFT_F7")
        self.assertIn("Check equations in F7", self.app.frame()[0][2])

    def test_bounds_editor_saves_manual_and_auto_settings_per_problem(self):
        self.app.calculator.define_equation("y1", "sin(x)")
        self.app.handle_key("SHIFT_F7")
        self.set_window()
        manual = dict(self.app.graph.settings)
        self.assertEqual(manual, {"x_min": "-pi", "x_max": "pi", "y_mode": "manual", "y_min": "-2", "y_max": "2"})
        restored = ConsoleApp(config_path=self.path)
        self.assertEqual(restored.graph.settings, manual)
        self.assertEqual(restored.calculator.equations, {"y1": "sin(x)"})
        self.app.new_problem("Other")
        self.assertEqual(self.app.graph.settings, DEFAULT_GRAPH)
        self.app.open_problem("Default")
        self.assertEqual(self.app.graph.settings, manual)
        self.app.handle_key("SHIFT_F7")
        self.app.handle_key("TAB")
        self.app.handle_key("TAB")
        self.app.handle_key("TAB")
        self.app.handle_key(" ")
        self.app.handle_key("TAB")
        self.assertEqual(self.app.graph.edit_field, 0)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.graph.settings["y_mode"], "auto")
        self.assertEqual(self.app.graph.settings["y_min"], "-2")
        self.assertEqual(ConsoleApp(config_path=self.path).graph.settings, self.app.graph.settings)

    def test_invalid_edits_stay_editable_and_escape_preserves_saved_window(self):
        self.app.handle_key("SHIFT_F7")
        self.app.handle_key("TAB")
        self.replace_field("20")
        for key in ("ENTER", "SHIFT_F7", "F7", "F8", "F10", "F1", "F9"):
            self.app.handle_key(key)
            self.assertTrue(self.app.graph_open)
            self.assertEqual(self.app.graph.edit_field, 0)
            self.assertEqual(self.app.graph.settings, DEFAULT_GRAPH)
            self.assertIn("lower bound", self.app.message)
        self.app.handle_key("ESC")
        self.assertTrue(self.app.graph_open)
        self.assertIsNone(self.app.graph.edit_field)
        self.app.handle_key("ESC")
        self.assertFalse(self.app.graph_open)

    def test_graph_open_commits_valid_equation_and_rejects_invalid_pending_edits(self):
        self.app.handle_key("F7")
        self.type_keys("x^2")
        self.app.handle_key("SHIFT_F7")
        self.assertTrue(self.app.graph_open)
        self.assertEqual(self.app.calculator.equations, {"y1": "x^2"})
        self.app.handle_key("F7")
        self.type_keys("+")
        self.app.handle_key("SHIFT_F7")
        self.assertTrue(self.app.equation_open)
        self.assertFalse(self.app.graph_open)
        self.app.handle_key("ESC")
        self.app.handle_key("F8")
        self.app.handle_key("TAB")
        self.app.handle_key("TAB")
        self.replace_field("0")
        self.app.handle_key("SHIFT_F7")
        self.assertTrue(self.app.table_open)
        self.assertFalse(self.app.graph_open)

    def test_resizes_empty_views_color_toggle_and_edit_cursor_stay_in_terminal(self):
        self.app.handle_key("SHIFT_F7")
        self.assertIn("Check equations in F7", self.app.frame()[0][2])
        self.app.calculator.define_equation("y1", "x")
        for width, height in ((40, 12), (100, 24), (160, 40), (20, 6)):
            with self.subTest(width=width, height=height):
                lines, _, _ = self.app.frame(width, height)
                self.assertLessEqual(len(lines), height)
                self.assertTrue(all(display_width(line) <= width for line in lines))
        self.app.frame()
        self.assertTrue(self.app.syntax_highlights)
        self.app.syntax_colors = False
        self.app.frame()
        self.assertFalse(self.app.syntax_highlights)
        self.app.handle_key("TAB")
        self.replace_field("1" * 200)
        lines, selected, cursor = self.app.frame(40, 12)
        self.assertLessEqual(cursor[1], 40)
        self.assertTrue(all(display_width(line) <= 40 for line in lines))

    def test_valid_pending_edits_save_on_exit_and_write_failure_retries(self):
        self.app.handle_key("SHIFT_F7")
        self.app.handle_key("TAB")
        self.replace_field("-3")
        self.assertTrue(self.app.save_session())
        self.assertEqual(ConsoleApp(config_path=self.path).graph.settings["x_min"], "-3")
        self.app.handle_key("TAB")
        self.replace_field("-4")
        before = self.app.problems_path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Locked")):
            self.app.handle_key("ENTER")
            self.assertIn("Problem save error", self.app.message)
        self.assertEqual(self.app.problems_path.read_bytes(), before)
        self.assertTrue(self.app.save_session())
        self.assertEqual(ConsoleApp(config_path=self.path).graph.settings["x_min"], "-4")

    def test_bad_saved_graph_settings_are_preserved_and_older_files_get_defaults(self):
        for graph in ([], {"x_min": "11"}, {"y_mode": "invalid"}, {"y_min": "x"}):
            document = json.dumps({"mode": "degree", "graph": graph})
            self.path.write_text(document, encoding="utf-8")
            restored = ConsoleApp(config_path=self.path)
            self.assertIn("Config error", restored.message)
            self.assertEqual(restored.calculator.mode, "radian")
            self.assertEqual(self.path.read_text(encoding="utf-8"), document)
        self.path.write_text("{}", encoding="utf-8")
        self.assertEqual(ConsoleApp(config_path=self.path).graph.settings, DEFAULT_GRAPH)
        document = json.dumps({"version": 1, "active": "Default", "problems": {"Default": {"graph": {"y_max": "-10"}}}})
        self.app.problems_path.write_text(document, encoding="utf-8")
        restored = ConsoleApp(config_path=self.path)
        self.assertIn("Problems load error", restored.message)
        self.assertFalse(restored.save_session())
        self.assertEqual(restored.problems_path.read_text(encoding="utf-8"), document)

    def test_windows_and_posix_distinguish_f7_from_shift_f7(self):
        for code, shifted, expected in (("A", False, "F7"), ("A", True, "SHIFT_F7"),
                                         ("Z", False, "SHIFT_F7")):
            with self.subTest(code=code, shifted=shifted):
                keyboard = Mock()
                keyboard.getwch.side_effect = ["\x00", code]
                with patch("os.name", "nt"), patch.dict("sys.modules", {"msvcrt": keyboard}), \
                        patch("calcterm.terminal.windows_shift_pressed", return_value=shifted):
                    self.assertEqual(Terminal().read_key(), expected)
        for sequence, expected in ((b"\x1b[18~", "F7"), (b"\x1b[18;2~", "SHIFT_F7")):
            with self.subTest(sequence=sequence), patch("os.name", "posix"), patch("sys.stdin") as stdin, \
                    patch("select.select", return_value=([0], [], [])), \
                    patch("os.read", side_effect=[bytes([char]) for char in sequence]):
                stdin.fileno.return_value = 0
                self.assertEqual(Terminal().read_key(), expected)

    def test_plain_f7_opens_equations_shift_f7_toggles_graph_and_f11_is_unused(self):
        self.app.handle_key("F7")
        self.assertTrue(self.app.equation_open)
        self.assertFalse(self.app.graph_open)
        self.app.handle_key("SHIFT_F7")
        self.assertFalse(self.app.equation_open)
        self.assertTrue(self.app.graph_open)
        self.app.handle_key("F11")
        self.assertTrue(self.app.graph_open)
        self.app.handle_key("SHIFT_F7")
        self.assertFalse(self.app.graph_open)
        self.app.handle_key("F11")
        self.assertFalse(self.app.graph_open)


if __name__ == "__main__":
    unittest.main()
