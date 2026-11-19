"""Protokoll-Schicht: SPP-ähnliche BLE-Profile, Modultypen, Header, GPIO-Fernbefehle.

Die Werte (UUIDs, Header-Bytes, Befehlscodes) entsprechen den öffentlichen
Developer-Guides der Proteus-Modulreihe (ANR005 / ANR009 / ANR024).
Die Implementierung selbst ist eigenständig.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum, IntEnum

# ---------------------------------------------------------------------------
# Profile (GATT-Services)
# ---------------------------------------------------------------------------


class ProfileType(str, Enum):
    WESPP = "WE-SPP"        # Proteus-I/-II/-III/-e, Setebos-I, Stephano-I
    WESPP2 = "WE-SPP2"      # Proteus-IV
    CYSPP = "CY-SPP"        # Skoll-I


@dataclass
class ProfileUUIDs:
    service: str
    rx: str          # PC -> Modul (Schreiben)
    tx: str          # Modul -> PC (Notification)


DEFAULT_PROFILES: dict[ProfileType, ProfileUUIDs] = {
    ProfileType.WESPP: ProfileUUIDs(
        "6e400001-c352-11e5-953d-0002a5d5c51b",
        "6e400002-c352-11e5-953d-0002a5d5c51b",
        "6e400003-c352-11e5-953d-0002a5d5c51b",
    ),
    ProfileType.WESPP2: ProfileUUIDs(
        "b70c0001-686c-4036-bb28-b797ae6a8d3a",
        "b70c0002-686c-4036-bb28-b797ae6a8d3a",
        "b70c0003-686c-4036-bb28-b797ae6a8d3a",
    ),
    # Skoll: unbestätigter Datenkanal – RX und TX sind dieselbe Characteristic
    ProfileType.CYSPP: ProfileUUIDs(
        "65333333-a115-11e2-9e9a-0800200ca100",
        "65333333-a115-11e2-9e9a-0800200ca102",
        "65333333-a115-11e2-9e9a-0800200ca102",
    ),
}

WE_COMPANY_ID = 0x031A  # Bluetooth-SIG-Firmenkennung Würth Elektronik eiSos


def profile_for_service(uuids: list[str], profiles: dict[ProfileType, ProfileUUIDs]) -> ProfileType | None:
    low = {u.lower() for u in uuids}
    for ptype, p in profiles.items():
        if p.service.lower() in low:
            return ptype
    return None


# ---------------------------------------------------------------------------
# Modultypen
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    label: str
    profile: ProfileType
    uses_header: bool             # 0x01-Datenheader / 0x02-Befehlsheader
    default_mtu: int
    max_payload_request: bool     # CMD_GETSTATE liefert max. Nutzdatenlänge
    gpio_pins: tuple = ()         # (id, name, pwm_fähig)


MODULES: list[ModuleSpec] = [
    ModuleSpec("proteus1", "Proteus-I", ProfileType.WESPP, True, 247, False),
    ModuleSpec("proteus2", "Proteus-II", ProfileType.WESPP, True, 247, False),
    ModuleSpec("proteus3", "Proteus-III", ProfileType.WESPP, True, 247, True,
               ((1, "B1", False), (2, "B2", False), (3, "B3", True),
                (4, "B4", True), (5, "B5", True), (6, "B6", True))),
    ModuleSpec("proteus4", "Proteus-IV", ProfileType.WESPP2, False, 23, False),
    ModuleSpec("proteuse", "Proteus-e", ProfileType.WESPP, True, 247, True,
               ((1, "B1", False), (2, "B2", False))),
    ModuleSpec("setebos1", "Setebos-I", ProfileType.WESPP, True, 247, True,
               ((2, "B2", False), (3, "B3", True), (4, "B4", True),
                (5, "B5", True), (6, "B6", True))),
    ModuleSpec("stephano1", "Stephano-I", ProfileType.WESPP, False, 515, False),
    ModuleSpec("skoll1", "Skoll-I", ProfileType.CYSPP, False, 131, False),
]
MODULE_BY_KEY = {m.key: m for m in MODULES}


def guess_module(name: str | None, profile: ProfileType | None) -> ModuleSpec:
    """Einfache Vorauswahl anhand Name/Profil – der Nutzer kann sie im Dialog ändern."""
    n = (name or "").lower()
    if profile == ProfileType.WESPP2:
        return MODULE_BY_KEY["proteus4"]
    if profile == ProfileType.CYSPP:
        return MODULE_BY_KEY["skoll1"]
    for key, needles in (
        ("setebos1", ("setebos",)),
        ("stephano1", ("stephano",)),
        ("proteuse", ("proteus-e", "proteus_e", "proteuse")),
        ("proteus4", ("proteus-iv", "proteus4", "proteus-4")),
        ("proteus3", ("proteus-iii", "proteus3", "proteus-3")),
        ("proteus2", ("proteus-ii", "proteus2", "proteus-2")),
        ("proteus1", ("proteus-i", "proteus1", "proteus-1")),
    ):
        if any(s in n for s in needles):
            return MODULE_BY_KEY[key]
    return MODULE_BY_KEY["proteus3"]


# ---------------------------------------------------------------------------
# Header & Befehle
# ---------------------------------------------------------------------------


class Header(IntEnum):
    DATA = 0x01
    CMD = 0x02
    FRAGDATA = 0x04


class Cmd(IntEnum):
    GETSTATE_REQ = 0x01
    GETSTATE_CNF = 0x41
    GPIO_REMOTE_WRITECONFIG_REQ = 0x28
    GPIO_REMOTE_WRITECONFIG_CNF = 0x68
    GPIO_REMOTE_WRITE_REQ = 0x29
    GPIO_REMOTE_WRITE_CNF = 0x69
    GPIO_REMOTE_READ_REQ = 0x2A
    GPIO_REMOTE_READ_CNF = 0x6A
    GPIO_REMOTE_READCONFIG_REQ = 0x2C
    GPIO_REMOTE_READCONFIG_CNF = 0x6C
    GPIO_LOCAL_WRITE_IND = 0xA6


def cmd_name(code: int) -> str:
    try:
        return "CMD_" + Cmd(code).name
    except ValueError:
        return f"CMD_0x{code:02X}"


class PinType(IntEnum):
    NONE = 0
    INPUT = 1
    OUTPUT = 2
    PWM = 3


PIN_TYPE_LABEL = {PinType.NONE: "Nicht konfiguriert", PinType.INPUT: "Eingang",
                  PinType.OUTPUT: "Ausgang", PinType.PWM: "PWM"}
PULL_LABEL = {0: "Kein Pull", 1: "Pull-Down", 2: "Pull-Up"}
LEVEL_LABEL = {0: "Low", 1: "High"}


@dataclass
class GpioPin:
    pin_id: int
    name: str
    pwm_capable: bool
    ptype: PinType = PinType.NONE
    pull: int = 0            # nur Eingang
    level: int = 0           # Ausgang: Startpegel / aktueller Wert
    pwm_period_ms: int = 1000
    pwm_ratio: int = 50      # 0..100 %
    value: int | None = None  # zuletzt gelesener / geschriebener Wert


def build_data_packets(payload: bytes, module: ModuleSpec, mtu: int | None, split: bool) -> list[bytes]:
    """Nutzdaten in BLE-Pakete verpacken. ``mtu`` ist die ATT-MTU."""
    att = (mtu or module.default_mtu) - 3
    room = att - (1 if module.uses_header else 0)
    if room <= 0:
        room = 20
    if len(payload) > room and not split:
        raise ValueError(f"Nutzdaten zu groß ({len(payload)} Bytes, max. {room} Bytes pro Paket)")
    chunks = [payload[i:i + room] for i in range(0, len(payload), room)] or [b""]
    if module.uses_header:
        return [bytes([Header.DATA]) + c for c in chunks]
    return chunks


def max_payload(module: ModuleSpec, mtu: int | None) -> int:
    return (mtu or module.default_mtu) - 3 - (1 if module.uses_header else 0)


def cmd_packet(cmd: Cmd, body: bytes = b"") -> bytes:
    return bytes([Header.CMD, cmd]) + body


def gpio_writeconfig_body(pins: list[GpioPin]) -> bytes:
    out = bytearray()
    for p in pins:
        if p.ptype == PinType.PWM:
            per = max(0, min(0xFFFF, int(p.pwm_period_ms)))
            out += bytes([0x05, p.pin_id, PinType.PWM, (per >> 8) & 0xFF, per & 0xFF,
                          max(0, min(100, int(p.pwm_ratio)))])
        elif p.ptype == PinType.INPUT:
            out += bytes([0x03, p.pin_id, PinType.INPUT, p.pull & 0xFF])
        elif p.ptype == PinType.OUTPUT:
            out += bytes([0x03, p.pin_id, PinType.OUTPUT, p.level & 0xFF])
        else:
            out += bytes([0x03, p.pin_id, PinType.NONE, 0x00])
    return bytes(out)


def gpio_read_body(pins: list[GpioPin]) -> bytes:
    return bytes([len(pins)] + [p.pin_id for p in pins])


def gpio_write_body(values: list[tuple[int, int]]) -> bytes:
    out = bytearray()
    for pin_id, val in values:
        out += bytes([0x02, pin_id, val & 0xFF])
    return bytes(out)


def iter_blocks(data: bytes, start: int = 2):
    """Blöcke der Form [Länge, Inhalt...] ab ``start`` durchlaufen."""
    i = start
    while i < len(data):
        n = data[i]
        if n == 0:
            break
        yield data[i + 1:i + 1 + n]
        i += n + 1


@dataclass
class Incoming:
    kind: str                       # "data" | "cmd" | "unknown"
    payload: bytes = b""
    cmd: int | None = None
    info: dict = field(default_factory=dict)


class FragmentAssembler:
    """Empfang von Hochdurchsatz-Fragmenten (Header 0x04)."""

    def __init__(self):
        self.parts: dict[int, bytes] = {}
        self.seq: int | None = None

    def feed(self, raw: bytes) -> bytes | None:
        if len(raw) < 3:
            return None
        seq, nr, total = raw[1], (raw[2] >> 4) & 0x0F, raw[2] & 0x0F
        if not (1 <= nr <= total <= 4):
            return None
        if self.seq != seq:
            self.parts, self.seq = {}, seq
        self.parts[nr] = raw[3:]
        if len(self.parts) == total:
            data = b"".join(self.parts[i] for i in range(1, total + 1))
            self.parts, self.seq = {}, None
            return data
        return None


def parse_incoming(raw: bytes, module: ModuleSpec, frag: FragmentAssembler) -> Incoming | None:
    if not module.uses_header:
        return Incoming("data", bytes(raw))
    if not raw:
        return Incoming("unknown", b"")
    h = raw[0]
    if h == Header.DATA:
        return Incoming("data", bytes(raw[1:]))
    if h == Header.FRAGDATA:
        full = frag.feed(bytes(raw))
        return Incoming("data", full, info={"fragmented": True}) if full is not None else None
    if h == Header.CMD and len(raw) >= 2:
        inc = Incoming("cmd", bytes(raw), cmd=raw[1])
        c = raw[1]
        if c == Cmd.GETSTATE_CNF and len(raw) >= 3:
            inc.info["max_payload"] = raw[2]
        elif c == Cmd.GPIO_REMOTE_READCONFIG_CNF:
            cfg = []
            for blk in iter_blocks(raw):
                if len(blk) < 2:
                    cfg.append((blk[0] if blk else 0, PinType.NONE, b""))
                    continue
                cfg.append((blk[0], blk[1], bytes(blk[2:])))
            inc.info["config"] = cfg
        elif c in (Cmd.GPIO_REMOTE_WRITECONFIG_CNF, Cmd.GPIO_REMOTE_WRITE_CNF):
            inc.info["status"] = [(b[0], b[1]) for b in iter_blocks(raw) if len(b) >= 2]
        elif c in (Cmd.GPIO_REMOTE_READ_CNF, Cmd.GPIO_LOCAL_WRITE_IND):
            inc.info["values"] = [(b[0], b[1]) for b in iter_blocks(raw) if len(b) >= 2]
        return inc
    return Incoming("unknown", bytes(raw))


# ---------------------------------------------------------------------------
# Kodierungen
# ---------------------------------------------------------------------------


class Encoding(str, Enum):
    HEX = "HEX"
    ASCII = "ASCII"
    ASCII_PRINTABLE = "ASCII (druckbar)"


def to_text(data: bytes, enc: Encoding) -> str:
    if enc == Encoding.HEX:
        return " ".join(f"{b:02X}" for b in data)
    if enc == Encoding.ASCII:
        return data.decode("latin-1")
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def from_text(text: str, enc: Encoding) -> bytes:
    if enc == Encoding.HEX:
        cleaned = text.replace("0x", "").replace("0X", "").replace(",", " ")
        cleaned = "".join(cleaned.split())
        if len(cleaned) % 2:
            raise ValueError("HEX-Eingabe muss eine gerade Anzahl Ziffern haben")
        try:
            return bytes.fromhex(cleaned)
        except ValueError as exc:
            raise ValueError("Ungültige HEX-Eingabe") from exc
    # Escapes \r \n \t \xNN in ASCII-Eingaben erlauben
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nx = text[i + 1]
            if nx in "rnt0\\":
                out.append({"r": 13, "n": 10, "t": 9, "0": 0, "\\": 92}[nx])
                i += 2
                continue
            hx = text[i + 2:i + 4]
            if nx == "x" and len(hx) == 2 and all(c in "0123456789abcdefABCDEF" for c in hx):
                out.append(int(text[i + 2:i + 4], 16))
                i += 4
                continue
        out += ch.encode("latin-1", errors="replace")
        i += 1
    return bytes(out)


def random_payload(n: int) -> bytes:
    return os.urandom(max(1, n))


def parse_we_beacon(manufacturer_data: dict[int, bytes]) -> bytes | None:
    """Würth-Beacon: Herstellerdaten 0x031A, erstes Byte 0x01 = Nutzdaten."""
    d = manufacturer_data.get(WE_COMPANY_ID)
    if d and len(d) >= 1 and d[0] == 0x01:
        return bytes(d[1:])
    return None
