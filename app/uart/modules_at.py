"""AT-Befehlssätze weiterer Funkmodule und Mobilfunk-Modems (Fremdhersteller).

Jeder Eintrag ist eine Vorlage, die im Programm vor dem Senden angepasst werden kann.
Kurzbeschreibungen sind eigene Erklärungen; maßgeblich ist das jeweilige Handbuch.
"""
from __future__ import annotations

from .modules import Command, ModuleDef


def _cmds(groups: dict[str, list[tuple[str, str]]], danger: tuple = ()) -> list[Command]:
    out = []
    for group, items in groups.items():
        for tpl, desc in items:
            name = tpl.split("=")[0].split("?")[0] or tpl
            out.append(Command(name, 0, (), desc, group, at=tpl,
                               danger=any(tpl.startswith(d) for d in danger)))
    return out


# ---------------------------------------------------------------------------
# Gemeinsame 3GPP-Befehle (TS 27.007 / 27.005) – gelten für fast alle Modems
# ---------------------------------------------------------------------------

GSM_BASIS = {
    "Grundlagen": [
        ("AT", "Verbindungstest – Antwort OK"),
        ("ATI", "Hersteller, Modell und Firmware"),
        ("ATE0", "Echo aus (Befehle werden nicht zurückgesendet)"),
        ("ATE1", "Echo ein"),
        ("AT+CMEE=2", "Fehlermeldungen im Klartext statt nur ERROR"),
        ("AT+CGMI", "Hersteller"),
        ("AT+CGMM", "Modell"),
        ("AT+CGMR", "Firmware-Version"),
        ("AT+CGSN", "IMEI"),
        ("AT+CFUN?", "Funktionsstufe (1 = voll, 0/4 = Funk aus)"),
        ("AT+CFUN=1", "Funk einschalten"),
        ("AT+CFUN=4", "Flugmodus (Funk aus)"),
        ("AT+CCLK?", "Uhrzeit des Modems"),
        ("AT&W", "Aktuelle Einstellungen dauerhaft speichern"),
    ],
    "SIM": [
        ("AT+CPIN?", "SIM-Status: READY oder PIN-Abfrage"),
        ("AT+CPIN=1234", "PIN eingeben"),
        ("AT+CCID", "SIM-Kartennummer (ICCID)"),
        ("AT+CIMI", "Teilnehmerkennung (IMSI)"),
        ("AT+CNUM", "Eigene Rufnummer (falls auf SIM gespeichert)"),
    ],
    "Netz": [
        ("AT+CSQ", "Signalqualität: 0–31 (99 = unbekannt), höher ist besser"),
        ("AT+CREG?", "GSM-Netzregistrierung: 1 = Heimnetz, 5 = Roaming"),
        ("AT+CGREG?", "Paketdienst-Registrierung (GPRS)"),
        ("AT+CEREG?", "LTE-Registrierung"),
        ("AT+COPS?", "Aktueller Netzbetreiber"),
        ("AT+COPS=?", "Verfügbare Netze suchen (dauert bis zu 3 min)"),
        ("AT+COPS=0", "Netz automatisch wählen"),
        ("AT+CGATT?", "Paketdienst angemeldet?"),
        ("AT+CGDCONT?", "Eingestellte APNs"),
        ("AT+CGDCONT=1,\"IP\",\"internet\"", "APN setzen – »internet« durch den APN des Anbieters ersetzen"),
        ("AT+CGACT?", "Aktive Datenverbindungen"),
        ("AT+CGPADDR", "IP-Adresse der Datenverbindung"),
    ],
    "SMS": [
        ("AT+CMGF=1", "SMS-Textmodus einschalten"),
        ("AT+CSCS=\"GSM\"", "Zeichensatz GSM"),
        ("AT+CMGS=\"+491701234567\"", "SMS senden – danach Text eingeben und mit Strg+Z (\\x1A) abschließen"),
        ("AT+CMGL=\"ALL\"", "Alle gespeicherten SMS auflisten"),
        ("AT+CMGR=1", "SMS Nr. 1 lesen"),
        ("AT+CMGD=1,4", "Alle SMS löschen"),
        ("AT+CNMI=2,2,0,0,0", "Neue SMS direkt ausgeben"),
        ("AT+CPMS?", "SMS-Speicher und Belegung"),
    ],
    "Anrufe": [
        ("ATD+491701234567;", "Sprachanruf starten (Semikolon nicht vergessen)"),
        ("ATA", "Anruf annehmen"),
        ("ATH", "Auflegen"),
        ("AT+CLIP=1", "Rufnummer eingehender Anrufe anzeigen"),
        ("AT+CUSD=1,\"*100#\"", "USSD-Code senden, z. B. Guthabenabfrage"),
    ],
}


def _gsm(extra: dict[str, list[tuple[str, str]]]) -> dict:
    g = {k: list(v) for k, v in GSM_BASIS.items()}
    for k, v in extra.items():
        g.setdefault(k, []).extend(v)
    return g


# ---------------------------------------------------------------------------
# Kurzstreckenfunk
# ---------------------------------------------------------------------------

def _hc12() -> ModuleDef:
    return ModuleDef("hc12", "HC-12", "433 MHz Funk-UART", "at", 9600, _cmds({
        "Grundlagen": [
            ("AT", "Test – Antwort OK. SET-Pin muss auf GND liegen (Befehlsmodus)"),
            ("AT+V", "Firmware-Version"),
            ("AT+RX", "Alle Einstellungen anzeigen"),
            ("AT+DEFAULT", "Werkseinstellungen (9600 Baud, Kanal 001, FU3, 20 dBm)"),
            ("AT+SLEEP", "Schlafmodus – Aufwecken durch erneuten Befehlsmodus"),
        ],
        "Funk": [
            ("AT+C001", "Kanal 001–127 (433,4 MHz + 400 kHz × (Kanal−1))"),
            ("AT+RC", "Aktuellen Kanal abfragen"),
            ("AT+P8", "Sendeleistung 1–8 (8 = 20 dBm)"),
            ("AT+RP", "Sendeleistung abfragen"),
            ("AT+FU3", "Betriebsart FU1–FU4 (FU3 = Standard, FU4 = maximale Reichweite)"),
            ("AT+RF", "Betriebsart abfragen"),
        ],
        "UART": [
            ("AT+B9600", "Baudrate 1200…115200 (gilt nach Verlassen des Befehlsmodus)"),
            ("AT+RB", "Baudrate abfragen"),
            ("AT+U8N1", "Datenformat, z. B. 8N1, 8E1, 8O1"),
        ],
    }, danger=("AT+DEFAULT",)), vendor="Fremdhersteller", eol="",
        note="Befehle ohne Zeilenende. Befehlsmodus: SET-Pin auf GND, dann 9600 Baud. "
             "Transparenter Funk: SET offen lassen.")


def _hc05() -> ModuleDef:
    return ModuleDef("hc05", "HC-05", "Bluetooth Classic (SPP)", "at", 38400, _cmds({
        "Grundlagen": [
            ("AT", "Test – Antwort OK. KEY/EN-Pin beim Einschalten auf High = AT-Modus mit 38400 Baud"),
            ("AT+VERSION?", "Firmware-Version"),
            ("AT+RESET", "Neustart (verlässt den AT-Modus)"),
            ("AT+ORGL", "Werkseinstellungen"),
            ("AT+STATE?", "Zustand: INITIALIZED, INQUIRING, CONNECTED …"),
        ],
        "Gerät": [
            ("AT+NAME?", "Gerätename abfragen"),
            ("AT+NAME=HC-05", "Gerätename setzen"),
            ("AT+ADDR?", "Eigene Bluetooth-Adresse"),
            ("AT+PSWD?", "PIN abfragen"),
            ("AT+PSWD=\"1234\"", "PIN setzen (bei älterer Firmware ohne Anführungszeichen)"),
            ("AT+CLASS?", "Geräteklasse"),
            ("AT+UART?", "Baudrate, Stoppbits, Parität im Datenmodus"),
            ("AT+UART=9600,0,0", "Datenmodus: 9600 Baud, 1 Stoppbit, keine Parität"),
            ("AT+POLAR?", "Polarität der LED-/Status-Pins"),
        ],
        "Verbindung": [
            ("AT+ROLE?", "Rolle: 0 = Slave, 1 = Master, 2 = Slave-Loop"),
            ("AT+ROLE=1", "Als Master betreiben (baut selbst Verbindungen auf)"),
            ("AT+ROLE=0", "Als Slave betreiben"),
            ("AT+CMODE?", "0 = nur gebundene Adresse, 1 = beliebiges Gerät"),
            ("AT+CMODE=0", "Nur mit der gebundenen Adresse verbinden"),
            ("AT+BIND?", "Gebundene Adresse abfragen"),
            ("AT+BIND=98d3,31,fd1234", "Adresse binden – Format NAP,UAP,LAP mit Kommas"),
            ("AT+INIT", "SPP-Profil starten (vor INQ/LINK nötig)"),
            ("AT+INQM=0,5,9", "Suchmodus: Standard, max. 5 Geräte, 9 × 1,28 s"),
            ("AT+INQ", "Geräte in der Nähe suchen"),
            ("AT+INQC", "Suche abbrechen"),
            ("AT+PAIR=98d3,31,fd1234,10", "Mit Gerät koppeln (Timeout in s)"),
            ("AT+LINK=98d3,31,fd1234", "Mit gekoppeltem Gerät verbinden"),
            ("AT+DISC", "Verbindung trennen"),
            ("AT+RMAAD", "Alle Kopplungen löschen"),
            ("AT+ADCN?", "Anzahl gekoppelter Geräte"),
            ("AT+MRAD?", "Zuletzt verbundene Adresse"),
        ],
    }, danger=("AT+ORGL", "AT+RMAAD")), vendor="Fremdhersteller",
        note="Befehle mit CR LF. AT-Modus: KEY/EN beim Einschalten auf High, immer 38400 Baud.")


def _hc06() -> ModuleDef:
    return ModuleDef("hc06", "HC-06 / JDY-31", "Bluetooth Classic (SPP)", "at", 9600, _cmds({
        "Befehle": [
            ("AT", "Test – Antwort OK (nur ohne aktive Verbindung)"),
            ("AT+VERSION", "Firmware-Version"),
            ("AT+NAMEHC-06", "Gerätename direkt hinter NAME"),
            ("AT+PIN1234", "PIN setzen"),
            ("AT+BAUD4", "Baudrate: 1=1200 2=2400 3=4800 4=9600 5=19200 6=38400 7=57600 8=115200"),
        ],
    }), vendor="Fremdhersteller", eol="",
        note="Befehle ohne Zeilenende, schnell hintereinander tippen ist nicht nötig – Befehl komplett senden.")


def _hm10() -> ModuleDef:
    return ModuleDef("hm10", "HM-10 / HM-19 / CC2541", "Bluetooth LE", "at", 9600, _cmds({
        "Grundlagen": [
            ("AT", "Test – Antwort OK (trennt eine bestehende Verbindung)"),
            ("AT+VERR?", "Firmware-Version"),
            ("AT+RESET", "Neustart"),
            ("AT+RENEW", "Werkseinstellungen"),
            ("AT+ADDR?", "Eigene MAC-Adresse"),
            ("AT+NAME?", "Gerätename"),
            ("AT+NAMEHMSoft", "Gerätename setzen"),
        ],
        "Funk": [
            ("AT+ROLE?", "0 = Peripheral, 1 = Central"),
            ("AT+ROLE1", "Als Central betreiben"),
            ("AT+IMME1", "Nach Neustart auf Befehle warten (für Central-Betrieb)"),
            ("AT+DISC?", "Geräte suchen (Central)"),
            ("AT+CON001122334455", "Mit MAC-Adresse verbinden (Central)"),
            ("AT+POWE?", "Sendeleistung 0–3"),
            ("AT+ADVI?", "Werbeintervall"),
            ("AT+UUID?", "Service-UUID"),
            ("AT+CHAR?", "Characteristic-UUID"),
        ],
        "Sicherheit / UART": [
            ("AT+TYPE?", "0 = ohne PIN, 2 = mit PIN"),
            ("AT+PASS?", "PIN abfragen"),
            ("AT+BAUD?", "Baudrate: 0=9600 1=19200 2=38400 3=57600 4=115200"),
            ("AT+NOTI1", "Verbindungsmeldungen (OK+CONN / OK+LOST) ausgeben"),
        ],
    }, danger=("AT+RENEW",)), vendor="Fremdhersteller", eol="",
        note="Befehle ohne Zeilenende. Antworten beginnen mit OK+…")


# ---------------------------------------------------------------------------
# WLAN: ESP8266 / ESP-12 / ESP32 (ESP-AT)
# ---------------------------------------------------------------------------

ESP_WIFI = {
    "Grundlagen": [
        ("AT", "Test – Antwort OK"),
        ("AT+GMR", "AT-, SDK- und Firmware-Version"),
        ("AT+RST", "Neustart"),
        ("AT+RESTORE", "Werkseinstellungen"),
        ("ATE0", "Echo aus"),
        ("AT+UART_CUR?", "Aktuelle UART-Einstellung"),
        ("AT+UART_DEF=115200,8,1,0,0", "UART dauerhaft: Baud, Daten, Stopp, Parität, Fluss"),
        ("AT+SYSRAM?", "Freier Arbeitsspeicher"),
        ("AT+GSLP=10000", "Tiefschlaf für x ms (GPIO16 mit RST verbinden)"),
        ("AT+SLEEP=1", "Leichtschlaf (Modem-Sleep)"),
    ],
    "WLAN": [
        ("AT+CWMODE?", "Modus: 1 = Station, 2 = Access Point, 3 = beides"),
        ("AT+CWMODE=1", "Als Station (Client) betreiben"),
        ("AT+CWLAP", "WLAN-Netze suchen"),
        ("AT+CWJAP=\"SSID\",\"PASSWORT\"", "Mit WLAN verbinden"),
        ("AT+CWJAP?", "Aktuelles WLAN"),
        ("AT+CWQAP", "WLAN trennen"),
        ("AT+CWSAP=\"ESP-AP\",\"12345678\",5,3", "Eigenen Access Point: SSID, Passwort, Kanal, Verschlüsselung"),
        ("AT+CWLIF", "Am eigenen AP verbundene Geräte"),
        ("AT+CWDHCP?", "DHCP-Status"),
        ("AT+CWAUTOCONN=1", "Beim Start automatisch verbinden"),
        ("AT+CIPSTAMAC?", "MAC-Adresse der Station"),
    ],
    "TCP/IP": [
        ("AT+CIFSR", "Eigene IP- und MAC-Adressen"),
        ("AT+CIPSTA?", "IP, Gateway, Netzmaske der Station"),
        ("AT+CIPMUX=1", "Mehrere Verbindungen erlauben (nötig für Server)"),
        ("AT+CIPSTART=\"TCP\",\"192.168.1.10\",8000", "TCP-Verbindung aufbauen"),
        ("AT+CIPSTART=\"UDP\",\"192.168.1.10\",8000", "UDP-Verbindung"),
        ("AT+CIPSEND=5", "5 Bytes senden – nach »>« die Daten eingeben"),
        ("AT+CIPCLOSE", "Verbindung schließen"),
        ("AT+CIPSTATUS", "Verbindungsstatus"),
        ("AT+CIPSERVER=1,80", "TCP-Server auf Port 80 starten (CIPMUX=1 nötig)"),
        ("AT+CIPMODE=1", "Transparenter Durchreichmodus (nur eine Verbindung)"),
        ("AT+PING=\"8.8.8.8\"", "Ping"),
        ("AT+CIPDOMAIN=\"example.com\"", "DNS-Auflösung"),
        ("AT+CIPSNTPCFG=1,1,\"pool.ntp.org\"", "Zeitserver einstellen (Zeitzone +1)"),
        ("AT+CIPSNTPTIME?", "Uhrzeit vom Zeitserver"),
    ],
}

ESP32_EXTRA = {
    "MQTT": [
        ("AT+MQTTUSERCFG=0,1,\"esp32\",\"\",\"\",0,0,\"\"", "MQTT-Client einrichten (Client-ID esp32)"),
        ("AT+MQTTCONN=0,\"192.168.1.10\",1883,1", "Mit Broker verbinden"),
        ("AT+MQTTPUB=0,\"test/topic\",\"Hallo\",0,0", "Nachricht veröffentlichen"),
        ("AT+MQTTSUB=0,\"test/#\",0", "Topic abonnieren"),
        ("AT+MQTTUNSUB=0,\"test/#\"", "Abo beenden"),
        ("AT+MQTTCLEAN=0", "MQTT-Verbindung beenden"),
    ],
    "HTTP": [
        ("AT+HTTPCLIENT=2,0,\"http://example.com\",,,1", "HTTP-GET"),
        ("AT+HTTPGETSIZE=\"http://example.com\"", "Größe einer Ressource"),
    ],
    "Bluetooth LE": [
        ("AT+BLEINIT=2", "BLE als Server (1 = Client, 0 = aus)"),
        ("AT+BLEADDR?", "BLE-Adresse"),
        ("AT+BLENAME=\"ESP32-AT\"", "BLE-Name"),
        ("AT+BLEADVDATAEX=\"ESP32-AT\",\"A002\",\"0102030405\",1", "Werbedaten automatisch erzeugen"),
        ("AT+BLEADVSTART", "Werbung starten"),
        ("AT+BLEADVSTOP", "Werbung stoppen"),
        ("AT+BLESCAN=1,3", "3 s nach Geräten suchen (Client)"),
        ("AT+BLECONN=0,\"24:0a:c4:00:00:01\"", "Mit Gerät verbinden"),
        ("AT+BLEDISCONN=0", "Trennen"),
        ("AT+BLESPPCFG=1,1,7,1,5", "BLE-UART (SPP) konfigurieren"),
        ("AT+BLESPP", "BLE-UART-Durchreichmodus starten"),
    ],
}


def _esp8266() -> ModuleDef:
    return ModuleDef("esp8266", "ESP8266 / ESP-12 / ESP-01", "WLAN (ESP-AT)", "at", 115200,
                     _cmds(ESP_WIFI, danger=("AT+RESTORE",)), vendor="Fremdhersteller",
                     note="ESP-AT-Firmware. Ältere Module: 9600 oder 57600 Baud. Befehle mit CR LF.")


def _esp32() -> ModuleDef:
    g = {k: list(v) for k, v in ESP_WIFI.items()}
    g.update(ESP32_EXTRA)
    return ModuleDef("esp32", "ESP32 / ESP32-C3 / -S3 (ESP-AT)", "WLAN + Bluetooth LE", "at", 115200,
                     _cmds(g, danger=("AT+RESTORE",)), vendor="Fremdhersteller",
                     note="ESP-AT-Firmware nötig. Beim ESP32 liegt der AT-UART oft an GPIO16/17, nicht am USB-Port.")


# ---------------------------------------------------------------------------
# Mobilfunk
# ---------------------------------------------------------------------------

def _sim800() -> ModuleDef:
    return ModuleDef("sim800", "SIMCom SIM800 / SIM900 / A6", "GSM / GPRS (2G)", "at", 115200, _cmds(_gsm({
        "Grundlagen": [
            ("AT+CBC", "Versorgungsspannung in mV"),
            ("AT+IPR=115200", "Feste Baudrate (0 = automatisch)"),
            ("AT+CSCLK=0", "Schlafmodus aus"),
            ("AT+CNETLIGHT=1", "Netz-LED ein"),
        ],
        "GPRS/TCP": [
            ("AT+CIPSHUT", "Alle IP-Verbindungen beenden"),
            ("AT+CSTT=\"internet\"", "APN setzen"),
            ("AT+CIICR", "Datenverbindung aufbauen"),
            ("AT+CIFSR", "Eigene IP-Adresse"),
            ("AT+CIPSTART=\"TCP\",\"example.com\",80", "TCP-Verbindung"),
            ("AT+CIPSEND", "Daten senden – Text eingeben, mit Strg+Z (\\x1A) abschließen"),
            ("AT+CIPCLOSE", "Verbindung schließen"),
            ("AT+CIPSTATUS", "Verbindungsstatus"),
        ],
        "HTTP": [
            ("AT+SAPBR=3,1,\"APN\",\"internet\"", "APN für HTTP"),
            ("AT+SAPBR=1,1", "Bearer öffnen"),
            ("AT+HTTPINIT", "HTTP starten"),
            ("AT+HTTPPARA=\"URL\",\"http://example.com\"", "Adresse setzen"),
            ("AT+HTTPACTION=0", "GET ausführen – Ergebnis kommt als +HTTPACTION"),
            ("AT+HTTPREAD", "Antwort lesen"),
            ("AT+HTTPTERM", "HTTP beenden"),
        ],
    }), danger=("AT+CMGD",)), vendor="Mobilfunk-Modems",
        note="Automatische Baudrate: zuerst »AT« senden. Versorgung muss 2 A Spitzen liefern. "
             "2G-Netze werden in vielen Ländern abgeschaltet.")


def _sim7600() -> ModuleDef:
    return ModuleDef("sim7600", "SIMCom SIM7600 / A7670 / SIM7080", "LTE Cat-1/4, LTE-M, NB-IoT", "at", 115200, _cmds(_gsm({
        "Netz": [
            ("AT+CPSI?", "Ausführliche Zellinfo: Technik, Band, Zelle, Signal"),
            ("AT+CNMP?", "Bevorzugte Netztechnik"),
            ("AT+CNMP=2", "Netztechnik automatisch"),
        ],
        "TCP/IP": [
            ("AT+NETOPEN", "IP-Dienst öffnen"),
            ("AT+IPADDR", "Eigene IP-Adresse"),
            ("AT+CIPOPEN=0,\"TCP\",\"example.com\",80", "TCP-Verbindung auf Kanal 0"),
            ("AT+CIPSEND=0,5", "5 Bytes auf Kanal 0 senden – nach »>« Daten eingeben"),
            ("AT+CIPCLOSE=0", "Kanal 0 schließen"),
            ("AT+NETCLOSE", "IP-Dienst schließen"),
        ],
        "HTTP": [
            ("AT+HTTPINIT", "HTTP starten"),
            ("AT+HTTPPARA=\"URL\",\"http://example.com\"", "Adresse setzen"),
            ("AT+HTTPACTION=0", "GET ausführen"),
            ("AT+HTTPREAD=0,500", "500 Bytes der Antwort lesen"),
            ("AT+HTTPTERM", "HTTP beenden"),
        ],
        "MQTT": [
            ("AT+CMQTTSTART", "MQTT-Dienst starten"),
            ("AT+CMQTTACCQ=0,\"client01\"", "Client anlegen"),
            ("AT+CMQTTCONNECT=0,\"tcp://broker.example.com:1883\",60,1", "Mit Broker verbinden"),
            ("AT+CMQTTDISC=0,120", "Trennen"),
            ("AT+CMQTTSTOP", "MQTT-Dienst beenden"),
        ],
        "GNSS": [
            ("AT+CGPS=1", "GPS einschalten"),
            ("AT+CGPSINFO", "Position abfragen"),
            ("AT+CGPS=0", "GPS ausschalten"),
        ],
    }), danger=("AT+CMGD",)), vendor="Mobilfunk-Modems",
        note="Befehle mit CR LF. Über USB meldet das Modem mehrere COM-Ports – den »AT Port« wählen.")


def _quectel_lte() -> ModuleDef:
    return ModuleDef("quectel_lte", "Quectel EC2x / EG9x / BG9x", "LTE, LTE-M, NB-IoT", "at", 115200, _cmds(_gsm({
        "Grundlagen": [
            ("AT+QPOWD=1", "Modem geordnet ausschalten"),
            ("AT+QCCID", "SIM-Kartennummer"),
            ("AT+QTEMP", "Temperaturen"),
        ],
        "Netz": [
            ("AT+QNWINFO", "Netztechnik, Betreiber, Band, Kanal"),
            ("AT+QCSQ", "Signal je Technik (RSSI, RSRP, SINR, RSRQ)"),
            ("AT+QENG=\"servingcell\"", "Details der aktuellen Zelle"),
            ("AT+QCFG=\"nwscanmode\",0", "Netztechnik automatisch (BG9x: mit iotopmode kombinieren)"),
            ("AT+QCFG=\"iotopmode\",2", "BG9x: LTE-M und NB-IoT erlauben"),
        ],
        "TCP/IP": [
            ("AT+QICSGP=1,1,\"internet\",\"\",\"\",1", "Datenkontext 1 mit APN konfigurieren"),
            ("AT+QIACT=1", "Datenkontext aktivieren"),
            ("AT+QIACT?", "Aktive Kontexte und IP-Adresse"),
            ("AT+QIOPEN=1,0,\"TCP\",\"example.com\",80,0,0", "TCP-Verbindung auf Kanal 0"),
            ("AT+QISEND=0,5", "5 Bytes senden – nach »>« Daten eingeben"),
            ("AT+QIRD=0,1500", "Empfangene Daten lesen"),
            ("AT+QICLOSE=0", "Kanal schließen"),
            ("AT+QPING=1,\"8.8.8.8\"", "Ping"),
            ("AT+QIDEACT=1", "Datenkontext beenden"),
        ],
        "HTTP": [
            ("AT+QHTTPCFG=\"contextid\",1", "Datenkontext für HTTP"),
            ("AT+QHTTPURL=18,80", "URL-Länge ankündigen – danach URL senden"),
            ("AT+QHTTPGET=80", "GET ausführen"),
            ("AT+QHTTPREAD=80", "Antwort lesen"),
        ],
        "MQTT": [
            ("AT+QMTOPEN=0,\"broker.example.com\",1883", "Netzwerkverbindung zum Broker"),
            ("AT+QMTCONN=0,\"client01\"", "MQTT-Anmeldung"),
            ("AT+QMTSUB=0,1,\"test/#\",0", "Topic abonnieren"),
            ("AT+QMTPUBEX=0,0,0,0,\"test/topic\",5", "5 Bytes veröffentlichen – nach »>« Daten eingeben"),
            ("AT+QMTDISC=0", "Trennen"),
        ],
        "GNSS": [
            ("AT+QGPS=1", "GNSS einschalten"),
            ("AT+QGPSLOC=2", "Position (Dezimalgrad)"),
            ("AT+QGPSEND", "GNSS ausschalten"),
        ],
    }), danger=("AT+CMGD",)), vendor="Mobilfunk-Modems",
        note="Über USB mehrere COM-Ports – den »AT Port« (oft »Quectel USB AT Port«) wählen.")


def _quectel_5g() -> ModuleDef:
    return ModuleDef("quectel_5g", "Quectel RM500Q / RM520N / RG50x", "5G NR (SA/NSA) + LTE", "at", 115200, _cmds(_gsm({
        "5G / Netz": [
            ("AT+QENG=\"servingcell\"", "Aktuelle Zelle: Technik (NR5G-SA/NSA, LTE), Band, Signalwerte"),
            ("AT+QNWINFO", "Netztechnik und Band"),
            ("AT+QCAINFO", "Trägerbündelung (Carrier Aggregation)"),
            ("AT+QRSRP", "Empfangsleistung je Antenne"),
            ("AT+QNWPREFCFG=\"mode_pref\"", "Erlaubte Techniken abfragen"),
            ("AT+QNWPREFCFG=\"mode_pref\",AUTO", "Alle Techniken erlauben"),
            ("AT+QNWPREFCFG=\"mode_pref\",NR5G", "Nur 5G"),
            ("AT+QNWPREFCFG=\"nr5g_band\"", "Erlaubte 5G-Bänder"),
            ("AT+QNWPREFCFG=\"nr5g_disable_mode\"", "SA/NSA-Sperren abfragen"),
            ("AT+QSCAN=3,1", "Umgebung nach LTE- und 5G-Zellen scannen (dauert)"),
        ],
        "System": [
            ("AT+QTEMP", "Temperaturen"),
            ("AT+QCFG=\"usbnet\"", "USB-Netzwerkmodus (0 RmNet, 1 ECM, 2 MBIM, 3 RNDIS)"),
            ("AT+QNETDEVCTL?", "Datenverbindung über USB-Netzwerk"),
            ("AT+QPOWD=1", "Modem geordnet ausschalten"),
        ],
    }), danger=("AT+CMGD",)), vendor="Mobilfunk-Modems",
        note="Daten laufen meist über USB-Netzwerk; der COM-Port dient der Steuerung (»AT Port« wählen).")


def _ublox() -> ModuleDef:
    return ModuleDef("ublox_sara", "u-blox SARA-R4 / R5 / LARA", "LTE-M, NB-IoT, LTE", "at", 115200, _cmds(_gsm({
        "Netz": [
            ("AT+URAT?", "Erlaubte Funktechniken"),
            ("AT+UMNOPROF?", "Netzbetreiber-Profil"),
            ("AT+UMNOPROF=100", "Profil »Europa« (danach Neustart mit AT+CFUN=15)"),
            ("AT+CESQ", "Erweiterte Signalwerte (RSRP, RSRQ)"),
            ("AT+UCGED?", "Zelleninformation"),
            ("AT+CFUN=15", "Modem neu starten"),
        ],
        "Sockets": [
            ("AT+USOCR=6", "TCP-Socket anlegen (17 = UDP)"),
            ("AT+USOCO=0,\"example.com\",80", "Socket 0 verbinden"),
            ("AT+USOWR=0,5,\"Hallo\"", "5 Bytes senden"),
            ("AT+USORD=0,100", "Bis zu 100 Bytes lesen"),
            ("AT+USOCL=0", "Socket schließen"),
            ("AT+UPING=\"8.8.8.8\"", "Ping"),
            ("AT+UDNSRN=0,\"example.com\"", "DNS-Auflösung"),
        ],
    }), danger=("AT+CMGD",)), vendor="Mobilfunk-Modems")


def _nrf91() -> ModuleDef:
    return ModuleDef("nrf91", "Nordic nRF9160 / nRF9151 (SLM)", "LTE-M, NB-IoT + GNSS", "at", 115200, _cmds(_gsm({
        "Netz": [
            ("AT%XSYSTEMMODE?", "Erlaubte Techniken (LTE-M, NB-IoT, GNSS)"),
            ("AT%XSYSTEMMODE=1,1,1,0", "LTE-M, NB-IoT und GNSS erlauben"),
            ("AT%XMONITOR", "Netzwerkstatus kompakt"),
            ("AT%XICCID", "SIM-Kartennummer"),
            ("AT%XTEMP?", "Temperatur"),
            ("AT%CONEVAL", "Verbindungsqualität bewerten"),
        ],
        "Sockets (Serial LTE Modem)": [
            ("AT#XSOCKET=1,1,0", "TCP-Socket öffnen"),
            ("AT#XCONNECT=\"example.com\",80", "Verbinden"),
            ("AT#XSEND=\"Hallo\"", "Daten senden"),
            ("AT#XRECV=10", "Empfangen mit 10 s Timeout"),
            ("AT#XSOCKET=0", "Socket schließen"),
            ("AT#XPING=\"8.8.8.8\",45,5000", "Ping"),
        ],
        "GNSS": [
            ("AT#XGPS=1,0,0,0", "GNSS starten (Einzelposition)"),
            ("AT#XGPS=0", "GNSS stoppen"),
        ],
    }), danger=("AT+CMGD",)), vendor="Mobilfunk-Modems",
        note="#X…-Befehle nur mit der Serial-LTE-Modem-Anwendung (SLM).")


def _gsm_generic() -> ModuleDef:
    return ModuleDef("modem_generic", "Mobilfunk-Modem allgemein (3GPP)", "GSM / LTE / 5G", "at", 115200,
                     _cmds(GSM_BASIS, danger=("AT+CMGD",)), vendor="Mobilfunk-Modems",
                     note="Standardbefehle nach 3GPP – funktionieren bei praktisch jedem GSM-, LTE- und 5G-Modem.")


EXTRA_MODULES: list[ModuleDef] = [
    _hc12(), _hc05(), _hc06(), _hm10(), _esp8266(), _esp32(),
    _sim800(), _sim7600(), _quectel_lte(), _quectel_5g(), _ublox(), _nrf91(), _gsm_generic(),
]
