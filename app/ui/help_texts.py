"""Erklärtexte für die Seiten und Funktionen (aufklappbare Hilfe)."""

HELP = {
    "scan": (
        "Geräte-Suche über Bluetooth LE",
        [
            ("Was passiert hier?", "Der Bluetooth-Adapter des PCs sucht nach Geräten, die sich per Bluetooth LE "
             "bemerkbar machen (Advertising). Proteus-, Setebos- und Skoll-Module werden am SPP-Profil erkannt."),
            ("Scan starten", "Startet die Suche. Gefundene Geräte erscheinen sofort in der Liste; der Balken zeigt "
             "die Signalstärke (RSSI). Geräte, die länger nicht mehr gesehen wurden, werden grau."),
            ("Filter", "Name/Adresse durchsucht die Liste. »min. RSSI« blendet schwache Geräte aus. "
             "»Nur SPP-Profil« zeigt nur Würth-Module mit Datenkanal, »0x031A« nur Geräte mit Würth-Kennung."),
            ("Verbinden", "Doppelklick oder »Verbinden« öffnet die Modulauswahl. Der Modultyp legt Header-Bytes, "
             "Paketgröße und GPIO-Funktionen fest. Klappt der erste Versuch nicht, sucht das Programm das Gerät "
             "neu und versucht es bis zu dreimal; »Abbrechen« beendet den Versuch."),
            ("Übersicht", "»Nur mit Namen« blendet namenlose Geräte (Handys, Beacons) aus. Ein ausgewähltes Gerät "
             "bleibt fest an seiner Position, damit es sich sicher anklicken lässt."),
            ("Mit Adresse verbinden", "Ist die MAC-Adresse bekannt (z. B. vom Aufkleber oder aus dem UART-Terminal), "
             "kann direkt verbunden werden – auch wenn das Modul in der Liste nicht auftaucht."),
        ],
    ),
    "terminal": (
        "Daten mit dem verbundenen Bluetooth-Modul austauschen",
        [
            ("Protokoll", "Zeigt gesendete (▲) und empfangene (▼) Daten mit Zeitstempel. Über die Kästchen lassen "
             "sich Info-Meldungen, Daten und Fernbefehle ein- und ausblenden."),
            ("Anzeige", "HEX zeigt jedes Byte als Zahl, ASCII als Text, »druckbar« ersetzt Steuerzeichen durch Punkte."),
            ("Senden", "Daten als HEX (z. B. 48 61 6C 6C 6F) oder Text eingeben. Das Header-Byte 0x01 fügt das "
             "Programm bei Proteus/Setebos automatisch hinzu."),
            ("Mehrfach / Zufallsdaten", "Für Reichweiten- und Durchsatztests: Pakete mehrfach im Abstand senden "
             "oder zufällige Daten fester Länge erzeugen."),
            ("Makros", "Häufig benutzte Daten als Knopf speichern und mit einem Klick senden."),
            ("MTU", "Größte Paketgröße der Verbindung. Daraus ergibt sich die maximale Nutzdatenlänge pro Paket."),
        ],
    ),
    "gpio": (
        "Pins des Bluetooth-Moduls fernsteuern",
        [
            ("Funktion", "Jeder freigegebene Pin kann Eingang (mit Pull-Up/-Down), Ausgang (mit Startpegel) oder "
             "PWM (Periode und Tastgrad) sein."),
            ("Konfiguration schreiben", "Überträgt die gewählten Funktionen an das Modul. Erst danach lassen sich "
             "Ausgänge umschalten und PWM-Werte ändern."),
            ("Werte lesen", "Fragt die aktuellen Pegel ab; »Zyklisch lesen« wiederholt das automatisch."),
            ("Voraussetzung", "Die Pins müssen im Modul für den Fernzugriff freigegeben sein (Remote-GPIO)."),
        ],
    ),
    "uart": (
        "Funkmodule über den COM-Port bedienen (Befehlsschnittstelle)",
        [
            ("① Port wählen", "Board oder USB-Stick einstecken – der Port erscheint automatisch. Angezeigt wird "
             "auch der USB-Seriell-Chip (FTDI, CP210x, CH340, PL2303, CDC …)."),
            ("② Modul wählen", "Bestimmt Befehlsliste, Frame-Format und Standard-Baudrate. Die Liste ist nach "
             "Würth-Modulen, Fremdmodulen (HC-12, HC-05, HM-10, ESP8266/ESP32) und Mobilfunk-Modems (SIM800, "
             "SIM7600, Quectel, u-blox, nRF91, 5G) sortiert. »Erkennen« probiert alles automatisch durch."),
            ("③ Verbinden", "Öffnet den Port. DTR/RTS werden vorher gesetzt – auf vielen Boards hängt daran der "
             "Reset des Moduls. »Reset-Impuls« startet das Modul über diese Leitung neu."),
            ("Befehle", "Gruppe wählen, Kachel anklicken, Parameter ausfüllen, »Senden«. Rote Kacheln setzen das "
             "Modul zurück und fragen vorher nach. Doppelklick sendet sofort."),
            ("Frame-Aufbau", "Die farbigen Kästchen zeigen, was gesendet wird: Startbyte, Befehl, Länge, Daten "
             "und Prüfsumme. Länge und Prüfsumme berechnet das Programm selbst."),
            ("Protokoll", "Jede Zeile ist ein Frame: REQ = Anfrage vom PC, CNF = Bestätigung, IND = Meldung des "
             "Moduls (z. B. empfangene Funkdaten), RSP = Antwort (z. B. Senden abgeschlossen). Zeile anklicken "
             "zeigt die Zerlegung des Frames."),
            ("Freie Eingabe", "»Frame« baut aus Befehl + Daten automatisch einen gültigen Frame. »HEX roh« sendet "
             "Bytes unverändert, »Text« z. B. AT-Befehle. »Strg+Z« schließt SMS- oder Datentext nach »>« ab, "
             "»Esc« bricht ihn ab."),
            ("Zeilenende", "Die meisten AT-Geräte erwarten CR LF. HC-12, HC-06 und HM-10 erwarten Befehle ohne "
             "Zeilenende – das Programm wählt das passend zum Modul."),
            ("Transparenter Modus", "Für Module ohne Befehlsmodus: alle Daten werden unverändert weitergereicht "
             "und als Text/HEX angezeigt."),
        ],
    ),
    "recipes": (
        "Fertige Abläufe für das gewählte Modul",
        [
            ("Was ist ein Ablauf?", "Eine Folge von Befehlen für eine typische Aufgabe – z. B. Initialisierung nach "
             "dem Start, SMS senden, Anruf, WLAN verbinden, Daten per Funk senden. Jeder Schritt ist erklärt."),
            ("Parameter", "Werte wie Rufnummer, APN, WLAN-Name, Kanal oder Adresse oben eintragen – sie werden in "
             "die Befehle eingesetzt (Spalte »Befehl«) und für das nächste Mal gespeichert."),
            ("Ausführen", "»Ablauf starten« sendet Schritt für Schritt und wartet jeweils auf die erwartete Antwort "
             "(z. B. OK, »>« oder eine Bestätigung des Moduls). Der Status zeigt OK, Fehler oder »keine Antwort«."),
            ("Einzelne Schritte", "Schritt in der Tabelle anklicken: »Nur Auswahl« sendet nur diesen, »Ab Auswahl« "
             "macht ab dort weiter. Die Antwort des Moduls steht unter der Tabelle."),
            ("Hinweise", "Grüne Schritte verlangen eine Handlung am Gerät (z. B. SET-Pin auf GND) und warten auf "
             "Bestätigung. Optionale Schritte brechen den Ablauf nie ab."),
            ("Voraussetzung", "Modul und COM-Port werden im UART-Terminal gewählt und verbunden; alle Befehle "
             "und Antworten erscheinen dort zusätzlich im Protokoll."),
        ],
    ),
    "uart_settings": (
        "Nutzereinstellungen des Moduls (UART)",
        [
            ("Alle lesen", "Fragt jede Einstellung einzeln per GET-Befehl ab. Rot = vom Modul abgelehnt "
             "(z. B. bei dieser Firmware nicht vorhanden)."),
            ("Schreiben", "Zeile doppelklicken, Wert eingeben. Das Programm prüft den Wertebereich, schreibt per "
             "SET-Befehl und liest den Wert zur Kontrolle zurück."),
            ("Neustart", "Viele Einstellungen (Baudrate, Kanal, Name) gelten erst nach einem Neustart des Moduls."),
            ("Achtung", "Eine geänderte UART-Baudrate trennt die Verbindung – danach mit der neuen Baudrate öffnen."),
        ],
    ),
    "settings": (
        "Programm-Einstellungen",
        [
            ("Schreibart", "»Ohne Antwort« ist schneller, »mit Antwort« gesichert. »Automatisch« nimmt, was das "
             "Modul anbietet."),
            ("Profil-UUIDs", "Nur nötig, wenn ein Modul mit geänderten Service-UUIDs betrieben wird."),
        ],
    ),
}

FRAME_PARTS = {
    "STX": "Startbyte – markiert den Beginn eines Frames (0x02, bei Metis 0xFF)",
    "CMD": "Befehlscode – Bit 6/7 geben den Typ an: Anfrage, Bestätigung, Meldung, Antwort",
    "LEN": "Anzahl der Datenbytes (LSB zuerst)",
    "DATA": "Nutzdaten / Parameter des Befehls",
    "CS": "Prüfsumme – XOR aller vorherigen Bytes",
    "TEXT": "Text / AT-Befehl",
}

PARAM_HELP = {
    "u8": "Zahl 0…255 (dezimal oder 0x…)",
    "i8": "Zahl -128…127, z. B. Sendeleistung in dBm",
    "u16": "Zahl 0…65535, wird als 2 Bytes (LSB zuerst) gesendet",
    "u32": "Zahl, wird als 4 Bytes (LSB zuerst) gesendet – z. B. Thyone-Adresse",
    "hex": "Bytes in HEX, z. B. 01 A0 FF",
    "data": "Nutzdaten in HEX, z. B. 48 61 6C 6C 6F = »Hallo«",
    "mac": "6 Bytes HEX, LSB zuerst (umgekehrte Reihenfolge der angezeigten MAC)",
    "ascii": "Text",
    "choice": "Auswahl",
}

TYPE_HELP = {
    "REQ": "Anfrage vom PC an das Modul",
    "CNF": "Bestätigung des Moduls auf eine Anfrage (erstes Datenbyte = Status, 00 = OK)",
    "IND": "Meldung des Moduls ohne Anfrage, z. B. empfangene Funkdaten",
    "RSP": "Antwort/Abschluss, z. B. Funkübertragung beendet",
    "RAW": "Rohdaten ohne Frame",
    "TEXT": "Textzeile (AT-Befehl oder Antwort)",
}
