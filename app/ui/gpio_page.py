from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ..protocol import (
    Cmd, GpioPin, LEVEL_LABEL, PIN_TYPE_LABEL, PULL_LABEL, PinType,
    gpio_read_body, gpio_write_body, gpio_writeconfig_body,
)
from .common import Card, hbox, label


class PinRow:
    """Widgets einer GPIO-Zeile."""

    def __init__(self, page, grid: QGridLayout, row: int, pin: GpioPin):
        self.page, self.pin = page, pin
        self.name = label(pin.name, "Accent")
        self.type = QComboBox()
        types = [PinType.NONE, PinType.INPUT, PinType.OUTPUT] + ([PinType.PWM] if pin.pwm_capable else [])
        for t in types:
            self.type.addItem(PIN_TYPE_LABEL[t], int(t))
        self.pull = QComboBox()
        for k, v in PULL_LABEL.items():
            self.pull.addItem(v, k)
        self.level = QComboBox()
        for k, v in LEVEL_LABEL.items():
            self.level.addItem(f"Start: {v}", k)
        self.period = QSpinBox()
        self.period.setRange(1, 65535)
        self.period.setSuffix(" ms")
        self.period.setPrefix("Periode ")
        self.ratio = QSpinBox()
        self.ratio.setRange(0, 100)
        self.ratio.setSuffix(" %")
        self.ratio.setPrefix("Tastgrad ")
        self.cfg = hbox(self.pull, self.level, self.period, self.ratio, None, spacing=6)

        self.val_lbl = label("–", "Teal")
        self.val_lbl.setMinimumWidth(60)
        self.btn_toggle = QPushButton("Umschalten")
        self.btn_toggle.clicked.connect(self._toggle)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setFixedWidth(140)
        self.slider.sliderReleased.connect(self._pwm_write)
        self.slider.valueChanged.connect(lambda v: self.val_lbl.setText(f"{v} %") if self.slider.isSliderDown() else None)
        self.val = hbox(self.val_lbl, self.btn_toggle, self.slider, None, spacing=6)

        grid.addWidget(self.name, row, 0)
        grid.addWidget(self.type, row, 1)
        grid.addWidget(self.cfg, row, 2)
        grid.addWidget(self.val, row, 3)
        self.type.currentIndexChanged.connect(self._type_changed)
        self.load()

    def load(self):
        p = self.pin
        for w in (self.type, self.pull, self.level, self.period, self.ratio):
            w.blockSignals(True)
        self.type.setCurrentIndex(max(0, self.type.findData(int(p.ptype))))
        self.pull.setCurrentIndex(max(0, self.pull.findData(p.pull)))
        self.level.setCurrentIndex(max(0, self.level.findData(p.level)))
        self.period.setValue(max(1, p.pwm_period_ms))
        self.ratio.setValue(p.pwm_ratio)
        for w in (self.type, self.pull, self.level, self.period, self.ratio):
            w.blockSignals(False)
        self._type_changed()
        self.show_value()

    def store(self):
        p = self.pin
        p.ptype = PinType(self.type.currentData())
        p.pull = self.pull.currentData()
        p.level = self.level.currentData()
        p.pwm_period_ms = self.period.value()
        p.pwm_ratio = self.ratio.value()

    def _type_changed(self):
        t = PinType(self.type.currentData())
        self.pull.setVisible(t == PinType.INPUT)
        self.level.setVisible(t == PinType.OUTPUT)
        self.period.setVisible(t == PinType.PWM)
        self.ratio.setVisible(t == PinType.PWM)
        self.show_value()

    def show_value(self):
        p = self.pin
        active = PinType(self.type.currentData()) == p.ptype   # Anzeige nur für gespeicherte Konfiguration
        t = p.ptype
        self.btn_toggle.setVisible(t == PinType.OUTPUT and active)
        self.slider.setVisible(t == PinType.PWM and active)
        if p.value is None or t == PinType.NONE:
            self.val_lbl.setText("–")
        elif t == PinType.PWM:
            self.val_lbl.setText(f"{p.value} %")
            if not self.slider.isSliderDown():
                self.slider.blockSignals(True)
                self.slider.setValue(p.value)
                self.slider.blockSignals(False)
        else:
            self.val_lbl.setText("HIGH" if p.value else "LOW")

    def _toggle(self):
        cur = self.pin.value if self.pin.value is not None else self.pin.level
        self.page.write_values([(self.pin.pin_id, 0 if cur else 1)])

    def _pwm_write(self):
        self.page.write_values([(self.pin.pin_id, self.slider.value())])


class GpioPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.rows: list[PinRow] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        head = Card("GPIO-Fernsteuerung")
        self.lbl_info = label("", "Muted")
        self.lbl_info.setWordWrap(True)
        head.lay.addWidget(self.lbl_info)
        self.b_rcfg = QPushButton("Konfiguration lesen")
        self.b_wcfg = QPushButton("Konfiguration schreiben")
        self.b_wcfg.setObjectName("Primary")
        self.b_read = QPushButton("Werte lesen")
        self.cb_poll = QCheckBox("Zyklisch lesen")
        self.sp_poll = QSpinBox()
        self.sp_poll.setRange(200, 60000)
        self.sp_poll.setValue(1000)
        self.sp_poll.setSuffix(" ms")
        self.b_rcfg.clicked.connect(self.read_config)
        self.b_wcfg.clicked.connect(self.write_config)
        self.b_read.clicked.connect(self.read_values)
        self.cb_poll.toggled.connect(self._poll_toggled)
        self.sp_poll.valueChanged.connect(lambda v: self.poll.setInterval(v))
        head.lay.addWidget(hbox(self.b_rcfg, self.b_wcfg, self.b_read, None, self.cb_poll, self.sp_poll))
        root.addWidget(head)

        self.pins_card = Card("Pins")
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(10)
        self.grid.setColumnStretch(2, 1)
        self.pins_card.lay.addWidget(self.grid_host)
        root.addWidget(self.pins_card)
        root.addStretch(1)

        self.poll = QTimer(self)
        self.poll.setInterval(1000)
        self.poll.timeout.connect(self.read_values)
        self.refresh_device()

    def dev(self):
        return self.mw.current_device()

    def refresh_device(self):
        for r in self.rows:
            for w in (r.name, r.type, r.cfg, r.val):
                w.setParent(None)
                w.deleteLater()
        self.rows = []
        d = self.dev()
        supported = d is not None and bool(d.gpio)
        for b in (self.b_rcfg, self.b_wcfg, self.b_read, self.cb_poll, self.sp_poll):
            b.setEnabled(supported)
        if d is None:
            self.lbl_info.setText("Kein Gerät verbunden.")
            self.pins_card.setVisible(False)
            self.cb_poll.setChecked(False)
            return
        if not d.gpio:
            self.lbl_info.setText(f"{d.module.label} unterstützt keine GPIO-Fernsteuerung. "
                                  "Verfügbar bei Proteus-III, Proteus-e und Setebos-I "
                                  "(Pins müssen im Modul für Fernzugriff freigegeben sein).")
            self.pins_card.setVisible(False)
            self.cb_poll.setChecked(False)
            return
        self.lbl_info.setText(f"{d.module.label} · {len(d.gpio)} Pins. Funktion wählen und "
                              "»Konfiguration schreiben«. Ausgänge lassen sich danach umschalten, "
                              "PWM über den Schieber einstellen.")
        self.pins_card.setVisible(True)
        hdrs = ["PIN", "FUNKTION", "KONFIGURATION", "WERT"]
        if self.grid.itemAtPosition(0, 0) is None:
            for c, h in enumerate(hdrs):
                self.grid.addWidget(label(h, "CardTitle"), 0, c)
        for i, pin in enumerate(d.gpio):
            self.rows.append(PinRow(self, self.grid, i + 1, pin))
        self._relayout()

    def _relayout(self):
        self.grid.invalidate()
        self.grid_host.updateGeometry()
        self.pins_card.updateGeometry()
        self.pins_card.lay.activate()
        self.layout().activate()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._relayout()

    def refresh_values(self, addr):
        d = self.dev()
        if d and d.address == addr:
            for r in self.rows:
                r.show_value()

    def refresh_config(self, addr):
        d = self.dev()
        if d and d.address == addr:
            for r in self.rows:
                r.load()

    # ------------------------------------------------------------------ Befehle
    def read_config(self):
        d = self.dev()
        if d:
            self.mw.worker.send_command(d.address, Cmd.GPIO_REMOTE_READCONFIG_REQ, b"",
                                        Cmd.GPIO_REMOTE_READCONFIG_CNF)

    def write_config(self):
        d = self.dev()
        if not d:
            return
        for r in self.rows:
            r.store()
        self.mw.pending_gpio_cfg[d.address] = [GpioPin(**vars(p)) for p in d.gpio]
        self.mw.worker.send_command(d.address, Cmd.GPIO_REMOTE_WRITECONFIG_REQ,
                                    gpio_writeconfig_body(d.gpio), Cmd.GPIO_REMOTE_WRITECONFIG_CNF)

    def read_values(self):
        d = self.dev()
        if not d:
            return
        pins = [p for p in d.gpio if p.ptype != PinType.NONE]
        if not pins:
            if not self.cb_poll.isChecked():
                self.mw.toast("Keine konfigurierten Pins zum Lesen.", error=True)
            return
        self.mw.worker.send_command(d.address, Cmd.GPIO_REMOTE_READ_REQ, gpio_read_body(pins),
                                    Cmd.GPIO_REMOTE_READ_CNF)

    def write_values(self, values):
        d = self.dev()
        if not d:
            return
        self.mw.pending_gpio_val[d.address] = dict(values)
        self.mw.worker.send_command(d.address, Cmd.GPIO_REMOTE_WRITE_REQ, gpio_write_body(values),
                                    Cmd.GPIO_REMOTE_WRITE_CNF)

    def _poll_toggled(self, on):
        if on:
            self.poll.start(self.sp_poll.value())
        else:
            self.poll.stop()
