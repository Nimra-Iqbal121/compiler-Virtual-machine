"""Token definitions shared by every language front end."""
from dataclasses import dataclass

KEYWORD = "KEYWORD"
IDENTIFIER = "IDENTIFIER"
NUMBER = "NUMBER"
STRING = "STRING"
PLUS, MINUS, STAR, SLASH, PERCENT = "PLUS", "MINUS", "STAR", "SLASH", "PERCENT"
ASSIGN = "ASSIGN"
PLUS_ASSIGN, MINUS_ASSIGN, STAR_ASSIGN, SLASH_ASSIGN, PERCENT_ASSIGN = (
    "PLUS_ASSIGN", "MINUS_ASSIGN", "STAR_ASSIGN", "SLASH_ASSIGN", "PERCENT_ASSIGN")
EQ, NEQ, LT, GT, LTE, GTE = "EQ", "NEQ", "LT", "GT", "LTE", "GTE"
AND, OR, BANG = "AND", "OR", "BANG"
INC, DEC, SHL = "INC", "DEC", "SHL"
LPAREN, RPAREN, LBRACE, RBRACE = "LPAREN", "RPAREN", "LBRACE", "RBRACE"
LBRACKET, RBRACKET = "LBRACKET", "RBRACKET"
SEMICOLON, COMMA, DOT, SCOPE = "SEMICOLON", "COMMA", "DOT", "SCOPE"
NEWLINE, INDENT, DEDENT, COLON = "NEWLINE", "INDENT", "DEDENT", "COLON"
POW, FLOORDIV, FLOORDIV_ASSIGN, POW_ASSIGN = "POW", "FLOORDIV", "FLOORDIV_ASSIGN", "POW_ASSIGN"
FSTRING = "FSTRING"
EOF_ = "EOF"


@dataclass(frozen=True)
class Token:
    type: str
    lexeme: str          # for STRING this is the decoded content (no quotes)
    line: int
    col: int
    end_col: int = 0     # column just after the token (single-line tokens)

    def __str__(self):
        return f"{self.type}({self.lexeme})"
