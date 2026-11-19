from __future__ import annotations

import html
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..protocol import Encoding, from_text, max_payload, random_payload, to_text
from ..theme import LOG_COLORS
from .common import Card, hbox, label

KIND_GROUP = {"info": "info", "error": "info", "tx": "data", "rx": "data",
              "cmd_tx": "cmd", "cmd_rx": "cmd"}


class MacroDialog(QDialog):
    """Makros anlegen, bearbeiten, löschen und sortieren."""

    def __init__(self, parent, macros: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Makros verwalten")
        self.resize(560, 420)
        self.macros = [dict(m) for m in macros]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        lay.addWidget(label("MAKROS", "CardTitle"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load)
        lay.addWidget(self.list, 1)

        form = QFormLayout()
        self.e_name = QLineEdit()
        self.e_enc = QComboBox()
        self.e_enc.addItems([Encoding.HEX.value, Encoding.ASCII.value])
        self.e_enc.currentIndexChanged.connect(self._enc_changed)
        self.e_data = QLineEdit()
        self.e_data.setObjectName("Payload")
        form.addRow("Name", self.e_name)
        form.addRow("Kodierung", self.e_enc)
        form.addRow("Daten", self.e_data)
        lay.addLayout(form)

        b_new = QPushButton("Neu")
        b_save = QPushButton("Übernehmen")
        b_save.setObjectName("Primary")
        b_del = QPushButton("Löschen")
        b_del.setObjectName("Danger")
        b_up = QPushButton("▲")
        b_dn = QPushButton("▼")
        b_new.clicked.connect(self._new)
        b_save.clicked.connect(self._save)
        b_del.clicked.connect(self._delete)
        b_up.clicked.connect(lambda: self._move(-1))
        b_dn.clicked.connect(lambda: self._move(1))
        lay.addWidget(hbox(b_new, b_up, b_dn, None, b_del, b_save))

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Speichern")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._rebuild()
        if self.macros:
            self.list.setCurrentRow(0)

    def _rebuild(self, sel=None):
        self.list.blockSignals(True)
        self.list.clear()
        for m in self.macros:
            QListWidgetItem(f"{m['name']}    —    {to_text(bytes.fromhex(m['hex']), Encoding.HEX)}", self.list)
        self.list.blockSignals(False)
        if sel is not None and 0 <= sel < len(self.macros):
            self.list.setCurrentRow(sel)

    def _load(self, row):
        if 0 <= row < len(self.macros):
            m = self.macros[row]
            self.e_name.setText(m["name"])
            enc = Encoding(self.e_enc.currentText())
            self.e_data.setText(to_text(bytes.fromhex(m["hex"]), enc))

    def _enc_changed(self):
        self._load(self.list.currentRow())

    def _parse(self):
        enc = Encoding(self.e_enc.currentText())
        data = from_text(self.e_data.text(), enc)
        if not data:
            raise ValueError("Keine Daten eingegeben")
        return data

    def _new(self):
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        self.e_name.setText("")
        self.e_data.setText("")
        self.e_name.setFocus()

    def _save(self):
        try:
            data = self._parse()
        except ValueError as exc:
            QMessageBox.warning(self, "Makro", str(exc))
            return
        name = self.e_name.text().strip() or to_text(data, Encoding.HEX)[:20]
        row = self.list.currentRow()
        entry = {"name": name, "hex": data.hex().upper()}
        if 0 <= row < len(self.macros):
            self.macros[row] = entry
        else:
            self.macros.append(entry)
            row = len(self.macros) - 1
        self._rebuild(row)

    def _delete(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.macros):
            del self.macros[row]
            self._rebuild(min(row, len(self.macros) - 1))

    def _move(self, d):
        row = self.list.currentRow()
        nr = row + d
        if 0 <= row < len(self.macros) and 0 <= nr < len(self.macros):
            self.macros[row], self.macros[nr] = self.macros[nr], self.macros[row]
            self._rebuild(nr)


class TerminalPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        s = mw.settings
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # --- Gerätestatus -------------------------------------------------
        top = Card("Verbindung")
        self.lbl_dev = label("Kein Gerät verbunden", "Accent")
        self.lbl_meta = label("Verbinde ein Gerät über die Seite »Scan«.", "Muted")
        self.btn_mtu = QPushButton("MTU lesen")
        self.btn_mtu.clicked.connect(self._read_mtu)
        self.btn_disc = QPushButton("Trennen")
        self.btn_disc.setObjectName("Danger")
        self.btn_disc.clicked.connect(self._disconnect)
        col = QWidget()
        cl = QVBoxLayout(col)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)
        cl.addWidget(self.lbl_dev)
        cl.addWidget(self.lbl_meta)
        top.lay.addWidget(hbox(col, None, self.btn_mtu, self.btn_disc))
        root.addWidget(top)

        # --- Log ----------------------------------------------------------
        logc = Card("Protokoll")
        self.cb_info = QCheckBox("Info")
        self.cb_data = QCheckBox("Daten")
        self.cb_cmd = QCheckBox("Fernbefehle")
        for cb in (self.cb_info, self.cb_data, self.cb_cmd):
            cb.setChecked(True)
            cb.toggled.connect(self.rebuild_log)
        self.enc = QComboBox()
        for e in Encoding:
            self.enc.addItem(e.value)
        self.enc.setCurrentText(s.get("encoding", "HEX"))
        self._prev_enc = Encoding(self.enc.currentText())
        self.enc.currentIndexChanged.connect(self._enc_changed)
        self.btn_auto = QPushButton("Autoscroll")
        self.btn_auto.setCheckable(True)
        self.btn_auto.setChecked(True)
        self.btn_clear = QPushButton("Leeren")
        self.btn_clear.clicked.connect(self._clear_log)
        self.btn_save = QPushButton("Speichern …")
        self.btn_save.clicked.connect(self._save_log)
        logc.lay.addWidget(hbox(self.cb_info, self.cb_data, self.cb_cmd, None,
                                label("Anzeige", "Muted"), self.enc, self.btn_auto, self.btn_clear, self.btn_save))
        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.log.setMaximumBlockCount(int(s.get("log_max", 5000)) * 2)
        logc.lay.addWidget(self.log, 1)
        root.addWidget(logc, 1)

        # --- Senden -------------------------------------------------------
        send = Card("Senden")
        self.macro_bar = QWidget()
        self.macro_lay = QHBoxLayout(self.macro_bar)
        self.macro_lay.setContentsMargins(0, 0, 0, 0)
        self.macro_lay.setSpacing(6)
        msc = QScrollArea()
        msc.setWidget(self.macro_bar)
        msc.setWidgetResizable(True)
        msc.setFixedHeight(44)
        msc.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        msc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.btn_macros = QPushButton("Makros …")
        self.btn_macros.clicked.connect(self._manage_macros)
        send.lay.addWidget(hbox(msc, self.btn_macros))

        self.payload = QLineEdit()
        self.payload.setObjectName("Payload")
        self.payload.textChanged.connect(self._update_count)
        self.payload.returnPressed.connect(self.send)
        self.lbl_bytes = label("0 Bytes", "Muted")
        self.lbl_bytes.setMinimumWidth(150)
        self.lbl_bytes.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.btn_send = QPushButton("Senden")
        self.btn_send.setObjectName("Primary")
        self.btn_send.setMinimumWidth(120)
        self.btn_send.clicked.connect(self.send)
        self.cb_crlf = QComboBox()
        self.cb_crlf.addItems(["Kein Zeilenende", "+ CR", "+ LF", "+ CR LF"])
        self.cb_crlf.currentIndexChanged.connect(self._update_count)
        send.lay.addWidget(hbox(self.payload, self.cb_crlf, self.lbl_bytes, self.btn_send))

        self.cb_multi = QCheckBox("Mehrfach senden")
        self.sp_count = QSpinBox()
        self.sp_count.setRange(1, 1_000_000)
        self.sp_count.setValue(10)
        self.sp_count.setPrefix("Anzahl ")
        self.sp_int = QSpinBox()
        self.sp_int.setRange(50, 3_600_000)
        self.sp_int.setValue(1000)
        self.sp_int.setSuffix(" ms")
        self.sp_int.setPrefix("Intervall ")
        self.cb_rand = QCheckBox("Zufallsdaten")
        self.sp_rand = QSpinBox()
        self.sp_rand.setRange(1, 4096)
        self.sp_rand.setValue(20)
        self.sp_rand.setSuffix(" Bytes")
        self.cb_split = QCheckBox("Große Daten aufteilen")
        self.cb_split.setChecked(bool(s.get("split_large")))
        self.cb_multi.toggled.connect(self._opts_changed)
        self.cb_rand.toggled.connect(self._opts_changed)
        send.lay.addWidget(hbox(self.cb_multi, self.sp_count, self.sp_int, self.cb_rand, self.sp_rand,
                                None, self.cb_split))
        root.addWidget(send)

        self._opts_changed()
        self.rebuild_macros()
        self.refresh_device()

    # ------------------------------------------------------------------ Gerät
    def dev(self):
        return self.mw.current_device()

    def refresh_device(self):
        d = self.dev()
        on = d is not None
        for w in (self.btn_mtu, self.btn_disc, self.payload, self.btn_macros):
            w.setEnabled(on)
        if not on:
            self.lbl_dev.setText("Kein Gerät verbunden")
            self.lbl_meta.setText("Verbinde ein Gerät über die Seite »Scan«.")
            self.btn_send.setEnabled(False)
        else:
            self.lbl_dev.setText(d.title)
            mp = max_payload(d.module, d.mtu)
            hdr = "mit 0x01-Header" if d.module.uses_header else "ohne Header"
            self.lbl_meta.setText(f"{d.module.label}  ·  Profil {d.profile}  ·  MTU {d.mtu}  ·  "
                                  f"max. {mp} Bytes/Paket ({hdr})  ·  TX {d.tx_bytes} B / RX {d.rx_bytes} B")
            self._sending_changed()
        self._update_count()
        self.rebuild_log()
        self._update_macro_enabled()

    def _sending_changed(self):
        d = self.dev()
        if d is None:
            return
        self.btn_send.setEnabled(True)
        self.btn_send.setText("Stopp" if d.sending else "Senden")
        self.btn_send.setObjectName("Danger" if d.sending else "Primary")
        self.btn_send.style().unpolish(self.btn_send)
        self.btn_send.style().polish(self.btn_send)
        self._update_macro_enabled()

    def on_sending(self, addr):
        if self.dev() and self.dev().address == addr:
            self._sending_changed()

    def on_meta(self, addr):
        d = self.dev()
        if d and d.address == addr:
            mp = max_payload(d.module, d.mtu)
            hdr = "mit 0x01-Header" if d.module.uses_header else "ohne Header"
            self.lbl_meta.setText(f"{d.module.label}  ·  Profil {d.profile}  ·  MTU {d.mtu}  ·  "
                                  f"max. {mp} Bytes/Paket ({hdr})  ·  TX {d.tx_bytes} B / RX {d.rx_bytes} B")
            self._update_count()

    def _read_mtu(self):
        d = self.dev()
        if d:
            self.mw.worker.read_mtu(d.address)

    def _disconnect(self):
        d = self.dev()
        if d:
            self.mw.worker.disconnect_device(d.address)

    # ------------------------------------------------------------------ Log
    def _enc(self) -> Encoding:
        return Encoding(self.enc.currentText())

    def _enc_changed(self):
        new = self._enc()
        # Eingabefeld in die neue Darstellung umrechnen
        try:
            data = from_text(self.payload.text(), self._prev_enc)
            self.payload.setText(to_text(data, Encoding.ASCII if new != Encoding.HEX else new))
        except ValueError:
            pass
        self._prev_enc = new
        self.mw.settings.set("encoding", self.enc.currentText())
        self._update_count()
        self.rebuild_log()

    def _visible(self, kind):
        g = KIND_GROUP.get(kind, "info")
        return {"info": self.cb_info, "data": self.cb_data, "cmd": self.cb_cmd}[g].isChecked()

    def _fmt(self, e) -> str:
        ms = self.mw.settings.get("timestamp_ms", True)
        t = time.strftime("%H:%M:%S", time.localtime(e.ts))
        if ms:
            t += f".{int((e.ts % 1) * 1000):03d}"
        col = LOG_COLORS.get(e.kind, "#ccc")
        arrow = {"tx": "▲", "rx": "▼", "cmd_tx": "▲", "cmd_rx": "▼", "error": "✖"}.get(e.kind, "•")
        out = (f'<span style="color:#4f5d70">{t}</span>&nbsp;&nbsp;'
               f'<span style="color:{col}">{arrow} {html.escape(e.text)}</span>')
        if e.data:
            enc = self._enc() if e.kind in ("tx", "rx") else Encoding.HEX
            txt = to_text(e.data, enc)
            txt = html.escape(txt).replace("\r\n", "↵<br>").replace("\n", "↵<br>").replace("\r", "↵<br>")
            out += (f'<br><span style="color:#e8eef5">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
                    f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{txt}</span>')
        return out

    def rebuild_log(self):
        self.log.clear()
        d = self.dev()
        if d is None:
            return
        chunk = [self._fmt(e) for e in d.log if self._visible(e.kind)]
        if chunk:
            self.log.appendHtml("<br>".join(chunk))
        self._scroll()

    def append(self, addr, entry):
        d = self.dev()
        if d is None or d.address != addr or not self._visible(entry.kind):
            return
        self.log.appendHtml(self._fmt(entry))
        self._scroll()
        if entry.kind in ("tx", "rx"):
            self.on_meta(addr)

    def _scroll(self):
        if self.btn_auto.isChecked():
            self.log.moveCursor(QTextCursor.End)
            sb = self.log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _clear_log(self):
        d = self.dev()
        if d:
            d.log.clear()
        self.log.clear()

    def _save_log(self):
        d = self.dev()
        if d is None:
            return
        name = (d.name or "geraet").replace(" ", "_")
        path, _ = QFileDialog.getSaveFileName(self, "Protokoll speichern",
                                              f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.txt",
                                              "Textdatei (*.txt);;CSV (*.csv)")
        if not path:
            return
        csv = path.lower().endswith(".csv")
        with open(path, "w", encoding="utf-8") as f:
            if csv:
                f.write("Zeit;Typ;Text;HEX;ASCII\n")
            for e in d.log:
                t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.ts)) + f".{int((e.ts % 1) * 1000):03d}"
                hx = to_text(e.data, Encoding.HEX)
                asc = to_text(e.data, Encoding.ASCII_PRINTABLE)
                if csv:
                    f.write(f'{t};{e.kind};"{e.text}";{hx};"{asc}"\n')
                else:
                    f.write(f"{t}  [{e.kind}]  {e.text}\n")
                    if e.data:
                        f.write(f"    HEX:   {hx}\n    ASCII: {asc}\n")
        self.mw.toast(f"Protokoll gespeichert: {path}")

    # ------------------------------------------------------------------ Senden
    def _opts_changed(self):
        self.sp_count.setEnabled(self.cb_multi.isChecked())
        self.sp_int.setEnabled(self.cb_multi.isChecked())
        self.sp_rand.setEnabled(self.cb_rand.isChecked())
        self.payload.setEnabled(not self.cb_rand.isChecked() and self.dev() is not None)
        self.cb_crlf.setEnabled(not self.cb_rand.isChecked())
        self._update_count()

    def _suffix(self) -> bytes:
        return [b"", b"\r", b"\n", b"\r\n"][self.cb_crlf.currentIndex()]

    def _update_count(self):
        enc = self._enc()
        self.payload.setPlaceholderText(
            "Nutzdaten als HEX, z. B. 48 61 6C 6C 6F" if enc == Encoding.HEX
            else "Nutzdaten als Text – Escapes: \\r \\n \\t \\xNN")
        d = self.dev()
        lim = f" / max. {max_payload(d.module, d.mtu)}" if d else ""
        if self.cb_rand.isChecked():
            self.lbl_bytes.setText(f"{self.sp_rand.value()} Bytes{lim}")
            return
        try:
            n = len(from_text(self.payload.text(), enc)) + len(self._suffix())
            self.lbl_bytes.setText(f"{n} Bytes{lim}")
            self.lbl_bytes.setStyleSheet("")
        except ValueError:
            self.lbl_bytes.setText("ungültig")
            self.lbl_bytes.setStyleSheet("color:#ff5f5f")

    def send(self):
        d = self.dev()
        if d is None:
            return
        if d.sending:
            self.mw.worker.stop_sending(d.address)
            return
        count = self.sp_count.value() if self.cb_multi.isChecked() else 1
        interval = self.sp_int.value() if self.cb_multi.isChecked() else 0
        if self.cb_rand.isChecked():
            n = self.sp_rand.value()
            payloads = [random_payload(n) for _ in range(min(count, 1000))]
        else:
            try:
                data = from_text(self.payload.text(), self._enc()) + self._suffix()
            except ValueError as exc:
                self.mw.toast(str(exc), error=True)
                return
            if not data:
                self.mw.toast("Keine Nutzdaten eingegeben.", error=True)
                return
            payloads = [data]
        self._dispatch(d, payloads, count, interval)

    def _dispatch(self, d, payloads, count, interval):
        mp = max_payload(d.module, d.mtu)
        if not self.cb_split.isChecked() and max(len(p) for p in payloads) > mp:
            self.mw.toast(f"Nutzdaten zu groß – max. {mp} Bytes pro Paket. "
                          "Option »Große Daten aufteilen« aktivieren.", error=True)
            return
        self.mw.worker.send_data(d.address, payloads, count, interval, self.cb_split.isChecked())

    # ------------------------------------------------------------------ Makros
    def rebuild_macros(self):
        while self.macro_lay.count():
            it = self.macro_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        macros = self.mw.settings.get("macros") or []
        if not macros:
            self.macro_lay.addWidget(label("Keine Makros – über »Makros …« anlegen.", "Muted"))
        for m in macros:
            b = QPushButton(m["name"])
            b.setObjectName("Chip")
            b.setToolTip(to_text(bytes.fromhex(m["hex"]), Encoding.HEX))
            b.clicked.connect(lambda _=False, h=m["hex"]: self._send_macro(h))
            self.macro_lay.addWidget(b)
        self.macro_lay.addStretch(1)
        self._update_macro_enabled()

    def _update_macro_enabled(self):
        d = self.dev()
        ok = d is not None and not d.sending
        for i in range(self.macro_lay.count()):
            w = self.macro_lay.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setEnabled(ok)

    def _send_macro(self, hexstr):
        d = self.dev()
        if d is None or d.sending:
            return
        count = self.sp_count.value() if self.cb_multi.isChecked() else 1
        interval = self.sp_int.value() if self.cb_multi.isChecked() else 0
        self._dispatch(d, [bytes.fromhex(hexstr)], count, interval)

    def _manage_macros(self):
        dlg = MacroDialog(self, self.mw.settings.get("macros") or [])
        if dlg.exec() == QDialog.Accepted:
            self.mw.settings.set("macros", dlg.macros)
            self.rebuild_macros()
