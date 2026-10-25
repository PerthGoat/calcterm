"""Syntax token spans and ANSI colors for incomplete expressions."""

from __future__ import annotations

import re

from .core import BITWISE
from .engine import EQUATION_NAMES, FUNCTIONS, RESERVED, TOKEN


SYNTAX_TOKEN = re.compile(r"(?P<base>0[bB][01_]*|0[hH][0-9a-fA-F_]*|0[oO][0-7_]*)|"
                          + TOKEN.pattern + r"|(?P<unicode>[→⇒×÷−²³≤≥≠])", re.UNICODE)
SYNTAX_COLORS = {"number": "38;2;184;134;11", "function": "94", "constant": "95",
                 "unit": "92", "operator": "96", "command": "96"}


def expression_highlights(text) -> list[tuple[int, int, str]]:
    """Lex incomplete input for display without parsing or evaluating it."""
    spans: list[tuple[int, int, str]] = []
    for match in SYNTAX_TOKEN.finditer(text):
        kind, token = match.lastgroup, match.group()
        if kind == "base":
            kind = "number"
        elif kind in ("op", "unicode") or token in BITWISE:
            kind = "operator"
        elif kind == "name":
            if token in FUNCTIONS or token in EQUATION_NAMES:
                kind = "function"
            elif token in RESERVED or token == "ans":
                kind = "constant"
            else:
                continue
        if kind is not None and kind in SYNTAX_COLORS:
            spans.append((match.start(), match.end(), kind))
    command = re.match(r"\s*(:[a-z]+)", text)
    if command:
        spans.append((*command.span(1), "command"))
    return spans


def colorize_line(text, spans=(), selected=None):
    """Apply colors after layout; inverse selection takes precedence over syntax."""
    styles = [""] * len(text)
    for first, last, kind in spans:
        first, last = max(0, first), min(len(text), last)
        if first < last:
            styles[first:last] = [SYNTAX_COLORS[kind]] * (last - first)
    if selected is not None:
        first, last = max(0, selected[0]), min(len(text), selected[1])
        if first < last:
            styles[first:last] = ["7"] * (last - first)
    output = []
    first = 0
    while first < len(text):
        last = first + 1
        while last < len(text) and styles[last] == styles[first]:
            last += 1
        segment = text[first:last]
        output.append(f"\x1b[{styles[first]}m{segment}\x1b[0m" if styles[first] else segment)
        first = last
    return "".join(output)
