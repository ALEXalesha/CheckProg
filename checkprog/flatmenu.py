"""Menus drawn with plain Tk widgets inside the main window.

Native Windows popup menus get a thick frame painted by the system, which
ignores the dark palette. These menus are ordinary frames placed over the
window, so the border is one pixel in the theme's color and the font is ours.
"""
import sys
import tkinter as tk

ALT_MASK = 0x20000 if sys.platform == "win32" else 0x0008


class FlatMenu:
    """Entries plus drawing; the subset of the tk.Menu API the app uses."""

    def __init__(self, system):
        self.system = system
        self.entries = []
        self.colors = {"background": "#ffffff", "foreground": "#000000",
                       "activebackground": "#0078d7", "activeforeground": "#ffffff",
                       "bordercolor": "#a0a0a0", "acceleratorforeground": "#606060",
                       "selectcolor": "#000000"}
        self.frame = None
        self._inner = None
        self._separators = []
        self.rows = {}
        self.active = None

    # ---- building ----------------------------------------------------------

    def add_command(self, label, command=None, accelerator=""):
        self.entries.append({"type": "command", "label": label, "command": command,
                             "accelerator": accelerator})

    def add_radiobutton(self, label, value, variable, command=None):
        self.entries.append({"type": "radiobutton", "label": label, "value": value,
                             "variable": variable, "command": command, "accelerator": ""})

    def add_cascade(self, label, menu):
        self.entries.append({"type": "cascade", "label": label, "menu": menu,
                             "accelerator": ""})

    def add_separator(self):
        self.entries.append({"type": "separator"})

    def index(self, what):
        if what != "end":
            raise ValueError("only index('end') is supported")
        return len(self.entries) - 1 if self.entries else None

    def type(self, index):
        return self.entries[index]["type"]

    def entrycget(self, index, option):
        return self.entries[index].get(option, "")

    def configure(self, **options):
        unknown = set(options) - set(self.colors)
        if unknown:
            raise tk.TclError(f'unknown option "-{sorted(unknown)[0]}"')
        self.colors.update(options)
        if self.frame is not None:
            self._paint()

    config = configure

    def cget(self, option):
        return self.colors[option]

    def invoke(self, index):
        entry = self.entries[index]
        if entry["type"] == "radiobutton":
            entry["variable"].set(entry["value"])
        command = entry.get("command")
        return command() if command is not None else None

    # ---- navigation ----------------------------------------------------------

    def selectable(self):
        return [i for i, e in enumerate(self.entries) if e["type"] != "separator"]

    def activate(self, index):
        if index != self.active:
            self.active = index
            if self.frame is not None:
                self._paint()

    def step(self, delta):
        choices = self.selectable()
        if not choices:
            return
        if self.active not in choices:
            self.activate(choices[0] if delta > 0 else choices[-1])
        else:
            self.activate(choices[(choices.index(self.active) + delta) % len(choices)])

    def jump(self, char):
        """Activates the next entry whose label starts with char (Windows menu habit)."""
        char = char.casefold()
        choices = [i for i in self.selectable()
                   if self.entries[i]["label"].casefold().startswith(char)]
        if not choices:
            return
        later = [i for i in choices if self.active is None or i > self.active]
        self.activate((later or choices)[0])

    # ---- drawing -------------------------------------------------------------

    def post(self, x, y, flip_x=None):
        """Shows the menu at (x, y) in root coordinates, kept inside the window.

        If it does not fit to the right of x, it is drawn ending at flip_x instead
        (a submenu then opens to the left of its parent)."""
        s = self.system
        self.unpost()
        outer = tk.Frame(s.root, borderwidth=0, highlightthickness=0)
        inner = tk.Frame(outer, borderwidth=0, highlightthickness=0, pady=s.px(4))
        inner.pack(fill="both", expand=True, padx=1, pady=1)  # the 1 px border
        self.frame, self._inner = outer, inner
        self._separators = []
        self.rows = {}
        pad_y = s.px(5)
        for r, entry in enumerate(self.entries):
            if entry["type"] == "separator":
                line = tk.Frame(inner, height=1, borderwidth=0, highlightthickness=0)
                line.grid(row=r, column=0, columnspan=4, sticky="ew",
                          padx=s.px(10), pady=s.px(4))
                self._separators.append(line)
                continue
            mark = ""
            if entry["type"] == "radiobutton" and entry["variable"].get() == entry["value"]:
                mark = "●"
            texts = (mark, entry["label"], entry["accelerator"],
                     "›" if entry["type"] == "cascade" else "")
            cells = []
            for col, (text, padx) in enumerate(zip(texts, (8, 4, 14, 8))):
                cell = tk.Label(inner, text=text, font=s.font, anchor="w", borderwidth=0,
                                highlightthickness=0, padx=s.px(padx), pady=pad_y)
                cell.grid(row=r, column=col, sticky="nsew")
                cells.append(cell)
            self.rows[r] = cells
        inner.columnconfigure(0, minsize=s.px(30))
        inner.columnconfigure(1, weight=1, minsize=s.px(110))
        self._paint()

        outer.update_idletasks()
        width, height = outer.winfo_reqwidth(), outer.winfo_reqheight()
        room_w, room_h = s.root.winfo_width(), s.root.winfo_height()
        if x + width > room_w and flip_x is not None:
            x = flip_x - width
        x = max(0, min(x, room_w - width))
        y = max(0, min(y, room_h - height))
        outer.place(x=x, y=y)
        outer.lift()
        outer.update_idletasks()
        for widget in (outer, inner, *self._separators,
                       *(c for cells in self.rows.values() for c in cells)):
            s.bind_pointer(widget)

    def unpost(self):
        if self.frame is not None:
            self.frame.destroy()
        self.frame = self._inner = None
        self._separators = []
        self.rows = {}
        self.active = None

    def _paint(self):
        c = self.colors
        self.frame.configure(background=c["bordercolor"])
        self._inner.configure(background=c["background"])
        for line in self._separators:
            line.configure(background=c["bordercolor"])
        for r, cells in self.rows.items():
            active = r == self.active
            bg = c["activebackground"] if active else c["background"]
            fg = c["activeforeground"] if active else c["foreground"]
            for col, cell in enumerate(cells):
                muted = col == 2 and not active
                cell.configure(background=bg,
                               foreground=c["acceleratorforeground"] if muted else fg)

    # Geometry in screen coordinates. Computed from Tk's own layout rather than
    # asking Windows what is under the pointer, which also works off-screen.
    def contains(self, x, y):
        f = self.frame
        if f is None:
            return False
        fx, fy = f.winfo_rootx(), f.winfo_rooty()
        return fx <= x < fx + f.winfo_width() and fy <= y < fy + f.winfo_height()

    def entry_at(self, x, y):
        if not self.contains(x, y):
            return None
        for r, cells in self.rows.items():
            top = cells[1].winfo_rooty()
            if top <= y < top + cells[1].winfo_height():
                return r
        return None


def _inside(widget, x, y):
    wx, wy = widget.winfo_rootx(), widget.winfo_rooty()
    return wx <= x < wx + widget.winfo_width() and wy <= y < wy + widget.winfo_height()


class MenuSystem:
    """The menu bar labels and the chain of open menus (menu, submenu, ...)."""

    def __init__(self, root, font, scale=1.0):
        self.root = root
        self.font = font
        self.scale = scale
        self.bar = {}
        self.chain = []
        self.bar_key = None
        self.before_open = None
        self._prev_focus = None
        self._hover = None

    def px(self, n):
        return max(1, round(n * self.scale))

    @property
    def is_open(self):
        return bool(self.chain)

    # ---- menu bar --------------------------------------------------------------

    def add_bar(self, key, label, menu):
        self.bar[key] = (label, menu)
        label.bind("<ButtonPress-1>", lambda e, k=key: self._bar_press(k))
        # While the button is held the pointer is captured by the label, so a
        # press-drag-release onto an entry arrives here.
        label.bind("<B1-Motion>", self._motion)
        label.bind("<ButtonRelease-1>", self._release)
        label.bind("<Enter>", lambda e, k=key: self._set_hover(k))
        label.bind("<Leave>", lambda e: self._set_hover(None))

    def _set_hover(self, key):
        self._hover = key
        self.paint_bar()

    def paint_bar(self):
        for key, (label, _) in self.bar.items():
            on = key == self.bar_key or (not self.chain and key == self._hover)
            label.configure(state="active" if on else "normal")

    def _bar_press(self, key):
        if self.chain and key == self.bar_key:
            self.close()
        else:
            self.open_bar(key)
        return "break"

    def open_bar(self, key, keyboard=False):
        label, menu = self.bar[key]
        self._start()
        self._post_root(menu, label.winfo_rootx() - self.root.winfo_rootx(),
                        label.winfo_rooty() + label.winfo_height() - self.root.winfo_rooty(),
                        keyboard)
        self.bar_key = key
        self.paint_bar()

    def _switch_bar(self, delta):
        keys = list(self.bar)
        self.open_bar(keys[(keys.index(self.bar_key) + delta) % len(keys)], keyboard=True)

    # ---- opening and closing ---------------------------------------------------

    def popup(self, menu, x_root, y_root, keyboard=False):
        self._start()
        # A small offset keeps the pointer off the first entry.
        self._post_root(menu, x_root - self.root.winfo_rootx() + self.px(2),
                        y_root - self.root.winfo_rooty() + self.px(2), keyboard)
        self.paint_bar()

    def _start(self):
        if self.chain:
            self._unpost_from(0)  # switching menus: keep the focus saved earlier
            self.bar_key = None
            return
        if self.before_open is not None:
            self.before_open()
        self._prev_focus = self._focus()

    def _focus(self):
        try:
            return self.root.focus_get()
        except (KeyError, tk.TclError):
            return None

    def _post_root(self, menu, x, y, keyboard):
        menu.post(x, y)
        self.chain = [menu]
        frame = menu.frame
        frame.bind("<KeyPress>", self._key)
        frame.bind("<FocusOut>", lambda e: self.root.after_idle(self._check_focus))
        frame.focus_set()
        try:
            # Every click in the window now reaches the menu, so a click on the
            # list only closes the menu instead of also ticking a checkbox.
            frame.grab_set()
        except tk.TclError:
            pass  # another grab is active; the menu still works, clicks just pass through
        if keyboard:
            menu.step(1)

    def _open_sub(self, depth, keyboard):
        menu = self.chain[depth]
        entry = menu.entries[menu.active]
        self._unpost_from(depth + 1)
        sub = entry["menu"]
        cell = menu.rows[menu.active][1]
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        fx, fw = menu.frame.winfo_rootx() - rx, menu.frame.winfo_width()
        sub.post(fx + fw - self.px(3), cell.winfo_rooty() - ry - self.px(4) - 1,
                 flip_x=fx + self.px(3))
        self.chain.append(sub)
        if keyboard:
            sub.step(1)

    def _unpost_from(self, depth):
        if depth == 0 and self.chain and self.chain[0].frame is not None:
            try:
                self.chain[0].frame.grab_release()
            except tk.TclError:
                pass
        for menu in self.chain[depth:]:
            menu.unpost()
        del self.chain[depth:]

    def close(self):
        if not self.chain:
            return
        self._unpost_from(0)
        self.bar_key = None
        self.paint_bar()
        prev, self._prev_focus = self._prev_focus, None
        try:
            if prev is not None and prev.winfo_exists():
                prev.focus_set()  # also fine while inactive: Tk restores it on activation
        except tk.TclError:
            pass

    def _check_focus(self):
        if not self.chain:
            return
        focus = self._focus()
        if focus is None or str(focus) != str(self.chain[0].frame):
            self.close()  # the user switched to another program

    def _choose(self, depth, index, keyboard):
        menu = self.chain[depth]
        if menu.entries[index]["type"] == "cascade":
            menu.activate(index)
            self._open_sub(depth, keyboard)
            return
        # Close first: the command may open a dialog or even destroy the window.
        self.close()
        menu.invoke(index)

    # ---- pointer -------------------------------------------------------------

    def bind_pointer(self, widget):
        widget.bind("<Motion>", self._motion)
        widget.bind("<ButtonPress>", self._press)
        widget.bind("<ButtonRelease-1>", self._release)
        widget.bind("<MouseWheel>", lambda e: "break")

    def _hit(self, x, y):
        for depth in range(len(self.chain) - 1, -1, -1):
            menu = self.chain[depth]
            if menu.contains(x, y):
                return "menu", depth, menu.entry_at(x, y)
        for key, (label, _) in self.bar.items():
            if _inside(label, x, y):
                return "bar", key, None
        return None, None, None

    def _motion(self, event):
        if not self.chain:
            return None
        kind, where, index = self._hit(event.x_root, event.y_root)
        if kind == "menu" and index is not None:
            menu = self.chain[where]
            entry = menu.entries[index]
            opened_here = (len(self.chain) > where + 1 and entry["type"] == "cascade"
                           and self.chain[where + 1] is entry["menu"])
            if not opened_here:
                self._unpost_from(where + 1)
            menu.activate(index)
            if entry["type"] == "cascade" and not opened_here:
                self._open_sub(where, keyboard=False)
        elif kind == "bar" and self.bar_key is not None and where != self.bar_key:
            self.open_bar(where)
        return "break"

    def _press(self, event):
        if not self.chain:
            return None
        kind, where, _ = self._hit(event.x_root, event.y_root)
        if kind == "bar":
            self._bar_press(where)
        elif kind is None:
            self.close()  # a click outside only dismisses the menu
        return "break"

    def _release(self, event):
        if not self.chain:
            return None
        kind, where, index = self._hit(event.x_root, event.y_root)
        if kind == "menu" and index is not None:
            self._choose(where, index, keyboard=False)
        return "break"

    # ---- keyboard --------------------------------------------------------------

    def _key(self, event):
        if not self.chain:
            return None
        keysym = event.keysym
        if keysym in ("Alt_L", "Alt_R", "F10"):
            self.close()
            return "break"
        if event.state & ALT_MASK:
            return None  # the app's Alt+letter handler switches to that menu
        depth = len(self.chain) - 1
        menu = self.chain[depth]
        active = menu.active
        if keysym in ("Up", "Down"):
            menu.step(-1 if keysym == "Up" else 1)
        elif keysym in ("Home", "End"):
            menu.activate(None)
            menu.step(1 if keysym == "Home" else -1)
        elif keysym in ("Return", "KP_Enter", "space"):
            if active is not None:
                self._choose(depth, active, keyboard=True)
        elif keysym == "Escape":
            if depth:
                self._unpost_from(depth)
            else:
                self.close()
        elif keysym == "Right":
            if active is not None and menu.entries[active]["type"] == "cascade":
                self._open_sub(depth, keyboard=True)
            elif self.bar_key is not None:
                self._switch_bar(1)
        elif keysym == "Left":
            if depth:
                self._unpost_from(depth)
            elif self.bar_key is not None:
                self._switch_bar(-1)
        elif event.char and event.char.isprintable() and not event.char.isspace():
            menu.jump(event.char)
        return "break"
