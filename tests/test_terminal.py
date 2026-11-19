import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import Mock, patch

from calcterm.terminal import windows_console_focused


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
