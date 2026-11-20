import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from minilang.compiler import compile_source, run_bytecode
from minilang.lexer import Lexer
from minilang.bytecode import format_bytecode


def run(src, max_steps=1_000_000, lang="minilang"):
    res = compile_source(src, lang)
    assert res.ok, [str(e) for e in res.errors]
    out, err = run_bytecode(res.bytecode, max_steps=max_steps, style=res.style)
    assert err is None, str(err)
    return out


def errors(src, lang="minilang"):
    res = compile_source(src, lang)
    assert not res.ok, "expected a compile error"
    return [str(e) for e in res.errors], res


class LexerTests(unittest.TestCase):
    def test_spec_example(self):
        toks = Lexer("let x = 10 + 20;").tokenize()
        self.assertEqual([str(t) for t in toks[:-1]], [
            "KEYWORD(let)", "IDENTIFIER(x)", "ASSIGN(=)", "NUMBER(10)",
            "PLUS(+)", "NUMBER(20)", "SEMICOLON(;)"])

    def test_floats_strings_operators(self):
        toks = Lexer('3.14 "hi" == != <= >= < >').tokenize()
        self.assertEqual([t.type for t in toks[:-1]],
                         ["NUMBER", "STRING", "EQ", "NEQ", "LTE", "GTE", "LT", "GT"])

    def test_invalid_character(self):
        msgs, res = errors("let x = 5 @ 2;")
        self.assertIn("Lexical Error: Invalid character '@' at line 1, column 11.", msgs)
        self.assertIsNone(res.bytecode)

    def test_unterminated_string(self):
        msgs, _ = errors('print("abc);')
        self.assertTrue(msgs[0].startswith("Lexical Error: Unterminated string"))

    def test_line_numbers(self):
        msgs, _ = errors("let x = 1;\nlet y = 2;\n#")
        self.assertIn("line 3", msgs[0])


class ParserTests(unittest.TestCase):
    def test_missing_semicolon(self):
        msgs, res = errors("let a = 1;\nlet b = 2\nprint(b);")
        self.assertEqual(msgs[0], "Syntax Error: Missing semicolon at line 2, column 10.")
        self.assertIsNone(res.bytecode)

    def test_unmatched_paren(self):
        msgs, _ = errors("print((1 + 2);")
        self.assertTrue(msgs[0].startswith("Syntax Error: Expected ')'"))

    def test_unclosed_block(self):
        msgs, _ = errors("while (true) { print(1);")
        self.assertIn("Expected '}'", msgs[0])

    def test_invalid_statement(self):
        msgs, _ = errors("10 + 5;")
        self.assertIn("Invalid statement", msgs[0])

    def test_missing_expression(self):
        msgs, _ = errors("let x = ;")
        self.assertIn("Expected an expression", msgs[0])

    def test_else_without_if(self):
        msgs, _ = errors("else { }")
        self.assertIn("'else' without", msgs[0])

    def test_ast_generated(self):
        res = compile_source("let x = 1 + 2 * 3;")
        self.assertEqual(res.ast.statements[0].init.op, "+")
        self.assertEqual(res.ast.statements[0].init.right.op, "*")


class SemanticTests(unittest.TestCase):
    def test_undeclared(self):
        msgs, _ = errors("let x = 10;\nlet y = z + 5;")
        self.assertEqual(msgs, ["Semantic Error: Variable 'z' is not declared at line 2, column 9."])

    def test_undeclared_assignment(self):
        msgs, _ = errors("total = 5;")
        self.assertIn("Variable 'total' is not declared", msgs[0])

    def test_self_reference_in_initializer(self):
        msgs, _ = errors("let x = x + 1;")
        self.assertIn("Variable 'x' is not declared", msgs[0])

    def test_duplicate(self):
        msgs, _ = errors("let x = 1;\nlet x = 2;")
        self.assertIn("already declared", msgs[0])

    def test_type_mismatch_assign(self):
        msgs, _ = errors('let x = 10;\nx = "a";')
        self.assertIn("Type mismatch", msgs[0])

    def test_invalid_operation(self):
        msgs, _ = errors('print("a" - 1);')
        self.assertIn("cannot apply '-' to 'string' and 'number'", msgs[0])
        msgs, _ = errors('print(1 + "a");')
        self.assertIn("cannot apply '+'", msgs[0])

    def test_condition_must_be_bool(self):
        msgs, _ = errors("if (1) { print(1); }")
        self.assertIn("must be a boolean", msgs[0])

    def test_multiple_errors_reported(self):
        msgs, _ = errors("print(a);\nprint(b);")
        self.assertEqual(len(msgs), 2)

    def test_shadowing_allowed(self):
        self.assertEqual(run("let x = 1; { let x = 2; print(x); } print(x);"), ["2", "1"])


class BytecodeTests(unittest.TestCase):
    def test_spec_example(self):
        res = compile_source("let x = 10;\nlet y = 20;\nlet sum = x + y;\nprint(sum);")
        self.assertEqual(
            [str(i) for i in res.bytecode],
            ["PUSH 10", "STORE x", "PUSH 20", "STORE y", "LOAD x", "LOAD y",
             "ADD", "STORE sum", "LOAD sum", "PRINT", "HALT"])

    def test_loop_jumps(self):
        res = compile_source("let i = 0; while (i < 2) { i = i + 1; }")
        text = format_bytecode(res.bytecode)
        self.assertIn("JMP_IF_FALSE", text)
        self.assertIn("JMP 2", text)


class ExecutionTests(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(run("print(10 + 20 * 2);"), ["50"])
        self.assertEqual(run("print((10 + 20) * 2);"), ["60"])
        self.assertEqual(run("print(20 / 4);"), ["5"])
        self.assertEqual(run("print(7 / 2);"), ["3.5"])
        self.assertEqual(run("print(1.5 + 2.5);"), ["4"])
        self.assertEqual(run("print(-3 + 5);"), ["2"])
        self.assertEqual(run("print(10 - 3 - 2);"), ["5"])      # left associative

    def test_variables_and_assignment(self):
        self.assertEqual(run("let a = 1; let b = 2; a = a + b; print(a); print(b);"),
                         ["3", "2"])

    def test_strings(self):
        self.assertEqual(run('let n = "Ali"; print("Hi " + n);'), ["Hi Ali"])
        self.assertEqual(run(r'print("a\tb");'), ["a\tb"])

    def test_if_else(self):
        src = 'let age = %d; if (age >= 18) { print("Adult"); } else { print("Minor"); }'
        self.assertEqual(run(src % 20), ["Adult"])
        self.assertEqual(run(src % 10), ["Minor"])

    def test_else_if_chain(self):
        src = ("let s = %d; if (s >= 90) { print(\"A\"); } "
               "else if (s >= 70) { print(\"B\"); } else { print(\"C\"); }")
        self.assertEqual([run(src % n)[0] for n in (95, 75, 10)], ["A", "B", "C"])

    def test_while(self):
        self.assertEqual(run("let i = 0; while (i < 5) { print(i); i = i + 1; }"),
                         ["0", "1", "2", "3", "4"])

    def test_nested_loops(self):
        src = ("let i = 1; while (i <= 2) { let j = 1; while (j <= 2) "
               "{ print(i * j); j = j + 1; } i = i + 1; }")
        self.assertEqual(run(src), ["1", "2", "2", "4"])

    def test_booleans(self):
        self.assertEqual(run('let v = true; if (v == true) { print("Valid"); }'), ["Valid"])
        self.assertEqual(run("print(1 < 2); print(2 == 3); print(2 != 3);"),
                         ["true", "false", "true"])

    def test_all_comparisons(self):
        out = run("print(3 > 2); print(3 < 2); print(3 >= 3); print(3 <= 2);")
        self.assertEqual(out, ["true", "false", "true", "false"])

    def test_factorial(self):
        self.assertEqual(run("let r = 1; let i = 1; while (i <= 10) { r = r * i; i = i + 1; } print(r);"),
                         ["3628800"])

    def test_division_by_zero(self):
        res = compile_source("let a = 10;\nlet b = 0;\nprint(a / b);")
        out, err = run_bytecode(res.bytecode)
        self.assertEqual(str(err), "Runtime Error: Division by zero at line 3.")

    def test_infinite_loop_guard(self):
        res = compile_source("while (true) { }")
        _, err = run_bytecode(res.bytecode, max_steps=1000)
        self.assertIn("step limit", str(err))




class MultiErrorTests(unittest.TestCase):
    """The compiler must analyse everything first and report ALL errors at once."""

    SRC = ("let a = 10;\nlet b = a @ 2;\nlet c = 5\nprint(d);\nif (a > 1 {\n"
           "    print(a);\n}\nlet e = ;\nx = \"s\" - 1;\n")

    def test_all_error_kinds_reported_together(self):
        msgs, res = errors(self.SRC)
        kinds = {m.split(" Error")[0] for m in msgs}
        self.assertEqual(kinds, {"Lexical", "Syntax", "Semantic"})
        self.assertGreaterEqual(len(msgs), 6)
        self.assertIsNone(res.bytecode)

    def test_errors_sorted_by_position(self):
        _, res = errors(self.SRC)
        pos = [(e.line, e.col) for e in res.errors]
        self.assertEqual(pos, sorted(pos))

    def test_each_stage_has_its_own_list(self):
        _, res = errors(self.SRC)
        self.assertTrue(res.stage_errors["lexer"])
        self.assertTrue(res.stage_errors["parser"])
        self.assertTrue(res.stage_errors["semantic"])

    def test_several_syntax_errors_in_one_pass(self):
        msgs, _ = errors("let a = 1\nlet b = 2\nlet c = ;\nprint(a);")
        self.assertEqual(len(msgs), 3)

    def test_no_cascade_after_bad_declaration(self):
        # 'y' is declared (even though its initializer is broken) -> no 'undeclared y'
        msgs, _ = errors("let y = ;\nprint(y);")
        self.assertEqual(len(msgs), 1)

    def test_lexical_error_does_not_cascade(self):
        msgs, _ = errors("let y = 5 @ 2;\nprint(y);")
        self.assertEqual(len(msgs), 1)

    def test_stray_else_and_brace(self):
        msgs, _ = errors("else { print(1); }\nprint(2);\n}")
        self.assertEqual(len(msgs), 2)

    def test_parser_always_terminates(self):
        for junk in ["}}}", "((((", "let", "let x", "if", "while (", "{", ";;;", "print(", "@@@",
                     "if x:", "if x:\n  ", "for", "for i in", "    x", "a, b", "f'{", "x = [", "else:",
                     "if 1:\n    x\n  y"]:
            compile_source(junk)                      # must not hang or crash
            compile_source(junk, "cpp")
            compile_source(junk, "java")
            compile_source(junk, "python")


class StepTraceTests(unittest.TestCase):
    def test_trace_keeps_every_step(self):
        from minilang.vm import VirtualMachine
        res = compile_source("let x = 5;\nlet y = x + 2;\nprint(y);")
        vm = VirtualMachine(res.bytecode)
        seen = []
        while vm.step():
            seen.append(len(vm.history))
        self.assertEqual([h.step for h in vm.history], list(range(1, len(vm.history) + 1)))
        self.assertEqual(seen, sorted(seen))                  # history only grows
        self.assertEqual(vm.history[0].text, "PUSH 5")
        self.assertEqual(vm.history[0].stack, "[5]")
        self.assertEqual(vm.history[1].stack, "[]")           # STORE popped it...
        self.assertEqual(vm.memory["x"], 5)                   # ...into memory
        self.assertEqual(vm.output, ["7"])

    def test_halted_vm_does_not_restart(self):
        from minilang.vm import VirtualMachine
        res = compile_source("print(1);")
        vm = VirtualMachine(res.bytecode)
        vm.run()
        self.assertFalse(vm.step())
        self.assertEqual(vm.output, ["1"])


class CppTests(unittest.TestCase):
    def cpp(self, body, head="#include <iostream>\nusing namespace std;\n"):
        return run(head + "int main() {\n" + body + "\nreturn 0;\n}", lang="cpp")

    def test_hello_and_endl(self):
        self.assertEqual(self.cpp('cout << "Hello" << endl;'), ["Hello"])

    def test_chain_without_endl_flushes(self):
        self.assertEqual(self.cpp('cout << 1 << " " << 2;'), ["1 2"])

    def test_integer_division_and_modulo(self):
        self.assertEqual(self.cpp("cout << 7 / 2 << endl; cout << 7 % 2 << endl; "
                                  "cout << 7.0 / 2 << endl; cout << -7 / 2 << endl;"),
                         ["3", "1", "3.5", "-3"])

    def test_for_loop_break_continue(self):
        src = ("for (int i = 1; i <= 10; i++) { if (i % 2 == 0) continue; if (i > 7) break; "
               "cout << i << endl; }")
        self.assertEqual(self.cpp(src), ["1", "3", "5", "7"])

    def test_while_and_compound_ops(self):
        self.assertEqual(self.cpp("int n = 1; while (n < 100) { n *= 3; } cout << n << endl;"),
                         ["243"])

    def test_declarations_and_defaults(self):
        self.assertEqual(self.cpp("int a = 1, b = 2, c; cout << a + b + c << endl;"), ["3"])

    def test_strings_and_to_string(self):
        self.assertEqual(self.cpp('string s = "n=" + to_string(5 * 2); cout << s << endl;'),
                         ["n=10"])

    def test_double_to_int_truncates(self):
        self.assertEqual(self.cpp("int x = 3.99; double d = 4; cout << x << endl; cout << d << endl;"),
                         ["3", "4"])

    def test_std_prefix(self):
        self.assertEqual(self.cpp('std::string s = "a"; std::cout << s << std::endl;', head=""),
                         ["a"])

    def test_logic_and_short_circuit(self):
        self.assertEqual(self.cpp("int b = 0; if (b != 0 && 10 / b > 1) { cout << 1; } "
                                  "else { cout << 2; } cout << endl;"), ["2"])

    def test_bool_prints_as_number(self):
        self.assertEqual(self.cpp("bool t = true; cout << t << endl;"), ["1"])

    def test_without_main_wrapper(self):
        self.assertEqual(run("int x = 5; cout << x << endl;", lang="cpp"), ["5"])

    def test_errors(self):
        msgs, _ = errors("int main() { string s = 5; int x = \"a\"; cout << y; return 0; }", "cpp")
        self.assertEqual(len(msgs), 3)
        self.assertIn("cannot assign 'int' to variable 's' of type 'string'", msgs[0])
        msgs, _ = errors("int main() { cout << 1 return 0; }", "cpp")
        self.assertIn("Syntax Error", msgs[0])
        msgs, _ = errors("int main() { break; }", "cpp")
        self.assertIn("outside of a loop", msgs[0])


class JavaTests(unittest.TestCase):
    def java(self, body):
        return run("public class Main {\n public static void main(String[] args) {\n"
                   + body + "\n }\n}", lang="java")

    def test_println_and_print(self):
        self.assertEqual(self.java('System.out.print("a"); System.out.print("b"); '
                                   'System.out.println("c"); System.out.println();'),
                         ["abc", ""])

    def test_string_concatenation_with_numbers(self):
        self.assertEqual(self.java('int y = 2026; System.out.println("Year " + y + 1); '
                                   'System.out.println("Sum " + (y + 1));'),
                         ["Year 20261", "Sum 2027"])

    def test_double_formatting(self):
        self.assertEqual(self.java("double d = 5; System.out.println(d); "
                                   "System.out.println(7 / 2.0); System.out.println(7 / 2);"),
                         ["5.0", "3.5", "3"])

    def test_boolean_and_loops(self):
        src = ("boolean ok = true; int s = 0; for (int i = 0; i < 5; i++) { s += i; } "
               "if (ok && s == 10) { System.out.println(\"ten\"); }")
        self.assertEqual(self.java(src), ["ten"])

    def test_fizzbuzz(self):
        src = ("for (int i = 1; i <= 5; i++) { if (i % 3 == 0) System.out.println(\"Fizz\"); "
               "else System.out.println(i); }")
        self.assertEqual(self.java(src), ["1", "2", "Fizz", "4", "5"])

    def test_string_valueof_and_var(self):
        self.assertEqual(self.java("var n = 5; String s = String.valueOf(n * 2); "
                                   "System.out.println(s);"), ["10"])

    def test_lossy_conversion_is_an_error(self):
        msgs, _ = errors("public class A { public static void main(String[] a) "
                         "{ int x = 3.5; } }", "java")
        self.assertIn("possible lossy conversion from double to int", msgs[0])

    def test_unsupported_member_reported(self):
        msgs, _ = errors("public class A { static int f(int x) { return x; } "
                         "public static void main(String[] a) { int y = 1; } }", "java")
        self.assertEqual(len(msgs), 1)
        self.assertIn("Only the 'main' method", msgs[0])

    def test_multiple_errors_at_once(self):
        src = ("public class A { public static void main(String[] a) {\n"
               "int x = 1\nint y = z;\nString s = 5;\n} }")
        msgs, _ = errors(src, "java")
        self.assertEqual(len(msgs), 3)


class PythonTests(unittest.TestCase):
    def py(self, src):
        return run(src, lang="python")

    def test_tokens_have_newline_indent_dedent(self):
        from minilang.pylexer import PythonLexer
        toks = PythonLexer("if x:\n    y = 1\nz = 2\n").tokenize()
        kinds = [t.type for t in toks]
        for k in ("NEWLINE", "INDENT", "DEDENT", "COLON", "KEYWORD", "EOF"):
            self.assertIn(k, kinds)
        self.assertEqual(kinds.count("INDENT"), kinds.count("DEDENT"))

    def test_print_and_strings(self):
        self.assertEqual(self.py('print("Hello")\nprint("a" + "b", "ab" * 3)'), ["Hello", "ab ababab"])

    def test_print_sep_end(self):
        self.assertEqual(self.py('print("a", "b", sep="-", end="!")\nprint()\nprint("x", end="")\nprint("y")'),
                         ["a-b!", "xy"])

    def test_division_family(self):
        self.assertEqual(self.py("print(7 / 2, 4 / 2, 7 // 2, -7 // 2, 7 % 3, -7 % 3, 2 ** 10, 2 ** -1)"),
                         ["3.5 2.0 3 -4 1 2 1024 0.5"])

    def test_power_precedence(self):
        self.assertEqual(self.py("print(-2 ** 2, 2 ** 3 ** 2)"), ["-4 512"])

    def test_booleans_print_like_python(self):
        self.assertEqual(self.py("print(True, False, not True, 1 < 2 < 3, 3 < 2 < 1)"),
                         ["True False False True False"])

    def test_and_or_return_values(self):
        self.assertEqual(self.py('print(0 or "d", 5 and 0, "" or 7, 3 and 4)'), ["d 0 7 4"])

    def test_if_elif_else(self):
        src = ("s = %d\nif s >= 90:\n    g = 'A'\nelif s >= 70:\n    g = 'B'\nelse:\n    g = 'C'\nprint(g)")
        self.assertEqual([self.py(src % n)[0] for n in (95, 75, 10)], ["A", "B", "C"])

    def test_one_line_suite(self):
        self.assertEqual(self.py("x = 3\nif x > 1: print('big')\nelse: print('small')"), ["big"])

    def test_while_break_continue(self):
        src = "x = 3\nwhile True:\n    x -= 1\n    if x == 1:\n        continue\n    if x < 0:\n        break\n    print(x)"
        self.assertEqual(self.py(src), ["2", "0"])

    def test_for_range_forms(self):
        self.assertEqual(self.py("for i in range(3):\n    print(i)"), ["0", "1", "2"])
        self.assertEqual(self.py("for i in range(2, 5):\n    print(i)"), ["2", "3", "4"])
        self.assertEqual(self.py("for i in range(10, 0, -4):\n    print(i)"), ["10", "6", "2"])
        self.assertEqual(self.py("s = 2\nfor i in range(0, 7, s):\n    print(i)"), ["0", "2", "4", "6"])
        self.assertEqual(self.py("for i in range(0):\n    print(i)\nprint('done')"), ["done"])

    def test_loop_variable_survives_and_body_cannot_break_counter(self):
        self.assertEqual(self.py("for i in range(3):\n    i = 10\nprint(i)"), ["10"])
        self.assertEqual(self.py("n = 0\nfor i in range(3):\n    n += 1\nprint(n, i)"), ["3 2"])

    def test_nested_loops(self):
        src = "for i in range(1, 3):\n    for j in range(1, 3):\n        print(i * j)"
        self.assertEqual(self.py(src), ["1", "2", "2", "4"])

    def test_tuple_swap_and_chained_assignment(self):
        self.assertEqual(self.py("a, b = 1, 2\na, b = b, a\nprint(a, b)"), ["2 1"])
        self.assertEqual(self.py("a = b = 4\nprint(a + b)"), ["8"])

    def test_augmented_assignment(self):
        self.assertEqual(self.py("x = 2\nx += 3\nx *= 2\nx -= 1\nx //= 3\nx **= 2\nprint(x)"), ["9"])

    def test_dynamic_typing_allows_rebinding(self):
        self.assertEqual(self.py('x = 5\nx = "now a string"\nprint(x)'), ["now a string"])

    def test_fstrings(self):
        self.assertEqual(self.py('x = 5\nprint(f"x = {x}, double = {x * 2}")'), ["x = 5, double = 10"])
        self.assertEqual(self.py('print(f"{3.14159:.2f}|{42:5d}|{{literal}}")'), ["3.14|   42|{literal}"])
        self.assertEqual(self.py('n = "Ali"\nprint(f"Hi {n}!")'), ["Hi Ali!"])

    def test_builtins(self):
        self.assertEqual(self.py('print(len("abc"), int("5") + 1, float("2.5"), abs(-3), min(2, 1), '
                                 'max(2, 5), round(2.5), round(3.5), str(3) + "x")'),
                         ["3 6 2.5 3 1 5 2 4 3x"])

    def test_string_comparison(self):
        self.assertEqual(self.py('print("a" < "b", "x" == "x", "x" != "y")'), ["True True True"])

    def test_float_repr_like_python(self):
        self.assertEqual(self.py("print(0.1 + 0.2, 1e3, 2.50)"), ["0.30000000000000004 1000.0 2.5"])

    def test_triple_quote_and_comments(self):
        self.assertEqual(self.py('# comment\nx = """a\nb"""  # trailing\nprint(x)'), ["a", "b"])

    def test_implicit_line_joining(self):
        self.assertEqual(self.py("x = (1 +\n     2 +\n     3)\nprint(x)"), ["6"])

    def test_pass_and_blank_lines(self):
        self.assertEqual(self.py("x = 1\n\nif x:\n    pass\n\nprint('ok')"), ["ok"])

    # ---- compile-time errors (all reported together) ----
    def test_undefined_name(self):
        msgs, _ = errors("print(y)", "python")
        self.assertEqual(msgs, ["Semantic Error: name 'y' is not defined at line 1, column 7."])

    def test_missing_colon(self):
        msgs, _ = errors("x = 1\nif x > 0\n    print(x)", "python")
        self.assertEqual(len(msgs), 1)
        self.assertIn("Expected ':'", msgs[0])

    def test_indentation_errors(self):
        msgs, _ = errors("x = 1\n  y = 2", "python")
        self.assertIn("Unexpected indent", msgs[0])
        msgs, _ = errors("if True:\nprint(1)", "python")
        self.assertIn("Expected an indented block", msgs[0])
        msgs, _ = errors("if True:\n        x = 1\n    y = 2", "python")
        self.assertIn("Unindent does not match", msgs[0])

    def test_unclosed_bracket(self):
        msgs, _ = errors("x = (1 +\n", "python")
        self.assertEqual(len(msgs), 1)
        self.assertIn("was never closed", msgs[0])

    def test_unsupported_features_have_clear_messages(self):
        for src, word in (("def f():\n    pass", "'def'"), ("x = [1]", "Lists"),
                          ("x = None", "'None'"), ("import os", "'import'"),
                          ("for c in 'ab':\n    pass", "range")):
            msgs, _ = errors(src, "python")
            self.assertIn(word, msgs[0], src)

    def test_many_errors_in_one_pass(self):
        src = "total = 10\nif total > 5\n    print(total)\nprint(missing)\ncount = (1 +\n"
        msgs, res = errors(src, "python")
        self.assertEqual({m.split(" Error")[0] for m in msgs}, {"Lexical", "Syntax", "Semantic"})
        self.assertIsNone(res.bytecode)

    def test_break_outside_loop(self):
        msgs, _ = errors("break", "python")
        self.assertIn("outside of a loop", msgs[0])

    def test_wrong_argument_count(self):
        msgs, _ = errors("print(len(1, 2))", "python")
        self.assertIn("takes exactly 1 argument", msgs[0])

    # ---- runtime errors (Python reports type problems at run time) ----
    def test_runtime_errors(self):
        for src, text in (("print(10 / 0)", "Division by zero"), ("print(5 // 0)", "Division by zero"),
                          ("print(5 % 0)", "Division by zero"), ('print("a" - 1)', "SUB requires numeric"),
                          ('print("a" + 1)', "incompatible types"), ('print(int("abc"))', "Cannot convert"),
                          ("print(len(5))", "len()")):
            res = compile_source(src, "python")
            self.assertTrue(res.ok, src)
            _, err = run_bytecode(res.bytecode, style="python")
            self.assertIn(text, str(err), src)

    def test_step_trace_for_python(self):
        from minilang.vm import VirtualMachine
        res = compile_source("x = 1\nprint(x)", "python")
        vm = VirtualMachine(res.bytecode, style="python")
        vm.run()
        self.assertEqual([h.text for h in vm.history][:2], ["PUSH 1", "STORE x"])
        self.assertEqual(vm.output, ["1"])


class ExamplesTests(unittest.TestCase):
    def test_every_example_behaves(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
        from minilang.languages import LANGUAGES
        count = 0
        for spec in LANGUAGES.values():
            folder = os.path.join(root, spec.examples_dir)
            for name in sorted(os.listdir(folder)):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    res = compile_source(f.read(), spec.key)
                runtime_demo = "error_runtime" in name.lower()
                bad = name.lower().startswith("error") and not runtime_demo
                self.assertEqual(res.ok, not bad, f"{spec.key}/{name}: {[str(e) for e in res.errors]}")
                if res.ok:
                    out, err = run_bytecode(res.bytecode, style=res.style)
                    if runtime_demo:
                        self.assertIn("Division by zero", str(err))
                    else:
                        self.assertIsNone(err, f"{spec.key}/{name}: {err}")
                count += 1
        self.assertGreaterEqual(count, 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
