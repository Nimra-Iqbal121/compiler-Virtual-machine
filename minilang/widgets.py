"""Theme colours + custom animated widgets (pure Tkinter, no extra packages).

Palette: baby pink, burgundy and beige, with small accents of peach, sage and
lavender.  Effects: gradient header, hover/press button animation, colour-tweened
stage chips that pulse while the VM runs, a moving accent bar and toast messages.
"""
import math
import tkinter as tk
import tkinter.font as tkfont

# ------------------------------------------------------------------ palette
BG = "#F6EDE1"          # beige
SAND = "#EADBC8"        # deeper beige
PANEL = "#FFFBF6"       # warm white
BLUSH = "#FFF0F5"
BABY = "#F9CFE0"        # baby pink
BABY_DARK = "#F2AFCB"
ROSE = "#D94F86"
ROSE_SOFT = "#F28DB4"
ROSE_HOVER = "#E8719F"
BURGUNDY = "#7A1F3D"
WINE = "#9A2E52"
DEEP = "#4E1128"
TEXT = "#4A2A35"
MUTED = "#A08B8F"
BORDER = "#E4D3C0"
PEACH = "#F2A97E"
ORANGE_TXT = "#C2570C"
SAGE = "#5FA384"
SAGE_DARK = "#2F7D5B"
SAGE_LIGHT = "#CBE7D6"
GOLD = "#F2C766"
LAVENDER = "#B8A2DC"
LAV_TXT = "#6B4FA0"
ERROR = "#C0264F"
ERR_LINE = "#FAD0DB"
CONSOLE_BG = "#3B0F20"
CONSOLE_FG = "#FDE8F0"


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Blend colour a towards colour b by t (0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def rounded_points(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    kw.setdefault("outline", "")
    return canvas.create_polygon(rounded_points(x1, y1, x2, y2, r), smooth=True, **kw)


# ------------------------------------------------------------------- button
class RoundButton(tk.Canvas):
    """Rounded button with a soft shadow, hover colour fade + lift, press dip."""
    KINDS = {                      # base, hover, text
        "primary": (BURGUNDY, WINE, "#FFFFFF"),
        "rose": (ROSE, ROSE_HOVER, "#FFFFFF"),
        "soft": (BABY, BABY_DARK, BURGUNDY),
        "sand": (SAND, BABY, TEXT),
    }

    def __init__(self, parent, text, command, kind="sand", font=None,
                 padx=18, height=36, bg=BG):
        self._font = font or tkfont.nametofont("TkDefaultFont")
        w = self._font.measure(text) + padx * 2 + 6
        super().__init__(parent, width=w, height=height + 6, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.base, self.hover, self.fg = self.KINDS[kind]
        self._cur, self._dy, self._jobs, self._inside = self.base, 0, [], False
        self.shadow = round_rect(self, 3, 5, w - 3, height + 3, 13,
                                 fill=mix(bg, DEEP, 0.16))
        self.body = round_rect(self, 3, 2, w - 3, height, 13, fill=self.base)
        self.label = self.create_text(w / 2, height / 2 + 1, text=text, fill=self.fg,
                                      font=self._font)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def _lift(self, dy):
        delta = dy - self._dy
        if delta:
            self.move(self.body, 0, delta)
            self.move(self.label, 0, delta)
            self._dy = dy

    def _paint(self, color):
        self._cur = color
        self.itemconfigure(self.body, fill=color)

    def _tween(self, target, steps=6, delay=14):
        for j in self._jobs:
            self.after_cancel(j)
        start = self._cur
        self._jobs = [self.after(i * delay, lambda c=mix(start, target, i / steps): self._paint(c))
                      for i in range(1, steps + 1)]

    def _enter(self, _e):
        self._inside = True
        self._lift(-1)
        self._tween(self.hover)

    def _leave(self, _e):
        self._inside = False
        self._lift(0)
        self._tween(self.base)

    def _press(self, _e):
        self._lift(2)
        self._tween(mix(self.hover, DEEP, 0.22), steps=3, delay=8)

    def _release(self, _e):
        self._lift(-1 if self._inside else 0)
        self._tween(self.hover if self._inside else self.base)
        if self._inside and self.command:
            self.command()


# --------------------------------------------------------------- stage chip
class StageChip(tk.Canvas):
    """Pill that fades between states; pulses softly while the VM is running."""
    STATES = {
        "pending": (SAND, "#9A8680"),
        "ok": (SAGE, "#FFFFFF"),
        "fail": (ERROR, "#FFFFFF"),
        "run": (BABY, BURGUNDY),
    }

    def __init__(self, parent, name, font, bg=BG, height=28):
        w = font.measure(f"✗ {name} (99)") + 28
        self._h = height
        super().__init__(parent, width=w, height=self._h, bg=bg, highlightthickness=0, bd=0)
        self.body = round_rect(self, 0, 0, w, self._h - 1, self._h // 2, fill=SAND)
        self.text = self.create_text(w / 2, self._h / 2, text=name, fill="#9A8680", font=font)
        self.state, self._cur, self._jobs, self._phase = "pending", SAND, [], False

    def _paint(self, color):
        self._cur = color
        self.itemconfigure(self.body, fill=color)

    def _cancel(self):
        for j in self._jobs:
            self.after_cancel(j)
        self._jobs = []

    def _tween(self, target, steps, delay, then=None):
        start = self._cur
        for i in range(1, steps + 1):
            self._jobs.append(self.after(i * delay,
                                         lambda c=mix(start, target, i / steps): self._paint(c)))
        if then:
            self._jobs.append(self.after((steps + 1) * delay, then))

    def set(self, state, text, animate=True):
        self._cancel()
        self.state = state
        bg, fg = self.STATES[state]
        self.itemconfigure(self.text, text=text, fill=fg)
        if animate:
            self._tween(bg, 9, 18, self._pulse if state == "run" else None)
        else:
            self._paint(bg)
            if state == "run":
                self._pulse()

    def _pulse(self):
        if self.state != "run":
            return
        self._phase = not self._phase
        self._jobs = []
        self._tween(ROSE_SOFT if self._phase else BABY, 14, 45, self._pulse)


# ------------------------------------------------------------------- header
class GradientHeader(tk.Canvas):
    """Burgundy -> rose -> baby-pink gradient banner with logo and language badges."""
    STOPS = [DEEP, BURGUNDY, "#B83A66", ROSE, "#F08DB5"]
    BADGES = (("minilang", "MiniLang", BABY), ("python", "Python", GOLD),
              ("cpp", "C++", PEACH), ("java", "Java", LAVENDER))

    def __init__(self, parent, fonts, height=90):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=DEEP)
        self.f_title, self.f_sub, self.f_badge = fonts
        self.h, self._width, self.active = height, 0, "minilang"
        self.bind("<Configure>", self._configure)

    def _grad(self, x):
        n = len(self.STOPS) - 1
        pos = max(0.0, min(1.0, x / max(self._width, 1))) * n
        i = min(int(pos), n - 1)
        return mix(self.STOPS[i], self.STOPS[i + 1], pos - i)

    def _configure(self, e):
        if e.width != self._width:
            self._width = e.width
            self.draw()

    def set_active(self, key):
        self.active = key
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self._width, self.h
        compact = h < 80
        for x in range(0, w, 3):
            self.create_rectangle(x, 0, x + 3, h, fill=self._grad(x), outline="")
        for cx, cy, r, t in ((w - 90, h * 0.1, h * 0.78, 0.10), (w - 300, h * 1.0, h * 0.5, 0.08),
                             (w * 0.46, -h * 0.2, h * 0.62, 0.07), (w * 0.62, h * 1.1, h * 0.42, 0.06)):
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             fill=mix(self._grad(cx), "#FFFFFF", t), outline="")
        cy = h / 2
        ring, inner = h * 0.35, h * 0.28
        lx = 18 + ring
        self.create_oval(lx - ring, cy - ring, lx + ring, cy + ring,
                         outline=mix(self._grad(lx), "#FFFFFF", 0.45), width=2)
        self.create_oval(lx - inner, cy - inner, lx + inner, cy + inner, fill=BABY, outline="")
        self.create_text(lx, cy, text="ML", fill=BURGUNDY, font=self.f_title)
        tx = lx + ring + 16
        ty = cy if compact else cy - 12
        self.create_text(tx + 2, ty + 2, text="MiniLang", anchor="w", fill=DEEP, font=self.f_title)
        self.create_text(tx, ty, text="MiniLang", anchor="w", fill="#FFFFFF", font=self.f_title)
        tw = self.f_title.measure("MiniLang")
        self.create_text(tx + tw + 12, ty + (3 if compact else 5), text="Compiler & Virtual Machine",
                         anchor="w", fill="#FBDDE9", font=self.f_sub)
        if not compact:
            self.create_text(tx, cy + 21,
                             text="Lexer  ›  Parser  ›  AST  ›  Semantic  ›  Bytecode  ›  Stack VM",
                             anchor="w", fill="#F6C3D6", font=self.f_badge)
        bh = 13 if compact else 15
        x = w - 20
        for key, label, color in self.BADGES[::-1]:
            bw = self.f_badge.measure(label) + 24
            x1 = x - bw
            if key == self.active:
                round_rect(self, x1, cy - bh, x, cy + bh, bh, fill=color)
                self.create_text((x1 + x) / 2, cy, text=label, fill=BURGUNDY, font=self.f_badge)
            else:
                round_rect(self, x1, cy - bh, x, cy + bh, bh,
                           fill=mix(self._grad(x1), DEEP, 0.32))
                self.create_text((x1 + x) / 2, cy, text=label, fill="#FFFFFF", font=self.f_badge)
            x = x1 - 8


class AccentBar(tk.Canvas):
    """Thin bar under the header with a soft glow that keeps sweeping across."""

    def __init__(self, parent, height=4):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=DEEP)
        self._x, self._h, self._glow = -200.0, height, 200
        for i in range(20):
            t = math.sin(math.pi * i / 19)
            self.create_rectangle(i * 10, 0, i * 10 + 10, height, outline="",
                                  fill=mix(DEEP, BABY, t), tags="glow")
        self.move("glow", self._x, 0)
        self.after(60, self._tick)

    def _tick(self):
        try:
            w = self.winfo_width()
            self._x += 5
            self.move("glow", 5, 0)
            if self._x > w:
                self.move("glow", -(self._x + self._glow), 0)
                self._x = -float(self._glow)
            self.after(26, self._tick)
        except tk.TclError:
            pass


# -------------------------------------------------------------------- toast
class Toast:
    """Small rounded message that slides in from the right and slides out again."""
    KINDS = {"ok": (SAGE, "#FFFFFF"), "error": (ERROR, "#FFFFFF"),
             "info": (BURGUNDY, "#FFFFFF"), "pink": (BABY, BURGUNDY)}

    def __init__(self, root, font):
        self.root, self.font, self.label, self._jobs = root, font, None, []

    def _clear(self):
        for j in self._jobs:
            try:
                self.root.after_cancel(j)
            except tk.TclError:
                pass
        self._jobs = []
        if self.label is not None:
            self.label.destroy()
            self.label = None

    def show(self, text, kind="ok", hold=2600):
        self._clear()
        bg, fg = self.KINDS[kind]
        self.label = tk.Label(self.root, text=text, bg=bg, fg=fg, font=self.font,
                              padx=20, pady=11, bd=0)
        self.label.place(relx=1.0, rely=1.0, x=420, y=-52, anchor="se")
        steps = 14
        for i in range(1, steps + 1):                       # slide in (ease-out)
            x = 420 - (420 + 22) * (1 - (1 - i / steps) ** 3)
            self._jobs.append(self.root.after(i * 16, lambda x=x: self._move(x)))
        self._jobs.append(self.root.after(steps * 16 + hold, self._slide_out))

    def _move(self, x):
        if self.label is not None:
            self.label.place_configure(x=x)

    def _slide_out(self):
        steps = 10
        for i in range(1, steps + 1):
            x = -22 + (440) * (i / steps) ** 2
            self._jobs.append(self.root.after(i * 16, lambda x=x: self._move(x)))
        self._jobs.append(self.root.after(steps * 16 + 30, self._clear))
