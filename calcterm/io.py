"""Session command transcript with terminal-cell wrapping and scrollback."""

from collections import deque
from itertools import islice


DISCARDED = "(Older IO entries removed from scrollback.)"


class IOTranscript:
    def __init__(self, max_characters=4 * 1024 * 1024):
        self.entries = deque()
        self.max_characters = max_characters
        self.characters = 0
        self.start = None  # Follow the newest output until the user scrolls.
        self.discarded = False
        self._wrap_key = None
        self._lines: deque[str] = deque()
        self._line_counts: deque[int] = deque()

    def append(self, text):
        if not text:
            return
        if len(text) > self.max_characters:
            self.discarded = True
            text = text[-self.max_characters:] if self.max_characters > 0 else ""
        while self.entries and self.characters + len(text) > self.max_characters:
            self.characters -= len(self.entries.popleft())
            self.discarded = True
            if self._line_counts:
                for _ in range(self._line_counts.popleft()):
                    self._lines.popleft()
        if text:
            self.entries.append(text)
            self.characters += len(text)
        self.start = None

    def _wrap(self, width, measure):
        width = max(1, width)
        key = width, measure
        if self._wrap_key != key:
            self._wrap_key = key
            self._lines.clear()
            self._line_counts.clear()
        pending = len(self.entries) - len(self._line_counts)
        for entry in reversed(list(islice(reversed(self.entries), pending))):
            before = len(self._lines)
            for raw in entry.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4).split("\n"):
                text = raw if raw.isprintable() else "".join(char if char.isprintable() else " " for char in raw)
                start, used = 0, 0
                for index, char in enumerate(text):
                    cells = measure(char)
                    if index > start and used + cells > width:
                        self._lines.append(text[start:index])
                        start, used = index, 0
                    used += cells
                self._lines.append(text[start:])
            self._line_counts.append(len(self._lines) - before)

    def wrapped_lines(self, width, measure):
        self._wrap(width, measure)
        return [DISCARDED, *self._lines] if self.discarded else list(self._lines)

    def window(self, width, rows, measure):
        self._wrap(width, measure)
        banner_rows = int(self.discarded)
        total = len(self._lines) + banner_rows
        last = max(0, total - rows)
        first = last if self.start is None else max(0, min(last, self.start))
        if self.start is not None:
            self.start = first
        stop = min(total, first + rows)
        begin, end = max(0, first - banner_rows), max(0, stop - banner_rows)
        if begin <= len(self._lines) - end:
            lines = list(islice(self._lines, begin, end))
        else:
            lines = list(islice(reversed(self._lines), len(self._lines) - end, len(self._lines) - begin))
            lines.reverse()
        if self.discarded and first == 0 and stop:
            lines.insert(0, DISCARDED)
        return lines, first, total

    def scroll(self, key, width, rows, measure):
        _, first, total = self.window(width, rows, measure)
        last = max(0, total - rows)
        if key == "HOME":
            self.start = 0
        elif key == "END":
            self.start = None
        else:
            delta = {"UP": -1, "DOWN": 1, "PAGEUP": -rows, "PAGEDOWN": rows}[key]
            self.start = max(0, min(last, first + delta))
            if self.start == last:
                self.start = None
