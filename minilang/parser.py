"""Syntax analyzer for MiniLang: recursive-descent parser producing an AST.

ERROR RECOVERY - like a real compiler, the parser does NOT stop at the first
mistake. It records the error, repairs/skips to a safe point ("panic mode")
and keeps parsing, so every syntax error in the file is reported in one pass.

Grammar (EBNF)
    program    := statement* EOF
    statement  := letStmt | assignStmt | printStmt | ifStmt | whileStmt
                | "break" ";" | "continue" ";" | block
    letStmt    := "let" IDENT "=" expr ";"
    assignStmt := IDENT "=" expr ";"
    printStmt  := "print" "(" expr ")" ";"
    ifStmt     := "if" "(" expr ")" block [ "else" ( ifStmt | block ) ]
    whileStmt  := "while" "(" expr ")" block
    block      := "{" statement* "}"
    expr       := or
    or         := and ( "||" and )*
    and        := equality ( "&&" equality )*
    equality   := comparison ( ("==" | "!=") comparison )*
    comparison := term ( ("<" | ">" | "<=" | ">=") term )*
    term       := factor ( ("+" | "-") factor )*
    factor     := unary ( ("*" | "/" | "%") unary )*
    unary      := ("-" | "!") unary | primary
    primary    := NUMBER | STRING | "true" | "false" | IDENT | "(" expr ")"
"""
from . import ast_nodes as ast
from . import tokens as T
from .errors import ParseError


class Parser:
    STMT_KEYWORDS = {"let", "print", "if", "while", "break", "continue"}

    def __init__(self, tokens, lex_errors=None):
        self.tokens = tokens
        self.pos = 0
        self.errors = []
        # positions of lexical errors: used to hide follow-on (cascade) syntax errors
        self._lex_pos = sorted((e.line or 0, e.col or 0) for e in (lex_errors or []))
        self._stmt_start = None
        self._depth = 0                      # block nesting (for recovery)

    # -- helpers -----------------------------------------------------------
    @property
    def cur(self):
        return self.tokens[self.pos]

    @property
    def prev(self):
        return self.tokens[self.pos - 1]

    def _tok(self, offset=1):
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def _advance(self):
        tok = self.cur
        if tok.type != T.EOF_:
            self.pos += 1
        return tok

    def _is_kw(self, word):
        return self.cur.type == T.KEYWORD and self.cur.lexeme == word

    @staticmethod
    def _desc(tok):
        if tok.type == T.EOF_:
            return "end of input"
        if tok.type == T.STRING:
            return f'"{tok.lexeme}"'
        return f"'{tok.lexeme}'"

    def _error(self, msg, tok=None):
        tok = tok or self.cur
        return ParseError(msg, tok.line, tok.col)

    def _expect(self, type_, msg):
        if self.cur.type == type_:
            return self._advance()
        raise self._error(f"{msg}, found {self._desc(self.cur)}")

    # -- error recording / recovery ----------------------------------------
    def _record(self, err, start=None):
        start = start or self._stmt_start
        if start is not None:                # consequence of a lexical error? hide it
            lo, hi = (start.line, start.col), (err.line or 0, err.col or 0)
            if any(lo <= p <= hi for p in self._lex_pos):
                return
        for e in self.errors:
            if (e.line, e.col, e.message) == (err.line, err.col, err.message):
                return
        self.errors.append(err)

    def _at_statement_start(self):
        return self.cur.type == T.KEYWORD and self.cur.lexeme in self.STMT_KEYWORDS

    def _synchronize(self, start_pos=None):
        """Skip tokens until a safe place to resume parsing."""
        if start_pos is not None and self.pos == start_pos and self.cur.type != T.EOF_:
            self._advance()                  # guarantee progress
        while self.cur.type != T.EOF_:
            if self.pos > 0 and self.prev.type == T.SEMICOLON:
                return
            if self.cur.type == T.RBRACE:
                if self._depth > 0:
                    return
                self._advance()
                continue
            if self._at_statement_start():
                return
            self._advance()

    def _statement_with_recovery(self):
        start_tok, start_pos = self.cur, self.pos
        saved = self._stmt_start
        self._stmt_start = start_tok
        try:
            return self._statement()
        except ParseError as e:
            self._record(e, start_tok)
            self._synchronize(start_pos)
            return None
        finally:
            self._stmt_start = saved

    def _expect_semicolon(self):
        if self.cur.type == T.SEMICOLON:
            return self._advance()
        nxt = self.cur
        if nxt.type in (T.EOF_, T.RBRACE) or nxt.line > self.prev.line:
            # classic recovery: pretend the ';' was there and carry on
            self._record(ParseError("Missing semicolon", self.prev.line, self.prev.end_col))
            return None
        self._record(self._error(f"Expected ';' but found {self._desc(nxt)}"))
        while (self.cur.type not in (T.SEMICOLON, T.EOF_, T.RBRACE)
               and not self._at_statement_start()):
            self._advance()
        if self.cur.type == T.SEMICOLON:
            self._advance()
        return None

    def _close_paren(self, open_tok):
        if self.cur.type == T.RPAREN:
            return self._advance()
        self._record(self._error(
            f"Expected ')' to close '(' opened at line {open_tok.line}, "
            f"found {self._desc(self.cur)}"))
        while (self.cur.type not in (T.RPAREN, T.SEMICOLON, T.EOF_, T.RBRACE, T.LBRACE)
               and not self._at_statement_start()):
            self._advance()
        if self.cur.type == T.RPAREN:
            self._advance()
        return None

    # -- entry point -------------------------------------------------------
    def parse(self):
        stmts = []
        while self.cur.type != T.EOF_:
            s = self._statement_with_recovery()
            if s is not None:
                stmts.append(s)
        return ast.Program(1, 1, stmts)

    # -- statements --------------------------------------------------------
    def _statement(self):
        t = self.cur
        if t.type == T.KEYWORD:
            kw = t.lexeme
            if kw == "let":
                return self._let()
            if kw == "print":
                return self._print()
            if kw == "if":
                return self._if()
            if kw == "while":
                return self._while()
            if kw in ("break", "continue"):
                return self._jump()
            if kw == "else":
                return self._stray_else()
            raise self._error(f"Invalid statement: unexpected keyword '{kw}'")
        if t.type == T.LBRACE:
            return self._block()
        if t.type == T.IDENTIFIER:
            return self._assignment()
        raise self._error(f"Invalid statement: unexpected {self._desc(t)}")

    def _stray_else(self):
        tok = self._advance()
        self._record(ParseError("'else' without a matching 'if'", tok.line, tok.col))
        if self.cur.type == T.LBRACE:        # parse and discard its block to avoid cascades
            self._block("else")
        return None

    def _jump(self):
        kw = self._advance()
        self._expect_semicolon()
        node = ast.Break if kw.lexeme == "break" else ast.Continue
        return node(kw.line, kw.col)

    def _let(self):
        kw = self._advance()
        name = self._expect(T.IDENTIFIER, "Expected variable name after 'let'")
        try:
            self._expect(T.ASSIGN, f"Expected '=' after '{name.lexeme}'")
            init = self._expression()
        except ParseError as e:
            self._record(e)
            self._synchronize()
            # keep the declaration so later uses of the name don't cascade
            return ast.VarDecl(kw.line, kw.col, name.lexeme, ast.ErrorExpr(name.line, name.col))
        self._expect_semicolon()
        return ast.VarDecl(kw.line, kw.col, name.lexeme, init)

    def _assignment(self):
        name = self._advance()
        if self.cur.type != T.ASSIGN:
            raise self._error(
                f"Invalid statement: expected '=' after '{name.lexeme}', "
                f"found {self._desc(self.cur)}")
        self._advance()
        try:
            value = self._expression()
        except ParseError as e:
            self._record(e)
            self._synchronize()
            return ast.Assign(name.line, name.col, name.lexeme, ast.ErrorExpr(name.line, name.col))
        self._expect_semicolon()
        return ast.Assign(name.line, name.col, name.lexeme, value)

    def _print(self):
        kw = self._advance()
        lp = self._expect(T.LPAREN, "Expected '(' after 'print'")
        expr = self._expression()
        self._close_paren(lp)
        self._expect_semicolon()
        return ast.Print(kw.line, kw.col, expr)

    def _paren_condition(self, kw):
        """'(' expr ')' for if/while - recovers from a missing/broken parenthesis."""
        if self.cur.type == T.LPAREN:
            lp = self._advance()
        else:
            self._record(self._error(f"Expected '(' after '{kw}', found {self._desc(self.cur)}"))
            lp = None
        try:
            cond = self._expression()
        except ParseError as e:
            self._record(e)
            while self.cur.type not in (T.RPAREN, T.LBRACE, T.SEMICOLON, T.EOF_):
                self._advance()
            if self.cur.type == T.RPAREN:
                self._advance()
            return ast.ErrorExpr(self.cur.line, self.cur.col)
        if lp is not None:
            self._close_paren(lp)
        elif self.cur.type == T.RPAREN:
            self._advance()
        return cond

    def _if(self):
        kw = self._advance()
        cond = self._paren_condition("if")
        then_block = self._body("if")
        else_block = None
        if self._is_kw("else"):
            self._advance()
            if self._is_kw("if"):
                nested = self._if()
                else_block = ast.Block(nested.line, nested.col, [nested])
            else:
                else_block = self._body("else")
        return ast.If(kw.line, kw.col, cond, then_block, else_block)

    def _while(self):
        kw = self._advance()
        cond = self._paren_condition("while")
        body = self._body("while")
        return ast.While(kw.line, kw.col, cond, body)

    def _body(self, owner):
        return self._block(owner)

    def _block(self, owner=None):
        what = f"to start the '{owner}' body" if owner else "to start a block"
        lb = self._expect(T.LBRACE, f"Expected '{{' {what}")
        self._depth += 1
        stmts = []
        while self.cur.type != T.RBRACE:
            if self.cur.type == T.EOF_:
                self._record(ParseError(
                    f"Expected '}}' to close block opened at line {lb.line}, "
                    f"found end of input", self.cur.line, self.cur.col))
                break
            s = self._statement_with_recovery()
            if s is not None:
                stmts.append(s)
        self._depth -= 1
        if self.cur.type == T.RBRACE:
            self._advance()
        return ast.Block(lb.line, lb.col, stmts)

    # -- expressions -------------------------------------------------------
    def _expression(self):
        return self._binary_level(0)

    _LEVELS = [
        {T.OR: "||"},
        {T.AND: "&&"},
        {T.EQ: "==", T.NEQ: "!="},
        {T.LT: "<", T.GT: ">", T.LTE: "<=", T.GTE: ">="},
        {T.PLUS: "+", T.MINUS: "-"},
        {T.STAR: "*", T.SLASH: "/", T.PERCENT: "%"},
    ]

    def _binary_level(self, level):
        if level == len(self._LEVELS):
            return self._unary()
        ops = self._LEVELS[level]
        left = self._binary_level(level + 1)
        while self.cur.type in ops:
            op_tok = self._advance()
            right = self._binary_level(level + 1)
            left = ast.BinaryOp(op_tok.line, op_tok.col, ops[op_tok.type], left, right)
        return left

    def _unary(self):
        if self.cur.type in (T.MINUS, T.BANG):
            tok = self._advance()
            return ast.UnaryOp(tok.line, tok.col, tok.lexeme, self._unary())
        return self._primary()

    def _primary(self):
        t = self.cur
        if t.type == T.NUMBER:
            self._advance()
            value = float(t.lexeme) if "." in t.lexeme else int(t.lexeme)
            return ast.Number(t.line, t.col, value)
        if t.type == T.STRING:
            self._advance()
            return ast.String(t.line, t.col, t.lexeme)
        if t.type == T.KEYWORD and t.lexeme in ("true", "false"):
            self._advance()
            return ast.Boolean(t.line, t.col, t.lexeme == "true")
        if t.type == T.IDENTIFIER:
            self._advance()
            return ast.Variable(t.line, t.col, t.lexeme)
        if t.type == T.LPAREN:
            self._advance()
            expr = self._expression()
            self._close_paren(t)
            return expr
        raise self._error(f"Expected an expression, found {self._desc(t)}")
