from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from .. import APP_NAME, APP_VERSION
from ..protocol import MODULES
from .common import Card, label


class InfoPage(QWidget):
    def __init__(self, mw):
        super().__init__()
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

        c = Card("Programm")
        c.lay.addWidget(label(APP_NAME, "Big"))
        c.lay.addWidget(label(f"Version {APP_VERSION}", "Accent"))
        t = label("Bluetooth-LE-Terminal für Windows zum Testen von Würth-Elektronik-Funkmodulen "
                  "über die Bluetooth-Schnittstelle des PCs oder Laptops – nach dem Vorbild der "
                  "mobilen »WE Bluetooth LE Terminal«-App. Unabhängiges Projekt, nicht von "
                  "Würth Elektronik eiSos herausgegeben.", "Muted")
        t.setWordWrap(True)
        c.lay.addWidget(t)
        root.addWidget(c)

        m = Card("Unterstützte Module")
        for spec in MODULES:
            feats = [spec.profile.value, f"Standard-MTU {spec.default_mtu}"]
            feats.append("Header 0x01/0x02" if spec.uses_header else "ohne Header")
            if spec.gpio_pins:
                feats.append(f"GPIO ({len(spec.gpio_pins)} Pins)")
            if spec.max_payload_request:
                feats.append("Abfrage max. Nutzdaten")
            m.lay.addWidget(label(f"{spec.label:<12}  ·  " + "  ·  ".join(feats)))
        root.addWidget(m)

        h = Card("Hinweise")
        for txt in (
            "Voraussetzung: Windows 10 (ab 1809) oder Windows 11 mit Bluetooth-4.0+-Adapter (BLE). "
            "Bluetooth muss in den Windows-Einstellungen eingeschaltet sein.",
            "Die Module müssen nicht in Windows gekoppelt werden – die Verbindung baut das Programm selbst auf.",
            "Proteus-I/II/III/e und Setebos-I erwarten vor den Nutzdaten das Header-Byte 0x01; "
            "das Programm fügt es automatisch hinzu und entfernt es beim Empfang.",
            "GPIO-Fernsteuerung funktioniert nur, wenn die Pins im Modul für den Fernzugriff "
            "freigegeben sind (siehe Modul-Handbuch, Remote-GPIO).",
            "Mehrere Geräte können gleichzeitig verbunden sein; das aktive Gerät wird oben rechts gewählt.",
            "Einstellungen und Makros liegen unter %APPDATA%\\" + APP_NAME + ".",
        ):
            lb = label("•  " + txt, "Muted")
            lb.setWordWrap(True)
            h.lay.addWidget(lb)
        root.addWidget(h)
        root.addStretch(1)
