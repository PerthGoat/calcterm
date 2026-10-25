import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from calc_term import ConsoleApp


SCRIPT = Path(__file__).resolve().parents[1] / "calc_term.py"


class EntrypointTests(unittest.TestCase):
    def test_default_saved_data_paths_remain_beside_entry_script(self):
        with patch.object(ConsoleApp, "_load_config"), \
                patch.object(ConsoleApp, "_load_history"), \
                patch.object(ConsoleApp, "_load_problems"):
            app = ConsoleApp()
        self.assertEqual(app.config_path, SCRIPT.with_name("calc_term_config.json"))
        self.assertEqual(app.history_path, SCRIPT.with_name("calc_term_config.history.json"))
        self.assertEqual(app.problems_path, SCRIPT.with_name("calc_term_config.problems.json"))

    def test_batch_launch_from_another_directory_keeps_shared_session(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", "settings.json",
                 "--eval", "3->x", "--eval", "4*x", "--eval", "3_in=>_ft"],
                cwd=directory, capture_output=True, text=True, encoding="utf-8", timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["3->x = 3", "4*x = 12", "3_in=>_ft = 1/4_ft"])
            history = json.loads((Path(directory) / "settings.history.json").read_text(encoding="utf-8"))
            self.assertEqual([entry["result"] for entry in history], ["3", "12", "1/4_ft"])

    def test_plain_launch_from_another_directory_saves_config_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--plain", "--config", "settings.json"],
                input=":mode degree\n:backupconfig\nsqrt(9)\n:quit\n",
                cwd=directory, capture_output=True, text=True, encoding="utf-8", timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Backed up configuration to settings.backup1.json", result.stdout)
            self.assertIn("sqrt(9) = 3", result.stdout)
            config = Path(directory) / "settings.json"
            backup = Path(directory) / "settings.backup1.json"
            self.assertEqual(backup.read_bytes(), config.read_bytes())
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8"))["mode"], "degree")


if __name__ == "__main__":
    unittest.main()
