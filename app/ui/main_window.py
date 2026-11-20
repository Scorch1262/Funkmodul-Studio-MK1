from __future__ import annotations

import time

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..ble_worker import BleWorker
from ..protocol import Cmd, GpioPin, MODULE_BY_KEY, PinType
from ..settings import Settings
from .common import DeviceState, LogEntry, label, set_pill
from .gpio_page import GpioPage
from .info_page import InfoPage
from .scan_page import ScanPage
from .settings_page import SettingsPage
from .terminal_page import TerminalPage
from .uart_page import UartPage
from .uart_settings_page import UartSettingsPage
from ..uart.controller import UartController


class MainWindow(QMainWindow):
    def __init__(self, icon: QIcon | None = None):
        super().__init__()
        self.settings = Settings()
        self.devices: dict[str, DeviceState] = {}
        self.current: str | None = None
        self.pending_gpio_cfg: dict[str, list[GpioPin]] = {}
        self.pending_gpio_val: dict[str, dict] = {}

        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        if icon:
            self.setWindowIcon(icon)
        self.resize(1280, 820)
        self.setMinimumSize(1100, 700)

        self.worker = BleWorker(self.settings)
        self.uart = UartController(self.settings)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # --- Kopfzeile ----------------------------------------------------
        top = QFrame()
        top.setObjectName("TopBar")
        top.setFixedHeight(58)
        th = QHBoxLayout(top)
        th.setContentsMargins(18, 0, 18, 0)
        th.setSpacing(12)
        dot = QLabel("◆")
        dot.setStyleSheet("color:#ffb020; font-size:15pt;")
        tcol = QWidget()
        tl = QVBoxLayout(tcol)
        tl.setContentsMargins(0, 8, 0, 8)
        tl.setSpacing(0)
        tl.addWidget(label("PROTEUS BLE TERMINAL", "AppTitle"))
        tl.addWidget(label(f"MK1 · v{APP_VERSION} · Bluetooth LE über PC-Adapter · UART-Befehlsschnittstelle", "AppSub"))
        th.addWidget(dot)
        th.addWidget(tcol)
        th.addStretch(1)
        self.pill_scan = QLabel()
        self.pill_scan.setObjectName("Pill")
        self.pill_conn = QLabel()
        self.pill_conn.setObjectName("Pill")
        self.pill_uart = QLabel()
        self.pill_uart.setObjectName("Pill")
        for pill in (self.pill_scan, self.pill_conn, self.pill_uart):
            pill.setFixedHeight(24)
            th.addWidget(pill, 0, Qt.AlignVCenter)
        th.addSpacing(10)
        th.addWidget(label("AKTIVES GERÄT", "CardTitle"))
        self.dev_combo = QComboBox()
        self.dev_combo.setMinimumWidth(300)
        self.dev_combo.currentIndexChanged.connect(self._combo_changed)
        th.addWidget(self.dev_combo, 0, Qt.AlignVCenter)
        v.addWidget(top)

        # --- Körper -------------------------------------------------------
        body = QWidget()
        bh = QHBoxLayout(body)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(0)
        side = QFrame()
        side.setObjectName("SideBar")
        side.setFixedWidth(215)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 14, 0, 14)
        sv.setSpacing(2)
        self.stack = QStackedWidget()
        self.scan = ScanPage(self)
        self.terminal = TerminalPage(self)
        self.gpio = GpioPage(self)
        self.settings_page = SettingsPage(self)
        self.uart_page = UartPage(self)
        self.uart_settings = UartSettingsPage(self)
        self.info = InfoPage(self)
        self.pages = {"scan": self.scan, "terminal": self.terminal, "gpio": self.gpio,
                      "uart": self.uart_page, "uart_settings": self.uart_settings,
                      "settings": self.settings_page, "info": self.info}
        self.nav = QButtonGroup(self)
        self.nav_btns = {}
        for key, text in (("scan", "SCAN"), ("terminal", "TERMINAL"), ("gpio", "GPIO"),
                          ("uart", "UART-TERMINAL"), ("uart_settings", "MODUL-EINSTELLUNGEN"),
                          ("settings", "EINSTELLUNGEN"), ("info", "INFO")):
            if key == "scan":
                sv.addWidget(self._section("BLUETOOTH LE (PC)"))
            elif key == "uart":
                sv.addWidget(self._section("UART · SMARTCOMMANDER"))
            elif key == "settings":
                sv.addWidget(self._section("PROGRAMM"))
            b = QPushButton(text)
            b.setObjectName("NavBtn")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.goto(k))
            self.nav.addButton(b)
            self.nav_btns[key] = b
            sv.addWidget(b)
            self.stack.addWidget(self.pages[key])
            if key in ("gpio", "uart_settings"):
                sv.addSpacing(14)
        sv.addStretch(1)
        self.side_status = label("", "Muted")
        self.side_status.setWordWrap(True)
        self.side_status.setContentsMargins(16, 0, 12, 0)
        sv.addWidget(self.side_status)
        bh.addWidget(side)
        bh.addWidget(self.stack, 1)
        v.addWidget(body, 1)

        # --- Meldungsleiste ----------------------------------------------
        self.toast_lbl = QLabel("")
        self.toast_lbl.setStyleSheet("background:#151d27; border-top:1px solid #233041; padding:6px 18px; color:#7a889a;")
        v.addWidget(self.toast_lbl)
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(lambda: self.toast_lbl.setText(""))

        # --- Signale ------------------------------------------------------
        w = self.worker
        w.scan_result.connect(self.scan.on_result)
        w.scan_state.connect(self._on_scan_state)
        w.connecting.connect(lambda a: self.toast(f"Verbinde mit {a} …"))
        w.connected.connect(self._on_connected)
        w.disconnected.connect(self._on_disconnected)
        w.log.connect(self._on_log)
        w.incoming.connect(self._on_incoming)
        w.mtu_changed.connect(self._on_mtu)
        w.sending_state.connect(self._on_sending)
        w.error.connect(lambda m: self.toast(m, error=True))

        self.pending_logs: dict[str, list[LogEntry]] = {}
        self._on_scan_state(False)
        self._update_status()
        geo = self.settings.get("window")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
            except Exception:
                pass
        self.goto("scan")

    # ------------------------------------------------------------------ Navigation
    def goto(self, key):
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_btns[key].setChecked(True)

    def toast(self, text, error=False):
        self.toast_lbl.setStyleSheet(
            "background:#151d27; border-top:1px solid #233041; padding:6px 18px; color:%s;"
            % ("#ff5f5f" if error else "#1fd1c1"))
        self.toast_lbl.setText(text.replace("\n", "  "))
        self.toast_timer.start(8000 if error else 5000)

    def current_device(self) -> DeviceState | None:
        return self.devices.get(self.current) if self.current else None

    def select_device(self, addr):
        i = self.dev_combo.findData(addr)
        if i >= 0:
            self.dev_combo.setCurrentIndex(i)

    def _combo_changed(self):
        self.current = self.dev_combo.currentData()
        self.terminal.refresh_device()
        self.gpio.refresh_device()

    def _rebuild_combo(self, select=None):
        self.dev_combo.blockSignals(True)
        self.dev_combo.clear()
        if not self.devices:
            self.dev_combo.addItem("— kein Gerät verbunden —", None)
        for addr, d in self.devices.items():
            self.dev_combo.addItem(f"{d.name or 'Unbenannt'}  ({d.module.label})  {addr}", addr)
        self.dev_combo.blockSignals(False)
        target = select if select in self.devices else (self.current if self.current in self.devices else None)
        if target is None and self.devices:
            target = next(iter(self.devices))
        i = self.dev_combo.findData(target)
        self.dev_combo.setCurrentIndex(max(0, i))
        self._combo_changed()

    def _update_status(self):
        n = len(self.devices)
        set_pill(self.pill_conn, f"{n} VERBUNDEN", "ok" if n else "")
        lines = [f"{d.name or d.address}\n{d.module.label}" for d in self.devices.values()]
        self.side_status.setText("\n\n".join(lines) if lines else "Keine BLE-Verbindung")

    @staticmethod
    def _section(text):
        lb = label(text, "CardTitle")
        lb.setContentsMargins(16, 6, 8, 4)
        lb.setStyleSheet("font-size:7.5pt; color:#4f5d70;")
        return lb

    def update_uart_pill(self, is_open, port):
        set_pill(self.pill_uart, f"UART {port}" if is_open else "UART AUS", "ok" if is_open else "")

    def _on_scan_state(self, on):
        set_pill(self.pill_scan, "SCAN AKTIV" if on else "SCAN AUS", "warn" if on else "")
        self.scan.on_scan_state(on)

    # ------------------------------------------------------------------ Verbindung
    def connect_device(self, addr, name, module_key):
        self.worker.connect_device(addr, name, MODULE_BY_KEY[module_key])

    def _on_connected(self, addr, info):
        mod = MODULE_BY_KEY[info["module"]]
        d = DeviceState(addr, info.get("name", ""), mod, info.get("profile", ""), info.get("mtu", mod.default_mtu))
        d.gpio = [GpioPin(pid, name, pwm) for pid, name, pwm in mod.gpio_pins]
        d.log = self.pending_logs.pop(addr, [])
        # Ergebnis der Konfigurationsabfrage während der Initialisierung übernehmen
        cfg = self.pending_gpio_cfg.pop(addr + "#init", None)
        if cfg:
            self._apply_config(d, cfg)
        self.devices[addr] = d
        self._rebuild_combo(select=addr)
        self._update_status()
        self.toast(f"Verbunden mit {d.name or addr} ({mod.label}).")
        self.goto("terminal")

    def _on_disconnected(self, addr, reason):
        self.pending_logs.pop(addr, None)
        d = self.devices.pop(addr, None)
        if d is None:
            self.toast(reason, error=True)
            return
        self._rebuild_combo()
        self._update_status()
        self.toast(f"{d.name or addr}: {reason}", error=reason != "Getrennt.")

    def _on_log(self, addr, kind, text, data):
        e = LogEntry(time.time(), kind, text, bytes(data))
        d = self.devices.get(addr)
        if d is None:
            # Meldungen während des Verbindungsaufbaus puffern
            self.pending_logs.setdefault(addr, []).append(e)
            return
        if kind == "tx":
            d.tx_bytes += len(data)
        elif kind == "rx":
            d.rx_bytes += len(data)
        d.log.append(e)
        lim = int(self.settings.get("log_max", 5000))
        if len(d.log) > lim:
            del d.log[: len(d.log) - lim]
        self.terminal.append(addr, e)

    def _on_mtu(self, addr, mtu):
        d = self.devices.get(addr)
        if d:
            d.mtu = mtu
            self.terminal.on_meta(addr)

    def _on_sending(self, addr, on):
        d = self.devices.get(addr)
        if d:
            d.sending = on
            self.terminal.on_sending(addr)

    # ------------------------------------------------------------------ GPIO-Antworten
    def _apply_config(self, d: DeviceState, cfg):
        pins = {p.pin_id: p for p in d.gpio}
        for pid, ptype, raw in cfg:
            p = pins.get(pid)
            if p is None:
                continue
            try:
                p.ptype = PinType(ptype)
            except ValueError:
                p.ptype = PinType.NONE
            if p.ptype == PinType.INPUT and raw:
                p.pull = raw[0]
            elif p.ptype == PinType.OUTPUT and raw:
                p.level = raw[0]
                p.value = raw[0]
            elif p.ptype == PinType.PWM and len(raw) >= 3:
                p.pwm_period_ms = (raw[0] << 8) | raw[1]
                p.pwm_ratio = raw[2]
                p.value = raw[2]

    def _on_incoming(self, addr, inc):
        if inc.kind != "cmd":
            return
        d = self.devices.get(addr)
        if inc.cmd == Cmd.GPIO_REMOTE_READCONFIG_CNF:
            cfg = inc.info.get("config", [])
            if d is None:
                self.pending_gpio_cfg[addr + "#init"] = cfg
                return
            self._apply_config(d, cfg)
            self.gpio.refresh_config(addr)
        elif d is None:
            return
        elif inc.cmd == Cmd.GPIO_REMOTE_WRITECONFIG_CNF:
            sent = {p.pin_id: p for p in self.pending_gpio_cfg.pop(addr, [])}
            pins = {p.pin_id: p for p in d.gpio}
            bad = []
            for pid, status in inc.info.get("status", []):
                if status == 0 and pid in sent and pid in pins:
                    s = sent[pid]
                    p = pins[pid]
                    p.ptype, p.pull, p.level = s.ptype, s.pull, s.level
                    p.pwm_period_ms, p.pwm_ratio = s.pwm_period_ms, s.pwm_ratio
                    p.value = s.level if s.ptype == PinType.OUTPUT else (s.pwm_ratio if s.ptype == PinType.PWM else None)
                elif status != 0:
                    bad.append(pins[pid].name if pid in pins else str(pid))
            self.gpio.refresh_config(addr)
            if bad:
                self.toast("Konfiguration abgelehnt für: " + ", ".join(bad) +
                           " (Pin für Fernzugriff freigegeben?)", error=True)
            else:
                self.toast("GPIO-Konfiguration übernommen.")
        elif inc.cmd == Cmd.GPIO_REMOTE_WRITE_CNF:
            sent = self.pending_gpio_val.pop(addr, {})
            pins = {p.pin_id: p for p in d.gpio}
            bad = []
            for pid, status in inc.info.get("status", []):
                if status == 0 and pid in sent and pid in pins:
                    pins[pid].value = sent[pid]
                elif status != 0:
                    bad.append(pins[pid].name if pid in pins else str(pid))
            self.gpio.refresh_values(addr)
            if bad:
                self.toast("Schreiben fehlgeschlagen für: " + ", ".join(bad), error=True)
        elif inc.cmd in (Cmd.GPIO_REMOTE_READ_CNF, Cmd.GPIO_LOCAL_WRITE_IND):
            pins = {p.pin_id: p for p in d.gpio}
            for pid, val in inc.info.get("values", []):
                p = pins.get(pid)
                if p is None:
                    continue
                if p.ptype in (PinType.INPUT, PinType.OUTPUT) and val in (0, 1):
                    p.value = val
                elif p.ptype == PinType.PWM and val != 0xFF:
                    p.value = val
            self.gpio.refresh_values(addr)

    # ------------------------------------------------------------------ Ende
    def closeEvent(self, ev):
        self.settings.data["window"] = bytes(self.saveGeometry().toBase64()).decode()
        self.settings.save()
        self.toast("Verbindungen werden getrennt …")
        try:
            self.uart.shutdown()
        except Exception:
            pass
        try:
            self.worker.shutdown()
        except Exception:
            pass
        ev.accept()
