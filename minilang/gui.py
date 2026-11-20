"""Tkinter front end - baby pink / burgundy / beige theme with animated effects.

Editor with syntax highlighting and a language selector, Compile / Execute /
Step / Clear, stage tabs (Source, Tokens, Syntax Tree, Bytecode, Execution
Output, Errors), an animated pipeline bar, toast messages, and a VM inspector
with a persistent step-by-step execution trace.
"""
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox

from .compiler import compile_source, format_tokens
from .ast_nodes import format_ast
from .bytecode import format_bytecode
from .vm import VirtualMachine, format_value
from .errors import MiniLangError
from . import __version__
from .languages import LANGUAGES, ORDER, language_for_extension
from .widgets import *            # palette + RoundButton, StageChip, GradientHeader ...

EXAMPLES_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "examples")
STAGES = ["Lexer", "Parser", "Semantic", "Bytecode", "VM"]

TYPE_WORDS = {"int", "long", "short", "double", "float", "bool", "boolean", "string",
              "String", "char", "auto", "var", "void"}

OP_COLORS = {
    "PUSH": ROSE, "POP": ROSE, "LOAD": ROSE, "STORE": ROSE,
    "ADD": BURGUNDY, "SUB": BURGUNDY, "MUL": BURGUNDY, "DIV": BURGUNDY, "IDIV": BURGUNDY,
    "MOD": BURGUNDY, "NEG": BURGUNDY, "NOT": BURGUNDY, "CONCAT": BURGUNDY,
    "TOSTR": BURGUNDY, "TOINT": BURGUNDY, "TOFLOAT": BURGUNDY,
    "EQ": ORANGE_TXT, "NEQ": ORANGE_TXT, "GT": ORANGE_TXT, "LT": ORANGE_TXT,
    "GTE": ORANGE_TXT, "LTE": ORANGE_TXT,
    "JMP": LAV_TXT, "JMP_IF_FALSE": LAV_TXT,
    "PRINT": SAGE_DARK, "WRITE": SAGE_DARK, "NEWLINE": SAGE_DARK, "HALT": MUTED,
    "FDIV": BURGUNDY, "FLOORDIV": BURGUNDY, "PYMOD": BURGUNDY, "POW": BURGUNDY,
    "LEN": BURGUNDY, "ABS": BURGUNDY, "MIN": BURGUNDY, "MAX": BURGUNDY, "ROUND": BURGUNDY,
    "FORMAT": SAGE_DARK, "DUP": ROSE, "JMP_IF_TRUE": LAV_TXT,
}
TOKEN_COLORS = {"KEYWORD": (BURGUNDY, True), "IDENTIFIER": (LAV_TXT, False),
                "NUMBER": (ORANGE_TXT, False), "STRING": (SAGE_DARK, False),
                "FSTRING": (SAGE_DARK, False), "EOF": (MUTED, False)}
PUNCT = {"LPAREN", "RPAREN", "LBRACE", "RBRACE", "LBRACKET", "RBRACKET", "SEMICOLON",
         "COMMA", "DOT", "SCOPE", "COLON", "NEWLINE", "INDENT", "DEDENT"}


def _highlight_patterns(spec):
    types = sorted(spec.keywords & TYPE_WORDS)
    words = sorted(spec.keywords - TYPE_WORDS)
    pats = []
    if types:
        pats.append(("type", re.compile(r"\b(?:" + "|".join(types) + r")\b")))
    if spec.builtins:
        pats.append(("builtin", re.compile(r"\b(?:" + "|".join(spec.builtins) + r")\b")))
    pats.append(("keyword", re.compile(r"\b(?:" + "|".join(words) + r")\b")))
    pats.append(("number", re.compile(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b")))
    if spec.key == "python":
        pats.append(("string", re.compile(
            r"""(?i:[frb]{1,2})?(?:\"\"\"[\s\S]*?\"\"\"|\'\'\'[\s\S]*?\'\'\'"""
            r"""|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')""")))
        pats.append(("comment", re.compile(r"#[^\n]*")))
        return pats
    str_rx = r'"(?:\\.|[^"\\\n])*"' + (r"|'(?:\\.|[^'\\\n])*'" if spec.char_literals else "")
    pats.append(("string", re.compile(str_rx)))
    pats.append(("comment", re.compile(r"//[^\n]*|/\*.*?\*/", re.S)))
    if spec.preprocessor:
        pats.append(("comment", re.compile(r"^[ \t]*#[^\n]*", re.M)))
    return pats


class MiniLangApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"MiniLang Compiler & Virtual Machine  -  v{__version__}")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.compact = sh < 820                      # laptop screens: tighter layout
        w, h = min(1360, sw - 20), min(880, sh - 90)
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 25)}")
        self.minsize(min(1180, w), min(600, h))
        if sys.platform == "win32":
            try:
                self.state("zoomed")                 # use the whole work area (above the taskbar)
            except tk.TclError:
                pass
        self.configure(bg=BG)

        self.spec = LANGUAGES["minilang"]
        self.result = None
        self.vm = None
        self.tabs = {}
        self._loaded_text = self.spec.sample
        self._patterns = _highlight_patterns(self.spec)
        self._chip_jobs = []
        self._var_names = []
        self._prev_mem = {}
        self._fresh_job = None
        self._status_job = None

        self._init_fonts()
        self._init_style()
        self._build_menu()
        self._build_header()
        self._build_toolbar()
        self._build_pipeline()
        self._build_status()
        self._build_tabs()
        self._bind_keys()
        self.toast = Toast(self, self.f_bold)

        self._set_editor(self.spec.sample)
        self._fade_in()
        self.after(500, self._ensure_on_screen)

    def _ensure_on_screen(self):
        """If the window is taller than the visible screen, shrink it so the bottom
        panels (Variables & Values, status bar) are never hidden behind the taskbar."""
        try:
            if self.state() == "zoomed":
                return
            bottom = self.winfo_rooty() + self.winfo_height()
            limit = self.winfo_screenheight() - 48
            if bottom > limit:
                h = max(560, self.winfo_height() - (bottom - limit))
                self.geometry(f"{self.winfo_width()}x{h}+{max(0, self.winfo_x())}+{max(0, self.winfo_y())}")
        except tk.TclError:
            pass

    # ------------------------------------------------------- fonts & style
    def _pick(self, candidates, default):
        available = set(tkfont.families(self))
        return next((c for c in candidates if c in available), default)

    def _init_fonts(self):
        ui = self._pick(["Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu", "Cantarell",
                         "DejaVu Sans", "Arial"], "TkDefaultFont")
        mono = self._pick(["Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono",
                           "Liberation Mono", "Courier New"], "TkFixedFont")
        self.f_ui = tkfont.Font(family=ui, size=10)
        self.f_bold = tkfont.Font(family=ui, size=10, weight="bold")
        self.f_title = tkfont.Font(family=ui, size=18 if self.compact else 22, weight="bold")
        self.f_sub = tkfont.Font(family=ui, size=11)
        self.f_small = tkfont.Font(family=ui, size=9)
        self.f_small_b = tkfont.Font(family=ui, size=9, weight="bold")
        self.f_mono = tkfont.Font(family=mono, size=11)
        self.f_mono_s = tkfont.Font(family=mono, size=10)
        self.f_mono_bold = tkfont.Font(family=mono, size=11, weight="bold")
        self.f_mono_it = tkfont.Font(family=mono, size=11, slant="italic")

    def _init_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, font=self.f_ui, bordercolor=BORDER,
                    lightcolor=BG, darkcolor=BG, troughcolor=SAND, focuscolor=BG)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Muted.TLabel", background=BG, foreground=WINE, font=self.f_small_b)
        s.configure("Mono.TLabel", background=PANEL, foreground=TEXT, font=self.f_mono)
        s.configure("TPanedwindow", background=BG)

        s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(2, 6, 0, 0))
        pad = (18, 7) if self.compact else (22, 10)
        s.configure("TNotebook.Tab", padding=pad, background=SAND, foreground=WINE,
                    borderwidth=0, font=self.f_bold)
        s.map("TNotebook.Tab",
              background=[("selected", BURGUNDY), ("active", BABY)],
              foreground=[("selected", "#FFFFFF"), ("active", BURGUNDY)],
              padding=[("selected", (pad[0], pad[1] + 2))])

        for orient in ("Vertical", "Horizontal"):
            s.configure(f"{orient}.TScrollbar", background=BABY, troughcolor=BLUSH,
                        bordercolor=BLUSH, arrowcolor=BURGUNDY, relief="flat", gripcount=0)
            s.map(f"{orient}.TScrollbar", background=[("active", ROSE_SOFT)])

        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=25, borderwidth=0, font=self.f_mono_s)
        s.map("Treeview", background=[("selected", BABY)], foreground=[("selected", BURGUNDY)])
        s.configure("Treeview.Heading", background=BURGUNDY, foreground="#FFFFFF",
                    font=self.f_bold, relief="flat", padding=(8, 6))
        s.map("Treeview.Heading", background=[("active", WINE)])

        s.configure("TCombobox", fieldbackground=PANEL, background=BABY, foreground=TEXT,
                    arrowcolor=BURGUNDY, padding=6, bordercolor=BORDER, relief="flat")
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)],
              foreground=[("readonly", TEXT)], bordercolor=[("focus", ROSE)],
              background=[("active", BABY_DARK)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", BURGUNDY)
        self.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
        self.option_add("*TCombobox*Listbox.font", self.f_ui)

    def _fade_in(self):
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            return

        def step(a=0.0):
            a = min(1.0, a + 0.12)
            try:
                self.attributes("-alpha", a)
            except tk.TclError:
                return
            if a < 1.0:
                self.after(24, lambda: step(a))
        self.after(40, step)

    # ---------------------------------------------------------------- menu
    def _build_menu(self):
        kw = dict(tearoff=0, bg=PANEL, fg=TEXT, activebackground=BABY,
                  activeforeground=BURGUNDY, bd=0, relief="flat")
        bar = tk.Menu(self, **kw)
        file_m = tk.Menu(bar, **kw)
        file_m.add_command(label="Open…", command=self.on_open)
        file_m.add_command(label="Save…", command=self.on_save)
        file_m.add_separator()
        file_m.add_command(label="Exit", command=self.destroy)
        run_m = tk.Menu(bar, **kw)
        run_m.add_command(label="Compile\tF5", command=self.on_compile)
        run_m.add_command(label="Execute\tF6", command=self.on_execute)
        run_m.add_command(label="Step\tF7", command=self.on_step)
        run_m.add_command(label="Reset VM", command=self.on_reset_vm)
        help_m = tk.Menu(bar, **kw)
        help_m.add_command(label="Language quick reference", command=self.on_reference)
        help_m.add_command(label="About", command=self.on_about)
        bar.add_cascade(label="File", menu=file_m)
        bar.add_cascade(label="Run", menu=run_m)
        bar.add_cascade(label="Help", menu=help_m)
        self.config(menu=bar)

    # -------------------------------------------------------------- header
    def _build_header(self):
        self.header = GradientHeader(self, (self.f_title, self.f_sub, self.f_small_b),
                                     height=64 if self.compact else 90)
        self.header.pack(fill="x")
        AccentBar(self).pack(fill="x")

    # ------------------------------------------------------------- toolbar
    def _build_toolbar(self):
        tb = tk.Frame(self, bg=BG)
        tb.pack(fill="x", padx=16, pady=(8 if self.compact else 12, 0))
        bh = 32 if self.compact else 36
        f = self.f_bold
        for text, cmd, kind in (("⚙  Compile", self.on_compile, "primary"),
                                ("▶  Execute", self.on_execute, "rose"),
                                ("⏭  Step", self.on_step, "soft"),
                                ("↺  Reset VM", self.on_reset_vm, "sand"),
                                ("✕  Clear", self.on_clear, "sand")):
            RoundButton(tb, text, cmd, kind, font=f, padx=13, height=bh, bg=BG).pack(side="left", padx=(0, 6))
        tk.Frame(tb, bg=BORDER, width=1, height=28).pack(side="left", padx=6)
        RoundButton(tb, "Open…", self.on_open, "sand", font=f, padx=13, height=bh, bg=BG).pack(side="left", padx=(0, 6))
        RoundButton(tb, "Save…", self.on_save, "sand", font=f, padx=13, height=bh, bg=BG).pack(side="left")

        self.example_var = tk.StringVar()
        self.example_combo = ttk.Combobox(tb, textvariable=self.example_var, values=[],
                                          state="readonly", width=20)
        self.example_combo.pack(side="right", pady=4)
        self.example_combo.bind("<<ComboboxSelected>>", self.on_example)
        tk.Label(tb, text="Examples", bg=BG, fg=WINE, font=self.f_small_b).pack(
            side="right", padx=(14, 6))
        self.lang_var = tk.StringVar(value=self.spec.name)
        lang = ttk.Combobox(tb, textvariable=self.lang_var, state="readonly", width=9,
                            values=[LANGUAGES[k].name for k in ORDER])
        lang.pack(side="right", pady=4)
        lang.bind("<<ComboboxSelected>>", self.on_language)
        tk.Label(tb, text="Language", bg=BG, fg=WINE, font=self.f_small_b).pack(
            side="right", padx=(14, 6))
        self._refresh_examples()

    # ------------------------------------------------------- pipeline chips
    def _build_pipeline(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=18, pady=(2, 4) if self.compact else (4, 6))
        tk.Label(row, text="PIPELINE", bg=BG, fg=WINE, font=self.f_small_b).pack(
            side="left", padx=(0, 12))
        self.chips = {}
        for i, name in enumerate(STAGES):
            if i:
                tk.Label(row, text="›", bg=BG, fg=ROSE_SOFT, font=self.f_bold).pack(
                    side="left", padx=5)
            chip = StageChip(row, name, self.f_small_b, bg=BG, height=24 if self.compact else 28)
            chip.pack(side="left")
            self.chips[name] = chip
        self._set_pipeline({})

    def _set_pipeline(self, states, counts=None, animate=False):
        for j in self._chip_jobs:
            self.after_cancel(j)
        self._chip_jobs = []
        counts = counts or {}
        marks = {"pending": "", "ok": "✓ ", "fail": "✗ ", "run": "● "}
        for i, name in enumerate(STAGES):
            st = states.get(name, "pending")
            n = counts.get(name)
            text = marks[st] + name + (f" ({n})" if n else "")
            if animate and st != "pending":              # cascade: stages light up one by one
                self.chips[name].set("pending", name, animate=False)
                self._chip_jobs.append(self.after(
                    i * 130, lambda c=self.chips[name], s=st, t=text: c.set(s, t)))
            else:
                self.chips[name].set(st, text, animate=False)

    def _pipeline_states(self, res, vm_state=None):
        states, counts = {}, {}
        for key, name in (("lexer", "Lexer"), ("parser", "Parser"), ("semantic", "Semantic")):
            n = len(res.stage_errors.get(key, []))
            states[name] = "fail" if n else "ok"
            counts[name] = n
        states["Bytecode"] = "ok" if res.ok else "pending"
        if vm_state:
            states["VM"] = vm_state
        return states, counts

    def _show_pipeline(self, vm_state=None, animate=False):
        if self.result is None:
            self._set_pipeline({})
            return
        states, counts = self._pipeline_states(self.result, vm_state)
        self._set_pipeline(states, counts, animate)

    # ---------------------------------------------------------- status bar
    def _build_status(self):
        bar = tk.Frame(self, bg=SAND)
        bar.pack(fill="x", side="bottom")
        self.status = tk.StringVar(value="Ready.")
        self.cursor_var = tk.StringVar(value="Ln 1, Col 1")
        self.dot = tk.Canvas(bar, width=16, height=16, bg=SAND, highlightthickness=0)
        self.dot.pack(side="left", padx=(14, 4), pady=6)
        self.dot_item = self.dot.create_oval(3, 3, 13, 13, fill=ROSE_SOFT, outline="")
        self.status_lbl = tk.Label(bar, textvariable=self.status, bg=SAND, fg=TEXT,
                                   font=self.f_small, anchor="w", pady=6)
        self.status_lbl.pack(side="left")
        tk.Label(bar, textvariable=self.cursor_var, bg=SAND, fg=MUTED, font=self.f_small,
                 padx=14).pack(side="right")
        self.lang_badge = tk.Label(bar, text=self.spec.name, bg=BURGUNDY, fg="#FFFFFF",
                                   font=self.f_small_b, padx=12, pady=2)
        self.lang_badge.pack(side="right", pady=5)

    def _status(self, text, kind="info"):
        self.status.set(text)
        color = {"info": ROSE_SOFT, "ok": SAGE, "error": ERROR}[kind]
        self.dot.itemconfigure(self.dot_item, fill=color)
        self.status_lbl.configure(fg=BURGUNDY if kind != "error" else ERROR)
        if self._status_job:
            self.after_cancel(self._status_job)
        self._status_job = self.after(900, lambda: self.status_lbl.configure(fg=TEXT))

    # ---------------------------------------------------------------- tabs
    def _card(self, parent, accent=ROSE):
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        inner = tk.Frame(outer, bg=PANEL)
        if accent:
            tk.Frame(inner, bg=accent, height=4).pack(fill="x", side="top")
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _make_text(self, parent, bg=PANEL, fg=TEXT, accent=ROSE):
        outer, inner = self._card(parent, accent)
        txt = tk.Text(inner, font=self.f_mono, wrap="none", bg=bg, fg=fg, relief="flat",
                      borderwidth=0, highlightthickness=0, padx=14, pady=10,
                      selectbackground=BABY if bg == PANEL else WINE,
                      selectforeground=BURGUNDY if bg == PANEL else "#FFFFFF",
                      insertbackground=fg)
        ys = ttk.Scrollbar(inner, orient="vertical", command=txt.yview)
        xs = ttk.Scrollbar(inner, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        txt.pack(side="left", fill="both", expand=True)
        return outer, txt

    def _add_tab(self, widget, name):
        self.nb.add(widget, text=f"  {name}  ")
        self.tabs[name] = widget

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # --- Source Code ---
        outer, inner = self._card(self.nb, ROSE)
        self.gutter = tk.Text(inner, width=4, font=self.f_mono, bg=BLUSH, fg=MUTED,
                              state="disabled", takefocus=0, relief="flat", borderwidth=0,
                              highlightthickness=0, padx=8, pady=10, cursor="arrow")
        self.gutter.pack(side="left", fill="y")
        self.gutter.tag_configure("r", justify="right")
        self.gutter.tag_configure("cur", foreground=BURGUNDY, font=self.f_mono_bold)
        self.editor = tk.Text(inner, font=self.f_mono, wrap="none", undo=True, bg=PANEL,
                              fg=TEXT, insertbackground=ROSE, insertwidth=2, relief="flat",
                              borderwidth=0, highlightthickness=0, padx=14, pady=10,
                              selectbackground=BABY, selectforeground=BURGUNDY,
                              inactiveselectbackground=BABY)
        self.edit_scroll = ttk.Scrollbar(inner, orient="vertical", command=self._yview_both)
        self.editor.configure(yscrollcommand=self._on_editor_scroll)
        self.edit_scroll.pack(side="right", fill="y")
        self.editor.pack(side="left", fill="both", expand=True)
        for tag, kw in (("curline", dict(background=BLUSH)),
                        ("errline", dict(background=ERR_LINE)),
                        ("type", dict(foreground=LAV_TXT, font=self.f_mono_bold)),
                        ("builtin", dict(foreground=ROSE)),
                        ("keyword", dict(foreground=BURGUNDY, font=self.f_mono_bold)),
                        ("number", dict(foreground=ORANGE_TXT)),
                        ("string", dict(foreground=SAGE_DARK)),
                        ("comment", dict(foreground=MUTED, font=self.f_mono_it))):
            self.editor.tag_configure(tag, **kw)
        self.editor.bind("<KeyRelease>", self._on_edit)
        self.editor.bind("<ButtonRelease-1>", lambda e: self._update_cursor())
        self.editor.bind("<<Paste>>", lambda e: self.after(10, self._on_edit))
        self._add_tab(outer, "Source Code")

        f, self.tokens_txt = self._make_text(self.nb, accent=PEACH)
        self._add_tab(f, "Tokens")
        f, self.ast_txt = self._make_text(self.nb, accent=LAVENDER)
        self._add_tab(f, "Syntax Tree")
        f, self.bc_txt = self._make_text(self.nb, accent=BURGUNDY)
        self._add_tab(f, "Bytecode")
        self._add_tab(self._build_execution_tab(), "Execution Output")

        f, self.err_txt = self._make_text(self.nb, accent=ERROR)
        self.err_txt.tag_configure("err", foreground=ERROR)
        self.err_txt.tag_configure("ok", foreground=SAGE_DARK, font=self.f_mono_bold)
        self.err_txt.tag_configure("head", foreground=BURGUNDY, font=self.f_mono_bold)
        self._add_tab(f, "Errors")

        # colour tags for the read-only panels
        for ttype, (fg, bold) in TOKEN_COLORS.items():
            self.tokens_txt.tag_configure(f"tok_{ttype}", foreground=fg,
                                          font=self.f_mono_bold if bold else self.f_mono)
        self.tokens_txt.tag_configure("tok_OP", foreground=ROSE)
        self.tokens_txt.tag_configure("tok_PUNCT", foreground=MUTED)
        self.tokens_txt.tag_configure("pos", foreground=MUTED)
        for op, fg in set(OP_COLORS.items()):
            self.bc_txt.tag_configure(f"op_{op}", foreground=fg, font=self.f_mono_bold)
        self.bc_txt.tag_configure("addr", foreground=MUTED)
        self.bc_txt.tag_configure("arg", foreground=TEXT)
        self.ast_txt.tag_configure("edge", foreground=LAV_TXT)
        self.ast_txt.tag_configure("node", foreground=BURGUNDY, font=self.f_mono_bold)
        self.ast_txt.tag_configure("leaf", foreground=ORANGE_TXT)
        self.ast_txt.tag_configure("glyph", foreground=BABY_DARK)

        for t in (self.tokens_txt, self.ast_txt, self.bc_txt, self.out_txt, self.err_txt):
            t.configure(state="disabled")

    def _build_execution_tab(self):
        ex = ttk.PanedWindow(self.nb, orient="horizontal")

        # left: console (top) + step-by-step trace (bottom)
        left = ttk.PanedWindow(ex, orient="vertical")
        con = tk.Frame(left, bg=BG)
        tk.Label(con, text="CONSOLE", bg=BG, fg=WINE, font=self.f_small_b).pack(
            anchor="w", pady=(4, 4))
        f, self.out_txt = self._make_text(con, bg=CONSOLE_BG, fg=CONSOLE_FG, accent=ROSE)
        f.pack(fill="both", expand=True, padx=(0, 8))
        self.out_txt.configure(height=4 if self.compact else 6)
        self.out_txt.tag_configure("fresh", background=WINE, foreground="#FFFFFF")
        self.out_txt.tag_configure("err", foreground="#FF9AB5", font=self.f_mono_bold)
        self.out_txt.tag_configure("done", foreground=SAGE_LIGHT, font=self.f_mono_it)
        left.add(con, weight=2)

        tr = tk.Frame(left, bg=BG)
        tk.Label(tr, text="EXECUTION TRACE  -  every instruction that has run (nothing is erased)",
                 bg=BG, fg=WINE, font=self.f_small_b).pack(anchor="w", pady=(8, 4))
        outer, inner = self._card(tr, PEACH)
        outer.pack(fill="both", expand=True, padx=(0, 8))
        self.trace = ttk.Treeview(inner, columns=("n", "ip", "ins", "stack"), show="headings",
                                  selectmode="browse", height=6 if self.compact else 9)
        for c, label, w, anchor in (("n", "Step", 64, "e"), ("ip", "IP", 56, "e"),
                                    ("ins", "Instruction", 170, "w"),
                                    ("stack", "Stack after this step", 240, "w")):
            self.trace.heading(c, text=label)
            self.trace.column(c, width=w, anchor=anchor, stretch=(c == "stack"))
        ys = ttk.Scrollbar(inner, orient="vertical", command=self.trace.yview)
        self.trace.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        self.trace.pack(side="left", fill="both", expand=True)
        self.trace.tag_configure("odd", background=BLUSH)
        self.trace.tag_configure("last", background=BABY, foreground=BURGUNDY)
        self.trace.tag_configure("err", background=ERR_LINE, foreground=ERROR)
        left.add(tr, weight=3)
        ex.add(left, weight=5)

        # right: state strip, VARIABLES & VALUES (big), stack | bytecode
        right = ttk.PanedWindow(ex, orient="vertical")
        top = tk.Frame(right, bg=BG)
        outer, card = self._card(top, BURGUNDY)
        outer.pack(fill="x", padx=(8, 0), pady=(4, 0))
        self.vm_state = tk.StringVar(value="ip  -    steps  0    next  -")
        tk.Label(card, textvariable=self.vm_state, bg=PANEL, fg=TEXT, font=self.f_mono_s,
                 anchor="w", padx=12, pady=5).pack(fill="x")
        right.add(top, weight=0)
        right.add(self._variables_card(right), weight=5)
        bottom = ttk.PanedWindow(right, orient="horizontal")
        bottom.add(self._list_card(bottom, "Stack  (top first)", "stack", PEACH), weight=1)
        bottom.add(self._list_card(bottom, "Bytecode  (selected = next)", "code", LAVENDER), weight=2)
        right.add(bottom, weight=3)
        ex.add(right, weight=4)
        return ex

    def _variables_card(self, parent):
        frame = tk.Frame(parent, bg=BG)
        tk.Label(frame, text="VARIABLES & VALUES", bg=BG, fg=WINE, font=self.f_small_b).pack(
            anchor="w", pady=(8, 3), padx=(8, 0))
        outer, inner = self._card(frame, SAGE)
        outer.pack(fill="both", expand=True, padx=(8, 0))
        self.mem_tree = ttk.Treeview(inner, columns=("name", "value", "type"), show="headings",
                                     height=5, selectmode="browse")
        for c, label, w, stretch in (("name", "Variable", 110, False), ("value", "Value", 150, True),
                                     ("type", "Type", 70, False)):
            self.mem_tree.heading(c, text=label)
            self.mem_tree.column(c, width=w, stretch=stretch, anchor="w")
        ys = ttk.Scrollbar(inner, orient="vertical", command=self.mem_tree.yview)
        self.mem_tree.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        self.mem_tree.pack(side="left", fill="both", expand=True)
        self.mem_tree.tag_configure("odd", background=BLUSH)
        self.mem_tree.tag_configure("unset", foreground=MUTED)
        self.mem_tree.tag_configure("changed", background=BABY, foreground=BURGUNDY)
        return frame

    def _list_card(self, parent, title, kind, accent):
        frame = tk.Frame(parent, bg=BG)
        tk.Label(frame, text=title.upper(), bg=BG, fg=WINE, font=self.f_small_b).pack(
            anchor="w", pady=(8, 3), padx=(8, 0))
        outer, inner = self._card(frame, accent)
        outer.pack(fill="both", expand=True, padx=(8, 0))
        tree = ttk.Treeview(inner, show="tree", height=5, selectmode="browse")
        tree.column("#0", stretch=True, width=120)
        ys = ttk.Scrollbar(inner, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        if kind == "code":
            self.code_tree = tree
            for fg in set(OP_COLORS.values()):
                tree.tag_configure(f"fg_{fg}", foreground=fg)
        else:
            self.stack_tree = tree
        return frame

    def _bind_keys(self):
        self.bind("<F5>", lambda e: self.on_compile())
        self.bind("<F6>", lambda e: self.on_execute())
        self.bind("<F7>", lambda e: self.on_step())

    # -------------------------------------------------------------- helpers
    def _select_tab(self, name):
        self.nb.select(self.tabs[name])

    def _yview_both(self, *args):
        self.editor.yview(*args)
        self.gutter.yview(*args)

    def _on_editor_scroll(self, first, last):
        self.edit_scroll.set(first, last)
        self.gutter.yview_moveto(first)

    def _on_edit(self, event=None):
        self.editor.tag_remove("errline", "1.0", "end")
        if self.result is not None and self.result.source != self._source():
            self._set_pipeline({})
        self._update_gutter()
        self._highlight()
        self._update_cursor()

    def _update_cursor(self):
        line, col = self.editor.index("insert").split(".")
        self.cursor_var.set(f"Ln {line}, Col {int(col) + 1}")
        self.editor.tag_remove("curline", "1.0", "end")
        self.editor.tag_add("curline", f"{line}.0", f"{line}.0 lineend+1c")
        self.gutter.tag_remove("cur", "1.0", "end")
        self.gutter.tag_add("cur", f"{line}.0", f"{line}.0 lineend")

    def _update_gutter(self):
        n = int(self.editor.index("end-1c").split(".")[0])
        self.gutter.configure(state="normal")
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", "\n".join(str(i) for i in range(1, n + 1)))
        self.gutter.tag_add("r", "1.0", "end")
        self.gutter.configure(state="disabled")
        self.gutter.yview_moveto(self.editor.yview()[0])

    def _highlight(self):
        names = ("type", "builtin", "keyword", "number", "string", "comment")
        for tag in names:
            self.editor.tag_remove(tag, "1.0", "end")
        text = self.editor.get("1.0", "end-1c")
        for tag, rx in self._patterns:
            for m in rx.finditer(text):
                self.editor.tag_add(tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")
        for tag in names:
            self.editor.tag_raise(tag)

    def _set_editor(self, text):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.mark_set("insert", "1.0")
        self._loaded_text = text
        self._on_edit()

    @staticmethod
    def _set_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _source(self):
        return self.editor.get("1.0", "end-1c")

    # ---- colourised read-only panels ----
    def _color_tokens(self, tokens):
        w = self.tokens_txt
        for i, tok in enumerate(tokens[:4000], start=1):
            t = tok.type
            tag = f"tok_{t}" if t in TOKEN_COLORS else ("tok_PUNCT" if t in PUNCT else "tok_OP")
            head = len(str(tok))
            w.tag_add(tag, f"{i}.0", f"{i}.{head}")
            w.tag_add("pos", f"{i}.{head}", f"{i}.0 lineend")

    def _color_bytecode(self, code):
        w = self.bc_txt
        for i, ins in enumerate(code[:4000], start=1):
            w.tag_add("addr", f"{i}.0", f"{i}.4")
            end = 6 + len(ins.op)
            w.tag_add(f"op_{ins.op}", f"{i}.6", f"{i}.{end}")
            if ins.arg is not None:
                w.tag_add("arg", f"{i}.{end}", f"{i}.0 lineend")

    def _color_ast(self, text):
        w = self.ast_txt
        rx = re.compile(r"^([│├└─\s]*)(?:(\w+): )?(<error>|\w+)(\(.*\))?$")
        for i, line in enumerate(text.split("\n")[:4000], start=1):
            m = rx.match(line)
            if not m:
                continue
            g1, edge, node, args = m.group(1), m.group(2), m.group(3), m.group(4)
            pos = len(g1)
            if g1:
                w.tag_add("glyph", f"{i}.0", f"{i}.{pos}")
            if edge:
                w.tag_add("edge", f"{i}.{pos}", f"{i}.{pos + len(edge) + 1}")
                pos += len(edge) + 2
            w.tag_add("node", f"{i}.{pos}", f"{i}.{pos + len(node)}")
            if args:
                w.tag_add("leaf", f"{i}.{pos + len(node)}", f"{i}.{pos + len(node) + len(args)}")

    def _clear_panels(self):
        for w in (self.tokens_txt, self.ast_txt, self.bc_txt, self.out_txt, self.err_txt):
            self._set_text(w, "")
        self._trace_clear()
        self._fill_code_list(None)
        self._var_names = []
        self._refresh_vm_view(None)
        self._set_pipeline({})

    def _show_errors(self, errors, stage_errors=None):
        self.err_txt.configure(state="normal")
        self.err_txt.delete("1.0", "end")
        if not errors:
            self.err_txt.insert("1.0", "✓ No errors.", "ok")
        else:
            if stage_errors:
                parts = [f"{len(stage_errors.get(k, []))} {label}" for k, label in
                         (("lexer", "lexical"), ("parser", "syntax"), ("semantic", "semantic"))
                         if stage_errors.get(k)]
                head = f"{len(errors)} error(s) found  ({', '.join(parts)})\n\n"
            else:
                head = f"{len(errors)} error(s)\n\n"
            self.err_txt.insert("end", head, "head")
            for e in errors:
                self.err_txt.insert("end", "✗ " + str(e) + "\n", "err")
        self.err_txt.configure(state="disabled")

    def _mark_error_lines(self, errors):
        self.editor.tag_remove("errline", "1.0", "end")
        for e in errors:
            if e.line:
                self.editor.tag_add("errline", f"{e.line}.0", f"{e.line}.0 lineend+1c")

    # ---- VM views ----
    def _style(self):
        return self.result.style if self.result else self.spec.dialect

    def _fmt(self, v):
        style = self._style()
        if isinstance(v, str):
            return repr(v) if style == "python" else f'"{v}"'
        return format_value(v, style)

    def _type_name(self, v):
        names = {"minilang": ("number", "number", "string", "bool"),
                 "python": ("int", "float", "str", "bool"),
                 "cpp": ("int", "double", "string", "bool"),
                 "java": ("int", "double", "String", "boolean")}[self._style()]
        if isinstance(v, bool):
            return names[3]
        if isinstance(v, int):
            return names[0]
        if isinstance(v, float):
            return names[1]
        return names[2]

    def _refresh_vm_view(self, vm):
        self.stack_tree.delete(*self.stack_tree.get_children())
        self.mem_tree.delete(*self.mem_tree.get_children())
        sel = self.code_tree.selection()
        if sel:
            self.code_tree.selection_remove(*sel)
        memory = vm.memory if vm is not None else {}
        names = [n for n in self._var_names]
        names += [n for n in memory if n not in names and not n.startswith("$")]
        if not names:
            self.mem_tree.insert("", "end", values=("(none)", "this program has no variables", ""),
                                 tags=("unset",))
        for i, name in enumerate(names):
            if name in memory:
                val = memory[name]
                prev = self._prev_mem.get(name, self)
                changed = vm is not None and (prev is self or prev != val
                                              or type(prev) is not type(val))
                tags = ("changed",) if changed else (("odd",) if i % 2 else ())
                self.mem_tree.insert("", "end", values=(name, self._fmt(val), self._type_name(val)),
                                     tags=tags)
            else:
                self.mem_tree.insert("", "end", values=(name, "—  (not assigned yet)", ""),
                                     tags=("unset",))
        if vm is None:
            self._prev_mem = {}
            self.vm_state.set("ip  -    steps  0    next  -")
            return
        self._prev_mem = dict(memory)
        for v in reversed(vm.stack):
            self.stack_tree.insert("", "end", text=self._fmt(v))
        kids = self.stack_tree.get_children()
        if kids:
            self.stack_tree.selection_set(kids[0])
        nxt = vm.next_instruction
        self.vm_state.set(f"ip  {vm.ip}    steps  {vm.steps}    next  "
                          f"{nxt if nxt else '(halted)'}")
        if nxt is not None:
            self.code_tree.selection_set(str(vm.ip))
            row = str(vm.ip)
            self.code_tree.see(row)
            self.code_tree.after(30, lambda: self.code_tree.exists(row) and self.code_tree.see(row))

    def _fill_code_list(self, bytecode):
        self.code_tree.delete(*self.code_tree.get_children())
        for i, ins in enumerate(bytecode or []):
            self.code_tree.insert("", "end", iid=str(i), text=f"{i:04d}  {ins}",
                                  tags=(f"fg_{OP_COLORS.get(ins.op, TEXT)}",))

    # ---- trace ----
    def _trace_clear(self):
        for item in self.trace.get_children():
            self.trace.delete(item)

    def _trace_add(self, entry, error=False):
        for item in self.trace.get_children()[-1:]:
            tags = [t for t in self.trace.item(item, "tags") if t != "last"]
            self.trace.item(item, tags=tags)
        n = len(self.trace.get_children())
        tags = ["err" if error else "last"] + (["odd"] if n % 2 else [])
        iid = self.trace.insert("", "end", values=(entry.step, entry.ip, entry.text, entry.stack),
                                tags=tuple(tags))
        self.trace.see(iid)

    def _trace_fill(self, vm, error=False):
        self._trace_clear()
        for entry in vm.history:
            self._trace_add(entry)
        if vm.history_truncated:
            self.trace.insert("", "end", values=("…", "", "trace limited to the first "
                                                 f"{vm.history_limit} steps", ""))
        kids = self.trace.get_children()
        if error and kids:
            self.trace.item(kids[-1], tags=("err",))

    def _append_console(self, text, tag=None):
        w = self.out_txt
        w.configure(state="normal")
        w.tag_remove("fresh", "1.0", "end")
        start = w.index("end-1c")
        w.insert("end", text + "\n", tag or ())
        if tag is None:
            w.tag_add("fresh", start, f"{start} lineend")     # newest line flashes
            if self._fresh_job:
                self.after_cancel(self._fresh_job)
            self._fresh_job = self.after(450, lambda: w.tag_remove("fresh", "1.0", "end"))
        w.see("end")
        w.configure(state="disabled")

    def _new_vm(self):
        self._prev_mem = {}
        self._set_text(self.out_txt, "")
        self._trace_clear()
        self.vm = VirtualMachine(self.result.bytecode, self._append_console,
                                 style=self.result.style)

    # -------------------------------------------------------------- actions
    def on_compile(self):
        self.vm = None
        res = compile_source(self._source(), self.spec.key)
        self.result = res
        self._set_text(self.tokens_txt, format_tokens(res.tokens))
        self._color_tokens(res.tokens)
        tree = format_ast(res.ast) if res.ast else ""
        if res.errors:
            tree = "(partial syntax tree - the source still has errors)\n\n" + tree
        self._set_text(self.ast_txt, tree)
        self._color_ast(tree)
        self._set_text(self.bc_txt, format_bytecode(res.bytecode) if res.bytecode else
                       "(no bytecode - fix all errors first; see the Errors tab)")
        if res.bytecode:
            self._color_bytecode(res.bytecode)
        self._fill_code_list(res.bytecode)
        self._var_names = []
        for ins in res.bytecode or []:
            if ins.op == "STORE" and not ins.arg.startswith("$") and ins.arg not in self._var_names:
                self._var_names.append(ins.arg)
        self._set_text(self.out_txt, "")
        self._trace_clear()
        self._refresh_vm_view(None)
        self._show_errors(res.errors, res.stage_errors)
        self._mark_error_lines(res.errors)
        self._show_pipeline(animate=True)
        if res.ok:
            self._status(f"Compiled successfully: {len(res.tokens) - 1} tokens, "
                         f"{len(res.bytecode)} instructions.", "ok")
            self.toast.show(f"✓  Compiled - {len(res.bytecode)} instructions", "ok")
            self._select_tab("Bytecode")
        else:
            n = len(res.errors)
            self._status(f"Compilation failed: {n} error(s) found in one pass - "
                         f"see the Errors tab.", "error")
            self.toast.show(f"✗  {n} error{'s' if n != 1 else ''} found", "error")
            self._select_tab("Errors")
        return res.ok

    def _ensure_compiled(self):
        if (self.result is None or self.result.source != self._source()
                or self.result.language != self.spec.key):
            return self.on_compile()
        return self.result.ok

    def on_execute(self):
        if not self._ensure_compiled():
            return
        self._new_vm()
        error = None
        try:
            self.vm.run()
        except MiniLangError as e:
            error = e
        self._trace_fill(self.vm, error=error is not None)
        self._prev_mem = dict(self.vm.memory)          # full run: nothing is "just changed"
        self._refresh_vm_view(self.vm)
        self._select_tab("Execution Output")
        if error:
            self._append_console(str(error), "err")
            self._show_errors([error])
            self._show_pipeline("fail")
            self._status("Execution stopped by a runtime error.", "error")
            self.toast.show("✗  Runtime error", "error")
        else:
            self._append_console("[Program finished]", "done")
            self._show_errors([])
            self._show_pipeline("ok")
            self._status(f"Execution finished in {self.vm.steps} steps.", "ok")
            self.toast.show(f"✓  Finished in {self.vm.steps} steps", "pink")

    def on_step(self):
        """Execute ONE instruction. Earlier steps stay visible in the trace."""
        if not self._ensure_compiled():
            return
        if self.vm is None:
            self._new_vm()
        if self.vm.halted:
            self._status("The program has finished - press 'Reset VM' to step through it again.")
            self.toast.show("Program finished - press Reset VM", "pink", hold=1800)
            self._select_tab("Execution Output")
            return
        ins = self.vm.next_instruction
        before = len(self.vm.history)
        error = None
        try:
            self.vm.step()
        except MiniLangError as e:
            error = e
        for entry in self.vm.history[before:]:
            self._trace_add(entry, error=error is not None)
        if error:
            self._append_console(str(error), "err")
            self._show_errors([error])
            self._show_pipeline("fail")
            self._status("Execution stopped by a runtime error.", "error")
            self.toast.show("✗  Runtime error", "error")
        elif self.vm.halted:
            self._append_console("[Program finished]", "done")
            self._show_pipeline("ok")
            self._status(f"Executed: {ins}   -   program finished.", "ok")
            self.toast.show("✓  Program finished", "ok", hold=1500)
        else:
            self._show_pipeline("run")
            self._status(f"Executed: {ins}")
        self._refresh_vm_view(self.vm)
        self._select_tab("Execution Output")

    def on_reset_vm(self):
        self.vm = None
        self._set_text(self.out_txt, "")
        self._trace_clear()
        self._refresh_vm_view(None)
        if self.result is not None and self.result.ok:
            self._show_pipeline()
        self._status("VM reset.")

    def on_clear(self):
        self.editor.delete("1.0", "end")
        self.result = None
        self.vm = None
        self._on_edit()
        self._clear_panels()
        self._select_tab("Source Code")
        self._status("Cleared.")

    # ---- language / files ----
    def _apply_language(self, key):
        self.spec = LANGUAGES[key]
        self._patterns = _highlight_patterns(self.spec)
        self.lang_var.set(self.spec.name)
        self.lang_badge.configure(text=self.spec.name)
        self.header.set_active(key)
        self._refresh_examples()

    def _refresh_examples(self):
        folder = os.path.join(EXAMPLES_ROOT, self.spec.examples_dir)
        names = sorted(f for f in os.listdir(folder)
                       if f.endswith(self.spec.extension)) if os.path.isdir(folder) else []
        self.example_combo.configure(values=names)
        self.example_var.set("")

    def on_language(self, event=None):
        key = next(k for k in ORDER if LANGUAGES[k].name == self.lang_var.get())
        if key == self.spec.key:
            return
        pristine = self._source().strip() in ("", self._loaded_text.strip())
        self._apply_language(key)
        self.result = None
        self.vm = None
        self._clear_panels()
        if pristine:
            self._set_editor(self.spec.sample)
        else:
            self._on_edit()
        self._select_tab("Source Code")
        self._status(f"Language: {self.spec.name}")
        self.toast.show(f"Language: {self.spec.name}", "pink", hold=1200)

    def on_open(self):
        folder = os.path.join(EXAMPLES_ROOT, self.spec.examples_dir)
        kinds = [(s.name, f"*{s.extension}") for s in LANGUAGES.values()]
        path = filedialog.askopenfilename(
            initialdir=folder if os.path.isdir(folder) else ".",
            filetypes=kinds + [("All files", "*.*")])
        if path:
            self._load(path)

    def on_save(self):
        path = filedialog.asksaveasfilename(
            defaultextension=self.spec.extension,
            filetypes=[(self.spec.name, f"*{self.spec.extension}")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._source())
            self._status(f"Saved {path}", "ok")

    def on_example(self, event=None):
        self._load(os.path.join(EXAMPLES_ROOT, self.spec.examples_dir, self.example_var.get()))

    def _load(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            messagebox.showerror("Open failed", str(e))
            return
        key = language_for_extension(path)
        if key and key != self.spec.key:
            self._apply_language(key)
        self._set_editor(text)
        self.result = None
        self.vm = None
        self._clear_panels()
        self._select_tab("Source Code")
        self._status(f"Loaded {os.path.basename(path)}")

    def on_about(self):
        messagebox.showinfo(
            "About MiniLang",
            f"MiniLang Compiler & Virtual Machine  v{__version__}\n\n"
            "Front ends: MiniLang, Python subset, C++ subset, Java subset.\n"
            "Lexer → Parser → AST → Semantic Analyzer → Bytecode → Stack VM.\n"
            "Built for the Compiler Construction semester project.")

    def on_reference(self):
        refs = {
            "minilang": 'let x = 10;  let s = "text";  let ok = true;\nx = x + 1;\nprint(x);\n'
                        "if (...) { } else { }   while (...) { }   break;  continue;\n"
                        "Operators: + - * / %  == != < > <= >=  && || !",
            "python": "x = 10   name = \"Ali\"   (no declaration needed)\n"
                      "print(x, name, sep=\"-\")   print(f\"x = {x:.2f}\")\n"
                      "if / elif / else:   while cond:   for i in range(a, b, step):\n"
                      "break  continue  pass   a, b = b, a   x += 1\n"
                      "+ - * / // % **   and or not   == != < > <= >=   (indent = 4 spaces)",
            "cpp": "int main() { ... return 0; }\nint/double/bool/string/auto  x = ...;\n"
                   'cout << "a" << x << endl;   to_string(x)\n'
                   "if / else if / else, while, for, break, continue, ++ -- += -= ...",
            "java": "public class Main { public static void main(String[] args) { ... } }\n"
                    "int/double/boolean/String/var  x = ...;\n"
                    'System.out.println("a" + x);   System.out.print(x);   String.valueOf(x)\n'
                    "if / else if / else, while, for, break, continue, ++ -- += -= ...",
        }
        messagebox.showinfo(f"{self.spec.name} quick reference", refs[self.spec.key])


def launch():
    MiniLangApp().mainloop()
