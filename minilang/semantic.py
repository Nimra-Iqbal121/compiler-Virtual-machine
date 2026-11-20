"""Semantic analyzer (shared by all languages, with per-dialect rules).

Checks: declared-before-use, duplicate declarations per block scope, static
types (int / float / string / bool), operator compatibility, break/continue
placement, and implicit conversions (annotated on the AST for the generator).

Block scoping with flat VM memory: each declaration gets a unique `resolved`
name (x, x#1, x#2 ...) so shadowed variables never collide at runtime.
"""
from . import ast_nodes as ast
from .errors import SemanticError

INT, FLOAT, STRING, BOOL = "int", "float", "string", "bool"
NUM = (INT, FLOAT)

TYPE_NAMES = {
    "minilang": {INT: "number", FLOAT: "number", STRING: "string", BOOL: "bool"},
    "cpp": {INT: "int", FLOAT: "double", STRING: "string", BOOL: "bool"},
    "java": {INT: "int", FLOAT: "double", STRING: "String", BOOL: "boolean"},
    "python": {INT: "int", FLOAT: "float", STRING: "str", BOOL: "bool"},
}

# Python built-ins: name -> (number of arguments, result type or None if it depends)
PY_FUNCS = {"int": (1, INT), "float": (1, FLOAT), "len": (1, INT), "abs": (1, None),
            "min": (2, None), "max": (2, None), "round": (1, INT)}


class Symbol:
    def __init__(self, type_, resolved):
        self.type = type_
        self.resolved = resolved


class SemanticAnalyzer:
    def __init__(self, dialect="minilang"):
        self.dialect = dialect
        self.names = TYPE_NAMES[dialect]
        self.scopes = [{}]
        self.errors = []
        self._counts = {}
        self.loop_depth = 0
        self.py = dialect == "python"     # dynamic typing, one flat scope, runtime type errors

    def analyze(self, program):
        for stmt in program.statements:
            self._stmt(stmt)
        return self.errors

    # -- helpers -----------------------------------------------------------
    def tn(self, t):
        return self.names.get(t, str(t))

    def _err(self, msg, node):
        self.errors.append(SemanticError(msg, node.line, node.col))

    def _lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def _declare(self, name, type_, node):
        if name in self.scopes[-1]:
            self._err(f"Variable '{name}' is already declared in this scope", node)
            return self.scopes[-1][name]
        n = self._counts.get(name, 0)
        self._counts[name] = n + 1
        sym = Symbol(type_, name if n == 0 else f"{name}#{n}")
        self.scopes[-1][name] = sym
        return sym

    def _coerce(self, target, got, name, node):
        """Check `got` can be stored in a variable of type `target`.
        Returns the conversion the generator must emit ("toint"/"tofloat"/None)."""
        if target is None or got is None or target == got:
            return None
        if target in NUM and got in NUM:
            if self.dialect == "minilang":
                return None
            if target == FLOAT:
                return "tofloat"
            if self.dialect == "cpp":
                return "toint"                       # C++ truncates silently
            self._err(f"Type mismatch: possible lossy conversion from {self.tn(got)} "
                      f"to {self.tn(target)} for variable '{name}'", node)
            return None
        self._err(f"Type mismatch: cannot assign '{self.tn(got)}' to variable "
                  f"'{name}' of type '{self.tn(target)}'", node)
        return None

    # -- statements --------------------------------------------------------
    def _stmt(self, s):
        if isinstance(s, ast.VarDecl):
            self._var_decl(s)
        elif isinstance(s, ast.Assign) and self.py:
            t = self._expr(s.value)
            sym = self._lookup(s.name)
            if sym is None:
                sym = self._declare(s.name, t, s)      # first assignment creates the variable
            else:
                sym.type = t                           # Python variables can change type
            s.resolved = sym.resolved
        elif isinstance(s, ast.ExprStmt):
            self._expr(s.expr)
        elif isinstance(s, ast.Assign):
            t = self._expr(s.value)
            sym = self._lookup(s.name)
            if sym is None:
                self._err(f"Variable '{s.name}' is not declared", s)
                return
            s.resolved = sym.resolved
            s.convert = self._coerce(sym.type, t, s.name, s)
        elif isinstance(s, ast.Print):
            self._expr(s.expr)
        elif isinstance(s, ast.Block):
            self._block(s)
        elif isinstance(s, ast.Sequence):
            for st in s.statements:
                self._stmt(st)
        elif isinstance(s, ast.If):
            self._condition(s.cond, "if")
            self._block(s.then_block)
            if s.else_block:
                self._block(s.else_block)
        elif isinstance(s, ast.While):
            self._condition(s.cond, "while")
            self.loop_depth += 1
            self._block(s.body)
            self.loop_depth -= 1
        elif isinstance(s, ast.For):
            if not self.py:
                self.scopes.append({})
            if s.init is not None:
                self._stmt(s.init)
            if s.cond is not None:
                self._condition(s.cond, "for")
            self.loop_depth += 1
            self._block(s.body)
            if s.update is not None:
                self._stmt(s.update)
            self.loop_depth -= 1
            if not self.py:
                self.scopes.pop()
        elif isinstance(s, (ast.Break, ast.Continue)):
            if self.loop_depth == 0:
                word = "break" if isinstance(s, ast.Break) else "continue"
                self._err(f"'{word}' used outside of a loop", s)
        elif isinstance(s, ast.Halt):
            if s.expr is not None:
                self._expr(s.expr)

    def _var_decl(self, s):
        if s.init is None:
            t = s.decl_type
            if t == "auto":
                self._err(f"Cannot infer the type of '{s.name}' without an initializer", s)
                t = None
        else:
            it = self._expr(s.init)
            if s.decl_type and s.decl_type != "auto":
                t = s.decl_type
                s.convert = self._coerce(t, it, s.name, s)
            else:
                t = it
        s.resolved = self._declare(s.name, t, s).resolved

    def _block(self, block):
        if not self.py:
            self.scopes.append({})
        for st in block.statements:
            self._stmt(st)
        if not self.py:
            self.scopes.pop()

    def _condition(self, cond, kw):
        t = self._expr(cond)
        if self.py:
            return                                     # any value has a truth value
        if t is not None and t != BOOL:
            self._err(f"Condition of '{kw}' must be a boolean expression, "
                      f"got '{self.tn(t)}'", cond)

    # -- expressions (return a type name, or None after an error) ---------------
    def _expr(self, e):
        if isinstance(e, ast.Number):
            e.etype = INT if isinstance(e.value, int) else FLOAT
        elif isinstance(e, ast.String):
            e.etype = STRING
        elif isinstance(e, ast.Boolean):
            e.etype = BOOL
        elif isinstance(e, ast.Variable):
            sym = self._lookup(e.name)
            if sym is None:
                self._err(f"name '{e.name}' is not defined" if self.py
                          else f"Variable '{e.name}' is not declared", e)
                e.etype = None
            else:
                e.resolved = sym.resolved
                e.etype = sym.type
        elif isinstance(e, ast.ToString):
            self._expr(e.expr)
            e.etype = STRING
        elif isinstance(e, ast.FormatExpr):
            self._expr(e.expr)
            e.etype = STRING
        elif isinstance(e, ast.Call):
            e.etype = self._call(e)
        elif isinstance(e, ast.UnaryOp):
            e.etype = self._unary(e)
        elif isinstance(e, ast.BinaryOp):
            e.etype = self._binary(e)
        else:                                          # ErrorExpr
            return None
        return e.etype

    def _call(self, e):
        for a in e.args:
            self._expr(a)
        spec = PY_FUNCS.get(e.name)
        if spec is None:
            self._err(f"name '{e.name}' is not defined", e)
            return None
        n, rtype = spec
        if len(e.args) != n:
            self._err(f"{e.name}() takes exactly {n} argument{'s' if n != 1 else ''} "
                      f"({len(e.args)} given)", e)
            return None
        if e.name == "abs":
            return e.args[0].etype if e.args[0].etype in NUM else None
        return rtype

    def _unary(self, e):
        t = self._expr(e.operand)
        if self.py:
            return BOOL if e.op == "!" else (t if t in NUM else None)
        if t is None:
            return None
        if e.op == "-" and t in NUM:
            return t
        if e.op == "!" and t == BOOL:
            return BOOL
        self._err(f"Invalid operation: cannot apply unary '{e.op}' to '{self.tn(t)}'", e)
        return None

    def _binary_py(self, e, lt, rt):
        """Python is dynamically typed: type problems are runtime errors, not compile errors."""
        e.py = True
        op = e.op
        num = lt in NUM and rt in NUM
        numtype = INT if lt == INT and rt == INT else FLOAT
        if op in ("==", "!=", "<", ">", "<=", ">="):
            return BOOL
        if op == "/":
            return FLOAT if num else None
        if op == "+":
            if lt == rt == STRING:
                return STRING
            return numtype if num else None
        if op == "*" and STRING in (lt, rt):
            return STRING if STRING in (lt, rt) and (lt in NUM or rt in NUM) else None
        if op in ("-", "*", "//", "%", "**"):
            if op == "**" and num and not (lt == INT and rt == INT):
                return FLOAT
            return numtype if num else None
        return None                                  # and / or: value of one of the operands

    def _binary(self, e):
        lt, rt = self._expr(e.left), self._expr(e.right)
        if self.py:
            return self._binary_py(e, lt, rt)
        if lt is None or rt is None:
            return None                              # avoid cascading errors
        op = e.op
        num = lt in NUM and rt in NUM
        both_int = lt == INT and rt == INT
        numtype = INT if both_int else FLOAT

        def bad():
            self._err(f"Invalid operation: cannot apply '{op}' to "
                      f"'{self.tn(lt)}' and '{self.tn(rt)}'", e)
            return None

        if op == "+":
            if num:
                return numtype
            if lt == rt == STRING:
                return STRING
            if self.dialect == "java" and STRING in (lt, rt):
                e.concat = True
                return STRING
            return bad()
        if op in ("-", "*"):
            return numtype if num else bad()
        if op == "/":
            if not num:
                return bad()
            if self.dialect != "minilang" and both_int:
                e.idiv = True
            return numtype
        if op == "%":
            if not num or (self.dialect == "cpp" and not both_int):
                return bad()
            return numtype
        if op in ("<", ">", "<=", ">="):
            return BOOL if num else bad()
        if op in ("==", "!="):
            return BOOL if (num or lt == rt) else bad()
        if op in ("&&", "||"):
            return BOOL if lt == rt == BOOL else bad()
        return bad()
