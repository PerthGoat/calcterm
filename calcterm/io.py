"""Session command transcript with terminal-cell wrapping and scrollback."""

from collections import deque


class IOTranscript:
    def __init__(self, max_characters=4 * 1024 * 1024):
        self.entries = deque()
        self.max_characters = max_characters
        self.characters = 0
        self.start = None  # Follow the newest output until the user scrolls.
        self.discarded = False
        self._cache = None

    def append(self, text):
        self.entries.append(text)
        self.characters += len(text)
        while self.characters > self.max_characters and len(self.entries) > 1:
            self.characters -= len(self.entries.popleft())
            self.discarded = True
        self.start = None
        self._cache = None

    def wrapped_lines(self, width, measure):
        width = max(1, width)
        if self._cache is not None and self._cache[0] == width:
            return self._cache[1]
        lines = ["(Older IO entries removed from scrollback.)"] if self.discarded else []
        for entry in self.entries:
            for raw in entry.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4).split("\n"):
                text = "".join(char if char.isprintable() else " " for char in raw)
                segment, used = [], 0
                for char in text:
                    cells = measure(char)
                    if segment and used + cells > width:
                        lines.append("".join(segment))
                        segment, used = [], 0
                    segment.append(char)
                    used += cells
                lines.append("".join(segment))
        self._cache = width, lines
        return lines

    def window(self, width, rows, measure):
        lines = self.wrapped_lines(width, measure)
        last = max(0, len(lines) - rows)
        first = last if self.start is None else max(0, min(last, self.start))
        if self.start is not None:
            self.start = first
        return lines[first:first + rows], first, len(lines)

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
