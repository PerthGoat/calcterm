import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calc_term import CalcError, Calculator, ConsoleApp, default_menus, display_width, main


class ProblemTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "settings.json"
        self.app = ConsoleApp(config_path=self.config)

    def type_keys(self, text):
        for char in text:
            self.app.handle_key(char)

    def equation(self, expression):
        self.app.handle_key("F7")
        self.app.handle_key("CTRL_U")
        self.type_keys(expression)
        self.app.handle_key("F7")

    def calculate(self, expression):
        self.app.text = expression
        self.app.submit()

    def choose_problem_action(self, action):
        self.app.handle_key("F5")
        self.type_keys("Problems")
        self.app.handle_key("RIGHT")
        self.type_keys(action)
        self.app.handle_key("ENTER")

    def test_equations_and_checkmarks_save_without_save_command(self):
        self.equation("4x")
        self.assertTrue(self.app.problems_path.exists())
        self.assertFalse(self.config.exists())
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.calculator.calculate("y1(3)"), "12")
        self.app.handle_key("F7")
        self.app.handle_key("CTRL_T")
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.table_equation_names(), [])
        self.assertEqual(restored.calculator.equations, {"y1": "4x"})
        self.app.handle_key("CTRL_U")
        self.app.handle_key("F7")
        self.assertFalse(ConsoleApp(config_path=self.config).calculator.equations)

    def test_problems_isolate_history_equations_and_table_settings(self):
        self.equation("4x")
        self.calculate("7->x")
        self.app.table_start, self.app.table_step = "3", "1/2"
        self.app.new_problem("Mechanics")
        self.assertFalse(self.app.calculator.history)
        self.assertFalse(self.app.calculator.equations)
        self.assertFalse(self.app.calculator.variables)
        self.assertEqual(self.app.calculator.answer.value, 0)
        self.equation("x^2")
        self.calculate("1/0")
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.problem_name, "Mechanics")
        self.assertEqual(restored.calculator.equations, {"y1": "x^2"})
        self.assertTrue(restored.calculator.history[-1].is_error)
        self.app.open_problem("Default")
        self.assertEqual(self.app.calculator.equations, {"y1": "4x"})
        self.assertEqual([entry.source for entry in self.app.calculator.history], ["7->x"])
        self.assertEqual((self.app.table_start, self.app.table_step), ("3", "1/2"))
        self.assertFalse(self.app.calculator.variables)
        self.app.open_problem("Mechanics")
        self.assertEqual([entry.source for entry in self.app.calculator.history], ["1/0"])
        self.assertEqual((self.app.table_start, self.app.table_step), ("0", "1"))

    def test_new_and_open_problem_are_available_through_options(self):
        self.choose_problem_action("New")
        self.assertEqual(self.app.problem_dialog, "new")
        self.type_keys("Algebra ε")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.problem_name, "Algebra ε")
        self.assertIsNone(self.app.problem_dialog)
        self.choose_problem_action("Open")
        self.assertEqual(self.app.problem_dialog, "open")
        self.type_keys("Default")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.problem_name, "Default")
        self.assertIsNone(self.app.problem_dialog)
        lines, _, _ = self.app.frame()
        self.assertIn("Problem: Default", lines[1])

    def test_new_problem_rejects_empty_and_duplicate_names_without_overwriting(self):
        self.app.new_problem("Algebra")
        before = self.app.problems_path.read_bytes()
        for name in ("", "  ", "a" * 81, "bad\nname", "algebra", "Default"):
            with self.subTest(name=name), self.assertRaises(CalcError):
                self.app.new_problem(name)
            self.assertEqual(self.app.problems_path.read_bytes(), before)
        self.app.begin_problem_dialog("new")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.problem_dialog, "new")
        self.assertIn("Error:", self.app.message)
        self.app.handle_key("ESC")
        self.assertEqual(self.app.problem_name, "Algebra")

    def test_delete_requires_confirmation_and_defaults_to_cancel(self):
        self.equation("4x")
        self.app.new_problem("Algebra")
        self.equation("x^2")
        before = self.app.problems_path.read_bytes()
        self.choose_problem_action("Delete")
        self.assertEqual(self.app.problem_choices(), ["Algebra"])
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.problem_dialog, "confirm")
        for width, height in ((40, 12), (100, 24)):
            lines, selected, cursor = self.app.frame(width, height)
            self.assertIn("Delete Problem?", "\n".join(lines))
            row, (first, last) = next(iter(selected.items()))
            self.assertEqual(lines[row][first:last], "Cancel")
            self.assertIsNone(cursor)
            self.assertTrue(all(display_width(line) <= width for line in lines))
        self.assertEqual(self.app.problems_path.read_bytes(), before)
        self.app.handle_key("ENTER")
        self.assertIn("Algebra", self.app.problems)
        self.assertEqual(self.app.problems_path.read_bytes(), before)
        self.app.command(":problem delete Algebra")
        self.app.handle_key("RIGHT")
        self.app.handle_key("ENTER")
        self.assertNotIn("Algebra", self.app.problems)
        self.assertEqual(self.app.problem_name, "Default")
        self.assertEqual(self.app.calculator.equations, {"y1": "4x"})
        restored = ConsoleApp(config_path=self.config)
        self.assertNotIn("Algebra", restored.problems)
        self.assertEqual(restored.problem_name, "Default")

    def test_delete_inactive_problem_keeps_current_work_and_escape_cancels(self):
        self.app.new_problem("Algebra")
        self.app.new_problem("Mechanics")
        self.equation("3x")
        self.calculate("5+3")
        self.app.command(":problem delete Algebra")
        self.app.handle_key("RIGHT")
        self.app.handle_key("ESC")
        self.assertIn("Algebra", self.app.problems)
        self.app.command(":problem delete Algebra")
        self.app.handle_key("y")
        self.assertIn("Algebra", self.app.problems)
        self.app.handle_key("ENTER")
        self.assertNotIn("Algebra", self.app.problems)
        self.assertEqual(self.app.problem_name, "Mechanics")
        self.assertEqual(self.app.calculator.equations, {"y1": "3x"})
        self.assertEqual(self.app.calculator.history[-1].result, "8")
        with self.assertRaises(CalcError):
            self.app.command(":problem delete Default")

    def test_legacy_settings_and_history_migrate_without_replaying_history(self):
        self.config.write_text(json.dumps({"equations": {"y1": "4x"}}), encoding="utf-8")
        self.app.history_path.write_text(json.dumps([
            {"source": "3->x", "result": "3"},
            {"source": "unsupported()", "result": "recorded text"}]), encoding="utf-8")
        with patch.object(Calculator, "evaluate", side_effect=AssertionError("Do not replay history")):
            restored = ConsoleApp(config_path=self.config)
            restored.new_problem("New")
            restored.open_problem("Default")
            reopened = ConsoleApp(config_path=self.config)
        self.assertEqual(reopened.calculator.equations, {"y1": "4x"})
        self.assertEqual(len(reopened.calculator.history), 2)
        self.assertFalse(reopened.calculator.variables)
        self.assertEqual(reopened.calculator.answer.value, 0)

    def test_existing_options_menu_gets_problems_without_resetting_customizations(self):
        menus = default_menus(self.app.calculator.registry)
        menus[4]["label"] = "My Options"
        menus[4]["items"] = [item for item in menus[4]["items"] if item["label"] != "Problems"]
        self.config.write_text(json.dumps({"menus": menus}), encoding="utf-8")
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.menus[4]["label"], "My Options")
        self.assertIn("Problems", [item["label"] for item in restored.menus[4]["items"]])
        self.assertEqual(restored.menus[0], menus[0])

    def test_problems_write_failure_keeps_current_problem_and_retries(self):
        self.app.new_problem("Algebra")
        before = self.app.problems_path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Locked")):
            with self.assertRaises(CalcError):
                self.app.new_problem("Mechanics")
            self.assertEqual(self.app.problem_name, "Algebra")
            self.assertNotIn("Mechanics", self.app.problems)
            self.calculate("5+3")
            self.assertIn("Problem save error:", self.app.message)
            with self.assertRaises(CalcError):
                self.app.open_problem("Default")
        self.assertEqual(self.app.problems_path.read_bytes(), before)
        self.assertEqual(self.app.calculator.history[-1].result, "8")
        self.assertTrue(self.app.save_history())
        self.assertNotIn("Problem save error:", self.app.message)
        reopened = ConsoleApp(config_path=self.config)
        self.assertEqual(reopened.calculator.history[-1].result, "8")

    def test_corrupt_problems_file_is_preserved_and_not_partially_loaded(self):
        invalid = ["not json", "[]", '{"version":2}',
                   json.dumps({"version": 1, "active": "Missing", "problems": {"Default": {}}}),
                   json.dumps({"version": 1, "active": "Default", "problems": {
                       "Default": {"equations": {"y1": "4x"}}, "Bad": {"equations": {"y2": "x+"}}}})]
        for document in invalid:
            with self.subTest(document=document):
                self.app.problems_path.write_text(document, encoding="utf-8")
                restored = ConsoleApp(config_path=self.config)
                self.assertIn("Problems load error:", restored.message)
                self.assertFalse(restored.calculator.equations)
                self.assertFalse(restored.save_session())
                self.assertEqual(restored.problems_path.read_text(encoding="utf-8"), document)

    def test_failed_confirmed_deletion_keeps_the_problem_and_its_file(self):
        self.app.new_problem("Algebra")
        self.equation("4x")
        before = self.app.problems_path.read_bytes()
        self.app.command(":problem delete Algebra")
        self.app.handle_key("RIGHT")
        with patch.object(Path, "replace", side_effect=PermissionError("Locked")):
            self.app.handle_key("ENTER")
        self.assertEqual(self.app.problem_dialog, "confirm")
        self.assertEqual(self.app.problem_name, "Algebra")
        self.assertEqual(self.app.problems_path.read_bytes(), before)
        self.assertIn("Algebra", self.app.problems)
        self.assertEqual(self.app.calculator.equations, {"y1": "4x"})

    def test_plain_mode_problem_commands_keep_separate_histories(self):
        script = ":problem new Algebra\n5+3\n:problem open Default\n3+4\n:problem open Algebra\n:quit\n"
        with patch("sys.stdin", io.StringIO(script)), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["--config", str(self.config), "--plain"]), 0)
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.problem_name, "Algebra")
        self.assertEqual([entry.result for entry in restored.calculator.history], ["8"])
        restored.open_problem("Default")
        self.assertEqual([entry.result for entry in restored.calculator.history], ["7"])

    def test_valid_pending_equation_saves_on_exit_and_invalid_edit_preserves_previous(self):
        self.app.handle_key("F7")
        self.type_keys("4x")
        self.assertTrue(self.app.save_session())
        self.assertEqual(ConsoleApp(config_path=self.config).calculator.equations, {"y1": "4x"})
        self.type_keys("+")
        self.assertTrue(self.app.save_session())
        self.assertEqual(ConsoleApp(config_path=self.config).calculator.equations, {"y1": "4x"})

    def test_interactive_exit_saves_the_current_equation_draft(self):
        def run(app):
            app.handle_key("F7")
            app.handle_key("4")
            app.handle_key("x")
            raise KeyboardInterrupt

        with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stdout.isatty", return_value=True), \
                patch("sys.stdin.isatty", return_value=True), patch("calc_term.Terminal") as terminal:
            terminal.return_value.__enter__.return_value.run.side_effect = run
            self.assertEqual(main(["--config", str(self.config)]), 0)
        self.assertEqual(ConsoleApp(config_path=self.config).calculator.equations, {"y1": "4x"})

    def test_problem_loading_preserves_numeric_formulas_using_ans(self):
        self.calculate("3")
        self.equation("x/ans")
        restored = ConsoleApp(config_path=self.config)
        self.assertNotIn("Problems load error", restored.message)
        self.assertEqual(restored.calculator.equations, {"y1": "x/ans"})
        self.assertEqual(restored.calculator.calculate("2"), "2")
        self.assertEqual(restored.calculator.calculate("y1(4)"), "2")


if __name__ == "__main__":
    unittest.main()
