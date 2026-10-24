import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from calc_term import CalcError, Calculator, ConsoleApp, Terminal, display_width, main, validate_menus


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config_path = Path(self.directory.name) / "settings.json"
        self.app = ConsoleApp(config_path=self.config_path)

    def type_keys(self, text):
        for char in text:
            self.app.handle_key(char)

    def highlighted_text(self, width=100, height=24):
        lines, selected, _ = self.app.frame(width=width, height=height)
        self.assertEqual(len(selected), 1)
        row, (first, last) = next(iter(selected.items()))
        return lines[row][first:last]

    def test_history_saves_without_settings_save_and_can_be_recalled(self):
        self.type_keys("5+3")
        self.app.handle_key("ENTER")
        self.assertTrue(self.app.history_path.exists())
        self.assertFalse(self.config_path.exists())
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(list(restored.calculator.history), list(self.app.calculator.history))
        restored.text, restored.cursor = "()+1", 1
        restored.handle_key("UP")
        restored.handle_key("UP")
        restored.handle_key("ENTER")
        self.assertEqual(restored.text, "(5+3)+1")
        self.assertEqual(restored.cursor, 4)
        restored.handle_key("ENTER")
        reopened = ConsoleApp(config_path=self.config_path)
        self.assertEqual(reopened.calculator.history[-1].result, "9")

    def test_persistent_history_preserves_unicode_and_arbitrary_precision(self):
        source = "1" + "0" * 5000 + "+1->ε"
        self.app.text, self.app.cursor = source, len(source)
        self.app.submit()
        expected = list(self.app.calculator.history)
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(list(restored.calculator.history), expected)
        self.assertIn("ε", restored.calculator.history[0].source)
        self.assertEqual(len(restored.calculator.history[0].result), 5001)
        self.assertTrue(restored.calculator.history[0].result.endswith("1"))
        self.assertFalse(restored.calculator.variables)

    def test_restoring_history_does_not_evaluate_saved_expressions(self):
        data = [{"source": "3->x", "result": "3"},
                {"source": "4*x", "result": "12"},
                {"source": "unsupported()", "result": "recorded result"}]
        self.app.history_path.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(Calculator, "evaluate", side_effect=AssertionError("History must not be evaluated")):
            restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual([entry.line for entry in restored.calculator.history],
                         [item["source"] + " = " + item["result"] for item in data])
        self.assertFalse(restored.calculator.variables)
        self.assertEqual(restored.calculator.answer.value, 0)

    def test_clear_also_clears_saved_history(self):
        self.type_keys("5+3")
        self.app.handle_key("ENTER")
        self.app.command(":clear")
        self.assertEqual(json.loads(self.app.history_path.read_text(encoding="utf-8")), [])
        self.assertFalse(ConsoleApp(config_path=self.config_path).calculator.history)

    def test_saved_history_keeps_tall_terminal_entries_until_first_frame(self):
        self.app.frame(height=50)
        for i in range(50):
            self.app.text = str(i)
            self.app.submit()
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(len(restored.calculator.history), 44)
        self.assertEqual(restored.calculator.history[0].source, "6")
        restored.frame(height=50)
        self.assertEqual(len(restored.calculator.history), 44)
        restored.frame(height=24)
        self.assertEqual(len(restored.calculator.history), 30)
        reopened = ConsoleApp(config_path=self.config_path)
        self.assertEqual(len(reopened.calculator.history), 30)
        self.assertEqual(reopened.calculator.history[0].source, "20")

    def test_failed_calculation_is_saved_and_settings_leave_history_intact(self):
        self.type_keys("5+3")
        self.app.handle_key("ENTER")
        self.type_keys("1/0")
        self.app.handle_key("ENTER")
        before = self.app.history_path.read_bytes()
        self.app.command(":mode degree")
        self.assertEqual(self.app.history_path.read_bytes(), before)
        self.assertFalse(self.config_path.exists())
        self.assertEqual(self.app.text, "1/0")
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(list(restored.calculator.history), list(self.app.calculator.history))
        self.assertEqual(restored.calculator.history[-1].line, "1/0 = Error: Division by zero.")
        self.assertTrue(restored.calculator.history[-1].is_error)

    def test_bad_history_file_is_preserved_on_startup_and_exit(self):
        invalid = ["not json", "{}", '[{"source":"1","result":"1"},{}]',
                   '[{"source":1,"result":"1"}]', '[{"source":"1","result":null}]',
                   '[{"source":"","result":"1"}]',
                   '[{"source":"1","result":"1","is_error":"false"}]']
        for data in invalid:
            with self.subTest(data=data):
                self.app.history_path.write_text(data, encoding="utf-8")
                restored = ConsoleApp(config_path=self.config_path)
                self.assertIn("History load error:", restored.message)
                self.assertFalse(restored.calculator.history)
                self.assertTrue(restored.save_history())
                self.assertEqual(restored.history_path.read_text(encoding="utf-8"), data)
                restored.command(":clear")
                self.assertEqual(json.loads(restored.history_path.read_text(encoding="utf-8")), [])

    def test_history_save_failure_preserves_file_and_calculation_then_retries(self):
        self.type_keys("5+3")
        self.app.handle_key("ENTER")
        before = self.app.history_path.read_bytes()
        self.type_keys("6+3")
        with patch.object(Path, "replace", side_effect=PermissionError("File is locked")):
            self.app.handle_key("ENTER")
        self.assertEqual(self.app.history_path.read_bytes(), before)
        self.assertEqual(self.app.calculator.history[-1].result, "9")
        self.assertEqual(self.app.text, "6+3")
        self.assertTrue(self.app.input_selected)
        self.assertIn("6+3 = 9", self.app.message)
        self.assertIn("History save error:", self.app.message)
        self.assertTrue(self.app.save_history())
        self.assertNotIn("History save error:", self.app.message)
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(list(restored.calculator.history), list(self.app.calculator.history))

    def test_submit_and_layout(self):
        self.type_keys("3->x")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "3->x")
        self.assertTrue(self.app.input_selected)
        lines, selected, cursor = self.app.frame()
        self.assertIn("F1 Math", lines[0])
        self.assertIn("F6 Help", lines[0])
        self.assertIn("3->x = 3", "\n".join(lines[2:5]))
        self.assertEqual(lines[-3], "> 3->x")
        self.assertIn("RADIAN", lines[-2])
        self.assertIn("history 1/30", lines[-2])
        self.assertIsNone(cursor)
        self.assertEqual(selected, {21: (2, 6)})

    def test_submitted_input_is_deleted_as_a_whole(self):
        for key in ("BACKSPACE", "DELETE", "CTRL_U"):
            with self.subTest(key=key):
                self.type_keys("5+3")
                self.app.handle_key("ENTER")
                history = list(self.app.calculator.history)
                self.app.handle_key(key)
                self.assertEqual((self.app.text, self.app.cursor), ("", 0))
                self.assertFalse(self.app.input_selected)
                self.assertEqual(list(self.app.calculator.history), history)
                self.assertEqual(self.app.calculator.answer.value, 8)

    def test_arrow_keys_collapse_selection_to_the_ends_before_normal_editing(self):
        for key, position in (("LEFT", 0), ("RIGHT", 3), ("HOME", 0), ("END", 3)):
            with self.subTest(key=key):
                self.app.clear_input()
                self.type_keys("5+3")
                self.app.handle_key("ENTER")
                self.app.handle_key(key)
                self.assertEqual(self.app.text, "5+3")
                self.assertEqual(self.app.cursor, position)
                self.assertFalse(self.app.input_selected)
                self.app.handle_key("2")
                self.assertEqual(self.app.text, "25+3" if position == 0 else "5+32")
                self.assertEqual(self.app.cursor, position + 1)

    def test_typing_replaces_submitted_input_and_enter_can_repeat_a_calculation(self):
        self.type_keys("5+3")
        self.app.handle_key("ENTER")
        self.app.handle_key("ENTER")
        self.assertEqual([entry.result for entry in self.app.calculator.history], ["8", "8"])
        self.assertEqual(self.highlighted_text(), "5+3")
        self.type_keys("9+1")
        self.assertEqual(self.app.text, "9+1")
        self.assertFalse(self.app.input_selected)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.history[-1].result, "10")
        self.assertEqual(self.highlighted_text(), "9+1")

    def test_history_menu_and_catalog_insertions_replace_selected_input(self):
        self.type_keys("5+3")
        self.app.handle_key("ENTER")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "8")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "8")
        self.assertFalse(self.app.input_selected)
        self.app.handle_key("ENTER")
        self.app.handle_key("F4")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "ε")
        self.app.handle_key("ENTER")
        self.app.handle_key("F6")
        self.type_keys("Catalog")
        self.app.handle_key("ENTER")
        self.type_keys("sqrt(")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "sqrt(")
        self.assertFalse(self.app.input_selected)

    def test_selected_long_and_wide_input_renders_and_can_be_edited_at_either_end(self):
        for source in ("1+" * 100 + "1", "数" * 100):
            with self.subTest(source=source):
                self.app.clear_input()
                self.type_keys(source)
                self.app.handle_key("ENTER")
                lines, selected, cursor = self.app.frame(width=40, height=12)
                self.assertEqual(self.app.text, source)
                self.assertEqual(selected, {9: (2, len(lines[9]))})
                self.assertTrue(all(display_width(line) <= 40 for line in lines))
                self.assertIsNone(cursor)
                self.app.handle_key("LEFT")
                self.assertEqual(self.app.cursor, 0)
                self.assertEqual(self.app.frame(width=40, height=12)[2], (10, 3))
                self.app.handle_key("END")
                cursor = self.app.frame(width=40, height=12)[2]
                self.assertIsNotNone(cursor)
                self.assertLessEqual(cursor[1], 40)

    def test_failed_calculations_select_input_and_commands_still_clear_the_line(self):
        self.type_keys("1/0")
        self.app.handle_key("ENTER")
        self.assertEqual(self.highlighted_text(), "1/0")
        self.assertTrue(self.app.calculator.history[-1].is_error)
        self.app.handle_key("LEFT")
        self.assertEqual(self.app.cursor, 0)
        self.app.handle_key("DELETE")
        self.assertEqual(self.app.text, "/0")
        self.app.clear_input()
        self.type_keys(":precision 12")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "")
        self.assertFalse(self.app.input_selected)
        self.assertEqual(self.app.calculator.precision, 12)

    def test_f7_equation_editor_and_calculator_call(self):
        self.type_keys("y1(3)")
        self.app.handle_key("F7")
        self.type_keys("4x")
        lines, selected, cursor = self.app.frame()
        self.assertIn("F7 Equations", lines[0])
        self.assertIn("y1=4x", lines[2])
        self.assertEqual(lines[-3], "y1(x)=4x")
        self.assertEqual(lines[next(iter(selected))], "> [✓] y1=4x")
        self.assertEqual(cursor, (22, 9))
        self.app.handle_key("F7")
        self.assertFalse(self.app.equation_open)
        self.assertEqual(self.app.text, "y1(3)")
        self.assertEqual(self.app.cursor, 5)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.history[-1].line, "y1(3) = 12")

    def test_equation_navigation_reaches_y99_and_tracks_selection_on_resize(self):
        self.app.handle_key("F7")
        self.type_keys("4x")
        self.app.handle_key("DOWN")
        self.type_keys("x^2")
        self.app.handle_key("UP")
        self.assertEqual(self.app.equation_text, "4x")
        for _ in range(6):
            self.app.handle_key("PAGEDOWN")
        self.assertEqual(self.app.equation_index, 98)
        self.type_keys("x+99")
        for width, height in ((40, 12), (80, 24), (100, 120)):
            lines, selected, cursor = self.app.frame(width, height)
            self.assertEqual(len(lines), height)
            self.assertIn("y99(x)=x+99", lines[-3])
            self.assertIn("y99=x+99", lines[next(iter(selected))])
            self.assertLessEqual(cursor[1], width)
            self.assertTrue(all(display_width(line) <= width for line in lines))
        self.app.handle_key("F7")
        self.assertEqual(self.app.calculator.calculate("y99(1)"), "100")
        self.assertEqual(self.app.calculator.calculate("y2(3)"), "9")

    def test_equation_editing_and_clearing(self):
        self.app.handle_key("F7")
        self.type_keys("4x+1")
        self.app.handle_key("HOME")
        self.app.handle_key("DELETE")
        self.type_keys("2")
        self.app.handle_key("END")
        self.app.handle_key("BACKSPACE")
        self.type_keys("3")
        self.app.handle_key("LEFT")
        self.app.handle_key("RIGHT")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.equations["y1"], "2x+3")
        self.app.handle_key("UP")
        self.app.handle_key("CTRL_U")
        self.app.handle_key("F7")
        self.assertNotIn("y1", self.app.calculator.equations)

    def test_invalid_equation_can_be_corrected_or_canceled(self):
        self.app.calculator.define_equation("y1", "4x")
        self.app.handle_key("F7")
        self.type_keys("+")
        for key in ("DOWN", "ENTER", "F7", "F1", "F9"):
            self.app.handle_key(key)
            self.assertTrue(self.app.equation_open)
            self.assertEqual(self.app.equation_index, 0)
            self.assertEqual(self.app.equation_text, "4x+")
            self.assertIn("Error:", self.app.message)
            self.assertEqual(self.app.calculator.equations["y1"], "4x")
        self.type_keys("1")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.equations["y1"], "4x+1")
        self.type_keys("x+")
        self.app.handle_key("ESC")
        self.assertFalse(self.app.equation_open)
        self.assertNotIn("y2", self.app.calculator.equations)

    def test_equations_save_and_restore_with_forward_references(self):
        self.app.calculator.define_equation("y1", "y99(x)+1")
        self.app.calculator.define_equation("y99", "4x")
        self.app.command(":save")
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(restored.calculator.equations, self.app.calculator.equations)
        self.assertFalse(restored.calculator.variables)
        self.assertEqual(restored.calculator.calculate("y1(3)"), "13")

    def test_invalid_saved_equations_leave_config_intact_and_load_atomically(self):
        for equations in ([], {"y0": "x"}, {"y1": 4}, {"y1": "4x", "y2": "x+"}):
            with self.subTest(equations=equations):
                configuration = json.dumps({"mode": "degree", "equations": equations})
                self.config_path.write_text(configuration, encoding="utf-8")
                restored = ConsoleApp(config_path=self.config_path)
                self.assertIn("Config error:", restored.message)
                self.assertEqual(restored.calculator.mode, "radian")
                self.assertFalse(restored.calculator.equations)
                self.assertEqual(self.config_path.read_text(encoding="utf-8"), configuration)

    def test_equation_long_wide_input_scrolls_and_f7_closes_other_overlays(self):
        self.app.handle_key("F6")
        self.app.handle_key("ENTER")
        self.app.handle_key("F7")
        self.assertFalse(self.app.help_open)
        self.assertIsNone(self.app.open_menu)
        self.type_keys("数" * 100)
        lines, _, cursor = self.app.frame(40, 12)
        self.assertLessEqual(cursor[1], 40)
        self.assertTrue(all(display_width(line) <= 40 for line in lines))
        self.app.handle_key("F1")
        self.assertFalse(self.app.equation_open)
        self.assertEqual(self.app.open_menu, 0)

    def test_equation_checkmarks_toggle_and_stay_unchecked_when_browsing(self):
        self.app.handle_key("F7")
        self.type_keys("4x")
        self.app.handle_key("ENTER")
        self.app.handle_key("UP")
        self.app.handle_key("CTRL_T")
        lines, _, _ = self.app.frame()
        self.assertIn("> [ ] y1=4x", lines)
        self.assertEqual(lines[-3], "y1(x)=4x")
        self.app.handle_key("DOWN")
        self.app.handle_key("UP")
        self.app.handle_key("F8")
        self.assertFalse(self.app.equation_open)
        self.assertTrue(self.app.table_open)
        self.assertEqual(self.app.table_equation_names(), [])
        self.assertEqual(self.app.calculator.calculate("y1(3)"), "12")
        self.app.handle_key("F7")
        self.app.handle_key("CTRL_T")
        self.assertEqual(self.app.table_equation_names(), ["y1"])
        self.app.handle_key("CTRL_T")
        self.type_keys("+1")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.table_equation_names(), ["y1"])
        self.app.handle_key("UP")
        self.app.handle_key("CTRL_U")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.table_equation_names(), [])
        self.assertNotIn("y1", self.app.calculator.unchecked_equations)
        self.app.handle_key("CTRL_T")
        self.assertFalse(self.app.calculator.unchecked_equations)

    def test_table_displays_checked_equations_without_changing_calculator_state(self):
        self.app.calculator.define_equation("y1", "4x")
        self.app.calculator.define_equation("y2", "x^2")
        self.app.calculator.define_equation("y3", "x+99")
        self.app.calculator.unchecked_equations.add("y3")
        self.app.calculator.calculate("7->x")
        before = list(self.app.calculator.history)
        self.type_keys("y1(3)+")
        self.app.handle_key("F8")
        lines, selected, cursor = self.app.frame()
        self.assertEqual([cell.strip() for cell in lines[2].split("|")], ["x", "y1", "y2"])
        self.assertEqual([cell.strip() for cell in lines[7].split("|")], ["3", "12", "9"])
        self.assertFalse(selected)
        self.assertIsNone(cursor)
        self.assertEqual(self.app.calculator.answer.value, 7)
        self.assertEqual(self.app.calculator.variables["x"].value, 7)
        self.assertEqual(list(self.app.calculator.history), before)
        self.app.handle_key("F8")
        self.assertEqual(self.app.text, "y1(3)+")
        self.assertEqual(self.app.cursor, 6)

    def test_table_setup_accepts_exact_start_and_negative_step(self):
        self.app.calculator.define_equation("y1", "4x")
        self.app.handle_key("F8")
        self.app.handle_key("TAB")
        self.app.handle_key("CTRL_U")
        self.type_keys("3")
        self.app.handle_key("TAB")
        self.app.handle_key("CTRL_U")
        self.type_keys("-1/2")
        lines, _, cursor = self.app.frame()
        self.assertEqual(lines[-3], "Step=-1/2")
        self.assertIsNotNone(cursor)
        self.app.handle_key("ENTER")
        self.assertEqual((self.app.table_start, self.app.table_step), ("3", "-1/2"))
        lines, _, cursor = self.app.frame()
        self.assertEqual([cell.strip() for cell in lines[4].split("|")], ["3", "12"])
        self.assertEqual([cell.strip() for cell in lines[5].split("|")], ["5/2", "10"])
        self.assertIsNone(cursor)
        self.app.handle_key("DOWN")
        lines, _, _ = self.app.frame()
        self.assertEqual(lines[4].split("|")[0].strip(), "5/2")
        self.app.handle_key("HOME")
        self.assertEqual(self.app.table_row, 0)

    def test_invalid_table_setup_stays_editable_and_can_be_canceled(self):
        self.app.handle_key("F8")
        self.app.handle_key("TAB")
        self.app.handle_key("TAB")
        self.app.handle_key("CTRL_U")
        self.type_keys("0")
        for key in ("ENTER", "F8", "F7", "F1", "F9"):
            self.app.handle_key(key)
            self.assertTrue(self.app.table_open)
            self.assertEqual(self.app.table_edit_field, 1)
            self.assertIn("step cannot be zero", self.app.message)
            self.assertEqual(self.app.table_step, "1")
        self.app.handle_key("ESC")
        self.assertTrue(self.app.table_open)
        self.assertIsNone(self.app.table_edit_field)
        self.app.handle_key("ESC")
        self.assertFalse(self.app.table_open)
        for bad_start, bad_step in (("t", "1"), ("True", "1"), ("1_m", "1"),
                                    ("i", "1"), ("1/0", "1"), ("0", "x")):
            with self.subTest(start=bad_start, step=bad_step), self.assertRaises(CalcError):
                self.app.validate_table_settings(self.app.calculator, bad_start, bad_step)

    def test_table_errors_are_per_cell_and_empty_table_explains_checkmarks(self):
        self.app.handle_key("F8")
        lines, _, _ = self.app.frame()
        self.assertIn("Check equations in F7", lines[4])
        self.app.calculator.define_equation("y1", "1/x")
        self.app.calculator.define_equation("y2", "4x")
        self.app.calculator.define_equation("y3", "y99(x)")
        lines, _, _ = self.app.frame()
        self.assertEqual([cell.strip() for cell in lines[4].split("|")], ["0", "Error", "0", "Error"])
        self.assertEqual([cell.strip() for cell in lines[5].split("|")], ["1", "1", "4", "Error"])
        self.assertFalse(self.app.calculator.history)

    def test_table_scrolls_to_all_99_equations_and_resizes(self):
        for i in range(1, 100):
            self.app.calculator.define_equation(f"y{i}", f"{i}x")
        self.app.handle_key("F8")
        for _ in range(100):
            self.app.handle_key("RIGHT")
        for width, height in ((40, 12), (100, 24), (160, 40)):
            lines, _, cursor = self.app.frame(width, height)
            self.assertIn("y99", lines[2])
            self.assertEqual(len(lines), height)
            self.assertTrue(all(display_width(line) <= width for line in lines))
            self.assertIsNone(cursor)
        self.app.handle_key("PAGEDOWN")
        self.assertGreater(self.app.table_row, 0)
        self.app.handle_key("PAGEUP")
        self.assertEqual(self.app.table_row, 0)
        self.app.handle_key("HOME")
        self.assertEqual(self.app.table_column, 0)

    def test_table_settings_and_unchecked_equations_persist_and_old_configs_default_checked(self):
        self.app.calculator.define_equation("y1", "4x")
        self.app.calculator.define_equation("y2", "y1(x)+1")
        self.app.calculator.unchecked_equations.add("y1")
        self.app.table_start, self.app.table_step = "3", "1/3"
        self.app.command(":save")
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(restored.table_equation_names(), ["y2"])
        self.assertEqual((restored.table_start, restored.table_step), ("3", "1/3"))
        restored.handle_key("F8")
        lines, _, _ = restored.frame()
        self.assertEqual([cell.strip() for cell in lines[4].split("|")], ["3", "13"])
        legacy_config = self.config_path.with_name("legacy.json")
        legacy_config.write_text(json.dumps({"equations": {"y1": "4x"}}), encoding="utf-8")
        restored = ConsoleApp(config_path=legacy_config)
        self.assertEqual(restored.table_equation_names(), ["y1"])
        self.assertEqual((restored.table_start, restored.table_step), ("0", "1"))

    def test_bad_table_configuration_loads_atomically_and_preserves_file(self):
        for extra in ({"unchecked_equations": "y1"}, {"unchecked_equations": ["y99"]},
                      {"table": []}, {"table": {"step": "0"}}, {"table": {"start": 3}}):
            configuration = json.dumps({"equations": {"y1": "4x"}, **extra})
            with self.subTest(extra=extra):
                self.config_path.write_text(configuration, encoding="utf-8")
                restored = ConsoleApp(config_path=self.config_path)
                self.assertIn("Config error:", restored.message)
                self.assertFalse(restored.calculator.equations)
                self.assertEqual(self.config_path.read_text(encoding="utf-8"), configuration)

    def test_invalid_equation_blocks_opening_table(self):
        self.app.handle_key("F7")
        self.type_keys("4x+")
        self.app.handle_key("F8")
        self.assertTrue(self.app.equation_open)
        self.assertFalse(self.app.table_open)
        self.assertIn("Error:", self.app.message)

    def test_recent_calculations_and_browsing_older_entries(self):
        for i in range(10):
            self.app.calculator.evaluate(str(i))
        lines, _, _ = self.app.frame(height=12)
        self.assertEqual(sum(" = " in line for line in lines[2:-4]), 6)
        self.assertIn("4 = 4", lines[2])
        self.app.handle_key("UP")
        for _ in range(16):
            self.app.handle_key("UP")
        lines, selected, cursor = self.app.frame(height=12)
        self.assertEqual(self.app.history_index, 1)
        self.assertIn("1 = 1", lines[2])
        self.assertIn(2, selected)
        self.assertIsNone(cursor)
        self.app.handle_key("ESC")
        self.assertIsNone(self.app.history_index)

    def test_history_fills_terminal_and_footer_stays_at_bottom(self):
        for i in range(30):
            self.app.calculator.evaluate(str(i))
        self.type_keys("2+3")
        for height in (12, 24, 40, 16):
            with self.subTest(height=height):
                lines, selected, cursor = self.app.frame(height=height)
                count = min(30, height - 6)
                self.assertEqual(len(lines), height)
                self.assertEqual(sum(" = " in line for line in lines[2:-4]), count)
                self.assertIn(f"{30 - count} = {30 - count}", lines[2])
                self.assertEqual(lines[-4], "-" * 100)
                self.assertEqual(lines[-3], "> 2+3")
                self.assertIn(f"history 30/{max(30, height - 6)}", lines[-2])
                self.assertEqual(lines[-1], self.app.message)
                self.assertEqual(cursor, (height - 2, 6))
                self.assertFalse(selected)

    def test_history_limit_expands_to_visible_rows_and_caps_entries(self):
        self.app.frame(height=50)
        for i in range(50):
            self.app.calculator.evaluate(str(i))
        history = self.app.calculator.history
        self.assertEqual(history.maxlen, 44)
        self.assertEqual(len(history), 44)
        self.assertEqual(history[0].source, "6")
        self.assertEqual(history[-1].source, "49")
        lines, _, _ = self.app.frame(height=50)
        self.assertEqual(sum(" = " in line for line in lines[2:-4]), 44)
        self.assertIn("history 44/44", lines[-2])

    def test_history_limit_shrinks_and_keeps_selected_entry(self):
        self.app.frame(height=50)
        for i in range(50):
            self.app.calculator.evaluate(f"{i}+1")
        self.app.text, self.app.cursor = "()+2", 1
        self.app.handle_key("UP")
        for _ in range(47):
            self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(height=50), "26+1")
        self.assertEqual(self.highlighted_text(height=41), "26+1")
        history = self.app.calculator.history
        self.assertEqual(history.maxlen, 35)
        self.assertEqual(len(history), 35)
        self.assertEqual(history[0].source, "15+1")
        self.assertEqual(self.app.history_index, 11)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "(26+1)+2")

    def test_history_limit_minimum_and_discarded_selection(self):
        self.app.frame(height=50)
        for i in range(50):
            self.app.calculator.evaluate(str(i))
        self.app.text, self.app.cursor = "2+3", 1
        self.app.history_index = 0
        lines, selected, cursor = self.app.frame(height=24)
        self.assertEqual(self.app.calculator.history.maxlen, 30)
        self.assertEqual(len(self.app.calculator.history), 30)
        self.assertEqual(self.app.calculator.history[0].source, "20")
        self.assertIn("history 30/30", lines[-2])
        self.assertIsNone(self.app.history_index)
        self.assertFalse(selected)
        self.assertEqual(cursor, (22, 4))
        for height in (12, 6):
            self.app.frame(height=height)
            self.assertEqual(self.app.calculator.history.maxlen, 30)
            self.assertEqual(len(self.app.calculator.history), 30)

    def test_growing_history_limit_preserves_existing_entries(self):
        for i in range(35):
            self.app.calculator.evaluate(str(i))
        before = list(self.app.calculator.history)
        self.app.handle_key("UP")
        lines, _, _ = self.app.frame(height=50)
        self.assertEqual(list(self.app.calculator.history), before)
        self.assertEqual(self.app.history_index, 29)
        self.assertIn("history 30/44", lines[-2])
        for i in range(35, 45):
            self.app.calculator.evaluate(str(i))
        self.assertEqual(len(self.app.calculator.history), 40)
        self.assertEqual(self.app.calculator.history[0].source, "5")

    def test_resize_preserves_selected_part_and_input_cursor(self):
        for i in range(30):
            self.app.calculator.evaluate(f"{i}+1")
        self.app.text, self.app.cursor = "()+2", 1
        self.app.frame(height=24)
        self.app.handle_key("UP")
        for _ in range(43):
            self.app.handle_key("UP")
        self.assertEqual(self.app.history_index, 8)
        for height in (24, 12, 40, 16):
            with self.subTest(height=height):
                self.assertEqual(self.highlighted_text(height=height), "8+1")
                self.assertEqual(self.app.history_index, 8)
                self.assertEqual(self.app.cursor, 1)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "(8+1)+2")
        self.assertEqual(self.app.cursor, 4)

    def test_consecutive_up_selects_result_then_expression(self):
        self.app.calculator.evaluate("5+3")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "8")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "5+3")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "5+3")
        self.app.handle_key("DOWN")
        self.assertEqual(self.highlighted_text(), "8")
        self.app.handle_key("DOWN")
        self.assertIsNone(self.app.history_index)
        _, selected, cursor = self.app.frame()
        self.assertFalse(selected)
        self.assertIsNotNone(cursor)

    def test_history_parts_follow_order_across_entries(self):
        self.app.calculator.evaluate("1+2")
        self.app.calculator.evaluate("5+3")
        self.type_keys("()+1")
        self.app.handle_key("LEFT")
        initial_cursor = self.app.cursor
        for expected in ["8", "5+3", "3", "1+2"]:
            self.app.handle_key("UP")
            self.assertEqual(self.highlighted_text(), expected)
        for expected in ["3", "5+3", "8"]:
            self.app.handle_key("DOWN")
            self.assertEqual(self.highlighted_text(), expected)
        self.assertEqual(self.app.text, "()+1")
        self.assertEqual(self.app.cursor, initial_cursor)

    def test_selected_expression_inserts_at_input_cursor(self):
        self.app.calculator.evaluate("5+3")
        self.app.text, self.app.cursor = "()+1", 1
        self.app.handle_key("UP")
        self.app.handle_key("UP")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "(5+3)+1")
        self.assertEqual(self.app.cursor, 4)
        self.assertIsNone(self.app.history_index)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.history[-1].result, "9")

    def test_grouped_input_is_cleaned_in_history_and_expression_recall(self):
        self.type_keys("1_000+2_500")
        self.assertEqual(self.app.text, "1_000+2_500")
        self.app.handle_key("ENTER")
        lines, _, _ = self.app.frame()
        self.assertIn("1000+2500 = 3500", "\n".join(lines[2:5]))
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "3500")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "1000+2500")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "1000+2500")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.history[-1].result, "3500")

    def test_base_literals_are_decimal_in_history_and_recall(self):
        self.type_keys("0h3FA2+0o10")
        self.assertEqual(self.app.text, "0h3FA2+0o10")
        self.app.handle_key("ENTER")
        lines, _, _ = self.app.frame()
        self.assertIn("16290+8 = 16298", "\n".join(lines[2:5]))
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "16298")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "16290+8")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "16290+8")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.history[-1].result, "16298")

    def test_selected_result_after_long_expression_scrolls_into_view(self):
        self.app.calculator.evaluate("+".join(["1"] * 100))
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(width=40), "100")
        lines, _, _ = self.app.frame(width=40)
        self.assertTrue(all(display_width(line) <= 40 for line in lines))
        self.app.handle_key("UP")
        self.assertTrue(self.highlighted_text(width=40).startswith("1+1+1"))

    def test_unicode_expression_and_unit_result_highlight_separately(self):
        self.app.calculator.evaluate("3->ε")
        self.app.handle_key("UP")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "3->ε")
        self.app.handle_key("ESC")
        self.app.calculator.evaluate("3_in=>_ft")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "1/4_ft")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "3_in=>_ft")

    def test_page_navigation_preserves_selected_part(self):
        for i in range(10):
            self.app.calculator.evaluate(f"{i}+1")
        self.app.frame(height=12)
        self.app.handle_key("UP")
        self.app.handle_key("UP")
        self.app.handle_key("PAGEUP")
        self.assertEqual(self.app.history_index, 3)
        self.assertEqual(self.highlighted_text(height=12), "3+1")
        self.app.handle_key("PAGEDOWN")
        self.assertEqual(self.app.history_index, 9)
        self.assertEqual(self.highlighted_text(height=12), "9+1")

    def test_page_navigation_uses_resized_history_capacity(self):
        for i in range(30):
            self.app.calculator.evaluate(str(i))
        self.app.frame(height=24)
        self.app.handle_key("UP")
        self.app.handle_key("PAGEUP")
        self.assertEqual(self.app.history_index, 11)
        self.assertEqual(self.highlighted_text(height=12), "11")
        self.app.handle_key("PAGEUP")
        self.assertEqual(self.app.history_index, 5)
        self.assertEqual(self.highlighted_text(height=12), "5")

    def test_preferred_first_selection_still_allows_both_parts(self):
        self.app.command(":recall expression")
        self.app.calculator.evaluate("5+3")
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(), "5+3")
        self.app.handle_key("DOWN")
        self.assertEqual(self.highlighted_text(), "8")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "8")

    def test_insert_history_at_current_cursor(self):
        self.app.calculator.evaluate("3*4")
        self.type_keys("1++2")
        self.app.handle_key("LEFT")
        self.app.handle_key("LEFT")
        self.app.handle_key("UP")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "1+12+2")
        self.assertEqual(self.app.cursor, 4)
        self.assertIsNone(self.app.history_index)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.history[-1].result, "15")

    def test_composite_recall_preserves_precedence_and_unit(self):
        self.app.calculator.evaluate("3_in=>_ft")
        self.type_keys("4*")
        self.app.handle_key("UP")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "4*(1/4_ft)")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.history[-1].result, "1_ft")

    def test_configurable_expression_recall(self):
        self.app.command(":recall expression")
        self.app.calculator.evaluate("3*4")
        self.app.text, self.app.cursor = "()+1", 1
        self.app.handle_key("UP")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "(3*4)+1")

    def test_history_navigation_bounds_and_tab(self):
        self.app.handle_key("UP")
        self.assertIsNone(self.app.history_index)
        for i in range(3):
            self.app.calculator.evaluate(str(i))
        self.app.handle_key("TAB")
        self.assertEqual(self.app.history_index, 2)
        self.app.handle_key("PAGEUP")
        self.assertEqual(self.app.history_index, 0)
        self.app.handle_key("UP")
        self.assertEqual(self.app.history_index, 0)
        self.app.handle_key("PAGEDOWN")
        self.assertIsNone(self.app.history_index)

    def test_editing_keys(self):
        self.type_keys("1234")
        self.app.handle_key("HOME")
        self.app.handle_key("DELETE")
        self.app.handle_key("END")
        self.app.handle_key("BACKSPACE")
        self.assertEqual(self.app.text, "23")
        self.app.handle_key("LEFT")
        self.type_keys("+")
        self.assertEqual(self.app.text, "2+3")
        self.app.handle_key("CTRL_U")
        self.assertEqual(self.app.text, "")
        self.assertEqual(self.app.cursor, 0)

    def test_symbols_menu_inserts_unicode_at_cursor(self):
        self.type_keys("1+")
        self.app.handle_key("F4")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "1+ε")
        self.assertIsNone(self.app.open_menu)

    def test_all_six_menus_open_and_toggle(self):
        for i in range(6):
            self.app.handle_key("F" + str(i+1))
            self.assertEqual(self.app.open_menu, i)
            self.app.handle_key("F" + str(i+1))
            self.assertIsNone(self.app.open_menu)

    def test_cleanup_clears_set_variables_and_preserves_equations_history_and_ans(self):
        self.app.calculator.calculate("3->x")
        self.app.calculator.calculate("4->X")
        self.app.calculator.define_equation("y1", "4x")
        history = list(self.app.calculator.history)
        self.app.text, self.app.cursor = "2+", 2
        self.app.handle_key("F9")
        lines, selected, cursor = self.app.frame()
        self.assertIn("F9 Clean Up", lines[0])
        self.assertIn("Clear set variables", lines[next(iter(selected))])
        self.assertIsNone(cursor)
        self.app.handle_key("ENTER")
        self.assertFalse(self.app.calculator.variables)
        self.assertEqual(self.app.calculator.equations, {"y1": "4x"})
        self.assertEqual(list(self.app.calculator.history), history)
        self.assertEqual(self.app.calculator.answer.value, 4)
        self.assertEqual((self.app.text, self.app.cursor), ("2+", 2))
        self.assertEqual(self.app.calculator.calculate("x+X"), "X + x")

    def test_cleanup_clears_history_and_preserves_set_variables_and_equations(self):
        self.app.calculator.calculate("3->x")
        self.app.calculator.define_equation("y1", "4x")
        self.app.handle_key("F9")
        self.app.handle_key("DOWN")
        self.app.handle_key("ENTER")
        self.assertFalse(self.app.calculator.history)
        self.assertEqual(self.app.calculator.variables["x"].value, 3)
        self.assertEqual(self.app.calculator.answer.value, 3)
        self.assertEqual(self.app.calculator.equations, {"y1": "4x"})
        self.assertFalse(ConsoleApp(config_path=self.config_path).calculator.history)

    def test_cleanup_menu_toggles_and_participates_in_dropdown_navigation(self):
        self.app.handle_key("F9")
        self.app.handle_key("F9")
        self.assertIsNone(self.app.open_menu)
        self.app.handle_key("F6")
        self.app.handle_key("RIGHT")
        self.assertEqual(self.app.menu_root()["label"], "Clean Up")
        self.app.handle_key("RIGHT")
        self.assertEqual(self.app.open_menu, 0)
        self.app.handle_key("LEFT")
        self.assertEqual(self.app.menu_root()["label"], "Clean Up")
        for width in (40, 80, 100):
            lines, _, cursor = self.app.frame(width, 12)
            self.assertIn("F9", lines[0])
            self.assertTrue(all(display_width(line) <= width for line in lines))
            self.assertIsNone(cursor)
        self.app.handle_key("ESC")
        self.assertIsNone(self.app.open_menu)

    def test_saved_options_history_action_moves_to_cleanup_and_keeps_other_items(self):
        self.app.menus[4]["items"].append({"label": "Clear history", "command": ":clear"})
        self.app.menus[4]["items"].append({"label": "Custom option", "insert": "123"})
        document = json.dumps({"menus": self.app.menus})
        self.config_path.write_text(document, encoding="utf-8")
        restored = ConsoleApp(config_path=self.config_path)
        self.assertFalse(any(item.get("command") == ":clear" for item in restored.menus[4]["items"]))
        self.assertIn("Custom option", [item["label"] for item in restored.menus[4]["items"]])
        self.assertEqual(restored.config_path.read_text(encoding="utf-8"), document)
        restored.handle_key("F9")
        self.assertEqual([item["label"] for item in restored.menu_items()],
                         ["Clear set variables", "Clear history"])
        restored.save_config()
        self.assertEqual(len(json.loads(restored.config_path.read_text(encoding="utf-8"))["menus"]), 6)

    def test_filter_units_and_insert(self):
        self.app.handle_key("F2")
        self.type_keys("nautical")
        self.assertEqual(len(self.app.menu_items()), 1)
        self.app.handle_key("ENTER")
        self.assertEqual(len(self.app.menu_items()), 1)
        self.assertEqual(self.app.menu_items()[0]["insert"], "_Nmi")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "_Nmi")

    def test_units_menu_categories_contain_all_units(self):
        self.app.handle_key("F2")
        categories = {item["label"]: item["items"] for item in self.app.menu_items() if "items" in item}
        units = [unit for unit in self.app.calculator.registry.units.values() if not unit.constant]
        self.assertEqual(set(categories), {unit.category for unit in units})
        for category, items in categories.items():
            with self.subTest(category=category):
                self.assertEqual({item["insert"] for item in items},
                                 {unit.notation for unit in units if unit.category == category})
        self.assertEqual(self.app.menu_items()[-1]["label"], "Define a unit")
        self.app.handle_key("F3")
        self.assertTrue(all("insert" in item for item in self.app.menu_items()))

    def test_category_opens_with_right_and_inserts_at_cursor(self):
        self.app.text, self.app.cursor = "()+1", 1
        self.app.handle_key("F2")
        self.type_keys("LENGTH")
        self.app.handle_key("RIGHT")
        self.assertEqual(self.app.open_menu, 1)
        self.assertEqual(len(self.app.menu_stack), 1)
        self.assertEqual(self.app.menu_filter, "")
        self.type_keys("foot")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "(_ft)+1")
        self.assertEqual(self.app.cursor, 4)
        self.assertIsNone(self.app.open_menu)
        self.assertFalse(self.app.menu_stack)

    def test_right_from_unit_submenu_switches_to_constants(self):
        self.app.text, self.app.cursor = "()+1", 1
        for unit_filter in ("foot", "xxxxx"):
            with self.subTest(unit_filter=unit_filter):
                self.app.handle_key("F2")
                self.type_keys("length")
                self.app.handle_key("ENTER")
                self.type_keys(unit_filter)
                self.assertEqual(len(self.app.menu_stack), 1)
                self.assertEqual(bool(self.app.menu_items()), unit_filter == "foot")
                self.app.handle_key("RIGHT")
                self.assertEqual(self.app.open_menu, 2)
                self.assertFalse(self.app.menu_stack)
                self.assertEqual(self.app.menu_filter, "")
                self.assertEqual(self.app.menu_index, 0)
                self.assertEqual(self.app.menu_items(), self.app.menus[2]["items"])
                self.assertEqual(self.app.text, "()+1")
                self.assertEqual(self.app.cursor, 1)

    def test_submenu_back_restores_parent_selection_and_filter(self):
        self.app.handle_key("F2")
        self.type_keys("length")
        self.app.handle_key("ENTER")
        self.app.handle_key("DOWN")
        self.type_keys("foot")
        self.app.handle_key("LEFT")
        self.assertFalse(self.app.menu_stack)
        self.assertEqual(self.app.open_menu, 1)
        self.assertEqual(self.app.menu_filter, "length")
        self.assertEqual(self.app.menu_index, 0)
        self.app.handle_key("ENTER")
        self.app.handle_key("ESC")
        self.assertEqual(self.app.open_menu, 1)
        self.app.handle_key("ESC")
        self.assertIsNone(self.app.open_menu)

    def test_submenu_paging_and_function_keys_reset_navigation(self):
        self.app.handle_key("F2")
        self.type_keys("length")
        self.app.handle_key("ENTER")
        self.app.handle_key("PAGEDOWN")
        self.assertEqual(self.app.menu_index, 8)
        self.app.handle_key("END")
        self.assertEqual(self.app.menu_index, len(self.app.menu_items()) - 1)
        self.app.handle_key("HOME")
        self.assertEqual(self.app.menu_index, 0)
        self.app.handle_key("F4")
        self.assertFalse(self.app.menu_stack)
        self.assertEqual(self.app.menu_filter, "")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "ε")

    def test_submenu_empty_filter_can_be_edited_and_closed(self):
        self.app.handle_key("F2")
        self.app.handle_key("ENTER")
        self.type_keys("xxxxx")
        self.assertFalse(self.app.menu_items())
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "")
        self.assertEqual(len(self.app.menu_stack), 1)
        lines, selected, _ = self.app.frame()
        self.assertIn("no matching items", "\n".join(lines))
        self.assertFalse(selected)
        self.app.handle_key("BACKSPACE")
        self.assertEqual(self.app.menu_filter, "xxxx")
        self.app.handle_key("ESC")
        self.assertFalse(self.app.menu_stack)
        self.assertEqual(self.app.open_menu, 1)

    def test_custom_units_appear_in_custom_submenu_after_save(self):
        self.app.command(":unit smoot = 1.7018_m")
        self.app.command(":unit doubleSmoot = 2_smoot")
        self.app.save_config()
        restored = ConsoleApp(config_path=self.config_path)
        restored.handle_key("F2")
        for char in "custom":
            restored.handle_key(char)
        restored.handle_key("ENTER")
        self.assertEqual({item["insert"] for item in restored.menu_items()}, {"_smoot", "_doubleSmoot"})
        restored.handle_key("ENTER")
        self.assertEqual(restored.text, "_smoot")

    def test_legacy_flat_units_configuration_is_grouped(self):
        menus = self.app.menus
        menus[1]["items"] = [{"label": "Length: _in inch", "insert": "_in"},
                             {"label": "Length: _ft foot", "insert": "_ft"},
                             {"label": "Favorite calculation", "insert": "3_in=>_ft"}]
        configuration = json.dumps({"menus": menus})
        self.config_path.write_text(configuration, encoding="utf-8")
        restored = ConsoleApp(config_path=self.config_path)
        restored.handle_key("F2")
        items = restored.menu_items()
        self.assertEqual(items[0]["label"], "Length")
        self.assertEqual(items[0]["items"], [{"label": "_in inch", "insert": "_in"},
                                             {"label": "_ft foot", "insert": "_ft"}])
        self.assertEqual(items[1]["label"], "Favorite calculation")
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), configuration)

    def test_nested_menu_configuration_and_commands(self):
        self.app.menus[0]["items"] = [{"label": "Favorites", "items": [
            {"label": "Angles", "items": [{"label": "Degrees", "command": ":mode degree"}]}]}]
        self.app.save_config()
        restored = ConsoleApp(config_path=self.config_path)
        restored.handle_key("F1")
        restored.handle_key("RIGHT")
        restored.handle_key("ENTER")
        self.assertEqual(len(restored.menu_stack), 2)
        restored.handle_key("ENTER")
        self.assertEqual(restored.calculator.mode, "degree")
        self.assertIsNone(restored.open_menu)
        self.assertFalse(restored.menu_stack)

    def test_invalid_submenu_configuration_is_rejected(self):
        invalid = [{"label": "Bad", "items": "not a list"},
                   {"label": "Bad", "items": [], "insert": "1"},
                   {"label": "Bad", "items": [{"label": "Leaf"}]},
                   {"label": "Bad", "items": [{"label": "Leaf", "command": "quit"}]}]
        node = {"label": "Leaf", "insert": "1"}
        for _ in range(9):
            node = {"label": "Nested", "items": [node]}
        invalid.append(node)
        for item in invalid:
            with self.subTest(item=item):
                self.app.menus[0]["items"] = [item]
                with self.assertRaises(CalcError):
                    validate_menus(self.app.menus)

    def test_submenus_render_beside_parent_or_fit_small_terminal(self):
        self.app.handle_key("F2")
        self.type_keys("length")
        self.app.handle_key("ENTER")
        self.type_keys("foot")
        for width, height in ((120, 24), (80, 24), (40, 12)):
            with self.subTest(width=width, height=height):
                lines, selected, cursor = self.app.frame(width=width, height=height)
                self.assertTrue(all(display_width(line) <= width for line in lines))
                self.assertEqual(len(lines), height)
                self.assertIn("Units > Length", "\n".join(lines))
                self.assertEqual(len(selected), 1)
                row, (first, last) = next(iter(selected.items()))
                self.assertIn("_ft foot", lines[row][first:last])
                self.assertEqual(lines[-3], "> ")
                self.assertIsNone(cursor)
                if width == 120:
                    self.assertTrue(any("Length >" in line for line in lines))

    def test_empty_filtered_menu_and_backspace(self):
        self.app.handle_key("F4")
        self.type_keys("xxxx")
        self.app.handle_key("DOWN")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "")
        lines, _, _ = self.app.frame()
        self.assertIn("no matching", "\n".join(lines))
        self.app.handle_key("BACKSPACE")
        self.assertEqual(self.app.menu_filter, "xxx")
        self.app.handle_key("ESC")
        self.assertIsNone(self.app.open_menu)

    def test_menu_switching_paging_and_option(self):
        self.app.handle_key("F4")
        self.app.handle_key("RIGHT")
        self.app.handle_key("DOWN")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.mode, "degree")
        self.app.handle_key("F2")
        self.app.handle_key("PAGEDOWN")
        self.assertEqual(self.app.menu_index, 8)
        self.app.handle_key("END")
        self.assertEqual(self.app.menu_index, len(self.app.menu_items()) - 1)
        self.app.handle_key("HOME")
        self.assertEqual(self.app.menu_index, 0)

    def test_failed_input_is_kept_for_correction(self):
        self.type_keys("1/0")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "1/0")
        self.assertIn("Error:", self.app.message)
        self.assertEqual(self.app.calculator.history[-1].line, "1/0 = Error: Division by zero.")
        self.assertIn("1/0 = Error: Division by zero.", "\n".join(self.app.frame()[0]))

    def test_history_navigation_skips_error_messages_and_recalls_bad_input(self):
        for text in ("5+3", "0hG", "(1+", "2+2"):
            self.app.text, self.app.cursor = text, len(text)
            self.app.submit()
        expected = ["4", "2+2", "(1+", "0hG", "8", "5+3"]
        for part in expected:
            self.app.handle_key("UP")
            self.assertEqual(self.highlighted_text(), part)
        for part in reversed(expected[:-1]):
            self.app.handle_key("DOWN")
            self.assertEqual(self.highlighted_text(), part)
        self.app.handle_key("DOWN")
        self.assertIsNone(self.app.history_index)
        self.app.text, self.app.cursor = "", 0
        self.app.handle_key("UP")
        self.app.handle_key("UP")
        self.app.handle_key("UP")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "(1+")

    def test_error_recall_after_restart_and_page_navigation(self):
        for i in range(7):
            self.app.calculator.evaluate(str(i))
        self.app.text = "1/0"
        self.app.submit()
        self.app = ConsoleApp(config_path=self.config_path)
        self.app.text, self.app.cursor = "", 0
        self.app.frame(height=12)
        self.app.handle_key("UP")
        self.assertEqual(self.highlighted_text(height=12), "1/0")
        self.app.handle_key("PAGEUP")
        self.app.handle_key("DOWN")
        self.assertEqual(self.app.history_part, "result")
        self.app.handle_key("PAGEDOWN")
        self.assertEqual(self.highlighted_text(height=12), "1/0")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "1/0")

    def test_errors_and_commands_preserve_latest_ans(self):
        for text in ("1/3", "1/0", ":clear", ":mode degree", "ans*3"):
            self.app.text, self.app.cursor = text, len(text)
            self.app.submit()
        self.assertEqual(self.app.calculator.history[-1].line, "ans*3 = 1")
        self.assertEqual(self.app.calculator.answer.value, 1)

    def test_options_select_exact_and_approximate_output(self):
        for label, mode, expected in (("Approximate output", "approximate", "0.33333"),
                                      ("Exact output", "exact", "1/3")):
            self.app.handle_key("F5")
            self.type_keys(label)
            self.app.handle_key("ENTER")
            self.assertEqual(self.app.calculator.output_mode, mode)
            self.assertIsNone(self.app.open_menu)
            self.app.command(":precision 5")
            self.type_keys("1/3")
            self.app.handle_key("ENTER")
            self.assertEqual(self.app.calculator.history[-1].result, expected)
            lines, _, _ = self.app.frame()
            self.assertIn(f"| {mode} |", lines[-2])

    def test_output_mode_is_saved_and_restored_with_settings(self):
        self.app.command(":format approximate")
        self.app.command(":precision 12")
        self.app.command(":unit thirdmeter = 1/3_m")
        self.app.command(":save")
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(restored.calculator.output_mode, "approximate")
        self.assertEqual(restored.calculator.calculate("1/3"), "0.333333333333")
        self.assertEqual(restored.calculator.calculate("3_thirdmeter=>_m"), "1_m")
        restored.command(":format exact")
        restored.command(":save")
        self.assertEqual(ConsoleApp(config_path=self.config_path).calculator.output_mode, "exact")

    def test_older_settings_default_to_exact_and_gain_output_options(self):
        menus = self.app.menus
        menus[4]["items"] = [item for item in menus[4]["items"]
                             if not item.get("command", "").startswith(":format ")]
        self.config_path.write_text(json.dumps({"mode": "degree", "menus": menus}), encoding="utf-8")
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(restored.calculator.output_mode, "exact")
        restored.handle_key("F5")
        commands = [item.get("command") for item in restored.menu_items()]
        self.assertIn(":format exact", commands)
        self.assertIn(":format approximate", commands)

    def test_invalid_output_mode_settings_are_preserved(self):
        configuration = json.dumps({"mode": "degree", "output_mode": "invalid"})
        self.config_path.write_text(configuration, encoding="utf-8")
        restored = ConsoleApp(config_path=self.config_path)
        self.assertIn("Config error:", restored.message)
        self.assertEqual(restored.calculator.output_mode, "exact")
        self.assertEqual(restored.calculator.mode, "radian")
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), configuration)
        with self.assertRaises(CalcError):
            restored.command(":format invalid")

    def test_custom_menu_and_unit_configuration_roundtrip(self):
        for command in [":mode degree", ":precision 123", ":recall expression", ":unit smoot = 1.7018_m",
                        ":unit span = 2_smoot", ":menu 1 Favorites", ":menuclear 1",
                        ":menuadd 1 Epsilon | ε", ":menuadd 1 Radians | :mode radian", ":save"]:
            self.app.command(command)
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(restored.calculator.mode, "degree")
        self.assertEqual(restored.calculator.precision, 123)
        self.assertEqual(restored.history_insert, "expression")
        self.assertEqual(restored.menus, self.app.menus)
        self.assertEqual(restored.calculator.calculate("1_span=>_m"), "8509/2500_m")
        restored.handle_key("F1")
        restored.handle_key("ENTER")
        self.assertEqual(restored.text, "ε")
        restored.handle_key("F1")
        restored.handle_key("DOWN")
        restored.handle_key("ENTER")
        self.assertEqual(restored.calculator.mode, "radian")

    def test_config_unit_dependency_order(self):
        self.config_path.write_text(json.dumps({"units": {"double": "2_smoot", "smoot": "1.7018_m"}}), encoding="utf-8")
        restored = ConsoleApp(config_path=self.config_path)
        self.assertEqual(restored.calculator.calculate("1_double=>_smoot"), "2_smoot")

    def test_bad_config_is_preserved_and_loaded_atomically(self):
        configurations = ["not json", "[]", '{"mode":"degree","precision":1}',
                          '{"mode":"degree","menus":[]}', '{"mode":"degree","units":{"bad":"x_m"}}',
                          '{"units":{"a":"1_b","b":"1_a"}}', '{"history_insert":"invalid"}']
        for text in configurations:
            with self.subTest(config=text):
                self.config_path.write_text(text, encoding="utf-8")
                restored = ConsoleApp(config_path=self.config_path)
                self.assertIn("Config error:", restored.message)
                self.assertEqual(restored.calculator.mode, "radian")
                self.assertEqual(self.config_path.read_text(encoding="utf-8"), text)

    def test_menu_validation_and_command_errors(self):
        with self.assertRaises(CalcError):
            validate_menus([])
        menus = self.app.menus
        menus[0]["items"] = [{"label": "bad", "insert": "1", "command": ":quit"}]
        with self.assertRaises(CalcError):
            validate_menus(menus)
        for command in [":mode wrong", ":precision 1", ":recall wrong", ":unit bad", ":menu 7 Bad",
                        ":menu 1", ":menuadd 1 Bad", ":unset unknown", ":unknown"]:
            with self.subTest(command=command), self.assertRaises(CalcError):
                self.app.command(command)

    def test_status_full_history_and_long_input_cursor(self):
        for i in range(35):
            self.app.calculator.evaluate(str(i))
        self.type_keys("1" * 200)
        lines, _, cursor = self.app.frame(width=80)
        self.assertIn("history 30/30", lines[-2])
        assert cursor is not None
        self.assertLessEqual(cursor[1], 80)
        self.assertTrue(all(display_width(line) <= 80 for line in lines))

    def test_wide_unicode_input_and_small_terminal(self):
        self.type_keys("数" * 40)
        lines, _, cursor = self.app.frame(width=50)
        assert cursor is not None
        self.assertLessEqual(cursor[1], 50)
        self.assertTrue(all(display_width(line) <= 50 for line in lines))
        lines, _, _ = self.app.frame(width=20, height=6)
        self.assertTrue(all(display_width(line) <= 20 for line in lines))
        lines, _, _ = self.app.frame(width=40, height=12)
        for i in range(6):
            self.assertIn("F" + str(i+1), lines[0])

    def test_help_and_quit(self):
        self.app.handle_key("F6")
        self.app.handle_key("ENTER")
        self.assertTrue(self.app.help_open)
        lines, _, cursor = self.app.frame()
        self.assertIn("HELP", lines[2])
        self.assertIsNone(cursor)
        self.app.handle_key("ESC")
        self.assertFalse(self.app.help_open)
        self.app.handle_key("CTRL_C")
        self.assertFalse(self.app.running)

    def test_render_outputs_ansi_and_highlight(self):
        self.app.calculator.evaluate("3")
        self.app.handle_key("UP")
        with patch("sys.stdout", new_callable=io.StringIO) as stdout, patch("shutil.get_terminal_size", return_value=(80, 24)):
            Terminal().render(self.app)
            output = stdout.getvalue()
        self.assertIn("3 = \x1b[7m3\x1b[0m", output)
        self.assertIn("history 1/30", output)

    def test_renderer_highlights_only_the_selected_expression(self):
        self.app.calculator.evaluate("5+3")
        self.app.handle_key("UP")
        self.app.handle_key("UP")
        with patch("sys.stdout", new_callable=io.StringIO) as stdout, patch("shutil.get_terminal_size", return_value=(80, 24)):
            Terminal().render(self.app)
            output = stdout.getvalue()
        self.assertIn("\x1b[7m5+3\x1b[0m = 8", output)

    def test_idle_resize_redraws_without_a_keypress(self):
        terminal = Terminal()
        with patch("sys.stdout", new_callable=io.StringIO), \
                patch("shutil.get_terminal_size", side_effect=[(80, 24), (80, 40), (80, 40)]), \
                patch.object(terminal, "read_key", side_effect=[None, "CTRL_C"]), \
                patch.object(self.app, "frame", wraps=self.app.frame) as frame:
            terminal.run(self.app)
        self.assertEqual([call.args for call in frame.call_args_list], [(79, 24), (79, 40)])
        self.assertFalse(self.app.running)

    def test_idle_without_resize_does_not_redraw(self):
        terminal = Terminal()
        with patch("sys.stdout", new_callable=io.StringIO), \
                patch("shutil.get_terminal_size", return_value=(80, 24)), \
                patch.object(terminal, "read_key", side_effect=[None, "2", "CTRL_C"]), \
                patch.object(self.app, "frame", wraps=self.app.frame) as frame:
            terminal.run(self.app)
        self.assertEqual(frame.call_count, 2)  # Initial frame and the input edit.
        self.assertEqual(self.app.text, "2")

    def test_resize_to_small_terminal_clears_old_rows(self):
        terminal = Terminal()
        with patch("sys.stdout", new_callable=io.StringIO) as output, \
                patch("shutil.get_terminal_size", side_effect=[(80, 24), (20, 6)]):
            terminal.render(self.app)
            output.seek(0)
            output.truncate()
            terminal.render(self.app)
            self.assertIn("\x1b[2J", output.getvalue())
            self.assertIn("Please resize", output.getvalue())

    def test_windows_key_timeout_leaves_input_unread(self):
        keyboard = Mock()
        keyboard.kbhit.return_value = False
        with patch("os.name", "nt"), patch.dict("sys.modules", {"msvcrt": keyboard}):
            self.assertIsNone(Terminal().read_key(timeout=0))
            keyboard.getwch.assert_not_called()

    def test_windows_equation_and_table_shortcuts(self):
        for code, expected in ((["\x00", "A"], "F7"), (["\x00", "B"], "F8"),
                               (["\x00", "C"], "F9"), (["\x14"], "CTRL_T")):
            with self.subTest(expected=expected):
                keyboard = Mock()
                keyboard.getwch.side_effect = code
                with patch("os.name", "nt"), patch.dict("sys.modules", {"msvcrt": keyboard}):
                    self.assertEqual(Terminal().read_key(), expected)

    def test_posix_equation_and_table_shortcuts(self):
        for code, expected in ((b"\x1b[18~", "F7"), (b"\x1b[19~", "F8"),
                               (b"\x1b[20~", "F9"), (b"\x14", "CTRL_T")):
            with self.subTest(expected=expected), patch("os.name", "posix"), patch("sys.stdin") as stdin, \
                    patch("select.select", return_value=([0], [], [])), \
                    patch("os.read", side_effect=[bytes([byte]) for byte in code]):
                stdin.fileno.return_value = 0
                self.assertEqual(Terminal().read_key(), expected)

    def test_posix_key_timeout_leaves_input_unread(self):
        with patch("os.name", "posix"), patch("select.select", return_value=([], [], [])), \
                patch("os.read") as read:
            self.assertIsNone(Terminal().read_key(timeout=0))
            read.assert_not_called()


class CommandLineTests(unittest.TestCase):
    def test_plain_and_eval_use_saved_output_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.json"
            text = ":format approximate\n:precision 12\n1/3\n:save\n:quit\n"
            with patch("sys.stdin", io.StringIO(text)), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(["--config", str(config), "--plain"]), 0)
                self.assertIn("1/3 = 0.333333333333", output.getvalue())
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(["--config", str(config), "--eval", "sqrt(2)"]), 0)
                self.assertIn("sqrt(2) = 1.41421356237", output.getvalue())

    def test_eval_and_plain_modes_share_history_across_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.json"
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["--config", str(config), "--eval", "3->x", "--eval", "4*x"]), 0)
            restored = ConsoleApp(config_path=config)
            self.assertEqual([entry.line for entry in restored.calculator.history], ["3->x = 3", "4*x = 12"])
            with patch("sys.stdin", io.StringIO("5+3\n")), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["--config", str(config), "--plain"]), 0)
            reopened = ConsoleApp(config_path=config)
            self.assertEqual([entry.line for entry in reopened.calculator.history],
                             ["3->x = 3", "4*x = 12", "5+3 = 8"])

    def test_keyboard_interrupt_saves_history_before_interactive_exit(self):
        def interrupted_run(app):
            app.calculator.evaluate("3+4")
            raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.json"
            with patch("sys.stdout", new_callable=io.StringIO), \
                    patch("sys.stdout.isatty", return_value=True), \
                    patch("sys.stdin.isatty", return_value=True), patch("calc_term.Terminal") as terminal:
                terminal.return_value.__enter__.return_value.run.side_effect = interrupted_run
                self.assertEqual(main(["--config", str(config)]), 0)
            restored = ConsoleApp(config_path=config)
            self.assertEqual(restored.calculator.history[-1].line, "3+4 = 7")

    def test_repeated_eval_with_assignment_and_conversion(self):
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdout", new_callable=io.StringIO) as output:
            status = main(["--config", str(Path(directory) / "missing.json"), "--eval", "3->x",
                           "--eval", "4*x", "--eval", "3_in=>_ft"])
            self.assertEqual(status, 0)
            self.assertIn("4*x = 12", output.getvalue())
            self.assertIn("3_in=>_ft = 1/4_ft", output.getvalue())

    def test_eval_reports_failure_with_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory, patch("sys.stderr", new_callable=io.StringIO) as error:
            status = main(["--config", str(Path(directory) / "missing.json"), "--eval", "1/0"])
            self.assertEqual(status, 1)
            self.assertIn("Division by zero", error.getvalue())

    def test_eval_saves_errors_and_keeps_ans_for_following_calculations(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.json"
            with patch("sys.stdout", new_callable=io.StringIO) as output, \
                    patch("sys.stderr", new_callable=io.StringIO) as error:
                status = main(["--config", str(config), "--eval", "1/3", "--eval", "1/0",
                               "--eval", "ans*3", "--eval", "0hG"])
            self.assertEqual(status, 1)
            self.assertIn("ans*3 = 1", output.getvalue())
            self.assertIn("Invalid digits", error.getvalue())
            restored = ConsoleApp(config_path=config)
            self.assertEqual([entry.is_error for entry in restored.calculator.history],
                             [False, True, False, True])
            self.assertEqual(restored.calculator.history[-1].source, "0hG")

    def test_plain_mode_saves_bad_input(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.json"
            with patch("sys.stdin", io.StringIO("1+\n1/3\n1/0\nans*3\n")), \
                    patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(["--config", str(config), "--plain"]), 0)
            self.assertIn("ans*3 = 1", output.getvalue())
            restored = ConsoleApp(config_path=config)
            self.assertEqual([entry.is_error for entry in restored.calculator.history],
                             [True, False, True, False])

    def test_plain_mode_processes_lines_and_commands(self):
        text = "3->x\n4*x\n:mode degree\nsin(30)\n:quit\n99\n"
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdin", io.StringIO(text)), patch("sys.stdout", new_callable=io.StringIO) as output:
            status = main(["--plain", "--config", str(Path(directory) / "missing.json")])
            self.assertEqual(status, 0)
            self.assertIn("4*x = 12", output.getvalue())
            self.assertIn("sin(30) = 1/2", output.getvalue())
            self.assertNotIn("99 =", output.getvalue())


if __name__ == "__main__":
    unittest.main()
