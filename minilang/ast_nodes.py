"""Abstract Syntax Tree node classes + tree printer (shared by all languages)."""
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class Node:
    line: int = 0
    col: int = 0


# ---- expressions ----------------------------------------------------------
@dataclass
class Number(Node):
    value: Any = 0
    etype: Optional[str] = None


@dataclass
class String(Node):
    value: str = ""
    etype: Optional[str] = None


@dataclass
class Boolean(Node):
    value: bool = False
    etype: Optional[str] = None


@dataclass
class Variable(Node):
    name: str = ""
    resolved: Optional[str] = None     # unique VM memory name (set by semantic pass)
    etype: Optional[str] = None


@dataclass
class UnaryOp(Node):
    op: str = "-"                      # "-" or "!"
    operand: Node = None
    etype: Optional[str] = None


@dataclass
class BinaryOp(Node):
    op: str = "+"
    left: Node = None
    right: Node = None
    etype: Optional[str] = None
    concat: bool = False               # Java / f-strings: string + anything
    idiv: bool = False                 # C++/Java: int / int
    py: bool = False                   # Python semantics (true division, value-keeping and/or ...)


@dataclass
class ToString(Node):                  # to_string(x), String.valueOf(x)
    expr: Node = None
    etype: Optional[str] = None


@dataclass
class Call(Node):                      # Python built-ins: int(), float(), len(), abs(), min() ...
    name: str = ""
    args: List[Node] = field(default_factory=list)
    etype: Optional[str] = None


@dataclass
class FormatExpr(Node):                # f"{x:.2f}"
    expr: Node = None
    spec: str = ""
    etype: Optional[str] = None


@dataclass
class ErrorExpr(Node):                 # placeholder left by error recovery
    etype: Optional[str] = None


# ---- statements -----------------------------------------------------------
@dataclass
class VarDecl(Node):
    name: str = ""
    init: Optional[Node] = None
    decl_type: Optional[str] = None    # None for MiniLang 'let'; int/float/string/bool/auto
    resolved: Optional[str] = None
    convert: Optional[str] = None      # "toint" / "tofloat"


@dataclass
class Assign(Node):
    name: str = ""
    value: Node = None
    resolved: Optional[str] = None
    convert: Optional[str] = None


@dataclass
class ExprStmt(Node):                  # an expression used as a statement (value is discarded)
    expr: Node = None


@dataclass
class Print(Node):
    expr: Node = None
    newline: bool = True


@dataclass
class Newline(Node):
    pass


@dataclass
class Block(Node):                     # scoped
    statements: List[Node] = field(default_factory=list)


@dataclass
class Sequence(Node):                  # NOT scoped (e.g. "int a = 1, b = 2;")
    statements: List[Node] = field(default_factory=list)


@dataclass
class If(Node):
    cond: Node = None
    then_block: Block = None
    else_block: Optional[Block] = None


@dataclass
class While(Node):
    cond: Node = None
    body: Block = None


@dataclass
class For(Node):
    init: Optional[Node] = None
    cond: Optional[Node] = None
    update: Optional[Node] = None
    body: Block = None


@dataclass
class Break(Node):
    pass


@dataclass
class Continue(Node):
    pass


@dataclass
class Halt(Node):                      # 'return' from main
    expr: Optional[Node] = None


@dataclass
class Program(Node):
    statements: List[Node] = field(default_factory=list)


# ---- pretty printer ---------------------------------------------------------
def _describe(node):
    """Return (label, [(edge_label, child), ...])."""
    if isinstance(node, Program):
        return "Program", [("", s) for s in node.statements]
    if isinstance(node, (Block, Sequence)):
        return type(node).__name__, [("", s) for s in node.statements]
    if isinstance(node, VarDecl):
        label = f"VarDecl({node.decl_type + ' ' if node.decl_type else ''}{node.name})"
        return label, ([("init", node.init)] if node.init is not None else [])
    if isinstance(node, Assign):
        return f"Assign({node.name})", [("value", node.value)]
    if isinstance(node, Print):
        return ("Print" if node.newline else "Write"), [("expr", node.expr)]
    if isinstance(node, Newline):
        return "Newline", []
    if isinstance(node, If):
        kids = [("cond", node.cond), ("then", node.then_block)]
        if node.else_block:
            kids.append(("else", node.else_block))
        return "If", kids
    if isinstance(node, While):
        return "While", [("cond", node.cond), ("body", node.body)]
    if isinstance(node, For):
        kids = []
        if node.init is not None:
            kids.append(("init", node.init))
        if node.cond is not None:
            kids.append(("cond", node.cond))
        if node.update is not None:
            kids.append(("update", node.update))
        kids.append(("body", node.body))
        return "For", kids
    if isinstance(node, Break):
        return "Break", []
    if isinstance(node, Continue):
        return "Continue", []
    if isinstance(node, Halt):
        return "Return", ([("expr", node.expr)] if node.expr is not None else [])
    if isinstance(node, BinaryOp):
        return f"BinaryOp({node.op})", [("left", node.left), ("right", node.right)]
    if isinstance(node, UnaryOp):
        return f"UnaryOp({node.op})", [("operand", node.operand)]
    if isinstance(node, ToString):
        return "ToString", [("expr", node.expr)]
    if isinstance(node, Call):
        return f"Call({node.name})", [("arg", a) for a in node.args]
    if isinstance(node, FormatExpr):
        return f"Format({node.spec})", [("expr", node.expr)]
    if isinstance(node, ExprStmt):
        return "ExprStmt", [("expr", node.expr)]
    if isinstance(node, Number):
        return f"Number({node.value})", []
    if isinstance(node, String):
        return f'String("{node.value}")', []
    if isinstance(node, Boolean):
        return f"Boolean({'true' if node.value else 'false'})", []
    if isinstance(node, Variable):
        return f"Variable({node.name})", []
    if isinstance(node, ErrorExpr):
        return "<error>", []
    return type(node).__name__, []


def format_ast(node):
    lines = []

    def walk(n, prefix, edge, is_last, is_root):
        label, kids = _describe(n)
        text = f"{edge}: {label}" if edge else label
        if is_root:
            lines.append(text)
            child_prefix = ""
        else:
            lines.append(prefix + ("└── " if is_last else "├── ") + text)
            child_prefix = prefix + ("    " if is_last else "│   ")
        for i, (e, c) in enumerate(kids):
            walk(c, child_prefix, e, i == len(kids) - 1, False)

    walk(node, "", "", True, True)
    return "\n".join(lines)
