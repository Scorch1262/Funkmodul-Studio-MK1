"""Grafische Bausteine: aufklappbare Hilfe, Frame-Grafik, Befehlskacheln, Fluss-Layout, Kennzahlen."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ..theme import C
from .help_texts import FRAME_PARTS, HELP


# ---------------------------------------------------------------------------
# Fluss-Layout (Elemente brechen automatisch um)
# ---------------------------------------------------------------------------

class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self.items = []
        self.sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self.items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self.items:
            w = it.widget()
            if w is not None and w.isHidden() and w.testAttribute(Qt.WA_WState_ExplicitShowHide):
                continue
            hint = it.sizeHint()
            nx = x + hint.width() + self.sp
            if nx - self.sp > rect.right() + 1 and line_h > 0:
                x = rect.x()
                y += line_h + self.sp
                nx = x + hint.width() + self.sp
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


# ---------------------------------------------------------------------------
# Aufklappbare Hilfe
# ---------------------------------------------------------------------------

class HelpPanel(QFrame):
    """Kopfzeile mit »?«-Knopf; klappt Erklärungen zur Seite auf."""

    def __init__(self, key: str, settings=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Help")
        self.key = key
        self.settings = settings
        title, items = HELP[key]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        icon = QLabel("?")
        icon.setObjectName("HelpIcon")
        icon.setFixedSize(22, 22)
        icon.setAlignment(Qt.AlignCenter)
        t = QLabel(title)
        t.setObjectName("HelpTitle")
        self.btn = QPushButton()
        self.btn.setObjectName("Link")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self.toggle)
        head.addWidget(icon)
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(self.btn)
        lay.addLayout(head)
        self.body = QWidget()
        grid = QGridLayout(self.body)
        grid.setContentsMargins(30, 2, 0, 4)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(5)
        cols = 2 if len(items) > 3 else 1
        for i, (name, text) in enumerate(items):
            row = QLabel(f'<span style="color:{C["amber"]};font-weight:600">{name}</span>'
                         f'<span style="color:{C["muted"]}"> — {text}</span>')
            row.setWordWrap(True)
            row.setTextFormat(Qt.RichText)
            row.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            grid.addWidget(row, i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        lay.addWidget(self.body)
        opened = True
        if settings is not None:
            opened = (settings.get("help_open") or {}).get(key, True)
        self._set(opened)

    def _set(self, on):
        self.body.setVisible(on)
        self.btn.setText("Erklärung ausblenden ▴" if on else "Erklärung anzeigen ▾")

    def toggle(self):
        on = not self.body.isVisible()
        self._set(on)
        if self.settings is not None:
            d = dict(self.settings.get("help_open") or {})
            d[self.key] = on
            self.settings.set("help_open", d)


def help_dot(text: str) -> QLabel:
    """Kleines »?« mit Tooltip-Erklärung."""
    lb = QLabel("?")
    lb.setObjectName("HelpDot")
    lb.setFixedSize(16, 16)
    lb.setAlignment(Qt.AlignCenter)
    lb.setToolTip(text)
    return lb


# ---------------------------------------------------------------------------
# Frame-Grafik
# ---------------------------------------------------------------------------

SEG_COLOR = {"STX": "#5b6b80", "CMD": C["amber"], "LEN": "#5fa8ff", "DATA": C["teal"], "CS": C["violet"],
             "TEXT": C["teal"], "RAW": "#c9d3df"}
SEG_LABEL = {"STX": "START", "CMD": "BEFEHL", "LEN": "LÄNGE", "DATA": "DATEN", "CS": "PRÜFSUMME",
             "TEXT": "TEXT", "RAW": "ROHDATEN"}


def segments(proto: str, data: bytes) -> list[tuple[str, bytes]]:
    """Zerlegt Bytes in Abschnitte für die Grafik."""
    if not data:
        return []
    if proto in ("cmd16", "cmd8", "metis") and len(data) >= 4 and data[0] in (0x02, 0xFF):
        h = 4 if proto == "cmd16" else 3
        if len(data) >= h + 1:
            segs = [("STX", data[:1]), ("CMD", data[1:2]), ("LEN", data[2:h])]
            if len(data) > h + 1:
                segs.append(("DATA", data[h:-1]))
            segs.append(("CS", data[-1:]))
            return segs
    if all(32 <= b < 127 or b in (9, 10, 13) for b in data):
        return [("TEXT", data)]
    return [("RAW", data)]


class FrameView(QWidget):
    """Zeichnet einen Frame als farbige Byte-Kästchen mit Beschriftung der Abschnitte."""

    CELL = 26
    GAP = 3

    def __init__(self, parent=None, max_bytes=96):
        super().__init__(parent)
        self.segs: list[tuple[str, bytes]] = []
        self.max_bytes = max_bytes
        self.message = "Noch kein Frame"
        self.mono = QFont("Consolas")
        self.mono.setStyleHint(QFont.Monospace)
        self.mono.setPointSizeF(8.5)
        self.small = QFont()
        self.small.setPointSizeF(7)
        self.small.setBold(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tips = "\n".join(f"{SEG_LABEL[k]}: {v}" for k, v in FRAME_PARTS.items() if k in SEG_LABEL)
        self.setToolTip(tips)

    def set_frame(self, proto: str, data: bytes, message: str = ""):
        self.segs = segments(proto, data)
        self.message = message
        self.updateGeometry()
        self.update()

    def clear(self, message="Noch kein Frame"):
        self.segs = []
        self.message = message
        self.updateGeometry()
        self.update()

    # Layout der Kästchen berechnen
    def _layout(self, width):
        cells = []
        x, y = 0, 0
        row_h = self.CELL + 18
        shown = 0
        for kind, b in self.segs:
            if kind == "TEXT":
                txt = b.decode("latin-1").replace("\r", "␍").replace("\n", "␊")
                fm = QFontMetrics(self.mono)
                w = min(width, fm.horizontalAdvance(txt) + 16)
                if x + w > width and x > 0:
                    x, y = 0, y + row_h
                cells.append((QRectF(x, y, w, self.CELL), kind, txt, True))
                x += w + self.GAP * 3
                continue
            first = True
            for byte in b:
                if shown >= self.max_bytes:
                    cells.append((QRectF(x, y, 30, self.CELL), "RAW", "…", False))
                    return cells, y + row_h
                if x + self.CELL > width:
                    x, y = 0, y + row_h
                    first = True
                cells.append((QRectF(x, y, self.CELL, self.CELL), kind, f"{byte:02X}", first))
                first = False
                x += self.CELL + self.GAP
                shown += 1
            x += self.GAP * 3
        return cells, y + row_h

    def sizeHint(self):
        w = max(200, self.width())
        if not self.segs:
            return QSize(w, 40)
        _, h = self._layout(w)
        return QSize(w, int(h) + 4)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        if not self.segs:
            return 40
        return int(self._layout(w)[1]) + 4

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.segs:
            p.setPen(QColor(C["dim"]))
            p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self.message)
            return
        cells, _ = self._layout(self.width())
        for rect, kind, text, first in cells:
            col = QColor(SEG_COLOR[kind])
            fill = QColor(col)
            fill.setAlpha(40)
            p.setPen(QPen(col, 1.2))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 4, 4)
            p.setFont(self.mono)
            p.setPen(QColor("#e8eef5"))
            p.drawText(rect, Qt.AlignCenter, text)
            if first:
                p.setFont(self.small)
                p.setPen(col)
                p.drawText(QRectF(rect.left(), rect.bottom() + 2, 120, 14), Qt.AlignLeft, SEG_LABEL[kind])
        if self.message:
            self.setToolTip(self.message)


# ---------------------------------------------------------------------------
# Befehlskachel
# ---------------------------------------------------------------------------

class Tile(QFrame):
    clicked = Signal(object)
    double_clicked = Signal(object)

    def __init__(self, cmd, code_text: str, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.setObjectName("TileDanger" if cmd.danger else "Tile")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(186, 74)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)
        top = QHBoxLayout()
        name = QLabel(cmd.name if not cmd.at else cmd.at.split("=")[0])
        name.setObjectName("TileName")
        code = QLabel(code_text)
        code.setObjectName("TileCode")
        top.addWidget(name, 1)
        top.addWidget(code)
        lay.addLayout(top)
        desc = QLabel(cmd.desc or (cmd.at if cmd.at else ""))
        desc.setObjectName("TileDesc")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(desc, 1)
        self.setToolTip(f"{cmd.name}\n{cmd.desc}" + ("\n⚠ Setzt das Modul zurück" if cmd.danger else "")
                        + "\nKlick: auswählen · Doppelklick: sofort senden")

    def set_selected(self, on):
        self.setProperty("sel", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self.cmd)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.double_clicked.emit(self.cmd)


# ---------------------------------------------------------------------------
# Kennzahl / Schritt
# ---------------------------------------------------------------------------

class Kpi(QFrame):
    def __init__(self, title, value="–", color=None, tip=""):
        super().__init__()
        self.setObjectName("Kpi")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(0)
        t = QLabel(title.upper())
        t.setObjectName("KpiTitle")
        self.v = QLabel(value)
        self.v.setObjectName("KpiValue")
        if color:
            self.v.setStyleSheet(f"color:{color};")
        lay.addWidget(t)
        lay.addWidget(self.v)
        if tip:
            self.setToolTip(tip)

    def set(self, v):
        self.v.setText(str(v))


class StepBadge(QLabel):
    def __init__(self, n: int):
        super().__init__(str(n))
        self.n = n
        self.setObjectName("Step")
        self.setFixedSize(26, 26)
        self.setAlignment(Qt.AlignCenter)

    def set_done(self, done: bool):
        self.setProperty("done", done)
        self.setText("✓" if done else str(self.n))
        self.style().unpolish(self)
        self.style().polish(self)
