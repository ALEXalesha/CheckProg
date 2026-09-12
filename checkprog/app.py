import os
import sys
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from checkprog import APP_NAME, __version__, theme
from checkprog.model import Checklist, ChecklistFormatError
from checkprog.settings import load_settings, resolve_paths, save_settings

UNTITLED = "Без имени"
FILETYPES = [("Чек-листы", "*.json"), ("Все файлы", "*.*")]
# Windows virtual-key codes do not depend on the keyboard layout, so Ctrl+S
# keeps working when the Russian layout is active (keysym is then Cyrillic_*).
WIN_KEYCODES = {78: "n", 79: "o", 83: "s"}
# Alt+Ф / Alt+П / Alt+В / Alt+С: physical keys A, G, D, C in the ЙЦУКЕН layout.
WIN_ALT_KEYCODES = {65: "file", 71: "item", 68: "view", 67: "help"}
# Tk on Windows reports Alt as 0x20000; 0x0008 there means NumLock.
ALT_MASK = 0x20000 if sys.platform == "win32" else 0x0008
CONTROL_MASK = 0x0004
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
CHECK_COLUMN = "#0"
# Treeview item without the expand/collapse indicator, which would leave a gap
# before the checkbox. Layouts belong to a ttk theme, so this is reapplied on switch.
ITEM_LAYOUT = [("Treeitem.padding", {"sticky": "nswe", "children": [
    ("Treeitem.image", {"side": "left", "sticky": ""}),
    ("Treeitem.focus", {"side": "left", "sticky": "", "children": [
        ("Treeitem.text", {"side": "left", "sticky": ""})]})]})]


def _stamp_line(img, start, end, width, color):
    (x0, y0), (x1, y1) = start, end
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(int(steps) + 1):
        x = round(x0 + (x1 - x0) * i / steps - width / 2)
        y = round(y0 + (y1 - y0) * i / steps - width / 2)
        img.put(color, to=(x, y, x + width, y + width))


def make_checkbox_image(master, size, checked, palette):
    img = tk.PhotoImage(master=master, width=size, height=size)
    border = max(1, size // 10)
    img.put(palette.accent if checked else palette.check_off_border, to=(0, 0, size, size))
    img.put(palette.accent if checked else palette.check_off_fill,
            to=(border, border, size - border, size - border))
    for x, y in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
        img.transparency_set(x, y, True)
    if checked:
        pen = max(2, round(size / 7))
        a, b, c = (size * 0.24, size * 0.52), (size * 0.43, size * 0.71), (size * 0.77, size * 0.31)
        _stamp_line(img, a, b, pen, "#ffffff")
        _stamp_line(img, b, c, pen, "#ffffff")
    return img


class _Editor:
    def __init__(self, entry, index):
        self.entry = entry
        self.index = index


class App:
    def __init__(self, root, paths, initial_path=None):
        self.root = root
        self.paths = paths
        self.settings = load_settings(paths.settings_file)
        self.checklist = Checklist()
        self.editor = None
        self._drag = None
        self.theme_mode = theme.normalize_mode(self.settings.get("theme"))
        self.theme = None
        self.theme_var = tk.StringVar(master=root, value=self.theme_mode)
        self._build_ui()
        self._bind_events()
        root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.apply_theme()
        if initial_path:
            self.open_path(initial_path)
        else:
            last = self.settings.get("last_file")
            if isinstance(last, str) and last and not self.open_path(last, quiet_missing=True):
                self.settings.pop("last_file", None)
                save_settings(self.paths.settings_file, self.settings)

    # ---- UI construction -------------------------------------------------

    def _build_ui(self):
        root = self.root
        scale = root.winfo_fpixels("1i") / 96.0
        width = min(round(520 * scale), int(root.winfo_screenwidth() * 0.9))
        height = min(round(620 * scale), int(root.winfo_screenheight() * 0.85))
        root.geometry(f"{width}x{height}")
        root.minsize(min(round(340 * scale), width), min(round(320 * scale), height))
        if os.path.isfile(ICON_PATH):
            try:
                root.iconbitmap(default=ICON_PATH)
            except tk.TclError:
                pass

        base_font = tkfont.nametofont("TkDefaultFont")
        linespace = base_font.metrics("linespace")
        # Keep a reference: Tk deletes the named font when the Python object is collected.
        self._done_font = base_font.copy()
        self._done_font.configure(overstrike=1)
        self._box = max(12, linespace - 2)
        # ttk rows have a fixed pixel height; derive it from the font so text is not
        # clipped at 125-200% display scaling.
        self._row_height = max(linespace, self._box) + round(8 * scale)

        self._build_menu(scale)

        top = ttk.Frame(root, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        self.progress_label = ttk.Label(top)
        self.progress_label.pack(anchor="w")
        self.progress_bar = ttk.Progressbar(top, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(4, 0))

        bottom = ttk.Frame(root, padding=(10, 4, 10, 10))
        bottom.pack(side="bottom", fill="x")
        add_row = ttk.Frame(bottom)
        add_row.pack(fill="x")
        self.entry = ttk.Entry(add_row)
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(add_row, text="Добавить", command=self.add_item).pack(side="left", padx=(6, 0))
        self.hint = ttk.Label(
            bottom,
            text="Щелчок по квадратику: отметить  •  двойной щелчок: изменить  •  "
                 "Delete: удалить  •  перетащите строку, чтобы переставить")
        self.hint.pack(fill="x", pady=(6, 0))
        self.hint.bind("<Configure>",
                       lambda e: self.hint.configure(wraplength=max(e.width, 50)))

        middle = ttk.Frame(root, padding=(10, 4))
        middle.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(middle, columns=("text",), show="tree headings",
                                 selectmode="browse")
        self.tree.heading(CHECK_COLUMN, text="✓")
        self.tree.heading("text", text="Пункт", anchor="w")
        check_width = self._box + round(20 * scale)
        self.tree.column(CHECK_COLUMN, width=check_width, minwidth=check_width, stretch=False)
        self.tree.column("text", anchor="w", stretch=True)
        scrollbar = ttk.Scrollbar(middle, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        self.item_menu = self._new_menu(root)
        self._fill_item_menu(self.item_menu)
        self.entry.focus_set()

    def _new_menu(self, parent):
        menu = tk.Menu(parent, tearoff=0)
        self.menus.append(menu)
        return menu

    def _build_menu(self, scale):
        # A native Windows menu bar ignores colors, so the bar is drawn with
        # Menubuttons; their drop-down menus do follow the palette.
        self.menu_bar = tk.Frame(self.root, borderwidth=0, highlightthickness=0)
        self.menu_bar.pack(side="top", fill="x")
        self.menu_buttons = {}
        self.menus = []

        def add(key, label):
            button = tk.Menubutton(self.menu_bar, text=label, underline=0, relief="flat",
                                   borderwidth=0, highlightthickness=0,
                                   padx=round(8 * scale), pady=round(3 * scale))
            menu = self._new_menu(button)
            button.configure(menu=menu)
            button.pack(side="left")
            self.menu_buttons[key] = button
            return menu

        file_menu = add("file", "Файл")
        file_menu.add_command(label="Создать", accelerator="Ctrl+N", command=self.new_file)
        file_menu.add_command(label="Открыть…", accelerator="Ctrl+O", command=self.open_file)
        file_menu.add_command(label="Сохранить", accelerator="Ctrl+S", command=self.save)
        file_menu.add_command(label="Сохранить как…", accelerator="Ctrl+Shift+S",
                              command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", accelerator="Alt+F4", command=self.on_exit)

        self._fill_item_menu(add("item", "Пункт"))

        view_menu = add("view", "Вид")
        theme_menu = self._new_menu(view_menu)
        for mode in theme.MODES:
            theme_menu.add_radiobutton(label=theme.MODE_LABELS[mode], value=mode,
                                       variable=self.theme_var,
                                       command=lambda m=mode: self.set_theme_mode(m))
        view_menu.add_cascade(label="Тема", menu=theme_menu)

        help_menu = add("help", "Справка")
        help_menu.add_command(label="О программе", command=self.show_about)

    def _fill_item_menu(self, menu):
        menu.add_command(label="Отметить / снять отметку", accelerator="Пробел",
                         command=self.toggle_selected)
        menu.add_command(label="Изменить", accelerator="F2", command=self.edit_selected)
        menu.add_command(label="Удалить", accelerator="Delete", command=self.delete_selected)
        menu.add_separator()
        menu.add_command(label="Выше", accelerator="Ctrl+↑",
                         command=lambda: self.move_selected(-1))
        menu.add_command(label="Ниже", accelerator="Ctrl+↓",
                         command=lambda: self.move_selected(1))

    def _bind_events(self):
        tree = self.tree
        tree.bind("<ButtonPress-1>", self._on_press)
        tree.bind("<B1-Motion>", self._on_motion)
        tree.bind("<ButtonRelease-1>", lambda e: self.drag_end())
        tree.bind("<Double-Button-1>", self._on_double)
        tree.bind("<Button-3>", self._on_right_click)
        tree.bind("<space>", lambda e: self._key(self.toggle_selected))
        tree.bind("<Delete>", lambda e: self._key(self.delete_selected))
        tree.bind("<F2>", lambda e: self._key(self.edit_selected))
        tree.bind("<Control-Up>", lambda e: self._key(lambda: self.move_selected(-1)))
        tree.bind("<Control-Down>", lambda e: self._key(lambda: self.move_selected(1)))
        # The inline editor is placed in tree pixels; scrolling or resizing would
        # leave it over the wrong row, so finish the edit first.
        tree.bind("<MouseWheel>", lambda e: self.end_edit(True))
        tree.bind("<Configure>", lambda e: self.end_edit(True))
        self.entry.bind("<Return>", lambda e: self._key(self.add_item))
        self.entry.bind("<KP_Enter>", lambda e: self._key(self.add_item))
        self.root.bind("<Control-KeyPress>", self.on_ctrl_key)
        self.root.bind("<Alt-KeyPress>", self.on_alt_key)
        self.root.bind("<F10>", self.on_f10)
        self.root.bind("<FocusIn>", self.on_focus_in, add="+")
        self.root.bind("<Map>", self._on_map, add="+")

    @staticmethod
    def _key(action):
        action()
        return "break"

    # ---- theme -------------------------------------------------------------

    def set_theme_mode(self, mode):
        self.theme_mode = theme.normalize_mode(mode)
        self.settings["theme"] = self.theme_mode
        save_settings(self.paths.settings_file, self.settings)
        self.apply_theme()

    def apply_theme(self):
        self.theme = theme.resolve(self.theme_mode, theme.system_prefers_dark())
        palette = theme.palette_for(self.theme)
        style = ttk.Style(self.root)
        ttk_theme = palette.ttk_theme if palette.ttk_theme in style.theme_names() else "clam"
        if style.theme_use() != ttk_theme:
            style.theme_use(ttk_theme)
        if self.theme == "dark":
            self._style_dark(style, palette)
        style.configure("Treeview", rowheight=self._row_height)
        style.layout("Treeview.Item", ITEM_LAYOUT)

        self.root.configure(background=palette.bg)
        self.menu_bar.configure(background=palette.menu_bar_bg)
        for button in self.menu_buttons.values():
            button.configure(background=palette.menu_bar_bg, foreground=palette.fg,
                             activebackground=palette.menu_active_bg,
                             activeforeground=palette.menu_active_fg)
        for menu in self.menus:
            menu.configure(background=palette.menu_bg, foreground=palette.menu_fg,
                           activebackground=palette.menu_active_bg,
                           activeforeground=palette.menu_active_fg,
                           selectcolor=palette.menu_fg)
        self.hint.configure(foreground=palette.muted)
        self.tree.tag_configure("done", foreground=palette.done_fg, font=self._done_font)

        # Hold the old images until refresh() has pointed every row at the new ones:
        # dropping the last reference deletes the Tk image immediately.
        old_images = (getattr(self, "img_on", None), getattr(self, "img_off", None))
        self.img_on = make_checkbox_image(self.root, self._box, True, palette)
        self.img_off = make_checkbox_image(self.root, self._box, False, palette)
        self.theme_var.set(self.theme_mode)
        theme.set_title_bar_dark(self.root, self.theme == "dark")
        self.refresh()
        del old_images

    @staticmethod
    def _style_dark(style, p):
        style.configure(".", background=p.bg, foreground=p.fg, fieldbackground=p.field,
                        bordercolor=p.border, lightcolor=p.bg, darkcolor=p.bg,
                        troughcolor=p.field, selectbackground=p.select_bg,
                        selectforeground=p.select_fg, insertcolor=p.fg, arrowcolor=p.fg,
                        focuscolor=p.select_bg)
        style.configure("Treeview", background=p.field, fieldbackground=p.field,
                        foreground=p.fg, bordercolor=p.border)
        style.map("Treeview", background=[("selected", p.select_bg)],
                  foreground=[("selected", p.select_fg)])
        style.configure("Treeview.Heading", background=p.heading_bg, foreground=p.fg,
                        bordercolor=p.border, lightcolor=p.heading_bg, darkcolor=p.heading_bg)
        style.map("Treeview.Heading", background=[("active", p.border)])
        style.configure("TEntry", fieldbackground=p.field, foreground=p.fg, insertcolor=p.fg,
                        bordercolor=p.border, lightcolor=p.field, darkcolor=p.field)
        style.map("TEntry", bordercolor=[("focus", p.select_bg)],
                  lightcolor=[("focus", p.select_bg)])
        style.configure("TButton", background=p.field, foreground=p.fg, bordercolor=p.border,
                        lightcolor=p.field, darkcolor=p.field)
        style.map("TButton", background=[("pressed", p.bg), ("active", p.border)])
        style.configure("Horizontal.TProgressbar", background=p.accent, troughcolor=p.field,
                        bordercolor=p.border, lightcolor=p.accent, darkcolor=p.accent)
        style.configure("Vertical.TScrollbar", background=p.field, troughcolor=p.bg,
                        bordercolor=p.bg, arrowcolor=p.muted, lightcolor=p.field,
                        darkcolor=p.field)
        style.map("Vertical.TScrollbar", background=[("active", p.border)])

    def on_focus_in(self, event):
        if self.theme_mode != "system":
            return
        if theme.resolve("system", theme.system_prefers_dark()) != self.theme:
            self.apply_theme()

    def _on_map(self, event):
        # Before the first map the window has no frame to recolor.
        if str(event.widget) == str(self.root):
            theme.set_title_bar_dark(self.root, self.theme == "dark")

    # ---- rendering -------------------------------------------------------

    def refresh(self, select=None):
        tree = self.tree
        items = self.checklist.items
        # Row iids are always "0".."n-1" in order; rows are updated in place so the
        # scroll position survives a toggle.
        existing = tree.get_children()
        if len(existing) > len(items):
            tree.delete(*existing[len(items):])
        for i, item in enumerate(items):
            iid = str(i)
            options = {
                "image": self.img_on if item.done else self.img_off,
                "values": (item.text,),
                "tags": ("done",) if item.done else (),
            }
            if tree.exists(iid):
                tree.item(iid, **options)
            else:
                tree.insert("", "end", iid=iid, **options)
        if select is not None:
            self.select(select)

        cl = self.checklist
        self.progress_label.configure(text=f"Выполнено: {cl.done_count} из {cl.total}")
        self.progress_bar.configure(maximum=max(cl.total, 1), value=cl.done_count)
        name = os.path.basename(cl.path) if cl.path else UNTITLED
        self.root.title(f"{'*' if cl.dirty else ''}{name} - {APP_NAME}")

    def select(self, index):
        iid = str(index)
        if not self.tree.exists(iid):
            return
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)

    def selected_index(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    # ---- item operations -------------------------------------------------

    def add_item(self):
        self.end_edit(True)
        index = self.checklist.add(self.entry.get())
        if index is None:
            return
        self.entry.delete(0, "end")
        self.refresh(select=index)

    def toggle_index(self, index):
        self.end_edit(True)
        if 0 <= index < len(self.checklist):
            self.checklist.toggle(index)
            self.refresh()

    def toggle_selected(self):
        index = self.selected_index()
        if index is not None:
            self.toggle_index(index)

    def delete_selected(self):
        self.end_edit(True)
        index = self.selected_index()
        if index is None:
            return
        self.checklist.remove(index)
        remaining = len(self.checklist)
        self.refresh(select=min(index, remaining - 1) if remaining else None)

    def move_selected(self, delta):
        self.end_edit(True)
        index = self.selected_index()
        if index is None:
            return
        target = index + delta
        if 0 <= target < len(self.checklist):
            self.refresh(select=self.checklist.move(index, target))

    def drag_start(self, index):
        self.end_edit(True)
        self._drag = index if 0 <= index < len(self.checklist) else None

    def drag_to(self, index):
        if self._drag is None:
            return
        if not 0 <= self._drag < len(self.checklist):
            self._drag = None
            return
        if index != self._drag:
            self._drag = self.checklist.move(self._drag, index)
            self.refresh(select=self._drag)

    def drag_end(self):
        self._drag = None

    # ---- inline editing ---------------------------------------------------

    def edit_selected(self):
        index = self.selected_index()
        if index is not None:
            self.begin_edit(index)

    def begin_edit(self, index):
        self.end_edit(True)
        if not 0 <= index < len(self.checklist):
            return
        iid = str(index)
        self.select(index)
        self.tree.update_idletasks()
        entry = ttk.Entry(self.tree)
        entry.insert(0, self.checklist.items[index].text)
        entry.select_range(0, "end")
        bbox = self.tree.bbox(iid, "text")
        if bbox:
            x, y, width, height = bbox
            entry.place(x=x, y=y, width=width, height=height)
        else:
            entry.place(x=0, y=0, relwidth=1)
        entry.bind("<Return>", lambda e: self._finish_edit(True))
        entry.bind("<KP_Enter>", lambda e: self._finish_edit(True))
        entry.bind("<Escape>", lambda e: self._finish_edit(False))
        entry.bind("<FocusOut>", lambda e: self.end_edit(True))
        self.editor = _Editor(entry, index)
        entry.focus_set()

    def _finish_edit(self, commit):
        self.end_edit(commit)
        self.tree.focus_set()
        return "break"

    def end_edit(self, commit=True):
        editor = self.editor
        if editor is None:
            return
        # Clear first: destroying a focused entry fires <FocusOut> re-entrantly.
        self.editor = None
        text = editor.entry.get()
        editor.entry.destroy()
        if commit and 0 <= editor.index < len(self.checklist):
            self.checklist.rename(editor.index, text)
        # No select= here: the edit may be finishing because the user acted on a
        # different row, and moving the selection back would redirect that action.
        self.refresh()

    # ---- mouse --------------------------------------------------------------

    def _row_under(self, event):
        if self.tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return None
        row = self.tree.identify_row(event.y)
        return int(row) if row else None

    def _on_press(self, event):
        index = self._row_under(event)
        if index is None:
            return None
        if self.tree.identify_column(event.x) == CHECK_COLUMN:
            self.toggle_index(index)
            self.select(index)
            self.tree.focus_set()
            return "break"
        self.drag_start(index)
        return None

    def _on_motion(self, event):
        if self._drag is None:
            return None
        height = self.tree.winfo_height()
        if event.y < 0:
            self.tree.yview_scroll(-1, "units")
        elif event.y > height:
            self.tree.yview_scroll(1, "units")
        target = self._row_at_y(event.y)
        if target is not None:
            self.drag_to(target)
        return "break"

    def _row_at_y(self, y):
        row = self.tree.identify_row(y)
        if row:
            return int(row)
        visible = [iid for iid in self.tree.get_children() if self.tree.bbox(iid)]
        if not visible:
            return None
        first_top = self.tree.bbox(visible[0])[1]
        return int(visible[0]) if y < first_top else int(visible[-1])

    def _on_double(self, event):
        index = self._row_under(event)
        if index is None:
            return None
        if self.tree.identify_column(event.x) == CHECK_COLUMN:
            # The second click of a double click lands here instead of <ButtonPress-1>.
            self.toggle_index(index)
            self.select(index)
        else:
            self.begin_edit(index)
        return "break"

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.end_edit(True)
        self.select(int(row))
        try:
            self.item_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.item_menu.grab_release()

    # ---- keyboard ------------------------------------------------------------

    def on_ctrl_key(self, event):
        if event.state & ALT_MASK:
            return None  # Ctrl+Alt is AltGr on many layouts: it types characters.
        if sys.platform == "win32":
            key = WIN_KEYCODES.get(event.keycode)
        else:
            key = event.keysym.lower() if len(event.keysym) == 1 else None
        shift = bool(event.state & 0x1)
        actions = {
            ("n", False): self.new_file,
            ("o", False): self.open_file,
            ("s", False): self.save,
            ("s", True): self.save_as,
        }
        action = actions.get((key, shift))
        if action is None:
            return None
        action()
        return "break"

    def on_alt_key(self, event):
        if event.state & CONTROL_MASK or sys.platform != "win32":
            return None  # AltGr (Ctrl+Alt) types characters such as ą or @.
        key = WIN_ALT_KEYCODES.get(event.keycode)
        if key is None:
            return None  # leaves Alt+F4 and friends to Windows
        self.open_menu(key)
        return "break"

    def on_f10(self, event):
        self.open_menu("file")
        return "break"

    def open_menu(self, key):
        self.end_edit(True)
        self.menu_buttons[key].event_generate("<<Invoke>>")

    # ---- files ---------------------------------------------------------------

    def _confirm_discard(self):
        self.end_edit(True)
        if not self.checklist.dirty:
            return True
        name = os.path.basename(self.checklist.path) if self.checklist.path else UNTITLED
        answer = messagebox.askyesnocancel(
            APP_NAME, f"Сохранить изменения в «{name}»?", parent=self.root)
        if answer is None:
            return False
        if answer:
            return self.save()
        return True

    def new_file(self):
        if not self._confirm_discard():
            return
        self._drag = None
        self.checklist = Checklist()
        self.refresh()

    def open_file(self):
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            parent=self.root, title="Открыть список", filetypes=FILETYPES,
            initialdir=self._initial_dir())
        if path:
            self.open_path(path)

    def open_path(self, path, quiet_missing=False):
        try:
            checklist = Checklist.load(path)
        except FileNotFoundError:
            if not quiet_missing:
                self._error(f"Файл не найден:\n{path}")
            return False
        except ChecklistFormatError as e:
            self._error(f"Не удалось открыть файл:\n{path}\n\n{e}")
            return False
        except OSError as e:
            self._error(f"Не удалось открыть файл:\n{path}\n\n{e.strerror or e}")
            return False
        self.end_edit(False)
        self._drag = None
        self.checklist = checklist
        self._remember(checklist.path)
        self.refresh(select=0 if len(checklist) else None)
        return True

    def save(self):
        self.end_edit(True)
        if self.checklist.path:
            return self._save_to(self.checklist.path)
        return self.save_as()

    def save_as(self):
        self.end_edit(True)
        current = self.checklist.path
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Сохранить список", filetypes=FILETYPES,
            defaultextension=".json", initialdir=self._initial_dir(),
            initialfile=os.path.basename(current) if current else "Новый список.json")
        if not path:
            return False
        return self._save_to(path)

    def _save_to(self, path):
        try:
            self.checklist.save(path)
        except OSError as e:
            self._error(f"Не удалось сохранить файл:\n{path}\n\n{e.strerror or e}")
            return False
        self._remember(self.checklist.path)
        self.refresh()
        return True

    def _initial_dir(self):
        if self.checklist.path:
            return os.path.dirname(self.checklist.path)
        try:
            os.makedirs(self.paths.lists_dir, exist_ok=True)
        except OSError:
            return None
        return self.paths.lists_dir

    def _remember(self, path):
        self.settings["last_file"] = path
        save_settings(self.paths.settings_file, self.settings)

    def _error(self, text):
        messagebox.showerror(APP_NAME, text, parent=self.root)

    def show_about(self):
        mode = "portable" if self.paths.portable else "установленная версия"
        messagebox.showinfo(
            f"О программе {APP_NAME}",
            f"{APP_NAME} {__version__}\n"
            "Чек-лист: впишите пункты и отмечайте выполненные.\n\n"
            f"Режим: {mode}\n"
            f"Тема: {theme.MODE_LABELS[self.theme_mode]}\n"
            f"Настройки: {self.paths.settings_file}\n"
            f"Папка списков: {self.paths.lists_dir}",
            parent=self.root)

    def on_exit(self):
        if self._confirm_discard():
            self.root.destroy()


def _report_error(exc, value, tb):
    # A --windowed build has no stderr, so Tk's default handler would hide errors.
    details = "".join(traceback.format_exception(exc, value, tb))
    try:
        messagebox.showerror(APP_NAME, f"Непредвиденная ошибка: {value}\n\n{details[-1500:]}")
    except tk.TclError:
        pass


def _enable_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    _enable_dpi_awareness()
    root = tk.Tk()
    root.report_callback_exception = _report_error
    App(root, resolve_paths(), args[0] if args else None)
    root.mainloop()
