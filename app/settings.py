"""Einstellungen und Makros – gespeichert als JSON unter %APPDATA%."""
from __future__ import annotations

import json
import os
from pathlib import Path

import shutil

from . import APP_NAME, OLD_APP_NAMES
from .protocol import DEFAULT_PROFILES, ProfileType, ProfileUUIDs

DEFAULTS = {
    "write_mode": "auto",          # auto | with | without
    "encoding": "HEX",
    "connect_timeout": 20,
    "scan_passive": False,
    "log_max": 5000,
    "timestamp_ms": True,
    "split_large": False,
    "stale_seconds": 15,
    "uuid_overrides": {},          # Profil -> {service, rx, tx}
    "macros": [
        {"name": "Hallo", "hex": "48616C6C6F"},
        {"name": "0x01 02 03", "hex": "010203"},
    ],
    "window": None,
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    p = Path(base) / APP_NAME
    if not p.exists():
        # Einstellungen und Makros der Vorgängerversion übernehmen
        for old in OLD_APP_NAMES:
            src = Path(base) / old
            if (src / "settings.json").exists():
                try:
                    shutil.copytree(src, p)
                except OSError:
                    pass
                break
    p.mkdir(parents=True, exist_ok=True)
    return p


class Settings:
    def __init__(self):
        self.path = config_dir() / "settings.json"
        self.data = dict(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def profiles(self) -> dict[ProfileType, ProfileUUIDs]:
        out = {}
        ov = self.get("uuid_overrides") or {}
        for ptype, default in DEFAULT_PROFILES.items():
            o = ov.get(ptype.value) or {}
            out[ptype] = ProfileUUIDs(
                (o.get("service") or default.service).lower(),
                (o.get("rx") or default.rx).lower(),
                (o.get("tx") or default.tx).lower(),
            )
        return out
