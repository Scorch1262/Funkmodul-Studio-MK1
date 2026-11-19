from __future__ import annotations

import time
from dataclasses import dataclass, field

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..protocol import GpioPin, ModuleSpec


@dataclass
class LogEntry:
    ts: float
    kind: str
    text: str
    data: bytes


@dataclass
class DeviceState:
    address: str
    name: str
    module: ModuleSpec
    profile: str = ""
    mtu: int = 0
    sending: bool = False
    log: list[LogEntry] = field(default_factory=list)
    gpio: list[GpioPin] = field(default_factory=list)
    connected_at: float = field(default_factory=time.time)
    rx_bytes: int = 0
    tx_bytes: int = 0

    @property
    def title(self) -> str:
        return f"{self.name or 'Unbenannt'}  ·  {self.address}"


class Card(QFrame):
    def __init__(self, title: str | None = None, parent=None, margins=(14, 12, 14, 14)):
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(*margins)
        self.lay.setSpacing(10)
        if title:
            t = QLabel(title.upper())
            t.setObjectName("CardTitle")
            self.lay.addWidget(t)


def label(text: str, obj: str | None = None) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    return lb


def hbox(*widgets, spacing=8, margins=(0, 0, 0, 0), stretch_at=None) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for i, wd in enumerate(widgets):
        if wd is None:
            lay.addStretch(1)
        else:
            lay.addWidget(wd)
    return w


def set_pill(lbl: QLabel, text: str, state: str = ""):
    lbl.setText(text)
    lbl.setProperty("state", state)
    lbl.style().unpolish(lbl)
    lbl.style().polish(lbl)
