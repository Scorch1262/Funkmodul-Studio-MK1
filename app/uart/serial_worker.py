"""COM-Port-Anbindung (pyserial) in einem eigenen Lese-Thread."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from .usb_chips import identify

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None


@dataclass
class PortInfo:
    device: str
    description: str
    chip: str
    driver_hint: str
    vid: int | None
    pid: int | None
    manufacturer: str
    product: str
    serial_number: str

    @property
    def label(self) -> str:
        prod = self.product or self.description or ""
        if prod and prod.lower().startswith(self.device.lower()):
            prod = ""
        extra = f"  ·  {prod}" if prod and prod not in self.chip else ""
        return f"{self.device}   {self.chip}{extra}"


def available_ports() -> list[PortInfo]:
    """Alle seriellen Ports – unabhängig vom USB-Seriell-Chip (FTDI, CP210x, CH340, PL2303, CDC …)."""
    if list_ports is None:
        return []
    out = []
    for p in sorted(list_ports.comports(), key=lambda x: _port_key(x.device)):
        chip, hint = identify(p.vid, p.pid, p.description or "")
        out.append(PortInfo(p.device, p.description or "", chip, hint, p.vid, p.pid,
                            p.manufacturer or "", p.product or "", p.serial_number or ""))
    return out


def _port_key(dev: str):
    digits = "".join(c for c in dev if c.isdigit())
    return (dev.rstrip("0123456789"), int(digits) if digits else 0)


def open_port(port, baud, bytesize=8, parity="N", stopbits=1.0, flow="none", dtr=False, rts=False, timeout=0.05):
    """Port öffnen und DTR/RTS schon VOR dem Öffnen festlegen.

    Viele Wandler (CH340, CP210x, PL2303, CDC) setzen DTR/RTS sonst beim Öffnen aktiv –
    auf Evaluation-Boards hängen daran oft RESET oder WAKE_UP des Funkmoduls.
    """
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.bytesize = bytesize
    ser.parity = parity
    ser.stopbits = stopbits
    ser.timeout = timeout
    ser.write_timeout = 2
    ser.rtscts = flow == "rtscts"
    ser.xonxoff = flow == "xonxoff"
    ser.dtr = dtr
    if flow != "rtscts":
        ser.rts = rts
    ser.open()
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    return ser


class SerialWorker(QObject):
    received = Signal(bytes)
    opened = Signal(str)
    closed = Signal(str)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.ser = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.tx_bytes = 0
        self.rx_bytes = 0

    @property
    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def open(self, port: str, baud: int, bytesize=8, parity="N", stopbits=1.0, flow="none",
             dtr: bool = False, rts: bool = False):
        if serial is None:
            self.error.emit("pyserial ist nicht installiert.")
            return False
        self.close()
        try:
            self.ser = open_port(port, baud, bytesize, parity, stopbits, flow, dtr, rts)
        except Exception as exc:
            self.ser = None
            self.error.emit(f"{port} konnte nicht geöffnet werden: {exc}")
            return False
        self.tx_bytes = self.rx_bytes = 0
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, name="uart-reader", daemon=True)
        self._thread.start()
        self.opened.emit(port)
        return True

    def close(self, reason="Port geschlossen."):
        if self.ser is None:
            return
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        try:
            self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.closed.emit(reason)

    def _reader(self):
        while not self._stop.is_set():
            try:
                n = self.ser.in_waiting
                data = self.ser.read(n or 1)
            except Exception as exc:
                if not self._stop.is_set():
                    self._stop.set()
                    self.error.emit(f"Lesefehler: {exc}")
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                    self.ser = None
                    self.closed.emit("Verbindung zum Port verloren.")
                return
            if data:
                self.rx_bytes += len(data)
                self.received.emit(bytes(data))

    def write(self, data: bytes) -> bool:
        if not self.is_open:
            self.error.emit("Kein COM-Port geöffnet.")
            return False
        try:
            with self._lock:
                self.ser.write(data)
                self.ser.flush()
            self.tx_bytes += len(data)
            return True
        except Exception as exc:
            self.error.emit(f"Schreibfehler: {exc}")
            return False

    def set_lines(self, dtr: bool | None = None, rts: bool | None = None):
        if not self.is_open:
            return
        try:
            if dtr is not None:
                self.ser.dtr = dtr
            if rts is not None:
                self.ser.rts = rts
        except Exception as exc:
            self.error.emit(f"Steuerleitung: {exc}")

    def pulse(self, line: str, ms: int = 100, active_low: bool = True):
        """Kurzer Impuls auf DTR/RTS, z. B. für RESET/WAKE_UP auf Evaluation-Boards."""
        if not self.is_open:
            return

        def job():
            on, off = (True, False) if active_low else (False, True)
            self.set_lines(**{line: on})
            time.sleep(ms / 1000)
            self.set_lines(**{line: off})
        threading.Thread(target=job, daemon=True).start()
