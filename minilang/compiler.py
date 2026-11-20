"""Pipeline driver:  Source -> Lexer -> Parser -> AST -> Semantic -> Bytecode.

Like a real compiler it analyses the WHOLE program first: all lexical, syntax
and semantic errors are collected and reported together (sorted by position).
Bytecode is generated only when there are no errors at all.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from .lexer import Lexer
from .parser import Parser
from .cparser import CFamilyParser
from .pylexer import PythonLexer
from .pyparser import PyParser
from .semantic import SemanticAnalyzer
from .bytecode import BytecodeGenerator
from .languages import get_language
from .vm import VirtualMachine
from .errors import MiniLangError

STAGE_ORDER = ("lexer", "parser", "semantic")


@dataclass
class CompileResult:
    source: str
    language: str = "minilang"
    tokens: list = field(default_factory=list)
    ast: Optional[object] = None
    bytecode: Optional[list] = None
    errors: List[MiniLangError] = field(default_factory=list)
    stage_errors: dict = field(default_factory=dict)

    @property
    def ok(self):
        return not self.errors and self.bytecode is not None

    @property
    def style(self):
        return get_language(self.language).dialect

    @property
    def failed_stage(self):
        for s in STAGE_ORDER:
            if self.stage_errors.get(s):
                return s
        return None


def _make_lexer(spec, source):
    return PythonLexer(source, spec) if spec.key == "python" else Lexer(source, spec)


def _make_parser(spec, tokens, lex_errors):
    if spec.key == "minilang":
        return Parser(tokens, lex_errors)
    if spec.key == "python":
        return PyParser(tokens, lex_errors)
    return CFamilyParser(tokens, spec.key, lex_errors)


def compile_source(source, language="minilang"):
    spec = get_language(language)
    res = CompileResult(source, language)

    lexer = _make_lexer(spec, source)
    res.tokens = lexer.tokenize()
    parser = _make_parser(spec, res.tokens, lexer.errors)
    res.ast = parser.parse()                       # never stops at the first error
    sem_errors = SemanticAnalyzer(spec.dialect).analyze(res.ast)

    res.stage_errors = {"lexer": lexer.errors, "parser": parser.errors,
                        "semantic": sem_errors}
    res.errors = sorted(lexer.errors + parser.errors + sem_errors,
                        key=lambda e: (e.line or 0, e.col or 0))
    if not res.errors:
        res.bytecode = BytecodeGenerator().generate(res.ast)
    return res


def run_bytecode(bytecode, on_output=None, max_steps=1_000_000, style="minilang"):
    """Execute bytecode on a fresh VM. Returns (output_lines, error_or_None)."""
    vm = VirtualMachine(bytecode, on_output, max_steps, style)
    try:
        vm.run()
        return vm.output, None
    except MiniLangError as e:
        return vm.output, e


def format_tokens(tokens):
    return "\n".join(f"{str(t):<28} line {t.line}, col {t.col}" for t in tokens)
