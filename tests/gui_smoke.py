"""Opens the real Tk GUI (needs a display, e.g. xvfb-run) and drives every example
through the Compile / Execute / Step handlers. Exits non-zero on any failure."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from minilang import gui  # noqa: E402

app = gui.MiniLangApp()


def pump(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.update()
        time.sleep(0.01)


pump(300)
count = 0
for key in ("minilang", "python", "cpp", "java"):
    spec = gui.LANGUAGES[key]
    app.lang_var.set(spec.name)
    app.on_language()
    folder = os.path.join(gui.EXAMPLES_ROOT, spec.examples_dir)
    for name in sorted(os.listdir(folder)):
        app._load(os.path.join(folder, name))
        app.on_compile()
        if app.result.ok:
            app.on_execute()
            app.on_reset_vm()
            for _ in range(8):
                app.on_step()
            assert app.mem_tree.get_children(), f"variables table empty for {key}/{name}"
            app.on_reset_vm()
        count += 1

# the Variables & Values table shows the final values after a full run
app.lang_var.set("Python")
app.on_language()
app._load(os.path.join(gui.EXAMPLES_ROOT, "python", "loops.py"))
app.on_compile()
app.on_execute()
rows = [app.mem_tree.item(i, "values") for i in app.mem_tree.get_children()]
assert any(r[0] == "n" and r[1] == "3" for r in rows), rows
assert not any(str(r[0]).startswith("$") for r in rows), rows
app.destroy()
print(f"GUI smoke test OK: {count} examples driven through the real window")
