"""Frame-Aufbau und -Auswertung für die UART-Befehlsschnittstelle."""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .modules import ModuleDef, Param, STATUS_TEXT, TYPE_SUFFIX

STX = {"cmd16": 0x02, "cmd8": 0x02, "metis": 0xFF}


def xor(data: bytes) -> int:
    cs = 0
    for b in data:
        cs ^= b
    return cs


def build_frame(proto: str, cmd: int, payload: bytes) -> bytes:
    if proto == "cmd16":
        head = bytes([0x02, cmd]) + struct.pack("<H", len(payload))
    elif proto in ("cmd8", "metis"):
        if len(payload) > 255:
            raise ValueError("Nutzdaten zu lang (max. 255 Bytes bei diesem Modul)")
        head = bytes([STX[proto], cmd, len(payload)])
    else:
        raise ValueError(f"Protokoll {proto} hat keine Frames")
    body = head + payload
    return body + bytes([xor(body)])


# ---------------------------------------------------------------------------
# Parameter → Bytes
# ---------------------------------------------------------------------------

def _int(text: str) -> int:
    t = text.strip().replace("_", "")
    if not t:
        return 0
    return int(t, 0)


def _hex(text: str) -> bytes:
    t = text.replace("0x", "").replace("0X", "").replace(",", " ")
    t = "".join(t.split())
    if len(t) % 2:
        raise ValueError("HEX-Wert braucht eine gerade Anzahl Ziffern")
    return bytes.fromhex(t)


def param_bytes(p: Param, text: str) -> bytes:
    try:
        if p.kind == "u8" or p.kind == "choice":
            v = _int(text)
            if not 0 <= v <= 255:
                raise ValueError
            return bytes([v])
        if p.kind == "i8":
            return struct.pack("<b", _int(text))
        if p.kind == "u16":
            return struct.pack("<H", _int(text))
        if p.kind == "u32":
            return struct.pack("<I", _int(text))
        if p.kind in ("hex", "mac", "data"):
            b = _hex(text)
            if p.kind == "mac" and len(b) != 6:
                raise ValueError("MAC braucht 6 Bytes")
            return b
        if p.kind == "ascii":
            b = text.encode("latin-1")
            if p.length and len(b) != p.length:
                raise ValueError(f"{p.name}: genau {p.length} Zeichen nötig")
            return b
    except (ValueError, struct.error) as exc:
        msg = str(exc) if str(exc) else "ungültiger Wert"
        raise ValueError(f"{p.name}: {msg}") from None
    raise ValueError(f"Unbekannter Parametertyp {p.kind}")


def command_payload(module: ModuleDef, cmd, values: list[str]) -> bytes:
    """Nutzdaten eines Befehls aus den Formularwerten bauen (inkl. Sonderfälle)."""
    if cmd.name == "DataEx" and module.proto == "cmd8":
        mode = _int(values[0])
        ch = param_bytes(cmd.params[1], values[1])
        net = param_bytes(cmd.params[2], values[2])
        addr = _int(values[3])
        data = param_bytes(cmd.params[4], values[4])
        if mode == 0:
            return ch + data
        if mode == 1:
            return ch + bytes([addr & 0xFF]) + data
        if mode == 2:
            return ch + net + bytes([addr & 0xFF]) + data
        return ch + net + bytes([(addr >> 8) & 0xFF, addr & 0xFF]) + data
    return b"".join(param_bytes(p, v) for p, v in zip(cmd.params, values))


# ---------------------------------------------------------------------------
# Werte → Text
# ---------------------------------------------------------------------------

def hexs(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def decode_value(kind: str, b: bytes) -> str:
    if not b:
        return ""
    try:
        if kind == "u8":
            return str(b[0])
        if kind == "i8":
            return f"{struct.unpack('<b', b[:1])[0]} dBm" if len(b) else ""
        if kind == "u16" and len(b) >= 2:
            return str(struct.unpack("<H", b[:2])[0])
        if kind == "u32" and len(b) >= 4:
            v = struct.unpack("<I", b[:4])[0]
            return f"{v} (0x{v:08X})"
        if kind == "ascii":
            return b.split(b"\x00")[0].decode("latin-1")
        if kind == "mac":
            return ":".join(f"{x:02X}" for x in reversed(b))
    except struct.error:
        pass
    return hexs(b)


def encode_value(kind: str, text: str) -> bytes:
    return param_bytes(Param("Wert", kind), text)


# ---------------------------------------------------------------------------
# Empfang
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    raw: bytes
    cmd: int
    payload: bytes
    ok: bool                  # Prüfsumme korrekt


class FrameParser:
    """Zerlegt den Bytestrom in Frames; Bytes außerhalb gelten als Rohdaten."""

    def __init__(self, proto: str):
        self.proto = proto
        self.buf = bytearray()

    def feed(self, data: bytes) -> list:
        """Liefert Liste aus Frame-Objekten und bytes (Rohdaten)."""
        out = []
        self.buf += data
        stx = STX.get(self.proto)
        hlen = 4 if self.proto == "cmd16" else 3
        while self.buf:
            i = self.buf.find(bytes([stx]))
            if i < 0:
                out.append(bytes(self.buf))
                self.buf.clear()
                break
            if i > 0:
                out.append(bytes(self.buf[:i]))
                del self.buf[:i]
            if len(self.buf) < hlen:
                break
            ln = struct.unpack("<H", self.buf[2:4])[0] if self.proto == "cmd16" else self.buf[2]
            if ln > 2048:
                out.append(bytes(self.buf[:1]))
                del self.buf[:1]
                continue
            total = hlen + ln + 1
            if len(self.buf) < total:
                break
            raw = bytes(self.buf[:total])
            ok = xor(raw[:-1]) == raw[-1]
            if not ok:
                # kein gültiger Frame: STX als Rohbyte behandeln und weitersuchen
                out.append(raw[:1])
                del self.buf[:1]
                continue
            out.append(Frame(raw, raw[1], raw[hlen:-1], ok))
            del self.buf[:total]
        return out

    def flush(self) -> bytes:
        b = bytes(self.buf)
        self.buf.clear()
        return b


def frame_type(module: ModuleDef, cmd: int) -> str:
    if module.proto == "metis":
        if cmd == 0x03:
            return "IND"
        return "CNF" if cmd & 0x80 else "REQ"
    return TYPE_SUFFIX[(cmd >> 6) & 0x03]


def frame_name(module: ModuleDef, cmd: int) -> str:
    if cmd in module.full_names:
        return "CMD_" + module.full_names[cmd]
    t = frame_type(module, cmd)
    if module.proto == "metis":
        if cmd == 0x03:
            return "CMD_" + module.names.get(0x03, "DATA_IND")
        base = cmd & 0x7F
    else:
        base = cmd & 0x3F
    return f"CMD_{module.names.get(base, f'0x{base:02X}')}_{t}"


def describe(module: ModuleDef, f: Frame) -> str:
    """Kurze Auswertung des Frame-Inhalts für das Protokoll."""
    t = frame_type(module, f.cmd)
    p = f.payload
    parts = []
    base = f.cmd & (0x7F if module.proto == "metis" else 0x3F)
    if t == "CNF" and p:
        st = p[0]
        if module.get_code is not None and base == module.get_code and len(p) > 1:
            parts.append(f"Status {st:02X} ({STATUS_TEXT.get(st, '?')}) · Wert: {hexs(p[1:])}")
        else:
            parts.append(f"Status {st:02X} ({STATUS_TEXT.get(st, '?')})")
    elif t == "IND" and p:
        if module.proto == "cmd16" and module.key.startswith("thyone") and base == 0x04 and len(p) >= 5:
            src = struct.unpack("<I", p[:4])[0]
            rssi = struct.unpack("<b", p[4:5])[0]
            parts.append(f"von 0x{src:08X}, RSSI {rssi} dBm, Daten: {_txt(p[5:])}")
        elif module.proto == "cmd16" and module.key.startswith("proteus") and base == 0x04 and len(p) >= 7:
            mac = ":".join(f"{x:02X}" for x in reversed(p[:6]))
            rssi = struct.unpack("<b", p[6:7])[0]
            parts.append(f"von {mac}, RSSI {rssi} dBm, Daten: {_txt(p[7:])}")
        elif module.proto == "cmd8" and base in (0x00, 0x01) and len(p) >= 2:
            rssi = struct.unpack("<b", p[-1:])[0]
            parts.append(f"RSSI {rssi} dBm, Inhalt: {hexs(p[:-1])}")
    return "  ".join(parts)


def _txt(b: bytes) -> str:
    s = "".join(chr(x) if 32 <= x < 127 else "." for x in b)
    return f"{hexs(b)}  »{s}«"
