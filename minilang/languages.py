"""Language definitions. Every language has its own lexer table + parser but
shares the AST, semantic analyzer, bytecode generator and virtual machine."""
from dataclasses import dataclass
from . import tokens as T

_BASE_SINGLE = {
    "+": T.PLUS, "-": T.MINUS, "*": T.STAR, "/": T.SLASH, "%": T.PERCENT,
    "=": T.ASSIGN, "<": T.LT, ">": T.GT, "!": T.BANG,
    "(": T.LPAREN, ")": T.RPAREN, "{": T.LBRACE, "}": T.RBRACE, ";": T.SEMICOLON,
}
_BASE_DOUBLE = {"==": T.EQ, "!=": T.NEQ, "<=": T.LTE, ">=": T.GTE,
                "&&": T.AND, "||": T.OR}
_C_SINGLE = dict(_BASE_SINGLE, **{",": T.COMMA, ".": T.DOT, "[": T.LBRACKET, "]": T.RBRACKET})
_C_DOUBLE = dict(_BASE_DOUBLE, **{
    "<<": T.SHL, "++": T.INC, "--": T.DEC, "::": T.SCOPE,
    "+=": T.PLUS_ASSIGN, "-=": T.MINUS_ASSIGN, "*=": T.STAR_ASSIGN,
    "/=": T.SLASH_ASSIGN, "%=": T.PERCENT_ASSIGN})
_PY_SINGLE = {
    "+": T.PLUS, "-": T.MINUS, "*": T.STAR, "/": T.SLASH, "%": T.PERCENT,
    "=": T.ASSIGN, "<": T.LT, ">": T.GT, "(": T.LPAREN, ")": T.RPAREN,
    "[": T.LBRACKET, "]": T.RBRACKET, "{": T.LBRACE, "}": T.RBRACE,
    ",": T.COMMA, ".": T.DOT, ":": T.COLON,
}
_PY_DOUBLE = {"==": T.EQ, "!=": T.NEQ, "<=": T.LTE, ">=": T.GTE, "**": T.POW,
              "//": T.FLOORDIV, "+=": T.PLUS_ASSIGN, "-=": T.MINUS_ASSIGN,
              "*=": T.STAR_ASSIGN, "/=": T.SLASH_ASSIGN, "%=": T.PERCENT_ASSIGN}

MINILANG_SAMPLE = '''// MiniLang demo
let age = 20;

if (age >= 18) {
    print("Adult");
} else {
    print("Minor");
}

let i = 0;
while (i < 5) {
    print(i);
    i = i + 1;
}
'''

PYTHON_SAMPLE = '''# Python demo
age = 20

if age >= 18:
    print("Adult")
else:
    print("Minor")

total = 0
for i in range(5):
    print(i)
    total += i

print(f"Sum of 0..4 = {total}")
'''

CPP_SAMPLE = '''#include <iostream>
using namespace std;

int main() {
    int age = 20;

    if (age >= 18) {
        cout << "Adult" << endl;
    } else {
        cout << "Minor" << endl;
    }

    for (int i = 0; i < 5; i++) {
        cout << i << endl;
    }
    return 0;
}
'''

JAVA_SAMPLE = '''public class Main {
    public static void main(String[] args) {
        int age = 20;

        if (age >= 18) {
            System.out.println("Adult");
        } else {
            System.out.println("Minor");
        }

        for (int i = 0; i < 5; i++) {
            System.out.println(i);
        }
    }
}
'''


@dataclass
class LanguageSpec:
    key: str                  # "minilang" | "python" | "cpp" | "java"
    name: str                 # shown in the UI
    extension: str
    keywords: frozenset
    single: dict
    double: dict
    block_comments: bool = False
    preprocessor: bool = False
    char_literals: bool = False
    sample: str = ""
    examples_dir: str = ""
    builtins: tuple = ()      # names highlighted as built-ins in the editor

    @property
    def dialect(self):        # semantic rules / VM output style
        return self.key


MINILANG = LanguageSpec(
    "minilang", "MiniLang", ".ml",
    frozenset({"let", "if", "else", "while", "print", "true", "false", "break", "continue"}),
    _BASE_SINGLE, _BASE_DOUBLE, block_comments=True,
    sample=MINILANG_SAMPLE, examples_dir="minilang")

PYTHON = LanguageSpec(
    "python", "Python", ".py",
    frozenset({"if", "elif", "else", "while", "for", "in", "and", "or", "not", "True",
               "False", "None", "pass", "break", "continue", "def", "return", "class",
               "import", "from", "as", "lambda", "global", "nonlocal", "try", "except",
               "finally", "with", "del", "assert", "raise", "yield", "is"}),
    _PY_SINGLE, _PY_DOUBLE,
    sample=PYTHON_SAMPLE, examples_dir="python",
    builtins=("print", "range", "str", "int", "float", "len", "abs", "min", "max", "round"))

CPP = LanguageSpec(
    "cpp", "C++", ".cpp",
    frozenset({"int", "long", "short", "double", "float", "bool", "string", "char", "auto",
               "void", "const", "static", "if", "else", "while", "for", "do", "return",
               "break", "continue", "true", "false", "using", "namespace"}),
    _C_SINGLE, _C_DOUBLE, block_comments=True, preprocessor=True, char_literals=True,
    sample=CPP_SAMPLE, examples_dir="cpp",
    builtins=("cout", "endl", "cin", "std", "to_string"))

JAVA = LanguageSpec(
    "java", "Java", ".java",
    frozenset({"public", "private", "protected", "static", "final", "class", "void",
               "int", "long", "short", "double", "float", "boolean", "String", "char", "var",
               "if", "else", "while", "for", "do", "return", "break", "continue",
               "true", "false", "import", "package"}),
    _C_SINGLE, _C_DOUBLE, block_comments=True, char_literals=True,
    sample=JAVA_SAMPLE, examples_dir="java",
    builtins=("System", "out", "print", "println", "valueOf"))

LANGUAGES = {"minilang": MINILANG, "python": PYTHON, "cpp": CPP, "java": JAVA}
ORDER = ["minilang", "python", "cpp", "java"]


def get_language(key):
    return LANGUAGES[key]


def language_for_extension(path):
    low = path.lower()
    for spec in LANGUAGES.values():
        if low.endswith(spec.extension):
            return spec.key
    if low.endswith((".cc", ".cxx", ".c++")):
        return "cpp"
    return None
