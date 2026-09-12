import os
import sys
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from checkprog import APP_NAME, __version__
from checkprog.model import Checklist, ChecklistFormatError
from checkprog.settings import load_settings, resolve_paths, save_settings

CHECK_ON = "☑"
CHECK_OFF = "☐"
UNTITLED = "Без имени"
FILETYPES = [("Чек-листы", "*.json"), ("Все файлы", "*.*")]
# Windows virtual-key codes do not depend on the keyboard layout, so Ctrl+S
# keeps working when the Russian layout is active (keysym is then Cyrillic_*).
WIN_KEYCODES = {78: "n", 79: "o", 83: "s"}
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")


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
        self._build_ui()
        self._bind_events()
        root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.refresh()
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
        root.geometry(f"{round(520 * scale)}x{round(620 * scale)}")
        root.minsize(round(340 * scale), round(320 * scale))
        if os.path.isfile(ICON_PATH):
            try:
                root.iconbitmap(default=ICON_PATH)
            except tk.TclError:
                pass

        base_font = tkfont.nametofont("TkDefaultFont")
        # Keep a reference: Tk deletes the named font when the Python object is collected.
        self._done_font = base_font.copy()
        self._done_font.configure(overstrike=1)
        # ttk rows have a fixed pixel height; derive it from the font so text is not
        # clipped at 125-200% display scaling.
        ttk.Style(root).configure(
            "Treeview", rowheight=base_font.metrics("linespace") + round(8 * scale))

        self._build_menu()

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
        hint = ttk.Label(
            bottom, foreground="gray40",
            text="Щелчок по ☐: отметить  •  двойной щелчок: изменить  •  "
                 "Delete: удалить  •  перетащите строку, чтобы переставить")
        hint.pack(fill="x", pady=(6, 0))
        hint.bind("<Configure>", lambda e: hint.configure(wraplength=max(e.width, 50)))

        middle = ttk.Frame(root, padding=(10, 4))
        middle.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(middle, columns=("done", "text"), show="headings",
                                 selectmode="browse")
        self.tree.heading("done", text="✓")
        self.tree.heading("text", text="Пункт", anchor="w")
        check_width = base_font.measure(CHECK_ON * 2) + round(16 * scale)
        self.tree.column("done", width=check_width, minwidth=check_width,
                         stretch=False, anchor="center")
        self.tree.column("text", anchor="w", stretch=True)
        self.tree.tag_configure("done", foreground="gray50", font=self._done_font)
        scrollbar = ttk.Scrollbar(middle, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        self.item_menu = tk.Menu(root, tearoff=0)
        self._fill_item_menu(self.item_menu)
        self.entry.focus_set()

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Создать", accelerator="Ctrl+N", command=self.new_file)
        file_menu.add_command(label="Открыть…", accelerator="Ctrl+O", command=self.open_file)
        file_menu.add_command(label="Сохранить", accelerator="Ctrl+S", command=self.save)
        file_menu.add_command(label="Сохранить как…", accelerator="Ctrl+Shift+S",
                              command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", accelerator="Alt+F4", command=self.on_exit)
        menubar.add_cascade(label="Файл", menu=file_menu)

        item_menu = tk.Menu(menubar, tearoff=0)
        self._fill_item_menu(item_menu)
        menubar.add_cascade(label="Пункт", menu=item_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self.show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)
        self.root.configure(menu=menubar)

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

    @staticmethod
    def _key(action):
        action()
        return "break"

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
            values = (CHECK_ON if item.done else CHECK_OFF, item.text)
            tags = ("done",) if item.done else ()
            if tree.exists(iid):
                tree.item(iid, values=values, tags=tags)
            else:
                tree.insert("", "end", iid=iid, values=values, tags=tags)
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
        if self.tree.identify_column(event.x) == "#1":
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
        if self.tree.identify_column(event.x) == "#1":
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

    # ---- files ---------------------------------------------------------------

    def on_ctrl_key(self, event):
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
