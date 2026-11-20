"""Lexer for the Python subset: adds NEWLINE / INDENT / DEDENT tokens (significant
indentation), '#' comments, single/double/triple-quoted strings, f-strings,
implicit line joining inside brackets and floats with exponents."""
from . import tokens as T
from .errors import LexicalError
from .languages import PYTHON
from .lexer import Lexer, DIGITS, _is_ident_start, _is_ident_part

ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "0": "\0"}
PREFIXES = {"f", "r", "b", "u", "fr", "rf", "br", "rb"}
THREE = {"//=": T.FLOORDIV_ASSIGN, "**=": T.POW_ASSIGN}


def decode_escapes(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in ESC:
                out.append(ESC[n]); i += 2; continue
            if n == "\n":
                i += 2; continue
        out.append(c)
        i += 1
    return "".join(out)


class PythonLexer(Lexer):
    def __init__(self, source, spec=None):
        super().__init__(source, spec or PYTHON)
        self.indents = [0]
        self.depth = 0
        self.open_brackets = []

    # -- helpers -----------------------------------------------------------
    def _last_type(self):
        return self.tokens[-1].type if self.tokens else None

    def _tok(self, type_, lexeme, line, col, end=None):
        self.tokens.append(T.Token(type_, lexeme, line, col, end if end is not None else col))

    # -- main loop ---------------------------------------------------------
    def tokenize(self):
        line_start = True
        while not self._at_end():
            if line_start and self.depth == 0:
                r = self._line_start()
                if r == "blank":
                    continue
                if r == "eof":
                    break
                line_start = False
            ch = self._peek()
            if ch == "\n":
                line, col = self.line, self.col
                self._advance()
                if self.depth == 0:
                    if self._last_type() not in (None, T.NEWLINE, T.INDENT, T.DEDENT):
                        self._tok(T.NEWLINE, "\\n", line, col, col + 1)
                    line_start = True
            elif ch in " \t\r\f":
                self._advance()
            elif ch == "#":
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
            elif ch == "\\" and self._peek(1) == "\n":
                self._advance(); self._advance()
            elif ch in DIGITS or (ch == "." and self._peek(1) in DIGITS):
                self._py_number()
            elif _is_ident_start(ch):
                self._py_identifier()
            elif ch in "\"'":
                self._py_string("", self.line, self.col)
            else:
                self._py_operator()
        # end of file
        if self.open_brackets:
            ch, line, col = self.open_brackets[0]
            self._error(f"'{ch}' was never closed", line, col)
        if self._last_type() not in (None, T.NEWLINE, T.INDENT, T.DEDENT):
            self._tok(T.NEWLINE, "\\n", self.line, self.col, self.col)
        while len(self.indents) > 1:
            self.indents.pop()
            self._tok(T.DEDENT, "dedent", self.line, 1, 1)
        self.tokens.append(T.Token(T.EOF_, "", self.line, self.col, self.col))
        return self.tokens

    def _line_start(self):
        width = 0
        while self._peek() in " \t\f":
            ch = self._advance()
            width = width + 1 if ch == " " else (width // 8 + 1) * 8 if ch == "\t" else width
        if self._peek() == "\r":
            self._advance()
        if self._at_end():
            return "eof"
        ch = self._peek()
        if ch == "\n":
            self._advance()
            return "blank"
        if ch == "#":
            while not self._at_end() and self._peek() != "\n":
                self._advance()
            if not self._at_end():
                self._advance()
            return "blank"
        line, col = self.line, self.col
        if width > self.indents[-1]:
            self.indents.append(width)
            self._tok(T.INDENT, "indent", line, 1, col)
        elif width < self.indents[-1]:
            while width < self.indents[-1]:
                self.indents.pop()
                self._tok(T.DEDENT, "dedent", line, 1, col)
            if width != self.indents[-1]:
                self._error("Unindent does not match any outer indentation level", line, col)
        return "code"

    # -- tokens ------------------------------------------------------------
    def _py_number(self):
        line, col, start = self.line, self.col, self.pos
        if self._peek() == ".":
            self._advance()
            while self._peek() in DIGITS:
                self._advance()
        else:
            while self._peek() in DIGITS:
                self._advance()
            if self._peek() == "." and not _is_ident_start(self._peek(1)) and self._peek(1) != ".":
                self._advance()
                while self._peek() in DIGITS:
                    self._advance()
        if self._peek() in "eE" and (self._peek(1) in DIGITS or
                                     (self._peek(1) in "+-" and self._peek(2) in DIGITS)):
            self._advance()
            if self._peek() in "+-":
                self._advance()
            while self._peek() in DIGITS:
                self._advance()
        if _is_ident_start(self._peek()):
            while _is_ident_part(self._peek()):
                self._advance()
            self._error(f"Invalid number '{self.src[start:self.pos]}'", line, col)
            return
        self._add(T.NUMBER, self.src[start:self.pos], line, col)

    def _py_identifier(self):
        line, col, start = self.line, self.col, self.pos
        while _is_ident_part(self._peek()):
            self._advance()
        text = self.src[start:self.pos]
        if text.lower() in PREFIXES and self._peek() in "\"'":
            self._py_string(text.lower(), line, col)
            return
        self._add(T.KEYWORD if text in self.spec.keywords else T.IDENTIFIER, text, line, col)

    def _py_string(self, prefix, line, col):
        quote = self._peek()
        triple = self._peek(1) == quote and self._peek(2) == quote
        for _ in range(3 if triple else 1):
            self._advance()
        raw = []
        while True:
            if self._at_end():
                self._error("Unterminated string literal", line, col)
                return
            c = self._peek()
            if triple:
                if c == quote and self._peek(1) == quote and self._peek(2) == quote:
                    for _ in range(3):
                        self._advance()
                    break
            else:
                if c == "\n":
                    self._error("Unterminated string literal", line, col)
                    return
                if c == quote:
                    self._advance()
                    break
            if c == "\\":
                raw.append(self._advance())
                if not self._at_end():
                    raw.append(self._advance())
                continue
            raw.append(self._advance())
        content = "".join(raw)
        if "b" in prefix:
            self._error("Bytes literals are not supported", line, col)
            return
        if "f" in prefix:
            if "r" in prefix:
                content = content.replace("\\", "\\\\")
            self._add(T.FSTRING, content, line, col)
        else:
            self._add(T.STRING, content if "r" in prefix else decode_escapes(content), line, col)

    def _py_operator(self):
        line, col = self.line, self.col
        three = "".join(self._peek(i) for i in range(3))
        if three in THREE:
            for _ in range(3):
                self._advance()
            self._add(THREE[three], three, line, col)
            return
        two = self._peek() + self._peek(1)
        if two in self.spec.double:
            self._advance(); self._advance()
            self._add(self.spec.double[two], two, line, col)
            return
        ch = self._peek()
        if ch in self.spec.single:
            self._advance()
            if ch in "([{":
                self.depth += 1
                self.open_brackets.append((ch, line, col))
            elif ch in ")]}" and self.depth > 0:
                self.depth -= 1
                self.open_brackets.pop()
            self._add(self.spec.single[ch], ch, line, col)
            return
        self._advance()
        self._error(f"Invalid character '{ch}'", line, col)
