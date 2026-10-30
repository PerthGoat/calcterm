"""Platform keyboard input and ANSI rendering with terminal restoration."""

from __future__ import annotations

import os
import re
import shutil
import sys
import time

from .core import CalcError
from .syntax import colorize_line


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
CONTROL_KEYS = {"\r": "ENTER", "\n": "ENTER", "\x1b": "ESC", "\t": "TAB", "\x08": "BACKSPACE",
                "\x7f": "BACKSPACE", "\x03": "CTRL_C", "\x04": "CTRL_D", "\x15": "CTRL_U", "\x0c": "CTRL_L",
                "\x14": "CTRL_T"}


def windows_shift_pressed():
    # msvcrt uses the same arrow/Enter codes with and without Shift.
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    return bool(user32.GetAsyncKeyState(0x10) & 0x8000)


def modified_terminal_key(sequence):
    """Decode CSI-u or xterm modifyOtherKeys reports for character keys."""
    match = re.fullmatch(r"\x1b\[(\d+);(\d+)u", sequence)
    if match:
        codepoint, modifiers = map(int, match.groups())
    else:
        match = re.fullmatch(r"\x1b\[27;(\d+);(\d+)~", sequence)
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
    """Raw key input plus ANSI output, restoring console state on every exit."""

    def __init__(self):
        self.size = None

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
            # Raw mode delivers individual keys without waiting for Enter or echoing them.
            tty.setraw(sys.stdin.fileno())
        # Use the alternate screen so the user's previous terminal contents survive exit.
        sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H")
        if os.name != "nt":
            # Ask supporting terminals to distinguish Shift+Enter from Enter.
            sys.stdout.write("\x1b[>4;2m")
        sys.stdout.flush()
        return self

    def __exit__(self, *args):
        # Restore the cursor, screen, and console settings even when the app raises.
        try:
            if os.name != "nt":
                sys.stdout.write("\x1b[>4m")
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        finally:
            if self.old_mode is not None:
                if os.name == "nt":
                    self.kernel.SetConsoleMode(self.handle, self.old_mode)
                else:
                    import termios
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_mode)

    def read_key(self, timeout: float | None = None) -> str | None:
        """Read one key, returning None on timeout so idle resizes can be handled."""
        if os.name == "nt":
            import msvcrt
            if timeout is not None:
                deadline = time.monotonic() + timeout
                while not msvcrt.kbhit():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    time.sleep(min(0.01, remaining))
            char = msvcrt.getwch()
            if char in ("\x00", "\xe0"):
                # Windows extended keys arrive as a prefix followed by a key code.
                key = WINDOWS_KEYS.get(msvcrt.getwch(), "UNKNOWN")
                if key in ("LEFT", "RIGHT", "F7") and windows_shift_pressed():
                    return "SHIFT_" + key
                return key
            if 0xd800 <= ord(char) <= 0xdbff:
                # Join UTF-16 surrogate pairs into one Unicode character.
                following = msvcrt.getwch()
                return (char + following).encode("utf-16", "surrogatepass").decode("utf-16")
            if char in ("\r", "\n") and windows_shift_pressed():
                return "SHIFT_ENTER"
        else:
            # Read bytes directly: TextIO buffering can otherwise swallow pasted keys.
            import select
            if timeout is not None and not select.select([sys.stdin], [], [], timeout)[0]:
                return None
            char = os.read(sys.stdin.fileno(), 1)
            if not char:
                return "CTRL_D"
            if char == b"\x1b":
                # A short lookahead distinguishes Esc alone from a multi-byte key sequence.
                sequence = char
                while select.select([sys.stdin], [], [], 0.04)[0]:
                    sequence += os.read(sys.stdin.fileno(), 1)
                    text = sequence.decode("ascii", "ignore")
                    if text in ANSI_KEYS:
                        return ANSI_KEYS[text]
                    modified = modified_terminal_key(text)
                    if modified != "UNKNOWN":
                        return modified
                    if len(sequence) > 2 and sequence[-1:] in b"~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
                        break
                return "ESC" if sequence == b"\x1b" else "UNKNOWN"
            required = 1 if char[0] < 0x80 else 2 if char[0] < 0xe0 else 3 if char[0] < 0xf0 else 4
            # Read the rest of a UTF-8 character before passing it to the editor.
            while len(char) < required:
                char += os.read(sys.stdin.fileno(), 1)
            char = char.decode("utf-8", "replace")
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
            output.append(colorize_line(line, app.syntax_highlights.get(row, ()), selected.get(row)))
        if cursor:
            output.append(f"\x1b[{cursor[0]};{cursor[1]}H\x1b[?25h")
        sys.stdout.write("".join(output))
        sys.stdout.flush()

    def run(self, app):
        # Poll modifiers as well as input so a bare Shift press/release can redraw.
        app.shift_pressed = self.read_shift_state()
        self.render(app)
        while app.running:
            key = self.read_key(timeout=0.1)
            if key is not None:
                app.handle_key(key)
            if not app.running:
                break
            shift_pressed = self.read_shift_state()
            shift_changed = shift_pressed != app.shift_pressed
            app.shift_pressed = shift_pressed
            if key is not None or shift_changed or shutil.get_terminal_size((100, 24)) != self.size:
                self.render(app)

    def read_shift_state(self):
        # POSIX character reports do not provide reliable standalone modifier releases.
        # Do not infer a held key from the last Shift shortcut, which could stick on.
        return windows_shift_pressed() if os.name == "nt" else False
