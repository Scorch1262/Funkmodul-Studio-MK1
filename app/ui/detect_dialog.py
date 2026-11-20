"""Dialog für die automatische Modul-Erkennung."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from ..uart.detect import DEFAULT_BAUDS, Detector
from ..uart.modules import MODULE_BY_KEY
from .common import hbox, label


class DetectDialog(QDialog):
    def __init__(self, parent, ports, current, dtr, rts):
        super().__init__(parent)
        self.setWindowTitle("Modul erkennen")
        self.resize(640, 560)
        self.result_obj = None
        self.chosen_key = None
        self.results = []
        self.dtr, self.rts = dtr, rts
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        lay.addWidget(label("AUTOMATISCHE MODUL-ERKENNUNG", "CardTitle"))
        t = label("Probiert Baudraten und Protokolle durch: Befehlsframes (Proteus, Thyone, Metis-e), "
                  "Sub-GHz-Frames (Tarvos, Telesto, Thebe, Themisto), Metis, AT-Befehle (Calypso, Cordelia, "
                  "Stephano, Daphnis, Adrastea) und Skoll. Funktioniert mit jedem USB-Seriell-Wandler. "
                  "Das Modul muss im Befehlsmodus sein, nicht im transparenten Modus.", "Muted")
        t.setWordWrap(True)
        lay.addWidget(t)

        lay.addWidget(label("Ports", "Accent"))
        self.plist = QListWidget()
        self.plist.setMaximumHeight(130)
        for p in ports:
            it = QListWidgetItem(p.label)
            it.setData(Qt.UserRole, p.device)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if (p.device == current or not current) else Qt.Unchecked)
            self.plist.addItem(it)
        lay.addWidget(self.plist)
        self.cb_all_bauds = QCheckBox("Alle Baudraten prüfen (" + ", ".join(str(b) for b in DEFAULT_BAUDS) + ")")
        self.cb_all_bauds.setChecked(True)
        self.cb_continue = QCheckBox("Nach dem ersten Treffer je Port weitere Baudraten überspringen")
        self.cb_continue.setChecked(True)
        lay.addWidget(self.cb_all_bauds)
        lay.addWidget(self.cb_continue)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        lay.addWidget(self.log, 1)

        lay.addWidget(label("Gefunden", "Accent"))
        self.res = QListWidget()
        self.res.setMaximumHeight(110)
        self.res.currentRowChanged.connect(self._sel)
        lay.addWidget(self.res)
        self.mod = QComboBox()
        self.mod.setEnabled(False)
        lay.addWidget(hbox(label("Modultyp", "Muted"), self.mod, None))

        self.b_start = QPushButton("Erkennung starten")
        self.b_start.setObjectName("Primary")
        self.b_start.clicked.connect(self.start)
        self.b_use = QPushButton("Übernehmen und öffnen")
        self.b_use.setEnabled(False)
        self.b_use.clicked.connect(self._use)
        b_close = QPushButton("Schließen")
        b_close.clicked.connect(self.reject)
        lay.addWidget(hbox(self.b_start, None, b_close, self.b_use))

        self.det = Detector()
        self.det.progress.connect(lambda m: self.log.appendPlainText(m))
        self.det.found.connect(self._found)
        self.det.finished.connect(self._finished)
        if not ports:
            self.log.appendPlainText("Kein COM-Port gefunden. Board anschließen – der Port erscheint automatisch.")
            self.b_start.setEnabled(False)

    def start(self):
        if self.det.running:
            self.det.cancel()
            return
        ports = [self.plist.item(i).data(Qt.UserRole) for i in range(self.plist.count())
                 if self.plist.item(i).checkState() == Qt.Checked]
        if not ports:
            self.log.appendPlainText("Bitte mindestens einen Port auswählen.")
            return
        bauds = DEFAULT_BAUDS if self.cb_all_bauds.isChecked() else [115200]
        self.res.clear()
        self.results.clear()
        self.log.clear()
        self.b_start.setText("Abbrechen")
        self.det.start(ports, bauds, self.dtr, self.rts, self.cb_continue.isChecked())

    def _found(self, r):
        self.results.append(r)
        m = MODULE_BY_KEY[r.module_key]
        sure = "" if r.sure else "  (vermutlich)"
        self.res.addItem(f"{r.port} · {r.baud} Baud · {m.label}{sure} – {r.details}")
        self.log.appendPlainText(f"✔ Treffer: {m.label} an {r.port} mit {r.baud} Baud")
        if self.res.currentRow() < 0:
            self.res.setCurrentRow(0)

    def _finished(self, n):
        self.b_start.setText("Erkennung starten")
        self.log.appendPlainText(f"Fertig – {n} Modul(e) gefunden." if n else
                                 "Kein Modul gefunden. Prüfen: Versorgung, Befehlsmodus (nicht transparent), "
                                 "DTR/RTS-Einstellung (RESET-Leitung), anderes Datenformat.")

    def _sel(self, row):
        if not 0 <= row < len(self.results):
            return
        r = self.results[row]
        self.mod.clear()
        for k in r.candidates or [r.module_key]:
            self.mod.addItem(MODULE_BY_KEY[k].label, k)
        self.mod.setCurrentIndex(max(0, self.mod.findData(r.module_key)))
        self.mod.setEnabled(self.mod.count() > 1)
        self.b_use.setEnabled(True)

    def _use(self):
        row = self.res.currentRow()
        if 0 <= row < len(self.results):
            self.result_obj = self.results[row]
            self.chosen_key = self.mod.currentData()
            self.det.cancel()
            self.accept()

    def reject(self):
        self.det.cancel()
        super().reject()
