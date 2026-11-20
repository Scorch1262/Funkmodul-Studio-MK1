"""Bindeglied zwischen COM-Port, Frame-Auswertung und Oberfläche."""
from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from .framing import Frame, FrameParser, build_frame, describe, frame_name, frame_type
from .modules import MODULE_BY_KEY, ModuleDef
from .serial_worker import SerialWorker


@dataclass
class UartLog:
    ts: float
    kind: str          # tx | rx | info | error
    ftype: str         # REQ | CNF | IND | RSP | RAW | TEXT | ""
    text: str
    data: bytes


class UartController(QObject):
    log = Signal(object)            # UartLog
    frame = Signal(object)          # Frame (empfangen)
    state = Signal(bool, str)       # offen?, Port
    module_changed = Signal(object)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.worker = SerialWorker()
        self.module: ModuleDef = MODULE_BY_KEY.get(settings.get("uart_module", "proteus3"), MODULE_BY_KEY["proteus3"])
        self.parser = FrameParser(self.module.proto)
        self.raw_mode = False           # transparenter Modus: keine Frame-Auswertung
        self.port = ""
        self._textbuf = bytearray()
        self._raw_pending = bytearray()
        self._raw_timer = QTimer(self)
        self._raw_timer.setSingleShot(True)
        self._raw_timer.timeout.connect(self._flush_raw)
        self._frame_timer = QTimer(self)        # unvollständige Frames nach Pause verwerfen
        self._frame_timer.setSingleShot(True)
        self._frame_timer.timeout.connect(self._frame_timeout)
        w = self.worker
        w.received.connect(self._on_rx)
        w.opened.connect(self._on_open)
        w.closed.connect(self._on_close)
        w.error.connect(lambda m: self._emit("error", "", m, b""))

    # ------------------------------------------------------------------ Steuerung
    def set_module(self, key: str):
        self.module = MODULE_BY_KEY[key]
        self.parser = FrameParser(self.module.proto)
        self._textbuf.clear()
        self.settings.set("uart_module", key)
        self.module_changed.emit(self.module)
        self._emit("info", "", f"Modul: {self.module.label} ({self.module.family}) – {self.module.note}", b"")

    def set_raw_mode(self, on: bool):
        self.raw_mode = on
        self.parser = FrameParser(self.module.proto)
        self._emit("info", "", "Transparenter Modus " + ("ein – keine Frame-Auswertung" if on else "aus"), b"")

    def open(self, port, baud, bytesize, parity, stopbits, flow):
        self.port = port
        if self.worker.open(port, baud, bytesize, parity, stopbits, flow):
            self._emit("info", "", f"{port} geöffnet: {baud} Baud, {bytesize}{parity}{stopbits:g}, "
                                   f"Flusssteuerung {flow}", b"")

    def close(self):
        self.worker.close()

    @property
    def is_open(self):
        return self.worker.is_open

    def _on_open(self, port):
        self.state.emit(True, port)

    def _on_close(self, reason):
        self._flush_raw()
        self._emit("info", "", reason, b"")
        self.state.emit(False, self.port)

    # ------------------------------------------------------------------ Senden
    def send_command(self, cmd_code: int, payload: bytes, label: str = "") -> bool:
        frame = build_frame(self.module.proto, cmd_code, payload)
        return self.send_frame(frame, label)

    def send_frame(self, frame: bytes, label: str = "") -> bool:
        if not self.worker.write(frame):
            return False
        name = label or frame_name(self.module, frame[1])
        self._emit("tx", "REQ", f"{name}  ({len(frame)} Bytes)", frame)
        return True

    def send_raw(self, data: bytes, label="Rohdaten") -> bool:
        if not self.worker.write(data):
            return False
        is_text = self.module.proto in ("at", "text") and all(32 <= b < 127 or b in (9, 10, 13) for b in data)
        self._emit("tx", "TEXT" if is_text else "RAW", f"{label}  ({len(data)} Bytes)", data)
        return True

    # ------------------------------------------------------------------ Empfang
    def _on_rx(self, data: bytes):
        proto = self.module.proto
        if self.raw_mode or proto == "text":
            self._raw_pending += data
            self._raw_timer.start(30)
            return
        if proto == "at":
            self._textbuf += data
            while True:
                i = self._textbuf.find(b"\n")
                if i < 0:
                    break
                line = bytes(self._textbuf[: i + 1])
                del self._textbuf[: i + 1]
                if line.strip():
                    self._emit("rx", "TEXT", "Antwort", line)
            if self._textbuf:
                self._raw_timer.start(300)       # Zeile ohne Zeilenende (z. B. Prompt ">")
            return
        for item in self.parser.feed(data):
            if isinstance(item, Frame):
                self._flush_raw()
                t = frame_type(self.module, item.cmd)
                desc = describe(self.module, item)
                self._emit("rx", t, f"{frame_name(self.module, item.cmd)}  {desc}".rstrip(), item.raw)
                self.frame.emit(item)
            else:
                self._raw_pending += item
                self._raw_timer.start(30)
        if self.parser.buf:
            self._frame_timer.start(200)

    def _frame_timeout(self):
        rest = self.parser.flush()
        if rest:
            self._raw_pending += rest
            self._flush_raw()

    def _flush_raw(self):
        if self.module.proto == "at" and self._textbuf:
            self._emit("rx", "TEXT", "Antwort", bytes(self._textbuf))
            self._textbuf.clear()
        if self._raw_pending:
            data = bytes(self._raw_pending)
            self._raw_pending.clear()
            text = self.module.proto in ("text",) and all(32 <= b < 127 or b in (9, 10, 13) for b in data)
            self._emit("rx", "TEXT" if text else "RAW", f"Daten empfangen ({len(data)} Bytes)", data)

    def _emit(self, kind, ftype, text, data):
        self.log.emit(UartLog(time.time(), kind, ftype, text, bytes(data)))

    def shutdown(self):
        self.worker.close("Programm beendet.")
