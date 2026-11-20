"""Automatische Modul-Erkennung am COM-Port.

Probiert nacheinander Baudraten und Protokolle (Befehlsframes 16/8 Bit, Metis, AT, Text)
und grenzt das Modul über einzelne Nutzereinstellungen ein. Funktioniert mit jedem
USB-Seriell-Wandler, da nur der COM-Port benutzt wird.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from .framing import Frame, FrameParser, build_frame
from .serial_worker import open_port

DEFAULT_BAUDS = [115200, 9600, 921600, 57600, 38400, 19200, 230400, 460800]


@dataclass
class DetectResult:
    port: str
    baud: int
    proto: str
    module_key: str
    candidates: list = field(default_factory=list)
    details: str = ""
    sure: bool = False


class Detector(QObject):
    progress = Signal(str)
    found = Signal(object)          # DetectResult
    finished = Signal(int)          # Anzahl Treffer

    def __init__(self):
        super().__init__()
        self._cancel = threading.Event()
        self._thread = None

    def start(self, ports: list[str], bauds: list[int], dtr=False, rts=False, stop_first=True):
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(ports, bauds, dtr, rts, stop_first), daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    def _run(self, ports, bauds, dtr, rts, stop_first):
        hits = 0
        for port in ports:
            for baud in bauds:
                if self._cancel.is_set():
                    self.finished.emit(hits)
                    return
                self.progress.emit(f"{port} · {baud} Baud …")
                try:
                    ser = open_port(port, baud, dtr=dtr, rts=rts, timeout=0.02)
                except Exception as exc:
                    self.progress.emit(f"{port}: nicht nutzbar ({exc})")
                    break
                try:
                    res = self._probe(ser, port, baud)
                finally:
                    try:
                        ser.close()
                    except Exception:
                        pass
                if res:
                    hits += 1
                    self.found.emit(res)
                    if stop_first:
                        break
        self.finished.emit(hits)

    # ------------------------------------------------------------------ Hilfen
    @staticmethod
    def _xfer(ser, data: bytes, wait: float = 0.25) -> bytes:
        try:
            ser.reset_input_buffer()
        except Exception:
            pass
        ser.write(data)
        ser.flush()
        end = time.time() + wait
        buf = bytearray()
        while time.time() < end:
            chunk = ser.read(256)
            if chunk:
                buf += chunk
                end = max(end, time.time() + 0.05)
        return bytes(buf)

    def _frames(self, ser, proto, cmd, payload, want, wait=0.25):
        raw = self._xfer(ser, build_frame(proto, cmd, payload), wait)
        for it in FrameParser(proto).feed(raw):
            if isinstance(it, Frame) and it.cmd == want:
                return it
        return None

    def _get_ok(self, ser, sid: int) -> bytes | None:
        f = self._frames(ser, "cmd16", 0x10, bytes([sid]), 0x50)
        if f and f.payload and f.payload[0] == 0x00:
            return f.payload[1:]
        return None

    def _at(self, ser, cmd: str, wait=0.35) -> str:
        return self._xfer(ser, cmd.encode() + b"\r\n", wait).decode("latin-1", "replace")

    # ------------------------------------------------------------------ Proben
    def _probe(self, ser, port, baud) -> DetectResult | None:
        # 1) Befehlsframes mit 16-Bit-Länge: GETSTATE (Proteus, Thyone)
        f = self._frames(ser, "cmd16", 0x01, b"", 0x41)
        if f:
            return self._classify_cmd16(ser, port, baud)
        # Metis-e: GET Firmware (Option 0x81)
        f = self._frames(ser, "cmd16", 0x05, b"\x81", 0x45)
        if f:
            return DetectResult(port, baud, "cmd16", "metise", ["metise"], "Antwort auf CMD_GET (Option 0x81)", True)
        # 2) Befehlsframes mit 8-Bit-Länge: GET Firmware-Version (Tarvos-Familie)
        f = self._frames(ser, "cmd8", 0x0A, b"\x21", 0x4A)
        if f:
            fw = " ".join(f"{b:02X}" for b in f.payload[1:]) if len(f.payload) > 1 else "?"
            return DetectResult(port, baud, "cmd8", "tarvos3",
                                ["tarvos3", "tarvose", "telesto3", "thebe2", "themisto1"],
                                f"Sub-GHz-Modul (Tarvos/Telesto/Thebe/Themisto), Firmware {fw} – "
                                "Typ bitte anhand der Frequenz wählen", False)
        # 3) Metis-I/-II: GET_FWRELEASE
        f = self._frames(ser, "metis", 0x0C, b"", 0x8C)
        if f:
            return DetectResult(port, baud, "metis", "metis", ["metis"], "Antwort auf CMD_GET_FWRELEASE", True)
        # 4) AT-Befehle
        r = self._at(ser, "AT+test")
        if "OK" in r.upper() and "ERROR" not in r.upper():
            key = "calypso" if baud == 921600 else "cordelia"
            return DetectResult(port, baud, "at", key, ["calypso", "cordelia"],
                                "Antwort auf AT+test (Calypso/Cordelia)", False)
        r = self._at(ser, "AT+GMR")
        if "AT VERSION" in r.upper() or ("OK" in r and "SDK" in r.upper()):
            return DetectResult(port, baud, "at", "stephano", ["stephano"], "Antwort auf AT+GMR", True)
        r = self._at(ser, "AT+CGMI")
        if "OK" in r and len(r.strip()) > 2:
            return DetectResult(port, baud, "at", "adrastea", ["adrastea"], "Antwort auf AT+CGMI: " +
                                " ".join(r.split())[:40], True)
        r = self._at(ser, "AT+VER=?") + self._at(ser, "AT")
        if "OK" in r.upper() or "AT_ERROR" in r.upper():
            return DetectResult(port, baud, "at", "daphnis", ["daphnis"], "Antwort auf AT-Befehl (LoRaWAN-AT)", False)
        # 5) Skoll-I (EZSerial-Text-API)
        r = self._xfer(ser, b"/PING\r\n", 0.3).decode("latin-1", "replace")
        if "@R" in r or ("PING" in r.upper() and len(r) > 7):
            return DetectResult(port, baud, "text", "skoll", ["skoll"], "Antwort auf /PING", False)
        return None

    def _classify_cmd16(self, ser, port, baud) -> DetectResult:
        has01 = self._get_ok(ser, 0x01) is not None
        has0f = self._get_ok(ser, 0x0F) is not None
        name = self._get_ok(ser, 0x02)
        if has01 and not has0f:
            fw = self._get_ok(ser, 0x02)
            mode = self._get_ok(ser, 0x16)       # CCA_Mode nur Thyone-I
            key = "thyone1" if mode is not None else "thyonee"
            fwt = " ".join(f"{b:02X}" for b in fw) if fw else "?"
            return DetectResult(port, baud, "cmd16", key, ["thyone1", "thyonee"],
                                f"Thyone-Familie, Firmware {fwt}", mode is not None)
        nm = name.split(b"\x00")[0].decode("latin-1", "replace") if name else ""
        if has01 and has0f:
            return DetectResult(port, baud, "cmd16", "proteus4", ["proteus4"],
                                f"Proteus-IV, Name »{nm}«", True)
        if self._get_ok(ser, 0x23) is not None:
            key = "proteus3"
        elif self._get_ok(ser, 0x24) is not None:
            key = "proteuse"
        else:
            key = "proteus2"
        return DetectResult(port, baud, "cmd16", key, ["proteus2", "proteus3", "proteuse"],
                            f"Proteus-Familie, Name »{nm}«", True)
