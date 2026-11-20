"""UART-Seite: COM-Port, Befehlsliste mit Parameterformular, farbiges Frame-Protokoll."""
from __future__ import annotations

import html
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..theme import C
from ..uart.framing import build_frame, command_payload, hexs, xor
from ..uart.modules import MODULES
from ..uart.serial_worker import available_ports
from .common import Card, hbox, label, set_pill

BAUDS = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1000000]
FTYPE_COLOR = {"REQ": C["amber"], "CNF": C["teal"], "IND": C["violet"], "RSP": "#5fa8ff",
               "RAW": "#e8eef5", "TEXT": "#e8eef5", "": C["muted"]}


class UartPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.ctl = mw.uart
        self.entries = []
        self.param_edits: list[QWidget] = []
        self.current_cmd = None
        s = mw.settings

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # --- Verbindung --------------------------------------------------
        conn = Card("COM-Port (Evaluation-Board / USB-Stick)")
        self.port = QComboBox()
        self.port.setMinimumWidth(260)
        self.btn_ports = QPushButton("⟳")
        self.btn_ports.setToolTip("Port-Liste aktualisieren")
        self.btn_ports.setFixedWidth(40)
        self.btn_ports.clicked.connect(self.refresh_ports)
        self.module = QComboBox()
        for m in MODULES:
            self.module.addItem(f"{m.label}   ·   {m.family}", m.key)
        self.module.setCurrentIndex(max(0, self.module.findData(self.ctl.module.key)))
        self.module.currentIndexChanged.connect(self._module_changed)
        self.baud = QComboBox()
        self.baud.setEditable(True)
        for b in BAUDS:
            self.baud.addItem(str(b))
        self.baud.setCurrentText(str(s.get("uart_baud") or self.ctl.module.baud))
        self.fmt = QComboBox()
        for f in ("8N1", "8E1", "8O1", "8N2", "7E1"):
            self.fmt.addItem(f)
        self.fmt.setCurrentText(s.get("uart_fmt") or "8N1")
        self.flow = QComboBox()
        self.flow.addItem("Keine Flusssteuerung", "none")
        self.flow.addItem("RTS/CTS", "rtscts")
        self.flow.addItem("XON/XOFF", "xonxoff")
        self.btn_open = QPushButton("Öffnen")
        self.btn_open.setObjectName("Primary")
        self.btn_open.setMinimumWidth(110)
        self.btn_open.clicked.connect(self.toggle_open)
        self.pill = QLabel()
        self.pill.setObjectName("Pill")
        self.pill.setFixedHeight(24)
        conn.lay.addWidget(hbox(label("Port", "Muted"), self.port, self.btn_ports, label("Modul", "Muted"),
                                self.module, None, self.pill, self.btn_open))
        self.dtr = QCheckBox("DTR")
        self.rts = QCheckBox("RTS")
        self.dtr.toggled.connect(lambda v: self.ctl.worker.set_lines(dtr=v))
        self.rts.toggled.connect(lambda v: self.ctl.worker.set_lines(rts=v))
        self.btn_rst = QPushButton("Reset-Impuls")
        self.btn_rst.setToolTip("Kurzer Impuls auf der gewählten Leitung (Evaluation-Board: RESET / WAKE_UP)")
        self.pulse_line = QComboBox()
        self.pulse_line.addItems(["DTR", "RTS"])
        self.btn_rst.clicked.connect(lambda: self.ctl.worker.pulse(self.pulse_line.currentText().lower()))
        self.raw = QCheckBox("Transparenter Modus (keine Frame-Auswertung)")
        self.raw.toggled.connect(self.ctl.set_raw_mode)
        conn.lay.addWidget(hbox(label("Baud", "Muted"), self.baud, self.fmt, self.flow, None,
                                self.dtr, self.rts, self.pulse_line, self.btn_rst, self.raw))
        root.addWidget(conn)

        # --- Hauptbereich ------------------------------------------------
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(10)

        # Befehle
        cmdc = Card("Befehle")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Befehl suchen …")
        self.search.textChanged.connect(self._filter_tree)
        cmdc.lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.currentItemChanged.connect(self._cmd_selected)
        self.tree.itemDoubleClicked.connect(lambda *_: self.send_current())
        self.tree.setStyleSheet(f"QTreeWidget {{ background:{C['panel']}; border:1px solid {C['border']}; }}"
                                f"QTreeWidget::item {{ padding:3px; }}"
                                f"QTreeWidget::item:selected {{ background:{C['panel3']}; color:{C['amber']}; }}")
        cmdc.lay.addWidget(self.tree, 3)
        self.cmd_title = label("", "Accent")
        self.cmd_desc = label("", "Muted")
        self.cmd_desc.setWordWrap(True)
        cmdc.lay.addWidget(self.cmd_title)
        cmdc.lay.addWidget(self.cmd_desc)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(6)
        cmdc.lay.addWidget(self.form_host)
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        self.preview.setObjectName("Payload")
        cmdc.lay.addWidget(self.preview)
        self.rep = QSpinBox()
        self.rep.setRange(1, 100000)
        self.rep.setPrefix("× ")
        self.rep_int = QSpinBox()
        self.rep_int.setRange(10, 3_600_000)
        self.rep_int.setValue(500)
        self.rep_int.setSuffix(" ms")
        self.btn_send_cmd = QPushButton("Befehl senden")
        self.btn_send_cmd.setObjectName("Primary")
        self.btn_send_cmd.clicked.connect(self.send_current)
        cmdc.lay.addWidget(hbox(self.rep, self.rep_int, None, self.btn_send_cmd))
        split.addWidget(cmdc)

        # Protokoll
        logc = Card("Protokoll")
        self.f = {}
        boxes = []
        for key, text in (("REQ", "REQ"), ("CNF", "CNF"), ("IND", "IND"),
                          ("RSP", "RSP"), ("RAW", "Daten/Text"), ("INFO", "Info")):
            cb = QCheckBox(text)
            cb.setChecked(True)
            cb.toggled.connect(self.rebuild_log)
            col = FTYPE_COLOR.get(key, C["muted"])
            cb.setStyleSheet(f"QCheckBox {{ color:{col}; }}")
            cb.setToolTip({"REQ": "Anfragen", "CNF": "Bestätigungen", "IND": "Meldungen des Moduls",
                           "RSP": "Antworten"}.get(key, text))
            self.f[key] = cb
            boxes.append(cb)
        self.view = QComboBox()
        self.view.addItems(["HEX", "ASCII", "HEX + ASCII"])
        self.view.setCurrentIndex(2)
        self.view.currentIndexChanged.connect(self.rebuild_log)
        self.btn_auto = QPushButton("Autoscroll")
        self.btn_auto.setCheckable(True)
        self.btn_auto.setChecked(True)
        b_clear = QPushButton("Leeren")
        b_clear.clicked.connect(self._clear)
        b_save = QPushButton("Speichern …")
        b_save.clicked.connect(self._save)
        logc.lay.addWidget(hbox(*boxes, None, spacing=12))
        logc.lay.addWidget(hbox(label("Anzeige", "Muted"), self.view, None, self.btn_auto, b_clear, b_save))
        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(40000)
        logc.lay.addWidget(self.log, 1)
        self.stats = label("", "Muted")
        logc.lay.addWidget(self.stats)

        self.mode = QComboBox()
        self.mode.addItem("Frame (CMD + Daten)", "frame")
        self.mode.addItem("HEX roh", "hex")
        self.mode.addItem("Text", "text")
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.eol = QComboBox()
        self.eol.addItems(["kein Zeilenende", "CR", "LF", "CR LF"])
        self.input = QLineEdit()
        self.input.setObjectName("Payload")
        self.input.returnPressed.connect(self.send_input)
        self.btn_send = QPushButton("Senden")
        self.btn_send.setObjectName("Primary")
        self.btn_send.clicked.connect(self.send_input)
        self.mode.setToolTip("Frame: STX, Länge und Prüfsumme werden automatisch ergänzt")
        logc.lay.addWidget(hbox(self.mode, self.input, self.eol, self.btn_send))
        self.input.setMinimumWidth(220)
        split.addWidget(logc)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([430, 700])
        root.addWidget(split, 1)

        # --- Signale ------------------------------------------------------
        self.ctl.log.connect(self._on_log)
        self.ctl.state.connect(self._on_state)
        self.repeat_timer = QTimer(self)
        self.repeat_timer.timeout.connect(self._repeat_tick)
        self.repeat_left = 0
        self.stat_timer = QTimer(self)
        self.stat_timer.timeout.connect(self._update_stats)
        self.stat_timer.start(1000)

        self.refresh_ports()
        self._fill_tree()
        self._mode_changed()
        self._on_state(False, "")

    # ------------------------------------------------------------------ Port
    def refresh_ports(self):
        cur = self.port.currentData()
        self.port.clear()
        ports = available_ports()
        for dev, desc in ports:
            self.port.addItem(f"{dev}   {desc}", dev)
        if not ports:
            self.port.addItem("— kein COM-Port gefunden —", None)
        want = cur or self.mw.settings.get("uart_port")
        i = self.port.findData(want)
        if i >= 0:
            self.port.setCurrentIndex(i)

    def toggle_open(self):
        if self.ctl.is_open:
            self.ctl.close()
            return
        port = self.port.currentData()
        if not port:
            self.mw.toast("Kein COM-Port ausgewählt.", error=True)
            return
        try:
            baud = int(self.baud.currentText())
        except ValueError:
            self.mw.toast("Ungültige Baudrate.", error=True)
            return
        fmt = self.fmt.currentText()
        s = self.mw.settings
        s.data.update({"uart_port": port, "uart_baud": baud, "uart_fmt": fmt})
        s.save()
        self.ctl.open(port, baud, int(fmt[0]), fmt[1], float(fmt[2]), self.flow.currentData())

    def _on_state(self, is_open, port):
        set_pill(self.pill, f"{port} OFFEN" if is_open else "GESCHLOSSEN", "ok" if is_open else "")
        self.btn_open.setText("Schließen" if is_open else "Öffnen")
        self.btn_open.setObjectName("Danger" if is_open else "Primary")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        for w in (self.port, self.btn_ports, self.baud, self.fmt, self.flow):
            w.setEnabled(not is_open)
        for w in (self.dtr, self.rts, self.btn_rst, self.pulse_line, self.btn_send, self.btn_send_cmd):
            w.setEnabled(is_open)
        if not is_open:
            self.repeat_timer.stop()
        self.mw.update_uart_pill(is_open, port)

    def _module_changed(self):
        key = self.module.currentData()
        self.ctl.set_module(key)
        m = self.ctl.module
        if not self.ctl.is_open:
            self.baud.setCurrentText(str(m.baud))
        self._fill_tree()
        self._mode_changed()

    # ------------------------------------------------------------------ Befehle
    def _fill_tree(self):
        self.tree.clear()
        m = self.ctl.module
        groups = {}
        for c in m.commands:
            g = groups.get(c.group)
            if g is None:
                g = QTreeWidgetItem([c.group.upper()])
                g.setFlags(Qt.ItemIsEnabled)
                g.setForeground(0, QColor(C["muted"]))
                self.tree.addTopLevelItem(g)
                groups[c.group] = g
            text = c.at if c.at else f"{c.name}   0x{c.code:02X}"
            it = QTreeWidgetItem([text])
            it.setData(0, Qt.UserRole, c)
            if c.danger:
                it.setForeground(0, QColor(C["red"]))
            g.addChild(it)
        self.tree.expandAll()
        if not m.commands:
            self.cmd_title.setText("Keine Befehlsliste")
            self.cmd_desc.setText(m.note)
        else:
            self.cmd_title.setText(m.label)
            self.cmd_desc.setText(m.note)
        self._clear_form()

    def _filter_tree(self, text):
        t = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            any_vis = False
            for j in range(g.childCount()):
                it = g.child(j)
                c = it.data(0, Qt.UserRole)
                vis = not t or t in it.text(0).lower() or t in (c.desc or "").lower()
                it.setHidden(not vis)
                any_vis |= vis
            g.setHidden(not any_vis)

    def _clear_form(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.param_edits = []
        self.current_cmd = None
        self.preview.clear()

    def _cmd_selected(self, item, _prev=None):
        c = item.data(0, Qt.UserRole) if item else None
        self._clear_form()
        if c is None:
            return
        self.current_cmd = c
        m = self.ctl.module
        if c.at:
            self.cmd_title.setText(c.name)
            self.cmd_desc.setText(c.desc or "Vorlage bearbeiten und senden (CR LF wird angehängt).")
            e = QLineEdit(c.at)
            e.setObjectName("Payload")
            e.textChanged.connect(self._update_preview)
            self.form.addRow("Befehl", e)
            self.param_edits = [e]
        else:
            self.cmd_title.setText(f"CMD_{c.name.upper()}_REQ   0x{c.code:02X}")
            warn = "  ⚠ Setzt das Modul zurück!" if c.danger else ""
            self.cmd_desc.setText((c.desc or "") + warn)
            for p in c.params:
                if p.kind == "choice":
                    w = QComboBox()
                    for val, txt in p.choices:
                        w.addItem(txt, val)
                    w.setCurrentIndex(max(0, w.findData(p.default)))
                    w.currentIndexChanged.connect(self._update_preview)
                else:
                    w = QLineEdit(p.default)
                    if p.kind in ("hex", "data", "mac"):
                        w.setObjectName("Payload")
                    w.setPlaceholderText({"hex": "HEX", "data": "HEX", "mac": "6 Bytes HEX, LSB zuerst",
                                          "ascii": "Text", "u8": "0…255", "i8": "-128…127",
                                          "u16": "0…65535", "u32": "Zahl oder 0x…"}.get(p.kind, ""))
                    w.textChanged.connect(self._update_preview)
                if p.hint:
                    w.setToolTip(p.hint)
                self.form.addRow(p.name, w)
                self.param_edits.append(w)
            if c.name in ("Get", "Set") and m.settings:
                hint = label("Tipp: Einstellungen komfortabel unter »Modul-Einstellungen« lesen/schreiben.", "Muted")
                hint.setWordWrap(True)
                self.form.addRow(hint)
        self._update_preview()

    def _values(self):
        out = []
        for w in self.param_edits:
            out.append(w.currentData() if isinstance(w, QComboBox) else w.text())
        return out

    def _build_current(self) -> bytes:
        c = self.current_cmd
        m = self.ctl.module
        if c.at:
            return self._values()[0].encode("latin-1") + b"\r\n"
        payload = command_payload(m, c, self._values())
        return build_frame(m.proto, c.code, payload)

    def _update_preview(self):
        if self.current_cmd is None:
            self.preview.clear()
            return
        try:
            data = self._build_current()
            if self.current_cmd.at:
                self.preview.setText(hexs(data))
            else:
                self.preview.setText(hexs(data))
            self.preview.setStyleSheet("")
        except ValueError as exc:
            self.preview.setText(str(exc))
            self.preview.setStyleSheet(f"color:{C['red']}")

    def send_current(self):
        if self.current_cmd is None:
            return
        if not self.ctl.is_open:
            self.mw.toast("Zuerst den COM-Port öffnen.", error=True)
            return
        if self.current_cmd.danger:
            if QMessageBox.question(self, "Befehl senden",
                                    f"{self.current_cmd.name} setzt alle Einstellungen des Moduls zurück. Fortfahren?") \
                    != QMessageBox.Yes:
                return
        try:
            data = self._build_current()
        except ValueError as exc:
            self.mw.toast(str(exc), error=True)
            return
        self._pending = (data, self.current_cmd)
        self.repeat_left = self.rep.value()
        self._repeat_tick()
        if self.repeat_left > 0:
            self.repeat_timer.start(self.rep_int.value())

    def _repeat_tick(self):
        if self.repeat_left <= 0 or not self.ctl.is_open:
            self.repeat_timer.stop()
            return
        data, c = self._pending
        if c.at:
            self.ctl.send_raw(data, c.name)
        else:
            self.ctl.send_frame(data)
        self.repeat_left -= 1
        if self.repeat_left <= 0:
            self.repeat_timer.stop()

    # ------------------------------------------------------------------ Freie Eingabe
    def _mode_changed(self):
        m = self.ctl.module
        has_frames = m.proto in ("cmd16", "cmd8", "metis")
        model = self.mode.model()
        model.item(0).setEnabled(has_frames)
        if not has_frames and self.mode.currentData() == "frame":
            self.mode.setCurrentIndex(2)
        if m.proto == "at" and self.mode.currentData() == "text":
            self.eol.setCurrentIndex(3)
        mode = self.mode.currentData()
        self.eol.setEnabled(mode == "text")
        self.input.setPlaceholderText({
            "frame": "CMD und Daten in HEX, z. B. 01 = GetState · 10 02 = Get Einstellung 2",
            "hex": "Bytes in HEX, werden unverändert gesendet",
            "text": "Text, z. B. AT-Befehl – Escapes \\r \\n \\xNN",
        }[mode])

    def send_input(self):
        mode = self.mode.currentData()
        text = self.input.text()
        try:
            if mode == "text":
                from ..protocol import Encoding, from_text
                data = from_text(text, Encoding.ASCII) + [b"", b"\r", b"\n", b"\r\n"][self.eol.currentIndex()]
                if not data:
                    return
                self.ctl.send_raw(data, "Text")
            else:
                b = bytes.fromhex("".join(text.replace("0x", "").replace(",", " ").split()))
                if not b:
                    return
                if mode == "hex":
                    self.ctl.send_raw(b, "HEX roh")
                else:
                    self.ctl.send_command(b[0], b[1:])
        except ValueError:
            self.mw.toast("Ungültige HEX-Eingabe.", error=True)

    # ------------------------------------------------------------------ Protokoll
    def _group(self, e):
        if e.kind in ("info", "error"):
            return "INFO"
        if e.ftype in ("RAW", "TEXT"):
            return "RAW"
        return e.ftype or "INFO"

    def _fmt(self, e) -> str:
        t = time.strftime("%H:%M:%S", time.localtime(e.ts)) + f".{int((e.ts % 1) * 1000):03d}"
        if e.kind == "error":
            col, arrow = C["red"], "✖"
        elif e.kind == "info":
            col, arrow = C["muted"], "•"
        else:
            col = FTYPE_COLOR.get(e.ftype, C["text"])
            arrow = "▲" if e.kind == "tx" else "▼"
        tag = f"[{e.ftype}] " if e.ftype in ("REQ", "CNF", "IND", "RSP") else ""
        out = (f'<span style="color:#4f5d70">{t}</span>&nbsp;&nbsp;'
               f'<span style="color:{col}">{arrow} {html.escape(tag + e.text)}</span>')
        if e.data:
            v = self.view.currentIndex()
            lines = []
            if v in (0, 2):
                lines.append(hexs(e.data))
            if v in (1, 2):
                asc = "".join(chr(b) if 32 <= b < 127 else ("↵" if b == 10 else "·") for b in e.data)
                lines.append(asc if v == 1 else f'<span style="color:#7a889a">{html.escape(asc)}</span>')
            pad = "&nbsp;" * 16
            body = "<br>".join(pad + (ln if ln.startswith("<span") else html.escape(ln)) for ln in lines)
            out += f'<br><span style="color:#e8eef5">{body}</span>'
        return out

    def _on_log(self, e):
        self.entries.append(e)
        if len(self.entries) > 20000:
            del self.entries[:2000]
        if self.f[self._group(e)].isChecked():
            self.log.appendHtml(self._fmt(e))
            if self.btn_auto.isChecked():
                self.log.moveCursor(QTextCursor.End)

    def rebuild_log(self):
        self.log.clear()
        chunk = [self._fmt(e) for e in self.entries if self.f[self._group(e)].isChecked()]
        if chunk:
            self.log.appendHtml("<br>".join(chunk[-5000:]))
        if self.btn_auto.isChecked():
            self.log.moveCursor(QTextCursor.End)

    def _clear(self):
        self.entries.clear()
        self.log.clear()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "UART-Protokoll speichern",
                                              f"uart_{time.strftime('%Y%m%d_%H%M%S')}.txt",
                                              "Textdatei (*.txt);;CSV (*.csv)")
        if not path:
            return
        csv = path.lower().endswith(".csv")
        with open(path, "w", encoding="utf-8") as f:
            if csv:
                f.write("Zeit;Richtung;Typ;Text;HEX;ASCII\n")
            for e in self.entries:
                t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.ts)) + f".{int((e.ts % 1) * 1000):03d}"
                asc = "".join(chr(b) if 32 <= b < 127 else "." for b in e.data)
                if csv:
                    f.write(f'{t};{e.kind};{e.ftype};"{e.text}";{hexs(e.data)};"{asc}"\n')
                else:
                    f.write(f"{t}  {e.kind:<5} {e.ftype:<4} {e.text}\n")
                    if e.data:
                        f.write(f"      HEX:   {hexs(e.data)}\n      ASCII: {asc}\n")
        self.mw.toast(f"Protokoll gespeichert: {path}")

    def _update_stats(self):
        w = self.ctl.worker
        self.stats.setText(f"TX {w.tx_bytes} Bytes  ·  RX {w.rx_bytes} Bytes  ·  {len(self.entries)} Einträge")

    def checksum_helper(self, data: bytes) -> int:
        return xor(data)
