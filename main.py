#!/usr/bin/env python3
"""MiniLang entry point.

    python main.py                       -> open the GUI
    python main.py prog.ml               -> compile + run in the terminal
    python main.py Hello.java --bytecode -> language is detected from the extension
    python main.py prog.txt --lang cpp   -> or choose it explicitly
Languages: minilang (.ml), cpp (.cpp), java (.java)
"""
import argparse
import sys

from minilang.compiler import compile_source, run_bytecode, format_tokens
from minilang.ast_nodes import format_ast
from minilang.bytecode import format_bytecode
from minilang.languages import language_for_extension, LANGUAGES


def cli(args):
    with open(args.file, encoding="utf-8") as f:
        source = f.read()
    lang = args.lang or language_for_extension(args.file) or "minilang"
    res = compile_source(source, lang)
    if args.tokens:
        print("== TOKENS ==\n" + format_tokens(res.tokens) + "\n")
    if args.ast and res.ast:
        print("== SYNTAX TREE ==\n" + format_ast(res.ast) + "\n")
    if res.errors:
        print(f"{len(res.errors)} error(s) found in {args.file}:", file=sys.stderr)
        for e in res.errors:
            print("  " + str(e), file=sys.stderr)
        return 1
    if args.bytecode:
        print("== BYTECODE ==\n" + format_bytecode(res.bytecode) + "\n")
    if args.no_run:
        return 0
    _, err = run_bytecode(res.bytecode, on_output=print, style=res.style)
    if err:
        print(err, file=sys.stderr)
        return 2
    return 0


def main():
    p = argparse.ArgumentParser(description="MiniLang / C++ / Java compiler & virtual machine")
    p.add_argument("file", nargs="?", help="source file (omit for the GUI)")
    p.add_argument("--lang", choices=sorted(LANGUAGES), help="source language")
    p.add_argument("--tokens", action="store_true", help="print tokens")
    p.add_argument("--ast", action="store_true", help="print syntax tree")
    p.add_argument("--bytecode", action="store_true", help="print bytecode")
    p.add_argument("--no-run", action="store_true", help="compile only")
    args = p.parse_args()
    if args.file:
        sys.exit(cli(args))
    from minilang.gui import launch
    launch()


if __name__ == "__main__":
    main()
