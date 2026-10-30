import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from calc_term import ConsoleApp, Terminal, display_width, main
from calcterm.io import IOTranscript


class IOTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = ConsoleApp(config_path=Path(directory.name) / "settings.json")

    def submit(self, text):
        self.app.text, self.app.cursor = text, len(text)
        self.app.submit()

    def test_words_can_be_read_in_full_by_scrolling_io(self):
        self.app.command(":words")
        expected = self.app.message.split()
        self.assertIn("F10 IO: full output", self.app.frame(80, 12)[0][-1])
        self.app.handle_key("F10")
        self.app.frame(80, 12)
        self.app.handle_key("TAB")
        self.app.handle_key("HOME")
        content = []
        while True:
            lines, _, cursor = self.app.frame(80, 12)
            self.assertIsNone(cursor)
            content.extend(lines[2:2 + self.app.io_rows])
            previous = self.app.io.window(80, self.app.io_rows, display_width)[1]
            self.app.handle_key("PAGEDOWN")
            if self.app.io.window(80, self.app.io_rows, display_width)[1] == previous:
                break
        # Read each wrapped row exactly once to reconstruct the original output.
        wrapped = self.app.io.wrapped_lines(80, display_width)
        self.assertEqual("".join(wrapped[1:]).split(), expected)
        self.assertIn(expected[0], "".join(content))
        self.assertIn(expected[-1], "".join(content))
        self.assertIn("F10 IO", self.app.frame(100, 24)[0][0])

    def test_multiline_output_partial_output_and_errors_are_logged(self):
        self.submit(':forth ." first" cr ." second"')
        self.assertEqual(self.app.io.entries[-1], "first\nsecond")
        self.submit(':forth ." before error" 1 0 /')
        self.assertEqual(list(self.app.io.entries)[-2:], ["before error", "Error: Forth division by zero."])
        self.app.command(":words")
        self.submit(":unit missing-definition")
        self.assertNotEqual(self.app.io.entries[-2], self.app.message)
        self.assertEqual(self.app.io.entries[-2], "> :unit missing-definition")
        self.assertIn("Error: Use :unit", self.app.io.entries[-1])
        self.submit("1/0")
        self.assertIn("Error: Division by zero", self.app.io.entries[-1])

    def test_io_input_uses_the_editor_and_preserves_calculator_input_on_close(self):
        self.app.text, self.app.cursor = "sqrt(", 5
        self.app.handle_key("F10")
        self.assertEqual((self.app.text, self.app.cursor), ("sqrt(", 5))
        self.app.handle_key("ESC")
        self.assertFalse(self.app.io_open)
        self.assertEqual((self.app.text, self.app.cursor), ("sqrt(", 5))
        self.app.clear_input()
        self.app.handle_key("F10")
        for char in ":forth 2 3 + .":
            self.app.handle_key(char)
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.io.entries[-1], "5 ")
        self.assertTrue(self.app.io_open)
        self.app.handle_key("TAB")
        self.assertIsNone(self.app.frame()[2])
        self.app.handle_key("1")
        self.assertTrue(self.app.io_focus_input)
        self.app.handle_key("ENTER")
        self.assertFalse(self.app.calculator.history)
        self.assertEqual(list(self.app.io.entries)[-2:], ["> 1", "1"])
        self.app.handle_key("F10")
        self.assertFalse(self.app.io_open)
        self.assertEqual(self.app.text, "1")

    def test_scroll_keys_do_not_recall_or_change_calculator_history(self):
        self.submit("2+3")
        self.app.command(':forth 60 0 do i . cr loop')
        self.app.handle_key("F10")
        self.app.frame(60, 12)
        state = self.app.text, self.app.cursor, self.app.input_selection, list(self.app.calculator.history)
        last = self.app.io.window(60, 5, display_width)[1]
        self.app.handle_key("UP")
        self.assertEqual(self.app.io.window(60, 5, display_width)[1], last - 1)
        self.app.handle_key("PAGEUP")
        self.assertEqual(self.app.io.window(60, 5, display_width)[1], last - 6)
        self.app.handle_key("DOWN")
        self.app.handle_key("TAB")
        self.app.handle_key("HOME")
        self.assertEqual(self.app.io.start, 0)
        self.app.handle_key("END")
        self.assertIsNone(self.app.io.start)
        self.assertEqual(state, (self.app.text, self.app.cursor, self.app.input_selection,
                                 list(self.app.calculator.history)))

    def test_io_enter_executes_input_when_calculator_history_was_selected(self):
        self.app.calculator.calculate("3+4")
        self.app.text, self.app.cursor = "2+2", 3
        self.app.history_index = 0
        self.app.history_part = "result"
        self.app.handle_key("F10")
        self.app.handle_key("ENTER")
        self.assertEqual(self.app.calculator.history[-1].result, "7")
        self.assertEqual(self.app.io.entries[-1], "4")
        self.assertEqual(self.app.text, "2+2")

    def test_io_calculations_and_errors_stay_out_of_main_and_saved_history(self):
        self.submit("2+3")
        history = list(self.app.calculator.history)
        history_file = self.app.history_path.read_bytes()
        problems_file = self.app.problems_path.read_bytes()
        self.app.handle_key("F10")
        for text in ("3*2", "1/0", ':forth "4*5" calc type', ':forth "1/0" calc'):
            self.submit(text)
            self.assertEqual(list(self.app.calculator.history), history)
        self.assertIn("6", self.app.io.entries)
        self.assertIn("20", self.app.io.entries)
        self.assertIn("Error: Division by zero.", self.app.io.entries)
        self.assertTrue(self.app.save_session())
        self.assertEqual(self.app.history_path.read_bytes(), history_file)
        self.assertEqual(self.app.problems_path.read_bytes(), problems_file)
        self.assertEqual(list(ConsoleApp(config_path=self.app.config_path).calculator.history), history)
        self.app.handle_key("F10")
        lines, _, _ = self.app.frame()
        self.assertIn("2+3 = 5", "\n".join(lines[2:2 + self.app.history_rows]))
        self.assertNotIn("3*2", "\n".join(lines[2:2 + self.app.history_rows]))
        self.submit("7*8")
        self.assertEqual(self.app.calculator.history[-1].result, "56")
        self.assertEqual(len(self.app.calculator.history), len(history) + 1)

    def test_io_approximation_and_assignment_work_without_creating_history(self):
        self.app.handle_key("F10")
        self.app.text, self.app.cursor = "1/3", 3
        self.app.handle_key("SHIFT_ENTER")
        self.assertTrue(self.app.io.entries[-1].startswith("0.333"))
        self.assertFalse(self.app.calculator.history)
        self.submit("6->x")
        self.submit("ans*2")
        self.assertEqual(self.app.io.entries[-1], "12")
        self.assertEqual(self.app.calculator.variables["x"].value, 6)
        self.assertEqual(self.app.calculator.answer.value, 12)
        self.assertFalse(self.app.calculator.history)

    def test_frames_wrap_unicode_and_resize_without_clipping_transcript(self):
        self.app.command(':forth "' + '界e\u0301' * 120 + '" type')
        original = list(self.app.io.entries)
        self.app.handle_key("F10")
        for width, height in ((100, 24), (40, 12), (160, 40), (20, 6)):
            with self.subTest(width=width, height=height):
                lines, _, cursor = self.app.frame(width, height)
                self.assertLessEqual(len(lines), height)
                self.assertTrue(all(display_width(line) <= width for line in lines))
                if width >= 40:
                    wrapped = self.app.io.wrapped_lines(width, display_width)
                    self.assertEqual("".join(wrapped), "".join(original))
                    self.assertIsNotNone(cursor)
        self.assertEqual(list(self.app.io.entries), original)

    def test_tabs_switch_and_invalid_pending_edits_stay_in_the_editor(self):
        self.app.handle_key("F7")
        for char in "sqrt(":
            self.app.handle_key(char)
        self.app.handle_key("F10")
        self.assertTrue(self.app.equation_open)
        self.assertFalse(self.app.io_open)
        self.app.handle_key("ESC")
        for target in ("F7", "F8", "F1", "F9"):
            self.app.handle_key("F10")
            self.assertTrue(self.app.io_open)
            self.app.handle_key(target)
            self.assertFalse(self.app.io_open)
            self.app.handle_key("ESC")
        self.app.handle_key("F10")
        self.submit(":help")
        self.app.handle_key("ESC")
        self.assertFalse(self.app.help_open)
        self.assertTrue(self.app.io_open)

    def test_io_is_shared_between_problems_and_does_not_replace_plain_output(self):
        self.app.command(":words")
        self.app.new_problem("Another")
        self.assertIn("> :words", self.app.io.entries)
        with patch("sys.stdin", io.StringIO(':forth ." first" cr ." second"\n:quit\n')), \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(["--plain", "--config", str(self.app.config_path)]), 0)
        self.assertIn("first\nsecond", output.getvalue())

    def test_windows_and_posix_f10_input(self):
        keyboard = Mock()
        keyboard.getwch.side_effect = ["\x00", "D"]
        with patch("os.name", "nt"), patch.dict("sys.modules", {"msvcrt": keyboard}):
            self.assertEqual(Terminal().read_key(), "F10")
        with patch("os.name", "posix"), patch("sys.stdin") as stdin, \
                patch("select.select", return_value=([0], [], [])), \
                patch("os.read", side_effect=[bytes([char]) for char in b"\x1b[21~"]):
            stdin.fileno.return_value = 0
            self.assertEqual(Terminal().read_key(), "F10")


class TranscriptTests(unittest.TestCase):
    def test_scrollback_is_bounded_and_new_output_follows_tail(self):
        transcript = IOTranscript(max_characters=20)
        transcript.append("first entry")
        transcript.append("second entry")
        self.assertEqual(list(transcript.entries), ["second entry"])
        self.assertTrue(transcript.discarded)
        transcript.scroll("HOME", 80, 1, display_width)
        self.assertEqual(transcript.start, 0)
        transcript.append("third entry")
        self.assertIsNone(transcript.start)
        self.assertEqual(list(transcript.entries), ["third entry"])


if __name__ == "__main__":
    unittest.main()
