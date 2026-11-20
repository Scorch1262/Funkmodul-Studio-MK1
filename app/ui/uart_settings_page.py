"""Nutzereinstellungen des per UART angeschlossenen Moduls lesen und schreiben."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..theme import C
from ..uart.framing import decode_value, encode_value, hexs
from .common import Card, hbox, label

COL_ID, COL_NAME, COL_TYPE, COL_VALUE, COL_HEX, COL_DESC = range(6)
KIND_LABEL = {"u8": "u8", "i8": "i8", "u16": "u16", "u32": "u32", "hex": "HEX", "ascii": "Text", "mac": "MAC"}


class EditDialog(QDialog):
    def __init__(self, parent, setting, current: bytes | None):
        super().__init__(parent)
        self.setting = setting
        self.setWindowTitle("Einstellung schreiben")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.addWidget(label(f"{setting.name}   (0x{setting.sid:02X})", "Accent"))
        if setting.desc:
            d = label(setting.desc, "Muted")
            d.setWordWrap(True)
            lay.addWidget(d)
        form = QFormLayout()
        self.val = QLineEdit()
        self.val.setObjectName("Payload")
        if current:
            self.val.setText(hexs(current) if setting.kind in ("hex", "mac") else
                             decode_value(setting.kind, current).split(" ")[0])
        form.addRow(f"Wert ({KIND_LABEL.get(setting.kind, setting.kind)})", self.val)
        self.prev = label("", "Muted")
        form.addRow("Bytes", self.prev)
        lay.addLayout(form)
        self.val.textChanged.connect(self._upd)
        self._upd()
        note = label("Die meisten Module übernehmen geänderte Einstellungen erst nach einem Neustart.", "Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Schreiben")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.result_bytes = b""

    def _upd(self):
        try:
            self.prev.setText(hexs(encode_value(self.setting.kind, self.val.text())) or "–")
            self.prev.setStyleSheet("")
        except ValueError as exc:
            self.prev.setText(str(exc))
            self.prev.setStyleSheet(f"color:{C['red']}")

    def _accept(self):
        try:
            self.result_bytes = encode_value(self.setting.kind, self.val.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Einstellung", str(exc))
            return
        self.accept()


class UartSettingsPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.ctl = mw.uart
        self.values: dict[int, bytes] = {}
        self.queue: list = []          # (art, setting, wert)
        self.waiting = None
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        head = Card("Modul-Einstellungen (UART)")
        self.info = label("", "Muted")
        self.info.setWordWrap(True)
        head.lay.addWidget(self.info)
        self.b_all = QPushButton("Alle lesen")
        self.b_all.setObjectName("Primary")
        self.b_sel = QPushButton("Auswahl lesen")
        self.b_write = QPushButton("Auswahl schreiben …")
        self.b_reset = QPushButton("Modul neu starten")
        self.b_all.clicked.connect(self.read_all)
        self.b_sel.clicked.connect(self.read_selected)
        self.b_write.clicked.connect(self.write_selected)
        self.b_reset.clicked.connect(self.reset_module)
        self.progress = label("", "Teal")
        head.lay.addWidget(hbox(self.b_all, self.b_sel, self.b_write, None, self.progress, self.b_reset))
        root.addWidget(head)

        tc = Card("Einstellungen")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "NAME", "TYP", "WERT", "HEX", "BESCHREIBUNG"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        hh = self.table.horizontalHeader()
        for c in (COL_ID, COL_NAME, COL_TYPE):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_VALUE, QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_HEX, QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_DESC, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(lambda *_: self.write_selected())
        tc.lay.addWidget(self.table)
        root.addWidget(tc, 1)

        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._on_timeout)
        self.ctl.frame.connect(self._on_frame)
        self.ctl.module_changed.connect(lambda _m: self.reload())
        self.ctl.state.connect(lambda *_: self._enable())
        self.reload()

    # ------------------------------------------------------------------
    def reload(self):
        m = self.ctl.module
        self.values.clear()
        self.queue.clear()
        self.waiting = None
        self.progress.setText("")
        self.table.setRowCount(0)
        if not m.settings:
            if m.proto == "at":
                txt = f"{m.label} wird über AT-Befehle konfiguriert – bitte die Seite »UART-Terminal« nutzen."
            elif m.key == "metise":
                txt = "Metis-e verwendet TLV-Optionen – Get/Set über die Befehlsliste der Seite »UART-Terminal«."
            else:
                txt = f"Für {m.label} gibt es keine Einstellungstabelle."
            self.info.setText(txt)
        else:
            self.info.setText(f"{m.label} · {len(m.settings)} Einstellungen. Lesen per CMD_GET "
                              f"(0x{m.get_code:02X}), Schreiben per CMD_SET (0x{m.set_code:02X}). "
                              "Doppelklick auf eine Zeile zum Bearbeiten.")
        for s in m.settings:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [f"0x{s.sid:02X}", s.name, KIND_LABEL.get(s.kind, s.kind) + (" · nur lesen" if s.ro else ""),
                    "", "", s.desc]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == COL_NAME:
                    it.setForeground(QColor(C["amber"]))
                    it.setData(Qt.UserRole, s)
                elif c in (COL_ID, COL_TYPE, COL_DESC):
                    it.setForeground(QColor(C["muted"]))
                self.table.setItem(r, c, it)
        self._enable()

    def _enable(self):
        ok = self.ctl.is_open and bool(self.ctl.module.settings) and self.waiting is None
        for b in (self.b_all, self.b_sel, self.b_write):
            b.setEnabled(ok)
        self.b_reset.setEnabled(self.ctl.is_open and any(c.name == "Reset" for c in self.ctl.module.commands))

    def _selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [self.table.item(r, COL_NAME).data(Qt.UserRole) for r in rows]

    def _row_of(self, sid):
        for r in range(self.table.rowCount()):
            if self.table.item(r, COL_NAME).data(Qt.UserRole).sid == sid:
                return r
        return -1

    # ------------------------------------------------------------------ Ablauf
    def read_all(self):
        self.queue = [("get", s, None) for s in self.ctl.module.settings]
        self._next()

    def read_selected(self):
        sel = self._selected()
        if not sel:
            self.mw.toast("Keine Einstellung ausgewählt.", error=True)
            return
        self.queue = [("get", s, None) for s in sel]
        self._next()

    def write_selected(self):
        if not self.ctl.is_open:
            self.mw.toast("Zuerst den COM-Port öffnen.", error=True)
            return
        sel = self._selected()
        if len(sel) != 1:
            self.mw.toast("Bitte genau eine Einstellung auswählen.", error=True)
            return
        s = sel[0]
        if s.ro:
            self.mw.toast(f"{s.name} ist nur lesbar.", error=True)
            return
        dlg = EditDialog(self, s, self.values.get(s.sid))
        if dlg.exec() == QDialog.Accepted:
            self.queue = [("set", s, dlg.result_bytes), ("get", s, None)]
            self._next()

    def reset_module(self):
        cmd = next((c for c in self.ctl.module.commands if c.name == "Reset"), None)
        if cmd:
            self.ctl.send_command(cmd.code, b"")

    def _next(self):
        if not self.queue:
            self.waiting = None
            self.progress.setText("Fertig.")
            self._enable()
            return
        kind, s, val = self.queue.pop(0)
        m = self.ctl.module
        if m.settings_style == "metis":
            ln = s.length or 1
            payload = bytes([s.sid, ln]) + (val or b"") if kind == "set" else bytes([s.sid, ln])
        else:
            payload = bytes([s.sid]) + (val or b"") if kind == "set" else bytes([s.sid])
        code = m.set_code if kind == "set" else m.get_code
        self.waiting = (kind, s, code)
        self.progress.setText(f"{'Schreibe' if kind == 'set' else 'Lese'} {s.name} … ({len(self.queue)} offen)")
        self._enable()
        if not self.ctl.send_command(code, payload, f"CMD_{'SET' if kind == 'set' else 'GET'}_REQ  {s.name}"):
            self.queue.clear()
            self.waiting = None
            self._enable()
            return
        self.timeout.start(1500)

    def _cnf_code(self, code):
        return code | (0x80 if self.ctl.module.proto == "metis" else 0x40)

    def _on_frame(self, f):
        if self.waiting is None:
            return
        kind, s, code = self.waiting
        if f.cmd != self._cnf_code(code):
            return
        self.timeout.stop()
        r = self._row_of(s.sid)
        p = f.payload
        if self.ctl.module.settings_style == "metis":
            status_ok = True
            value = p[2:] if len(p) >= 2 else p
        else:
            status_ok = bool(p) and p[0] == 0x00
            value = p[1:]
        if kind == "get" and r >= 0:
            if status_ok:
                self.values[s.sid] = value
                self.table.item(r, COL_VALUE).setText(decode_value(s.kind, value))
                self.table.item(r, COL_HEX).setText(hexs(value))
                self.table.item(r, COL_VALUE).setForeground(QColor(C["teal"]))
            else:
                self.table.item(r, COL_VALUE).setText(f"Fehler (Status {p[0]:02X})" if p else "Fehler")
                self.table.item(r, COL_VALUE).setForeground(QColor(C["red"]))
        elif kind == "set":
            if status_ok:
                self.mw.toast(f"{s.name} geschrieben. Ggf. Modul neu starten.")
            else:
                self.mw.toast(f"{s.name}: Schreiben abgelehnt (Status {p[0]:02X})" if p else "Schreiben abgelehnt",
                              error=True)
                self.queue = [q for q in self.queue if q[1] is not s]
        self.waiting = None
        QTimer.singleShot(30, self._next)

    def _on_timeout(self):
        if self.waiting is None:
            return
        _, s, _ = self.waiting
        r = self._row_of(s.sid)
        if r >= 0:
            self.table.item(r, COL_VALUE).setText("keine Antwort")
            self.table.item(r, COL_VALUE).setForeground(QColor(C["red"]))
        self.waiting = None
        self._next()
