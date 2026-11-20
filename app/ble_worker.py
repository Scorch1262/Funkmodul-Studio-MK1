"""Bluetooth-LE-Schicht: bleak läuft in einem eigenen asyncio-Thread.

Die Oberfläche (Qt) ruft nur die öffentlichen Methoden auf; Ergebnisse kommen
als Qt-Signale zurück und werden automatisch im GUI-Thread zugestellt.
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from bleak import BleakClient, BleakScanner

from .protocol import (
    Cmd, FragmentAssembler, Incoming, ModuleSpec, ProfileType, ProfileUUIDs,
    build_data_packets, cmd_name, cmd_packet, parse_incoming, parse_we_beacon,
    profile_for_service, WE_COMPANY_ID,
)


@dataclass
class Session:
    address: str
    name: str
    module: ModuleSpec
    client: BleakClient
    uuids: ProfileUUIDs
    profile: ProfileType
    mtu: int | None = None
    write_response: bool = False
    frag: FragmentAssembler = field(default_factory=FragmentAssembler)
    waiters: dict = field(default_factory=dict)   # cmd -> asyncio.Future
    sending: bool = False
    stop_flag: bool = False
    user_disconnect: bool = False


class BleWorker(QObject):
    # Scan
    scan_result = Signal(dict)
    scan_state = Signal(bool)
    # Verbindung
    connecting = Signal(str)
    connect_progress = Signal(str, str)     # Adresse, Text
    connected = Signal(str, dict)
    disconnected = Signal(str, str)
    # Protokoll / Log: Adresse, Typ ("info"|"tx"|"rx"|"cmd_tx"|"cmd_rx"|"error"), Text, Daten
    log = Signal(str, str, str, bytes)
    incoming = Signal(str, object)          # Incoming (für GPIO-Seite)
    mtu_changed = Signal(str, int)
    sending_state = Signal(str, bool)
    error = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="ble-loop", daemon=True)
        self.thread.start()
        self.sessions: dict[str, Session] = {}
        self.devices: dict[str, object] = {}     # Adresse -> BLEDevice aus dem Scan
        self.scanner: BleakScanner | None = None
        # Scan-Ergebnisse werden gesammelt und von der Oberfläche abgeholt (kein Signal je Paket –
        # unter Windows kommen sonst Hunderte Meldungen pro Sekunde und die Oberfläche friert ein)
        self._scan_lock = threading.Lock()
        self._scan_buf: dict[str, dict] = {}
        self._scan_packets = 0
        self._connect_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ intern
    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _submit(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def done(f):
            exc = f.exception()
            if exc is not None:
                self.error.emit(f"{type(exc).__name__}: {exc}")
        fut.add_done_callback(done)
        return fut

    def profiles(self) -> dict[ProfileType, ProfileUUIDs]:
        return self.settings.profiles()

    # ------------------------------------------------------------------ Scan
    def start_scan(self):
        self._submit(self._start_scan())

    def stop_scan(self):
        self._submit(self._stop_scan())

    def take_scan_updates(self) -> tuple[list[dict], int]:
        """Seit dem letzten Aufruf geänderte Geräte und Anzahl empfangener Pakete abholen."""
        with self._scan_lock:
            items = list(self._scan_buf.values())
            n = self._scan_packets
            self._scan_buf.clear()
            self._scan_packets = 0
        return items, n

    async def _start_scan(self):
        if self.scanner is not None:
            return
        mode = "passive" if self.settings.get("scan_passive") else "active"

        def cb(device, adv):
            self.devices[device.address] = device
            uuids = list(adv.service_uuids or [])
            mdata = {k: bytes(v) for k, v in (adv.manufacturer_data or {}).items()}
            name = adv.local_name or device.name or ""
            with self._scan_lock:
                self._scan_packets += 1
                old = self._scan_buf.get(device.address)
                d = {
                    "address": device.address,
                    "name": name,
                    "rssi": adv.rssi,
                    "uuids": uuids,
                    "profile": profile_for_service(uuids, self.profiles()),
                    "we": WE_COMPANY_ID in mdata,
                    "beacon": parse_we_beacon(mdata),
                    "tx_power": adv.tx_power,
                    "time": time.time(),
                }
                if old:   # Name/Profil aus früheren Paketen (Scan-Response) behalten
                    d["name"] = d["name"] or old["name"]
                    d["profile"] = d["profile"] or old["profile"]
                    d["we"] = d["we"] or old["we"]
                    d["uuids"] = d["uuids"] or old["uuids"]
                    if d["beacon"] is None:
                        d["beacon"] = old["beacon"]
                self._scan_buf[device.address] = d

        try:
            self.scanner = BleakScanner(detection_callback=cb, scanning_mode=mode)
            await self.scanner.start()
        except Exception as exc:  # Adapter aus / nicht vorhanden
            self.scanner = None
            self.scan_state.emit(False)
            self.error.emit(f"Scan konnte nicht gestartet werden: {exc}\n"
                            "Ist Bluetooth am PC eingeschaltet?")
            return
        self.scan_state.emit(True)

    async def _stop_scan(self):
        if self.scanner is None:
            return
        try:
            await self.scanner.stop()
        finally:
            self.scanner = None
            self.scan_state.emit(False)

    # ------------------------------------------------------------------ Verbinden
    def connect_device(self, address: str, name: str, module: ModuleSpec):
        async def run():
            task = asyncio.ensure_future(self._connect(address, name, module))
            self._connect_tasks[address] = task
            try:
                await task
            except asyncio.CancelledError:
                self._info(address, "Verbindungsaufbau abgebrochen.")
                self.disconnected.emit(address, "Verbindungsaufbau abgebrochen.")
            finally:
                self._connect_tasks.pop(address, None)
        self._submit(run())

    def cancel_connect(self, address: str):
        def do():
            t = self._connect_tasks.get(address)
            if t and not t.done():
                t.cancel()
        self.loop.call_soon_threadsafe(do)

    def disconnect_device(self, address: str):
        self._submit(self._disconnect(address))

    def disconnect_all(self, timeout=4.0):
        fut = asyncio.run_coroutine_threadsafe(self._disconnect_all(), self.loop)
        try:
            fut.result(timeout)
        except Exception:
            pass

    async def _disconnect_all(self):
        if self.scanner is not None:
            await self._stop_scan()
        for addr in list(self.sessions):
            await self._disconnect(addr)

    def _info(self, addr, text, data=b""):
        self.log.emit(addr, "info", text, bytes(data))

    async def _connect(self, address: str, name: str, module: ModuleSpec):
        if address in self.sessions:
            self.error.emit(f"{address} ist bereits verbunden.")
            return
        self.connecting.emit(address)
        # Scan während des Verbindungsaufbaus pausieren – stabiler unter Windows
        was_scanning = self.scanner is not None
        if was_scanning:
            await self._stop_scan()

        self._info(address, f"Verbinde mit {name or address} als {module.label} …")

        def on_disc(_client):
            self.loop.call_soon_threadsafe(asyncio.ensure_future, self._on_lost(address))

        timeout = float(self.settings.get("connect_timeout", 20))
        client = None
        last_exc = None
        for attempt in (1, 2, 3):
            if attempt == 1:
                target = self.devices.get(address, address)
                self.connect_progress.emit(address, "Verbinde …")
            else:
                # Gerät frisch suchen – unter Windows hilft das, wenn der erste Versuch scheitert
                self.connect_progress.emit(address, f"Suche Gerät erneut (Versuch {attempt}/3) …")
                self._info(address, f"Versuch {attempt}: Gerät wird neu gesucht …")
                try:
                    found = await BleakScanner.find_device_by_address(address, timeout=8.0)
                except Exception:
                    found = None
                if found is None:
                    last_exc = last_exc or RuntimeError("Gerät nicht gefunden (wirbt es noch?)")
                    continue
                self.devices[address] = found
                target = found
                self.connect_progress.emit(address, f"Verbinde (Versuch {attempt}/3) …")
            client = BleakClient(target, disconnected_callback=on_disc, timeout=timeout,
                                 winrt={"use_cached_services": False})
            try:
                await asyncio.wait_for(client.connect(), timeout + 5)
                break
            except asyncio.CancelledError:
                try:
                    await client.disconnect()
                except Exception:
                    pass
                raise
            except Exception as exc:
                last_exc = exc
                self._info(address, f"Versuch {attempt} fehlgeschlagen: {type(exc).__name__}: {exc}")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                client = None
                await asyncio.sleep(0.5)
        if client is None:
            msg = f"Verbindung fehlgeschlagen: {last_exc}"
            self.disconnected.emit(address, msg)
            self._info(address, msg + " – Tipp: Modul neu starten, näher an den PC, "
                                     "und prüfen, ob es nicht schon mit einem anderen Gerät verbunden ist.")
            if was_scanning:
                await self._start_scan()
            return
        self.connect_progress.emit(address, "Dienste werden gelesen …")

        profiles = self.profiles()
        svc_uuids = [s.uuid for s in client.services]
        ptype = module.profile if profiles[module.profile].service.lower() in {u.lower() for u in svc_uuids} \
            else profile_for_service(svc_uuids, profiles)
        if ptype is None:
            await client.disconnect()
            msg = "Kein passender SPP-Service gefunden (Proteus/Setebos/Skoll). Gefundene Services: " + \
                  ", ".join(svc_uuids)
            self._info(address, msg)
            self.disconnected.emit(address, msg)
            if was_scanning:
                await self._start_scan()
            return
        if ptype != module.profile:
            self._info(address, f"Hinweis: Gerät bietet Profil {ptype.value}, gewähltes Modul erwartet "
                                f"{module.profile.value}. Es wird {ptype.value} verwendet.")
        uuids = profiles[ptype]
        sess = Session(address, name, module, client, uuids, ptype)
        self.sessions[address] = sess
        self._info(address, f"Verbunden. Service {uuids.service.upper()} gefunden.")

        # Schreibart bestimmen
        mode = self.settings.get("write_mode", "auto")
        char = client.services.get_characteristic(uuids.rx)
        props = set(char.properties) if char else set()
        if mode == "with":
            sess.write_response = True
        elif mode == "without":
            sess.write_response = False
        else:
            sess.write_response = "write-without-response" not in props
        self._info(address, "Schreibart: " + ("mit Antwort (Write Request)" if sess.write_response
                                             else "ohne Antwort (Write Command)"))

        try:
            await client.start_notify(uuids.tx, lambda _c, data: self._on_notify(address, bytes(data)))
            self._info(address, f"Notifications auf {uuids.tx.upper()} aktiviert.")
        except Exception as exc:
            self._info(address, f"Notifications konnten nicht aktiviert werden: {exc}")

        try:
            sess.mtu = int(client.mtu_size)
            self._info(address, f"ATT-MTU: {sess.mtu}")
        except Exception:
            sess.mtu = None

        # Modul-Initialisierung (Proteus-III / -e / Setebos)
        if module.uses_header and module.max_payload_request:
            await self._command(sess, Cmd.GETSTATE_REQ, b"", Cmd.GETSTATE_CNF)
        if module.uses_header and module.gpio_pins:
            await self._command(sess, Cmd.GPIO_REMOTE_READCONFIG_REQ, b"", Cmd.GPIO_REMOTE_READCONFIG_CNF)

        self.connected.emit(address, {
            "name": name, "module": module.key, "profile": ptype.value,
            "mtu": sess.mtu or module.default_mtu,
        })
        if was_scanning:
            await self._start_scan()

    async def _on_lost(self, address: str):
        sess = self.sessions.pop(address, None)
        if sess is None:
            return
        for fut in sess.waiters.values():
            if not fut.done():
                fut.cancel()
        reason = "Getrennt." if sess.user_disconnect else "Verbindung verloren."
        self._info(address, reason)
        self.disconnected.emit(address, reason)

    async def _disconnect(self, address: str):
        sess = self.sessions.get(address)
        if sess is None:
            return
        sess.user_disconnect = True
        sess.stop_flag = True
        try:
            try:
                await sess.client.stop_notify(sess.uuids.tx)
            except Exception:
                pass
            await sess.client.disconnect()
        finally:
            await self._on_lost(address)

    # ------------------------------------------------------------------ Empfang
    def _on_notify(self, address: str, data: bytes):
        sess = self.sessions.get(address)
        if sess is None:
            return
        inc = parse_incoming(data, sess.module, sess.frag)
        if inc is None:
            return
        if inc.kind == "data":
            note = " (Hochdurchsatz, zusammengesetzt)" if inc.info.get("fragmented") else ""
            self.log.emit(address, "rx", f"Daten empfangen – {len(inc.payload)} Bytes{note}", inc.payload)
        elif inc.kind == "cmd":
            if inc.cmd == Cmd.GETSTATE_CNF and "max_payload" in inc.info:
                sess.mtu = inc.info["max_payload"] + 4
                self.mtu_changed.emit(address, sess.mtu)
            self.log.emit(address, "cmd_rx", f"Fernbefehl empfangen: {cmd_name(inc.cmd)}", inc.payload)
            fut = sess.waiters.pop(inc.cmd, None)
            if fut is not None and not fut.done():
                fut.set_result(inc)
        else:
            self.log.emit(address, "rx", f"Unbekanntes Paket – {len(data)} Bytes", data)
        self.incoming.emit(address, inc)

    # ------------------------------------------------------------------ Senden
    async def _write(self, sess: Session, pkt: bytes):
        await sess.client.write_gatt_char(sess.uuids.rx, pkt, response=sess.write_response)

    async def _command(self, sess: Session, cmd: Cmd, body: bytes, expect: Cmd | None,
                       timeout: float = 0.8) -> Incoming | None:
        pkt = cmd_packet(cmd, body)
        fut = None
        if expect is not None:
            fut = self.loop.create_future()
            sess.waiters[int(expect)] = fut
        # vor dem Schreiben protokollieren, damit die Antwort danach erscheint
        self.log.emit(sess.address, "cmd_tx", f"Fernbefehl gesendet: {cmd_name(cmd)}", pkt)
        try:
            await self._write(sess, pkt)
        except Exception as exc:
            if expect is not None:
                sess.waiters.pop(int(expect), None)
            self.log.emit(sess.address, "error", f"Senden fehlgeschlagen: {exc}", b"")
            return None
        if fut is None:
            return None
        try:
            return await asyncio.wait_for(fut, timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            sess.waiters.pop(int(expect), None)
            self._info(sess.address, f"Keine Antwort auf {cmd_name(cmd)} (Zeitüberschreitung).")
            return None

    def send_command(self, address: str, cmd: Cmd, body: bytes, expect: Cmd | None):
        sess = self.sessions.get(address)
        if sess is None:
            self.error.emit("Kein Gerät verbunden.")
            return
        self._submit(self._command(sess, cmd, body, expect))

    def send_data(self, address: str, payloads: list[bytes], count: int, interval_ms: int, split: bool):
        """``payloads``: Liste mit einem Eintrag je Durchlauf (Zufallsdaten ändern sich je Paket)."""
        self._submit(self._send_data(address, payloads, count, interval_ms, split))

    def stop_sending(self, address: str):
        sess = self.sessions.get(address)
        if sess:
            sess.stop_flag = True

    async def _send_data(self, address, payloads, count, interval_ms, split):
        sess = self.sessions.get(address)
        if sess is None:
            self.error.emit("Kein Gerät verbunden.")
            return
        if sess.sending:
            return
        sess.sending, sess.stop_flag = True, False
        self.sending_state.emit(address, True)
        try:
            for i in range(count):
                if sess.stop_flag or address not in self.sessions:
                    self._info(address, "Senden abgebrochen.")
                    break
                payload = payloads[i % len(payloads)]
                try:
                    packets = build_data_packets(payload, sess.module, sess.mtu, split)
                except ValueError as exc:
                    self._info(address, str(exc))
                    break
                t0 = time.perf_counter()
                part = f" in {len(packets)} Paketen" if len(packets) > 1 else ""
                prefix = f"[{i + 1}/{count}] " if count > 1 else ""
                self.log.emit(address, "tx", f"{prefix}Daten gesendet – {len(payload)} Bytes{part}", payload)
                for pkt in packets:
                    await self._write(sess, pkt)
                if i != count - 1:
                    wait = interval_ms / 1000.0 - (time.perf_counter() - t0)
                    end = time.perf_counter() + max(0.0, wait)
                    while time.perf_counter() < end and not sess.stop_flag:
                        await asyncio.sleep(min(0.05, end - time.perf_counter()))
        except Exception as exc:
            self.log.emit(address, "error", f"Senden fehlgeschlagen: {exc}", b"")
        finally:
            sess.sending = False
            self.sending_state.emit(address, False)

    def read_mtu(self, address: str):
        sess = self.sessions.get(address)
        if sess is None:
            return

        async def job():
            try:
                sess.mtu = int(sess.client.mtu_size)
            except Exception:
                pass
            if sess.module.uses_header and sess.module.max_payload_request:
                await self._command(sess, Cmd.GETSTATE_REQ, b"", Cmd.GETSTATE_CNF)
            mtu = sess.mtu or sess.module.default_mtu
            self._info(address, f"MTU: {mtu} (max. Nutzdaten pro Paket: "
                                f"{mtu - 3 - (1 if sess.module.uses_header else 0)} Bytes)")
            self.mtu_changed.emit(address, mtu)
        self._submit(job())

    def shutdown(self):
        self.disconnect_all()
        self.loop.call_soon_threadsafe(self.loop.stop)
