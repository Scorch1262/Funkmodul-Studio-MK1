"""COM-Port-Anbindung (pyserial) in einem eigenen Lese-Thread."""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Signal

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None


def available_ports() -> list[tuple[str, str]]:
    if list_ports is None:
        return []
    out = []
    for p in sorted(list_ports.comports(), key=lambda x: x.device):
        desc = p.description or ""
        if p.vid is not None:
            desc += f"  [{p.vid:04X}:{p.pid:04X}]"
        out.append((p.device, desc))
    return out


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

    def open(self, port: str, baud: int, bytesize=8, parity="N", stopbits=1.0, flow="none"):
        if serial is None:
            self.error.emit("pyserial ist nicht installiert.")
            return False
        self.close()
        try:
            self.ser = serial.Serial(
                port=port, baudrate=baud, bytesize=bytesize, parity=parity,
                stopbits=stopbits, timeout=0.05, write_timeout=2,
                rtscts=(flow == "rtscts"), xonxoff=(flow == "xonxoff"),
            )
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
