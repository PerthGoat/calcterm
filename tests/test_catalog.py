import json
from pathlib import Path
import tempfile
import unittest

from calc_term import (BITWISE, EQUATION_NAMES, FUNCTIONS, RESERVED, SYMBOLS, TRANSLATE,
                       ConsoleApp, display_width)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "settings.json"
        self.app = ConsoleApp(config_path=self.config)

    def type_keys(self, text):
        for char in text:
            self.app.handle_key(char)

    def open_from_help(self):
        self.app.handle_key("F6")
        self.type_keys("Catalog")
        self.app.handle_key("ENTER")

    def test_help_opens_catalog_and_inserts_function_at_the_existing_cursor(self):
        self.app.calculator.calculate("3->a")
        history = list(self.app.calculator.history)
        self.app.text, self.app.cursor = "2()+1", 2
        self.open_from_help()
        self.assertTrue(self.app.catalog_open)
        self.assertIsNone(self.app.open_menu)
        self.type_keys("sqrt(")
        self.assertEqual(len(self.app.catalog_matches()), 1)
        self.app.handle_key("ENTER")
        self.assertFalse(self.app.catalog_open)
        self.assertEqual(self.app.text, "2(sqrt()+1")
        self.assertEqual(self.app.cursor, 7)
        self.assertEqual(self.app.calculator.answer.value, 3)
        self.assertEqual(self.app.calculator.variables["a"].value, 3)
        self.assertEqual(list(self.app.calculator.history), history)

    def test_catalog_covers_every_function_symbol_unit_constant_and_equation_slot(self):
        self.app.command(":unit smoot = 1.7018_m")
        self.app.menus[3]["items"].append({"label": "Custom symbols", "items": [
            {"label": "Nabla", "insert": "∇"}]})
        self.app.calculator.define_equation("y1", "4x")
        self.open_from_help()
        items = self.app.catalog_matches()
        inserted = {item["insert"] for item in items}
        self.assertTrue({name + "(" for name in FUNCTIONS}.issubset(inserted))
        self.assertTrue({name + "(" for name in EQUATION_NAMES}.issubset(inserted))
        self.assertTrue({symbol for symbol, _ in SYMBOLS}.issubset(inserted))
        self.assertTrue(set(map(chr, TRANSLATE)).issubset(inserted))
        self.assertTrue(set(RESERVED).issubset(inserted))
        self.assertTrue(set(BITWISE).issubset(inserted))
        self.assertTrue({unit.notation for unit in self.app.calculator.registry.units.values()}.issubset(inserted))
        self.assertIn("∇", inserted)
        self.assertIn("ans", inserted)
        self.assertEqual(len(inserted), len(items))
        labels = [item["label"] for item in items]
        self.assertEqual(labels, sorted(labels, key=lambda label: (label.casefold(), label)))
        self.assertIn("y1(x) - 4x", labels)
        self.assertGreater(len(items), 100)

    def test_catalog_centers_large_popup_and_resizes_while_scrolled_to_the_end(self):
        self.open_from_help()
        self.app.handle_key("END")
        for width, height in ((40, 12), (80, 24), (100, 50), (160, 40)):
            with self.subTest(width=width, height=height):
                lines, selected, cursor = self.app.frame(width, height)
                self.assertEqual(len(lines), height)
                self.assertTrue(all(display_width(line) <= width for line in lines))
                self.assertIsNone(cursor)
                left, right = lines[2].index("+"), lines[2].rindex("+")
                self.assertLessEqual(abs(left - (width - right - 1)), 1)
                self.assertEqual(lines[height - 3][left:right + 1], lines[2][left:right + 1])
                row, (first, last) = next(iter(selected.items()))
                self.assertGreater(row, 4)
                self.assertLess(row, height - 3)
                self.assertEqual((first, last), (left + 1, right))
                self.assertEqual(self.app.catalog_index, len(self.app.catalog_matches()) - 1)
        self.app.handle_key("HOME")
        self.app.handle_key("PAGEDOWN")
        self.assertEqual(self.app.catalog_index, self.app.catalog_rows)
        self.app.handle_key("PAGEUP")
        self.assertEqual(self.app.catalog_index, 0)
        self.app.handle_key("DOWN")
        self.app.handle_key("UP")
        self.assertEqual(self.app.catalog_index, 0)

    def test_empty_filter_results_are_safe_and_filter_can_be_edited_or_cleared(self):
        self.open_from_help()
        self.type_keys("no-such-function")
        lines, selected, cursor = self.app.frame()
        self.assertIn("(no matches)", "\n".join(lines))
        self.assertFalse(selected)
        self.assertIsNone(cursor)
        for key in ("END", "PAGEDOWN", "ENTER"):
            self.app.handle_key(key)
        self.assertTrue(self.app.catalog_open)
        self.assertEqual(self.app.catalog_index, 0)
        self.assertEqual(self.app.text, "")
        self.app.handle_key("CTRL_U")
        self.type_keys("epsilonx")
        self.app.handle_key("BACKSPACE")
        self.assertEqual(self.app.catalog_filter, "epsilon")
        self.assertTrue(self.app.catalog_matches())

    def test_catalog_can_insert_unicode_and_refreshes_custom_units_on_reopening(self):
        self.open_from_help()
        self.type_keys("EPSILON (ε)")
        self.assertEqual(len(self.app.catalog_matches()), 1)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "ε")
        self.app.command(":unit smoot = 1.7018_m")
        self.app.command(":catalog")
        self.type_keys("_smoot")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.text, "ε_smoot")

    def test_cancel_preserves_input_history_selection_and_does_not_run_other_shortcuts(self):
        self.app.calculator.calculate("7")
        self.app.text, self.app.cursor = "()+2", 1
        self.app.handle_key("UP")
        selected_history = self.app.history_index
        self.open_from_help()
        self.app.handle_key("F9")
        self.assertTrue(self.app.catalog_open)
        self.app.handle_key("ESC")
        self.assertFalse(self.app.catalog_open)
        self.assertEqual((self.app.text, self.app.cursor), ("()+2", 1))
        self.assertEqual(self.app.history_index, selected_history)
        self.assertEqual(len(self.app.calculator.history), 1)

    def test_catalog_is_added_to_saved_help_menu_without_resetting_custom_items(self):
        self.app.menus[5] = {"label": "Custom Help", "items": [{"label": "Keyboard", "command": ":help"}]}
        document = json.dumps({"menus": self.app.menus})
        self.config.write_text(document, encoding="utf-8")
        restored = ConsoleApp(config_path=self.config)
        self.assertEqual(restored.menus[5]["label"], "Custom Help")
        self.assertEqual(restored.menus[5]["items"][0], {"label": "Keyboard", "command": ":help"})
        self.assertIn({"label": "Catalog", "command": ":catalog"}, restored.menus[5]["items"])
        self.assertIn({"label": "Forth words", "command": ":words"}, restored.menus[5]["items"])
        self.assertEqual(self.config.read_text(encoding="utf-8"), document)
        restored.save_config()
        reopened = ConsoleApp(config_path=self.config)
        self.assertEqual(sum(item.get("command") == ":catalog" for item in reopened.menus[5]["items"]), 1)
        self.assertEqual(sum(item.get("command") == ":words" for item in reopened.menus[5]["items"]), 1)


if __name__ == "__main__":
    unittest.main()
