"""UART-Terminal: Verbindung in drei Schritten, Befehlskacheln, Frame-Grafik und Protokoll-Analyse."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..theme import C
from ..uart.framing import build_frame, command_payload, hexs
from ..uart.modules import MODULES, STATUS_TEXT
from ..uart.serial_worker import available_ports
from .common import Card, hbox, label, set_pill
from .detect_dialog import DetectDialog
from .help_texts import PARAM_HELP, TYPE_HELP
from .widgets import FlowLayout, FrameView, HelpPanel, Kpi, StepBadge, Tile, help_dot

BAUDS = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1000000]
FTYPE_COLOR = {"REQ": C["amber"], "CNF": C["teal"], "IND": C["violet"], "RSP": "#5fa8ff",
               "RAW": "#c9d3df", "TEXT": "#c9d3df", "": C["muted"]}
PROTO_TEXT = {"cmd16": "Befehlsframes · STX 0x02 · Länge 2 Byte · XOR",
              "cmd8": "Befehlsframes · STX 0x02 · Länge 1 Byte · XOR",
              "metis": "Befehlsframes · STX 0xFF · Länge 1 Byte · XOR",
              "at": "AT-Befehle · Textzeilen mit CR LF",
              "text": "Text / transparent · keine Frames"}
COL_T, COL_DIR, COL_TYPE, COL_NAME, COL_LEN = range(5)


class UartPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.ctl = mw.uart
        self.entries = []
        self.param_edits: list[QWidget] = []
        self.current_cmd = None
        self.tiles: list[Tile] = []
        self.group = None
        self.stats = {"tx": 0, "rx": 0, "err": 0, "rssi": "–"}
        s = mw.settings

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page.addWidget(scroll)
        inner = QWidget()
        inner.setObjectName("Root")
        scroll.setWidget(inner)
        outer = QVBoxLayout(inner)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)
        outer.addWidget(HelpPanel("uart", s))

        # ------------------------------------------------ Schritte 1–3
        steps = QHBoxLayout()
        steps.setSpacing(10)

        # 1 Port
        b1, l1, self.st1 = self._step(1, "PORT", "Board/USB-Stick einstecken – erscheint automatisch")
        self.port = QComboBox()
        self.port.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.port.setMinimumContentsLength(12)
        self.btn_ports = QPushButton("⟳")
        self.btn_ports.setFixedWidth(36)
        self.btn_ports.setToolTip("Port-Liste neu einlesen")
        self.btn_ports.clicked.connect(self.refresh_ports)
        l1.addWidget(hbox(self.port, self.btn_ports, spacing=6))
        self.chip = label("", "Muted")
        self.chip.setWordWrap(True)
        l1.addWidget(self.chip)
        steps.addWidget(b1, 3)

        # 2 Modul
        b2, l2, self.st2 = self._step(2, "MODUL", "Legt Befehle, Frame-Format und Baudrate fest")
        self.module = QComboBox()
        self.module.setMaxVisibleItems(24)
        last_vendor = None
        for m in MODULES:
            if m.vendor != last_vendor:
                last_vendor = m.vendor
                self.module.addItem(f"──  {m.vendor.upper()}  ──", None)
                it = self.module.model().item(self.module.count() - 1)
                it.setEnabled(False)
                it.setForeground(QColor(C["teal"]))
            self.module.addItem(f"   {m.label}  ·  {m.family}", m.key)
        self.module.setCurrentIndex(max(0, self.module.findData(self.ctl.module.key)))
        self.module.currentIndexChanged.connect(self._module_changed)
        self.module.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.module.setMinimumContentsLength(14)
        self.btn_detect = QPushButton("Erkennen …")
        self.btn_detect.setToolTip("Ports, Baudraten und Protokolle automatisch durchprobieren")
        self.btn_detect.clicked.connect(self.detect)
        l2.addWidget(hbox(self.module, self.btn_detect, spacing=6))
        self.proto_lbl = label("", "Muted")
        self.proto_lbl.setWordWrap(True)
        l2.addWidget(self.proto_lbl)
        steps.addWidget(b2, 3)

        # 3 Verbinden
        b3, l3, self.st3 = self._step(3, "VERBINDEN", "Port mit den Einstellungen öffnen")
        self.baud = QComboBox()
        self.baud.setEditable(True)
        for b in BAUDS:
            self.baud.addItem(str(b))
        self.baud.setCurrentText(str(s.get("uart_baud") or self.ctl.module.baud))
        self.baud.setToolTip("Baudrate – Standard des Moduls wird beim Modulwechsel vorgeschlagen")
        self.fmt = QComboBox()
        for f in ("8N1", "8E1", "8O1", "8N2", "7E1"):
            self.fmt.addItem(f)
        self.fmt.setCurrentText(s.get("uart_fmt") or "8N1")
        self.fmt.setToolTip("Datenbits, Parität (N/E/O), Stoppbits")
        self.flow = QComboBox()
        self.flow.addItem("ohne Fluss", "none")
        self.flow.addItem("RTS/CTS", "rtscts")
        self.flow.addItem("XON/XOFF", "xonxoff")
        self.flow.setToolTip("Flusssteuerung – bei Würth-Boards meist ohne")
        self.btn_open = QPushButton("Verbinden")
        self.btn_open.setObjectName("Primary")
        self.btn_open.setMinimumWidth(120)
        self.btn_open.clicked.connect(self.toggle_open)
        l3.addWidget(hbox(self.baud, self.fmt, self.flow, None, spacing=6))
        self.dtr = QCheckBox("DTR")
        self.rts = QCheckBox("RTS")
        self.dtr.setChecked(bool(s.get("uart_dtr", False)))
        self.rts.setChecked(bool(s.get("uart_rts", False)))
        self.dtr.toggled.connect(lambda v: self.ctl.worker.set_lines(dtr=v))
        self.rts.toggled.connect(lambda v: self.ctl.worker.set_lines(rts=v))
        self.pulse_line = QComboBox()
        self.pulse_line.addItems(["DTR", "RTS"])
        self.btn_rst = QPushButton("Reset-Impuls")
        self.btn_rst.clicked.connect(lambda: self.ctl.worker.pulse(self.pulse_line.currentText().lower()))
        self.raw = QCheckBox("Transparenter Modus")
        self.raw.toggled.connect(self.ctl.set_raw_mode)
        self.pill = QLabel()
        self.pill.setObjectName("Pill")
        self.pill.setFixedHeight(24)
        l3.addWidget(hbox(self.dtr, self.rts, help_dot(
            "Steuerleitungen des USB-Seriell-Wandlers. Ihr Zustand wird schon beim Öffnen gesetzt – "
            "auf Evaluation-Boards hängt daran oft RESET oder WAKE_UP des Moduls."),
            None, self.pulse_line, self.btn_rst, spacing=6))
        l3.addWidget(hbox(self.raw, help_dot(
            "Transparenter Modus: keine Frame-Auswertung, alle Bytes werden unverändert angezeigt."),
            None, self.pill, self.btn_open, spacing=6))
        steps.addWidget(b3, 4)
        outer.addLayout(steps)

        # ------------------------------------------------ Hauptbereich
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(10)
        split.addWidget(self._build_commands())
        split.addWidget(self._build_log())
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 6)
        split.setSizes([600, 720])
        split.setMinimumHeight(720)
        outer.addWidget(split, 1)

        # ------------------------------------------------ Signale
        self.ctl.log.connect(self._on_log)
        self.ctl.state.connect(self._on_state)
        self.repeat_timer = QTimer(self)
        self.repeat_timer.timeout.connect(self._repeat_tick)
        self.repeat_left = 0
        self.stat_timer = QTimer(self)
        self.stat_timer.timeout.connect(self._update_kpis)
        self.stat_timer.start(700)
        self.known_ports: set[str] = set()
        self.hotplug = QTimer(self)
        self.hotplug.timeout.connect(self._hotplug_tick)
        self.hotplug.start(2000)

        self.port.currentIndexChanged.connect(self._port_info)
        self.refresh_ports()
        self.known_ports = {p.device for p in self.port_infos}
        self._fill_commands()
        self._mode_changed()
        self._on_state(False, "")

    # ================================================================ Aufbau
    def _step(self, n, title, tip):
        box = QFrame()
        box.setObjectName("StepBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        badge = StepBadge(n)
        t = QLabel(title)
        t.setObjectName("StepTitle")
        sub = label(tip, "Muted")
        sub.setStyleSheet("font-size:8pt;")
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(badge)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(t)
        col.addWidget(sub)
        head.addLayout(col, 1)
        lay.addLayout(head)
        return box, lay, badge

    def _build_commands(self):
        card = Card("Befehle")
        # Gruppen
        self.group_host = QWidget()
        self.group_flow = FlowLayout(self.group_host, 6)
        sp = self.group_host.sizePolicy()
        sp.setHeightForWidth(True)
        self.group_host.setSizePolicy(sp)
        self.group_btns = QButtonGroup(self)
        self.group_btns.setExclusive(True)
        card.lay.addWidget(self.group_host)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Befehl suchen (Name oder Beschreibung) …")
        self.search.textChanged.connect(self._apply_tile_filter)
        card.lay.addWidget(self.search)
        # Kacheln
        self.tile_host = QWidget()
        self.tile_flow = FlowLayout(self.tile_host, 8)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.tile_host)
        sc.setMinimumHeight(200)
        card.lay.addWidget(sc, 3)

        # Ausgewählter Befehl
        sel = QFrame()
        sel.setObjectName("Analysis")
        sl = QVBoxLayout(sel)
        sl.setContentsMargins(12, 10, 12, 10)
        sl.setSpacing(6)
        self.cmd_title = label("", "Accent")
        self.cmd_title.setWordWrap(True)
        self.cmd_desc = label("", "Muted")
        self.cmd_desc.setWordWrap(True)
        sl.addWidget(self.cmd_title)
        sl.addWidget(self.cmd_desc)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(6)
        sl.addWidget(self.form_host)
        sl.addWidget(label("SO WIRD GESENDET", "CardTitle"))
        self.preview = FrameView()
        sl.addWidget(self.preview)
        self.preview_err = label("", "Muted")
        self.preview_err.setWordWrap(True)
        sl.addWidget(self.preview_err)
        self.rep = QSpinBox()
        self.rep.setRange(1, 100000)
        self.rep.setPrefix("Anzahl ")
        self.rep.setToolTip("Wie oft der Befehl gesendet wird")
        self.rep_int = QSpinBox()
        self.rep_int.setRange(10, 600_000)
        self.rep_int.setValue(500)
        self.rep_int.setPrefix("alle ")
        self.rep_int.setToolTip("Abstand zwischen Wiederholungen")
        self.rep_int.setSuffix(" ms")
        self.btn_send_cmd = QPushButton("Befehl senden")
        self.btn_send_cmd.setObjectName("Primary")
        self.btn_send_cmd.setMinimumWidth(140)
        self.btn_send_cmd.clicked.connect(self.send_current)
        self.rep.setRange(1, 99999)
        sl.addWidget(hbox(self.rep, self.rep_int, None, spacing=6))
        sl.addWidget(hbox(None, self.btn_send_cmd))
        card.lay.addWidget(sel, 2)
        return card

    def _build_log(self):
        card = Card("Protokoll")
        self.k_tx = Kpi("Gesendet", "0", C["amber"], "Gesendete Frames/Zeilen")
        self.k_rx = Kpi("Empfangen", "0", C["teal"], "Empfangene Frames/Zeilen")
        self.k_err = Kpi("Fehler", "0", C["red"], "Bestätigungen mit Status ≠ 00 und Fehlermeldungen")
        self.k_rssi = Kpi("Letzter RSSI", "–", C["violet"], "Signalstärke der zuletzt empfangenen Funkdaten")
        self.k_bytes = Kpi("Bytes TX / RX", "0 / 0", None, "Übertragene Bytes am COM-Port")
        kh = QWidget()
        kl = FlowLayout(kh, 8)
        sp = kh.sizePolicy()
        sp.setHeightForWidth(True)
        kh.setSizePolicy(sp)
        for k in (self.k_tx, self.k_rx, self.k_err, self.k_rssi, self.k_bytes):
            k.setMinimumWidth(104)
            kl.addWidget(k)
        card.lay.addWidget(kh)

        self.f = {}
        boxes = []
        for key, text in (("REQ", "Anfragen"), ("CNF", "Bestätigungen"), ("IND", "Meldungen"),
                          ("RSP", "Antworten"), ("RAW", "Daten/Text"), ("INFO", "Info")):
            cb = QCheckBox(text)
            cb.setChecked(True)
            cb.toggled.connect(self.rebuild_log)
            col = FTYPE_COLOR.get(key, C["muted"])
            cb.setStyleSheet(f"QCheckBox {{ color:{col}; }}")
            cb.setToolTip(TYPE_HELP.get(key, "Statusmeldungen des Programms"))
            self.f[key] = cb
            boxes.append(cb)
        self.btn_auto = QPushButton("Autoscroll")
        self.btn_auto.setCheckable(True)
        self.btn_auto.setChecked(True)
        b_clear = QPushButton("Leeren")
        b_clear.clicked.connect(self._clear)
        b_save = QPushButton("Speichern …")
        b_save.clicked.connect(self._save)
        fh = QWidget()
        fl = FlowLayout(fh, 12)
        sp = fh.sizePolicy()
        sp.setHeightForWidth(True)
        fh.setSizePolicy(sp)
        for b in [label("Anzeigen:", "Muted")] + boxes:
            fl.addWidget(b)
        card.lay.addWidget(fh)
        card.lay.addWidget(hbox(None, self.btn_auto, b_clear, b_save, spacing=8))

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ZEIT", "", "TYP", "BEFEHL / INHALT", "BYTES"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_T, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_DIR, QHeaderView.Fixed)
        self.table.setColumnWidth(COL_DIR, 28)
        hh.setSectionResizeMode(COL_TYPE, QHeaderView.Fixed)
        self.table.setColumnWidth(COL_TYPE, 58)
        hh.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_LEN, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._row_selected)
        self.table.setMinimumHeight(200)
        card.lay.addWidget(self.table, 3)

        an = QFrame()
        an.setObjectName("Analysis")
        al = QVBoxLayout(an)
        al.setContentsMargins(12, 8, 12, 8)
        al.setSpacing(5)
        al.addWidget(hbox(label("FRAME-ANALYSE", "CardTitle"), help_dot(
            "Zeile im Protokoll anklicken: Der Frame wird in Startbyte, Befehl, Länge, Daten und "
            "Prüfsumme zerlegt und erklärt."), None))
        self.an_view = FrameView()
        self.an_view.clear("Zeile im Protokoll anklicken, um den Frame zu zerlegen")
        al.addWidget(self.an_view)
        self.an_text = QLabel("")
        self.an_text.setTextFormat(Qt.RichText)
        self.an_text.setWordWrap(True)
        self.an_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        al.addWidget(self.an_text)
        card.lay.addWidget(an, 2)

        self.mode = QComboBox()
        self.mode.addItem("Frame (CMD + Daten)", "frame")
        self.mode.addItem("HEX roh", "hex")
        self.mode.addItem("Text", "text")
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.mode.setToolTip("Frame: Startbyte, Länge und Prüfsumme werden automatisch ergänzt")
        self.eol = QComboBox()
        self.eol.addItems(["kein Zeilenende", "CR", "LF", "CR LF"])
        self.input = QLineEdit()
        self.input.setObjectName("Payload")
        self.input.setMinimumWidth(200)
        self.input.returnPressed.connect(self.send_input)
        self.btn_send = QPushButton("Senden")
        self.btn_send.setObjectName("Primary")
        self.btn_send.clicked.connect(self.send_input)
        card.lay.addWidget(hbox(label("Freie Eingabe", "Muted"), help_dot(
            "Frame: aus Befehl + Daten wird automatisch ein gültiger Frame.\nHEX roh: Bytes unverändert.\n"
            "Text: z. B. AT-Befehle, mit wählbarem Zeilenende."), self.mode, spacing=6))
        self.btn_ctrlz = QPushButton("Strg+Z")
        self.btn_ctrlz.setToolTip("Sendet 0x1A – schließt z. B. SMS-Text (AT+CMGS) oder Daten bei AT+CIPSEND ab")
        self.btn_ctrlz.clicked.connect(lambda: self.ctl.send_raw(b"\x1a", "Strg+Z"))
        self.btn_esc = QPushButton("Esc")
        self.btn_esc.setToolTip("Sendet 0x1B – bricht eine Eingabe nach »>« ab")
        self.btn_esc.clicked.connect(lambda: self.ctl.send_raw(b"\x1b", "Esc"))
        card.lay.addWidget(hbox(self.input, self.eol, self.btn_ctrlz, self.btn_esc, self.btn_send))
        return card

    # ================================================================ Port
    def refresh_ports(self):
        cur = self.port.currentData()
        self.port.blockSignals(True)
        self.port.clear()
        self.port_infos = available_ports()
        for p in self.port_infos:
            self.port.addItem(p.label, p.device)
            tip = [p.chip]
            if p.manufacturer:
                tip.append(f"Hersteller: {p.manufacturer}")
            if p.product:
                tip.append(f"Produkt: {p.product}")
            if p.serial_number:
                tip.append(f"Seriennummer: {p.serial_number}")
            if p.vid is not None:
                tip.append(f"VID:PID {p.vid:04X}:{p.pid or 0:04X}")
            if p.driver_hint:
                tip.append(p.driver_hint)
            self.port.setItemData(self.port.count() - 1, "\n".join(tip), Qt.ToolTipRole)
        if not self.port_infos:
            self.port.addItem("— kein COM-Port gefunden —", None)
        want = cur or self.mw.settings.get("uart_port")
        i = self.port.findData(want)
        if i >= 0:
            self.port.setCurrentIndex(i)
        self.port.blockSignals(False)
        self._port_info()

    def _port_info(self):
        dev = self.port.currentData()
        info = next((p for p in getattr(self, "port_infos", []) if p.device == dev), None)
        self.st1.set_done(info is not None)
        if info is None:
            self.chip.setText("Kein Port – alle USB-Seriell-Wandler werden unterstützt "
                              "(FTDI, CP210x, CH340/CH9102, PL2303, MCP2221, CDC …).")
            return
        vp = f" · {info.vid:04X}:{info.pid or 0:04X}" if info.vid is not None else ""
        self.chip.setText(f"<span style='color:{C['teal']}'>●</span> {info.chip}{vp}")
        self.chip.setToolTip(info.driver_hint)

    def _hotplug_tick(self):
        if self.ctl.is_open or self.port.view().isVisible():
            return
        now = {p.device for p in available_ports()}
        if now != self.known_ports:
            added = now - self.known_ports
            removed = self.known_ports - now
            self.known_ports = now
            self.refresh_ports()
            if added:
                info = [p for p in self.port_infos if p.device in added]
                self.mw.toast("Neuer Port: " + ", ".join(f"{p.device} ({p.chip})" for p in info))
                if len(added) == 1:
                    self.port.setCurrentIndex(max(0, self.port.findData(next(iter(added)))))
            elif removed:
                self.mw.toast("Port entfernt: " + ", ".join(sorted(removed)), error=True)

    def detect(self):
        if self.ctl.is_open:
            self.ctl.close()
        dlg = DetectDialog(self, list(self.port_infos), self.port.currentData(),
                           self.dtr.isChecked(), self.rts.isChecked())
        if dlg.exec() and dlg.result_obj is not None:
            r = dlg.result_obj
            self.module.setCurrentIndex(max(0, self.module.findData(dlg.chosen_key or r.module_key)))
            self.port.setCurrentIndex(max(0, self.port.findData(r.port)))
            self.baud.setCurrentText(str(r.baud))
            self.fmt.setCurrentText("8N1")
            self.flow.setCurrentIndex(0)
            self.toggle_open()

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
        s.data.update({"uart_port": port, "uart_baud": baud, "uart_fmt": fmt,
                       "uart_dtr": self.dtr.isChecked(), "uart_rts": self.rts.isChecked()})
        s.save()
        self.ctl.open(port, baud, int(fmt[0]), fmt[1], float(fmt[2]), self.flow.currentData(),
                      self.dtr.isChecked(), self.rts.isChecked())

    def _on_state(self, is_open, port):
        set_pill(self.pill, f"{port} VERBUNDEN" if is_open else "GETRENNT", "ok" if is_open else "")
        self.st3.set_done(is_open)
        self.btn_open.setText("Trennen" if is_open else "Verbinden")
        self.btn_open.setObjectName("Danger" if is_open else "Primary")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        for w in (self.port, self.btn_ports, self.baud, self.fmt, self.flow, self.btn_detect):
            w.setEnabled(not is_open)
        for w in (self.btn_rst, self.pulse_line, self.btn_send, self.btn_send_cmd, self.btn_ctrlz, self.btn_esc):
            w.setEnabled(is_open)
        if not is_open:
            self.repeat_timer.stop()
        self.mw.update_uart_pill(is_open, port)

    def _module_changed(self):
        if self.module.currentData() is None:
            return
        self.ctl.set_module(self.module.currentData())
        if not self.ctl.is_open:
            self.baud.setCurrentText(str(self.ctl.module.baud))
        self._fill_commands()
        self._mode_changed()

    # ================================================================ Befehle
    def _fill_commands(self):
        m = self.ctl.module
        self.st2.set_done(True)
        proto = PROTO_TEXT[m.proto]
        if m.proto == "at":
            proto = "AT-Befehle · " + ("mit CR LF" if m.eol else "ohne Zeilenende")
        self.proto_lbl.setText(f"{m.vendor} · {m.family} · {proto} · Standard {m.baud} Baud")
        self.proto_lbl.setToolTip(m.note)
        for b in self.group_btns.buttons():
            self.group_btns.removeButton(b)
            b.hide()
            b.setParent(None)
            b.deleteLater()
        while self.group_flow.count():
            self.group_flow.takeAt(0)
        for t in self.tiles:
            t.hide()
            t.setParent(None)
            t.deleteLater()
        self.tiles = []
        while self.tile_flow.count():
            self.tile_flow.takeAt(0)
        groups = ["Alle"] + list(dict.fromkeys(c.group for c in m.commands))
        for g in groups:
            b = QPushButton(g)
            b.setObjectName("GroupChip")
            b.setCheckable(True)
            n = len(m.commands) if g == "Alle" else sum(1 for c in m.commands if c.group == g)
            b.setToolTip(f"{n} Befehle")
            b.clicked.connect(lambda _=False, gg=g: self._set_group(gg))
            self.group_btns.addButton(b)
            self.group_flow.addWidget(b)
        for c in m.commands:
            code = ("AT" if c.at.upper().startswith("AT") else "TXT") if c.at else (f"0x{c.code:02X}")
            if m.proto == "text" and c.at:
                code = "TXT"
            t = Tile(c, code)
            t.clicked.connect(self.select_command)
            t.double_clicked.connect(self._tile_double)
            self.tiles.append(t)
            self.tile_flow.addWidget(t)
        self.group = None
        if self.group_btns.buttons():
            self.group_btns.buttons()[0].setChecked(True)
        self._set_group("Alle")
        self._clear_form()
        if not m.commands:
            self.cmd_title.setText("Keine Befehlsliste")
            self.cmd_desc.setText(m.note + " Daten unten über »Freie Eingabe« senden.")
        else:
            self.cmd_title.setText("Befehl auswählen")
            self.cmd_desc.setText("Kachel anklicken – Parameter erscheinen hier. Doppelklick sendet sofort. " + m.note)
        self.tile_host.updateGeometry()

    def _set_group(self, g):
        self.group = g
        self._apply_tile_filter()

    def _apply_tile_filter(self):
        t = self.search.text().lower().strip()
        for tile in self.tiles:
            c = tile.cmd
            vis = (self.group in (None, "Alle") or c.group == self.group)
            if t:
                vis = vis and (t in c.name.lower() or t in (c.desc or "").lower() or t in (c.at or "").lower())
            tile.setVisible(vis)
        self.tile_flow.invalidate()
        self.tile_host.updateGeometry()

    def _clear_form(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.param_edits = []
        self.current_cmd = None
        self.preview.clear("Kein Befehl ausgewählt")
        self.preview_err.setText("")
        for t in self.tiles:
            t.set_selected(False)

    def select_command(self, c):
        """Befehl (Objekt oder Name) auswählen und Formular aufbauen."""
        if isinstance(c, str):
            c = next((x for x in self.ctl.module.commands if x.name == c), None)
            if c is None:
                return
        self._clear_form()
        self.current_cmd = c
        for t in self.tiles:
            t.set_selected(t.cmd is c)
        m = self.ctl.module
        if c.at:
            self.cmd_title.setText(c.at.split("=")[0] if m.proto == "at" else c.name)
            end = "CR LF wird angehängt" if m.eol else "es wird kein Zeilenende angehängt"
            self.cmd_desc.setText((c.desc + "  ·  " if c.desc else "") + f"Vorlage anpassen und senden – {end}.")
            e = QLineEdit(c.at)
            e.setObjectName("Payload")
            e.textChanged.connect(self._update_preview)
            self.form.addRow(hbox(label("Befehl", "Muted"), help_dot("Text des Befehls; Werte nach »=« anpassen."),
                                  spacing=4), e)
            self.param_edits = [e]
        else:
            self.cmd_title.setText(f"{c.name}   ·   CMD_{c.name.upper()}_REQ  0x{c.code:02X}")
            warn = "  ⚠ Setzt das Modul zurück!" if c.danger else ""
            self.cmd_desc.setText((c.desc or "") + warn + ("" if c.params else "  Keine Parameter nötig."))
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
                    w.setPlaceholderText(PARAM_HELP.get(p.kind, ""))
                    w.textChanged.connect(self._update_preview)
                tip = (p.hint + "\n" if p.hint else "") + PARAM_HELP.get(p.kind, "")
                w.setToolTip(tip)
                self.form.addRow(hbox(label(p.name, "Muted"), help_dot(tip), spacing=4), w)
                self.param_edits.append(w)
            if c.name in ("Get", "Set") and m.settings:
                hint = label("Tipp: Einstellungen lassen sich unter »Modul-Einstellungen« als Tabelle "
                             "lesen und schreiben.", "Muted")
                hint.setWordWrap(True)
                self.form.addRow(hint)
        self._update_preview()

    def _tile_double(self, c):
        self.select_command(c)
        self.send_current()

    def _values(self):
        return [w.currentData() if isinstance(w, QComboBox) else w.text() for w in self.param_edits]

    def _build_current(self) -> bytes:
        c = self.current_cmd
        m = self.ctl.module
        if c.at:
            from ..protocol import Encoding, from_text
            return from_text(self._values()[0], Encoding.ASCII) + m.eol.encode()
        return build_frame(m.proto, c.code, command_payload(m, c, self._values()))

    def _update_preview(self):
        if self.current_cmd is None:
            return
        try:
            data = self._build_current()
            self.preview.set_frame(self.ctl.module.proto, data)
            self.preview_err.setText(f"{len(data)} Bytes: {hexs(data)}")
            self.preview_err.setStyleSheet("")
        except ValueError as exc:
            self.preview.clear("—")
            self.preview_err.setText(f"⚠ {exc}")
            self.preview_err.setStyleSheet(f"color:{C['red']}")

    def send_current(self):
        if self.current_cmd is None:
            self.mw.toast("Zuerst einen Befehl auswählen.", error=True)
            return
        if not self.ctl.is_open:
            self.mw.toast("Zuerst verbinden (Schritt 3).", error=True)
            return
        if self.current_cmd.danger and QMessageBox.question(
                self, "Befehl senden",
                f"{self.current_cmd.name} setzt alle Einstellungen des Moduls zurück. Fortfahren?") != QMessageBox.Yes:
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
            self.ctl.send_raw(data, c.at.split("=")[0])
        else:
            self.ctl.send_frame(data)
        self.repeat_left -= 1
        if self.repeat_left <= 0:
            self.repeat_timer.stop()

    # ================================================================ Freie Eingabe
    def _mode_changed(self):
        m = self.ctl.module
        has_frames = m.proto in ("cmd16", "cmd8", "metis")
        self.mode.model().item(0).setEnabled(has_frames)
        if not has_frames and self.mode.currentData() == "frame":
            self.mode.setCurrentIndex(2)
        if m.proto in ("at", "text") and self.mode.currentData() == "text":
            self.eol.setCurrentIndex({"": 0, "\r": 1, "\n": 2, "\r\n": 3}.get(m.eol, 3))
        mode = self.mode.currentData()
        self.eol.setEnabled(mode == "text")
        self.input.setPlaceholderText({
            "frame": "Befehl + Daten in HEX, z. B. 01 oder 10 02",
            "hex": "Bytes in HEX – unverändert senden",
            "text": "Text – Escapes \\r \\n \\xNN",
        }[mode])

    def send_input(self):
        mode = self.mode.currentData()
        text = self.input.text()
        try:
            if mode == "text":
                from ..protocol import Encoding, from_text
                data = from_text(text, Encoding.ASCII) + [b"", b"\r", b"\n", b"\r\n"][self.eol.currentIndex()]
                if data:
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

    # ================================================================ Protokoll
    def _group_of(self, e):
        if e.kind in ("info", "error"):
            return "INFO"
        if e.ftype in ("RAW", "TEXT"):
            return "RAW"
        return e.ftype or "INFO"

    def _count(self, e):
        if e.kind == "tx":
            self.stats["tx"] += 1
        elif e.kind == "rx":
            self.stats["rx"] += 1
        if e.kind == "error" or (e.ftype == "CNF" and "Status 00" not in e.text and "Status" in e.text):
            self.stats["err"] += 1
        if "RSSI" in e.text:
            try:
                self.stats["rssi"] = e.text.split("RSSI ")[1].split(" dBm")[0] + " dBm"
            except IndexError:
                pass

    def _add_row(self, idx, e):
        r = self.table.rowCount()
        self.table.insertRow(r)
        t = time.strftime("%H:%M:%S", time.localtime(e.ts)) + f".{int((e.ts % 1) * 1000):03d}"
        if e.kind == "error":
            col, arrow, typ = C["red"], "✖", "FEHLER"
        elif e.kind == "info":
            col, arrow, typ = C["muted"], "•", "INFO"
        else:
            col = FTYPE_COLOR.get(e.ftype, C["text"])
            arrow = "▲" if e.kind == "tx" else "▼"
            typ = e.ftype or "–"
        vals = [t, arrow, typ, e.text, str(len(e.data)) if e.data else ""]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            if c == COL_T:
                it.setForeground(QColor(C["dim"]))
                it.setData(Qt.UserRole, idx)
            elif c in (COL_DIR, COL_TYPE):
                it.setForeground(QColor(col))
                it.setTextAlignment(Qt.AlignCenter)
                if c == COL_TYPE:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setToolTip(TYPE_HELP.get(typ, ""))
            elif c == COL_NAME:
                it.setForeground(QColor(col if e.kind in ("info", "error") else C["text"]))
                it.setToolTip(e.text)
            else:
                it.setForeground(QColor(C["muted"]))
            self.table.setItem(r, c, it)
        if self.table.rowCount() > 4000:
            self.table.removeRow(0)

    def _on_log(self, e):
        self.entries.append(e)
        self._count(e)
        if len(self.entries) > 20000:
            del self.entries[:2000]
            self.rebuild_log()
            return
        if self.f[self._group_of(e)].isChecked():
            self._add_row(len(self.entries) - 1, e)
            if self.btn_auto.isChecked():
                self.table.scrollToBottom()

    def rebuild_log(self):
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        vis = [(i, e) for i, e in enumerate(self.entries) if self.f[self._group_of(e)].isChecked()]
        for i, e in vis[-4000:]:
            self._add_row(i, e)
        self.table.setUpdatesEnabled(True)
        if self.btn_auto.isChecked():
            self.table.scrollToBottom()

    def _row_selected(self):
        items = self.table.selectedItems()
        if not items:
            return
        idx = self.table.item(items[0].row(), COL_T).data(Qt.UserRole)
        if idx is None or idx >= len(self.entries):
            return
        e = self.entries[idx]
        proto = self.ctl.module.proto if not self.ctl.raw_mode else "text"
        if not e.data:
            self.an_view.clear(e.text)
            self.an_text.setText("")
            return
        self.an_view.set_frame(proto, e.data)
        lines = [f"<b style='color:{FTYPE_COLOR.get(e.ftype, C['text'])}'>{e.ftype or e.kind.upper()}</b> "
                 f"<span style='color:{C['muted']}'>– {TYPE_HELP.get(e.ftype, '')}</span>",
                 f"<span style='color:{C['text']}'>{e.text}</span>"]
        d = e.data
        if e.ftype in ("REQ", "CNF", "IND", "RSP") and len(d) >= 4:
            h = 4 if proto == "cmd16" else 3
            payload = d[h:-1]
            lines.append(f"<span style='color:{C['muted']}'>Befehlscode 0x{d[1]:02X} · "
                         f"{len(payload)} Datenbytes · Prüfsumme 0x{d[-1]:02X} (gültig)</span>")
            if e.ftype == "CNF" and payload:
                st = payload[0]
                col = C["teal"] if st == 0 else C["red"]
                lines.append(f"<span style='color:{col}'>Status 0x{st:02X}: {STATUS_TEXT.get(st, 'unbekannt')}</span>")
            if payload:
                asc = "".join(chr(b) if 32 <= b < 127 else "·" for b in payload)
                lines.append(f"<span style='color:{C['muted']}'>Daten als Text: </span>"
                             f"<span style='font-family:Consolas'>{asc}</span>")
        else:
            asc = "".join(chr(b) if 32 <= b < 127 else "·" for b in d)
            lines.append(f"<span style='font-family:Consolas'>{asc}</span>")
        self.an_text.setText("<br>".join(lines))

    def _clear(self):
        self.entries.clear()
        self.table.setRowCount(0)
        self.stats = {"tx": 0, "rx": 0, "err": 0, "rssi": "–"}
        self.an_view.clear("Zeile im Protokoll anklicken, um den Frame zu zerlegen")
        self.an_text.setText("")

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

    def _update_kpis(self):
        w = self.ctl.worker
        self.k_tx.set(self.stats["tx"])
        self.k_rx.set(self.stats["rx"])
        self.k_err.set(self.stats["err"])
        self.k_rssi.set(self.stats["rssi"])
        self.k_bytes.set(f"{w.tx_bytes} / {w.rx_bytes}")
