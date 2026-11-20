from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout,
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QSlider, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..protocol import MODULES, guess_module
from ..theme import C
from .common import Card, hbox, label

COL_NAME, COL_ADDR, COL_RSSI, COL_PROFILE, COL_INFO, COL_SEEN = range(6)


class RssiDelegate(QStyledItemDelegate):
    def paint(self, p: QPainter, opt, idx):
        rssi = idx.data(Qt.UserRole)
        stale = idx.data(Qt.UserRole + 1)
        super().paint(p, opt, idx)
        if rssi is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = opt.rect.adjusted(8, 0, -8, 0)
        bars = 5
        level = max(0, min(bars, int((rssi + 100) / 10)))  # -100..-50 dBm
        bw, gap = 5, 3
        x0 = r.left()
        for i in range(bars):
            h = 5 + i * 3
            rect = QRectF(x0 + i * (bw + gap), r.center().y() + 9 - h, bw, h)
            if i < level:
                col = QColor(C["dim"] if stale else (C["teal"] if level >= 3 else C["amber"]))
            else:
                col = QColor(C["border2"])
            p.fillRect(rect, col)
        p.setPen(QColor(C["muted"] if stale else C["text"]))
        p.drawText(r.adjusted(bars * (bw + gap) + 6, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, f"{rssi} dBm")
        p.restore()

    def initStyleOption(self, opt, idx):
        super().initStyleOption(opt, idx)
        opt.text = ""


class ConnectDialog(QDialog):
    def __init__(self, parent, dev: dict):
        super().__init__(parent)
        self.setWindowTitle("Verbinden")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)
        lay.addWidget(label("MODUL AUSWÄHLEN", "CardTitle"))
        lay.addWidget(label(f"{dev.get('name') or 'Unbenannt'}  ·  {dev['address']}", "Accent"))
        form = QFormLayout()
        form.setSpacing(8)
        self.combo = QComboBox()
        guess = guess_module(dev.get("name"), dev.get("profile"))
        for m in MODULES:
            self.combo.addItem(f"{m.label}   ({m.profile.value})", m.key)
        self.combo.setCurrentIndex([m.key for m in MODULES].index(guess.key))
        form.addRow("Modultyp", self.combo)
        prof = dev.get("profile")
        form.addRow("Erkanntes Profil", label(prof.value if prof else "– (nicht in Werbedaten)", "Muted"))
        lay.addLayout(form)
        hint = label("Der Modultyp bestimmt Header-Bytes (0x01/0x02), Standard-MTU und die "
                     "GPIO-Fernsteuerung (Proteus-III, Proteus-e, Setebos-I).", "Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Verbinden")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def module_key(self) -> str:
        return self.combo.currentData()


class ScanPage(QWidget):
    """Geräteliste mit gedrosselter Aktualisierung.

    Die Scan-Ergebnisse werden im BLE-Thread gesammelt und hier alle 400 ms abgeholt.
    Zeilen behalten ihre Position, solange ein Gerät ausgewählt ist – so lässt sich ein
    Eintrag sicher anklicken und verbinden, auch wenn sehr viele Geräte senden.
    """

    POLL_MS = 400

    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.found: dict[str, dict] = {}
        self.rows: dict[str, int] = {}
        self.scanning = False
        self.connecting_addr: str | None = None
        self._last_sort = 0.0
        self._pkt_rate = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # --- Steuerung ---------------------------------------------------
        ctrl = Card("Geräte-Suche")
        self.btn_scan = QPushButton("Scan starten")
        self.btn_scan.setObjectName("Primary")
        self.btn_scan.setMinimumWidth(140)
        self.btn_scan.clicked.connect(self.toggle_scan)
        self.btn_clear = QPushButton("Liste leeren")
        self.btn_clear.clicked.connect(self.clear)
        self.btn_connect = QPushButton("Verbinden")
        self.btn_connect.setEnabled(False)
        self.btn_connect.clicked.connect(self.connect_selected)
        self.lbl_count = label("0 Geräte", "Muted")
        self.lbl_rate = label("", "Muted")
        self.lbl_rate.setToolTip("Empfangene Werbepakete pro Sekunde – zeigt, dass der Scan läuft")
        ctrl.lay.addWidget(hbox(self.btn_scan, self.btn_clear, None, self.lbl_rate, self.lbl_count, self.btn_connect))

        self.f_name = QLineEdit()
        self.f_name.setPlaceholderText("Name / Adresse enthält …")
        self.f_name.textChanged.connect(self.apply_filter)
        self.f_rssi = QSlider(Qt.Horizontal)
        self.f_rssi.setRange(-100, -30)
        self.f_rssi.setValue(-100)
        self.f_rssi.setFixedWidth(160)
        self.lbl_rssi = label("min. RSSI: aus", "Muted")
        self.lbl_rssi.setMinimumWidth(110)
        self.f_rssi.valueChanged.connect(self._rssi_changed)
        self.f_spp = QCheckBox("Nur SPP-Profil (Proteus/Setebos/Skoll)")
        self.f_spp.toggled.connect(self.apply_filter)
        self.f_we = QCheckBox("Nur Würth-Kennung 0x031A")
        self.f_we.toggled.connect(self.apply_filter)
        self.f_named = QCheckBox("Nur mit Namen")
        self.f_named.setChecked(bool(mw.settings.get("scan_only_named", True)))
        self.f_named.toggled.connect(self.apply_filter)
        self.f_named.setToolTip("Blendet namenlose Geräte (z. B. Smartphones, Beacons) aus – macht die Liste übersichtlich")
        self.sort = QComboBox()
        self.sort.addItems(["Sortierung: RSSI", "Sortierung: Name", "Sortierung: Adresse", "Sortierung: fest"])
        self.sort.currentIndexChanged.connect(lambda _: self.resort(force=True))
        self.sort.setToolTip("Bei »RSSI« wird alle 3 s neu sortiert – aber nie, solange ein Gerät ausgewählt ist")
        ctrl.lay.addWidget(hbox(self.f_name, self.lbl_rssi, self.f_rssi, self.sort))
        ctrl.lay.addWidget(hbox(self.f_spp, self.f_we, self.f_named, None))

        self.addr = QLineEdit()
        self.addr.setPlaceholderText("Direkt verbinden: MAC-Adresse, z. B. 00:18:DA:12:34:56")
        self.addr.returnPressed.connect(self.connect_address)
        b_addr = QPushButton("Mit Adresse verbinden")
        b_addr.clicked.connect(self.connect_address)
        ctrl.lay.addWidget(hbox(self.addr, b_addr))
        root.addWidget(ctrl)

        # --- Verbindungsanzeige ------------------------------------------
        self.busy = QFrame()
        self.busy.setObjectName("Help")
        bl = QHBoxLayout(self.busy)
        bl.setContentsMargins(14, 8, 14, 8)
        self.busy_lbl = label("", "Accent")
        self.busy_cancel = QPushButton("Abbrechen")
        self.busy_cancel.setObjectName("Danger")
        self.busy_cancel.clicked.connect(self._cancel_connect)
        bl.addWidget(self.busy_lbl, 1)
        bl.addWidget(self.busy_cancel)
        self.busy.setVisible(False)
        root.addWidget(self.busy)

        # --- Tabelle -----------------------------------------------------
        tcard = Card("Gefundene Geräte")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["NAME", "ADRESSE", "RSSI", "PROFIL", "WERBEDATEN", "ZULETZT"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_ADDR, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_RSSI, QHeaderView.Fixed)
        self.table.setColumnWidth(COL_RSSI, 130)
        hh.setSectionResizeMode(COL_PROFILE, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_INFO, QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_SEEN, QHeaderView.ResizeToContents)
        self.table.setItemDelegateForColumn(COL_RSSI, RssiDelegate(self.table))
        self.table.itemSelectionChanged.connect(self._sel_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self.connect_selected())
        tcard.lay.addWidget(self.table)
        root.addWidget(tcard, 1)

        self.poll = QTimer(self)
        self.poll.timeout.connect(self._poll)
        self.poll.start(self.POLL_MS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_times)
        self.timer.start(2000)

        mw.worker.connect_progress.connect(self._on_progress)
        mw.worker.connected.connect(lambda a, _i: self._end_busy(a))
        mw.worker.disconnected.connect(lambda a, _r: self._end_busy(a))

    # ------------------------------------------------------------------ Scan
    def _rssi_changed(self, v):
        self.lbl_rssi.setText("min. RSSI: aus" if v <= -100 else f"min. RSSI: {v} dBm")
        self.apply_filter()

    def toggle_scan(self):
        if self.scanning:
            self.mw.worker.stop_scan()
        else:
            self.btn_scan.setEnabled(False)
            self.mw.worker.start_scan()

    def on_scan_state(self, on: bool):
        self.scanning = on
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("Scan stoppen" if on else "Scan starten")
        self.btn_scan.setObjectName("Danger" if on else "Primary")
        self.btn_scan.style().unpolish(self.btn_scan)
        self.btn_scan.style().polish(self.btn_scan)
        if not on:
            self.lbl_rate.setText("")

    def clear(self):
        self.found.clear()
        self.rows.clear()
        self.table.setRowCount(0)
        self.lbl_count.setText("0 Geräte")
        self.btn_connect.setEnabled(False)

    def _poll(self):
        items, n = self.mw.worker.take_scan_updates()
        if self.scanning:
            self._pkt_rate = 0.6 * self._pkt_rate + 0.4 * (n * 1000 / self.POLL_MS)
            self.lbl_rate.setText(f"{self._pkt_rate:.0f} Pakete/s")
        if not items:
            return
        self.table.setUpdatesEnabled(False)
        added = False
        for d in items:
            self.found[d["address"]] = d
            if d["address"] not in self.rows:
                row = self.table.rowCount()
                self.table.insertRow(row)
                for c in range(6):
                    self.table.setItem(row, c, QTableWidgetItem(""))
                self.rows[d["address"]] = row
                added = True
            self._fill(self.rows[d["address"]], d)
        self.table.setUpdatesEnabled(True)
        self.lbl_count.setText(f"{len(self.rows)} Geräte · {self._visible_count()} angezeigt")
        if self.sort.currentIndex() == 0 and time.time() - self._last_sort > 3:
            self.resort()
        elif added and self.sort.currentIndex() in (1, 2):
            self.resort()

    # Kompatibilität (Tests / alte Aufrufe)
    def on_result(self, d: dict):
        with self.mw.worker._scan_lock:
            self.mw.worker._scan_buf[d["address"]] = d

    def _fill(self, row: int, d: dict):
        t = self.table
        stale = (time.time() - d["time"]) > float(self.mw.settings.get("stale_seconds", 15))
        it = t.item(row, COL_NAME)
        it.setText(d["name"] or "Unbenannt")
        it.setData(Qt.UserRole, d["address"])
        t.item(row, COL_ADDR).setText(d["address"])
        rs = t.item(row, COL_RSSI)
        rs.setData(Qt.UserRole, d["rssi"])
        rs.setData(Qt.UserRole + 1, stale)
        prof = d.get("profile")
        t.item(row, COL_PROFILE).setText(prof.value if prof else ("WE" if d.get("we") else "–"))
        info = []
        if d.get("beacon") is not None:
            info.append("Beacon: " + " ".join(f"{b:02X}" for b in d["beacon"]))
        elif d.get("we"):
            info.append("Würth-Herstellerdaten")
        if d.get("tx_power") is not None:
            info.append(f"TX {d['tx_power']} dBm")
        if not info and d.get("uuids"):
            info.append(f"{len(d['uuids'])} Service-UUID(s)")
        t.item(row, COL_INFO).setText("   ".join(info))
        t.item(row, COL_SEEN).setText(self._ago(d["time"]))
        color = QColor(C["dim"]) if stale else (QColor(C["amber"]) if (prof or d.get("we")) else QColor(C["text"]))
        for c in (COL_NAME, COL_PROFILE):
            t.item(row, c).setForeground(color)
        for c in (COL_ADDR, COL_INFO, COL_SEEN):
            t.item(row, c).setForeground(QColor(C["dim"] if stale else C["muted"]))
        hide = not self._visible(d)
        if t.isRowHidden(row) != hide:
            t.setRowHidden(row, hide)

    @staticmethod
    def _ago(ts):
        s = int(time.time() - ts)
        return "jetzt" if s < 2 else f"vor {s} s" if s < 60 else f"vor {s // 60} min"

    def _visible(self, d) -> bool:
        if self.connecting_addr == d["address"] or d["address"] == self.selected_address():
            return True
        txt = self.f_name.text().strip().lower()
        if txt and txt not in (d["name"] or "").lower() and txt not in d["address"].lower():
            return False
        v = self.f_rssi.value()
        if v > -100 and (d["rssi"] is None or d["rssi"] < v):
            return False
        if self.f_spp.isChecked() and not d.get("profile"):
            return False
        if self.f_we.isChecked() and not d.get("we"):
            return False
        if self.f_named.isChecked() and not d.get("name") and not d.get("we") and not d.get("profile"):
            return False
        return True

    def _visible_count(self):
        return sum(1 for r in self.rows.values() if not self.table.isRowHidden(r))

    def apply_filter(self):
        self.mw.settings.set("scan_only_named", self.f_named.isChecked())
        for addr, row in self.rows.items():
            self.table.setRowHidden(row, not self._visible(self.found[addr]))
        self.lbl_count.setText(f"{len(self.rows)} Geräte · {self._visible_count()} angezeigt")

    def refresh_times(self):
        stale_s = float(self.mw.settings.get("stale_seconds", 15))
        now = time.time()
        for addr, row in self.rows.items():
            d = self.found[addr]
            self.table.item(row, COL_SEEN).setText(self._ago(d["time"]))
            stale = (now - d["time"]) > stale_s
            if self.table.item(row, COL_RSSI).data(Qt.UserRole + 1) != stale:
                self._fill(row, d)

    def resort(self, force=False):
        sel = self.selected_address()
        if sel and not force:
            return          # Auswahl nie unter dem Mauszeiger wegsortieren
        self._last_sort = time.time()
        mode = self.sort.currentIndex()
        if mode == 3 and not force:
            return
        items = list(self.found.values())
        if mode == 0:
            items.sort(key=lambda d: -(d["rssi"] if d["rssi"] is not None else -999))
        elif mode == 1:
            items.sort(key=lambda d: ((d["name"] or "~").lower(), d["address"]))
        elif mode == 2:
            items.sort(key=lambda d: d["address"])
        else:
            return
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.rows = {}
        for row, d in enumerate(items):
            self.rows[d["address"]] = row
            self._fill(row, d)
        if sel and sel in self.rows:
            self.table.selectRow(self.rows[sel])
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)

    def selected_address(self) -> str | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        it = self.table.item(rows[0].row(), COL_NAME)
        return it.data(Qt.UserRole) if it else None

    def _sel_changed(self):
        self.btn_connect.setEnabled(self.selected_address() is not None and self.connecting_addr is None)

    # ------------------------------------------------------------------ Verbinden
    def connect_selected(self):
        addr = self.selected_address()
        if not addr:
            return
        self._open_connect(addr, self.found.get(addr, {"address": addr, "name": ""}))

    def connect_address(self):
        a = self.addr.text().strip().upper().replace("-", ":")
        parts = a.split(":")
        if len(parts) != 6 or not all(len(p) == 2 for p in parts):
            self.mw.toast("Ungültige Adresse – Format 00:18:DA:12:34:56", error=True)
            return
        self._open_connect(a, self.found.get(a, {"address": a, "name": "", "profile": None}))

    def _open_connect(self, addr, d):
        if addr in self.mw.devices:
            self.mw.select_device(addr)
            self.mw.goto("terminal")
            return
        if self.connecting_addr:
            self.mw.toast("Es läuft bereits ein Verbindungsaufbau.", error=True)
            return
        dlg = ConnectDialog(self, d)
        if dlg.exec() == QDialog.Accepted:
            self.connecting_addr = addr
            self.busy_lbl.setText(f"Verbinde mit {d.get('name') or addr} …")
            self.busy.setVisible(True)
            self.btn_connect.setEnabled(False)
            self.mw.connect_device(addr, d.get("name", ""), dlg.module_key())

    def _on_progress(self, addr, text):
        if addr == self.connecting_addr:
            name = self.found.get(addr, {}).get("name") or addr
            self.busy_lbl.setText(f"{name}: {text}")

    def _end_busy(self, addr):
        if addr == self.connecting_addr:
            self.connecting_addr = None
            self.busy.setVisible(False)
            self._sel_changed()

    def _cancel_connect(self):
        if self.connecting_addr:
            self.mw.worker.cancel_connect(self.connecting_addr)
