"""Main window: the list, the note panel, the add row, menus, files and keys."""
import os
import sys

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListView,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QStyle,
    QStyleOptionViewItem, QVBoxLayout, QWidget)

from checkprog import APP_NAME, __version__, theme
from checkprog.delegate import ItemDelegate
from checkprog.listmodel import ChecklistModel, NoteRole
from checkprog.model import Checklist, ChecklistFormatError, clean_note
from checkprog.settings import load_settings, save_settings

UNTITLED = "Без имени"
FILE_FILTER = "Списки CheckProg (*.json);;Все файлы (*.*)"
VIEW_THEME_LABELS = {"system": "Тема как в системе", "light": "Светлая тема",
                     "dark": "Тёмная тема"}

# Windows virtual-key codes of the Latin letters: they identify a key whatever
# the keyboard layout, so Ctrl+С in the Russian layout is still Ctrl+C.
VK_LETTERS = {code: chr(code) for code in range(0x41, 0x5B)}
# Alt + the key with Ф/П/В/С printed on it (A/G/D/C) opens a menu in any layout.
ALT_MENU_KEYS = {0x41: "file", 0x47: "item", 0x44: "view", 0x43: "help"}

HELP_TEXT = (
    "Добавить пункт: впишите текст в нижнее поле и нажмите Enter.\n"
    "Отметить: щелчок по квадратику или пробел.\n"
    "Изменить текст: двойной щелчок или F2 (Enter сохраняет, Esc отменяет).\n"
    "Комментарий: выделите пункт и пишите в поле под списком.\n"
    "Показать комментарий в списке: щелчок по ▼ справа, → раскрывает, ← сворачивает.\n"
    "Снять выделение: повторный щелчок по пункту, щелчок по пустому месту или Esc.\n"
    "Удалить: Delete. Переставить: перетащите строку или Ctrl+↑ / Ctrl+↓.\n"
    "Меню действий с пунктом: правая кнопка мыши, Shift+F10 или клавиша меню.\n\n"
    "Ctrl+N новый, Ctrl+O открыть, Ctrl+S сохранить, Ctrl+Shift+S сохранить как.\n"
    "Сочетания работают в русской и в английской раскладке.")


class ChecklistView(QListView):
    """List view whose clicks are routed by the delegate's hit zones."""
    check_clicked = Signal(int)
    arrow_clicked = Signal(int)
    note_double_clicked = Signal(int)
    text_double_clicked = Signal(int)
    deselect_requested = Signal()
    expand_requested = Signal(bool)
    menu_requested = Signal(int, QPoint)  # row, global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toggle_off_on_release = None
        self._press_pos = None
        self.key_actions = {}  # (key, modifiers) -> callable, filled by the window
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(False)
        self.setMouseTracking(False)

    def option_for(self, index):
        opt = QStyleOptionViewItem()
        self.initViewItemOption(opt)
        opt.rect = self.visualRect(index)
        return opt

    def zone_at(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return None, None
        return index, self.itemDelegate().hit(self.option_for(index), index, pos)

    def mousePressEvent(self, event):
        self._toggle_off_on_release = None
        self._press_pos = event.position().toPoint()
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        index, zone = self.zone_at(self._press_pos)
        if index is None:
            self.setFocus()
            self.deselect_requested.emit()
            return
        if zone == "check":
            self.setFocus()
            self.check_clicked.emit(index.row())
            return
        if zone == "arrow":
            self.setFocus()
            self.arrow_clicked.emit(index.row())
            return
        # Pressing an already selected row may still start a drag; decided on release.
        if self.selectionModel().isSelected(index):
            self._toggle_off_on_release = index.row()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._press_pos is not None and (event.position().toPoint() - self._press_pos)
                .manhattanLength() >= QApplication.startDragDistance()):
            self._toggle_off_on_release = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        row, self._toggle_off_on_release = self._toggle_off_on_release, None
        if row is not None and event.button() == Qt.LeftButton:
            index, _ = self.zone_at(event.position().toPoint())
            if index is not None and index.row() == row:
                self.deselect_requested.emit()

    def mouseDoubleClickEvent(self, event):
        self._toggle_off_on_release = None
        if event.button() != Qt.LeftButton:
            return
        index, zone = self.zone_at(event.position().toPoint())
        if index is None:
            return
        # The second click of a double click arrives here instead of a press:
        # on the box and the arrow it counts as a second click.
        if zone == "check":
            self.check_clicked.emit(index.row())
        elif zone == "arrow":
            self.arrow_clicked.emit(index.row())
        elif zone == "note":
            self.note_double_clicked.emit(index.row())
        else:
            self.text_double_clicked.emit(index.row())

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers() & ~Qt.KeypadModifier
        action = self.key_actions.get((key, mods))
        if action is not None:
            action()
            return
        if mods == Qt.NoModifier and key == Qt.Key_Escape:
            self.deselect_requested.emit()
            return
        if mods == Qt.NoModifier and key in (Qt.Key_Left, Qt.Key_Right):
            self.expand_requested.emit(key == Qt.Key_Right)
            return
        if mods == Qt.ShiftModifier and key == Qt.Key_F10:
            self._keyboard_menu()
            return
        super().keyPressEvent(event)

    def _keyboard_menu(self):
        index = self.currentIndex()
        if not index.isValid() or not self.selectionModel().isSelected(index):
            return
        rect = self.visualRect(index)
        self.menu_requested.emit(
            index.row(), self.viewport().mapToGlobal(QPoint(rect.left() + 20, rect.bottom())))

    def contextMenuEvent(self, event):
        if event.reason() == event.Reason.Keyboard:
            self._keyboard_menu()
            return
        index = self.indexAt(self.viewport().mapFromGlobal(event.globalPos()))
        if index.isValid():
            self.menu_requested.emit(index.row(), event.globalPos())


class LayoutKeys(QObject):
    """Makes Ctrl+letter and Alt+menu keys work in any keyboard layout.

    Qt already matches most shortcuts by the physical key; whatever it lets
    through with a non-Latin key is re-sent here as the Latin key.
    """

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress or not isinstance(event, QKeyEvent):
            return False
        win = self.window
        if not win.isActiveWindow() and not win.testAttribute(Qt.WA_DontShowOnScreen):
            return False
        mods = event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier)
        vk = event.nativeVirtualKey()
        letter = VK_LETTERS.get(vk)
        latin = Qt.Key_A <= event.key() <= Qt.Key_Z
        if mods & Qt.ControlModifier and mods & Qt.AltModifier:
            return False  # AltGr types characters (@, €, ą ...)
        if mods & Qt.ControlModifier and letter and not latin:
            action = win.ctrl_action(letter, bool(mods & Qt.ShiftModifier))
            if action is not None:
                action.trigger()
                return True
            if isinstance(obj, (QLineEdit, QPlainTextEdit)):
                QApplication.sendEvent(obj, QKeyEvent(
                    QEvent.KeyPress, getattr(Qt, f"Key_{letter}"), event.modifiers(),
                    event.nativeScanCode(), vk, event.nativeModifiers(), ""))
                return True
            return False
        if mods == Qt.AltModifier and vk in ALT_MENU_KEYS and not self._mnemonic_match(event):
            win.open_menu(ALT_MENU_KEYS[vk])
            return True
        return False

    def _mnemonic_match(self, event):
        text = event.text().lower()
        return bool(text) and any(m.title().lower().startswith("&" + text)
                                  for m in self.window.bar_menus.values())


class MainWindow(QMainWindow):
    def __init__(self, paths, initial_path=None):
        super().__init__()
        self.paths = paths
        self.settings = load_settings(paths.settings_file)
        self.theme_mode = theme.normalize_mode(self.settings.get("theme"))
        self.model = ChecklistModel(parent=self)
        self._note_index = QPersistentModelIndex()
        self._loading_note = False
        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._connect()
        self._keys = LayoutKeys(self)
        QApplication.instance().installEventFilter(self._keys)
        theme.apply_mode(QApplication.instance(), self.theme_mode)
        self.setMinimumSize(340, 360)
        self.resize(560, 660)
        self._refresh_status()
        self._sync_note_panel()
        self._update_item_actions()
        if initial_path:
            self.open_path(initial_path)
        else:
            last = self.settings.get("last_file")
            if isinstance(last, str) and last and not self.open_path(last, quiet_missing=True):
                self.settings.pop("last_file", None)
                save_settings(self.paths.settings_file, self.settings)

    # ---- construction --------------------------------------------------------

    def _build_ui(self):
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        self.progress_label = QLabel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

        self.view = ChecklistView()
        self.delegate = ItemDelegate(self.view)
        self.view.setItemDelegate(self.delegate)
        self.view.setModel(self.model)
        self.view.setToolTip("")
        layout.addWidget(self.view, 1)

        self.note_label = QLabel()
        # A long item name must not make the window's minimum width grow: an
        # explicit minimum replaces the label's text-wide minimum size hint.
        self.note_label.setMinimumWidth(1)
        self.note_edit = QPlainTextEdit()
        self.note_edit.setTabChangesFocus(True)
        line = self.note_edit.fontMetrics().lineSpacing()
        self.note_edit.setFixedHeight(line * 3 + 16)
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_edit)

        add_row = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Новый пункт")
        self.add_button = QPushButton("Добавить")
        add_row.addWidget(self.entry, 1)
        add_row.addWidget(self.add_button)
        layout.addLayout(add_row)

        self.setCentralWidget(central)
        self.entry.setFocus()

    def _action(self, text, slot, shortcut=None, view_key=None):
        # List keys are handled by the view itself (they must not fire while
        # typing in the entry or the inline editor); the menu only shows them.
        action = QAction(f"{text}	{view_key[0]}" if view_key else text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if view_key:
            self.view.key_actions[view_key[1:]] = action.trigger
        self.addAction(action)
        return action

    def _build_actions(self):
        a = self._action
        self.act_new = a("&Создать", self.new_file, "Ctrl+N")
        self.act_open = a("&Открыть…", self.open_file, "Ctrl+O")
        self.act_save = a("Со&хранить", self.save, "Ctrl+S")
        self.act_save_as = a("Сохранить &как…", self.save_as, "Ctrl+Shift+S")
        self.act_exit = a("В&ыход", self.close)
        self.act_exit.setShortcut(QKeySequence("Alt+F4"))
        self.act_exit.setShortcutContext(Qt.WidgetShortcut)  # Windows closes the window itself

        none, ctrl = Qt.NoModifier, Qt.ControlModifier
        self.act_toggle = a("Отметить / снять отметку", self.toggle_selected,
                            view_key=("Пробел", Qt.Key_Space, none))
        self.act_edit = a("Изменить", self.edit_selected, view_key=("F2", Qt.Key_F2, none))
        self.act_note = a("Комментарий", self.edit_note)
        self.act_delete = a("Удалить", self.delete_selected,
                            view_key=("Delete", Qt.Key_Delete, none))
        self.act_up = a("Выше", lambda: self.move_selected(-1),
                        view_key=("Ctrl+↑", Qt.Key_Up, ctrl))
        self.act_down = a("Ниже", lambda: self.move_selected(1),
                          view_key=("Ctrl+↓", Qt.Key_Down, ctrl))
        self.item_actions = [self.act_toggle, self.act_edit, self.act_note, self.act_delete,
                             self.act_up, self.act_down]

        self.act_expand_all = a("Развернуть все комментарии", lambda: self.expand_all(True))
        self.act_collapse_all = a("Свернуть все комментарии", lambda: self.expand_all(False))
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for mode in theme.MODES:
            act = a(VIEW_THEME_LABELS[mode], lambda checked=False, m=mode: self.set_theme_mode(m))
            act.setCheckable(True)
            act.setChecked(mode == self.theme_mode)
            self.theme_group.addAction(act)
            self.theme_actions[mode] = act
        self.act_help = a("Как пользоваться", self.show_help, "F1")
        # F10 opens the menu bar like in Windows apps (Alt alone does it too).
        self.act_menu_key = a("Меню", lambda: self.open_menu("file"), "F10")
        self.act_about = a("О программе", self.show_about)

    def _build_menus(self):
        bar = self.menuBar()
        self.bar_menus = {}

        def menu(key, title, actions):
            m = bar.addMenu(title)
            for act in actions:
                m.addSeparator() if act is None else m.addAction(act)
            self.bar_menus[key] = m
            return m

        menu("file", "&Файл", [self.act_new, self.act_open, self.act_save, self.act_save_as,
                               None, self.act_exit])
        menu("item", "&Пункт", self._item_menu_layout())
        menu("view", "&Вид", [*self.theme_actions.values(), None,
                              self.act_expand_all, self.act_collapse_all])
        menu("help", "&Справка", [self.act_help, self.act_about])
        self.item_menu = QMenu(self)
        for act in self._item_menu_layout():
            self.item_menu.addSeparator() if act is None else self.item_menu.addAction(act)

    def _item_menu_layout(self):
        return [self.act_toggle, self.act_edit, self.act_note, self.act_delete, None,
                self.act_up, self.act_down]

    def _connect(self):
        self.model.changed.connect(self._refresh_status)
        self.view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.model.rowsMoved.connect(lambda *a: self._update_item_actions())
        self.model.modelReset.connect(self._on_selection_changed)
        self.model.dataChanged.connect(self._on_data_changed)
        self.model.rowsRemoved.connect(self._on_selection_changed)
        self.view.check_clicked.connect(self._on_check_clicked)
        self.view.arrow_clicked.connect(self.toggle_expanded)
        self.view.text_double_clicked.connect(self.begin_edit)
        self.view.note_double_clicked.connect(self._on_note_double_clicked)
        self.view.deselect_requested.connect(self.deselect)
        self.view.expand_requested.connect(self._expand_selected)
        self.view.menu_requested.connect(self._on_menu_requested)
        self.entry.returnPressed.connect(self.add_item)
        self.add_button.clicked.connect(self.add_item)
        self.note_edit.textChanged.connect(self._on_note_changed)

    # ---- selection -------------------------------------------------------------

    def selected_row(self):
        rows = self.view.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def select(self, row):
        if row is None or not 0 <= row < self.model.rowCount():
            return
        index = self.model.index(row)
        self.view.selectionModel().setCurrentIndex(
            index, self.view.selectionModel().SelectionFlag.ClearAndSelect)
        self.view.scrollTo(index)

    def deselect(self):
        self.end_edit()
        sm = self.view.selectionModel()
        sm.clearSelection()
        sm.setCurrentIndex(QModelIndex(), sm.SelectionFlag.NoUpdate)

    # ---- item operations -----------------------------------------------------

    def add_item(self):
        self.end_edit()
        row = self.model.add(self.entry.text())
        if row is None:
            return
        self.entry.clear()
        self.select(row)

    def toggle_row(self, row):
        self.end_edit()
        if 0 <= row < self.model.rowCount():
            self.model.toggle(row)

    def toggle_selected(self):
        row = self.selected_row()
        if row is not None:
            self.toggle_row(row)

    def _on_check_clicked(self, row):
        self.toggle_row(row)
        self.select(row)

    def delete_selected(self):
        self.end_edit()
        row = self.selected_row()
        if row is None:
            return
        self.model.remove(row)
        remaining = self.model.rowCount()
        if remaining:
            self.select(min(row, remaining - 1))
        else:
            self.deselect()

    def move_selected(self, delta):
        self.end_edit()
        row = self.selected_row()
        if row is None:
            return
        target = row + delta
        if 0 <= target < self.model.rowCount():
            self.select(self.model.move(row, target))

    def set_expanded(self, row, expanded):
        self.end_edit()
        if not 0 <= row < self.model.rowCount():
            return False
        changed = self.model.set_expanded(row, expanded)
        if changed and expanded:
            self.view.scrollTo(self.model.index(row))
        return changed

    def toggle_expanded(self, row):
        if 0 <= row < self.model.rowCount():
            return self.set_expanded(row, not self.model.checklist.items[row].expanded)
        return False

    def _expand_selected(self, expanded):
        row = self.selected_row()
        if row is not None:
            self.set_expanded(row, expanded)

    def expand_all(self, expanded):
        self.end_edit()
        return self.model.expand_all(expanded)

    # ---- inline editing --------------------------------------------------------

    def edit_selected(self):
        row = self.selected_row()
        if row is not None:
            self.begin_edit(row)

    def begin_edit(self, row):
        self.end_edit()
        if not 0 <= row < self.model.rowCount():
            return
        self.select(row)
        self.view.edit(self.model.index(row))

    def editor(self):
        return self.delegate.current_editor

    def end_edit(self, commit=True):
        editor = self.delegate.current_editor
        if editor is None:
            return
        if commit:
            self.delegate.commitData.emit(editor)
        self.delegate.closeEditor.emit(editor, ItemDelegate.EndEditHint.NoHint)
        self.delegate.current_editor = None

    # ---- note panel -----------------------------------------------------------

    def _on_selection_changed(self, *args):
        self._sync_note_panel()
        self._update_item_actions()

    def _sync_note_panel(self):
        row = self.selected_row()
        current = self._note_index.row() if self._note_index.isValid() else None
        if row is not None and row == current:
            return  # the same item, perhaps moved: keep text and undo history
        self._loading_note = True
        try:
            if row is None:
                self._note_index = QPersistentModelIndex()
                self.note_edit.setPlainText("")
                self.note_edit.setEnabled(False)
                self.note_label.setText("Комментарий: выделите пункт в списке")
            else:
                self._note_index = QPersistentModelIndex(self.model.index(row))
                item = self.model.checklist.items[row]
                self.note_edit.setEnabled(True)
                self.note_edit.setPlainText(item.note)  # also clears the undo history
                self.note_label.setText(self._note_title(item))
        finally:
            self._loading_note = False

    def _on_data_changed(self, top, bottom, roles=()):
        # Keeps the panel equal to the note if it was changed some other way;
        # our own typing compares equal after cleaning, so the cursor stays put.
        if not self._note_index.isValid() or not top.row() <= self._note_index.row() <= bottom.row():
            return
        item = self.model.checklist.items[self._note_index.row()]
        if not roles or Qt.DisplayRole in roles:
            self.note_label.setText(self._note_title(item))
        if roles and NoteRole not in roles:
            return
        note = item.note
        if clean_note(self.note_edit.toPlainText()) != note:
            self._loading_note = True
            try:
                self.note_edit.setPlainText(note)
            finally:
                self._loading_note = False

    @staticmethod
    def _note_title(item):
        short = item.text if len(item.text) <= 40 else item.text[:39] + "…"
        return f"Комментарий к «{short}»:"

    def _on_note_changed(self):
        if self._loading_note or not self._note_index.isValid():
            return
        self.model.set_note(self._note_index.row(), self.note_edit.toPlainText())

    def edit_note(self):
        self.end_edit()
        if self.selected_row() is None:
            return
        self.note_edit.setFocus()
        cursor = self.note_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.note_edit.setTextCursor(cursor)

    def _on_note_double_clicked(self, row):
        self.select(row)
        self.edit_note()

    # ---- keyboard and menus ------------------------------------------------------

    def ctrl_action(self, letter, shift):
        return {("N", False): self.act_new, ("O", False): self.act_open,
                ("S", False): self.act_save, ("S", True): self.act_save_as}.get((letter, shift))

    def open_menu(self, key):
        self.end_edit()
        menu = self.bar_menus[key]
        self.menuBar().setActiveAction(menu.menuAction())

    def _on_menu_requested(self, row, pos):
        self.end_edit()
        self.select(row)
        self.view.setFocus()
        self.popup_item_menu(pos)

    def popup_item_menu(self, pos):
        self.item_menu.popup(pos)

    def _update_item_actions(self):
        has = self.selected_row() is not None
        for act in self.item_actions:
            act.setEnabled(has)
        row = self.selected_row()
        count = self.model.rowCount()
        self.act_up.setEnabled(has and row > 0)
        self.act_down.setEnabled(has and row < count - 1)

    # ---- status ----------------------------------------------------------------

    def _refresh_status(self):
        cl = self.model.checklist
        self.progress_label.setText(f"Выполнено: {cl.done_count} из {cl.total}")
        self.progress_bar.setMaximum(max(cl.total, 1))
        self.progress_bar.setValue(cl.done_count)
        name = os.path.basename(cl.path) if cl.path else UNTITLED
        self.setWindowTitle(f"{'*' if cl.dirty else ''}{name} - {APP_NAME}")

    # ---- theme -------------------------------------------------------------------

    def set_theme_mode(self, mode):
        self.theme_mode = theme.normalize_mode(mode)
        self.theme_actions[self.theme_mode].setChecked(True)
        self.settings["theme"] = self.theme_mode
        save_settings(self.paths.settings_file, self.settings)
        theme.apply_mode(QApplication.instance(), self.theme_mode)

    # ---- files ---------------------------------------------------------------------

    def _ask_save(self, name):
        """'save', 'discard' or 'cancel'."""
        answer = QMessageBox.question(
            self, APP_NAME, f"Сохранить изменения в «{name}»?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        return {QMessageBox.Save: "save", QMessageBox.Discard: "discard"}.get(answer, "cancel")

    def _ask_open_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть список", self._initial_dir() or "",
                                              FILE_FILTER)
        return path

    def _ask_save_path(self, suggested):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить список", suggested, FILE_FILTER)
        if path and not os.path.splitext(path)[1]:
            path += ".json"
        return path

    def _error(self, text):
        QMessageBox.critical(self, APP_NAME, text)

    def _info(self, title, text):
        QMessageBox.information(self, title, text)

    def _confirm_discard(self):
        self.end_edit()
        cl = self.model.checklist
        if not cl.dirty:
            return True
        name = os.path.basename(cl.path) if cl.path else UNTITLED
        answer = self._ask_save(name)
        if answer == "cancel":
            return False
        if answer == "save":
            return self.save()
        return True

    def new_file(self):
        if self._confirm_discard():
            self.model.set_checklist(Checklist())

    def open_file(self):
        if not self._confirm_discard():
            return
        path = self._ask_open_path()
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
        self.model.set_checklist(checklist)
        self._remember(checklist.path)
        if len(checklist):
            self.select(0)
        return True

    def save(self):
        self.end_edit()
        if self.model.checklist.path:
            return self._save_to(self.model.checklist.path)
        return self.save_as()

    def save_as(self):
        self.end_edit()
        current = self.model.checklist.path
        folder = os.path.dirname(current) if current else (self._initial_dir() or "")
        name = os.path.basename(current) if current else "Новый список.json"
        path = self._ask_save_path(os.path.join(folder, name))
        if not path:
            return False
        return self._save_to(path)

    def _save_to(self, path):
        try:
            self.model.checklist.save(path)
        except OSError as e:
            self._error(f"Не удалось сохранить файл:\n{path}\n\n{e.strerror or e}")
            return False
        self._remember(self.model.checklist.path)
        self._refresh_status()
        return True

    def _initial_dir(self):
        cl = self.model.checklist
        if cl.path:
            return os.path.dirname(cl.path)
        try:
            os.makedirs(self.paths.lists_dir, exist_ok=True)
        except OSError:
            return None
        return self.paths.lists_dir

    def _remember(self, path):
        self.settings["last_file"] = path
        save_settings(self.paths.settings_file, self.settings)

    def show_help(self):
        self._info("Как пользоваться", HELP_TEXT)

    def show_about(self):
        mode = "portable" if self.paths.portable else "установленная версия"
        self._info(f"О программе {APP_NAME}",
                   f"{APP_NAME} {__version__}\n"
                   "Чек-лист: впишите пункты и отмечайте выполненные.\n\n"
                   f"Режим: {mode}\n"
                   f"Тема: {theme.MODE_LABELS[self.theme_mode]}\n"
                   f"Настройки: {self.paths.settings_file}\n"
                   f"Папка списков: {self.paths.lists_dir}")

    def closeEvent(self, event):
        if self._confirm_discard():
            QApplication.instance().removeEventFilter(self._keys)
            event.accept()
        else:
            event.ignore()
