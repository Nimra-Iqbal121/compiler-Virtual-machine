"""Front end for the C++ and Java teaching subsets.

Both languages are parsed by one class (they share the C-style statement syntax);
the `dialect` switches the small differences:

  C++ : #include / using namespace, int main(){}, cout << a << endl, to_string(x)
  Java: public class X { public static void main(String[] a){} },
        System.out.println(x), String.valueOf(x)

Supported: int/long/short, double/float, bool/boolean, string/String, char (as
string), auto/var, declarations (several per line), = += -= *= /= %= ++ --,
if / else if / else, while, for, break, continue, return, && || !, % and
single-statement bodies. Not supported (clear error message): user-defined
functions, classes other than the one holding main, arrays, do-while, input.
Uses the same panic-mode error recovery as the MiniLang parser.
"""
from . import ast_nodes as ast
from . import tokens as T
from .errors import ParseError
from .parser import Parser

CPP_TYPES = {"int": "int", "long": "int", "short": "int", "double": "float",
             "float": "float", "bool": "bool", "string": "string", "char": "string",
             "auto": "auto"}
JAVA_TYPES = {"int": "int", "long": "int", "short": "int", "double": "float",
              "float": "float", "boolean": "bool", "String": "string", "char": "string",
              "var": "auto"}
CPP_MODS = {"const", "static"}
JAVA_MODS = {"final", "static", "public", "private", "protected"}
COMPOUND = {T.PLUS_ASSIGN: "+", T.MINUS_ASSIGN: "-", T.STAR_ASSIGN: "*",
            T.SLASH_ASSIGN: "/", T.PERCENT_ASSIGN: "%"}
CONTROL = {"if", "while", "for", "return", "break", "continue", "do"}


class CFamilyParser(Parser):
    def __init__(self, tokens, dialect, lex_errors=None):
        super().__init__(tokens, lex_errors)
        self.dialect = dialect
        self.is_cpp = dialect == "cpp"
        self.types = CPP_TYPES if self.is_cpp else JAVA_TYPES
        self.mods = CPP_MODS if self.is_cpp else JAVA_MODS

    # -- small helpers -----------------------------------------------------
    def _skip_std(self):
        if (self.is_cpp and self.cur.type == T.IDENTIFIER and self.cur.lexeme == "std"
                and self._tok(1).type == T.SCOPE):
            self._advance(); self._advance()

    def _is_type_start(self):
        return (self.cur.type == T.KEYWORD
                and (self.cur.lexeme in self.types or self.cur.lexeme in self.mods))

    def _at_statement_start(self):
        t = self.cur
        if t.type == T.KEYWORD:
            return t.lexeme in self.types or t.lexeme in CONTROL
        return t.type == T.IDENTIFIER and t.lexeme in ("cout", "System")

    def _expect_kw(self, word):
        if self._is_kw(word):
            return self._advance()
        raise self._error(f"Expected '{word}', found {self._desc(self.cur)}")

    def _skip_to_rparen(self):
        while self.cur.type not in (T.RPAREN, T.EOF_):
            self._advance()

    # -- program structure -------------------------------------------------
    def parse(self):
        stmts = []
        while self.cur.type != T.EOF_:
            start_tok, start_pos = self.cur, self.pos
            saved = self._stmt_start
            self._stmt_start = start_tok
            try:
                item = self._top_level()
            except ParseError as e:
                self._record(e, start_tok)
                self._synchronize(start_pos)
                item = None
            finally:
                self._stmt_start = saved
            if isinstance(item, list):
                stmts.extend(item)
            elif item is not None:
                stmts.append(item)
        return ast.Program(1, 1, stmts)

    def _top_level(self):
        if self.is_cpp:
            if self._is_kw("using"):
                while self.cur.type not in (T.SEMICOLON, T.EOF_):
                    self._advance()
                self._expect(T.SEMICOLON, "Expected ';' after 'using'")
                return None
            if self._is_main_decl():
                return self._function_main()
        else:
            if self._is_kw("import") or self._is_kw("package"):
                while self.cur.type not in (T.SEMICOLON, T.EOF_):
                    self._advance()
                self._expect(T.SEMICOLON, "Expected ';' after import")
                return None
            if self._is_class_decl():
                return self._java_class()
        return self._statement()

    def _is_main_decl(self):
        return (self.cur.type == T.KEYWORD and self.cur.lexeme in ("int", "void")
                and self._tok(1).type == T.IDENTIFIER and self._tok(1).lexeme == "main"
                and self._tok(2).type == T.LPAREN)

    def _function_main(self):
        self._advance(); self._advance(); self._advance()      # int main (
        self._skip_to_rparen()
        self._expect(T.RPAREN, "Expected ')' after the parameters of main")
        return self._block("main")

    def _is_class_decl(self):
        i = self.pos
        while self.tokens[i].type == T.KEYWORD and self.tokens[i].lexeme in self.mods:
            i += 1
        return self.tokens[i].type == T.KEYWORD and self.tokens[i].lexeme == "class"

    def _java_class(self):
        while self.cur.type == T.KEYWORD and self.cur.lexeme in self.mods:
            self._advance()
        self._expect_kw("class")
        name = self._expect(T.IDENTIFIER, "Expected a class name after 'class'")
        lb = self._expect(T.LBRACE, "Expected '{' to start the class body")
        self._depth += 1
        body = []
        while self.cur.type != T.RBRACE:
            if self.cur.type == T.EOF_:
                self._record(ParseError(
                    f"Expected '}}' to close class '{name.lexeme}' opened at line {lb.line}",
                    self.cur.line, self.cur.col))
                break
            member = self._java_member()
            if member is not None:
                body.append(member)
        self._depth -= 1
        if self.cur.type == T.RBRACE:
            self._advance()
        return body

    def _java_member(self):
        start = self.cur
        while self.cur.type == T.KEYWORD and self.cur.lexeme in self.mods:
            self._advance()
        if (self._is_kw("void") and self._tok(1).type == T.IDENTIFIER
                and self._tok(1).lexeme == "main" and self._tok(2).type == T.LPAREN):
            self._advance(); self._advance(); self._advance()
            self._skip_to_rparen()
            self._expect(T.RPAREN, "Expected ')' after the parameters of main")
            return self._block("main")
        self._record(ParseError(
            "Only the 'main' method is supported inside a class "
            "(user-defined methods and fields are not supported yet)",
            start.line, start.col), start)
        self._skip_member()
        return None

    def _skip_member(self):
        while self.cur.type not in (T.EOF_, T.SEMICOLON, T.LBRACE, T.RBRACE):
            self._advance()
        if self.cur.type == T.SEMICOLON:
            self._advance()
        elif self.cur.type == T.LBRACE:
            depth = 0
            while self.cur.type != T.EOF_:
                if self.cur.type == T.LBRACE:
                    depth += 1
                elif self.cur.type == T.RBRACE:
                    depth -= 1
                self._advance()
                if depth == 0:
                    break

    # -- statements --------------------------------------------------------
    def _body(self, owner):
        if self.cur.type == T.LBRACE:
            return self._block(owner)
        start = self.cur
        stmt = self._statement()
        return ast.Block(start.line, start.col, [] if stmt is None else [stmt])

    def _statement(self):
        self._skip_std()
        t = self.cur
        if t.type == T.LBRACE:
            return self._block()
        if t.type == T.SEMICOLON:
            self._advance()
            return None
        if t.type == T.KEYWORD:
            kw = t.lexeme
            if self._is_type_start():
                return self._declaration()
            if kw == "if":
                return self._if()
            if kw == "while":
                return self._while()
            if kw == "for":
                return self._for()
            if kw == "return":
                return self._return()
            if kw in ("break", "continue"):
                return self._jump()
            if kw == "else":
                return self._stray_else()
            if kw == "do":
                raise self._error("'do-while' loops are not supported yet; use a 'while' loop")
            raise self._error(f"Invalid statement: unexpected keyword '{kw}'")
        if t.type == T.IDENTIFIER:
            if self.is_cpp and t.lexeme == "cout":
                return self._cout()
            if not self.is_cpp and t.lexeme == "System":
                return self._system_out()
            return self._assign_stmt()
        if t.type in (T.INC, T.DEC):
            return self._assign_stmt()
        raise self._error(f"Invalid statement: unexpected {self._desc(t)}")

    def _declaration(self, expect_semi=True):
        while self.cur.type == T.KEYWORD and self.cur.lexeme in self.mods:
            self._advance()
        if not (self.cur.type == T.KEYWORD and self.cur.lexeme in self.types):
            raise self._error(f"Expected a type name, found {self._desc(self.cur)}")
        type_tok = self._advance()
        ctype = self.types[type_tok.lexeme]
        decls = []
        while True:
            name = self._expect(T.IDENTIFIER,
                                f"Expected a variable name after '{type_tok.lexeme}'")
            init = None
            if self.cur.type == T.ASSIGN:
                self._advance()
                try:
                    init = self._expression()
                except ParseError as e:
                    if not expect_semi:
                        raise
                    self._record(e)
                    self._synchronize()
                    decls.append(ast.VarDecl(type_tok.line, type_tok.col, name.lexeme,
                                             ast.ErrorExpr(name.line, name.col), ctype))
                    return decls[0] if len(decls) == 1 else \
                        ast.Sequence(type_tok.line, type_tok.col, decls)
            decls.append(ast.VarDecl(type_tok.line, type_tok.col, name.lexeme, init, ctype))
            if self.cur.type == T.COMMA:
                self._advance()
                continue
            break
        if expect_semi:
            self._expect_semicolon()
        return decls[0] if len(decls) == 1 else ast.Sequence(type_tok.line, type_tok.col, decls)

    def _incdec(self, name, ttype):
        op = "+" if ttype == T.INC else "-"
        one = ast.Number(name.line, name.col, 1)
        var = ast.Variable(name.line, name.col, name.lexeme)
        return ast.Assign(name.line, name.col, name.lexeme,
                          ast.BinaryOp(name.line, name.col, op, var, one))

    def _assign_stmt(self, expect_semi=True):
        first = self.cur
        if first.type in (T.INC, T.DEC):
            self._advance()
            name = self._expect(T.IDENTIFIER, f"Expected a variable after '{first.lexeme}'")
            node = self._incdec(name, first.type)
        else:
            name = self._advance()
            nt = self.cur
            if nt.type in (T.INC, T.DEC):
                self._advance()
                node = self._incdec(name, nt.type)
            elif nt.type == T.ASSIGN or nt.type in COMPOUND:
                self._advance()
                try:
                    value = self._expression()
                except ParseError as e:
                    if not expect_semi:
                        raise
                    self._record(e)
                    self._synchronize()
                    return ast.Assign(name.line, name.col, name.lexeme,
                                      ast.ErrorExpr(name.line, name.col))
                if nt.type != T.ASSIGN:
                    var = ast.Variable(name.line, name.col, name.lexeme)
                    value = ast.BinaryOp(nt.line, nt.col, COMPOUND[nt.type], var, value)
                node = ast.Assign(name.line, name.col, name.lexeme, value)
            elif nt.type == T.LPAREN:
                raise ParseError(f"Function calls are not supported yet ('{name.lexeme}')",
                                 name.line, name.col)
            else:
                raise self._error(f"Invalid statement: expected '=' after '{name.lexeme}', "
                                  f"found {self._desc(nt)}")
        if expect_semi:
            self._expect_semicolon()
        return node

    def _cout(self):
        start = self._advance()
        if self.cur.type != T.SHL:
            raise self._error(f"Expected '<<' after 'cout', found {self._desc(self.cur)}")
        items = []
        while self.cur.type == T.SHL:
            self._advance()
            self._skip_std()
            if self.cur.type == T.IDENTIFIER and self.cur.lexeme == "endl":
                tok = self._advance()
                items.append(ast.Newline(tok.line, tok.col))
            else:
                tok = self.cur
                items.append(ast.Print(tok.line, tok.col, self._expression(), False))
        self._expect_semicolon()
        return ast.Sequence(start.line, start.col, items)

    def _system_out(self):
        start = self._advance()
        self._expect(T.DOT, "Expected '.' after 'System'")
        out = self._expect(T.IDENTIFIER, "Expected 'out' after 'System.'")
        if out.lexeme != "out":
            raise self._error("Only 'System.out' is supported", out)
        self._expect(T.DOT, "Expected '.' after 'System.out'")
        fn = self._expect(T.IDENTIFIER, "Expected 'println' or 'print'")
        if fn.lexeme not in ("println", "print"):
            raise self._error(f"Unsupported method 'System.out.{fn.lexeme}'; "
                              f"use println or print", fn)
        lp = self._expect(T.LPAREN, f"Expected '(' after '{fn.lexeme}'")
        expr = None if self.cur.type == T.RPAREN else self._expression()
        self._close_paren(lp)
        self._expect_semicolon()
        if expr is None:
            if fn.lexeme == "println":
                return ast.Newline(start.line, start.col)
            raise ParseError("'System.out.print' needs an argument", fn.line, fn.col)
        return ast.Print(start.line, start.col, expr, fn.lexeme == "println")

    def _for(self):
        kw = self._advance()
        lp = self._expect(T.LPAREN, "Expected '(' after 'for'")
        init = None
        if self.cur.type != T.SEMICOLON:
            init = self._declaration(False) if self._is_type_start() else self._assign_stmt(False)
        self._expect(T.SEMICOLON, "Expected ';' after the for-loop initializer")
        cond = None if self.cur.type == T.SEMICOLON else self._expression()
        self._expect(T.SEMICOLON, "Expected ';' after the for-loop condition")
        update = None if self.cur.type == T.RPAREN else self._assign_stmt(False)
        self._close_paren(lp)
        body = self._body("for")
        return ast.For(kw.line, kw.col, init, cond, update, body)

    def _return(self):
        kw = self._advance()
        expr = None
        if self.cur.type != T.SEMICOLON:
            expr = self._expression()
        self._expect_semicolon()
        return ast.Halt(kw.line, kw.col, expr)

    # -- expressions -------------------------------------------------------
    def _primary(self):
        self._skip_std()
        t = self.cur
        if (self.is_cpp and t.type == T.IDENTIFIER and t.lexeme == "to_string"
                and self._tok(1).type == T.LPAREN):
            self._advance()
            return self._to_string_call(t)
        if (not self.is_cpp and t.type == T.KEYWORD and t.lexeme == "String"
                and self._tok(1).type == T.DOT and self._tok(2).type == T.IDENTIFIER
                and self._tok(2).lexeme == "valueOf" and self._tok(3).type == T.LPAREN):
            self._advance(); self._advance(); self._advance()
            return self._to_string_call(t)
        return super()._primary()

    def _to_string_call(self, start):
        lp = self._advance()                  # '('
        expr = self._expression()
        self._close_paren(lp)
        return ast.ToString(start.line, start.col, expr)
