"""Shared input events and the native Windows console input reader."""

from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
import math
import time


CONTROL_KEYS = {"\r": "ENTER", "\n": "ENTER", "\x1b": "ESC", "\t": "TAB", "\x08": "BACKSPACE",
                "\x7f": "BACKSPACE", "\x03": "CTRL_C", "\x04": "CTRL_D", "\x15": "CTRL_U", "\x0c": "CTRL_L",
                "\x14": "CTRL_T"}
VIRTUAL_KEYS = {0x21: "PAGEUP", 0x22: "PAGEDOWN", 0x23: "END", 0x24: "HOME", 0x25: "LEFT",
                0x26: "UP", 0x27: "RIGHT", 0x28: "DOWN", 0x2D: "INSERT", 0x2E: "DELETE",
                **{0x70 + index: f"F{index + 1}" for index in range(10)}}
SHIFT_KEYS = {"LEFT", "RIGHT", "F7", "ENTER"}


@dataclass(frozen=True)
class MouseClick:
    """A left-button press in zero-based terminal cells."""

    row: int
    column: int


class _KeyEvent(ct.Structure):
    _fields_ = [("down", ct.c_int32), ("repeat", ct.c_uint16), ("virtual_key", ct.c_uint16),
                ("scan_code", ct.c_uint16), ("character", ct.c_uint16), ("modifiers", ct.c_uint32)]


class _MouseEvent(ct.Structure):
    _fields_ = [("column", ct.c_int16), ("row", ct.c_int16), ("buttons", ct.c_uint32),
                ("modifiers", ct.c_uint32), ("flags", ct.c_uint32)]


class _InputEvent(ct.Union):
    _fields_ = [("key", _KeyEvent), ("mouse", _MouseEvent)]


class _InputRecord(ct.Structure):
    _fields_ = [("event_type", ct.c_uint16), ("event", _InputEvent)]


class _ScreenBufferInfo(ct.Structure):
    _fields_ = [("size", ct.c_int16 * 2), ("cursor", ct.c_int16 * 2), ("attributes", ct.c_uint16),
                ("left", ct.c_int16), ("top", ct.c_int16), ("right", ct.c_int16), ("bottom", ct.c_int16),
                ("maximum_size", ct.c_int16 * 2)]


class WindowsConsoleInput:
    """Decode keyboard and mouse records from the same Windows input buffer."""

    def __init__(self, kernel, handle, output, mode):
        from ctypes import wintypes

        self.kernel, self.handle, self.output, self.old_mode = kernel, handle, output, mode
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ct.POINTER(_InputRecord),
                                             wintypes.DWORD, ct.POINTER(wintypes.DWORD)]
        kernel.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ct.POINTER(_ScreenBufferInfo)]
        self.count = wintypes.DWORD()
        self.record = _InputRecord()
        self.screen = _ScreenBufferInfo()
        self.left_down = False
        self.surrogate = 0
        self.repeated_key = ""
        self.repeat_count = 0

    @classmethod
    def open(cls, kernel, output) -> WindowsConsoleInput | None:
        from ctypes import wintypes

        handle = kernel.GetStdHandle(-10 & 0xffffffff)
        mode = wintypes.DWORD()
        if not kernel.GetConsoleMode(handle, ct.byref(mode)):
            return None
        reader = cls(kernel, handle, output, mode.value)
        # Enable mouse events and disable Quick Edit, processed Ctrl+C and VT keyboard input.
        mouse_mode = (mode.value | 0x0010 | 0x0080) & ~(0x0040 | 0x0001 | 0x0200)
        return reader if kernel.SetConsoleMode(handle, mouse_mode) else None

    def close(self):
        self.kernel.SetConsoleMode(self.handle, self.old_mode)

    def _key(self, event: _KeyEvent) -> str | None:
        code = event.character
        # Windows can deliver Alt-numpad characters on the Alt key release.
        if not event.down and not (event.virtual_key == 0x12 and code):
            return None
        if 0xd800 <= code <= 0xdbff:
            self.surrogate = code
            return None
        leading, self.surrogate = self.surrogate, 0
        if 0xdc00 <= code <= 0xdfff:
            if not leading:
                return None
            code = 0x10000 + ((leading - 0xd800) << 10) + code - 0xdc00
        char = chr(code)
        key = VIRTUAL_KEYS.get(event.virtual_key) or CONTROL_KEYS.get(char)
        if key is None:
            return char if char.isprintable() else None
        return "SHIFT_" + key if event.modifiers & 0x0010 and key in SHIFT_KEYS else key

    def _mouse(self, event: _MouseEvent) -> MouseClick | None:
        was_down, self.left_down = self.left_down, bool(event.buttons & 1)
        if event.flags not in (0, 2) or not self.left_down or was_down:
            return None
        if not self.kernel.GetConsoleScreenBufferInfo(self.output, ct.byref(self.screen)):
            return None
        return MouseClick(event.row - self.screen.top, event.column - self.screen.left)

    def read(self, timeout: float | None) -> str | MouseClick | None:
        if self.repeat_count:
            self.repeat_count -= 1
            return self.repeated_key
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            wait = 0xffffffff if deadline is None else max(0, math.ceil((deadline - time.monotonic()) * 1000))
            status = self.kernel.WaitForSingleObject(self.handle, wait)
            if status == 0x0102:  # WAIT_TIMEOUT
                return None
            if status != 0 or not self.kernel.ReadConsoleInputW(self.handle, ct.byref(self.record), 1, ct.byref(self.count)):
                return "CTRL_D"
            if self.count.value:
                if self.record.event_type == 1:  # KEY_EVENT
                    key = self._key(self.record.event.key)
                    if key is not None:
                        self.repeated_key = key
                        self.repeat_count = max(0, self.record.event.key.repeat - 1)
                        return key
                elif self.record.event_type == 2:  # MOUSE_EVENT
                    click = self._mouse(self.record.event.mouse)
                    if click is not None:
                        return click
                elif self.record.event_type == 0x10:  # FOCUS_EVENT
                    self.left_down = False
            if deadline is not None and time.monotonic() >= deadline:
                return None
