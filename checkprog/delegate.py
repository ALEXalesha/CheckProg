"""Draws one checklist row: checkbox, text, ▼/▲ and, when expanded, the note.

layout() is the single place that decides where everything goes; paint(),
sizeHint() and hit() all use it, so what is drawn is exactly what is clickable.
"""
from typing import NamedTuple, Optional

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPalette, QTextLayout, QTextOption
from PySide6.QtWidgets import QLineEdit, QStyle, QStyledItemDelegate, QStyleOptionButton

from checkprog import theme
from checkprog.listmodel import ExpandedRole, NoteRole

ARROW_CLOSED = "▼"
ARROW_OPEN = "▲"


class RowLayout(NamedTuple):
    check: QRect           # the whole cell left of the text: clicking it toggles
    box: QRect             # the drawn checkbox inside `check`
    text: QRect
    arrow: Optional[QRect]
    note: Optional[QRect]
    note_lines: tuple


class ItemDelegate(QStyledItemDelegate):
    PAD = 8      # horizontal padding, px at 100 %
    VPAD = 5     # vertical padding of the first line

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wrap_cache = {}
        self.current_editor = None  # the open inline editor, if any
        self.closeEditor.connect(self._forget_editor)

    # ---- geometry -----------------------------------------------------------

    @staticmethod
    def note_font(font):
        f = QFont(font)
        f.setItalic(True)
        if f.pointSizeF() > 0:
            f.setPointSizeF(max(6.0, f.pointSizeF() - 1))
        return f

    def _row_width(self, option):
        if option.rect.width() > 0:
            return option.rect.width()
        widget = option.widget
        return widget.viewport().width() if widget is not None else 400

    def layout(self, option, index):
        fm = QFontMetrics(option.font)
        scale = max(1.0, fm.height() / 16)
        pad = round(self.PAD * scale)
        vpad = round(self.VPAD * scale)
        left = option.rect.left()
        top = option.rect.top()
        width = self._row_width(option)
        right = left + width  # exclusive

        box_size = max(13, fm.height() - 2)
        line_h = max(fm.height(), box_size) + 2 * vpad
        check = QRect(left, top, pad + box_size + pad, line_h)
        box = QRect(left + pad, top + (line_h - box_size) // 2, box_size, box_size)

        note = index.data(NoteRole) or ""
        arrow = None
        text_right = right - pad
        if note:
            arrow_w = fm.horizontalAdvance(ARROW_OPEN) + 2 * pad
            arrow = QRect(right - arrow_w, top, arrow_w, line_h)
            text_right = arrow.left() - 1
        text = QRect(check.right() + 1, top, max(1, text_right - check.right()), line_h)

        note_rect, lines = None, ()
        if note and index.data(ExpandedRole):
            nfont = self.note_font(option.font)
            note_w = max(1, right - pad - text.left())
            lines = self.wrap_note(note, note_w, nfont)
            nfm = QFontMetrics(nfont)
            note_h = len(lines) * nfm.lineSpacing() + vpad
            note_rect = QRect(text.left(), top + line_h, note_w, note_h)
        return RowLayout(check, box, text, arrow, note_rect, lines)

    def sizeHint(self, option, index):
        lay = self.layout(option, index)
        height = lay.check.height() + (lay.note.height() if lay.note is not None else 0)
        return QSize(self._row_width(option), height)

    def hit(self, option, index, pos):
        lay = self.layout(option, index)
        for name, rect in (("check", lay.check), ("arrow", lay.arrow),
                           ("text", lay.text), ("note", lay.note)):
            if rect is not None and rect.contains(pos):
                return name
        return None

    def wrap_note(self, note, width, font):
        """Note split into lines no wider than `width` (Qt wraps, we only cut)."""
        key = (note, width, font.key())
        cached = self._wrap_cache.get(key)
        if cached is not None:
            return cached
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        lines = []
        for paragraph in note.split("\n"):
            if not paragraph:
                lines.append("")
                continue
            tl = QTextLayout(paragraph, font)
            tl.setTextOption(text_option)
            tl.beginLayout()
            while True:
                line = tl.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(width)
                lines.append(paragraph[line.textStart():line.textStart() + line.textLength()]
                             .rstrip(" "))
            tl.endLayout()
        if len(self._wrap_cache) > 4000:
            self._wrap_cache.clear()
        result = self._wrap_cache[key] = tuple(lines)
        return result

    # ---- painting -----------------------------------------------------------

    def paint(self, painter, option, index):
        opt = type(option)(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else _app_style()
        lay = self.layout(opt, index)
        painter.save()
        opt.text = ""
        opt.features &= ~opt.ViewItemFeature.HasCheckIndicator
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, opt, painter, widget)
        if opt.state & QStyle.State_Selected:
            self._paint_selection(painter, opt, lay)

        done = index.data(Qt.CheckStateRole) == Qt.Checked
        button = QStyleOptionButton()
        button.rect = lay.box
        button.palette = opt.palette
        button.state = (QStyle.State_Enabled | (QStyle.State_On if done else QStyle.State_Off))
        style.drawPrimitive(QStyle.PE_IndicatorCheckBox, button, painter, widget)

        selected = bool(opt.state & QStyle.State_Selected)
        strong_selection = selected and style.name().lower() != "windows11"
        fg = opt.palette.color(QPalette.HighlightedText if strong_selection else QPalette.Text)
        muted = fg if strong_selection else theme.muted_color(opt.palette)

        font = QFont(opt.font)
        if done:
            font.setStrikeOut(True)
        painter.setFont(font)
        painter.setPen(muted if done else fg)
        fm = QFontMetrics(font)
        text = fm.elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, lay.text.width())
        painter.drawText(lay.text, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine, text)

        if lay.arrow is not None:
            painter.setFont(opt.font)
            painter.setPen(fg)
            painter.drawText(lay.arrow, Qt.AlignCenter,
                             ARROW_OPEN if index.data(ExpandedRole) else ARROW_CLOSED)

        if lay.note is not None:
            nfont = self.note_font(opt.font)
            painter.setFont(nfont)
            painter.setPen(muted)
            spacing = QFontMetrics(nfont).lineSpacing()
            y = lay.note.top()
            for line in lay.note_lines:
                painter.drawText(QRect(lay.note.left(), y, lay.note.width(), spacing),
                                 Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, line)
                y += spacing
        painter.restore()

    @staticmethod
    def _paint_selection(painter, opt, lay):
        # windows11 marks a selected row so faintly that in the dark scheme it
        # is hard to see; add a tint and an accent pill like Windows 11 lists.
        accent = opt.palette.color(QPalette.Highlight)
        tint = QColor(accent)
        tint.setAlpha(70)
        painter.fillRect(opt.rect, tint)
        pill_h = max(8, lay.check.height() // 2)
        pill = QRect(opt.rect.left() + 1, lay.check.top() + (lay.check.height() - pill_h) // 2,
                     3, pill_h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(pill, 1.5, 1.5)

    # ---- inline editor ------------------------------------------------------

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setFrame(True)
        self.current_editor = editor
        return editor

    def _forget_editor(self, editor, hint=None):
        if editor is self.current_editor:
            self.current_editor = None

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.EditRole) or "")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)  # empty text is refused there

    def updateEditorGeometry(self, editor, option, index):
        lay = self.layout(option, index)
        rect = QRect(lay.text)
        if lay.arrow is not None:
            rect.setRight(lay.arrow.right() - self.PAD)
        editor.setGeometry(rect)


def _app_style():
    from PySide6.QtWidgets import QApplication
    return QApplication.style()
