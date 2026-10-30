"""A bounded, embeddable Forth subset with a persistent word dictionary.

Values are arbitrary-width integers and Python strings, rather than raw memory
addresses. The host registers application words; source never executes Python.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import operator
import re

from .core import CalcError


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


def tokenize(source):
    if len(source) > 65536:
        raise CalcError("Forth source exceeds 65536 characters.")
    tokens, position = [], 0
    while position < len(source):
        if source[position].isspace():
            position += 1
            continue
        if source[position] == "\\":
            end = source.find("\n", position)
            position = len(source) if end < 0 else end + 1
            continue
        if source[position] == "(":
            end = source.find(")", position)
            if end < 0:
                raise CalcError("Unclosed Forth stack comment.")
            position = end + 1
            continue
        prefix = source[position:position + 2].lower()
        if prefix in ('s"', '."'):
            start = position + 2
            if start < len(source) and source[start].isspace():
                start += 1
            end = source.find('"', start)
            if end < 0:
                raise CalcError("Unclosed Forth string.")
            tokens.append(Token("print" if prefix == '."' else "string", source[start:end]))
            position = end + 1
        elif source[position] == '"':
            try:
                value, length = json.JSONDecoder().raw_decode(source[position:])
            except ValueError:
                raise CalcError("Invalid or unclosed quoted Forth string.") from None
            tokens.append(Token("string", value))
            position += length
        else:
            end = position
            while end < len(source) and not source[end].isspace() and source[end] not in ':;':
                end += 1
            if end == position:
                end += 1
            tokens.append(Token("word", source[position:end].lower()))
            position = end
    return tokens


class ForthInterpreter:
    """Stack, compiler, and execution engine independent of the calculator UI."""

    control_words = {":", ";", "if", "else", "then", "begin", "until", "again",
                     "while", "repeat", "do", "?do", "loop", "leave", "exit", "recurse"}

    def __init__(self, on_define=None):
        self.stack = []
        self.words = {}
        self.definitions = {}
        self.programs = {}
        self.pending = None
        self.output = []
        self._output_size = 0
        self.on_define = on_define
        self.max_steps = 10000
        self.max_stack = 1024
        self._steps = 0
        self._loops = []
        self._install_core()

    def register(self, name, action):
        self.words[name.lower()] = action

    def push(self, value):
        if len(self.stack) >= self.max_stack:
            raise CalcError("Forth stack limit exceeded.")
        self.stack.append(value)

    def pop(self):
        if not self.stack:
            raise CalcError("Forth stack underflow.")
        return self.stack.pop()

    def integer(self):
        value = self.pop()
        if type(value) is not int:
            raise CalcError("Forth word requires an integer.")
        return value

    def string(self):
        value = self.pop()
        if not isinstance(value, str):
            raise CalcError("Forth word requires a string.")
        return value

    def _binary(self, operation, flag=False):
        right, left = self.integer(), self.integer()
        value = operation(left, right)
        self.push(-int(bool(value)) if flag else value)

    @staticmethod
    def _quotient(left, right):
        if right == 0:
            raise CalcError("Forth division by zero.")
        return (abs(left) // abs(right)) * (-1 if (left < 0) != (right < 0) else 1)

    def _install_core(self):
        operations = {"+": operator.add, "-": operator.sub, "*": operator.mul,
                      "/": self._quotient, "mod": lambda a, b: a - self._quotient(a, b) * b,
                      "and": operator.and_, "or": operator.or_, "xor": operator.xor,
                      "min": min, "max": max}
        for name, operation in operations.items():
            self.register(name, lambda vm, op=operation: vm._binary(op))
        for name, operation in {"=": operator.eq, "<>": operator.ne, "<": operator.lt,
                                ">": operator.gt, "<=": operator.le, ">=": operator.ge}.items():
            self.register(name, lambda vm, op=operation: vm._binary(op, flag=True))
        for name, operation in {"negate": operator.neg, "abs": abs, "invert": operator.invert,
                                "1+": lambda n: n + 1, "1-": lambda n: n - 1,
                                "0=": lambda n: -int(n == 0), "0<": lambda n: -int(n < 0)}.items():
            self.register(name, lambda vm, op=operation: vm.push(op(vm.integer())))
        self.register("dup", lambda vm: vm._duplicate(0))
        self.register("over", lambda vm: vm._duplicate(1))
        self.register("drop", lambda vm: vm.pop())
        self.register("swap", lambda vm: vm._swap())
        self.register("rot", lambda vm: vm._rotate())
        self.register("depth", lambda vm: vm.push(len(vm.stack)))
        self.register("clearstack", lambda vm: vm.stack.clear())
        self.register("true", lambda vm: vm.push(-1))
        self.register("false", lambda vm: vm.push(0))
        self.register(".", lambda vm: vm._emit(str(vm.pop()) + " "))
        self.register(".s", lambda vm: vm._emit(vm.stack_text()))
        self.register("type", lambda vm: vm._emit(vm.string()))
        self.register("cr", lambda vm: vm._emit("\n"))
        self.register("i", lambda vm: vm._index(0))
        self.register("j", lambda vm: vm._index(1))
        self.register("words", lambda vm: vm._emit(" ".join(sorted(vm.words.keys() | vm.programs.keys()))))
        self.register("def", lambda vm: vm._emit(vm.definition(vm.string())))

    def definition(self, name):
        name = name.strip().lower()
        if not name or any(char.isspace() for char in name):
            raise CalcError("Use :def WORD to view a word definition.")
        if name in self.definitions:
            body = self.definitions[name]
            return f": {name}" + (" " + body if body else "") + " ;"
        if name in self.words:
            return f"{name} is a built-in Forth word (native implementation)."
        if name in self.control_words:
            return f"{name} is a built-in Forth compiler word."
        raise CalcError(f"Unknown Forth word: {name}")

    def _emit(self, text):
        self._output_size += len(text)
        if self._output_size > 1048576:
            raise CalcError("Forth output limit of 1048576 characters exceeded.")
        self.output.append(text)

    def _duplicate(self, offset):
        if len(self.stack) <= offset:
            raise CalcError("Forth stack underflow.")
        self.push(self.stack[-1 - offset])

    def _swap(self):
        right, left = self.pop(), self.pop()
        self.push(right)
        self.push(left)

    def _rotate(self):
        third, second, first = self.pop(), self.pop(), self.pop()
        for value in (second, third, first):
            self.push(value)

    def _index(self, offset):
        if len(self._loops) <= offset:
            raise CalcError("Forth I/J requires an active counted loop.")
        self.push(self._loops[-1 - offset][1])

    def stack_text(self):
        values = " ".join(json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value)
                          for value in self.stack)
        return f"<{len(self.stack)}>" + (" " + values if values else "")

    def _validate_name(self, name):
        if (not isinstance(name, str) or not name or len(name) > 128 or name != name.lower()
                or re.search(r'[\s:;"()\\]', name) or re.fullmatch(r"[+-]?\d+", name)
                or name in self.words or name in self.control_words or name in {"forth", "abort"}):
            raise CalcError(f"Invalid or reserved Forth word name: {name}")

    def _compile(self, tokens, known, defining=None):
        if len(tokens) > 8192:
            raise CalcError("Forth program exceeds 8192 tokens.")
        code, controls = [], []
        for token in tokens:
            word, position = token.value, len(code)
            if token.kind == "string":
                code.append(("push", word))
            elif token.kind == "print":
                code.append(("print", word))
            elif re.fullmatch(r"[+-]?\d+", word):
                code.append(("push", int(word)))
            elif word == "if":
                controls.append(("if", position))
                code.append(("zero", None))
            elif word == "else":
                if not controls or controls[-1][0] != "if":
                    raise CalcError("Forth ELSE requires IF.")
                _, branch = controls.pop()
                code[branch] = ("zero", position + 1)
                controls.append(("else", position))
                code.append(("jump", None))
            elif word == "then":
                if not controls or controls[-1][0] not in ("if", "else"):
                    raise CalcError("Forth THEN requires IF or ELSE.")
                kind, branch = controls.pop()
                code[branch] = ("zero" if kind == "if" else "jump", position)
            elif word == "begin":
                controls.append(("begin", position))
            elif word in ("until", "again"):
                if not controls or controls[-1][0] != "begin":
                    raise CalcError(f"Forth {word.upper()} requires BEGIN.")
                _, branch = controls.pop()
                code.append(("zero" if word == "until" else "jump", branch))
            elif word == "while":
                if not controls or controls[-1][0] != "begin":
                    raise CalcError("Forth WHILE requires BEGIN.")
                controls.append(("while", position))
                code.append(("zero", None))
            elif word == "repeat":
                if len(controls) < 2 or controls[-1][0] != "while" or controls[-2][0] != "begin":
                    raise CalcError("Forth REPEAT requires BEGIN ... WHILE.")
                _, branch = controls.pop()
                _, start = controls.pop()
                code[branch] = ("zero", position + 1)
                code.append(("jump", start))
            elif word in ("do", "?do"):
                controls.append((word, position))
                code.append((word, None))
            elif word == "loop":
                if not controls or controls[-1][0] not in ("do", "?do"):
                    raise CalcError("Forth LOOP requires DO or ?DO.")
                kind, start = controls.pop()
                code[start] = (kind, position + 1)
                code.append(("loop", start + 1))
            elif word == "leave":
                if not any(kind in ("do", "?do") for kind, _ in controls):
                    raise CalcError("Forth LEAVE requires a counted loop.")
                code.append(("leave", None))
            elif word in ("exit", "recurse"):
                if defining is None:
                    raise CalcError(f"Forth {word.upper()} requires a definition.")
                code.append(("call", defining) if word == "recurse" else ("exit", None))
            elif word in known:
                code.append(("call", word))
            else:
                raise CalcError(f"Unknown Forth word: {word}")
        if controls:
            raise CalcError(f"Unclosed Forth control structure: {controls[-1][0].upper()}")
        return code

    def load_definitions(self, definitions):
        """Validate and compile saved bodies without running any of their words."""
        if not isinstance(definitions, dict) or len(definitions) > 256:
            raise CalcError("forth_words must be an object of at most 256 word definitions.")
        for name, body in definitions.items():
            self._validate_name(name)
            if not isinstance(body, str):
                raise CalcError("Forth word bodies must be strings.")
        known = self.words.keys() | definitions.keys()
        programs = {name: self._compile(tokenize(body), known, name) for name, body in definitions.items()}
        self.definitions, self.programs = dict(definitions), programs
        self.pending = None

    def _define(self, name, tokens):
        self._validate_name(name)
        if name not in self.definitions and len(self.definitions) >= 256:
            raise CalcError("Forth dictionary limit of 256 user words exceeded.")
        parts = [json.dumps(token.value, ensure_ascii=False) if token.kind == "string" else
                 '." ' + token.value + '"' if token.kind == "print" else token.value for token in tokens]
        body = " ".join(parts)
        if len(body) > 65536:
            raise CalcError("Forth definition exceeds 65536 characters.")
        program = self._compile(tokens, self.words.keys() | self.programs.keys() | {name}, name)
        self.definitions[name], self.programs[name] = body, program
        if self.on_define:
            self.on_define(name)

    def execute(self, source):
        """Run input; keep the stack between inputs and restore it on errors."""
        previous = list(self.stack)
        self.output, self._steps, self._loops = [], 0, []
        self._output_size = 0
        try:
            tokens = tokenize(source)
            chunk = []
            index = 0
            while index < len(tokens):
                token = tokens[index]
                if self.pending is not None:
                    name, body = self.pending
                    if token == Token("word", ";"):
                        self.pending = None
                        self._define(name, body)
                    elif token == Token("word", ":"):
                        raise CalcError("Nested Forth definitions are not supported.")
                    else:
                        body.append(token)
                        if len(body) > 8192:
                            raise CalcError("Forth definition exceeds 8192 tokens.")
                elif token == Token("word", ":"):
                    self._run(self._compile(chunk, self.words.keys() | self.programs.keys()))
                    chunk = []
                    index += 1
                    if index >= len(tokens) or tokens[index].kind != "word":
                        raise CalcError("Use : name ... ; to define a Forth word.")
                    name = tokens[index].value
                    self._validate_name(name)
                    self.pending = (name, [])
                else:
                    chunk.append(token)
                index += 1
            self._run(self._compile(chunk, self.words.keys() | self.programs.keys()))
        except (CalcError, OSError):
            self.stack[:] = previous
            self.pending = None
            raise
        return "".join(self.output)

    def _run(self, code, depth=0):
        if depth >= 64:
            raise CalcError("Forth call depth limit exceeded.")
        position, loop_base = 0, len(self._loops)
        try:
            while position < len(code):
                self._steps += 1
                if self._steps > self.max_steps:
                    raise CalcError("Forth execution limit exceeded (10000 instructions).")
                operation, argument = code[position]
                position += 1
                if operation == "push":
                    self.push(argument)
                elif operation == "print":
                    self._emit(argument)
                elif operation == "call":
                    if argument in self.programs:
                        self._run(self.programs[argument], depth + 1)
                    elif argument in self.words:
                        self.words[argument](self)
                    else:
                        raise CalcError(f"Unknown Forth word: {argument}")
                elif operation == "jump":
                    position = argument
                elif operation == "zero":
                    if self.integer() == 0:
                        position = argument
                elif operation in ("do", "?do"):
                    start, limit = self.integer(), self.integer()
                    if operation == "?do" and start == limit:
                        position = argument
                    else:
                        self._loops.append([limit, start, argument])
                elif operation == "loop":
                    loop = self._loops[-1]
                    loop[1] += 1
                    if loop[1] == loop[0]:
                        self._loops.pop()
                    else:
                        position = argument
                elif operation == "leave":
                    position = self._loops.pop()[2]
                elif operation == "exit":
                    return
        finally:
            del self._loops[loop_base:]
