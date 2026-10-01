"""Textnormalisierung fuer deutsche Sprachausgabe.

Das, was kommerzielle Dienste vor dem Modell verstecken: Zahlen ausschreiben,
Abkuerzungen aufloesen, Einheiten und Akronyme sprechbar machen.

    python normalisieren.py "Die RTX 5080 hat 16 GB VRAM."
"""

import re
import sys

from num2words import num2words

# --- Abkuerzungen ----------------------------------------------------------
# Laengere zuerst, damit "z. B." vor "z." greift.
ABKUERZUNGEN = {
    r"\bz\.\s*B\.": "zum Beispiel",
    r"\bu\.\s*a\.": "unter anderem",
    r"\bd\.\s*h\.": "das heißt",
    r"\bbzw\.": "beziehungsweise",
    r"\busw\.": "und so weiter",
    r"\betc\.": "et cetera",
    r"\bca\.": "circa",
    r"\bevtl\.": "eventuell",
    r"\bggf\.": "gegebenenfalls",
    r"\binkl\.": "inklusive",
    r"\bexkl\.": "exklusive",
    r"\bmax\.": "maximal",
    r"\bmin\.": "minimal",
    r"\bNr\.": "Nummer",
    r"\bS\.": "Seite",
    r"\bvgl\.": "vergleiche",
    r"\bzzgl\.": "zuzüglich",
}

# --- Einheiten -------------------------------------------------------------
EINHEITEN = {
    "GB": "Gigabyte", "MB": "Megabyte", "TB": "Terabyte", "KB": "Kilobyte",
    "GHz": "Gigahertz", "MHz": "Megahertz", "kHz": "Kilohertz",
    "ms": "Millisekunden", "kg": "Kilogramm", "km": "Kilometer",
    "cm": "Zentimeter", "mm": "Millimeter", "W": "Watt", "V": "Volt",
}

# --- Anglizismen ------------------------------------------------------------
# Ein deutsches Modell kann englische Schreibweisen nicht aussprechen. Hier
# steht die deutsche Lautschrift. Liste waechst, wenn etwas falsch klingt.
# Keine Bindestriche! Das Modell liest sie als Pause und betont danach falsch.
ANGLIZISMEN = {
    "iPhone": "Eifohn",
    "iPad": "Eipäd",
    "Jetson": "Dschettsen",
    "Firewall": "Feierwoll",
    "Desktop": "Desktopp",
    "Laptop": "Läpptopp",
    "Browser": "Brauser",
    "Router": "Ruhter",
    "Server": "Söhrwer",
    "Update": "Appdeht",
    "Upload": "Applohd",
    "Download": "Daunlohd",
    "Cache": "Käsch",
    "Chatterbox": "Tschätterbox",
    "Python": "Peithonn",
    "Tailscale": "Teilskeil",
    "Raspberry": "Rahsberri",
    "Cloud": "Klaud",
    "Feature": "Fietscher",
    "Backup": "Bäckapp",
    "Home Assistant": "Hohm Assistent",
    "Homeassistant": "Hohm Assistent",
    "Whisper": "Wissper",
    "Prompt": "Prommt",
    "Streaming": "Strieming",
    "Workflow": "Wörkflau",
    "Token": "Tohken",
}

# --- Akronyme, die als WORT gesprochen werden -------------------------------
# Diese zuerst, sonst buchstabiert der naechste Schritt sie faelschlich.
ALS_WORT = {
    "VRAM": "Wieh-Ramm",
    "RAM": "Ramm",
    "WLAN": "Weh-Lahn",
    "NASA": "Nasa",
    "LAN": "Lahn",
    "GIF": "Gif",
}

# --- Akronyme, die buchstabiert gehoeren -----------------------------------
# Ohne das liest das Modell "RTX" als Wort statt "Err Teh Iks".
BUCHSTABIEREN = {
    "RTX", "GTX", "CPU", "GPU", "SSD", "HDD", "USB",
    "API", "URL", "HTML", "CSS", "SQL", "PDF", "KI", "PC", "TTS", "ASR",
    "LED", "USA", "EU", "DVD", "HDMI", "IP", "ID",
}

# Deutsche Aussprache der Buchstaben, wo sie vom Namen abweicht.
BUCHSTABEN = {
    "A": "Ah", "B": "Beh", "C": "Zeh", "D": "Deh", "E": "Eh", "F": "Eff",
    "G": "Geh", "H": "Hah", "I": "Ih", "J": "Jott", "K": "Kah", "L": "Ell",
    "M": "Emm", "N": "Enn", "O": "Oh", "P": "Peh", "Q": "Kuh", "R": "Err",
    "S": "Ess", "T": "Teh", "U": "Uh", "V": "Fau", "W": "Weh", "X": "Iks",
    "Y": "Üpsilon", "Z": "Tsett",
}


def _zahl(treffer: re.Match) -> str:
    roh = treffer.group(0)
    # Deutsches Format: Punkt trennt Tausender, Komma ist das Dezimalzeichen.
    sauber = roh.replace(".", "").replace(",", ".")
    try:
        wert = float(sauber)
    except ValueError:
        return roh
    if wert.is_integer():
        return num2words(int(wert), lang="de")
    ganz, rest = sauber.split(".")
    return (num2words(int(ganz), lang="de") + " Komma "
            + " ".join(num2words(int(z), lang="de") for z in rest))


def normalisieren(text: str) -> str:
    # 1. Abkuerzungen
    for muster, ersatz in ABKUERZUNGEN.items():
        text = re.sub(muster, ersatz, text)

    # 2. Einheiten (nur als eigenstaendiges Wort)
    for kurz, lang in EINHEITEN.items():
        text = re.sub(rf"\b{re.escape(kurz)}\b", lang, text)

    # 2b. Anglizismen deutsch schreiben (vor den Akronymen, da teils Mischform)
    for wort, lautschrift in sorted(ANGLIZISMEN.items(), key=lambda p: -len(p[0])):
        text = re.sub(rf"\b{re.escape(wort)}\b", lautschrift, text,
                      flags=re.IGNORECASE)

    # 3a. Akronyme, die als Wort gesprochen werden (vor dem Buchstabieren!)
    for akronym, gesprochen in sorted(ALS_WORT.items(), key=lambda p: -len(p[0])):
        text = re.sub(rf"\b{akronym}\b", gesprochen, text)

    # 3b. Akronyme buchstabieren
    for akronym in sorted(BUCHSTABIEREN, key=len, reverse=True):
        gesprochen = " ".join(BUCHSTABEN.get(b, b) for b in akronym)
        text = re.sub(rf"\b{akronym}\b", gesprochen, text)

    # 4. Waehrung: 1.200 € -> ... Euro
    text = re.sub(r"€", " Euro", text)
    text = re.sub(r"\$", " Dollar", text)
    text = re.sub(r"%", " Prozent", text)

    # 5. Zahlen zuletzt, damit Einheiten und Akronyme schon weg sind
    text = re.sub(r"\d+(?:\.\d{3})*(?:,\d+)?", _zahl, text)

    # 6. Mehrfache Leerzeichen
    return re.sub(r"\s{2,}", " ", text).strip()


if __name__ == "__main__":
    proben = sys.argv[1:] or [
        "Die RTX 5080 hat 16 GB VRAM und kostet ungefähr 1.200 Euro. "
        "Das Modell läuft z. B. lokal mit Chatterbox.",
        "Der Prozessor läuft mit 4,7 GHz und braucht ca. 125 W.",
        "Die SSD ist zu 87 % voll, d. h. noch 240 GB frei.",
    ]
    for p in proben:
        print("vorher :", p)
        print("nachher:", normalisieren(p))
        print()
