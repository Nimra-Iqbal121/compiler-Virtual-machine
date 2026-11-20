"""Bytecode generator: validated AST -> stack-machine instructions."""
import json
from dataclasses import dataclass
from typing import Any
from . import ast_nodes as ast

DEFAULTS = {"int": 0, "float": 0.0, "string": "", "bool": False}


@dataclass
class Instruction:
    op: str
    arg: Any = None
    line: int = 0            # source line (used for runtime error messages)

    def __str__(self):
        if self.arg is None:
            return self.op
        return f"{self.op} {format_arg(self.arg, quote_str=self.op == 'PUSH')}"


def format_arg(arg, quote_str=False):
    if isinstance(arg, bool):
        return "true" if arg else "false"
    if isinstance(arg, str):
        return json.dumps(arg, ensure_ascii=False) if quote_str else arg
    return str(arg)


class BytecodeGenerator:
    PY_BINOPS = {"/": "FDIV", "//": "FLOORDIV", "%": "PYMOD", "**": "POW"}
    CALLS = {"int": "TOINT", "float": "TOFLOAT", "len": "LEN", "abs": "ABS",
             "min": "MIN", "max": "MAX", "round": "ROUND"}
    BINOPS = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
              "==": "EQ", "!=": "NEQ", ">": "GT", "<": "LT", ">=": "GTE", "<=": "LTE"}

    def generate(self, program):
        self.code = []
        self.loops = []
        for s in program.statements:
            self._stmt(s)
        self._emit("HALT", None, 0)
        return self.code

    def _emit(self, op, arg=None, line=0):
        self.code.append(Instruction(op, arg, line))
        return len(self.code) - 1

    def _patch(self, idx):
        self.code[idx].arg = len(self.code)       # jump to the next instruction

    # -- statements --------------------------------------------------------
    def _store(self, node, value, default_type=None):
        if value is None:
            self._emit("PUSH", DEFAULTS[default_type], node.line)
        else:
            self._expr(value)
        if node.convert == "toint":
            self._emit("TOINT", None, node.line)
        elif node.convert == "tofloat":
            self._emit("TOFLOAT", None, node.line)
        self._emit("STORE", node.resolved, node.line)

    def _stmt(self, s):
        if isinstance(s, ast.VarDecl):
            self._store(s, s.init, s.decl_type)
        elif isinstance(s, ast.Assign):
            self._store(s, s.value)
        elif isinstance(s, ast.ExprStmt):
            self._expr(s.expr)
            self._emit("POP", None, s.line)
        elif isinstance(s, ast.Print):
            self._expr(s.expr)
            self._emit("PRINT" if s.newline else "WRITE", None, s.line)
        elif isinstance(s, ast.Newline):
            self._emit("NEWLINE", None, s.line)
        elif isinstance(s, (ast.Block, ast.Sequence)):
            for st in s.statements:
                self._stmt(st)
        elif isinstance(s, ast.If):
            self._expr(s.cond)
            jf = self._emit("JMP_IF_FALSE", None, s.line)
            self._stmt(s.then_block)
            if s.else_block:
                jend = self._emit("JMP", None, s.line)
                self._patch(jf)
                self._stmt(s.else_block)
                self._patch(jend)
            else:
                self._patch(jf)
        elif isinstance(s, ast.While):
            start = len(self.code)
            self._expr(s.cond)
            jf = self._emit("JMP_IF_FALSE", None, s.line)
            ctx = {"breaks": [], "conts": [], "target": start}
            self.loops.append(ctx)
            self._stmt(s.body)
            self.loops.pop()
            self._emit("JMP", start, s.line)
            self._patch(jf)
            for i in ctx["breaks"]:
                self._patch(i)
        elif isinstance(s, ast.For):
            if s.init is not None:
                self._stmt(s.init)
            start = len(self.code)
            jf = None
            if s.cond is not None:
                self._expr(s.cond)
                jf = self._emit("JMP_IF_FALSE", None, s.line)
            ctx = {"breaks": [], "conts": [], "target": None}
            self.loops.append(ctx)
            self._stmt(s.body)
            self.loops.pop()
            for i in ctx["conts"]:                   # 'continue' lands on the update part
                self._patch(i)
            if s.update is not None:
                self._stmt(s.update)
            self._emit("JMP", start, s.line)
            if jf is not None:
                self._patch(jf)
            for i in ctx["breaks"]:
                self._patch(i)
        elif isinstance(s, ast.Break):
            self.loops[-1]["breaks"].append(self._emit("JMP", None, s.line))
        elif isinstance(s, ast.Continue):
            ctx = self.loops[-1]
            if ctx["target"] is not None:
                self._emit("JMP", ctx["target"], s.line)
            else:
                ctx["conts"].append(self._emit("JMP", None, s.line))
        elif isinstance(s, ast.Halt):
            self._emit("HALT", None, s.line)

    # -- expressions -------------------------------------------------------
    def _expr(self, e):
        if isinstance(e, (ast.Number, ast.String, ast.Boolean)):
            self._emit("PUSH", e.value, e.line)
        elif isinstance(e, ast.Variable):
            self._emit("LOAD", e.resolved, e.line)
        elif isinstance(e, ast.ToString):
            self._expr(e.expr)
            self._emit("TOSTR", None, e.line)
        elif isinstance(e, ast.FormatExpr):
            self._expr(e.expr)
            self._emit("FORMAT", e.spec, e.line)
        elif isinstance(e, ast.Call):
            for a in e.args:
                self._expr(a)
            self._emit(self.CALLS[e.name], None, e.line)
        elif isinstance(e, ast.UnaryOp):
            self._expr(e.operand)
            self._emit("NEG" if e.op == "-" else "NOT", None, e.line)
        elif isinstance(e, ast.BinaryOp):
            if e.py and e.op == "&&":                # Python 'and': result is an operand value
                self._expr(e.left)
                self._emit("DUP", None, e.line)
                jf = self._emit("JMP_IF_FALSE", None, e.line)
                self._emit("POP", None, e.line)
                self._expr(e.right)
                self._patch(jf)
            elif e.py and e.op == "||":              # Python 'or'
                self._expr(e.left)
                self._emit("DUP", None, e.line)
                jt = self._emit("JMP_IF_TRUE", None, e.line)
                self._emit("POP", None, e.line)
                self._expr(e.right)
                self._patch(jt)
            elif e.op == "&&":                       # short-circuit
                self._expr(e.left)
                jf = self._emit("JMP_IF_FALSE", None, e.line)
                self._expr(e.right)
                jend = self._emit("JMP", None, e.line)
                self._patch(jf)
                self._emit("PUSH", False, e.line)
                self._patch(jend)
            elif e.op == "||":
                self._expr(e.left)
                jf = self._emit("JMP_IF_FALSE", None, e.line)
                self._emit("PUSH", True, e.line)
                jend = self._emit("JMP", None, e.line)
                self._patch(jf)
                self._expr(e.right)
                self._patch(jend)
            else:
                self._expr(e.left)
                self._expr(e.right)
                if e.concat:
                    self._emit("CONCAT", None, e.line)
                elif e.py and e.op in self.PY_BINOPS:
                    self._emit(self.PY_BINOPS[e.op], None, e.line)
                elif e.idiv:
                    self._emit("IDIV", None, e.line)
                else:
                    self._emit(self.BINOPS[e.op], None, e.line)


def format_bytecode(code):
    return "\n".join(f"{i:04d}  {ins}" for i, ins in enumerate(code))
