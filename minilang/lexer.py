"""Lexical analyzer: source text -> tokens (character by character).
One lexer serves every language; the LanguageSpec supplies keywords/operators."""
from .errors import LexicalError
from .languages import MINILANG
from .tokens import Token, KEYWORD, IDENTIFIER, NUMBER, STRING, EOF_

DIGITS = "0123456789"
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "'": "'", "\\": "\\", "0": "\0"}


def _is_ident_start(c):
    return c == "_" or (c.isascii() and c.isalpha())


def _is_ident_part(c):
    return _is_ident_start(c) or c in DIGITS


class Lexer:
    def __init__(self, source, spec=None):
        self.spec = spec or MINILANG
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        self.errors = []          # ALL lexical errors are collected

    # -- character helpers -------------------------------------------------
    def _peek(self, offset=0):
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else "\0"

    def _at_end(self):
        return self.pos >= len(self.src)

    def _advance(self):
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _error(self, msg, line, col):
        self.errors.append(LexicalError(msg, line, col))

    def _add(self, type_, lexeme, line, col):
        self.tokens.append(Token(type_, lexeme, line, col, self.col))

    # -- main loop ---------------------------------------------------------
    def tokenize(self):
        spec = self.spec
        while not self._at_end():
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
            elif ch == "/" and self._peek(1) == "*" and spec.block_comments:
                self._block_comment()
            elif ch == "#" and spec.preprocessor:
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
            elif ch in DIGITS:
                self._number()
            elif _is_ident_start(ch):
                self._identifier()
            elif ch == '"':
                self._string('"')
            elif ch == "'" and spec.char_literals:
                self._string("'")
            else:
                self._operator()
        self.tokens.append(Token(EOF_, "", self.line, self.col, self.col))
        return self.tokens

    # -- token readers -----------------------------------------------------
    def _block_comment(self):
        line, col = self.line, self.col
        self._advance(); self._advance()
        while not self._at_end():
            if self._peek() == "*" and self._peek(1) == "/":
                self._advance(); self._advance()
                return
            self._advance()
        self._error("Unterminated block comment", line, col)

    def _number(self):
        line, col, start = self.line, self.col, self.pos
        while self._peek() in DIGITS:
            self._advance()
        if self._peek() == "." and self._peek(1) in DIGITS:
            self._advance()
            while self._peek() in DIGITS:
                self._advance()
        if _is_ident_start(self._peek()):                  # e.g. 12abc
            while _is_ident_part(self._peek()):
                self._advance()
            self._error(f"Invalid number '{self.src[start:self.pos]}'", line, col)
            return
        self._add(NUMBER, self.src[start:self.pos], line, col)

    def _identifier(self):
        line, col, start = self.line, self.col, self.pos
        while _is_ident_part(self._peek()):
            self._advance()
        text = self.src[start:self.pos]
        self._add(KEYWORD if text in self.spec.keywords else IDENTIFIER, text, line, col)

    def _string(self, quote):
        what = "string" if quote == '"' else "character"
        line, col = self.line, self.col
        self._advance()                                    # opening quote
        chars = []
        while True:
            if self._at_end() or self._peek() == "\n":
                self._error(f"Unterminated {what} literal", line, col)
                return
            c = self._peek()
            if c == quote:
                self._advance()
                break
            if c == "\\":
                self._advance()
                if self._at_end():
                    continue
                esc = self._peek()
                if esc in ESCAPES:
                    chars.append(ESCAPES[esc])
                    self._advance()
                else:
                    self._error(f"Invalid escape sequence '\\{esc}'", self.line, self.col - 1)
                    if esc != "\n":
                        self._advance()
                continue
            chars.append(self._advance())
        self._add(STRING, "".join(chars), line, col)

    def _operator(self):
        line, col = self.line, self.col
        two = self._peek() + self._peek(1)
        if two in self.spec.double:
            self._advance(); self._advance()
            self._add(self.spec.double[two], two, line, col)
            return
        ch = self._peek()
        if ch in self.spec.single:
            self._advance()
            self._add(self.spec.single[ch], ch, line, col)
            return
        self._advance()
        self._error(f"Invalid character '{ch}'", line, col)
