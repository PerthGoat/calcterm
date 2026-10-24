from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calc_term import CalcError, ConsoleApp, display_width


class EditingModeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "settings.json"
        self.app = ConsoleApp(config_path=self.config)

    def type_keys(self, text):
        for char in text:
            self.app.handle_key(char)

    def test_insert_key_toggles_overwrite_typing_and_typing_at_end_appends(self):
        self.assertFalse(self.app.insert_mode)
        self.type_keys("12345")
        self.app.handle_key("HOME")
        self.app.handle_key("RIGHT")
        self.app.handle_key("INSERT")
        self.type_keys("abc")
        self.assertEqual((self.app.text, self.app.cursor), ("1abc5", 4))
        self.app.handle_key("INSERT")
        self.type_keys("Z")
        self.assertEqual((self.app.text, self.app.cursor), ("1abcZ5", 5))
        self.app.handle_key("END")
        self.app.handle_key("INSERT")
        self.type_keys("67")
        self.assertEqual(self.app.text, "1abcZ567")
        self.assertFalse(self.app.calculator.history)

    def test_overwrite_mode_replaces_only_the_selection_when_text_is_selected(self):
        self.type_keys("12+345+6")
        self.app.handle_key("HOME")
        for _ in range(3):
            self.app.handle_key("RIGHT")
        for _ in range(3):
            self.app.handle_key("SHIFT_RIGHT")
        self.app.handle_key("INSERT")
        self.assertEqual(self.app.input_selection, (3, 6))
        self.type_keys("9")
        self.assertEqual((self.app.text, self.app.cursor), ("12+9+6", 4))
        self.app.handle_key("ENTER")
        self.type_keys("2")
        self.assertEqual(self.app.text, "2")

    def test_insert_indicator_occupies_a_fixed_slot_after_shift_in_every_view(self):
        self.app.shift_pressed = True
        for view in (None, "F7", "F8"):
            self.app.equation_open, self.app.table_open = False, False
            self.app.insert_mode = False
            if view:
                self.app.handle_key(view)
            for width in (40, 100):
                with self.subTest(view=view, width=width):
                    inactive = self.app.frame(width, 24)[0][-2]
                    self.assertTrue(inactive.startswith(" Default | ↑ |     | "))
                    self.app.handle_key("INSERT")
                    active = self.app.frame(width, 24)[0][-2]
                    self.assertTrue(active.startswith(" Default | ↑ | INS | "))
                    self.assertEqual(active.replace("INS", "   ", 1), inactive)
                    self.assertLessEqual(display_width(active), width)
                    self.app.handle_key("INSERT")

    def test_overwrite_mode_also_edits_equation_table_and_problem_name_fields(self):
        self.app.calculator.define_equation("y1", "123x")
        self.app.handle_key("F7")
        self.app.handle_key("HOME")
        self.app.handle_key("INSERT")
        self.type_keys("4")
        self.assertEqual(self.app.equation_text, "423x")
        self.app.handle_key("F8")
        self.app.handle_key("TAB")
        self.app.handle_key("HOME")
        self.type_keys("2")
        self.app.handle_key("TAB")
        self.app.handle_key("HOME")
        self.type_keys("3")
        self.app.handle_key("ENTER")
        self.assertEqual((self.app.table_start, self.app.table_step), ("2", "3"))
        self.app.begin_problem_dialog("new")
        self.type_keys("ABCD")
        self.app.handle_key("HOME")
        self.app.handle_key("RIGHT")
        self.type_keys("Z")
        self.assertEqual(self.app.problem_dialog_text, "AZCD")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.problem_name, "AZCD")
        self.assertTrue(self.app.insert_mode)

    def test_menu_insertions_preserve_surrounding_text_in_overwrite_mode(self):
        self.type_keys("123")
        self.app.handle_key("HOME")
        self.app.handle_key("RIGHT")
        self.app.handle_key("INSERT")
        self.app.handle_key("F4")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "1ε23")

    def test_backspace_deletes_whole_history_rows_and_preserves_pending_input(self):
        for source in ("1+1", "2+2", "3+3"):
            self.app.calculator.calculate(source)
        self.app.save_history()
        self.app.text, self.app.cursor = "99+1", 2
        self.app.history_index, self.app.history_part = 1, "result"
        self.app.handle_key("BACKSPACE")
        self.assertEqual([entry.source for entry in self.app.calculator.history], ["1+1", "3+3"])
        self.assertEqual((self.app.history_index, self.app.history_part), (1, "result"))
        self.assertEqual((self.app.text, self.app.cursor), ("99+1", 2))
        self.assertEqual(self.app.calculator.answer.value, 6)
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual([entry.source for entry in restored.calculator.history], ["1+1", "3+3"])
        self.app.history_index, self.app.history_part = 0, "expression"
        self.app.handle_key("BACKSPACE")
        self.app.handle_key("BACKSPACE")
        self.assertFalse(self.app.calculator.history)
        self.assertIsNone(self.app.history_index)
        self.assertEqual((self.app.text, self.app.cursor), ("99+1", 2))
        self.assertFalse(ConsoleApp(config_path=self.config).calculator.history)

    def test_history_deletion_selects_an_error_expression_without_undoing_variables(self):
        self.app.calculator.calculate("2->x")
        with self.assertRaises(CalcError):
            self.app.calculator.calculate("1/0")
        self.app.calculator.calculate("3+3")
        self.app.handle_key("UP")
        self.app.handle_key("BACKSPACE")
        self.assertEqual((self.app.history_index, self.app.history_part), (1, "expression"))
        self.app.handle_key("BACKSPACE")
        self.assertEqual([entry.source for entry in self.app.calculator.history], ["2->x"])
        self.assertEqual(self.app.calculator.variables["x"].value, 2)
        self.assertEqual(self.app.calculator.answer.value, 6)

    def test_history_deletion_affects_only_current_problem_and_retries_failed_saves(self):
        self.app.text = "1+1"
        self.app.submit()
        self.app.new_problem("Algebra")
        self.app.text = "2+2"
        self.app.submit()
        self.app.text = "3+3"
        self.app.submit()
        self.app.handle_key("UP")
        before = self.app.problems_path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Locked")):
            self.app.handle_key("BACKSPACE")
        self.assertIn("Problem save error:", self.app.message)
        self.assertEqual(self.app.problems_path.read_bytes(), before)
        self.assertEqual([entry.result for entry in self.app.calculator.history], ["4"])
        self.assertTrue(self.app.save_session())
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.problem_name, "Algebra")
        self.assertEqual([entry.result for entry in restored.calculator.history], ["4"])
        restored.open_problem("Default")
        self.assertEqual([entry.result for entry in restored.calculator.history], ["2"])

    def test_backspace_edits_menu_filters_without_deleting_selected_history(self):
        self.app.calculator.calculate("1+1")
        self.app.handle_key("UP")
        self.app.handle_key("F1")
        self.type_keys("sqrtX")
        self.app.handle_key("BACKSPACE")
        self.assertEqual(self.app.menu_filter, "sqrt")
        self.assertEqual(len(self.app.calculator.history), 1)
        self.app.handle_key("ESC")
        self.app.handle_key("BACKSPACE")
        self.assertFalse(self.app.calculator.history)


if __name__ == "__main__":
    unittest.main()
