"""Qt model over a Checklist: after loading, every change goes through here."""
import html

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal

from checkprog.model import Checklist

NoteRole = Qt.UserRole + 1
ExpandedRole = Qt.UserRole + 2
ItemRole = Qt.UserRole + 3  # the immutable Item itself, for identity checks


class ChecklistModel(QAbstractListModel):
    changed = Signal()  # after every real change, including a new list

    def __init__(self, checklist=None, parent=None):
        super().__init__(parent)
        self._cl = checklist if checklist is not None else Checklist()

    @property
    def checklist(self):
        return self._cl

    def set_checklist(self, checklist):
        self.beginResetModel()
        self._cl = checklist
        self.endResetModel()
        self.changed.emit()

    # ---- read ---------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._cl)

    def data(self, index, role=Qt.DisplayRole):
        if not self._valid(index):
            return None
        item = self._cl.items[index.row()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return item.text
        if role == Qt.CheckStateRole:
            return Qt.Checked if item.done else Qt.Unchecked
        if role == NoteRole:
            return item.note
        if role == ExpandedRole:
            return item.expanded
        if role == ItemRole:
            return item
        if role == Qt.ToolTipRole:
            # A collapsed note as a preview. Rich text, so Qt wraps long lines
            # instead of drawing one strip across the screen.
            if not item.note or item.expanded:
                return None
            return "<p>" + html.escape(item.note).replace("\n", "<br>") + "</p>"
        return None

    def flags(self, index):
        if not self._valid(index):
            return Qt.ItemIsDropEnabled  # drops land between rows only
        return (Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
                | Qt.ItemIsDragEnabled | Qt.ItemNeverHasChildren)

    def supportedDropActions(self):
        return Qt.MoveAction

    def supportedDragActions(self):
        return Qt.MoveAction

    # ---- write --------------------------------------------------------------

    def setData(self, index, value, role=Qt.EditRole):
        if not self._valid(index):
            return False
        row = index.row()
        if role == Qt.EditRole:
            return self.rename(row, str(value))
        if role == Qt.CheckStateRole:
            done = Qt.CheckState(value) == Qt.Checked
            if self._cl.items[row].done == done:
                return True
            self._cl.set_done(row, done)
            self._row_changed(row, (Qt.CheckStateRole,))
            return True
        return False

    def add(self, text):
        row = len(self._cl)
        # Checklist.add cleans the text and refuses empty ones; only then insert.
        probe = Checklist()
        if probe.add(text) is None:
            return None
        self.beginInsertRows(QModelIndex(), row, row)
        self._cl.add(text)
        self.endInsertRows()
        self.changed.emit()
        return row

    def toggle(self, row):
        self._cl.toggle(row)
        self._row_changed(row, (Qt.CheckStateRole,))

    def rename(self, row, text):
        if not self._cl.rename(row, text):
            return False
        self._row_changed(row, (Qt.DisplayRole, Qt.EditRole))
        return True

    def set_note(self, row, text):
        old = self._cl.items[row]
        if not self._cl.set_note(row, text):
            return False
        roles = [NoteRole, Qt.ToolTipRole, Qt.SizeHintRole]  # tooltip follows the note
        if old.expanded and not self._cl.items[row].note:
            self._cl.set_expanded(row, False)  # nothing left to show
            roles.append(ExpandedRole)
        self._row_changed(row, roles)
        return True

    def set_expanded(self, row, expanded):
        if expanded and not self._cl.items[row].note:
            return False
        if not self._cl.set_expanded(row, expanded):
            return False
        self._row_changed(row, (ExpandedRole, Qt.SizeHintRole, Qt.ToolTipRole))
        return True

    def expand_all(self, expanded):
        changed = [row for row, item in enumerate(self._cl.items)
                   if item.note and item.expanded != expanded]
        for row in changed:
            self._cl.set_expanded(row, expanded)
        if not changed:
            return False
        self.dataChanged.emit(self.index(changed[0]), self.index(changed[-1]),
                              [ExpandedRole, Qt.SizeHintRole, Qt.ToolTipRole])
        self.changed.emit()
        return True

    def remove(self, row):
        self._cl._check_index(row)
        self.beginRemoveRows(QModelIndex(), row, row)
        item = self._cl.remove(row)
        self.endRemoveRows()
        self.changed.emit()
        return item

    def move(self, src, dst):
        """Moves item src to final position dst (clamped); returns that position."""
        self._cl._check_index(src)
        dst = max(0, min(dst, len(self._cl) - 1))
        if dst == src:
            return src
        # Qt wants the row it goes *before* in the old numbering.
        self.beginMoveRows(QModelIndex(), src, src, QModelIndex(), dst + 1 if dst > src else dst)
        self._cl.move(src, dst)
        self.endMoveRows()
        self.changed.emit()
        return dst

    def moveRows(self, source_parent, source_row, count, dest_parent, dest_child):
        # Called by QListView for internal drag-and-drop.
        if (count != 1 or source_parent.isValid() or dest_parent.isValid()
                or not 0 <= source_row < len(self._cl)
                or not 0 <= dest_child <= len(self._cl)
                or dest_child in (source_row, source_row + 1)):
            return False
        self.move(source_row, dest_child - 1 if dest_child > source_row else dest_child)
        return True

    # ---- helpers ------------------------------------------------------------

    def _valid(self, index):
        return index.isValid() and not index.parent().isValid() and 0 <= index.row() < len(self._cl)

    def _row_changed(self, row, roles):
        ix = self.index(row)
        self.dataChanged.emit(ix, ix, list(roles))
        self.changed.emit()
