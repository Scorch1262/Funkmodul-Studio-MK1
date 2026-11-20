"""Modultabellen für die UART-Befehlsschnittstelle (smartCommander-Funktionen).

Enthält je Modul: Frame-Format, Standard-Baudrate, Befehle mit Parametern und
Nutzereinstellungen. Die Codes stammen aus den öffentlichen Handbüchern der
Module; Aufbau und Texte dieser Tabellen sind eigenständig.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Grundtypen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Param:
    name: str
    kind: str = "hex"          # u8 | i8 | u16 | u32 | hex | ascii | mac | choice | data
    default: str = ""
    choices: tuple = ()        # ((wert, text), ...) für kind == "choice"
    length: int = 0            # feste Länge für hex/ascii/mac (0 = beliebig)
    hint: str = ""


@dataclass(frozen=True)
class Command:
    name: str
    code: int                  # REQ-Code (bei AT: 0)
    params: tuple = ()
    desc: str = ""
    group: str = "Allgemein"
    at: str = ""               # Vorlage bei AT-Modulen
    danger: bool = False       # z. B. Werkseinstellungen


@dataclass(frozen=True)
class Setting:
    sid: int
    name: str
    kind: str = "hex"          # u8 | i8 | u16 | u32 | hex | ascii | mac
    ro: bool = False
    desc: str = ""
    length: int = 0            # Metis: Länge des Speicherbereichs


@dataclass
class ModuleDef:
    key: str
    label: str
    family: str                # Funktechnik, nur Anzeige
    proto: str                 # cmd16 | cmd8 | metis | at | text
    baud: int = 115200
    commands: list = field(default_factory=list)
    settings: list = field(default_factory=list)
    names: dict = field(default_factory=dict)    # Basis-Code -> Name für die Log-Auswertung
    full_names: dict = field(default_factory=dict)  # vollständiger Code -> Name (Sondermeldungen)
    get_code: int | None = None
    set_code: int | None = None
    settings_style: str = "id"  # id: [id] / [id, wert]   metis: [pos, len] / [pos, len, wert]
    note: str = ""
    vendor: str = "Würth Elektronik"
    eol: str = "\r\n"          # Zeilenende bei AT-/Text-Befehlen


TYPE_SUFFIX = {0: "REQ", 1: "CNF", 2: "IND", 3: "RSP"}

STATUS_TEXT = {
    0x00: "OK",
    0x01: "Fehler",
    0x02: "Ungültiger Befehl / Parameter",
    0x03: "Nicht unterstützt",
    0x04: "Ungültige Option",
    0x05: "Option nicht unterstützt",
    0x06: "Nicht erlaubt",
    0xFF: "Unbekannt / beschäftigt",
}


def u8(name, default="0", hint=""):
    return Param(name, "u8", default, hint=hint)


def data(name="Nutzdaten", default="48 61 6C 6C 6F"):
    return Param(name, "data", default)


PHY = Param("PHY", "choice", "1", (("1", "1 Mbit"), ("2", "2 Mbit"), ("4", "LE Coded (Long Range)")))


# ---------------------------------------------------------------------------
# Bluetooth LE: Proteus-II / -III / -e / -IV
# ---------------------------------------------------------------------------

def _proteus_settings(variant: str) -> list[Setting]:
    s = [
        Setting(0x02, "RF_DeviceName", "ascii", desc="Gerätename in der Werbung"),
        Setting(0x03, "FS_MAC", "hex", True, "Eindeutige Geräte-MAC"),
        Setting(0x04, "FS_BTMAC", "hex", True, "Bluetooth-MAC"),
        Setting(0x07, "RF_AdvertisingTimeout", "u16", desc="Werbe-Timeout in s (0 = unbegrenzt)"),
        Setting(0x0B, "UART_ConfigIndex", "u8", desc="Baudraten-/UART-Index"),
        Setting(0x0C, "RF_SecFlags", "u8", desc="Sicherheitsmodus"),
        Setting(0x0F, "FS_DeviceInfo", "hex", True, "Firmware, Modul-ID"),
        Setting(0x10, "FS_SerialNumber", "hex", True, "Seriennummer"),
        Setting(0x11, "RF_TXPower", "i8", desc="Sendeleistung in dBm"),
        Setting(0x12, "RF_StaticPasskey", "ascii", desc="Statischer Passkey (6 Ziffern)"),
        Setting(0x19, "RF_Appearance", "u16", desc="GAP-Appearance"),
        Setting(0x1A, "RF_SPPBaseUUID", "hex", desc="Basis-UUID des SPP-Service (16 Byte)"),
        Setting(0x1C, "RF_CfgFlags", "u16", desc="Konfigurations-Flags"),
    ]
    if variant in ("II", "III"):
        s += [
            Setting(0x08, "RF_ConnectionTiming", "u8", desc="Verbindungsintervall-Index"),
            Setting(0x09, "RF_ScanTiming", "u8", desc="Scan-Timing-Index"),
            Setting(0x0A, "RF_ScanFactor", "u8", desc="Scan-Faktor"),
            Setting(0x0D, "RF_ScanFlags", "u8", desc="Scan-Flags"),
            Setting(0x0E, "RF_BeaconFlags", "u8", desc="Beacon-Flags"),
            Setting(0x13, "DIS_Flags", "u8", desc="Device Information Service aktiv"),
            Setting(0x14, "DIS_ManufacturerName", "ascii"),
            Setting(0x15, "DIS_ModelNumber", "ascii"),
            Setting(0x16, "DIS_SerialNumber", "ascii"),
            Setting(0x17, "DIS_HWVersion", "ascii"),
            Setting(0x18, "DIS_SWVersion", "ascii"),
            Setting(0x1D, "RF_AdvertisingFlags", "u8"),
            Setting(0x2C, "RF_SecFlagsPerOnly", "u8", desc="Sicherheit im Peripheral-only-Modus"),
        ]
    if variant == "II":
        s.append(Setting(0x1B, "UART_Flags", "u8"))
    if variant in ("III", "e"):
        s += [
            Setting(0x05, "UART_TransparentETX", "hex", desc="Endezeichen im transparenten Modus"),
            Setting(0x06, "UART_TransparentETXCfg", "u16"),
            Setting(0x21, "RF_SPPRXUUID", "hex"),
            Setting(0x22, "RF_SPPTXUUID", "hex"),
            Setting(0x24, "UART_TransparentTimeout", "u8"),
            Setting(0x25, "UART_TransparentMaxPayload", "u16"),
        ]
    if variant == "III":
        s.append(Setting(0x23, "RF_CompanyID", "u16"))
    if variant == "e":
        s += [
            Setting(0x08, "RF_ConnectionInterval", "hex"),
            Setting(0x09, "RF_AdvertisingInterval", "hex"),
            Setting(0x0D, "RF_AdvertisingData", "hex"),
            Setting(0x0E, "RF_ScanResponseData", "hex"),
        ]
    return sorted(s, key=lambda x: x.sid)


def _proteus4_settings() -> list[Setting]:
    return [
        Setting(0x01, "FS_FWVersion", "hex", True),
        Setting(0x02, "RF_DeviceName", "ascii"),
        Setting(0x03, "FS_MAC", "hex", True),
        Setting(0x04, "FS_BTMAC", "hex", True),
        Setting(0x05, "CFG_Flags", "hex"),
        Setting(0x06, "UART_TransparentETXCfg", "hex"),
        Setting(0x07, "RF_AdvertisingInterval", "hex"),
        Setting(0x08, "RF_ConnectionInterval", "hex"),
        Setting(0x09, "UART_ReceiveTransparentETX", "hex"),
        Setting(0x0A, "UART_TransmitTransparentETX", "hex"),
        Setting(0x0B, "UART_ConfigIndex", "u8"),
        Setting(0x0C, "RF_SecFlags", "u8"),
        Setting(0x0D, "RF_AdvertisingData", "hex"),
        Setting(0x0E, "RF_ScanResponseData", "hex"),
        Setting(0x0F, "FS_DeviceInfo", "hex", True),
        Setting(0x10, "FS_SerialNumber", "hex", True),
        Setting(0x11, "RF_TXPower", "i8"),
        Setting(0x12, "RF_StaticPasskey", "ascii"),
        Setting(0x19, "RF_Appearance", "u16"),
        Setting(0x1E, "RF_MaxPeripheralConnections", "u8"),
        Setting(0x20, "RF_SPPServiceUUID", "hex"),
        Setting(0x21, "RF_SPPRXUUID", "hex"),
        Setting(0x22, "RF_SPPTXUUID", "hex"),
    ]


def _ble_gpio_cmds(local_cfg=0x25, local_rcfg=0x2B, local_w=0x26, local_r=0x27,
                   rem_cfg=0x28, rem_rcfg=0x2C, rem_w=0x29, rem_r=0x2A) -> list[Command]:
    g = "GPIO"
    blk = "Blöcke [Länge, Pin, Funktion, Wert…], z. B. 03 01 02 01 = B1 Ausgang High"
    return [
        Command("GPIO_Local_WriteConfig", local_cfg, (Param("Konfiguration", "hex", "03 01 02 01", hint=blk),), "Lokale Pins konfigurieren", g),
        Command("GPIO_Local_ReadConfig", local_rcfg, (), "Konfiguration der lokalen Pins lesen", g),
        Command("GPIO_Local_Write", local_w, (Param("Werte", "hex", "02 01 01", hint="Blöcke [Länge, Pin, Wert]"),), "Lokale Ausgänge setzen", g),
        Command("GPIO_Local_Read", local_r, (Param("Pins", "hex", "02 01 02", hint="[Anzahl, Pin, Pin…]"),), "Lokale Pins lesen", g),
        Command("GPIO_Remote_WriteConfig", rem_cfg, (Param("Konfiguration", "hex", "03 01 02 01", hint=blk),), "Pins der Gegenstelle konfigurieren", g),
        Command("GPIO_Remote_ReadConfig", rem_rcfg, (), "Konfiguration der Gegenstelle lesen", g),
        Command("GPIO_Remote_Write", rem_w, (Param("Werte", "hex", "02 01 01", hint="Blöcke [Länge, Pin, Wert]"),), "Ausgänge der Gegenstelle setzen", g),
        Command("GPIO_Remote_Read", rem_r, (Param("Pins", "hex", "02 01 02", hint="[Anzahl, Pin, Pin…]"),), "Pins der Gegenstelle lesen", g),
    ]


def _proteus(key, label, variant) -> ModuleDef:
    c = [
        Command("Reset", 0x00, (), "Modul neu starten", "Allgemein"),
        Command("GetState", 0x01, (), "Rolle, Aktion und Verbindungsstatus abfragen", "Allgemein"),
        Command("Sleep", 0x02, (), "In den Schlafmodus wechseln", "Allgemein"),
        Command("UART_Disable", 0x1B, (), "UART abschalten (Wecken über WAKE_UP-Pin)", "Allgemein"),
        Command("FactoryReset", 0x1C, (), "Alle Einstellungen auf Werkszustand", "Allgemein", danger=True),
        Command("Get", 0x10, (Param("Einstellung", "u8", "2"),), "Nutzereinstellung lesen", "Einstellungen"),
        Command("Set", 0x11, (Param("Einstellung", "u8", "2"), Param("Wert", "hex", "")), "Nutzereinstellung schreiben (Neustart)", "Einstellungen"),
        Command("Data", 0x04, (data(),), "Daten an verbundene Gegenstelle senden", "Daten"),
        Command("Disconnect", 0x07, (), "Verbindung trennen", "Verbindung"),
        Command("PhyUpdate", 0x1A, (PHY,), "PHY der Verbindung ändern", "Verbindung"),
        Command("Passkey", 0x0D, (Param("Passkey", "ascii", "123123", length=6),), "Passkey bei Kopplung beantworten", "Sicherheit"),
        Command("NumericComparison", 0x24, (Param("Antwort", "choice", "0", (("0", "Bestätigen"), ("1", "Ablehnen"))),), "Numeric Comparison beantworten", "Sicherheit"),
        Command("GetBonds", 0x0F, (), "Gespeicherte Kopplungen auflisten", "Sicherheit"),
        Command("DeleteBonds", 0x0E, (Param("Bond-ID (leer = alle)", "hex", ""),), "Kopplungen löschen", "Sicherheit"),
        Command("DTMStart", 0x1D, (), "Direct Test Mode aktivieren", "Test"),
        Command("DTM", 0x1E, (u8("Befehl", "1"), u8("Kanal", "19"), u8("Länge / Leistung", "16"), u8("Muster", "0")), "DTM-Befehl (Funktest)", "Test"),
    ]
    if variant != "e":
        c += [
            Command("Connect", 0x06, (Param("BT-MAC", "mac", "11 22 33 44 55 66", length=6),), "Mit Gerät verbinden (MAC, LSB zuerst)", "Verbindung"),
            Command("ScanStart", 0x09, (), "Suche nach Geräten starten", "Scan"),
            Command("ScanStop", 0x0A, (), "Suche beenden", "Scan"),
            Command("GetDevices", 0x0B, (), "Gefundene Geräte abrufen", "Scan"),
            Command("SetBeacon", 0x0C, (data("Beacon-Daten", "01 02 03"),), "Beacon-Nutzdaten setzen", "Scan"),
        ]
    if variant in ("III", "e"):
        c += _ble_gpio_cmds()
        c.append(Command("AllowUnbondedConnections", 0x2D, (), "Ungekoppelte Verbindungen einmalig zulassen", "Sicherheit"))
    if variant == "e":
        c += [
            Command("Get_RAM", 0x20, (Param("Einstellung", "u8", "2"),), "Einstellung aus dem RAM lesen", "Einstellungen"),
            Command("Set_RAM", 0x21, (Param("Einstellung", "u8", "2"), Param("Wert", "hex", "")), "Einstellung nur im RAM setzen", "Einstellungen"),
        ]
    names = {0x00: "RESET", 0x01: "GETSTATE", 0x02: "SLEEP", 0x04: "DATA", 0x05: "DATA (TX)", 0x06: "CONNECT",
             0x07: "DISCONNECT", 0x08: "SECURITY", 0x09: "SCANSTART", 0x0A: "SCANSTOP", 0x0B: "GETDEVICES",
             0x0C: "SETBEACON", 0x0D: "PASSKEY", 0x0E: "DELETEBONDS", 0x0F: "GETBONDS", 0x10: "GET", 0x11: "SET",
             0x1A: "PHYUPDATE", 0x1B: "UART_DISABLE", 0x1C: "FACTORYRESET", 0x1D: "DTMSTART", 0x1E: "DTM",
             0x20: "GET_RAM", 0x21: "SET_RAM", 0x22: "ERROR", 0x24: "NUMERIC_COMP", 0x25: "GPIO_LOCAL_WRITECONFIG",
             0x26: "GPIO_LOCAL_WRITE", 0x27: "GPIO_LOCAL_READ", 0x28: "GPIO_REMOTE_WRITECONFIG",
             0x29: "GPIO_REMOTE_WRITE", 0x2A: "GPIO_REMOTE_READ", 0x2B: "GPIO_LOCAL_READCONFIG",
             0x2C: "GPIO_REMOTE_READCONFIG", 0x2D: "ALLOWUNBONDEDCONNECTIONS"}
    full = {0x88: "SECURITY_IND", 0x8B: "RSSI_IND", 0x9B: "UART_ENABLE_IND", 0xA2: "ERROR_IND",
            0x86: "CONNECT_IND", 0xC6: "CHANNELOPEN_RSP", 0x87: "DISCONNECT_IND", 0x84: "DATA_IND",
            0xC4: "TXCOMPLETE_RSP", 0x81: "GETSTATE_IND (Start)"}
    return ModuleDef(key, label, "Bluetooth LE", "cmd16", 115200, c, _proteus_settings(variant), names, full, 0x10, 0x11,
                     note="Befehlsmodus: Frame 0x02 · CMD · Länge (2 Byte) · Daten · XOR-Prüfsumme")


def _proteus4() -> ModuleDef:
    c = [
        Command("Reset", 0x00, (), "Modul neu starten"),
        Command("GetState", 0x01, (), "Status abfragen"),
        Command("Sleep", 0x02, (), "Schlafmodus"),
        Command("UART_Disable", 0x1B, (), "UART abschalten"),
        Command("FactoryReset", 0x1C, (), "Werkseinstellungen", danger=True),
        Command("Get", 0x10, (Param("Einstellung", "u8", "2"),), "Nutzereinstellung lesen", "Einstellungen"),
        Command("Set", 0x11, (Param("Einstellung", "u8", "2"), Param("Wert", "hex", "")), "Nutzereinstellung schreiben", "Einstellungen"),
        Command("Get_RAM", 0x20, (Param("Einstellung", "u8", "2"),), "Einstellung aus dem RAM lesen", "Einstellungen"),
        Command("Set_RAM", 0x21, (Param("Einstellung", "u8", "2"), Param("Wert", "hex", "")), "Einstellung nur im RAM", "Einstellungen"),
        Command("Data", 0x04, (Param("Verbindungs-ID", "u8", "0"), data()), "Daten an eine Verbindung senden", "Daten"),
        Command("MaxPayload", 0x13, (Param("Verbindungs-ID", "u8", "0"),), "Maximale Nutzdatenlänge abfragen", "Daten"),
        Command("Connect", 0x06, (Param("BT-MAC", "mac", "11 22 33 44 55 66", length=6),), "Verbinden", "Verbindung"),
        Command("Disconnect", 0x07, (Param("Verbindungs-ID", "u8", "0"),), "Trennen", "Verbindung"),
        Command("ConnectionInfo", 0x22, (Param("Verbindungs-ID", "u8", "0"),), "Verbindungsdaten abfragen", "Verbindung"),
        Command("PhyUpdate", 0x1A, (Param("Verbindungs-ID", "u8", "0"), PHY), "PHY ändern", "Verbindung"),
        Command("Scan", 0x09, (Param("Aktion", "choice", "1", (("1", "Start"), ("0", "Stopp"))),), "Scan starten/stoppen", "Scan"),
        Command("Advertising", 0x12, (Param("Aktion", "choice", "1", (("1", "Start"), ("0", "Stopp"))),), "Werbung starten/stoppen", "Scan"),
        Command("Passkey", 0x0D, (Param("Verbindungs-ID", "u8", "0"), Param("Passkey", "ascii", "123123", length=6)), "Passkey", "Sicherheit"),
        Command("NumericComparison", 0x24, (Param("Verbindungs-ID", "u8", "0"), Param("Antwort", "choice", "0", (("0", "Bestätigen"), ("1", "Ablehnen")))), "Numeric Comparison", "Sicherheit"),
        Command("GetBonds", 0x0F, (), "Kopplungen auflisten", "Sicherheit"),
        Command("DeleteBonds", 0x0E, (Param("Bond-ID (leer = alle)", "hex", ""),), "Kopplungen löschen", "Sicherheit"),
    ]
    names = {0x00: "RESET", 0x01: "GETSTATE", 0x02: "SLEEP", 0x04: "DATA", 0x06: "CONNECT", 0x07: "DISCONNECT",
             0x08: "SECURITY", 0x09: "SCAN", 0x0D: "PASSKEY", 0x0E: "DELETEBONDS", 0x0F: "GETBONDS", 0x10: "GET",
             0x11: "SET", 0x12: "ADVERTISING", 0x13: "MAXPAYLOAD", 0x1A: "PHYUPDATE", 0x1B: "UART_DISABLE",
             0x1C: "FACTORYRESET", 0x20: "GET_RAM", 0x21: "SET_RAM", 0x22: "CONNECTIONINFO", 0x24: "NUMERIC_COMP"}
    full = {0x81: "STARTUP_IND", 0x84: "DATA_IND", 0xC4: "TXCOMPLETE_RSP", 0x86: "CONNECT_IND",
            0xC6: "LINKOPEN_RSP"}
    return ModuleDef("proteus4", "Proteus-IV", "Bluetooth LE", "cmd16", 115200, c, _proteus4_settings(), names, full, 0x10, 0x11,
                     note="Konfigurationsmodus mit 9600 Baud möglich. Frame 0x02 · CMD · Länge (2 Byte) · Daten · XOR")


# ---------------------------------------------------------------------------
# 2,4 GHz proprietär: Thyone-I / Thyone-e
# ---------------------------------------------------------------------------

def _thyone(key, label, cca=True) -> ModuleDef:
    c = [
        Command("Reset", 0x00, (), "Modul neu starten"),
        Command("GetState", 0x01, (), "Status abfragen"),
        Command("Sleep", 0x02, (), "Schlafmodus"),
        Command("FactoryReset", 0x1C, (), "Werkseinstellungen", danger=True),
        Command("Get", 0x10, (Param("Einstellung", "u8", "1"),), "Nutzereinstellung lesen", "Einstellungen"),
        Command("Set", 0x11, (Param("Einstellung", "u8", "7"), Param("Wert", "hex", "")), "Nutzereinstellung schreiben", "Einstellungen"),
        Command("GetRAM", 0x20, (Param("Einstellung", "u8", "7"),), "Einstellung aus dem RAM lesen", "Einstellungen"),
        Command("SetRAM", 0x21, (Param("Einstellung", "u8", "7"), Param("Wert", "hex", "")), "Einstellung nur im RAM setzen", "Einstellungen"),
        Command("SetChannel", 0x09, (u8("Kanal", "21", "0…38"),), "Funkkanal vorübergehend ändern", "Funk"),
        Command("Unicast", 0x04, (data(),), "An voreingestellte Zieladresse senden", "Daten"),
        Command("Multicast", 0x05, (data(),), "An voreingestellte Gruppe senden", "Daten"),
        Command("Broadcast", 0x06, (data(),), "An alle senden", "Daten"),
        Command("UnicastEx", 0x07, (Param("Zieladresse", "u32", "0x00000001"), data()), "An beliebige Adresse senden", "Daten"),
        Command("MulticastEx", 0x08, (u8("Gruppen-ID", "1"), data()), "An beliebige Gruppe senden", "Daten"),
        Command("GPIO_Local_SetConfig", 0x25, (Param("Konfiguration", "hex", "03 01 02 01", hint="Blöcke [Länge, Pin, Funktion, Wert…]"),), "Lokale Pins konfigurieren", "GPIO"),
        Command("GPIO_Local_GetConfig", 0x26, (), "Lokale Konfiguration lesen", "GPIO"),
        Command("GPIO_Local_Write", 0x27, (Param("Werte", "hex", "02 01 01"),), "Lokale Ausgänge setzen", "GPIO"),
        Command("GPIO_Local_Read", 0x28, (Param("Pins", "hex", "02 01 02"),), "Lokale Pins lesen", "GPIO"),
        Command("GPIO_Remote_SetConfig", 0x29, (Param("Zieladresse", "u32", "0x00000001"), Param("Konfiguration", "hex", "03 01 02 01")), "Pins der Gegenstelle konfigurieren", "GPIO"),
        Command("GPIO_Remote_GetConfig", 0x2A, (Param("Zieladresse", "u32", "0x00000001"),), "Konfiguration der Gegenstelle lesen", "GPIO"),
        Command("GPIO_Remote_Write", 0x2B, (Param("Zieladresse", "u32", "0x00000001"), Param("Werte", "hex", "02 01 01")), "Ausgänge der Gegenstelle setzen", "GPIO"),
        Command("GPIO_Remote_Read", 0x2C, (Param("Zieladresse", "u32", "0x00000001"), Param("Pins", "hex", "02 01 02")), "Pins der Gegenstelle lesen", "GPIO"),
    ]
    s = [
        Setting(0x01, "SerialNumber", "hex", True),
        Setting(0x02, "FWVersion", "hex", True),
        Setting(0x04, "UART_Config", "hex", desc="Baudrate, Parität, Flusssteuerung"),
        Setting(0x07, "RF_Channel", "u8", desc="Funkkanal 0…38"),
        Setting(0x08, "EncryptionMode", "u8", desc="0 = aus"),
        Setting(0x09, "RF_Profile", "u8", desc="Datenrate / Reichweite"),
        Setting(0x0A, "RF_NumRetries", "u8"),
        Setting(0x0B, "RF_TXPower", "i8", desc="Sendeleistung in dBm"),
        Setting(0x0C, "RF_RP_NumSlots", "u8", desc="Repeater-Slots"),
        Setting(0x10, "MAC_SourceAddress", "u32"),
        Setting(0x11, "MAC_DestinationAddress", "u32"),
        Setting(0x12, "MAC_GroupID", "u8"),
        Setting(0x14, "MAC_EncryptionKey", "hex", desc="16 Byte, nur schreibbar"),
        Setting(0x15, "MAC_TTL", "u8", desc="Time to live (Mesh-Sprünge)"),
        Setting(0x18, "Remote_GPIO_Config", "u8"),
        Setting(0x1F, "MAC_DoublePacketClearTime", "hex"),
        Setting(0x20, "ModuleMode", "u8", desc="0 = Normal, 1 = Sniffer"),
    ]
    if cca:
        s += [Setting(0x16, "CCA_Mode", "u8"), Setting(0x17, "CCA_Threshold", "u8")]
    names = {0x00: "RESET", 0x01: "GETSTATE", 0x02: "SLEEP", 0x04: "DATA", 0x05: "MULTICAST", 0x06: "BROADCAST",
             0x07: "UNICAST_EX", 0x08: "MULTICAST_EX", 0x09: "SETCHANNEL", 0x10: "GET", 0x11: "SET",
             0x1C: "FACTORYRESET", 0x20: "GETRAM", 0x21: "SETRAM", 0x25: "GPIO_LOCAL_SETCONFIG",
             0x26: "GPIO_LOCAL_GETCONFIG", 0x27: "GPIO_LOCAL_WRITE", 0x28: "GPIO_LOCAL_READ",
             0x29: "GPIO_REMOTE_SETCONFIG", 0x2A: "GPIO_REMOTE_GETCONFIG", 0x2B: "GPIO_REMOTE_WRITE",
             0x2C: "GPIO_REMOTE_READ"}
    full = {0x73: "START_IND", 0x99: "SNIFFER_IND", 0x84: "DATA_IND", 0xC4: "TXCOMPLETE_RSP"}
    return ModuleDef(key, label, "2,4 GHz proprietär", "cmd16", 115200, c, sorted(s, key=lambda x: x.sid), names, full, 0x10, 0x11,
                     note="Frame 0x02 · CMD · Länge (2 Byte) · Daten · XOR. Adressen 4 Byte, LSB zuerst.")


# ---------------------------------------------------------------------------
# Sub-GHz: Tarvos-III / -e, Telesto-III, Thebe-II, Themisto-I
# ---------------------------------------------------------------------------

def _subghz(key, label, freq) -> ModuleDef:
    mode = Param("Adressmodus", "choice", "0", (("0", "0 – ohne Adresse"), ("1", "1 – Adresse 1 Byte"),
                                               ("2", "2 – Netz-ID + Adresse"), ("3", "3 – Netz-ID + Adresse 2 Byte")))
    c = [
        Command("Reset", 0x05, (), "Modul neu starten"),
        Command("FactoryReset", 0x12, (), "Werkseinstellungen", danger=True),
        Command("Standby", 0x0F, (), "Standby"),
        Command("Shutdown", 0x0E, (), "Abschalten (Wecken über Reset)"),
        Command("PingDUT", 0x1F, (), "Funktionstest des Moduls"),
        Command("Get", 0x0A, (Param("Einstellung", "u8", "33"),), "Nutzereinstellung lesen", "Einstellungen"),
        Command("Set", 0x09, (Param("Einstellung", "u8", "3"), Param("Wert", "hex", "")), "Nutzereinstellung schreiben", "Einstellungen"),
        Command("Data", 0x00, (data(),), "Mit voreingestellter Adresse senden", "Daten"),
        Command("DataEx", 0x01, (mode, u8("Kanal", "106"), u8("Ziel-Netz-ID", "0"), Param("Zieladresse", "u16", "0"), data()),
                "Mit Kanal und Adresse senden", "Daten"),
        Command("SetChannel", 0x06, (u8("Kanal", "106"),), "Kanal im RAM ändern", "Funk"),
        Command("SetDestNetID", 0x07, (u8("Netz-ID", "0"),), "Ziel-Netz-ID im RAM", "Funk"),
        Command("SetDestAddr", 0x08, (Param("Adresse", "hex", "00"),), "Zieladresse im RAM (1 oder 2 Byte)", "Funk"),
        Command("SetPAPower", 0x11, (Param("Leistung (dBm)", "i8", "14"),), "Sendeleistung im RAM", "Funk"),
        Command("RSSI", 0x0D, (), "RSSI des letzten Pakets", "Funk"),
    ]
    s = [
        Setting(0x00, "UART_Baudrate", "hex"),
        Setting(0x01, "Default_RF_Profile", "u8"),
        Setting(0x02, "Default_RF_TXPower", "i8"),
        Setting(0x03, "Default_RF_Channel", "u8"),
        Setting(0x04, "Default_AddressMode", "u8"),
        Setting(0x06, "NumRetries", "u8"),
        Setting(0x07, "Default_DestNetID", "u8"),
        Setting(0x08, "Default_DestAddr", "hex"),
        Setting(0x0A, "SourceNetID", "u8"),
        Setting(0x0B, "SourceAddr", "hex"),
        Setting(0x0F, "CFG_Flags", "hex"),
        Setting(0x10, "RP_Flags", "u8", desc="Repeater"),
        Setting(0x11, "RP_NumSlots", "u8"),
        Setting(0x1A, "LBT_ObservationPeriod", "hex", desc="Listen before talk"),
        Setting(0x1B, "LBT_Threshold", "i8"),
        Setting(0x20, "FactorySettings", "hex", True),
        Setting(0x21, "FWVersion", "hex", True),
    ]
    names = {0x00: "DATA", 0x01: "DATAEX", 0x05: "RESET", 0x06: "SET_CHANNEL", 0x07: "SET_DESTNETID",
             0x08: "SET_DESTADDR", 0x09: "SET", 0x0A: "GET", 0x0D: "RSSI", 0x0E: "SHUTDOWN", 0x0F: "STANDBY",
             0x11: "SET_PAPOWER", 0x12: "FACTORY_RESET", 0x1F: "PINGDUT"}
    full = {0x80: "DATA_IND (Repeat)", 0x81: "DATAEX_IND", 0x85: "RESET_IND", 0x8F: "STANDBY_IND"}
    return ModuleDef(key, label, freq, "cmd8", 115200, c, s, names, full, 0x0A, 0x09,
                     note="Frame 0x02 · CMD · Länge (1 Byte) · Daten · XOR-Prüfsumme")


# ---------------------------------------------------------------------------
# Wireless M-Bus: Metis-I/-II, Metis-e
# ---------------------------------------------------------------------------

def _metis() -> ModuleDef:
    c = [
        Command("Reset", 0x05, (), "Modul neu starten"),
        Command("FactoryReset", 0x11, (), "Werkseinstellungen", danger=True),
        Command("SetMode", 0x04, (Param("wM-Bus-Modus", "hex", "01", hint="z. B. S1, T1, C1 als Modus-Code"),), "Betriebsart setzen"),
        Command("Get", 0x0A, (Param("Position", "u8", "5"), Param("Länge", "u8", "1")), "Speicherbereich lesen", "Einstellungen"),
        Command("Set", 0x09, (Param("Position", "u8", "5"), Param("Länge", "u8", "1"), Param("Wert", "hex", "")), "Speicherbereich schreiben", "Einstellungen"),
        Command("GetSerialNo", 0x0B, (), "Seriennummer"),
        Command("GetFWRelease", 0x0C, (), "Firmware-Version"),
        Command("RSSI", 0x0D, (), "RSSI"),
        Command("SetUARTSpeed", 0x10, (u8("Index", "0"),), "UART-Baudrate wechseln"),
        Command("Data", 0x00, (data("wM-Bus-Telegramm", "44 2D 2C 01 02 03 04 01 07"),), "Telegramm senden", "Daten"),
    ]
    s = [
        Setting(0x05, "UART_CMD_Out_Enable", "u8", length=1),
        Setting(0x3D, "Default_RF_TXPower", "i8", length=1),
        Setting(0x45, "RSSI_Enable", "u8", length=1),
        Setting(0x50, "CFG_Flags", "hex", length=2),
    ]
    names = {0x00: "DATA", 0x03: "DATA_IND", 0x04: "SET_MODE", 0x05: "RESET", 0x09: "SET", 0x0A: "GET",
             0x0B: "GET_SERIALNO", 0x0C: "GET_FWRELEASE", 0x0D: "RSSI", 0x10: "SETUARTSPEED", 0x11: "FACTORYRESET"}
    return ModuleDef("metis", "Metis-I / Metis-II", "Wireless M-Bus 868 MHz", "metis", 9600, c, s, names, {}, 0x0A, 0x09,
                     settings_style="metis",
                     note="Frame 0xFF · CMD · Länge (1 Byte) · Daten · XOR; Bestätigung = CMD | 0x80")


def _metise() -> ModuleDef:
    c = [
        Command("Reset", 0x06, (), "Modul neu starten"),
        Command("FactoryReset", 0x10, (), "Werkseinstellungen", danger=True),
        Command("Standby", 0x07, (), "Standby"),
        Command("Shutdown", 0x08, (), "Abschalten"),
        Command("RXStart", 0x02, (Param("Optionen", "hex", "", hint="TLV: [Option, Länge, Wert]"),), "Empfang starten", "Daten"),
        Command("RXStop", 0x03, (), "Empfang beenden", "Daten"),
        Command("DataEx", 0x01, (Param("Optionen + Nutzdaten (TLV)", "hex", ""),), "Telegramm senden", "Daten"),
        Command("Get", 0x05, (Param("Option(en)", "hex", "81", hint="z. B. 81 = Firmware-Version"),), "Einstellung lesen", "Einstellungen"),
        Command("Set", 0x04, (Param("Optionen (TLV)", "hex", "", hint="[Option, Länge, Wert…]"),), "Einstellung schreiben", "Einstellungen"),
        Command("GetRAM", 0x13, (Param("Option(en)", "hex", "0B"),), "Einstellung aus dem RAM", "Einstellungen"),
        Command("SetRAM", 0x12, (Param("Optionen (TLV)", "hex", ""),), "Einstellung nur im RAM", "Einstellungen"),
    ]
    names = {0x01: "DATAEX", 0x02: "RXSTART", 0x03: "RXSTOP", 0x04: "SET", 0x05: "GET", 0x06: "RESET",
             0x07: "STANDBY", 0x08: "SHUTDOWN", 0x10: "FACTORY_RESET", 0x12: "SET_RAM", 0x13: "GET_RAM"}
    return ModuleDef("metise", "Metis-e", "Wireless M-Bus 868 MHz", "cmd16", 115200, c, [], names, {}, 0x05, 0x04,
                     note="Frame 0x02 · CMD · Länge (2 Byte) · TLV-Optionen · XOR. Optionen: 03 RX-Modus, "
                          "07 Rolle, 0A Baudrate, 0B Sendeleistung, 0C Flags, 80 Werkseinst., 81 Firmware")


# ---------------------------------------------------------------------------
# AT-Befehlsmodule
# ---------------------------------------------------------------------------

def _at_cmds(group_items: dict[str, list[str]]) -> list[Command]:
    out = []
    for group, items in group_items.items():
        for t in items:
            name = t.split("=")[0].split("?")[0]
            out.append(Command(name, 0, (), "", group, at=t))
    return out


def _calypso() -> ModuleDef:
    return ModuleDef("calypso", "Calypso", "WLAN", "at", 921600, _at_cmds({
        "Gerät": ["AT+test", "AT+start", "AT+stop=0", "AT+reboot", "AT+factoryreset", "AT+get=general,version",
                  "AT+set=general,time,", "AT+sleep=", "AT+powersave=", "AT+provisioningStart"],
        "WLAN": ["AT+wlanSetMode=STA", "AT+wlanScan=0,10", "AT+wlanConnect=SSID,,WPA_WPA2,PASSWORT,,,",
                 "AT+wlanDisconnect", "AT+wlanGet=general,country_code", "AT+wlanSet=", "AT+wlanProfileAdd=",
                 "AT+wlanProfileGet=0", "AT+wlanProfileDel=255", "AT+wlanPolicyGet=connection", "AT+wlanPolicySet="],
        "Netzwerk": ["AT+netCfgGet=IPV4_STA_ADDR", "AT+netCfgSet=", "AT+netAppStart=", "AT+netAppStop=",
                     "AT+netAppPing=INET,8.8.8.8,3,32,1000,0,0", "AT+netAppGetHostByName=www.example.com,INET",
                     "AT+netAppUpdateTime", "AT+netAppGet=", "AT+netAppSet="],
        "Socket": ["AT+socket=INET,STREAM,TCP", "AT+connect=0,INET,8000,192.168.1.10", "AT+bind=", "AT+listen=",
                   "AT+accept=", "AT+send=0,0,5,Hallo", "AT+recv=0,0,100", "AT+sendTo=", "AT+recvFrom=",
                   "AT+close=0", "AT+setSockOpt=", "AT+getSockOpt="],
        "Dateien": ["AT+fileGetFileList", "AT+fileGetInfo=", "AT+fileOpen=", "AT+fileRead=", "AT+fileWrite=",
                    "AT+fileClose=", "AT+fileDel="],
        "MQTT": ["AT+mqttCreate=", "AT+mqttSet=", "AT+mqttConnect=0", "AT+mqttSubscribe=", "AT+mqttPublish=",
                 "AT+mqttUnsubscribe=", "AT+mqttDisconnect=0", "AT+mqttDelete=0"],
        "HTTP": ["AT+httpCreate", "AT+httpConnect=", "AT+httpSendReq=", "AT+httpReadResBody=", "AT+httpSetHeader=",
                 "AT+httpGetHeader=", "AT+httpDisconnect=", "AT+httpDestroy=", "AT+httpCustomResponse="],
        "GPIO": ["AT+gpioGet=", "AT+gpioSet="],
    }), note="AT-Befehle, Zeilenende CR LF. Antworten: OK / error / Ereignisse mit +eventXYZ")


def _cordelia() -> ModuleDef:
    return ModuleDef("cordelia", "Cordelia-I", "WLAN (IoT-Cloud)", "at", 115200, _at_cmds({
        "Gerät": ["AT+test", "AT+start", "AT+stop=0", "AT+reboot", "AT+factoryreset", "AT+hibernate=",
                  "AT+get=general,version", "AT+set=", "AT+provisioningStart"],
        "WLAN": ["AT+wlanScan=0,10", "AT+wlanConnect=SSID,,WPA_WPA2,PASSWORT,,,", "AT+wlanDisconnect",
                 "AT+wlanGet=", "AT+wlanSet=", "AT+wlanProfileAdd=", "AT+wlanProfileGet=0",
                 "AT+wlanProfileDel=255", "AT+wlanPolicyGet=connection", "AT+wlanPolicySet="],
        "IoT": ["AT+iotenrol", "AT+iotconnect", "AT+iotpublish=", "AT+iotdisconnect"],
        "Dateien": ["AT+fileGetFileList", "AT+fileGetInfo=", "AT+fileOpen=", "AT+fileRead=", "AT+fileWrite=",
                    "AT+fileClose=", "AT+fileDel="],
    }), note="AT-Befehle, Zeilenende CR LF")


def _stephano() -> ModuleDef:
    return ModuleDef("stephano", "Stephano-I", "WLAN + Bluetooth LE", "at", 115200, _at_cmds({
        "Gerät": ["AT", "AT+GMR", "AT+RST", "AT+RESTORE", "AT+SYSSTORE=1", "AT+SYSTEMP?", "AT+SLEEP=",
                  "AT+GSLP=", "AT+RFPOWER?", "AT+UART_CUR?", "AT+UART_DEF=", "AT+SYSTIMESTAMP?"],
        "WLAN": ["AT+CWINIT=1", "AT+CWMODE=1", "AT+CWLAP", "AT+CWJAP=\"SSID\",\"PASSWORT\"", "AT+CWQAP",
                 "AT+CWSTATE?", "AT+CWSAP=", "AT+CWDHCP?", "AT+CWHOSTNAME?", "AT+CWAUTOCONN=1", "AT+CWCOUNTRY?"],
        "TCP/IP": ["AT+CIPSTA?", "AT+CIPSTAMAC?", "AT+CIPMUX=1", "AT+CIPSTART=\"TCP\",\"192.168.1.10\",8000",
                   "AT+CIPSEND=5", "AT+CIPCLOSE", "AT+CIPSTATE?", "AT+CIPSERVER=1,80", "AT+CIPDOMAIN=\"example.com\"",
                   "AT+PING=\"8.8.8.8\"", "AT+CIPSNTPCFG=1,1", "AT+CIPSNTPTIME?"],
        "MQTT": ["AT+MQTTUSERCFG=", "AT+MQTTCONN=", "AT+MQTTPUB=", "AT+MQTTSUB=", "AT+MQTTUNSUB=", "AT+MQTTCLEAN=0"],
        "HTTP": ["AT+HTTPCLIENT=", "AT+HTTPGETSIZE=", "AT+HTTPCGET=", "AT+HTTPCPOST="],
        "Bluetooth LE": ["AT+BLEINIT=2", "AT+BLEINIT?", "AT+BLEADDR?", "AT+BLENAME=\"Stephano\"",
                         "AT+BLEADVPARAM=", "AT+BLEADVDATA=", "AT+BLEADVSTART", "AT+BLEADVSTOP",
                         "AT+BLESCANPARAM=", "AT+BLESCAN=1,3", "AT+BLECONN=", "AT+BLEDISCONN=0",
                         "AT+BLEGATTSSRVCRE", "AT+BLEGATTSSRVSTART", "AT+BLEGATTSNTFY=", "AT+BLEGATTCPRIMSRV=0",
                         "AT+BLEGATTCCHAR=", "AT+BLEGATTCRD=", "AT+BLEGATTCWR=", "AT+BLECFGMTU=0,247",
                         "AT+BLESETPHY=", "AT+BLESECPARAM=", "AT+BLEENC=", "AT+BLEENCCLEAR"],
    }), note="AT-Befehle (ESP-AT-kompatibel), Zeilenende CR LF")


def _daphnis() -> ModuleDef:
    return ModuleDef("daphnis", "Daphnis-I", "LoRaWAN / LoRa P2P", "at", 9600, _at_cmds({
        "Gerät": ["AT", "AT+VER", "AT+FWVER", "AT+SN", "AT+RFS", "AT+SLEEP=", "AT+BAT=?"],
        "LoRaWAN": ["AT+DEUI=?", "AT+APPEUI=?", "AT+APPKEY=", "AT+NWKSKEY=", "AT+APPSKEY=", "AT+DADDR=?",
                    "AT+NWKID=?", "AT+JOIN=1", "AT+SEND=1:48616C6C6F", "AT+CLASS=?", "AT+ADR=?", "AT+DR=?",
                    "AT+TXP=?", "AT+RX1DL=?", "AT+RX2DL=?", "AT+RX2DR=?", "AT+RX2FQ=?", "AT+JN1DL=?",
                    "AT+JN2DL=?", "AT+DCS=?", "AT+PGSLOT=?", "AT+CS=?", "AT+LLVER=?", "AT+RPVER=?"],
        "P2P": ["AT+P2PRX=", "AT+P2PBROADCASTTX=", "AT+P2PUNICASTTX=", "AT+P2PUNICASTEXTX=",
                "AT+P2PMULTICASTTX=", "AT+P2PMULTICASTEXTX="],
        "GPIO": ["AT+GPIOLCFGSET=", "AT+GPIOLCFGGET=", "AT+GPIOLVALUESET=", "AT+GPIOLVALUEGET=",
                 "AT+P2PGPIORCFGSET=", "AT+P2PGPIORCFGGET=", "AT+P2PGPIORVALUESET=", "AT+P2PGPIORVALUEGET="],
    }), note="AT-Befehle, Zeilenende CR LF")


def _adrastea() -> ModuleDef:
    return ModuleDef("adrastea", "Adrastea-I", "LTE-M / NB-IoT + GNSS", "at", 115200, _at_cmds({
        "Gerät": ["AT", "AT+CGMI", "AT+CGMM", "AT+CGMR", "AT+CGSN", "AT+GCAP", "AT+CFUN?", "AT+CFUN=1",
                  "AT+CFUN=0"],
        "SIM": ["AT+CPIN?", "AT%CCID", "AT+CIMI", "AT+CNUM", "AT%CPININFO", "AT+CLCK=", "AT+CPWD="],
        "Netz": ["AT+COPS?", "AT+COPS=0", "AT+CEREG?", "AT+CESQ", "AT+CSQ", "AT+CGDCONT?", "AT+CGACT?",
                 "AT%RATACT?", "AT+CPSMS?", "AT+CEDRXS?", "AT%PDNSET?", "AT%PINGCMD=0,\"8.8.8.8\",3"],
        "SMS": ["AT+CSCA?", "AT+CMGS=", "AT+CMGL=\"ALL\"", "AT+CMGR=", "AT+CMGD=", "AT+CPMS?", "AT+CNMI="],
        "Socket": ["AT%SOCKETCMD=\"ALLOCATE\",1,\"TCP\",\"OPEN\",\"192.168.1.10\",8000", "AT%SOCKETCMD=\"ACTIVATE\",1",
                   "AT%SOCKETDATA=\"SEND\",1,5,\"48616C6C6F\"", "AT%SOCKETDATA=\"RECEIVE\",1,100",
                   "AT%SOCKETCMD=\"DELETE\",1", "AT%DNSRSLV=0,\"www.example.com\""],
        "MQTT": ["AT%MQTTCFG=", "AT%MQTTCMD=\"CONNECT\",1", "AT%MQTTCMD=\"PUBLISH\",", "AT%MQTTCMD=\"SUBSCRIBE\",",
                 "AT%MQTTCMD=\"DISCONNECT\",1", "AT%MQTTEV=\"ALL\",1"],
        "HTTP": ["AT%HTTPCFG=", "AT%HTTPCMD=\"GET\",1", "AT%HTTPSEND=", "AT%HTTPREAD=", "AT%HTTPEV=\"ALL\",1"],
        "GNSS": ["AT%IGNSSACT=1", "AT%IGNSSACT=0", "AT%IGNSSINFO=\"FIX\"", "AT%IGNSSCFG=", "AT%IGNSSEV=\"FIX\",1",
                 "AT%IGNSSMEM=", "AT%IGNSSCEP="],
        "Zertifikate": ["AT%CERTCMD=\"DIR\"", "AT%CERTCFG="],
    }), note="AT-Befehle (3GPP + herstellerspezifisch mit %), Zeilenende CR LF")


def _skoll() -> ModuleDef:
    return ModuleDef("skoll", "Skoll-I", "Bluetooth Classic + LE", "text", 115200, [
        Command("/PING", 0, (), "Verbindungstest", "Text-API", at="/PING"),
        Command("/RBT", 0, (), "Neustart", "Text-API", at="/RBT"),
        Command("/QFV", 0, (), "Firmware-Version abfragen", "Text-API", at="/QFV"),
    ], note="EZSerial-Text-API. Weitere Befehle laut Modulhandbuch direkt eingeben.")


def _transparent() -> ModuleDef:
    return ModuleDef("generic", "Allgemein / transparent", "beliebig", "text", 115200, [],
                     note="Reines Terminal ohne Frame-Auswertung – für den transparenten Modus aller Module")


MODULES: list[ModuleDef] = [
    _proteus("proteus2", "Proteus-II", "II"),
    _proteus("proteus3", "Proteus-III", "III"),
    _proteus("proteuse", "Proteus-e", "e"),
    _proteus4(),
    _thyone("thyone1", "Thyone-I"),
    _thyone("thyonee", "Thyone-e", cca=False),
    _subghz("tarvos3", "Tarvos-III", "Sub-GHz 868 MHz"),
    _subghz("tarvose", "Tarvos-e", "Sub-GHz 868 MHz"),
    _subghz("telesto3", "Telesto-III", "Sub-GHz 915 MHz"),
    _subghz("thebe2", "Thebe-II", "Sub-GHz 169 MHz"),
    _subghz("themisto1", "Themisto-I", "Sub-GHz 915 MHz"),
    _metis(),
    _metise(),
    _calypso(),
    _cordelia(),
    _stephano(),
    _daphnis(),
    _adrastea(),
    _skoll(),
]

from .modules_at import EXTRA_MODULES  # noqa: E402  (braucht die Klassen oben)

MODULES += EXTRA_MODULES
MODULES.append(_transparent())
for _m in MODULES:
    if _m.key == "generic":
        _m.vendor = "Allgemein"
MODULE_BY_KEY = {m.key: m for m in MODULES}
