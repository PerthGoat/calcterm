"""Platform keyboard and mouse input with ANSI rendering and restoration."""

from __future__ import annotations

from contextlib import suppress
from functools import lru_cache
import os
import re
import shutil
import sys
import time

from .core import CalcError
from .syntax import colorize_line
from .terminal_input import CONTROL_KEYS, MouseClick, WindowsConsoleInput


# Map Windows extended keys and POSIX escape sequences to shared UI key names.
WINDOWS_KEYS = {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT", "G": "HOME", "O": "END", "R": "INSERT",
                "I": "PAGEUP", "Q": "PAGEDOWN", "S": "DELETE", ";": "F1", "<": "F2", "=": "F3",
                ">": "F4", "?": "F5", "@": "F6", "A": "F7", "B": "F8", "C": "F9", "D": "F10", "Z": "SHIFT_F7"}
ANSI_KEYS = {"\x1b[A": "UP", "\x1b[B": "DOWN", "\x1b[C": "RIGHT", "\x1b[D": "LEFT",
             "\x1b[2~": "INSERT",
             "\x1b[1;2D": "SHIFT_LEFT", "\x1b[1;2C": "SHIFT_RIGHT",
             "\x1b[H": "HOME", "\x1b[F": "END", "\x1b[1~": "HOME", "\x1b[4~": "END",
             "\x1b[7~": "HOME", "\x1b[8~": "END", "\x1b[3~": "DELETE", "\x1b[5~": "PAGEUP",
             "\x1b[6~": "PAGEDOWN", "\x1bOP": "F1", "\x1bOQ": "F2", "\x1bOR": "F3",
             "\x1bOS": "F4", "\x1b[11~": "F1", "\x1b[12~": "F2", "\x1b[13~": "F3",
             "\x1b[14~": "F4", "\x1b[15~": "F5", "\x1b[17~": "F6", "\x1b[18~": "F7", "\x1b[19~": "F8", "\x1b[20~": "F9",
             "\x1b[21~": "F10",
             "\x1b[18;2~": "SHIFT_F7",
             "\x1bOH": "HOME", "\x1bOF": "END"}
SGR_MOUSE = re.compile(rb"\x1b\[<([0-9]+);([0-9]+);([0-9]+)M")


def _mouse_press(button: int, column: int, row: int) -> MouseClick | None:
    # Ignore modifier bits when recognizing a left press. Movement, wheels and releases have other bits.
    if button & ~0x1c == 0 and column > 0 and row > 0:
        return MouseClick(row - 1, column - 1)
    return None


def windows_shift_pressed():
    # msvcrt uses the same arrow/Enter codes with and without Shift.
    import ctypes
    loader = getattr(ctypes, "WinDLL", None)
    return loader is not None and bool(_windows_key_state(loader)(0x10) & 0x8000)


@lru_cache(maxsize=1)
def _windows_key_state(loader):
    import ctypes
    user32 = loader("user32", use_last_error=True)
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    return user32.GetAsyncKeyState


def windows_console_focused():
    """Check this console's window, including its Windows Terminal owner."""
    import ctypes
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        return False
    console_window, foreground_window, ancestor = _windows_console_api(loader)
    console, foreground = console_window(), foreground_window()
    # Windows Terminal owns its hidden ConPTY console window.
    return bool(console and foreground and (foreground == console or foreground == ancestor(console, 3)))


@lru_cache(maxsize=1)
def _windows_console_api(loader):
    from ctypes import wintypes

    kernel32 = loader("kernel32", use_last_error=True)
    user32 = loader("user32", use_last_error=True)
    kernel32.GetConsoleWindow.argtypes = []
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND

    return kernel32.GetConsoleWindow, user32.GetForegroundWindow, user32.GetAncestor


def modified_terminal_key(sequence):
    """Decode CSI-u or xterm modifyOtherKeys reports for character keys."""
    if len(sequence) > 64:
        return "UNKNOWN"
    match = re.fullmatch(r"\x1b\[([0-9]+);([0-9]+)u", sequence)
    if match:
        codepoint, modifiers = map(int, match.groups())
    else:
        match = re.fullmatch(r"\x1b\[27;([0-9]+);([0-9]+)~", sequence)
        if not match:
            return "UNKNOWN"
        modifiers, codepoint = map(int, match.groups())
    if not 0 <= codepoint <= 0x10ffff or modifiers < 1:
        return "UNKNOWN"
    modifiers = (modifiers - 1) & 63  # Ignore Caps Lock / Num Lock flags.
    if codepoint in (10, 13) and modifiers in (0, 1, 4, 5):
        return "SHIFT_ENTER" if modifiers & 1 else "ENTER"
    if modifiers in (4, 5) and 65 <= codepoint <= 122:
        return CONTROL_KEYS.get(chr(codepoint & 31), "UNKNOWN")
    if modifiers in (0, 1):
        char = chr(codepoint)
        return CONTROL_KEYS.get(char, char if char.isprintable() else "UNKNOWN")
    return "UNKNOWN"


class Terminal:
    """Interactive input and ANSI output, restoring console state on every exit."""

    def __init__(self):
        self.size = None
        self._pending_byte = b""
        self._pending_wchar = ""
        self._windows_input: WindowsConsoleInput | None = None

    def __enter__(self):
        # Save the host console settings before enabling interactive terminal behavior.
        self.old_mode = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.GetStdHandle.argtypes = [wintypes.DWORD]
            self.kernel.GetStdHandle.restype = wintypes.HANDLE
            self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.handle = self.kernel.GetStdHandle(-11 & 0xffffffff)
            # Windows needs virtual terminal processing (0x0004) for ANSI output.
            mode = wintypes.DWORD()
            if not self.kernel.GetConsoleMode(self.handle, ctypes.byref(mode)):
                raise CalcError("Interactive mode needs a Windows console. Use --plain in redirected shells.")
            if not self.kernel.SetConsoleMode(self.handle, mode.value | 0x0004):
                raise CalcError("This console does not support ANSI output. Use --plain.")
            self.old_mode = mode.value
        else:
            import termios
            import tty
            self.old_mode = termios.tcgetattr(sys.stdin.fileno())
        try:
            # Use the alternate screen and ask supporting POSIX terminals for modified keys.
            startup = "\x1b[?1049h\x1b[2J\x1b[H"
            if os.name == "nt":
                self._windows_input = WindowsConsoleInput.open(self.kernel, self.handle)
            else:
                tty.setraw(sys.stdin.fileno())
                startup += "\x1b[>4;2m\x1b[?1000;1006h"
            sys.stdout.write(startup)
            sys.stdout.flush()
        except BaseException:
            # Python calls __exit__ only after __enter__ succeeds.
            with suppress(OSError, ValueError):
                self.__exit__()
            raise
        return self

    def __exit__(self, *args):
        # Restore the cursor, screen, and console settings even when the app raises.
        try:
            if os.name != "nt":
                sys.stdout.write("\x1b[?1000;1006l\x1b[>4m")
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        finally:
            if self._windows_input is not None:
                self._windows_input.close()
                self._windows_input = None
            if self.old_mode is not None:
                if os.name == "nt":
                    self.kernel.SetConsoleMode(self.handle, self.old_mode)
                else:
                    import termios
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_mode)

    def read_key(self, timeout: float | None = None) -> str | MouseClick | None:
        """Read a key or click, returning None when no actionable event arrives."""
        if os.name == "nt":
            if self._windows_input is not None:
                return self._windows_input.read(timeout)
            import msvcrt
            if not self._pending_wchar and timeout is not None:
                deadline = time.monotonic() + timeout
                while not msvcrt.kbhit():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    time.sleep(min(0.01, remaining))
            char, self._pending_wchar = self._pending_wchar or msvcrt.getwch(), ""
            if char in ("\x00", "\xe0"):
                # Windows extended keys arrive as a prefix followed by a key code.
                key = WINDOWS_KEYS.get(msvcrt.getwch(), "UNKNOWN")
                if key in ("LEFT", "RIGHT", "F7") and windows_shift_pressed():
                    return "SHIFT_" + key
                return key
            if 0xd800 <= ord(char) <= 0xdbff:
                # Join UTF-16 surrogate pairs into one Unicode character.
                following = msvcrt.getwch()
                if 0xdc00 <= ord(following) <= 0xdfff:
                    return (char + following).encode("utf-16", "surrogatepass").decode("utf-16")
                self._pending_wchar = following
                return "UNKNOWN"
            if 0xdc00 <= ord(char) <= 0xdfff:
                return "UNKNOWN"
            if char in ("\r", "\n") and windows_shift_pressed():
                return "SHIFT_ENTER"
        else:
            # Read bytes directly: TextIO buffering can otherwise swallow pasted keys.
            import select
            if not self._pending_byte and timeout is not None and not select.select([sys.stdin], [], [], timeout)[0]:
                return None
            fd = sys.stdin.fileno()
            char, self._pending_byte = self._pending_byte or os.read(fd, 1), b""
            if not char:
                return "CTRL_D"
            if char == b"\x1b":
                # A short lookahead distinguishes Esc alone from a multi-byte key sequence.
                sequence = char
                while len(sequence) < 64 and select.select([sys.stdin], [], [], 0.04)[0]:
                    following = os.read(fd, 1)
                    if not following:
                        break
                    if len(sequence) == 1 and following not in (b"[", b"O"):
                        self._pending_byte = following
                        return "ESC"
                    if not b" " <= following <= b"~":
                        self._pending_byte = following
                        return "UNKNOWN"
                    sequence += following
                    if sequence == b"\x1b[M":
                        # Terminals without SGR reporting send three encoded bytes after CSI M.
                        payload = []
                        for _ in range(3):
                            if not select.select([sys.stdin], [], [], 0.04)[0]:
                                return "UNKNOWN"
                            byte = os.read(fd, 1)
                            if not byte:
                                return "UNKNOWN"
                            if byte[0] < 32:
                                self._pending_byte = byte
                                return "UNKNOWN"
                            payload.append(byte[0] - 32)
                        return _mouse_press(*payload)
                    if sequence.startswith(b"\x1b[<") and following in (b"M", b"m"):
                        match = SGR_MOUSE.fullmatch(sequence)
                        return _mouse_press(*map(int, match.groups())) if match else None
                    text = sequence.decode("ascii", "replace")
                    if text in ANSI_KEYS:
                        return ANSI_KEYS[text]
                    modified = modified_terminal_key(text)
                    if modified != "UNKNOWN":
                        return modified
                    if len(sequence) > 2 and sequence[-1:] in b"~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
                        break
                return "ESC" if sequence == b"\x1b" else "UNKNOWN"
            first = char[0]
            if first >= 0x80 and not 0xc2 <= first <= 0xf4:
                return "UNKNOWN"
            required = 1 if first < 0x80 else 2 if first < 0xe0 else 3 if first < 0xf0 else 4
            while len(char) < required:
                if not select.select([sys.stdin], [], [], 0.04)[0]:
                    return "UNKNOWN"
                following = os.read(fd, 1)
                if not following:
                    return "UNKNOWN"
                if not 0x80 <= following[0] <= 0xbf:
                    self._pending_byte = following
                    return "UNKNOWN"
                char += following
            try:
                char = char.decode("utf-8")
            except UnicodeDecodeError:
                return "UNKNOWN"
        return CONTROL_KEYS.get(char, char)

    def render(self, app):
        width, height = shutil.get_terminal_size((100, 24))
        # Leave the last column unused so writing a full row cannot trigger scrolling.
        lines, selected, cursor = app.frame(max(1, width - 1), height)
        output = ["\x1b[?25l\x1b[H"]
        if self.size != (width, height):
            output.append("\x1b[2J")
        self.size = (width, height)
        # Apply ANSI highlighting to the plain frame, then write the completed redraw
        # in one batch. Frame coordinates for the cursor are already one-based.
        for row, line in enumerate(lines):
            output.append(f"\x1b[{row + 1};1H\x1b[2K")
            highlights = list(app.syntax_highlights.get(row, ()))
            if row == 0:
                highlights.extend(app.function_highlights)
            output.append(colorize_line(line, highlights, selected.get(row)))
        if cursor:
            output.append(f"\x1b[{cursor[0]};{cursor[1]}H\x1b[?25h")
        sys.stdout.write("".join(output))
        sys.stdout.flush()

    def run(self, app):
        # Poll modifiers as well as input so a bare Shift press/release can redraw.
        app.shift_pressed = self.read_shift_state()
        self.render(app)
        while app.running:
            event = self.read_key(timeout=0.1)
            if isinstance(event, MouseClick):
                if shutil.get_terminal_size((100, 24)) == self.size:
                    app.handle_click(event.row, event.column)
            elif event is not None:
                app.handle_key(event)
            if not app.running:
                break
            shift_pressed = self.read_shift_state()
            shift_changed = shift_pressed != app.shift_pressed
            app.shift_pressed = shift_pressed
            if event is not None or shift_changed or shutil.get_terminal_size((100, 24)) != self.size:
                self.render(app)

    def read_shift_state(self):
        # POSIX character reports do not provide reliable standalone modifier releases.
        # Do not infer a held key from the last Shift shortcut, which could stick on.
        # Only display held modifiers while this console's window is focused.
        return (windows_console_focused() and windows_shift_pressed()) if os.name == "nt" else False
