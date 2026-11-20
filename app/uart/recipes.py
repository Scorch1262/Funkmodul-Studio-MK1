"""Beispiel-Abläufe je Modul: Befehlsfolgen mit Parametern, erwarteter Antwort und Erklärung.

Platzhalter in Befehlen:  {NAME}        Wert unverändert
                          {NAME:hex}    Text → HEX-Bytes
                          {NAME:u8}     Zahl → 1 Byte HEX
                          {NAME:u16le}  Zahl → 2 Byte HEX, LSB zuerst
                          {NAME:u32le}  Zahl → 4 Byte HEX, LSB zuerst
                          {NAME:mac}    AA:BB:CC:DD:EE:FF → HEX, LSB zuerst
                          {NAME:dec3}   Zahl dreistellig (001)
                          {NAME:len}    Länge des Textes in Bytes
Erwartete Antwort: Text (mehrere Möglichkeiten mit »|«) oder Frame-Code (Zahl).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    kind: str                  # at | text | hex | frame | expect | wait | hint
    value: str = ""            # Befehl / Text / HEX-Nutzdaten
    expect: object = None      # str oder int (Frame-Code) oder None
    timeout: int = 3000        # ms
    desc: str = ""
    code: int = 0              # Befehlscode bei »frame«
    optional: bool = False     # Fehler hier bricht den Ablauf nicht ab


@dataclass(frozen=True)
class Var:
    key: str
    label: str
    default: str
    hint: str = ""


@dataclass
class Recipe:
    name: str
    desc: str
    steps: list
    vars: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Kurzschreibweisen
# ---------------------------------------------------------------------------

def A(cmd, expect="OK", timeout=3000, desc="", optional=False):
    return Step("at", cmd, expect, timeout, desc, optional=optional)


def T(text, expect=None, timeout=3000, desc=""):
    return Step("text", text, expect, timeout, desc)


def X(hexs, expect=None, timeout=3000, desc=""):
    return Step("hex", hexs, expect, timeout, desc)


def F(code, payload="", expect=None, timeout=2000, desc="", optional=False):
    return Step("frame", payload, expect, timeout, desc, code, optional)


def E(expect, timeout=10000, desc="", optional=False):
    return Step("expect", "", expect, timeout, desc, optional=optional)


def W(ms, desc=""):
    return Step("wait", "", None, ms, desc or f"{ms / 1000:g} s warten")


def H(text):
    return Step("hint", text, None, 0, text)


V = Var


# ---------------------------------------------------------------------------
# Würth Bluetooth LE: Proteus
# ---------------------------------------------------------------------------

def _proteus(variant):
    r = [
        Recipe("Initialisierung nach dem Start",
               "Modul neu starten und die wichtigsten Daten auslesen. Nach dem Start meldet das Modul "
               "mit CMD_GETSTATE_CNF, dass es bereit ist.", [
                   F(0x00, "", 0x41, 3000, "Neustart – warten, bis das Modul »bereit« meldet"),
                   F(0x01, "", 0x41, 1000, "Status: Rolle (Peripheral/Central) und Verbindungszustand"),
                   F(0x10, "02", 0x50, 1000, "Gerätename lesen (Einstellung 0x02)"),
                   F(0x10, "04", 0x50, 1000, "Bluetooth-MAC lesen (Einstellung 0x04)"),
                   F(0x10, "0F", 0x50, 1000, "Geräteinfo / Firmware lesen (Einstellung 0x0F)"),
                   F(0x10, "11", 0x50, 1000, "Sendeleistung lesen (Einstellung 0x11)"),
               ]),
        Recipe("Gerätenamen ändern",
               "Schreibt den Namen, unter dem das Modul per Bluetooth sichtbar ist, und startet neu.", [
                   F(0x11, "02 {NAME:hex}", 0x51, 2000, "Einstellung 0x02 (RF_DeviceName) schreiben"),
                   F(0x00, "", 0x41, 3000, "Neustart, damit der Name gilt"),
                   F(0x10, "02", 0x50, 1000, "Zur Kontrolle zurücklesen"),
               ], [V("NAME", "Neuer Name", "Proteus-Test", "max. 8–20 Zeichen je nach Modul")]),
        Recipe("Daten an verbundenes Gerät senden",
               "Wartet auf eine Verbindung (z. B. vom Smartphone oder dem Bluetooth-Teil dieses Programms) "
               "und sendet dann Daten. Funkdaten der Gegenstelle kommen als CMD_DATA_IND.", [
                   F(0x01, "", 0x41, 1000, "Status prüfen – ist schon eine Verbindung offen?"),
                   E(0xC6, 60000, "Auf geöffneten Datenkanal warten (CMD_CHANNELOPEN_RSP) – jetzt verbinden", True),
                   F(0x04, "{DATEN:hex}", 0x44, 2000, "Daten senden (CMD_DATA_REQ)"),
                   E(0xC4, 3000, "Bestätigung, dass die Daten übertragen wurden (CMD_TXCOMPLETE_RSP)", True),
               ], [V("DATEN", "Text", "Hallo vom PC")]),
        Recipe("Verbindung trennen", "Beendet die aktuelle Bluetooth-Verbindung.", [
            F(0x07, "", 0x47, 2000, "CMD_DISCONNECT_REQ"),
            E(0x87, 5000, "Meldung »getrennt« (CMD_DISCONNECT_IND)", True),
        ]),
        Recipe("Kopplungen anzeigen und löschen", "Listet gespeicherte Kopplungen und löscht sie.", [
            F(0x0F, "", 0x4F, 2000, "Gespeicherte Kopplungen auflisten"),
            F(0x0E, "", 0x4E, 2000, "Alle Kopplungen löschen"),
            F(0x0F, "", 0x4F, 2000, "Kontrolle – Liste sollte leer sein"),
        ]),
        Recipe("Werkseinstellungen", "Setzt alle Einstellungen zurück – Name, Baudrate und Sicherheit inklusive.", [
            H("Alle Nutzereinstellungen gehen verloren. Fortfahren?"),
            F(0x1C, "", 0x5C, 3000, "CMD_FACTORYRESET_REQ"),
            E(0x41, 4000, "Modul startet neu und meldet sich bereit", True),
        ]),
    ]
    if variant in ("II", "III"):
        r.insert(2, Recipe(
            "Andere Geräte suchen und verbinden (Central)",
            "Das Modul sucht selbst nach Bluetooth-Geräten und verbindet sich mit einer MAC-Adresse.", [
                F(0x09, "", 0x49, 1000, "Suche starten (CMD_SCANSTART_REQ)"),
                W(4000, "4 s suchen lassen"),
                F(0x0A, "", 0x4A, 1000, "Suche beenden"),
                F(0x0B, "", 0x4B, 2000, "Gefundene Geräte abrufen – MAC, RSSI und Name stehen im CNF"),
                F(0x06, "{MAC:mac}", 0x46, 2000, "Verbindungsaufbau zur MAC-Adresse starten"),
                E(0x86, 10000, "Verbindung hergestellt (CMD_CONNECT_IND)"),
                E(0xC6, 10000, "Datenkanal offen (CMD_CHANNELOPEN_RSP)"),
                F(0x04, "{DATEN:hex}", 0x44, 2000, "Erste Daten senden"),
            ], [V("MAC", "MAC-Adresse der Gegenstelle", "00:18:DA:12:34:56", "wie in der Geräteliste angezeigt"),
                V("DATEN", "Text", "Hallo")]))
    if variant in ("III", "e"):
        r.append(Recipe(
            "Lokalen GPIO als Ausgang schalten",
            "Konfiguriert Pin B1 als Ausgang und schaltet ihn ein und wieder aus (z. B. LED).", [
                F(0x25, "03 01 02 00", 0x65, 1000, "B1 als Ausgang, Startpegel Low"),
                F(0x26, "02 01 01", 0x66, 1000, "B1 auf High"),
                W(1000),
                F(0x26, "02 01 00", 0x66, 1000, "B1 auf Low"),
                F(0x2B, "", 0x6B, 1000, "Konfiguration zur Kontrolle lesen"),
            ]))
    return r


def _proteus4():
    return [
        Recipe("Initialisierung nach dem Start", "Neustart und Grunddaten lesen.", [
            F(0x00, "", 0x81, 3000, "Neustart – Modul meldet sich mit STARTUP_IND"),
            F(0x01, "", 0x41, 1000, "Status abfragen"),
            F(0x10, "01", 0x50, 1000, "Firmware-Version (Einstellung 0x01)"),
            F(0x10, "02", 0x50, 1000, "Gerätename"),
            F(0x10, "04", 0x50, 1000, "Bluetooth-MAC"),
        ]),
        Recipe("Suchen, verbinden und senden", "Proteus-IV als Central: Suche, Verbindung, Daten.", [
            F(0x09, "01", 0x49, 1000, "Scan starten"),
            W(4000),
            F(0x09, "00", 0x49, 1000, "Scan stoppen"),
            F(0x06, "{MAC:mac}", 0x46, 2000, "Verbinden"),
            E(0xC6, 10000, "Verbindung offen (LINKOPEN_RSP)"),
            F(0x13, "00", 0x53, 1000, "Maximale Nutzdatenlänge der Verbindung 0"),
            F(0x04, "00 {DATEN:hex}", 0x44, 2000, "Daten auf Verbindung 0 senden"),
        ], [V("MAC", "MAC-Adresse", "00:18:DA:12:34:56"), V("DATEN", "Text", "Hallo")]),
        Recipe("Werbung starten / stoppen", "Peripheral-Betrieb ein- und ausschalten.", [
            F(0x12, "01", 0x52, 1000, "Werbung starten"),
            W(10000, "10 s sichtbar"),
            F(0x12, "00", 0x52, 1000, "Werbung stoppen"),
        ]),
    ]


# ---------------------------------------------------------------------------
# Thyone
# ---------------------------------------------------------------------------

def _thyone():
    return [
        Recipe("Initialisierung nach dem Start", "Neustart und Netzparameter lesen.", [
            F(0x00, "", 0x73, 3000, "Neustart – Modul meldet sich mit CMD_START_IND"),
            F(0x01, "", 0x41, 1000, "Status abfragen"),
            F(0x10, "01", 0x50, 1000, "Seriennummer"),
            F(0x10, "02", 0x50, 1000, "Firmware-Version"),
            F(0x10, "07", 0x50, 1000, "Funkkanal"),
            F(0x10, "10", 0x50, 1000, "Eigene Adresse (MAC_SourceAddress)"),
            F(0x10, "11", 0x50, 1000, "Zieladresse"),
            F(0x10, "0B", 0x50, 1000, "Sendeleistung"),
        ]),
        Recipe("Funknetz einrichten (Kanal und Adressen)",
               "Für zwei Module: beide auf denselben Kanal, eigene Adresse und Ziel jeweils über Kreuz.", [
                   F(0x11, "07 {KANAL:u8}", 0x51, 1000, "Funkkanal setzen (0–38)"),
                   F(0x11, "10 {QUELLE:u32le}", 0x51, 1000, "Eigene Adresse setzen"),
                   F(0x11, "11 {ZIEL:u32le}", 0x51, 1000, "Standard-Zieladresse setzen"),
                   F(0x00, "", 0x73, 3000, "Neustart, damit die Werte gelten"),
                   F(0x10, "07", 0x50, 1000, "Kontrolle: Kanal"),
               ], [V("KANAL", "Kanal", "21", "0–38"), V("QUELLE", "Eigene Adresse", "1"),
                   V("ZIEL", "Zieladresse", "2")]),
        Recipe("Daten an eine Adresse senden (Unicast)", "Sendet an eine beliebige Adresse und wartet auf das Ende.", [
            F(0x07, "{ZIEL:u32le} {DATEN:hex}", 0x47, 1000, "CMD_UNICAST_DATA_EX_REQ"),
            E(0xC4, 3000, "Übertragung abgeschlossen (TXCOMPLETE_RSP, Status 00 = OK)", True),
        ], [V("ZIEL", "Zieladresse", "2"), V("DATEN", "Text", "Hallo Thyone")]),
        Recipe("Rundsenden (Broadcast)", "An alle Module auf dem Kanal senden.", [
            F(0x06, "{DATEN:hex}", 0x46, 1000, "CMD_BROADCAST_DATA_REQ"),
            E(0xC4, 3000, "Übertragung abgeschlossen", True),
        ], [V("DATEN", "Text", "An alle")]),
        Recipe("Auf Funkdaten warten", "Zeigt eingehende Daten mit Absender und RSSI an.", [
            E(0x84, 60000, "Auf CMD_DATA_IND warten (bis 60 s) – Gegenstelle jetzt senden lassen"),
        ]),
        Recipe("GPIO der Gegenstelle schalten", "Pin 1 eines entfernten Thyone als Ausgang setzen und schalten.", [
            F(0x29, "{ZIEL:u32le} 03 01 02 00", 0x69, 3000, "Pin 1 der Gegenstelle als Ausgang"),
            F(0x2B, "{ZIEL:u32le} 02 01 01", 0x6B, 3000, "Pin 1 auf High"),
            W(1000),
            F(0x2B, "{ZIEL:u32le} 02 01 00", 0x6B, 3000, "Pin 1 auf Low"),
        ], [V("ZIEL", "Adresse der Gegenstelle", "2")]),
        Recipe("Werkseinstellungen", "Alle Einstellungen zurücksetzen.", [
            H("Alle Nutzereinstellungen gehen verloren. Fortfahren?"),
            F(0x1C, "", 0x5C, 3000, "CMD_FACTORYRESET_REQ"),
            E(0x73, 4000, "Neustart-Meldung", True),
        ]),
    ]


# ---------------------------------------------------------------------------
# Sub-GHz: Tarvos / Telesto / Thebe / Themisto
# ---------------------------------------------------------------------------

def _subghz():
    return [
        Recipe("Initialisierung nach dem Start", "Neustart und Funkparameter lesen.", [
            F(0x05, "", 0x45, 3000, "Neustart (CMD_RESET_REQ)"),
            W(500, "Modul hochfahren lassen"),
            F(0x0A, "21", 0x4A, 1000, "Firmware-Version (Speicherstelle 0x21)"),
            F(0x0A, "03", 0x4A, 1000, "Funkkanal"),
            F(0x0A, "04", 0x4A, 1000, "Adressmodus"),
            F(0x0A, "0A", 0x4A, 1000, "Eigene Netz-ID"),
            F(0x0A, "0B", 0x4A, 1000, "Eigene Adresse"),
            F(0x0A, "02", 0x4A, 1000, "Sendeleistung"),
        ]),
        Recipe("Funknetz einrichten", "Kanal, Adressmodus 2 (Netz-ID + Adresse) und eigene Adresse dauerhaft setzen.", [
            F(0x09, "03 {KANAL:u8}", 0x49, 1000, "Standard-Kanal"),
            F(0x09, "04 02", 0x49, 1000, "Adressmodus 2"),
            F(0x09, "0A {NETZ:u8}", 0x49, 1000, "Eigene Netz-ID"),
            F(0x09, "0B {ADRESSE:u8}", 0x49, 1000, "Eigene Adresse"),
            F(0x05, "", 0x45, 3000, "Neustart, damit die Werte gelten"),
        ], [V("KANAL", "Kanal", "106", "z. B. 100–140 bei 868 MHz"), V("NETZ", "Netz-ID", "1"),
            V("ADRESSE", "Eigene Adresse", "1")]),
        Recipe("Daten senden (Standardziel)", "Sendet mit den gespeicherten Zielwerten.", [
            F(0x00, "{DATEN:hex}", 0x40, 3000, "CMD_DATA_REQ – Status 00 = gesendet"),
        ], [V("DATEN", "Text", "Hallo Funk")]),
        Recipe("Daten an Adresse senden (Adressmodus 2)", "Kanal, Netz-ID und Zieladresse direkt angeben.", [
            F(0x01, "{KANAL:u8} {NETZ:u8} {ZIEL:u8} {DATEN:hex}", 0x41, 3000, "CMD_DATAEX_REQ"),
        ], [V("KANAL", "Kanal", "106"), V("NETZ", "Netz-ID", "1"), V("ZIEL", "Zieladresse", "2"),
            V("DATEN", "Text", "Hallo")]),
        Recipe("Auf Funkdaten warten", "Empfangene Telegramme mit RSSI anzeigen.", [
            E(0x81, 60000, "Auf CMD_DATAEX_IND warten (bis 60 s)"),
            F(0x0D, "", 0x4D, 1000, "RSSI des letzten Pakets", True),
        ]),
        Recipe("Werkseinstellungen", "Alle Einstellungen zurücksetzen.", [
            H("Alle Nutzereinstellungen gehen verloren. Fortfahren?"),
            F(0x12, "", 0x52, 3000, "CMD_FACTORY_RESET_REQ"),
        ]),
    ]


def _metis():
    return [
        Recipe("Initialisierung nach dem Start", "Neustart und Kenndaten lesen.", [
            F(0x05, "", 0x85, 3000, "Neustart"),
            W(500),
            F(0x0C, "", 0x8C, 1000, "Firmware-Version"),
            F(0x0B, "", 0x8B, 1000, "Seriennummer"),
        ]),
        Recipe("Betriebsart setzen und Telegramm senden", "wM-Bus-Modus wählen und ein Telegramm senden.", [
            F(0x04, "{MODUS:u8}", 0x84, 1000, "Betriebsart setzen (Modus-Code laut Handbuch)"),
            F(0x00, "{TELEGRAMM}", 0x80, 3000, "Telegramm senden"),
        ], [V("MODUS", "Modus-Code", "1", "z. B. S1/T1/C1 – Code laut Handbuch"),
            V("TELEGRAMM", "Telegramm (HEX)", "44 2D 2C 01 02 03 04 01 07")]),
        Recipe("Auf Zähler-Telegramme warten", "Empfängt wM-Bus-Telegramme.", [
            E(0x03, 120000, "Auf Telegramm warten (bis 2 min)"),
        ]),
    ]


def _metise():
    return [
        Recipe("Initialisierung nach dem Start", "Neustart und Firmware lesen.", [
            F(0x06, "", 0x46, 3000, "Neustart"),
            W(500),
            F(0x05, "81", 0x45, 1000, "Firmware-Version (Option 0x81)"),
            F(0x05, "80", 0x45, 1000, "Werkseinstellungen/Kenndaten (Option 0x80)"),
        ]),
        Recipe("Empfang starten und stoppen", "Empfang einschalten, 60 s mitlesen, ausschalten.", [
            F(0x02, "", 0x42, 1000, "Empfang starten"),
            W(60000, "60 s Telegramme sammeln"),
            F(0x03, "", 0x43, 1000, "Empfang stoppen"),
        ]),
    ]


# ---------------------------------------------------------------------------
# Würth AT-Module
# ---------------------------------------------------------------------------

WLAN_VARS = [V("SSID", "WLAN-Name", "MeinWLAN"), V("PASS", "WLAN-Passwort", "geheim123")]


def _calypso(cordelia=False):
    r = [
        Recipe("Initialisierung nach dem Start", "Verbindung testen und Version lesen.", [
            A("AT+test", desc="Verbindungstest"),
            A("AT+get=general,version", desc="Firmware-Version"),
            A("AT+wlanGet=general,country_code", desc="Ländereinstellung", optional=True),
        ]),
        Recipe("Mit WLAN verbinden", "Station-Modus, verbinden, IP-Adresse lesen. Parameterfolge laut Handbuch prüfen.", [
            A("AT+wlanSetMode=STA", desc="Als Station betreiben"),
            A("AT+wlanConnect={SSID},,WPA_WPA2,{PASS},,,", "OK", 20000, "Verbindung aufbauen"),
            W(5000, "Auf IP-Adresse warten"),
            A("AT+netCfgGet=IPV4_STA_ADDR", desc="Eigene IP-Adresse"),
        ], list(WLAN_VARS)),
        Recipe("Mit WLAN trennen", "", [A("AT+wlanDisconnect", desc="WLAN trennen")]),
    ]
    if not cordelia:
        r.append(Recipe("TCP-Client: Text senden", "Socket öffnen, verbinden, senden, schließen.", [
            A("AT+socket=INET,STREAM,TCP", desc="TCP-Socket anlegen (Antwort enthält die Socket-Nummer, meist 0)"),
            A("AT+connect=0,INET,{PORT},{IP}", "OK", 10000, "Mit Server verbinden"),
            A("AT+send=0,0,{TEXT:len},{TEXT}", desc="Text senden"),
            A("AT+close=0", desc="Socket schließen"),
        ], [V("IP", "Server-IP", "192.168.1.10"), V("PORT", "Port", "8000"), V("TEXT", "Text", "Hallo")]))
    else:
        r.append(Recipe("IoT-Cloud verbinden", "Anmeldung und Verbindung zur IoT-Plattform.", [
            A("AT+iotenrol", "OK", 30000, "Gerät registrieren (nur einmal nötig)"),
            A("AT+iotconnect", "OK", 30000, "Mit Plattform verbinden"),
            A("AT+iotpublish={NACHRICHT}", desc="Nachricht senden"),
        ], [V("NACHRICHT", "Nachricht", "Hallo")]))
    return r


def _daphnis():
    return [
        Recipe("Initialisierung nach dem Start", "Verbindung testen, Version und DevEUI lesen.", [
            A("AT", desc="Verbindungstest"),
            A("AT+VER=?", "OK|+VER", desc="Firmware-Version"),
            A("AT+DEUI=?", "OK|+DEUI", desc="Geräte-EUI (für die Registrierung im Netzwerkserver)"),
        ]),
        Recipe("LoRaWAN beitreten (OTAA)", "Schlüssel setzen und dem Netz beitreten.", [
            A("AT+APPEUI={APPEUI}", desc="JoinEUI/AppEUI setzen"),
            A("AT+APPKEY={APPKEY}", desc="AppKey setzen"),
            A("AT+JOIN=1", "OK", 10000, "Beitritt starten"),
            W(15000, "Auf Join-Accept warten (Ereignis erscheint im Protokoll)"),
        ], [V("APPEUI", "AppEUI / JoinEUI", "0000000000000000"),
            V("APPKEY", "AppKey", "00112233445566778899AABBCCDDEEFF")]),
        Recipe("Daten senden", "Uplink auf einem Port senden.", [
            A("AT+SEND={PORT}:{DATEN}", "OK", 10000, "Uplink (Daten in HEX)"),
        ], [V("PORT", "Port", "1"), V("DATEN", "Daten (HEX)", "48616C6C6F")]),
    ]


def _skoll():
    return [Recipe("Verbindung prüfen", "Grundbefehle der Text-API.", [
        A("/PING", "@R|PING", desc="Verbindungstest"),
        A("/QFV", "@R", desc="Firmware-Version"),
    ])]


# ---------------------------------------------------------------------------
# Fremdmodule
# ---------------------------------------------------------------------------

def _hc12():
    return [
        Recipe("Initialisierung im Befehlsmodus", "Zustand und Einstellungen lesen.", [
            H("SET-Pin des HC-12 auf GND legen (Befehlsmodus, 9600 Baud), dann »OK« klicken."),
            A("AT", "OK", 1000, "Verbindungstest"),
            A("AT+V", "HC-12", 1000, "Firmware-Version"),
            A("AT+RX", "OK", 2000, "Alle Einstellungen auf einmal"),
        ]),
        Recipe("Kanal, Leistung und Modus einstellen", "Beide Module müssen gleich eingestellt sein.", [
            A("AT+C{KANAL:dec3}", "OK+C", 1000, "Kanal setzen"),
            A("AT+P{LEISTUNG}", "OK+P", 1000, "Sendeleistung 1–8"),
            A("AT+FU{MODUS}", "OK+FU", 1000, "Betriebsart FU1–FU4"),
            A("AT+RX", "OK", 2000, "Kontrolle"),
            H("SET-Pin lösen – das Modul arbeitet jetzt transparent mit den neuen Werten."),
        ], [V("KANAL", "Kanal 1–127", "1"), V("LEISTUNG", "Leistung 1–8", "8"), V("MODUS", "Modus 1–4", "3")]),
        Recipe("UART-Baudrate ändern", "Gilt im transparenten Modus nach Lösen von SET.", [
            A("AT+B{BAUD}", "OK+B", 1000, "Baudrate setzen"),
        ], [V("BAUD", "Baudrate", "9600", "1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200")]),
        Recipe("Werkseinstellungen", "", [A("AT+DEFAULT", "OK", 1000, "Zurück auf 9600 Baud, Kanal 1, FU3, 20 dBm")]),
    ]


def _hc05():
    return [
        Recipe("Initialisierung im AT-Modus", "Grunddaten lesen.", [
            H("KEY/EN-Pin beim Einschalten auf High halten (LED blinkt langsam) – AT-Modus mit 38400 Baud."),
            A("AT", desc="Verbindungstest"),
            A("AT+VERSION?", desc="Firmware"),
            A("AT+NAME?", desc="Name", optional=True),
            A("AT+ADDR?", desc="Eigene Adresse"),
            A("AT+ROLE?", desc="Rolle"),
            A("AT+UART?", desc="Baudrate im Datenmodus"),
            A("AT+PSWD?", desc="PIN", optional=True),
        ]),
        Recipe("Als Slave einrichten", "Name, PIN und Baudrate für den Datenbetrieb setzen.", [
            A("AT+ROLE=0", desc="Slave"),
            A("AT+NAME={NAME}", desc="Name"),
            A("AT+PSWD=\"{PIN}\"", "OK", desc="PIN (ältere Firmware: ohne Anführungszeichen)"),
            A("AT+UART={BAUD},0,0", desc="Datenmodus-Baudrate"),
            A("AT+RESET", desc="Neustart – danach im Datenmodus"),
        ], [V("NAME", "Name", "HC-05"), V("PIN", "PIN", "1234"), V("BAUD", "Baudrate", "9600")]),
        Recipe("Als Master mit Slave verbinden", "Sucht Geräte, koppelt, bindet und verbindet.", [
            A("AT+ORGL", desc="Grundeinstellungen", optional=True),
            A("AT+ROLE=1", desc="Master"),
            A("AT+CMODE=0", desc="Nur feste Adresse"),
            A("AT+INIT", "OK|ERROR:(17)", 3000, "SPP starten (ERROR 17 = läuft schon)"),
            A("AT+INQM=0,5,9", desc="Suchparameter"),
            A("AT+INQ", "OK", 15000, "Geräte suchen – Adressen erscheinen als +INQ"),
            A("AT+PAIR={ADRESSE},20", "OK", 25000, "Koppeln"),
            A("AT+BIND={ADRESSE}", desc="Adresse fest binden"),
            A("AT+LINK={ADRESSE}", "OK", 10000, "Verbinden"),
        ], [V("ADRESSE", "Adresse (NAP,UAP,LAP)", "98d3,31,fd1234", "aus +INQ übernehmen, »:« durch »,« ersetzen")]),
    ]


def _hc06():
    return [Recipe("Einrichten", "Name, PIN, Baudrate (nur ohne Verbindung).", [
        A("AT", "OK", 1000, "Test"),
        A("AT+VERSION", "OK", 1000, "Version"),
        A("AT+NAME{NAME}", "OK", 1000, "Name setzen"),
        A("AT+PIN{PIN}", "OK", 1000, "PIN setzen"),
        A("AT+BAUD{BAUDCODE}", "OK", 1000, "Baudrate (4 = 9600)"),
    ], [V("NAME", "Name", "HC-06"), V("PIN", "PIN", "1234"), V("BAUDCODE", "Baud-Code", "4")])]


def _hm10():
    return [
        Recipe("Initialisierung", "Grunddaten lesen.", [
            A("AT", "OK", 1000, "Test"),
            A("AT+VERR?", "OK", 1000, "Version"),
            A("AT+ADDR?", "OK+ADDR", 1000, "Eigene MAC"),
            A("AT+NAME?", "OK+NAME", 1000, "Name"),
            A("AT+ROLE?", "OK+Get", 1000, "Rolle"),
        ]),
        Recipe("Als Central mit Peripheral verbinden", "", [
            A("AT+ROLE1", "OK+Set", 1000, "Central"),
            A("AT+IMME1", "OK+Set", 1000, "Auf Befehle warten"),
            A("AT+RESET", "OK+RESET", 2000, "Neustart"),
            W(1000),
            A("AT+DISC?", "OK+DISCE", 12000, "Geräte suchen"),
            A("AT+CON{MAC12}", "OK+CONN", 10000, "Verbinden"),
        ], [V("MAC12", "MAC (12 Zeichen ohne »:«)", "001122334455")]),
    ]


ESP_COMMON = [
    Recipe("Initialisierung nach dem Start", "Echo aus, Version lesen, Station-Modus.", [
        A("AT", "OK", 1000, "Test"),
        A("ATE0", desc="Echo aus"),
        A("AT+GMR", desc="AT- und SDK-Version"),
        A("AT+CWMODE=1", desc="Station-Modus"),
        A("AT+CWJAP?", "OK|No AP", 2000, "Bereits verbunden?"),
    ]),
    Recipe("Mit WLAN verbinden", "", [
        A("AT+CWMODE=1", desc="Station-Modus"),
        A("AT+CWJAP=\"{SSID}\",\"{PASS}\"", "OK", 20000, "Verbinden (bis 20 s)"),
        A("AT+CIFSR", desc="IP- und MAC-Adresse"),
    ], list(WLAN_VARS)),
    Recipe("TCP-Client: Text senden", "Einfache TCP-Verbindung, Text senden, schließen.", [
        A("AT+CIPMUX=0", desc="Eine Verbindung"),
        A("AT+CIPSTART=\"TCP\",\"{HOST}\",{PORT}", "OK|ALREADY CONNECTED", 10000, "Verbinden"),
        A("AT+CIPSEND={TEXT:len}", ">", 3000, "Länge ankündigen – warten auf »>«"),
        T("{TEXT}", "SEND OK", 5000, "Text senden"),
        A("AT+CIPCLOSE", "OK|CLOSED", 3000, "Schließen", optional=True),
    ], [V("HOST", "Server", "192.168.1.10"), V("PORT", "Port", "8000"), V("TEXT", "Text", "Hallo vom ESP")]),
    Recipe("HTTP-Abruf über TCP", "Webseite per HTTP-GET laden – Antwort erscheint als +IPD.", [
        A("AT+CIPMUX=0"),
        A("AT+CIPSTART=\"TCP\",\"{HOST}\",80", "OK|ALREADY CONNECTED", 10000, "Mit Webserver verbinden"),
        A("AT+CIPSEND={ANFRAGE:len}", ">", 3000, "Länge ankündigen"),
        T("{ANFRAGE}", "SEND OK", 5000, "HTTP-Anfrage senden"),
        E("+IPD", 10000, "Antwort des Servers"),
        A("AT+CIPCLOSE", "OK|CLOSED", 3000, optional=True),
    ], [V("HOST", "Server", "example.com"),
        V("ANFRAGE", "HTTP-Anfrage", "GET / HTTP/1.1\\r\\nHost: example.com\\r\\nConnection: close\\r\\n\\r\\n",
          "\\r\\n = Zeilenende")]),
    Recipe("TCP-Server starten", "ESP nimmt Verbindungen auf einem Port an.", [
        A("AT+CIPMUX=1", desc="Mehrere Verbindungen"),
        A("AT+CIPSERVER=1,{PORT}", desc="Server starten"),
        A("AT+CIFSR", desc="IP-Adresse – damit z. B. per Telnet verbinden"),
        E("CONNECT", 60000, "Auf Verbindung warten"),
    ], [V("PORT", "Port", "333")]),
    Recipe("Eigenen Access Point öffnen", "", [
        A("AT+CWMODE=2", desc="Access-Point-Modus"),
        A("AT+CWSAP=\"{SSID}\",\"{PASS}\",5,3", desc="Name, Passwort (min. 8 Zeichen), Kanal 5, WPA2"),
        A("AT+CIFSR", desc="IP des Access Points (meist 192.168.4.1)"),
    ], [V("SSID", "AP-Name", "ESP-AP"), V("PASS", "AP-Passwort", "12345678")]),
    Recipe("Uhrzeit aus dem Internet", "Zeitserver abfragen (WLAN muss verbunden sein).", [
        A("AT+CIPSNTPCFG=1,1,\"pool.ntp.org\"", desc="Zeitserver, Zeitzone +1"),
        W(3000, "Synchronisieren lassen"),
        A("AT+CIPSNTPTIME?", desc="Uhrzeit"),
    ]),
]


def _esp32():
    return list(ESP_COMMON) + [
        Recipe("MQTT: verbinden, senden, abonnieren", "", [
            A("AT+MQTTUSERCFG=0,1,\"{CLIENT}\",\"\",\"\",0,0,\"\"", desc="Client einrichten"),
            A("AT+MQTTCONN=0,\"{BROKER}\",{PORT},1", "OK", 10000, "Mit Broker verbinden"),
            A("AT+MQTTSUB=0,\"{TOPIC}\",0", desc="Topic abonnieren"),
            A("AT+MQTTPUB=0,\"{TOPIC}\",\"{TEXT}\",0,0", desc="Nachricht senden"),
            E("+MQTTSUBRECV", 5000, "Eigene Nachricht kommt über das Abo zurück", True),
            A("AT+MQTTCLEAN=0", desc="Trennen"),
        ], [V("BROKER", "Broker", "192.168.1.10"), V("PORT", "Port", "1883"), V("CLIENT", "Client-ID", "esp32-test"),
            V("TOPIC", "Topic", "test/esp32"), V("TEXT", "Nachricht", "Hallo")]),
        Recipe("Bluetooth LE: sichtbar werden", "Als BLE-Peripheral mit Namen werben.", [
            A("AT+BLEINIT=2", desc="BLE-Server"),
            A("AT+BLENAME=\"{NAME}\"", desc="Name"),
            A("AT+BLEADVDATAEX=\"{NAME}\",\"A002\",\"0102030405\",1", desc="Werbedaten"),
            A("AT+BLEADVSTART", desc="Werbung starten – jetzt im Scan sichtbar"),
        ], [V("NAME", "BLE-Name", "ESP32-AT")]),
    ]


def _stephano():
    return list(ESP_COMMON) + [
        Recipe("Bluetooth LE: sichtbar werden", "", [
            A("AT+BLEINIT=2", desc="BLE-Server"),
            A("AT+BLENAME=\"{NAME}\"", desc="Name"),
            A("AT+BLEADVSTART", desc="Werbung starten"),
        ], [V("NAME", "BLE-Name", "Stephano")]),
    ]


# ---------------------------------------------------------------------------
# Mobilfunk (3GPP-Standard + herstellerspezifisch)
# ---------------------------------------------------------------------------

def _cell_common():
    return [
        Recipe("Initialisierung nach dem Start",
               "Grundeinrichtung nach dem Einschalten: Echo aus, Klartextfehler, SIM und Netz prüfen.", [
                   A("AT", "OK", 2000, "Test – bei automatischer Baudrate ggf. zweimal nötig"),
                   A("ATE0", desc="Echo aus"),
                   A("AT+CMEE=2", desc="Fehler im Klartext"),
                   A("ATI", desc="Hersteller / Modell / Firmware"),
                   A("AT+CGSN", desc="IMEI", optional=True),
                   A("AT+CPIN?", "READY", 5000, "SIM-Status – bei »SIM PIN« den Ablauf »PIN eingeben« nutzen"),
                   A("AT+CCID", "OK", 2000, "SIM-Kartennummer", optional=True),
                   A("AT+CSQ", desc="Signal 0–31 (ab 10 brauchbar)"),
                   A("AT+CREG?", desc="GSM-Registrierung: ,1 = Heimnetz, ,5 = Roaming", optional=True),
                   A("AT+CEREG?", desc="LTE-Registrierung", optional=True),
                   A("AT+COPS?", desc="Netzbetreiber"),
               ]),
        Recipe("PIN eingeben", "Entsperrt die SIM-Karte. Dreimal falsch = PUK nötig!", [
            A("AT+CPIN?", "SIM PIN|READY", 3000, "Prüfen, ob eine PIN verlangt wird"),
            A("AT+CPIN={PIN}", "OK", 5000, "PIN senden"),
            W(5000, "Netzsuche"),
            A("AT+CPIN?", "READY", 3000, "Kontrolle"),
            A("AT+CREG?", desc="Registrierung", optional=True),
        ], [V("PIN", "SIM-PIN", "1234")]),
        Recipe("Netz und Signal prüfen", "Schneller Gesundheitscheck der Verbindung.", [
            A("AT+CSQ", desc="Signalqualität"),
            A("AT+COPS?", desc="Betreiber und Technik"),
            A("AT+CREG?", optional=True, desc="GSM"),
            A("AT+CGREG?", optional=True, desc="Paketdienst"),
            A("AT+CEREG?", optional=True, desc="LTE"),
            A("AT+CGATT?", optional=True, desc="Paketdienst angemeldet"),
        ]),
        Recipe("SMS senden", "Textmodus, Empfänger, Text, mit Strg+Z abschließen.", [
            A("AT+CMGF=1", desc="Textmodus"),
            A("AT+CSCS=\"GSM\"", desc="Zeichensatz"),
            A("AT+CMGS=\"{NUMMER}\"", ">", 5000, "Empfänger – Modem antwortet mit »>«"),
            T("{TEXT}", None, 1000, "SMS-Text eingeben"),
            X("1A", "+CMGS", 60000, "Strg+Z schließt ab – Erfolg: +CMGS: <Nr>"),
        ], [V("NUMMER", "Rufnummer (international)", "+491701234567"), V("TEXT", "Text", "Test vom Funkmodul-Studio")]),
        Recipe("SMS lesen", "Alle gespeicherten SMS auflisten.", [
            A("AT+CMGF=1", desc="Textmodus"),
            A("AT+CPMS?", desc="Speicherbelegung"),
            A("AT+CMGL=\"ALL\"", "OK", 10000, "Alle SMS"),
        ]),
        Recipe("Auf neue SMS warten", "Neue SMS werden sofort ausgegeben.", [
            A("AT+CMGF=1", desc="Textmodus"),
            A("AT+CNMI=2,2,0,0,0", desc="Direkte Ausgabe einschalten"),
            E("+CMT", 120000, "Auf SMS warten (2 min) – jetzt SMS an die Karte schicken"),
        ]),
        Recipe("Anruf aufbauen", "Sprachanruf starten, nach Gesprächsdauer auflegen.", [
            A("AT+CLCC", "OK", 2000, "Laufende Gespräche", optional=True),
            A("ATD{NUMMER};", "OK", 20000, "Wählen – Semikolon = Sprachanruf"),
            W(20000, "Gespräch (20 s)"),
            A("ATH", "OK", 3000, "Auflegen"),
        ], [V("NUMMER", "Rufnummer", "+491701234567")]),
        Recipe("Anruf annehmen", "Auf Klingeln warten, annehmen, nach 20 s auflegen.", [
            A("AT+CLIP=1", desc="Anrufernummer anzeigen"),
            E("RING", 120000, "Auf Anruf warten (2 min) – jetzt anrufen"),
            A("ATA", "OK", 5000, "Annehmen"),
            W(20000, "Gespräch"),
            A("ATH", desc="Auflegen"),
        ]),
        Recipe("Guthaben / USSD-Code", "z. B. *100# bei vielen Prepaid-Anbietern.", [
            A("AT+CUSD=1,\"{CODE}\",15", "+CUSD", 20000, "Code senden – Antwort als +CUSD"),
        ], [V("CODE", "USSD-Code", "*100#")]),
        Recipe("APN einstellen", "Zugangspunkt für mobile Daten setzen.", [
            A("AT+CGDCONT=1,\"IP\",\"{APN}\"", desc="Kontext 1 mit APN"),
            A("AT+CGDCONT?", desc="Kontrolle"),
            A("AT+CGATT=1", "OK", 30000, "Paketdienst anmelden", optional=True),
        ], [V("APN", "APN", "internet", "laut Mobilfunkanbieter")]),
    ]


def _sim800():
    return _cell_common() + [
        Recipe("HTTP-GET über GPRS", "Webseite abrufen (SIM800 HTTP-Dienst).", [
            A("AT+SAPBR=3,1,\"Contype\",\"GPRS\"", desc="Verbindungstyp"),
            A("AT+SAPBR=3,1,\"APN\",\"{APN}\"", desc="APN"),
            A("AT+SAPBR=1,1", "OK", 30000, "Datenverbindung öffnen", optional=True),
            A("AT+SAPBR=2,1", desc="IP-Adresse anzeigen"),
            A("AT+HTTPINIT", desc="HTTP starten"),
            A("AT+HTTPPARA=\"CID\",1", desc="Verbindung 1 nutzen"),
            A("AT+HTTPPARA=\"URL\",\"{URL}\"", desc="Adresse"),
            A("AT+HTTPACTION=0", "+HTTPACTION", 30000, "GET – Antwort: Methode, Statuscode, Länge"),
            A("AT+HTTPREAD", "OK", 10000, "Inhalt lesen"),
            A("AT+HTTPTERM", desc="HTTP beenden"),
            A("AT+SAPBR=0,1", "OK", 10000, "Datenverbindung schließen", optional=True),
        ], [V("APN", "APN", "internet"), V("URL", "Adresse", "http://example.com")]),
        Recipe("TCP-Verbindung und Text senden", "", [
            A("AT+CIPSHUT", "SHUT OK", 10000, "Alte Verbindungen beenden"),
            A("AT+CSTT=\"{APN}\"", desc="APN"),
            A("AT+CIICR", "OK", 60000, "Datenverbindung aufbauen (bis 60 s)"),
            A("AT+CIFSR", ".", 3000, "Eigene IP-Adresse"),
            A("AT+CIPSTART=\"TCP\",\"{HOST}\",\"{PORT}\"", "CONNECT OK|ALREADY CONNECT", 30000, "Verbinden"),
            A("AT+CIPSEND", ">", 5000, "Senden starten"),
            T("{TEXT}", None, 1000, "Text"),
            X("1A", "SEND OK", 20000, "Strg+Z schickt ab"),
            A("AT+CIPCLOSE", "CLOSE OK", 5000, "Schließen", optional=True),
        ], [V("APN", "APN", "internet"), V("HOST", "Server", "example.com"), V("PORT", "Port", "80"),
            V("TEXT", "Text", "Hallo")]),
        Recipe("Versorgung und Uhrzeit", "", [
            A("AT+CBC", desc="Spannung in mV – unter 3500 mV drohen Abstürze beim Senden"),
            A("AT+CCLK?", desc="Uhrzeit"),
        ]),
    ]


def _sim7600():
    return _cell_common() + [
        Recipe("Zellinformation (LTE)", "", [
            A("AT+CPSI?", desc="Technik, Band, Zelle, Signal"),
            A("AT+CNMP?", desc="Bevorzugte Technik"),
        ]),
        Recipe("TCP-Verbindung und Text senden", "", [
            A("AT+CGDCONT=1,\"IP\",\"{APN}\"", desc="APN"),
            A("AT+NETOPEN", "+NETOPEN: 0|already opened", 30000, "IP-Dienst öffnen"),
            A("AT+IPADDR", desc="IP-Adresse"),
            A("AT+CIPOPEN=0,\"TCP\",\"{HOST}\",{PORT}", "+CIPOPEN: 0,0", 30000, "Verbinden"),
            A("AT+CIPSEND=0,{TEXT:len}", ">", 5000, "Länge ankündigen"),
            T("{TEXT}", "+CIPSEND", 10000, "Text senden"),
            A("AT+CIPCLOSE=0", "OK", 5000, "Schließen", optional=True),
            A("AT+NETCLOSE", "OK", 10000, "IP-Dienst schließen", optional=True),
        ], [V("APN", "APN", "internet"), V("HOST", "Server", "example.com"), V("PORT", "Port", "80"),
            V("TEXT", "Text", "Hallo")]),
        Recipe("HTTP-GET", "", [
            A("AT+CGDCONT=1,\"IP\",\"{APN}\""),
            A("AT+HTTPINIT", desc="HTTP starten"),
            A("AT+HTTPPARA=\"URL\",\"{URL}\"", desc="Adresse"),
            A("AT+HTTPACTION=0", "+HTTPACTION", 30000, "GET"),
            A("AT+HTTPREAD=0,500", "OK", 10000, "500 Bytes lesen"),
            A("AT+HTTPTERM", desc="Beenden"),
        ], [V("APN", "APN", "internet"), V("URL", "Adresse", "http://example.com")]),
        Recipe("GPS-Position", "Antenne nötig, erster Fix kann 30 s bis mehrere Minuten dauern.", [
            A("AT+CGPS=1", "OK", 3000, "GPS ein", optional=True),
            W(30000, "Satelliten suchen"),
            A("AT+CGPSINFO", desc="Position – leere Felder = noch kein Fix"),
            A("AT+CGPS=0", "OK", 3000, "GPS aus", optional=True),
        ]),
    ]


def _quectel_lte():
    return _cell_common() + [
        Recipe("Zellinformation", "", [
            A("AT+QNWINFO", desc="Technik, Betreiber, Band"),
            A("AT+QCSQ", desc="Signalwerte"),
            A("AT+QENG=\"servingcell\"", desc="Zelldetails"),
        ]),
        Recipe("Datenverbindung aufbauen", "", [
            A("AT+QICSGP=1,1,\"{APN}\",\"\",\"\",1", desc="Kontext 1 mit APN"),
            A("AT+QIACT=1", "OK", 150000, "Aktivieren (bis 150 s)"),
            A("AT+QIACT?", desc="IP-Adresse"),
            A("AT+QPING=1,\"8.8.8.8\"", "+QPING", 20000, "Ping-Test", optional=True),
        ], [V("APN", "APN", "internet")]),
        Recipe("TCP-Verbindung und Text senden", "Datenverbindung muss aktiv sein.", [
            A("AT+QIOPEN=1,0,\"TCP\",\"{HOST}\",{PORT},0,0", "+QIOPEN: 0,0", 60000, "Verbinden"),
            A("AT+QISEND=0,{TEXT:len}", ">", 5000, "Länge ankündigen"),
            T("{TEXT}", "SEND OK", 10000, "Text senden"),
            A("AT+QICLOSE=0", "OK", 10000, "Schließen"),
        ], [V("HOST", "Server", "example.com"), V("PORT", "Port", "80"), V("TEXT", "Text", "Hallo")]),
        Recipe("HTTP-GET", "Datenverbindung muss aktiv sein.", [
            A("AT+QHTTPCFG=\"contextid\",1", desc="Kontext 1"),
            A("AT+QHTTPURL={URL:len},80", "CONNECT", 5000, "URL-Länge ankündigen"),
            T("{URL}", "OK", 5000, "URL senden"),
            A("AT+QHTTPGET=80", "+QHTTPGET", 80000, "GET – Antwort: Fehlercode, Statuscode, Länge"),
            A("AT+QHTTPREAD=80", "+QHTTPREAD", 80000, "Inhalt lesen"),
        ], [V("URL", "Adresse", "http://example.com")]),
        Recipe("MQTT: verbinden und senden", "Datenverbindung muss aktiv sein.", [
            A("AT+QMTOPEN=0,\"{BROKER}\",{PORT}", "+QMTOPEN: 0,0", 75000, "Netzwerkverbindung zum Broker"),
            A("AT+QMTCONN=0,\"{CLIENT}\"", "+QMTCONN: 0,0,0", 10000, "Anmelden"),
            A("AT+QMTPUBEX=0,0,0,0,\"{TOPIC}\",{TEXT:len}", ">", 5000, "Veröffentlichen ankündigen"),
            T("{TEXT}", "+QMTPUBEX", 10000, "Nachricht"),
            A("AT+QMTDISC=0", "OK", 5000, "Trennen", optional=True),
        ], [V("BROKER", "Broker", "broker.example.com"), V("PORT", "Port", "1883"),
            V("CLIENT", "Client-ID", "quectel01"), V("TOPIC", "Topic", "test/modem"), V("TEXT", "Text", "Hallo")]),
        Recipe("GNSS-Position", "", [
            A("AT+QGPS=1", "OK", 3000, "GNSS ein", optional=True),
            W(30000, "Satelliten suchen"),
            A("AT+QGPSLOC=2", "+QGPSLOC|ERROR", 3000, "Position (ERROR 516 = noch kein Fix)"),
            A("AT+QGPSEND", "OK", 3000, "GNSS aus", optional=True),
        ]),
    ]


def _quectel_5g():
    return _cell_common() + [
        Recipe("5G-Status anzeigen", "Technik (NR5G-SA / NSA / LTE), Bänder, Signal je Antenne.", [
            A("AT+QENG=\"servingcell\"", desc="Aktuelle Zelle mit Technik und Signal"),
            A("AT+QNWINFO", desc="Technik und Band"),
            A("AT+QCAINFO", desc="Trägerbündelung"),
            A("AT+QRSRP", desc="Empfangsleistung je Antenne"),
            A("AT+QTEMP", desc="Temperaturen"),
        ]),
        Recipe("Nur 5G erzwingen", "Für Tests – danach mit »Alle Techniken erlauben« zurückstellen.", [
            A("AT+QNWPREFCFG=\"mode_pref\",NR5G", desc="Nur 5G"),
            W(10000, "Neue Netzsuche"),
            A("AT+QENG=\"servingcell\"", desc="Kontrolle"),
        ]),
        Recipe("Alle Techniken erlauben", "", [
            A("AT+QNWPREFCFG=\"mode_pref\",AUTO", desc="Automatisch"),
            A("AT+QNWPREFCFG=\"mode_pref\"", desc="Kontrolle"),
        ]),
        Recipe("Zellen in der Umgebung scannen", "Dauert bis zu 3 Minuten.", [
            A("AT+QSCAN=3,1", "OK", 180000, "LTE- und 5G-Zellen suchen"),
        ]),
        Recipe("Datenverbindung über USB einrichten", "Der PC nutzt das Modem als Netzwerkkarte.", [
            A("AT+CGDCONT=1,\"IPV4V6\",\"{APN}\"", desc="APN"),
            A("AT+QCFG=\"usbnet\"", desc="USB-Netzwerkmodus abfragen (1 = ECM, 2 = MBIM, 3 = RNDIS)"),
            H("Bei Bedarf USB-Modus mit AT+QCFG=\"usbnet\",<Modus> ändern und das Modem neu starten."),
        ], [V("APN", "APN", "internet")]),
    ]


def _ublox():
    return _cell_common() + [
        Recipe("Netzbetreiber-Profil einrichten", "Wichtig bei SARA-R4/R5 vor dem ersten Betrieb.", [
            A("AT+CFUN=0", "OK", 10000, "Funk aus"),
            A("AT+UMNOPROF={PROFIL}", desc="Profil setzen"),
            A("AT+CFUN=15", "OK", 10000, "Neustart"),
            W(10000),
            A("AT", "OK", 2000),
            A("AT+CGDCONT=1,\"IP\",\"{APN}\"", desc="APN"),
            A("AT+COPS=0", "OK", 60000, "Netz automatisch"),
            A("AT+CEREG?", desc="Registrierung"),
        ], [V("PROFIL", "MNO-Profil", "100", "100 = Europa, 90 = global"), V("APN", "APN", "internet")]),
        Recipe("TCP-Socket: Text senden", "", [
            A("AT+USOCR=6", "+USOCR", 3000, "TCP-Socket anlegen (Antwort: Nummer, meist 0)"),
            A("AT+USOCO=0,\"{HOST}\",{PORT}", "OK", 30000, "Verbinden"),
            A("AT+USOWR=0,{TEXT:len},\"{TEXT}\"", "+USOWR", 10000, "Senden"),
            A("AT+USORD=0,100", "OK", 5000, "Antwort lesen", optional=True),
            A("AT+USOCL=0", "OK", 5000, "Schließen"),
        ], [V("HOST", "Server", "example.com"), V("PORT", "Port", "80"), V("TEXT", "Text", "Hallo")]),
    ]


def _nrf91():
    return _cell_common() + [
        Recipe("LTE-M/NB-IoT einrichten und verbinden", "", [
            A("AT+CFUN=0", desc="Funk aus"),
            A("AT%XSYSTEMMODE=1,1,1,0", desc="LTE-M, NB-IoT und GNSS erlauben"),
            A("AT+CGDCONT=0,\"IP\",\"{APN}\"", desc="APN (Kontext 0)"),
            A("AT+CFUN=1", desc="Funk ein"),
            W(20000, "Netzsuche"),
            A("AT+CEREG?", desc="Registrierung"),
            A("AT%XMONITOR", desc="Status"),
        ], [V("APN", "APN", "internet")]),
        Recipe("TCP-Socket: Text senden", "Nur mit Serial-LTE-Modem-Firmware.", [
            A("AT#XSOCKET=1,1,0", "#XSOCKET", 3000, "TCP-Socket öffnen"),
            A("AT#XCONNECT=\"{HOST}\",{PORT}", "#XCONNECT", 30000, "Verbinden"),
            A("AT#XSEND=\"{TEXT}\"", "#XSEND", 10000, "Senden"),
            A("AT#XRECV=5", "OK", 8000, "Antwort lesen", optional=True),
            A("AT#XSOCKET=0", "OK", 3000, "Schließen"),
        ], [V("HOST", "Server", "example.com"), V("PORT", "Port", "80"), V("TEXT", "Text", "Hallo")]),
        Recipe("GNSS-Position", "", [
            A("AT#XGPS=1,0,0,0", "OK", 3000, "GNSS starten"),
            E("#XGPS:", 180000, "Auf Position warten (bis 3 min)"),
            A("AT#XGPS=0", "OK", 3000, "GNSS stoppen"),
        ]),
    ]


def _adrastea():
    return _cell_common() + [
        Recipe("GNSS-Position", "", [
            A("AT%IGNSSACT=1", "OK", 3000, "GNSS ein"),
            W(30000, "Satelliten suchen"),
            A("AT%IGNSSINFO=\"FIX\"", desc="Position"),
            A("AT%IGNSSACT=0", "OK", 3000, "GNSS aus"),
        ]),
        Recipe("Socket: Text senden", "Parameter laut Handbuch prüfen.", [
            A("AT%SOCKETCMD=\"ALLOCATE\",1,\"TCP\",\"OPEN\",\"{HOST}\",{PORT}", "OK", 10000, "Socket anlegen"),
            A("AT%SOCKETCMD=\"ACTIVATE\",1", "OK", 30000, "Verbinden"),
            A("AT%SOCKETDATA=\"SEND\",1,{TEXT:len},\"{TEXT:hex}\"", "OK", 10000, "Daten (HEX) senden"),
            A("AT%SOCKETCMD=\"DELETE\",1", "OK", 5000, "Schließen"),
        ], [V("HOST", "Server", "example.com"), V("PORT", "Port", "80"), V("TEXT", "Text", "Hallo")]),
    ]


def _generic():
    return [Recipe("Verbindung prüfen", "Sendet einen Text und wartet auf beliebige Antwort.", [
        T("{TEXT}\\r\\n", None, 1000, "Text senden"),
        W(2000, "Antwort abwarten"),
    ], [V("TEXT", "Text", "AT")])]


RECIPES: dict[str, list[Recipe]] = {
    "proteus2": _proteus("II"),
    "proteus3": _proteus("III"),
    "proteuse": _proteus("e"),
    "proteus4": _proteus4(),
    "thyone1": _thyone(),
    "thyonee": _thyone(),
    "tarvos3": _subghz(),
    "tarvose": _subghz(),
    "telesto3": _subghz(),
    "thebe2": _subghz(),
    "themisto1": _subghz(),
    "metis": _metis(),
    "metise": _metise(),
    "calypso": _calypso(),
    "cordelia": _calypso(cordelia=True),
    "stephano": _stephano(),
    "daphnis": _daphnis(),
    "adrastea": _adrastea(),
    "skoll": _skoll(),
    "hc12": _hc12(),
    "hc05": _hc05(),
    "hc06": _hc06(),
    "hm10": _hm10(),
    "esp8266": list(ESP_COMMON),
    "esp32": _esp32(),
    "sim800": _sim800(),
    "sim7600": _sim7600(),
    "quectel_lte": _quectel_lte(),
    "quectel_5g": _quectel_5g(),
    "ublox_sara": _ublox(),
    "nrf91": _nrf91(),
    "modem_generic": _cell_common(),
    "generic": _generic(),
}
