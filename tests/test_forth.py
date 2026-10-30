import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calc_term import CalcError, ConsoleApp, ForthInterpreter, display_width, main


class ForthTests(unittest.TestCase):
    def setUp(self):
        self.vm = ForthInterpreter()

    def test_stack_operations_integer_arithmetic_and_flags(self):
        self.vm.execute("10 3 / 10 3 mod -10 3 / -10 3 mod 4 dup * 2 over + swap drop")
        self.assertEqual(self.vm.stack, [3, 1, -3, -1, 18])
        self.vm.execute("clearstack 1 2 3 rot swap over depth 2 3 < true and 0 0=")
        self.assertEqual(self.vm.stack, [2, 1, 3, 1, 4, -1, -1])

    def test_definitions_composition_and_case_insensitive_words(self):
        self.vm.execute(": Square ( n -- n*n ) DUP * ; : twice-square square 2 * ; 5 TWICE-SQUARE .")
        self.assertEqual(self.vm.output, ["50 "])
        self.assertEqual(self.vm.stack, [])
        self.vm.execute(": square dup * 1+ ; 3 twice-square")
        self.assertEqual(self.vm.stack, [20])

    def test_multiline_definition_comments_and_strings(self):
        self.vm.execute(': hello ( -- ) s" two words"')
        self.assertIsNotNone(self.vm.pending)
        self.vm.execute('type ." !" ; \\ ignored words\nHELLO')
        self.assertEqual("".join(self.vm.output), "two words!")
        self.vm.execute(r'"a \"quote\"\nline"')
        self.assertEqual(self.vm.stack, ['a "quote"\nline'])

    def test_branches_loops_nested_indices_and_recursion(self):
        self.vm.execute(": absolute dup 0< if negate else 0 + then ; -7 absolute 4 absolute")
        self.assertEqual(self.vm.stack, [7, 4])
        self.vm.execute("clearstack : sum 0 swap 0 do i + loop ; 5 sum")
        self.assertEqual(self.vm.stack, [10])
        self.vm.execute("clearstack 2 0 do 2 0 do i j + loop loop")
        self.assertEqual(self.vm.stack, [0, 1, 1, 2])
        self.vm.execute("clearstack 3 3 ?do 99 loop 5 0 do i dup 2 = if leave then loop")
        self.assertEqual(self.vm.stack, [0, 1, 2])
        self.vm.execute("clearstack 3 begin 1- dup 0= until")
        self.assertEqual(self.vm.stack, [0])
        self.vm.execute("clearstack 3 begin dup while 1- repeat")
        self.assertEqual(self.vm.stack, [0])
        self.vm.execute(": factorial dup 2 < if drop 1 exit then dup 1- recurse * ; 6 factorial")
        self.assertEqual(self.vm.stack, [0, 720])

    def test_failed_input_restores_stack_and_invalid_definitions_do_not_replace_words(self):
        self.vm.execute(": square dup * ; 42")
        original = dict(self.vm.definitions)
        for source in ("drop drop", "1 0 /", '"bad" 1 +', "unknown", ": square if ;",
                       ": square unknown ;", "else", "loop", "i", 's" unfinished', "( unfinished",
                       ": dup 1 ;", ": forth 1 ;", ": nested : other ; ;"):
            with self.subTest(source=source), self.assertRaises(CalcError):
                self.vm.execute(source)
            self.assertEqual(self.vm.stack, [42])
            self.assertEqual(self.vm.definitions, original)
            self.assertIsNone(self.vm.pending)

    def test_execution_recursion_and_stack_limits_leave_interpreter_usable(self):
        self.vm.execute(": forever begin again ; : recursive recurse ; 7")
        for source, message in (("forever", "execution limit"), ("recursive", "call depth limit"),
                                ("begin dup again", "stack limit")):
            with self.subTest(source=source), self.assertRaisesRegex(CalcError, message):
                self.vm.execute(source)
            self.assertEqual(self.vm.stack, [7])
            self.assertEqual(self.vm._loops, [])
        self.vm.execute("1+")
        self.assertEqual(self.vm.stack, [8])

    def test_loading_compiles_forward_references_without_running_them(self):
        self.vm.load_definitions({"first": "second", "second": '99 ." saved"', "forever": "begin again"})
        self.assertEqual(self.vm.stack, [])
        self.assertEqual(self.vm.output, [])
        self.vm.execute("first")
        self.assertEqual(self.vm.stack, [99])
        self.assertEqual("".join(self.vm.output), "saved")
        original = dict(self.vm.definitions)
        for definitions in ([], {"bad": 1}, {"bad": "no-such-word"}, {"dup": "1"}, {"bad": "if"}):
            with self.subTest(definitions=definitions), self.assertRaises(CalcError):
                self.vm.load_definitions(definitions)
            self.assertEqual(self.vm.definitions, original)

    def test_saved_strings_and_prints_round_trip(self):
        self.vm.execute(': greet "a \\"quote\\"" type ." hello world" ;')
        restored = ForthInterpreter()
        restored.load_definitions(json.loads(json.dumps(self.vm.definitions)))
        self.assertEqual(restored.execute("greet"), 'a "quote"hello world')

    def test_large_output_is_bounded_and_restores_stack(self):
        self.vm.execute('"' + 'x' * 1024 + '"')
        before = list(self.vm.stack)
        with self.assertRaisesRegex(CalcError, "output limit"):
            self.vm.execute("1100 0 do dup type loop")
        self.assertEqual(self.vm.stack, before)


class ForthAppTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "settings.json"
        self.app = ConsoleApp(config_path=self.path)

    def submit(self, text):
        self.app.text, self.app.cursor = text, len(text)
        self.app.submit()

    def test_native_words_process_existing_commands_and_stack_programs(self):
        self.app.command(":format approximate")
        self.app.command(':forth "exact" format 12 precision "degree" mode')
        self.assertEqual((self.app.calculator.output_mode, self.app.calculator.precision,
                          self.app.calculator.mode), ("exact", 12, "degree"))
        self.app.command(":mode degree")
        self.assertEqual(self.app.message, "Angle mode: degree")
        self.assertEqual(self.app.forth.stack, [])
        self.app.command(':forth "smoot" "1.7018_m" unit 1 "Favorites" menu 1 "Square" "^2" menuadd')
        self.assertEqual(self.app.calculator.calculate("1_smoot=>_m"), "8509/5000_m")
        self.assertEqual(self.app.menus[0]["label"], "Favorites")
        self.assertEqual(self.app.menus[0]["items"][-1], {"label": "Square", "insert": "^2"})

    def test_definitions_persist_are_shared_between_problems_and_run_from_menus(self):
        self.submit(': presentation "approximate" format 12 precision ;')
        self.assertEqual(self.app.text, "")
        self.assertIn("presentation", json.loads(self.path.read_text(encoding="utf-8"))["forth_words"])
        self.app.command(":menuadd 1 Presentation | :presentation")
        restored = ConsoleApp(config_path=self.path)
        self.assertEqual(restored.calculator.output_mode, "exact")
        restored.new_problem("New")
        restored.handle_key("F1")
        for char in "Presentation":
            restored.handle_key(char)
        restored.handle_key("ENTER")
        self.assertEqual(restored.calculator.output_mode, "approximate")
        self.assertEqual(restored.calculator.precision, 12)
        self.assertIsNone(restored.open_menu)
        restored.open_problem("Default")
        restored.command(":presentation")
        self.assertEqual(restored.calculator.precision, 12)

    def test_multiline_input_and_abort(self):
        self.submit(": square dup")
        self.assertIn("Compiling Forth word square", self.app.message)
        self.submit("* ;")
        self.app.command(":square 8")
        self.assertEqual(self.app.message, "Forth stack: <1> 64")
        self.submit(": unfinished dup")
        self.submit(":abort")
        self.assertIsNone(self.app.forth.pending)
        self.assertNotIn("unfinished", self.app.forth.definitions)
        self.submit("2+3")
        self.assertEqual(self.app.calculator.history[-1].result, "5")

    def test_calculator_bridge_and_insert_word(self):
        self.submit(':forth "1/3+1/6" calc type')
        self.assertEqual(self.app.message, "1/2")
        self.assertEqual(self.app.calculator.history[-1].result, "1/2")
        self.submit(': fill "sqrt(" insert ;')
        self.submit(":fill")
        self.assertEqual(self.app.text, "sqrt(")

    def test_invalid_saved_words_do_not_apply_settings_or_execute_code(self):
        for words in ({"bad": "__import__"}, {"quit": "1"}, ["bad"], {"bad": "if"}):
            with self.subTest(words=words):
                document = json.dumps({"mode": "degree", "forth_words": words})
                self.path.write_text(document, encoding="utf-8")
                restored = ConsoleApp(config_path=self.path)
                self.assertIn("Config error", restored.message)
                self.assertEqual(restored.calculator.mode, "radian")
                self.assertEqual(restored.forth.definitions, {})
                self.assertEqual(self.path.read_text(encoding="utf-8"), document)
        self.path.write_text(json.dumps({"forth_words": {"shutdown": "quit"}}), encoding="utf-8")
        self.assertTrue(ConsoleApp(config_path=self.path).running)

    def test_failed_definition_autosave_retries_and_reset_clears_user_words(self):
        self.app.command(":mode degree")
        original = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Locked")):
            with self.assertRaisesRegex(CalcError, "Cannot save configuration"):
                self.app.command(": square dup * ;")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(self.app._config_dirty)
        self.assertTrue(self.app.save_session())
        restored = ConsoleApp(config_path=self.path)
        restored.command(":square 4")
        self.assertEqual(restored.forth.stack, [16])
        restored.command(":resetconfig")
        self.assertEqual(restored.forth.definitions, {})
        self.assertEqual(restored.forth.stack, [])
        self.assertEqual(ConsoleApp(config_path=self.path).forth.definitions, {})

    def test_batch_commands_and_definition_persistence(self):
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            status = main(["--config", str(self.path), "--eval", ": square dup * ;",
                           "--eval", ":square 5", "--eval", ":forth .", "--eval", "2+3"])
        self.assertEqual(status, 0)
        self.assertIn("Forth stack: <1> 25", output.getvalue())
        self.assertIn("2+3 = 5", output.getvalue())
        self.assertIn("square", ConsoleApp(config_path=self.path).forth.definitions)

    def test_def_displays_saved_word_without_execution_or_changes(self):
        self.app.command(": square ( n -- n*n ) dup * ;")
        self.app.command(': dangerous "degree" mode quit ;')
        self.app.command(":forth 7")
        before = self.path.read_bytes()
        for name, expected in (("square", ": square dup * ;"),
                               ("SQUARE", ": square dup * ;"),
                               ("dangerous", ': dangerous "degree" mode quit ;')):
            with self.subTest(name=name):
                self.app.command(":def " + name)
                self.assertEqual(self.app.message, expected)
                self.assertEqual(self.app.io.entries[-1], expected)
                self.assertEqual(self.app.forth.stack, [7])
                self.assertEqual(self.app.calculator.mode, "radian")
                self.assertTrue(self.app.running)
                self.assertEqual(self.path.read_bytes(), before)
        restored = ConsoleApp(config_path=self.path)
        restored.command(':forth "square" def')
        self.assertEqual(restored.message, ": square dup * ;")
        restored.command(": square dup * 1+ ;")
        restored.command(":def square")
        self.assertEqual(restored.message, ": square dup * 1+ ;")

    def test_def_handles_builtins_missing_names_and_unknown_words(self):
        self.app.command(":forth 42")
        for name in ("dup", "format", "def"):
            with self.subTest(name=name):
                self.app.command(":def " + name)
                self.assertIn("built-in Forth word (native implementation)", self.app.message)
        self.app.command(":def if")
        self.assertIn("built-in Forth compiler word", self.app.message)
        for command in (":def", ":def square extra", ":def missing-word"):
            with self.subTest(command=command), self.assertRaises(CalcError):
                self.app.command(command)
            self.assertEqual(self.app.forth.stack, [42])

    def test_def_plain_output_and_long_definitions_in_io(self):
        body = " ".join(["dup drop"] * 50)
        self.app.command(": long-word " + body + " ;")
        with patch("sys.stdin", io.StringIO(":def long-word\n:quit\n")), \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(["--config", str(self.path), "--plain"]), 0)
        expected = ": long-word " + body + " ;"
        self.assertIn(expected, output.getvalue())
        self.app.command(":def long-word")
        self.app.handle_key("F10")
        self.app.frame(40, 12)
        rows = (len(expected) + 39) // 40
        self.assertEqual("".join(self.app.io.wrapped_lines(40, display_width)[-rows:]), expected)

    def test_unfinished_batch_and_plain_definitions_report_errors(self):
        for plain in (False, True):
            with self.subTest(plain=plain), patch("sys.stdout", new_callable=io.StringIO), \
                    patch("sys.stderr", new_callable=io.StringIO) as error:
                if plain:
                    with patch("sys.stdin", io.StringIO(": incomplete dup\n")):
                        status = main(["--config", str(self.path), "--plain"])
                else:
                    status = main(["--config", str(self.path), "--eval", ": incomplete dup"])
                self.assertEqual(status, 1)
                self.assertIn("Unfinished Forth definition", error.getvalue())
        self.assertFalse(self.path.exists())

    def test_backup_contains_definitions_and_failed_menu_word_is_recoverable(self):
        self.app.command(": square dup * ;")
        self.app.command(":backupconfig")
        backup = self.path.with_name("settings.backup1.json")
        self.assertIn("square", json.loads(backup.read_text(encoding="utf-8"))["forth_words"])
        self.app.command(":menuadd 1 Broken | :forth drop")
        self.app.handle_key("F1")
        for char in "Broken":
            self.app.handle_key(char)
        self.app.handle_key("ENTER")
        self.assertIn("Forth stack underflow", self.app.message)
        self.app.command(":square 3")
        self.assertEqual(self.app.forth.stack, [9])


if __name__ == "__main__":
    unittest.main()
