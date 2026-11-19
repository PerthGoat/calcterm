import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import Mock, call, patch

from calcterm.terminal import Terminal, windows_console_focused


class TerminalReadTests(unittest.TestCase):
    def test_windows_restores_console_mode_after_startup_failure(self):
        def get_console_mode(handle, mode):
            mode._obj.value = 1
            return True

        kernel = Mock()
        kernel.GetStdHandle.return_value = 123
        kernel.GetConsoleMode.side_effect = get_console_mode
        with patch("os.name", "nt"), patch.object(ctypes, "WinDLL", create=True, return_value=kernel), \
                patch("sys.stdout") as stdout:
            stdout.flush.side_effect = OSError("Failed to initialize screen")
            with self.assertRaisesRegex(OSError, "Failed to initialize screen"):
                with Terminal():
                    self.fail("Terminal entered after a failed startup")
        self.assertEqual(kernel.SetConsoleMode.call_args_list, [call(123, 5), call(123, 1)])

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
