"""Parser for the Python subset (recursive descent over NEWLINE/INDENT/DEDENT tokens).

Supported: assignment (also chained, tuple, augmented), print(... sep= end=),
if / elif / else, while, for ... in range(...), break, continue, pass, f-strings
(with :format specs), and / or / not, chained comparisons, + - * / // % **,
built-ins str int float len abs min max round.
Not supported (clear message): def/return/class/import/try/with/lambda, lists,
dictionaries, tuples as values, None, input().

Uses the same panic-mode recovery idea as the other parsers: a broken statement
is reported and skipped (with its indented body) so every error is found.
"""
import dataclasses
from . import ast_nodes as ast
from . import tokens as T
from .errors import ParseError
from .languages import PYTHON
from .parser import Parser
from .pylexer import PythonLexer, decode_escapes

AUG = {T.PLUS_ASSIGN: "+", T.MINUS_ASSIGN: "-", T.STAR_ASSIGN: "*", T.SLASH_ASSIGN: "/",
       T.PERCENT_ASSIGN: "%", T.FLOORDIV_ASSIGN: "//", T.POW_ASSIGN: "**"}
CMP = {T.EQ: "==", T.NEQ: "!=", T.LT: "<", T.GT: ">", T.LTE: "<=", T.GTE: ">="}
UNSUPPORTED = {"def", "return", "class", "import", "from", "lambda", "global", "nonlocal",
               "try", "except", "finally", "with", "del", "assert", "raise", "yield",
               "is", "in", "as"}
LINE_END = (T.NEWLINE, T.EOF_, T.DEDENT)


def _relocate(node, line, col):
    """Give every node of an embedded (f-string) expression the f-string's position."""
    if dataclasses.is_dataclass(node):
        node.line, node.col = line, col
        for f in dataclasses.fields(node):
            v = getattr(node, f.name)
            if isinstance(v, list):
                for x in v:
                    _relocate(x, line, col)
            elif dataclasses.is_dataclass(v):
                _relocate(v, line, col)


class PyParser(Parser):
    def __init__(self, tokens, lex_errors=None):
        super().__init__(tokens, lex_errors)
        self._tmp = 0

    @staticmethod
    def _desc(tok):
        if tok.type == T.NEWLINE:
            return "end of line"
        if tok.type == T.INDENT:
            return "an indented block"
        if tok.type == T.DEDENT:
            return "end of block"
        return Parser._desc(tok)

    # -- entry point -------------------------------------------------------
    def parse(self):
        stmts = []
        while self.cur.type != T.EOF_:
            s = self._statement_with_recovery()
            if s is not None:
                stmts.append(s)
        return ast.Program(1, 1, stmts)

    # -- recovery ----------------------------------------------------------
    def _statement_with_recovery(self):
        start_tok, start_pos = self.cur, self.pos
        saved = self._stmt_start
        self._stmt_start = start_tok
        try:
            return self._statement()
        except ParseError as e:
            self._record(e, start_tok)
            self._sync(start_pos)
            return None
        finally:
            self._stmt_start = saved

    def _skip_line(self):
        while self.cur.type not in LINE_END:
            self._advance()

    def _skip_block(self):
        depth = 0
        while self.cur.type != T.EOF_:
            if self.cur.type == T.INDENT:
                depth += 1
            elif self.cur.type == T.DEDENT:
                depth -= 1
            self._advance()
            if depth == 0:
                return

    def _sync(self, start_pos):
        if self.pos == start_pos and self.cur.type not in (T.EOF_, T.DEDENT):
            self._advance()
        self._skip_line()
        if self.cur.type == T.NEWLINE:
            self._advance()
        if self.cur.type == T.INDENT:                 # body of the broken statement
            self._skip_block()

    def _end_simple(self):
        if self.cur.type == T.NEWLINE:
            self._advance()
        elif self.cur.type in (T.EOF_, T.DEDENT):
            return
        else:
            self._record(self._error(f"Invalid syntax: unexpected {self._desc(self.cur)}"))
            self._skip_line()
            if self.cur.type == T.NEWLINE:
                self._advance()

    def _close_paren(self, open_tok):
        if self.cur.type == T.RPAREN:
            return self._advance()
        self._record(self._error(
            f"Expected ')' to close '(' opened at line {open_tok.line}, "
            f"found {self._desc(self.cur)}"))
        while self.cur.type not in (T.RPAREN, T.NEWLINE, T.EOF_, T.DEDENT):
            self._advance()
        if self.cur.type == T.RPAREN:
            self._advance()
        return None

    # -- statements --------------------------------------------------------
    def _statement(self):
        t = self.cur
        if t.type in (T.NEWLINE, T.DEDENT):
            self._advance()
            return None
        if t.type == T.INDENT:
            return self._unexpected_indent()
        if t.type == T.KEYWORD:
            kw = t.lexeme
            if kw == "if":
                return self._if()
            if kw == "while":
                return self._while()
            if kw == "for":
                return self._for()
            if kw == "pass":
                self._advance()
                self._end_simple()
                return None
            if kw in ("break", "continue"):
                self._advance()
                self._end_simple()
                return (ast.Break if kw == "break" else ast.Continue)(t.line, t.col)
            if kw in ("elif", "else"):
                return self._stray_branch()
            if kw in UNSUPPORTED:
                raise ParseError(f"'{kw}' is not supported yet in this Python subset",
                                 t.line, t.col)
        stmt = self._simple_statement()
        self._end_simple()
        return stmt

    def _unexpected_indent(self):
        tok = self._advance()
        self._record(ParseError("Unexpected indent", tok.line, tok.col))
        stmts = []
        while self.cur.type not in (T.DEDENT, T.EOF_):
            s = self._statement_with_recovery()
            if s is not None:
                stmts.append(s)
        if self.cur.type == T.DEDENT:
            self._advance()
        return ast.Sequence(tok.line, tok.col, stmts)

    def _stray_branch(self):
        tok = self._advance()
        self._record(ParseError(f"'{tok.lexeme}' without a matching 'if'", tok.line, tok.col))
        while self.cur.type not in (T.COLON, T.NEWLINE, T.EOF_, T.DEDENT):
            self._advance()
        self._colon(tok.lexeme)
        self._suite(tok)                              # parse and discard the body
        return None

    def _colon(self, owner):
        if self.cur.type == T.COLON:
            return self._advance()
        self._record(self._error(f"Expected ':' after {owner}, found {self._desc(self.cur)}"))
        return None

    def _suite(self, owner):
        if self.cur.type == T.NEWLINE:
            self._advance()
            if self.cur.type != T.INDENT:
                self._record(self._error(
                    f"Expected an indented block after '{owner.lexeme}' (line {owner.line})"))
                return ast.Block(owner.line, owner.col, [])
            self._advance()
            stmts = []
            while self.cur.type not in (T.DEDENT, T.EOF_):
                s = self._statement_with_recovery()
                if s is not None:
                    stmts.append(s)
            if self.cur.type == T.DEDENT:
                self._advance()
            return ast.Block(owner.line, owner.col, stmts)
        if self.cur.type in (T.EOF_, T.DEDENT):
            self._record(self._error(f"Expected an indented block after '{owner.lexeme}'"))
            return ast.Block(owner.line, owner.col, [])
        stmt = self._simple_statement()               # one-line suite:  if x: print(1)
        self._end_simple()
        return ast.Block(owner.line, owner.col, [] if stmt is None else [stmt])

    def _condition(self, owner):
        try:
            return self._expression()
        except ParseError as e:
            self._record(e)
            while self.cur.type not in (T.COLON, T.NEWLINE, T.EOF_, T.DEDENT):
                self._advance()
            return ast.ErrorExpr(owner.line, owner.col)

    def _if(self):
        kw = self._advance()
        cond = self._condition(kw)
        self._colon(f"the '{kw.lexeme}' condition")
        then_block = self._suite(kw)
        else_block = None
        if self._is_kw("elif"):
            nested = self._if()                       # 'elif' behaves like a nested 'if'
            else_block = ast.Block(nested.line, nested.col, [nested])
        elif self._is_kw("else"):
            ek = self._advance()
            self._colon("'else'")
            else_block = self._suite(ek)
        return ast.If(kw.line, kw.col, cond, then_block, else_block)

    def _while(self):
        kw = self._advance()
        cond = self._condition(kw)
        self._colon("the 'while' condition")
        body = self._suite(kw)
        return ast.While(kw.line, kw.col, cond, body)

    def _for(self):
        kw = self._advance()
        var = self._expect(T.IDENTIFIER, "Expected a loop variable after 'for'")
        if not self._is_kw("in"):
            raise self._error(f"Expected 'in' after the loop variable, found {self._desc(self.cur)}")
        self._advance()
        if not (self.cur.type == T.IDENTIFIER and self.cur.lexeme == "range"
                and self._tok(1).type == T.LPAREN):
            raise self._error("Only 'for ... in range(...)' loops are supported")
        self._advance()
        lp = self._advance()
        args = []
        while self.cur.type not in (T.RPAREN, T.NEWLINE, T.EOF_, T.DEDENT):
            args.append(self._expression())
            if self.cur.type == T.COMMA:
                self._advance()
            else:
                break
        self._close_paren(lp)
        if not 1 <= len(args) <= 3:
            raise ParseError(f"range expected 1 to 3 arguments, got {len(args)}", kw.line, kw.col)
        self._colon("the 'for' header")
        body = self._suite(kw)
        return self._desugar_for(kw, var, args, body)

    def _desugar_for(self, kw, var, args, body):
        """for v in range(a, b, s):  ->  hidden counter + For node (so 'continue' works)."""
        n = self._tmp
        self._tmp += 1
        L, C = kw.line, kw.col
        iv, sv, st = f"$i{n}", f"$stop{n}", f"$step{n}"
        V = lambda name: ast.Variable(L, C, name)
        start = args[0] if len(args) > 1 else ast.Number(L, C, 0)
        stop = args[1] if len(args) > 1 else args[0]
        step = args[2] if len(args) == 3 else ast.Number(L, C, 1)
        literal = None
        if isinstance(step, ast.Number):
            literal = step.value
        elif isinstance(step, ast.UnaryOp) and step.op == "-" and isinstance(step.operand, ast.Number):
            literal = -step.operand.value
        if literal == 0:
            raise ParseError("range() step must not be zero", kw.line, kw.col)
        init = [ast.Assign(L, C, iv, start), ast.Assign(L, C, sv, stop)]
        if literal is not None:
            cond = ast.BinaryOp(L, C, "<" if literal > 0 else ">", V(iv), V(sv))
            step_expr = step
        else:
            init.append(ast.Assign(L, C, st, step))
            up = ast.BinaryOp(L, C, "&&", ast.BinaryOp(L, C, ">", V(st), ast.Number(L, C, 0)),
                              ast.BinaryOp(L, C, "<", V(iv), V(sv)))
            down = ast.BinaryOp(L, C, "&&", ast.BinaryOp(L, C, "<", V(st), ast.Number(L, C, 0)),
                                ast.BinaryOp(L, C, ">", V(iv), V(sv)))
            cond = ast.BinaryOp(L, C, "||", up, down)
            step_expr = V(st)
        update = ast.Assign(L, C, iv, ast.BinaryOp(L, C, "+", V(iv), step_expr))
        stmts = [ast.Assign(var.line, var.col, var.lexeme, V(iv))] + body.statements
        return ast.For(L, C, ast.Sequence(L, C, init), cond, update,
                       ast.Block(body.line, body.col, stmts))

    # -- simple statements -------------------------------------------------
    def _simple_statement(self):
        t = self.cur
        if t.type == T.IDENTIFIER:
            nxt = self._tok(1).type
            if t.lexeme == "print" and nxt == T.LPAREN:
                return self._print()
            if nxt == T.ASSIGN or nxt in AUG:
                return self._assignment()
            if nxt == T.COMMA and self._looks_like_targets():
                return self._tuple_assign()
        expr = self._expression()
        if self.cur.type == T.ASSIGN:
            raise self._error("Cannot assign to this expression")
        return ast.ExprStmt(t.line, t.col, expr)

    def _looks_like_targets(self):
        i = self.pos
        while (self.tokens[i].type == T.IDENTIFIER and self.tokens[i + 1].type == T.COMMA):
            i += 2
        return self.tokens[i].type == T.IDENTIFIER and self.tokens[i + 1].type == T.ASSIGN

    def _value(self):
        """Parse the right-hand side; on error keep the target declared (no cascades)."""
        try:
            return self._expression()
        except ParseError as e:
            self._record(e)
            self._skip_line()
            return ast.ErrorExpr(self.cur.line, self.cur.col)

    def _assignment(self):
        names = []
        while self.cur.type == T.IDENTIFIER and self._tok(1).type == T.ASSIGN:
            names.append(self._advance())
            self._advance()
        if names:                                     # a = b = value
            value = self._value()
            last = names[-1]
            out = [ast.Assign(last.line, last.col, last.lexeme, value)]
            for n in reversed(names[:-1]):
                out.append(ast.Assign(n.line, n.col, n.lexeme,
                                      ast.Variable(last.line, last.col, last.lexeme)))
            return out[0] if len(out) == 1 else ast.Sequence(last.line, last.col, out)
        name = self._advance()                        # augmented:  x += value
        op = self._advance()
        value = self._value()
        var = ast.Variable(name.line, name.col, name.lexeme)
        return ast.Assign(name.line, name.col, name.lexeme,
                          ast.BinaryOp(op.line, op.col, AUG[op.type], var, value))

    def _tuple_assign(self):
        names = []
        while True:
            names.append(self._expect(T.IDENTIFIER, "Expected a variable name"))
            if self.cur.type == T.COMMA:
                self._advance()
                continue
            break
        eq = self._expect(T.ASSIGN, "Expected '='")
        values = [self._expression()]
        while self.cur.type == T.COMMA:
            self._advance()
            values.append(self._expression())
        if len(values) != len(names):
            raise ParseError(f"Cannot unpack {len(values)} value(s) into {len(names)} variable(s)",
                             eq.line, eq.col)
        n = self._tmp
        self._tmp += 1
        L, C = names[0].line, names[0].col
        out = [ast.Assign(L, C, f"$t{n}_{i}", v) for i, v in enumerate(values)]
        out += [ast.Assign(nm.line, nm.col, nm.lexeme, ast.Variable(L, C, f"$t{n}_{i}"))
                for i, nm in enumerate(names)]
        return ast.Sequence(L, C, out)

    def _print(self):
        kw = self._advance()
        lp = self._advance()
        args, sep, end = [], None, None
        while self.cur.type not in (T.RPAREN, T.NEWLINE, T.EOF_, T.DEDENT):
            if (self.cur.type == T.IDENTIFIER and self.cur.lexeme in ("sep", "end")
                    and self._tok(1).type == T.ASSIGN):
                key = self._advance().lexeme
                self._advance()
                val = self._expression()
                if key == "sep":
                    sep = val
                else:
                    end = val
            else:
                args.append(self._expression())
            if self.cur.type == T.COMMA:
                self._advance()
            else:
                break
        self._close_paren(lp)
        L, C = kw.line, kw.col
        items = []
        for i, a in enumerate(args):
            if i:
                items.append(ast.Print(L, C, sep if sep is not None else ast.String(L, C, " "), False))
            items.append(ast.Print(L, C, a, False))
        items.append(ast.Newline(L, C) if end is None else ast.Print(L, C, end, False))
        return ast.Sequence(L, C, items)

    # -- expressions -------------------------------------------------------
    def _expression(self):
        return self._or()

    def _or(self):
        left = self._and()
        while self._is_kw("or"):
            t = self._advance()
            left = ast.BinaryOp(t.line, t.col, "||", left, self._and())
        return left

    def _and(self):
        left = self._not()
        while self._is_kw("and"):
            t = self._advance()
            left = ast.BinaryOp(t.line, t.col, "&&", left, self._not())
        return left

    def _not(self):
        if self._is_kw("not"):
            t = self._advance()
            return ast.UnaryOp(t.line, t.col, "!", self._not())
        return self._comparison()

    def _comparison(self):
        operands = [self._arith()]
        ops = []
        while self.cur.type in CMP:
            t = self._advance()
            ops.append((t, CMP[t.type]))
            operands.append(self._arith())
        node = None
        for i, (t, op) in enumerate(ops):             # a < b < c  ->  (a < b) and (b < c)
            cmp_ = ast.BinaryOp(t.line, t.col, op, operands[i], operands[i + 1])
            node = cmp_ if node is None else ast.BinaryOp(t.line, t.col, "&&", node, cmp_)
        return node if node is not None else operands[0]

    def _arith(self):
        left = self._term()
        while self.cur.type in (T.PLUS, T.MINUS):
            t = self._advance()
            left = ast.BinaryOp(t.line, t.col, t.lexeme, left, self._term())
        return left

    def _term(self):
        left = self._factor()
        while self.cur.type in (T.STAR, T.SLASH, T.FLOORDIV, T.PERCENT):
            t = self._advance()
            left = ast.BinaryOp(t.line, t.col, t.lexeme, left, self._factor())
        return left

    def _factor(self):
        if self.cur.type == T.MINUS:
            t = self._advance()
            return ast.UnaryOp(t.line, t.col, "-", self._factor())
        if self.cur.type == T.PLUS:
            self._advance()
            return self._factor()
        return self._power()

    def _power(self):
        base = self._primary()
        if self.cur.type == T.POW:
            t = self._advance()
            return ast.BinaryOp(t.line, t.col, "**", base, self._factor())
        return base

    def _primary(self):
        t = self.cur
        if t.type == T.NUMBER:
            self._advance()
            is_float = any(c in t.lexeme for c in ".eE")
            return ast.Number(t.line, t.col, float(t.lexeme) if is_float else int(t.lexeme))
        if t.type == T.STRING:
            self._advance()
            return ast.String(t.line, t.col, t.lexeme)
        if t.type == T.FSTRING:
            self._advance()
            return self._fstring(t)
        if t.type == T.KEYWORD:
            if t.lexeme in ("True", "False"):
                self._advance()
                return ast.Boolean(t.line, t.col, t.lexeme == "True")
            if t.lexeme == "None":
                raise self._error("'None' is not supported yet in this Python subset")
            if t.lexeme in UNSUPPORTED:
                raise self._error(f"'{t.lexeme}' is not supported yet in this Python subset")
        if t.type == T.IDENTIFIER:
            if self._tok(1).type == T.LPAREN:
                return self._call()
            self._advance()
            return ast.Variable(t.line, t.col, t.lexeme)
        if t.type == T.LPAREN:
            self._advance()
            expr = self._expression()
            if self.cur.type == T.COMMA:
                raise self._error("Tuples are not supported yet in this Python subset")
            self._close_paren(t)
            return expr
        if t.type == T.LBRACKET:
            raise self._error("Lists are not supported yet in this Python subset")
        if t.type == T.LBRACE:
            raise self._error("Dictionaries and sets are not supported yet in this Python subset")
        raise self._error(f"Expected an expression, found {self._desc(t)}")

    def _call(self):
        name = self._advance()
        lp = self._advance()
        args = []
        while self.cur.type not in (T.RPAREN, T.NEWLINE, T.EOF_, T.DEDENT):
            args.append(self._expression())
            if self.cur.type == T.COMMA:
                self._advance()
            else:
                break
        self._close_paren(lp)
        if name.lexeme == "print":
            raise ParseError("print() cannot be used inside an expression", name.line, name.col)
        if name.lexeme == "range":
            raise ParseError("range() can only be used in a 'for' loop", name.line, name.col)
        if name.lexeme == "str" and len(args) == 1:
            return ast.ToString(name.line, name.col, args[0])
        return ast.Call(name.line, name.col, name.lexeme, args)

    # -- f-strings ---------------------------------------------------------
    def _fstring(self, tok):
        raw, n = tok.lexeme, len(tok.lexeme)
        parts, buf, i = [], [], 0

        def flush():
            if buf:
                parts.append(ast.String(tok.line, tok.col, decode_escapes("".join(buf))))
                buf.clear()

        while i < n:
            c = raw[i]
            if c == "{":
                if raw[i + 1:i + 2] == "{":
                    buf.append("{")
                    i += 2
                    continue
                flush()
                j, depth, quote, colon = i + 1, 0, None, None
                while j < n:
                    ch = raw[j]
                    if quote:
                        if ch == quote:
                            quote = None
                    elif ch in "'\"":
                        quote = ch
                    elif ch in "([{":
                        depth += 1
                    elif ch in ")]":
                        depth -= 1
                    elif ch == "}":
                        if depth == 0:
                            break
                        depth -= 1
                    elif ch == ":" and depth == 0 and colon is None:
                        colon = j
                    j += 1
                if j >= n:
                    raise ParseError("f-string: expecting '}'", tok.line, tok.col)
                src = raw[i + 1:(colon if colon is not None else j)].strip()
                spec = raw[colon + 1:j] if colon is not None else None
                if src.endswith(("!r", "!s", "!a")):
                    raise ParseError("f-string conversions (!r, !s, !a) are not supported",
                                     tok.line, tok.col)
                expr = self._embedded(src, tok)
                parts.append(ast.FormatExpr(tok.line, tok.col, expr, spec) if spec
                             else ast.ToString(tok.line, tok.col, expr))
                i = j + 1
            elif c == "}":
                if raw[i + 1:i + 2] == "}":
                    buf.append("}")
                    i += 2
                else:
                    raise ParseError("f-string: single '}' is not allowed", tok.line, tok.col)
            else:
                buf.append(c)
                i += 1
        flush()
        if not parts:
            return ast.String(tok.line, tok.col, "")
        result = parts[0]
        for p in parts[1:]:
            result = ast.BinaryOp(tok.line, tok.col, "+", result, p, concat=True, py=True)
        return result

    def _embedded(self, src, tok):
        if not src:
            raise ParseError("f-string: empty expression is not allowed", tok.line, tok.col)
        lexer = PythonLexer(src, PYTHON)
        toks = lexer.tokenize()
        if lexer.errors:
            raise ParseError(f"f-string: invalid expression '{src}'", tok.line, tok.col)
        sub = PyParser(toks, None)
        try:
            expr = sub._expression()
        except ParseError as e:
            raise ParseError(f"f-string: {e.message}", tok.line, tok.col)
        if sub.errors or sub.cur.type not in (T.NEWLINE, T.EOF_):
            raise ParseError(f"f-string: invalid expression '{src}'", tok.line, tok.col)
        _relocate(expr, tok.line, tok.col)
        return expr
