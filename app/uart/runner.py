"""Ausführung von Abläufen: Platzhalter ersetzen, senden, auf Antwort warten."""
from __future__ import annotations

import re

from PySide6.QtCore import QObject, QTimer, Signal

from ..protocol import Encoding, from_text
from .framing import build_frame
from .recipes import Recipe, Step

PH = re.compile(r"\{(\w+)(?::(\w+))?\}")


def _num(v: str) -> int:
    return int(v.strip().replace("_", ""), 0)


def substitute(text: str, values: dict[str, str]) -> str:
    def rep(m):
        key, fmt = m.group(1), m.group(2)
        if key not in values:
            return m.group(0)
        v = values[key]
        if fmt is None:
            return v
        if fmt == "hex":
            return " ".join(f"{b:02X}" for b in from_text(v, Encoding.ASCII))
        if fmt == "u8":
            return f"{_num(v) & 0xFF:02X}"
        if fmt == "u16le":
            n = _num(v)
            return f"{n & 0xFF:02X} {(n >> 8) & 0xFF:02X}"
        if fmt == "u32le":
            n = _num(v)
            return " ".join(f"{(n >> (8 * i)) & 0xFF:02X}" for i in range(4))
        if fmt == "mac":
            parts = [p for p in re.split(r"[:\-\s]", v.strip()) if p]
            if len(parts) == 1 and len(parts[0]) == 12:
                parts = [parts[0][i:i + 2] for i in range(0, 12, 2)]
            return " ".join(p.upper() for p in reversed(parts))
        if fmt == "dec3":
            return f"{_num(v):03d}"
        if fmt == "len":
            return str(len(from_text(v, Encoding.ASCII)))
        return v
    return PH.sub(rep, text)


def step_bytes(step: Step, values: dict, module) -> bytes:
    """Was für einen Schritt gesendet wird (leer bei expect/wait/hint)."""
    if step.kind == "at":
        return from_text(substitute(step.value, values), Encoding.ASCII) + module.eol.encode()
    if step.kind == "text":
        return from_text(substitute(step.value, values), Encoding.ASCII)
    if step.kind == "hex":
        return bytes.fromhex("".join(substitute(step.value, values).split()))
    if step.kind == "frame":
        payload = bytes.fromhex("".join(substitute(step.value, values).split()))
        return build_frame(module.proto, step.code, payload)
    return b""


def step_label(step: Step, values: dict, module) -> str:
    """Anzeige des Befehls mit eingesetzten Werten."""
    if step.kind == "at":
        return substitute(step.value, values)
    if step.kind == "text":
        return "Text: " + substitute(step.value, values)
    if step.kind == "hex":
        return "HEX: " + substitute(step.value, values) + ("  (Strg+Z)" if step.value.strip().upper() == "1A" else "")
    if step.kind == "frame":
        p = substitute(step.value, values).strip()
        name = next((c.name for c in module.commands if c.code == step.code and not c.at), f"0x{step.code:02X}")
        return f"{name}  [0x{step.code:02X}]" + (f"  {p}" if p else "")
    if step.kind == "expect":
        return "⧗ warten auf Antwort"
    if step.kind == "wait":
        return f"⧗ {step.timeout / 1000:g} s Pause"
    return "☞ Hinweis"


def expect_label(step: Step, module) -> str:
    e = step.expect
    if e is None:
        return "–"
    if isinstance(e, int):
        nm = module.full_names.get(e) or module.names.get(e & (0x7F if module.proto == "metis" else 0x3F), "")
        return f"0x{e:02X} {nm}".strip()
    return " oder ".join(f"»{x}«" for x in str(e).split("|"))


class RecipeRunner(QObject):
    step_started = Signal(int)
    step_done = Signal(int, str, str)        # Index, Status (ok|error|timeout|skipped), Text
    finished = Signal(str)                   # Zusammenfassung
    need_confirm = Signal(int, str)          # Hinweis-Schritt: Index, Text

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.recipe: Recipe | None = None
        self.values: dict = {}
        self.idx = -1
        self.running = False
        self.single = False
        self.stop_on_error = True
        self.buf = ""
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.results: list[str] = []
        self.pending: list = []          # Frames, die zwischen zwei Schritten ankamen
        ctl.log.connect(self._on_log)
        ctl.frame.connect(self._on_frame)

    # ------------------------------------------------------------------
    def start(self, recipe: Recipe, values: dict, stop_on_error=True, from_index=0, single=False):
        self.recipe, self.values = recipe, dict(values)
        self.stop_on_error = stop_on_error
        self.single = single
        self.results = ["" for _ in recipe.steps]
        self.running = True
        self.idx = from_index - 1
        self._next()

    def stop(self, reason="Abgebrochen."):
        if not self.running:
            return
        self.timer.stop()
        self.running = False
        self.finished.emit(reason)

    def confirm(self, ok: bool):
        if not self.running:
            return
        if ok:
            self._done("ok", "bestätigt")
        else:
            self._done("skipped", "abgebrochen")
            self.stop("Vom Benutzer abgebrochen.")

    # ------------------------------------------------------------------
    def _step(self) -> Step:
        return self.recipe.steps[self.idx]

    def _next(self):
        if not self.running:
            return
        self.idx += 1
        if self.idx >= len(self.recipe.steps) or (self.single and self.idx > 0 and self.results[self.idx - 1]):
            ok = sum(1 for r in self.results if r == "ok")
            bad = sum(1 for r in self.results if r in ("error", "timeout"))
            self.running = False
            self.finished.emit(f"Fertig: {ok} Schritte OK" + (f", {bad} mit Fehler" if bad else "") + ".")
            return
        st = self._step()
        if st.kind != "expect":
            # Antworten, die vor dem Senden eintreffen, gehören nicht zu diesem Schritt
            self.buf = ""
            self.pending = []
        self.step_started.emit(self.idx)
        if st.kind == "hint":
            self.need_confirm.emit(self.idx, st.value)
            return
        if st.kind == "wait":
            self.timer.start(st.timeout)
            return
        if st.kind != "expect":
            if not self.ctl.is_open:
                self._done("error", "COM-Port nicht geöffnet")
                return
            try:
                data = step_bytes(st, self.values, self.ctl.module)
            except ValueError as exc:
                self._done("error", f"Parameter ungültig: {exc}")
                return
            label = step_label(st, self.values, self.ctl.module)
            if st.kind == "frame":
                ok = self.ctl.send_frame(data, f"Ablauf {self.idx + 1}: {label}")
            else:
                ok = self.ctl.send_raw(data, f"Ablauf {self.idx + 1}")
            if not ok:
                self._done("error", "Senden fehlgeschlagen")
                return
        if st.expect is None:
            self.timer.start(min(st.timeout, 300))   # kurze Pause, dann weiter
            return
        self.timer.start(st.timeout)
        if st.kind == "expect":
            # Die Antwort kann schon direkt nach dem vorherigen Schritt eingetroffen sein
            if isinstance(st.expect, int):
                for f in list(self.pending):
                    if f.cmd == st.expect:
                        self.pending.remove(f)
                        self._on_frame(f)
                        return
            else:
                self._check_text()

    def _done(self, status, text):
        self.timer.stop()
        if not self.running:
            return
        st = self._step()
        if status in ("error", "timeout") and st.optional:
            status = "optional"
        self.results[self.idx] = status
        self.step_done.emit(self.idx, status, text)
        if status in ("error", "timeout") and self.stop_on_error and not st.optional:
            self.running = False
            self.finished.emit(f"Angehalten bei Schritt {self.idx + 1}: {text}")
            return
        QTimer.singleShot(120, self._next)

    def _timeout(self):
        if not self.running or self.idx < 0:
            return
        st = self._step()
        if st.kind == "wait" or st.expect is None:
            self._done("ok", self.buf.strip()[-200:] if self.buf.strip() else "")
        else:
            self._done("timeout", "Keine passende Antwort" + (f" – erhalten: {self.buf.strip()[-160:]}" if self.buf.strip() else ""))

    # ------------------------------------------------------------------ Antworten
    def _on_log(self, e):
        if not self.running or self.idx < 0 or e.kind != "rx":
            return
        st = self._step()
        if e.ftype in ("TEXT", "RAW"):
            self.buf += e.data.decode("latin-1", "replace")
            self._check_text()

    def _check_text(self):
        st = self._step()
        if not isinstance(st.expect, str) or not self.timer.isActive():
            return
        up = self.buf.upper()
        alts = [a.upper() for a in st.expect.split("|")]
        if any(a in up for a in alts):
            self._done("ok", self._tail())
        elif ("ERROR" in up and not any("ERROR" in a for a in alts)) or "FAIL" in up:
            self._done("error", self._tail())

    def _tail(self):
        lines = [ln.strip() for ln in self.buf.replace("\r", "\n").split("\n") if ln.strip()]
        return " | ".join(lines[-4:])[:220]

    def _on_frame(self, f):
        if not self.running or self.idx < 0:
            return
        st = self._step()
        if not isinstance(st.expect, int) or not self.timer.isActive() or f.cmd != st.expect:
            self.pending.append(f)
            del self.pending[:-30]
            return
        p = f.payload
        hexs = " ".join(f"{b:02X}" for b in p[:24])
        is_cnf = self.ctl.module.proto != "metis" and (f.cmd & 0xC0) == 0x40
        if is_cnf and p and p[0] != 0x00:
            self._done("error", f"Status 0x{p[0]:02X} – Daten: {hexs}")
        else:
            txt = "".join(chr(b) if 32 <= b < 127 else "·" for b in p[:40])
            self._done("ok", f"{hexs}  »{txt}«" if p else "OK")
