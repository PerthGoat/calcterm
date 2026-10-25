import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calc_term import CalcError, ConsoleApp, default_menus


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "settings.json"
        self.app = ConsoleApp(config_path=self.config)

    def test_valid_configuration_commands_save_without_explicit_save(self):
        for command, key, expected in ((":mode degree", "mode", "degree"),
                                       (":format approximate", "output_mode", "approximate"),
                                       (":precision 12", "precision", 12),
                                       (":recall expression", "history_insert", "expression"),
                                       (":colors off", "syntax_colors", False)):
            with self.subTest(command=command):
                self.app.command(command)
                self.assertEqual(json.loads(self.config.read_text(encoding="utf-8"))[key], expected)
                self.assertFalse(self.app._config_dirty)
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual((restored.calculator.mode, restored.calculator.output_mode,
                          restored.calculator.precision, restored.history_insert, restored.syntax_colors),
                         ("degree", "approximate", 12, "expression", False))

    def test_invalid_changes_do_not_replace_configuration(self):
        self.app.command(":mode degree")
        before = self.config.read_bytes()
        for command in (":mode wrong", ":precision 1", ":colors invalid", ":format wrong", ":recall wrong"):
            with self.subTest(command=command), self.assertRaises(CalcError):
                self.app.command(command)
            self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse(self.app._config_dirty)

    def test_options_create_numbered_backups_without_overwriting_previous_copies(self):
        self.app.command(":mode degree")
        original = self.config.read_bytes()
        first = self.config.with_name("settings.backup1.json")
        first.write_bytes(b"Existing backup")
        for number, mode in ((2, "degree"), (3, "radian")):
            self.app.command(":mode " + mode)
            current = self.config.read_bytes()
            self.app.handle_key("F5")
            for char in "Create backup config":
                self.app.handle_key(char)
            self.assertEqual(len(self.app.menu_items()), 1)
            self.app.handle_key("ENTER")
            backup = self.config.with_name(f"settings.backup{number}.json")
            self.assertEqual(backup.read_bytes(), current)
            self.assertEqual(self.config.read_bytes(), current)
            self.assertIn(str(backup), self.app.message)
            self.assertIsNone(self.app.open_menu)
        self.assertEqual(first.read_bytes(), b"Existing backup")
        self.assertEqual(self.config.with_name("settings.backup2.json").read_bytes(), original)

    def test_backup_saves_current_settings_when_no_config_exists(self):
        self.app.command(":backupconfig")
        backup = self.config.with_name("settings.backup1.json")
        self.assertEqual(backup.read_bytes(), self.config.read_bytes())
        restored = ConsoleApp(config_path=backup)
        self.assertEqual(restored.calculator.mode, self.app.calculator.mode)
        self.assertEqual(restored.menus, self.app.menus)

    def test_older_custom_options_gain_backup_action_once_without_rewriting_config(self):
        menus = self.app.menus
        menus[4]["label"] = "My Options"
        menus[4]["items"] = [{"label": "Custom", "insert": "123"}]
        document = json.dumps({"menus": menus})
        self.config.write_text(document, encoding="utf-8")
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.menus[4]["label"], "My Options")
        self.assertIn({"label": "Custom", "insert": "123"}, restored.menus[4]["items"])
        restored.command(":backupconfig")
        self.assertEqual(self.config.read_text(encoding="utf-8"), document)
        self.assertEqual(self.config.with_name("settings.backup1.json").read_text(encoding="utf-8"), document)
        restored.save_config()
        reloaded = ConsoleApp(config_path=self.config)
        actions = [item for item in reloaded.menus[4]["items"] if item.get("command") == ":backupconfig"]
        self.assertEqual(len(actions), 1)

    def test_backup_retries_pending_settings_after_failed_autosave(self):
        self.app.command(":mode degree")
        with patch.object(Path, "replace", side_effect=PermissionError("Locked")):
            with self.assertRaises(CalcError):
                self.app.command(":precision 12")
        self.app.command(":backupconfig")
        backup = self.config.with_name("settings.backup1.json")
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8"))["precision"], 12)
        self.assertFalse(self.app._config_dirty)

    def test_backup_io_failure_preserves_config_and_existing_backups(self):
        self.app.command(":mode degree")
        self.app.command(":backupconfig")
        original = self.config.read_bytes()
        first = self.config.with_name("settings.backup1.json")
        for operation in ("read_bytes", "open"):
            with self.subTest(operation=operation):
                with patch.object(Path, operation, side_effect=PermissionError("Locked")):
                    with self.assertRaisesRegex(CalcError, "Cannot back up configuration"):
                        self.app.command(":backupconfig")
                self.assertEqual(self.config.read_bytes(), original)
                self.assertEqual(first.read_bytes(), original)
                self.assertFalse(self.config.with_name("settings.backup2.json").exists())

    def test_cleanup_reset_restores_defaults_and_preserves_problem_data_and_custom_units(self):
        self.app.text = "2+2"
        self.app.submit()
        self.app.command(":unit smoot = 1.7018_m")
        self.app.new_problem("Engineering")
        self.app.calculator.define_equation("y1", "x_smoot")
        self.app.text = "7->a"
        self.app.submit()
        for command in (":mode degree", ":format approximate", ":precision 12", ":recall expression",
                        ":colors off", ":menu 1 Favorites", ":menuadd 1 Square | ^2"):
            self.app.command(command)
        problems_before = self.app.problems_path.read_bytes()
        self.app.handle_key("F9")
        self.assertEqual(self.app.menu_items()[2]["label"], "Reset configuration")
        self.app.handle_key("END")
        self.app.handle_key("ENTER")
        self.assertIsNone(self.app.open_menu)
        self.assertEqual((self.app.calculator.mode, self.app.calculator.output_mode,
                          self.app.calculator.precision, self.app.history_insert, self.app.syntax_colors),
                         ("radian", "exact", 50, "result", True))
        self.assertEqual(self.app.menus, default_menus(self.app.calculator.registry))
        self.assertEqual(self.app.problem_name, "Engineering")
        self.assertEqual(self.app.calculator.variables["a"].value, 7)
        self.assertEqual(self.app.calculator.answer.value, 7)
        self.assertEqual(self.app.problems_path.read_bytes(), problems_before)
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.problem_name, "Engineering")
        self.assertEqual(restored.calculator.mode, "radian")
        self.assertTrue(restored.syntax_colors)
        self.assertEqual(restored.calculator.equations, {"y1": "x_smoot"})
        self.assertEqual(restored.calculator.history[-1].source, "7->a")
        self.assertEqual(restored.calculator.calculate("y1(2)=>_m"), "8509/2500_m")
        restored.open_problem("Default")
        self.assertEqual([entry.result for entry in restored.calculator.history], ["4"])

    def test_failed_autosave_preserves_previous_file_and_retries_on_exit(self):
        self.app.command(":mode degree")
        before = self.config.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Locked")):
            with self.assertRaisesRegex(CalcError, "Cannot save configuration"):
                self.app.command(":format approximate")
            self.assertTrue(self.app._config_dirty)
            self.assertEqual(self.config.read_bytes(), before)
        self.assertTrue(self.app.save_session())
        self.assertFalse(self.app._config_dirty)
        self.assertEqual(ConsoleApp(config_path=self.config).calculator.output_mode, "approximate")

    def test_failed_reset_keeps_previous_file_and_retries_defaults_on_exit(self):
        self.app.command(":mode degree")
        self.app.command(":colors off")
        before = self.config.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Locked")):
            with self.assertRaisesRegex(CalcError, "Cannot save configuration"):
                self.app.command(":resetconfig")
            self.assertEqual(self.config.read_bytes(), before)
        self.assertTrue(self.app.save_session())
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.calculator.mode, "radian")
        self.assertTrue(restored.syntax_colors)


if __name__ == "__main__":
    unittest.main()
