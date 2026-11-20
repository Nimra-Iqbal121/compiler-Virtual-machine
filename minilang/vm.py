"""Stack-based virtual machine.

Components: operand stack, variable memory, instruction pointer (ip) and an
execution engine that fetches / decodes / executes one instruction per step().
Every executed instruction is also recorded in `history` (the execution trace).
"""
import math
from collections import namedtuple
from .errors import VMRuntimeError

TraceEntry = namedtuple("TraceEntry", "step ip text stack")


def format_value(v, style="minilang"):
    if isinstance(v, bool):
        if style == "cpp":
            return "1" if v else "0"
        if style == "python":
            return "True" if v else "False"
        return "true" if v else "false"
    if isinstance(v, float):
        if style == "python":
            return repr(v)
        if style == "java":
            s = repr(v)
            if "e" in s:
                mant, exp = s.split("e")
                if "." not in mant:
                    mant += ".0"
                return f"{mant}E{int(exp)}"
            return s
        if style == "cpp":
            return f"{v:g}"
        return f"{v:.10g}"
    return str(v)


def format_stack(stack, style="minilang"):
    return "[" + ", ".join(repr(v) if isinstance(v, str) else format_value(v, style)
                           for v in stack) + "]"


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _truthy(v):
    return v != "" if isinstance(v, str) else bool(v)


class VirtualMachine:
    def __init__(self, program, on_output=None, max_steps=1_000_000,
                 style="minilang", history_limit=5000):
        self.program = program
        self.on_output = on_output
        self.max_steps = max_steps
        self.style = style
        self.history_limit = history_limit
        self.reset()

    def reset(self):
        self.stack = []
        self.memory = {}
        self.ip = 0
        self.steps = 0
        self.halted = False
        self.output = []          # completed output lines
        self.history = []         # execution trace (TraceEntry)
        self.history_truncated = False
        self._buf = ""            # partial line (WRITE without NEWLINE)

    @property
    def next_instruction(self):
        if self.halted or not (0 <= self.ip < len(self.program)):
            return None
        return self.program[self.ip]

    # -- output handling ---------------------------------------------------
    def _emit_line(self, line):
        self.output.append(line)
        if self.on_output:
            self.on_output(line)

    def _write(self, text):
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._emit_line(line)

    def _newline(self):
        line, self._buf = self._buf, ""
        self._emit_line(line)

    def flush(self):
        if self._buf:
            self._newline()

    def _fmt(self, v):
        return format_value(v, self.style)

    def _record(self, ip, ins):
        if len(self.history) < self.history_limit:
            self.history.append(TraceEntry(self.steps, ip, str(ins),
                                           format_stack(self.stack, self.style)))
        else:
            self.history_truncated = True

    # -- execution engine --------------------------------------------------
    def run(self):
        while self.step():
            pass
        return self.output

    def step(self):
        """Execute exactly one instruction. Returns False once the VM has stopped."""
        if self.halted:
            return False
        if not (0 <= self.ip < len(self.program)):
            self.halted = True
            self.flush()
            return False
        ins = self.program[self.ip]
        exec_ip = self.ip
        self.steps += 1
        if self.steps > self.max_steps:
            self.halted = True
            self.flush()
            raise VMRuntimeError(
                f"Execution step limit ({self.max_steps}) exceeded - possible "
                f"infinite loop", ins.line)
        self.ip += 1
        handler = getattr(self, "_op_" + ins.op.lower(), None)
        if handler is None:
            self.halted = True
            raise VMRuntimeError(f"Unknown instruction '{ins.op}'", ins.line)
        try:
            handler(ins)
        except VMRuntimeError:
            self.halted = True
            self._record(exec_ip, ins)
            self.flush()
            raise
        self._record(exec_ip, ins)
        return not self.halted

    def _pop(self, ins):
        if not self.stack:
            raise VMRuntimeError("Stack underflow", ins.line)
        return self.stack.pop()

    def _pop2(self, ins):
        b = self._pop(ins)
        a = self._pop(ins)
        return a, b

    # -- instructions ------------------------------------------------------
    def _op_push(self, ins):
        self.stack.append(ins.arg)

    def _op_pop(self, ins):
        self._pop(ins)

    def _op_load(self, ins):
        if ins.arg not in self.memory:
            raise VMRuntimeError(f"Variable '{ins.arg}' has no value", ins.line)
        self.stack.append(self.memory[ins.arg])

    def _op_store(self, ins):
        self.memory[ins.arg] = self._pop(ins)

    def _op_add(self, ins):
        a, b = self._pop2(ins)
        if (_is_num(a) and _is_num(b)) or (isinstance(a, str) and isinstance(b, str)):
            self.stack.append(a + b)
        else:
            raise VMRuntimeError("Cannot add incompatible types", ins.line)

    def _numeric(self, ins, fn):
        a, b = self._pop2(ins)
        if not (_is_num(a) and _is_num(b)):
            raise VMRuntimeError(f"{ins.op} requires numeric operands", ins.line)
        self.stack.append(fn(a, b))

    def _compare(self, ins, fn):
        a, b = self._pop2(ins)
        if (_is_num(a) and _is_num(b)) or (isinstance(a, str) and isinstance(b, str)):
            self.stack.append(fn(a, b))
        else:
            raise VMRuntimeError(f"{ins.op}: cannot compare these types", ins.line)

    def _op_sub(self, ins):
        self._numeric(ins, lambda a, b: a - b)

    def _op_mul(self, ins):
        a, b = self._pop2(ins)
        if _is_num(a) and _is_num(b):
            self.stack.append(a * b)
        elif self.style == "python" and ((isinstance(a, str) and _is_int(b))
                                         or (_is_int(a) and isinstance(b, str))):
            text, count = (a, b) if isinstance(a, str) else (b, a)
            if len(text) * max(count, 0) > 1_000_000:
                raise VMRuntimeError("String repetition result is too large", ins.line)
            self.stack.append(text * count)
        else:
            raise VMRuntimeError("MUL requires numeric operands", ins.line)

    def _op_div(self, ins):
        a, b = self._pop2(ins)
        if not (_is_num(a) and _is_num(b)):
            raise VMRuntimeError("DIV requires numeric operands", ins.line)
        if b == 0:
            raise VMRuntimeError("Division by zero", ins.line)
        if isinstance(a, int) and isinstance(b, int) and a % b == 0:
            self.stack.append(a // b)
        else:
            self.stack.append(a / b)

    def _op_idiv(self, ins):                       # C/Java integer division (truncates)
        a, b = self._pop2(ins)
        if not (_is_num(a) and _is_num(b)):
            raise VMRuntimeError("IDIV requires numeric operands", ins.line)
        if b == 0:
            raise VMRuntimeError("Division by zero", ins.line)
        q = abs(int(a)) // abs(int(b))
        self.stack.append(-q if (a < 0) != (b < 0) else q)

    def _op_mod(self, ins):
        a, b = self._pop2(ins)
        if not (_is_num(a) and _is_num(b)):
            raise VMRuntimeError("MOD requires numeric operands", ins.line)
        if b == 0:
            raise VMRuntimeError("Division by zero", ins.line)
        if isinstance(a, int) and isinstance(b, int):
            r = abs(a) % abs(b)
            self.stack.append(-r if a < 0 else r)
        else:
            self.stack.append(math.fmod(a, b))

    def _op_neg(self, ins):
        a = self._pop(ins)
        if not _is_num(a):
            raise VMRuntimeError("NEG requires a numeric operand", ins.line)
        self.stack.append(-a)

    def _op_not(self, ins):
        a = self._pop(ins)
        self.stack.append(not _truthy(a))

    def _op_eq(self, ins):
        a, b = self._pop2(ins)
        self.stack.append(a == b)

    def _op_neq(self, ins):
        a, b = self._pop2(ins)
        self.stack.append(a != b)

    def _op_gt(self, ins):
        self._compare(ins, lambda a, b: a > b)

    def _op_lt(self, ins):
        self._compare(ins, lambda a, b: a < b)

    def _op_gte(self, ins):
        self._compare(ins, lambda a, b: a >= b)

    def _op_lte(self, ins):
        self._compare(ins, lambda a, b: a <= b)

    def _op_concat(self, ins):
        a, b = self._pop2(ins)
        self.stack.append(self._fmt(a) + self._fmt(b))

    def _op_tostr(self, ins):
        self.stack.append(self._fmt(self._pop(ins)))

    def _op_toint(self, ins):
        v = self._pop(ins)
        try:
            self.stack.append(int(v.strip()) if isinstance(v, str) else int(v))
        except (ValueError, OverflowError):
            raise VMRuntimeError(f"Cannot convert {v!r} to int", ins.line)

    def _op_tofloat(self, ins):
        v = self._pop(ins)
        try:
            self.stack.append(float(v.strip()) if isinstance(v, str) else float(v))
        except (ValueError, OverflowError):
            raise VMRuntimeError(f"Cannot convert {v!r} to float", ins.line)

    # ---- Python-only arithmetic / built-ins ----
    def _num2(self, ins):
        a, b = self._pop2(ins)
        if not (_is_num(a) and _is_num(b)):
            raise VMRuntimeError(f"{ins.op} requires numeric operands", ins.line)
        return a, b

    def _op_fdiv(self, ins):                       # Python '/': always a float
        a, b = self._num2(ins)
        if b == 0:
            raise VMRuntimeError("Division by zero", ins.line)
        try:
            self.stack.append(a / b)
        except OverflowError:
            raise VMRuntimeError("Numeric overflow", ins.line)

    def _op_floordiv(self, ins):                   # Python '//': floors toward -infinity
        a, b = self._num2(ins)
        if b == 0:
            raise VMRuntimeError("Division by zero", ins.line)
        self.stack.append(a // b)

    def _op_pymod(self, ins):                      # Python '%': sign follows the divisor
        a, b = self._num2(ins)
        if b == 0:
            raise VMRuntimeError("Division by zero", ins.line)
        self.stack.append(a % b)

    def _op_pow(self, ins):
        a, b = self._num2(ins)
        if _is_int(a) and _is_int(b) and b > 4096 and abs(a) > 1:
            raise VMRuntimeError("Exponent is too large", ins.line)
        try:
            r = a ** b
        except ZeroDivisionError:
            raise VMRuntimeError("Division by zero (0 cannot be raised to a negative power)", ins.line)
        except OverflowError:
            raise VMRuntimeError("Numeric overflow", ins.line)
        if isinstance(r, complex):
            raise VMRuntimeError("Complex results are not supported", ins.line)
        self.stack.append(r)

    def _op_len(self, ins):
        v = self._pop(ins)
        if not isinstance(v, str):
            raise VMRuntimeError("len() needs a string argument", ins.line)
        self.stack.append(len(v))

    def _op_abs(self, ins):
        v = self._pop(ins)
        if not _is_num(v):
            raise VMRuntimeError("abs() needs a number", ins.line)
        self.stack.append(abs(v))

    def _minmax(self, ins, pick):
        a, b = self._pop2(ins)
        if (_is_num(a) and _is_num(b)) or (isinstance(a, str) and isinstance(b, str)):
            self.stack.append(pick(a, b))
        else:
            raise VMRuntimeError(f"{ins.op.lower()}() arguments must be comparable", ins.line)

    def _op_min(self, ins):
        self._minmax(ins, min)

    def _op_max(self, ins):
        self._minmax(ins, max)

    def _op_round(self, ins):
        v = self._pop(ins)
        if not _is_num(v):
            raise VMRuntimeError("round() needs a number", ins.line)
        try:
            self.stack.append(round(v))
        except (ValueError, OverflowError):
            raise VMRuntimeError("Cannot round this value", ins.line)

    def _op_format(self, ins):
        v = self._pop(ins)
        try:
            self.stack.append(format(v, ins.arg))
        except (ValueError, TypeError):
            raise VMRuntimeError(f"Invalid format specifier '{ins.arg}' for this value", ins.line)

    def _op_jmp(self, ins):
        self.ip = ins.arg

    def _op_jmp_if_false(self, ins):
        if not _truthy(self._pop(ins)):
            self.ip = ins.arg

    def _op_jmp_if_true(self, ins):
        if _truthy(self._pop(ins)):
            self.ip = ins.arg

    def _op_dup(self, ins):
        if not self.stack:
            raise VMRuntimeError("Stack underflow", ins.line)
        self.stack.append(self.stack[-1])

    def _op_print(self, ins):
        self._write(self._fmt(self._pop(ins)))
        self._newline()

    def _op_write(self, ins):
        self._write(self._fmt(self._pop(ins)))

    def _op_newline(self, ins):
        self._newline()

    def _op_halt(self, ins):
        self.halted = True
        self.flush()
