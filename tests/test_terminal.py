import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import Mock, call, patch

from calcterm.terminal import Terminal, windows_console_focused
from calcterm.terminal_input import MouseClick, _InputRecord


class TerminalReadTests(unittest.TestCase):
    def test_windows_restores_console_mode_after_startup_failure(self):
        def get_console_mode(handle, mode):
            mode._obj.value = 0x0241 if handle == 456 else 1
            return True

        kernel = Mock()
        kernel.GetStdHandle.side_effect = [123, 456]
        kernel.GetConsoleMode.side_effect = get_console_mode
        with patch("os.name", "nt"), patch.object(ctypes, "WinDLL", create=True, return_value=kernel), \
                patch("sys.stdout") as stdout:
            stdout.flush.side_effect = OSError("Failed to initialize screen")
            with self.assertRaisesRegex(OSError, "Failed to initialize screen"):
                with Terminal():
                    self.fail("Terminal entered after a failed startup")
        self.assertEqual(kernel.SetConsoleMode.call_args_list,
                         [call(123, 5), call(456, 0x0090), call(456, 0x0241), call(123, 1)])

    def test_posix_decodes_sgr_and_legacy_left_presses(self):
        for sequence, expected in (
                (b"\x1b[<0;45;8M", MouseClick(7, 44)),
                (b"\x1b[<4;45;8M", MouseClick(7, 44)),
                (b"\x1b[<0;45;8m", None),
                (b"\x1b[<1;45;8M", None),
                (b"\x1b[<64;45;8M", None),
                (b"\x1b[<0;0;8M", None),
                (b"\x1b[M" + bytes((32, 152, 92)), MouseClick(59, 119))):
            with self.subTest(sequence=sequence), patch("os.name", "posix"), patch("sys.stdin"), \
                    patch("select.select", return_value=([0], [], [])), \
                    patch("os.read", side_effect=[bytes((byte,)) for byte in sequence + b"x"]):
                terminal = Terminal()
                self.assertEqual(terminal.read_key(), expected)
                self.assertEqual(terminal.read_key(), "x")

    def test_windows_native_reader_delivers_mouse_and_keyboard_events(self):
        def mouse(buttons, flags=0):
            record = _InputRecord(event_type=2)
            mouse_event = record.event.mouse
            mouse_event.column, mouse_event.row, mouse_event.buttons, mouse_event.flags = 10, 15, buttons, flags
            return record

        def key(code, character=0, modifiers=0, repeat=1):
            record = _InputRecord(event_type=1)
            key_event = record.event.key
            key_event.down, key_event.repeat, key_event.virtual_key = 1, repeat, code
            key_event.character, key_event.modifiers = character, modifiers
            return record

        records = iter([mouse(0, 1), mouse(2), mouse(1), mouse(1, 1), mouse(3), mouse(0), mouse(1, 2),
                        key(0x76, modifiers=16), key(0x25, modifiers=16), key(0, 13, 16),
                        key(0, 0x221A, repeat=2), key(0, 0xD83D), key(0, 0xDE00), key(0, 3)])

        def read_record(handle, record, length, count):
            ctypes.memmove(record, ctypes.byref(next(records)), ctypes.sizeof(_InputRecord))
            count._obj.value = 1
            return True

        def screen_info(handle, info):
            info._obj.left, info._obj.top = 3, 7
            return True

        kernel = Mock()
        kernel.GetStdHandle.side_effect = [123, 456]
        kernel.WaitForSingleObject.return_value = 0
        kernel.ReadConsoleInputW.side_effect = read_record
        kernel.GetConsoleScreenBufferInfo.side_effect = screen_info
        with patch("os.name", "nt"), patch.object(ctypes, "WinDLL", create=True, return_value=kernel), patch("sys.stdout"):
            with Terminal() as terminal:
                expected = [MouseClick(8, 7), MouseClick(8, 7), "SHIFT_F7", "SHIFT_LEFT", "SHIFT_ENTER", "√", "√", "😀", "CTRL_C"]
                self.assertEqual([terminal.read_key(timeout=0.1) for _ in expected], expected)
                kernel.WaitForSingleObject.return_value = 0x0102
                self.assertIsNone(terminal.read_key(timeout=0.1))
        self.assertEqual(kernel.SetConsoleMode.call_args_list[-2:], [call(456, 0), call(123, 0)])

    def test_posix_incomplete_sequences_return_at_eof(self):
        for sequence, expected in ((b"\x1b", "ESC"), (b"\x1b[", "UNKNOWN"), (b"\xe2\x82", "UNKNOWN")):
            with self.subTest(sequence=sequence), patch("os.name", "posix"), patch("sys.stdin"), \
                    patch("select.select", return_value=([0], [], [])), \
                    patch("os.read", side_effect=[*(bytes((byte,)) for byte in sequence), b"", b""]):
                terminal = Terminal()
                self.assertEqual(terminal.read_key(), expected)
                self.assertEqual(terminal.read_key(), "CTRL_D")

    def test_posix_invalid_utf8_keeps_following_ascii_key(self):
        with patch("os.name", "posix"), patch("sys.stdin"), \
                patch("select.select", return_value=([0], [], [])), \
                patch("os.read", side_effect=[b"\xe2", b"a"]):
            terminal = Terminal()
            self.assertEqual(terminal.read_key(), "UNKNOWN")
            self.assertEqual(terminal.read_key(), "a")

    def test_windows_invalid_surrogate_keeps_following_key(self):
        keyboard = Mock()
        keyboard.getwch.side_effect = ["\ud800", "a"]
        with patch("os.name", "nt"), patch.dict("sys.modules", {"msvcrt": keyboard}):
            terminal = Terminal()
            self.assertEqual(terminal.read_key(), "UNKNOWN")
            self.assertEqual(terminal.read_key(), "a")


class WindowsConsoleFocusTests(unittest.TestCase):
    def test_focus_matches_our_console_or_its_terminal_owner(self):
        # Handles exceed 32 bits to guard against truncating HWNDs on 64-bit Windows.
        console, terminal, other = 0x100000001, 0x100000002, 0x100000003
        for foreground, root_owner, expected in (
                (console, console, True),
                (terminal, terminal, True),
                (other, terminal, False),
                (other, console, False),
                (other, None, False),
                (None, terminal, False)):
            with self.subTest(foreground=foreground, root_owner=root_owner):
                kernel32, user32 = Mock(), Mock()
                kernel32.GetConsoleWindow.return_value = console
                user32.GetForegroundWindow.return_value = foreground
                user32.GetAncestor.return_value = root_owner
                with patch.object(ctypes, "WinDLL", create=True, side_effect=[kernel32, user32]):
                    self.assertEqual(windows_console_focused(), expected)
                self.assertEqual(kernel32.GetConsoleWindow.restype, wintypes.HWND)
                self.assertEqual(user32.GetForegroundWindow.restype, wintypes.HWND)
                self.assertEqual(user32.GetAncestor.restype, wintypes.HWND)
                self.assertEqual(user32.GetAncestor.argtypes, [wintypes.HWND, wintypes.UINT])
                if foreground and foreground != console:
                    user32.GetAncestor.assert_called_once_with(console, 3)
                else:
                    user32.GetAncestor.assert_not_called()

    def test_missing_console_never_counts_as_focused(self):
        for foreground in (None, 123):
            with self.subTest(foreground=foreground):
                kernel32, user32 = Mock(), Mock()
                kernel32.GetConsoleWindow.return_value = None
                user32.GetForegroundWindow.return_value = foreground
                with patch.object(ctypes, "WinDLL", create=True, side_effect=[kernel32, user32]):
                    self.assertFalse(windows_console_focused())
                user32.GetAncestor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
