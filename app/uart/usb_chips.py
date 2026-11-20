"""Erkennung gängiger USB-Seriell-Wandler anhand von USB-Hersteller- und Produkt-ID."""
from __future__ import annotations

# VID -> (Hersteller, {PID: Chip}, Treiberhinweis)
CHIPS: dict[int, tuple[str, dict[int, str], str]] = {
    0x0403: ("FTDI", {0x6001: "FT232R/FT232RL", 0x6010: "FT2232", 0x6011: "FT4232", 0x6014: "FT232H",
                      0x6015: "FT230X/FT231X"}, "Treiber bei Windows 10/11 meist automatisch (FTDI VCP)"),
    0x10C4: ("Silicon Labs", {0xEA60: "CP2102/CP2104", 0xEA70: "CP2105", 0xEA71: "CP2108",
                              0xEA63: "CP2102N"}, "Treiber: Silicon Labs CP210x VCP"),
    0x1A86: ("WCH", {0x7523: "CH340/CH341", 0x7522: "CH340K", 0x5523: "CH341", 0x55D4: "CH9102",
                     0x55D3: "CH343", 0x55D2: "CH342"}, "Treiber: WCH CH34x/CH9102 (bei älteren Windows-Versionen nötig)"),
    0x067B: ("Prolific", {0x2303: "PL2303", 0x23A3: "PL2303GC", 0x23C3: "PL2303GT"},
             "Treiber: Prolific PL2303 (ältere Chips teils nicht mehr unterstützt)"),
    0x04D8: ("Microchip", {0x00DD: "MCP2221", 0x000A: "CDC (PIC)", 0x00DF: "MCP2200"}, "Windows-Standardtreiber (CDC)"),
    0x0483: ("STMicroelectronics", {0x5740: "STM32 Virtual COM", 0x374B: "ST-LINK/V2-1 VCP",
                                    0x374E: "ST-LINK V3 VCP", 0x3752: "ST-LINK V3 VCP"}, "Windows-Standardtreiber (CDC)"),
    0x1366: ("SEGGER", {0x0105: "J-Link VCOM", 0x1015: "J-Link VCOM", 0x1051: "J-Link VCOM"}, "SEGGER J-Link-Treiber"),
    0x1915: ("Nordic Semiconductor", {0x520F: "nRF52 USB CDC", 0xC00A: "nRF Dongle"}, "Windows-Standardtreiber (CDC)"),
    0x2E8A: ("Raspberry Pi", {0x0005: "RP2040 CDC", 0x000A: "RP2040 CDC", 0x000C: "Debugprobe"}, "Windows-Standardtreiber (CDC)"),
    0x303A: ("Espressif", {0x1001: "ESP32-S3/C3 USB-JTAG/Serial", 0x0002: "ESP32-S2 CDC"}, "Windows-Standardtreiber (CDC)"),
    0x2341: ("Arduino", {}, "Windows-Standardtreiber (CDC)"),
    0x239A: ("Adafruit", {}, "Windows-Standardtreiber (CDC)"),
    0x0D28: ("ARM mbed / DAPLink", {0x0204: "DAPLink CDC"}, "Windows-Standardtreiber (CDC)"),
    0x1FC9: ("NXP", {}, "Windows-Standardtreiber (CDC)"),
    0x2FE3: ("Zephyr CDC-ACM", {}, "Windows-Standardtreiber (CDC)"),
}


def identify(vid: int | None, pid: int | None, description: str = "") -> tuple[str, str]:
    """Liefert (Chip-Bezeichnung, Treiberhinweis)."""
    if vid is None:
        d = description.lower()
        if "bluetooth" in d:
            return "Bluetooth-COM (kein USB)", ""
        return "Serieller Port (kein USB)", ""
    entry = CHIPS.get(vid)
    if entry is None:
        return f"USB-Seriell {vid:04X}:{pid or 0:04X}", "Unbekannter Chip – Windows-Standardtreiber (CDC) oder Herstellertreiber"
    maker, pids, hint = entry
    chip = pids.get(pid or -1)
    return (f"{maker} {chip}" if chip else f"{maker} ({pid or 0:04X})"), hint
