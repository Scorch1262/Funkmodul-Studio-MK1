from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGridLayout, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..protocol import DEFAULT_PROFILES, ProfileType
from .common import Card, hbox, label

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class SettingsPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        s = mw.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        outer.addWidget(area)
        host = QWidget()
        host.setObjectName("Root")
        area.setWidget(host)
        root = QVBoxLayout(host)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        from .widgets import HelpPanel
        root.addWidget(HelpPanel("settings", s))

        # --- Verbindung --------------------------------------------------
        c1 = Card("Verbindung & Scan")
        f = QFormLayout()
        f.setSpacing(10)
        self.write_mode = QComboBox()
        for k, t in (("auto", "Automatisch (nach Characteristic-Eigenschaften)"),
                     ("without", "Ohne Antwort (Write Command – schneller)"),
                     ("with", "Mit Antwort (Write Request – gesichert)")):
            self.write_mode.addItem(t, k)
        self.write_mode.setCurrentIndex(max(0, self.write_mode.findData(s.get("write_mode"))))
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(int(s.get("connect_timeout")))
        self.passive = QCheckBox("Passiver Scan (keine Scan-Requests, Namen evtl. unvollständig)")
        self.passive.setChecked(bool(s.get("scan_passive")))
        self.stale = QSpinBox()
        self.stale.setRange(3, 600)
        self.stale.setSuffix(" s")
        self.stale.setValue(int(s.get("stale_seconds")))
        f.addRow("Schreibart", self.write_mode)
        f.addRow("Verbindungs-Timeout", self.timeout)
        f.addRow("Gerät ausgrauen nach", self.stale)
        f.addRow("", self.passive)
        c1.lay.addLayout(f)
        root.addWidget(c1)

        # --- Terminal ----------------------------------------------------
        c2 = Card("Terminal")
        f2 = QFormLayout()
        f2.setSpacing(10)
        self.log_max = QSpinBox()
        self.log_max.setRange(100, 100000)
        self.log_max.setSingleStep(500)
        self.log_max.setValue(int(s.get("log_max")))
        self.ts_ms = QCheckBox("Zeitstempel mit Millisekunden")
        self.ts_ms.setChecked(bool(s.get("timestamp_ms")))
        self.split = QCheckBox("»Große Daten aufteilen« standardmäßig aktiv")
        self.split.setChecked(bool(s.get("split_large")))
        f2.addRow("Max. Protokolleinträge je Gerät", self.log_max)
        f2.addRow("", self.ts_ms)
        f2.addRow("", self.split)
        c2.lay.addLayout(f2)
        root.addWidget(c2)

        # --- UUIDs -------------------------------------------------------
        c3 = Card("Profil-UUIDs (für Module mit geänderter Firmware)")
        hint = label("Leer lassen = Standardwert. RX = PC → Modul (Schreiben), "
                     "TX = Modul → PC (Notifications).", "Muted")
        hint.setWordWrap(True)
        c3.lay.addWidget(hint)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        for c, h in enumerate(["PROFIL", "SERVICE", "RX", "TX"]):
            g.addWidget(label(h, "CardTitle"), 0, c)
        self.uuid_edits = {}
        ov = s.get("uuid_overrides") or {}
        for r, ptype in enumerate(ProfileType, start=1):
            g.addWidget(label(ptype.value, "Accent"), r, 0)
            dflt = DEFAULT_PROFILES[ptype]
            edits = {}
            for c, key in enumerate(("service", "rx", "tx"), start=1):
                e = QLineEdit((ov.get(ptype.value) or {}).get(key, ""))
                e.setPlaceholderText(getattr(dflt, key))
                e.setMinimumWidth(270)
                g.addWidget(e, r, c)
                edits[key] = e
            self.uuid_edits[ptype] = edits
        c3.lay.addLayout(g)
        b_reset = QPushButton("UUIDs zurücksetzen")
        b_reset.clicked.connect(self._reset_uuids)
        c3.lay.addWidget(hbox(None, b_reset))
        root.addWidget(c3)

        b_save = QPushButton("Einstellungen speichern")
        b_save.setObjectName("Primary")
        b_save.clicked.connect(self.save)
        root.addWidget(hbox(label(f"Gespeichert in: {s.path}", "Muted"), None, b_save))
        root.addStretch(1)

    def _reset_uuids(self):
        for edits in self.uuid_edits.values():
            for e in edits.values():
                e.clear()

    def save(self):
        ov = {}
        for ptype, edits in self.uuid_edits.items():
            entry = {}
            for k, e in edits.items():
                v = e.text().strip()
                if v:
                    if not UUID_RE.match(v):
                        QMessageBox.warning(self, "Einstellungen", f"Ungültige UUID bei {ptype.value} / {k}:\n{v}")
                        return
                    entry[k] = v.lower()
            if entry:
                ov[ptype.value] = entry
        s = self.mw.settings
        s.data.update({
            "write_mode": self.write_mode.currentData(),
            "connect_timeout": self.timeout.value(),
            "scan_passive": self.passive.isChecked(),
            "stale_seconds": self.stale.value(),
            "log_max": self.log_max.value(),
            "timestamp_ms": self.ts_ms.isChecked(),
            "split_large": self.split.isChecked(),
            "uuid_overrides": ov,
        })
        s.save()
        self.mw.terminal.log.setMaximumBlockCount(self.log_max.value() * 2)
        self.mw.terminal.rebuild_log()
        self.mw.toast("Einstellungen gespeichert. Schreibart/UUIDs gelten ab der nächsten Verbindung.")
