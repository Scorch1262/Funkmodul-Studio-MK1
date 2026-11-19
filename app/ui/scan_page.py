from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
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
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.found: dict[str, dict] = {}
        self.rows: dict[str, int] = {}
        self.scanning = False

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
        ctrl.lay.addWidget(hbox(self.btn_scan, self.btn_clear, None, self.lbl_count, self.btn_connect))

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
        self.f_named.toggled.connect(self.apply_filter)
        self.sort = QComboBox()
        self.sort.addItems(["Sortierung: RSSI", "Sortierung: Name", "Sortierung: Adresse"])
        self.sort.currentIndexChanged.connect(self.resort)
        ctrl.lay.addWidget(hbox(self.f_name, self.lbl_rssi, self.f_rssi, self.sort))
        ctrl.lay.addWidget(hbox(self.f_spp, self.f_we, self.f_named, None))
        root.addWidget(ctrl)

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

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_times)
        self.timer.start(1000)
        self._resort_pending = False

    # ------------------------------------------------------------------
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

    def clear(self):
        self.found.clear()
        self.rows.clear()
        self.table.setRowCount(0)
        self.lbl_count.setText("0 Geräte")
        self.btn_connect.setEnabled(False)

    def on_result(self, d: dict):
        old = self.found.get(d["address"])
        if old:
            # Name/Profil aus früheren Werbepaketen nicht verlieren (Scan-Response kommt getrennt)
            d["name"] = d["name"] or old.get("name", "")
            d["profile"] = d["profile"] or old.get("profile")
            d["we"] = d["we"] or old.get("we")
            d["beacon"] = d["beacon"] if d["beacon"] is not None else old.get("beacon")
            d["uuids"] = d["uuids"] or old.get("uuids", [])
        self.found[d["address"]] = d
        addr = d["address"]
        if addr not in self.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for c in range(6):
                self.table.setItem(row, c, QTableWidgetItem(""))
            self.rows[addr] = row
            self.lbl_count.setText(f"{len(self.rows)} Geräte")
        self._fill(self.rows[addr], d)
        self._schedule_resort()

    def _fill(self, row: int, d: dict):
        t = self.table
        stale = (time.time() - d["time"]) > float(self.mw.settings.get("stale_seconds", 15))
        name = d["name"] or "Unbenannt"
        it = t.item(row, COL_NAME)
        it.setText(name)
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
        color = QColor(C["dim"]) if stale else (QColor(C["amber"]) if prof else QColor(C["text"]))
        for c in (COL_NAME, COL_PROFILE):
            t.item(row, c).setForeground(color)
        for c in (COL_ADDR, COL_INFO, COL_SEEN):
            t.item(row, c).setForeground(QColor(C["dim"] if stale else C["muted"]))
        t.setRowHidden(row, not self._visible(d))
        t.viewport().update()

    @staticmethod
    def _ago(ts):
        s = int(time.time() - ts)
        return "jetzt" if s < 2 else f"vor {s} s" if s < 60 else f"vor {s // 60} min"

    def _visible(self, d) -> bool:
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
        if self.f_named.isChecked() and not d.get("name"):
            return False
        return True

    def apply_filter(self):
        for addr, row in self.rows.items():
            self.table.setRowHidden(row, not self._visible(self.found[addr]))

    def refresh_times(self):
        for addr, row in self.rows.items():
            self._fill(row, self.found[addr])

    def _schedule_resort(self):
        if not self._resort_pending:
            self._resort_pending = True
            QTimer.singleShot(700, self.resort)

    def resort(self):
        self._resort_pending = False
        sel = self.selected_address()
        mode = self.sort.currentIndex()
        items = list(self.found.values())
        if mode == 0:
            items.sort(key=lambda d: -(d["rssi"] if d["rssi"] is not None else -999))
        elif mode == 1:
            items.sort(key=lambda d: ((d["name"] or "~").lower(), d["address"]))
        else:
            items.sort(key=lambda d: d["address"])
        self.table.setUpdatesEnabled(False)
        self.rows = {}
        for row, d in enumerate(items):
            self.rows[d["address"]] = row
            self._fill(row, d)
        self.table.setUpdatesEnabled(True)
        if sel and sel in self.rows:
            self.table.blockSignals(True)
            self.table.selectRow(self.rows[sel])
            self.table.blockSignals(False)

    def selected_address(self) -> str | None:
        items = self.table.selectedItems()
        if not items:
            return None
        return self.table.item(items[0].row(), COL_NAME).data(Qt.UserRole)

    def _sel_changed(self):
        self.btn_connect.setEnabled(self.selected_address() is not None)

    def connect_selected(self):
        addr = self.selected_address()
        if not addr:
            return
        if addr in self.mw.devices:
            self.mw.select_device(addr)
            self.mw.goto("terminal")
            return
        d = self.found[addr]
        dlg = ConnectDialog(self, d)
        if dlg.exec() == QDialog.Accepted:
            self.mw.connect_device(addr, d.get("name", ""), dlg.module_key())
