"""Seeded, bounded fuzz cases that run with the regular unittest suite."""

import itertools
import operator
from fractions import Fraction
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from calcterm.app import ConsoleApp, display_width
from calcterm.core import CalcError, sp
from calcterm.engine import Calculator
from calcterm.forth import ForthInterpreter
from calcterm.io import DISCARDED, IOTranscript
from calcterm.terminal import Terminal


ARITHMETIC = {"+": operator.add, "-": operator.sub, "*": operator.mul, "/": operator.truediv}


def expression(randomizer, depth):
    if depth == 0 or randomizer.randrange(3) == 0:
        value = randomizer.randrange(200)
        spelling = randomizer.choice((str(value), f"0h{value:X}", f"0b{value:b}", f"0o{value:o}",
                                     f"{value // 10}_{value % 10}"))
        return spelling, Fraction(value)
    left, lhs = expression(randomizer, depth - 1)
    right, rhs = expression(randomizer, depth - 1)
    symbol = randomizer.choice(tuple(ARITHMETIC))
    spelling = {"-": "−", "*": "×", "/": "÷"}.get(symbol, symbol) if randomizer.randrange(2) else symbol
    source = f"({left} {spelling} {right})"
    if lhs is None or rhs is None or (symbol == "/" and rhs == 0):
        return source, None
    return source, ARITHMETIC[symbol](lhs, rhs)


class FuzzTests(unittest.TestCase):
    def test_exact_arithmetic_matches_fraction_oracle(self):
        rng = random.Random(7361)
        calculator = Calculator()
        for case in range(350):
            source, expected = expression(rng, 4)
            with self.subTest(case=case, source=source):
                old_answer = calculator.answer
                old_variables = dict(calculator.variables)
                if expected is None:
                    with self.assertRaises(CalcError):
                        calculator.calculate(source + "->result")
                    self.assertIs(calculator.answer, old_answer)
                    self.assertEqual(calculator.variables, old_variables)
                    self.assertTrue(calculator.history[-1].is_error)
                else:
                    self.assertEqual(calculator.calculate(source + "->result"), str(expected))
                    self.assertEqual(calculator.variables["result"].value, sp.Rational(str(expected)))
                    self.assertEqual(calculator.history[-1].result, str(expected))
                    self.assertFalse(calculator.history[-1].is_error)

    def test_mutated_expressions_preserve_state_on_errors(self):
        rng = random.Random(9305)
        calculator = Calculator()
        seeds = ("3_in=>_ft->length", "1_500+0hF", "sqrt(2)", "5 xor 3", "1<2<=3", "[1,2]", "2_m^2")
        fragments = ("0b2", "_", "=>", "→", "≤", "(", ")", "[", "]", ",", " ", "😀", "\x00", "π")
        for case in range(400):
            source = rng.choice(seeds)
            for _ in range(rng.randint(1, 3)):
                position = rng.randrange(len(source) + 1)
                source = source[:position] + rng.choice(fragments) + source[position + rng.randrange(3):]
            with self.subTest(case=case, source=source):
                old_answer = calculator.answer
                old_variables = dict(calculator.variables)
                try:
                    result = calculator.calculate(source)
                except CalcError:
                    self.assertIs(calculator.answer, old_answer)
                    self.assertEqual(calculator.variables, old_variables)
                    self.assertTrue(calculator.history[-1].is_error)
                else:
                    self.assertEqual(calculator.history[-1].result, result)
                    self.assertFalse(calculator.history[-1].is_error)
                self.assertLessEqual(len(calculator.history), 30)

    def test_forth_stack_matches_integer_oracle_and_rolls_back(self):
        rng = random.Random(1138)
        vm = ForthInterpreter()
        operations = {"+": operator.add, "-": operator.sub, "*": operator.mul,
                      "and": operator.and_, "or": operator.or_, "xor": operator.xor}
        for case in range(300):
            before = [rng.randint(-4, 4) for _ in range(rng.randrange(5))]
            vm.stack[:] = before
            tokens = [rng.choice([str(rng.randint(-20, 20)), "dup", "drop", *operations])
                      for _ in range(rng.randint(1, 25))]
            expected = list(before)
            with self.subTest(case=case, stack=before, tokens=tokens):
                try:
                    for token in tokens:
                        if token == "dup":
                            expected.append(expected[-1])
                        elif token == "drop":
                            expected.pop()
                        elif token in operations:
                            right = expected.pop()
                            expected.append(operations[token](expected.pop(), right))
                        else:
                            expected.append(int(token))
                except IndexError:
                    with self.assertRaises(CalcError):
                        vm.execute(" ".join(tokens))
                    self.assertEqual(vm.stack, before)
                else:
                    self.assertEqual(vm.execute(" ".join(tokens)), "")
                    self.assertEqual(vm.stack, expected)

    def test_transcript_cache_matches_uncached_transcript(self):
        rng = random.Random(5149)
        limit = 64
        transcript = IOTranscript(max_characters=limit)
        entries = []
        discarded = False
        alphabet = "abc\t\r\n界e\u0301\x1b"
        width = 10
        for case in range(220):
            text = "".join(rng.choices(alphabet, k=rng.randrange(1, 85)))
            transcript.append(text)
            entries.append(text[-limit:])
            discarded |= len(text) > limit
            while sum(map(len, entries)) > limit:
                entries.pop(0)
                discarded = True
            if rng.randrange(3) == 0:
                width = rng.randint(1, 20)
            rows = rng.randint(1, 12)
            expected = [DISCARDED] if discarded else []
            for entry in entries:
                uncached = IOTranscript(max_characters=limit)
                uncached.append(entry)
                expected.extend(uncached.wrapped_lines(width, display_width))
            with self.subTest(case=case, width=width, rows=rows):
                self.assertEqual(list(transcript.entries), entries)
                self.assertEqual(transcript.characters, sum(map(len, entries)))
                self.assertEqual(transcript.wrapped_lines(width, display_width), expected)
                first = rng.randrange(len(expected) + 1) if rng.randrange(2) else None
                transcript.start = first
                last = max(0, len(expected) - rows)
                first = last if first is None else min(first, last)
                self.assertEqual(transcript.window(width, rows, display_width),
                                 (expected[first:first + rows], first, len(expected)))

    def test_posix_decoder_consumes_bounded_byte_streams(self):
        rng = random.Random(2411)
        with patch("os.name", "posix"), patch("sys.stdin") as stdin, \
                patch("select.select", return_value=([0], [], [])):
            stdin.fileno.return_value = 0
            for case in range(180):
                stream = rng.randbytes(rng.randint(1, 70))
                if case % 3 == 0:
                    stream = b"\x1b[" + stream
                reads = (bytes((byte,)) for byte in stream)
                # A finite supply of EOF responses exposes accidental read loops.
                with self.subTest(case=case, stream=stream), \
                        patch("os.read", side_effect=itertools.chain(reads, [b""] * (len(stream) + 2))):
                    terminal = Terminal()
                    keys = [terminal.read_key(timeout=0.01) for _ in range(len(stream) + 1)]
                    self.assertEqual(keys[-1], "CTRL_D")
                    self.assertTrue(all(isinstance(key, str) and key for key in keys))

    def test_key_sequences_and_resizes_keep_frame_coordinates_valid(self):
        rng = random.Random(731)
        edit_keys = ("UP DOWN PAGEUP PAGEDOWN RIGHT LEFT HOME END ENTER SHIFT_ENTER ESC TAB BACKSPACE DELETE "
                     "INSERT CTRL_U CTRL_T SHIFT_LEFT SHIFT_RIGHT SHIFT_F7").split()
        keys = [*edit_keys, *(f"F{i}" for i in range(1, 11)), *"1x+2=界π"]
        with TemporaryDirectory() as directory:
            app = ConsoleApp(config_path=Path(directory) / "config.json")
            for case in range(500):
                key = rng.choice(keys)
                width = rng.choice((1, 39, 40, 41, 70, 121))
                height = rng.choice((1, 11, 12, 14, 24, 40))
                with self.subTest(case=case, key=key, width=width, height=height):
                    app.handle_key(key)
                    lines, selected, cursor = app.frame(width, height)
                    self.assertLessEqual(len(lines), height)
                    self.assertTrue(all(display_width(line) <= width for line in lines))
                    if cursor is not None:
                        self.assertTrue(1 <= cursor[0] <= len(lines) and 1 <= cursor[1] <= width)
                    for row, (start, end) in selected.items():
                        self.assertTrue(0 <= row < len(lines) and 0 <= start < end <= len(lines[row]))
