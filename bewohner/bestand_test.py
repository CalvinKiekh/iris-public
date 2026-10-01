"""Probe fuer bestand.py - aus vielen Funden eine Erkenntnis.

    python -X utf8 bestand_test.py          ohne Modell, Aufruf als Parameter
    python -X utf8 bestand_test.py --echt   dazu einmal wirklich gpt-oss

Calvins Einwand ist der Pruefstein: "Er zieht ja keine Erkenntnis daraus."
Gemessen wird darum nicht, ob ein Satz entsteht, sondern ob es der richtige
ist - und vor allem, was NICHT durchkommt. Zwoelf Horrorspiele heissen "er hat
zwoelf Horrorspiele", nicht "er mag Horror".

Das Modell wird ueber `fragen=` hereingegeben. Der Grund steht in
archiv.zusammenfassen() und war ein echter Fehler: Eine Probe meldete
monatelang "bestanden" fuer einen Aufruf, den es im Betrieb nicht gab.
"""
from __future__ import annotations

from einstellungen import NAME
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bestand
import probenort

GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


class Modell:
    """Zaehlt mit, wie oft es gefragt wurde, und was es zu sehen bekam."""

    def __init__(self, antwort="Auf dem Desktop liegen Spielverknuepfungen."):
        self.antwort = antwort
        self.aufrufe = 0
        self.prompts: list[str] = []

    def __call__(self, nachrichten):
        self.aufrufe += 1
        self.prompts.append(nachrichten[-1]["content"])
        if isinstance(self.antwort, Exception):
            raise self.antwort
        if callable(self.antwort):
            return {"satz": self.antwort(nachrichten)}
        return {"satz": self.antwort}


class Gedaechtnis:
    """Statt der echten Datenbank - zweimal ist heute schon eine Probe ins
    Echte gelaufen, und einmal hat es 131 Erinnerungen gekostet."""

    def __init__(self):
        self.eintraege: list[dict] = []
        self._id = 0

    def __call__(self, art, text, quelle, ersetzt=None):
        self._id += 1
        self.eintraege.append({"id": self._id, "art": art, "text": text,
                               "quelle": quelle, "ersetzt": ersetzt})
        return self._id


# Ein Desktop und ein Download-Ordner, wie Calvins aussehen.
ablage = probenort.ablage("bestand")
DESKTOP = ablage / "Desktop"
DOWNLOADS = ablage / "Downloads"
for d in (DESKTOP, DOWNLOADS):
    d.mkdir(parents=True, exist_ok=True)


def url(ordner: Path, name: str, ziel: str) -> Path:
    p = ordner / f"{name}.url"
    p.write_text(f"[InternetShortcut]\nURL={ziel}\n", encoding="utf-8")
    return p


def datei(ordner: Path, name: str, inhalt: bytes = b"x" * 50) -> Path:
    p = ordner / name
    p.write_bytes(inhalt)
    return p


SPIELE = ["Dying Light The Beast", "Prey", "Steelrising", "Split Brain",
          "The Mound Omen of Cthulhu", "Yet Another Zombie Defense HD",
          "PixelJunk Nom Nom Galaxy", "Subnautica", "Don't Starve",
          "Phasmophobia", "Dead by Daylight", "Outlast"]
for i, name in enumerate(SPIELE):
    url(DESKTOP, name, f"steam://rungameid/{100 + i}")

verknuepfung_spiel = DESKTOP / "Rockstar Games Launcher.lnk"
verknuepfung_spiel.write_bytes(
    b"L\x00\x00\x00" + b"\x00" * 40
    + rb"C:\Program Files\Rockstar Games\Launcher\Launcher.exe" + b"\x00")

for name, inhalt in [("ComfyUI starten.bat", "@echo off\ncd C:\\ComfyUI\n"),
                     ("SwarmUI starten.bat", "@echo off\ncd C:\\SwarmUI\n"),
                     ("ollama bedienen.bat", "@echo off\nollama serve\n")]:
    (DESKTOP / name).write_text(inhalt, encoding="utf-8")
url(DESKTOP, "SwarmUI", "http://localhost:7801/Text2Image")

# Bilder: drei Bildschirmfotos, zwei Fotos. Nur die Beschreibung unterscheidet
# sie - am Namen ist es nicht zu sehen.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80
bilder = {}
for i in range(3):
    p = datei(DESKTOP, f"Screenshot_{i}.png", PNG)
    bilder[str(p)] = "Ein Bildschirmfoto, das eine Benutzeroberflaeche zeigt."
for i in range(2):
    p = datei(DESKTOP, f"IMG_{i}.png", PNG)
    bilder[str(p)] = "Ein Foto, das eine Waldlandschaft zeigt."

# Downloads: Installationsprogramme, Modelle, Archive.
for name in ("cpu-z_2.17-en.exe", "TeamViewer_Setup_x64.exe",
             "L-Connect-3-x64.exe", "obs-studio-31.exe"):
    datei(DOWNLOADS, name, b"MZ" + b"\x00" * 60)
for name in ("sd_xl_base_1.0.safetensors", "tf_model.h5",
             "llama-3-8b.gguf", "vae.ckpt"):
    datei(DOWNLOADS, name)
for name in ("unterlagen.zip", "bilder.7z", "sicherung.zip"):
    datei(DOWNLOADS, name)

ALLE = sorted(list(DESKTOP.iterdir()) + list(DOWNLOADS.iterdir()))


# ------------------------------------------------------------------ Proben


def probe_gruppieren() -> None:
    print("\nGruppieren wird GERECHNET, nicht gefragt")
    g = bestand.gruppieren(ALLE, bilder)
    wie = {k: len(v) for k, v in g.items()}

    pruefe(wie.get(("Desktop", "spiel")) == 13,
           "zwoelf Steam-Verknuepfungen plus Rockstar-Launcher = 13 Spiele: %s"
           % wie.get(("Desktop", "spiel")))
    pruefe(wie.get(("Desktop", "werkzeug")) == 4,
           "drei Startskripte plus SwarmUI-Verknuepfung = 4 Werkzeuge: %s"
           % wie.get(("Desktop", "werkzeug")))
    pruefe(wie.get(("Desktop", "bildschirmfoto")) == 3,
           "Bildschirmfotos von Fotos getrennt: %s"
           % wie.get(("Desktop", "bildschirmfoto")))
    pruefe(wie.get(("Desktop", "bild")) == 2,
           "und die zwei Fotos daneben: %s" % wie.get(("Desktop", "bild")))
    pruefe(wie.get(("Downloads", "programm")) == 4,
           "vier Installationsprogramme in Downloads: %s"
           % wie.get(("Downloads", "programm")))
    pruefe(wie.get(("Downloads", "modell")) == 4,
           "vier Modelldateien: %s" % wie.get(("Downloads", "modell")))
    pruefe(wie.get(("Downloads", "archiv")) == 3,
           "drei Archive: %s" % wie.get(("Downloads", "archiv")))
    pruefe(("Desktop", "sonstiges") not in wie,
           "nichts faellt in 'sonstiges': %s" % wie)

    # Das Spiel erkennt er am ZIEL, nicht am Namen. "Prey.url" sieht nach
    # nichts aus.
    pruefe(bestand.kategorie(DESKTOP / "Prey.url") == "spiel",
           "Prey.url ist ein Spiel - erkannt an steam://, nicht am Namen")
    pruefe(bestand.kategorie(verknuepfung_spiel) == "spiel",
           "und der Rockstar-Launcher auch, erkannt am Zielpfad")
    pruefe(bestand.kategorie(DESKTOP / "SwarmUI.url") == "werkzeug",
           "SwarmUI.url ist ein Werkzeug, kein Spiel")

    # Zweimal dasselbe Ergebnis - sonst steht dieselbe Datei morgen in einer
    # anderen Gruppe.
    pruefe(bestand.gruppieren(ALLE, bilder) == g,
           "zweimal gruppiert gibt zweimal dasselbe")

    pruefe(bestand.ort(DESKTOP / "x.url") == "Desktop"
           and bestand.ort(DOWNLOADS / "x.exe") == "Downloads",
           f"der Ort heisst, wie {NAME} ihn nennt")


def probe_vermutet() -> None:
    print("\nDie Grenze: beobachten, nicht behaupten")

    durch = [
        "Auf dem Desktop liegen dreizehn Spielverknuepfungen, ueberwiegend "
        "Survival und Horror - Dying Light, Prey, Outlast.",
        "ComfyUI und SwarmUI sind Oberflaechen fuer lokale Bilderzeugung mit "
        "Stable Diffusion.",
        "In Downloads liegen vier Modelldateien fuer neuronale Netze.",
    ]
    for s in durch:
        pruefe(bestand.vermutet(s) is None,
               "durchgelassen: %s" % s[:62])

    zurueck = [
        (f"{NAME} mag Horrorspiele.", "mag"),
        ("Er liebt Survival-Spiele.", "liebt"),
        (f"{NAME} bevorzugt Horror vor allem anderen.", "bevorzugt"),
        ("Seine Lieblingsspiele sind Horrorspiele.", "lieblings"),
        ("Er ist offenbar ein Fan von Zombie-Spielen.", "fan von"),
        ("Vermutlich nutzt er den Rechner zum Spielen.", "vermutlich"),
        ("Er nutzt den Rechner wahrscheinlich fuer Bilder.", "wahrscheinlich"),
        ("Das deutet darauf hin, dass er gerne spielt.", "deutet darauf"),
        ("Er interessiert sich fuer Bildgenerierung.", "interessiert sich"),
        ("Moeglicherweise arbeitet er mit Bildern.", "moeglicherweise"),
    ]
    for satz, wort in zurueck:
        grund = bestand.vermutet(satz)
        pruefe(grund is not None and wort in grund.lower(),
               "zurueckgehalten (%s): %s" % (wort, satz[:48]))

    # "ueberwiegend" und "hauptsaechlich" sind genau das, was Calvin will -
    # sie duerfen nicht als Vermutung gelten.
    for wort in ("ueberwiegend", "hauptsaechlich", "meist", "die meisten",
                 "zum grossen Teil"):
        s = f"Die Spiele sind {wort} Survival und Horror."
        pruefe(bestand.vermutet(s) is None, "erlaubt: %r" % wort)


def probe_erfundene_zahlen() -> None:
    print("\nAusgeschriebene Zahlen - daran lief die erste echte Antwort vorbei")

    # Der Satz, den gpt-oss beim ersten Lauf wirklich geliefert hat. Dreizehn
    # Dateien lagen da, er schrieb dreiundzwanzig. Als Ziffer haette
    # wissen.mangel() es gefangen, als Wort nicht.
    echt = ("Sie stellen insgesamt dreiundzwanzig Spielstarter und Launcher "
            "für verschiedene Computerspiele auf dem Desktop bereit.")
    pruefe(23 in bestand.zahlen_ausgeschrieben(echt),
           "dreiundzwanzig wird als 23 erkannt: %s"
           % sorted(bestand.zahlen_ausgeschrieben(echt)))
    pruefe(bestand.zu_viele(echt, 13) is not None,
           "und bei dreizehn Dateien zurueckgehalten: %s"
           % bestand.zu_viele(echt, 13))
    pruefe(bestand.unvollstaendig(echt) is not None,
           "und ausserdem wegen 'Sie': %s" % bestand.unvollstaendig(echt))

    for wort, zahl in [("zwoelf", 12), ("zwölf", 12), ("dreizehn", 13),
                       ("einundzwanzig", 21), ("vierundsechzig", 64),
                       ("ein Dutzend", 12), ("hundert", 100), ("acht", 8)]:
        erkannt = bestand.zahlen_ausgeschrieben(f"Es sind {wort} Dateien.")
        pruefe(zahl in erkannt, "%r -> %d: %s" % (wort, zahl, sorted(erkannt)))

    # Wortgrenzen: "kein" ist nicht "ein", "siebenter" nicht "sieben".
    pruefe(1 not in bestand.zahlen_ausgeschrieben("Es gibt keinen Grund."),
           "'keinen' ist keine Eins")

    # Untergruppen DUERFEN kleiner sein - das ist Calvins Stufe 3.
    stufe3 = ("Auf dem Desktop liegen dreizehn Spielverknuepfungen, "
              "ueberwiegend Survival und Horror. Dazu zwei Aufbauspiele.")
    pruefe(bestand.zu_viele(stufe3, 13) is None,
           "dreizehn und zwei bei dreizehn Dateien: durch")
    pruefe(bestand.zu_viele(stufe3, 12) is not None,
           "aber dreizehn bei zwoelf Dateien nicht")

    print("\nEin Satz muss allein stehen - er wird Monate spaeter vorgelesen")
    for schlecht in ("Sie stellen Spielstarter bereit.",
                     "Es handelt sich um Verknuepfungen.",
                     "Diese Dateien starten ComfyUI.",
                     "Hier liegen vier Skripte.",
                     "Die Gruppe besteht aus Modellen.",
                     "Der Ordner enthaelt Archive."):
        pruefe(bestand.unvollstaendig(schlecht) is not None,
               "zurueckgehalten: %s" % schlecht)
    for gut in ("Auf dem Desktop liegen dreizehn Spielverknuepfungen.",
                "ComfyUI und SwarmUI sind Oberflaechen fuer Bilderzeugung.",
                "In Downloads liegen vier Modelldateien."):
        pruefe(bestand.unvollstaendig(gut) is None,
               "durchgelassen: %s" % gut[:58])

    print("\nAusweichen ist keine Antwort - Stufe 2 wird zurueckgehalten")
    # Genau der Satz, den gpt-oss im zweiten Lauf geliefert hat: Zahl richtig,
    # allein stehend, ohne Behauptung - und trotzdem nur Stufe 2, weil das
    # Genre fehlt. Das ist Calvins eigentliche Frage.
    stufe2 = ("Auf dem Desktop liegen 13 Spielstarter und -verknuepfungen, "
              "die schnellen Zugriff auf verschiedene Spiele ermoeglichen.")
    pruefe(bestand.ungenau(stufe2) is not None,
           "'verschiedene Spiele' wird zurueckgehalten: %s"
           % bestand.ungenau(stufe2))
    pruefe(bestand.vermutet(stufe2) is None
           and bestand.unvollstaendig(stufe2) is None
           and bestand.zu_viele(stufe2, 13) is None,
           "und zwar NUR daran - die anderen Wachen lassen ihn durch")
    for wort in ("verschiedene", "diverse", "unterschiedlichen", "allerlei",
                 "aller Art"):
        s = f"Auf dem Desktop liegen Spiele {wort} Machart."
        pruefe(bestand.ungenau(s) is not None, "zurueckgehalten: %r" % wort)
    for gut in ("Auf dem Desktop liegen dreizehn Spiele, ueberwiegend "
                "Survival und Horror.",
                "ComfyUI und SwarmUI dienen der lokalen Bilderzeugung."):
        pruefe(bestand.ungenau(gut) is None, "durchgelassen: %s" % gut[:56])

    print("\nAnfuehrungszeichen und Sternchen werden mitgesprochen")
    pruefe(bestand.saeubern('Auf dem Desktop liegen Spiele.“')
           == "Auf dem Desktop liegen Spiele.",
           "das uebriggebliebene Anfuehrungszeichen fliegt weg: %r"
           % bestand.saeubern('Auf dem Desktop liegen Spiele.“'))
    pruefe(bestand.saeubern("**Vier** Skripte starten ComfyUI.")
           == "Vier Skripte starten ComfyUI.", "Sternchen auch")


def probe_erfundener_zweck() -> None:
    print("\nErfundene Kausalitaet - 'Bildgenerierung' an alles drangehaengt")

    audio = [DOWNLOADS / "Yeah.mp3", DOWNLOADS / "aufnahme.wav",
             DOWNLOADS / "config.json"]
    gifs = [DOWNLOADS / "homer.gif", DOWNLOADS / "simpsons.gif",
            DOWNLOADS / "katze.gif"]
    modelle = [p for p in DOWNLOADS.iterdir()
               if bestand.kategorie(p) == "modell"]
    starter = [p for p in DESKTOP.iterdir()
               if bestand.kategorie(p) == "werkzeug"]

    # Die drei Saetze, die am 12.09. wirklich im Gedaechtnis standen.
    gemessen = [
        ("Im Downloads-Ordner liegen vorwiegend Audiodateien, die für die "
         "lokale Bildgenerierung verwendet werden.", audio),
        ("In Downloads liegen animierte GIFs zu Pop-Culture-Themen, die die "
         "Vielfalt lokaler Bildgenerierung widerspiegeln.", gifs),
        ("In Downloads liegen zwölf Archive, die Entwickler-Tools für lokale "
         "Bildbearbeitung und Systemmanagement bereitstellen.",
         [DOWNLOADS / "unterlagen.zip", DOWNLOADS / "bilder.7z"]),
    ]
    for satz, dateien in gemessen:
        grund = bestand.ungegruendet(satz, dateien)
        pruefe(grund is not None,
               "zurueckgehalten: %s" % satz[:66])
        if grund:
            print(f"        -> {grund}")

    # Und die zwei, bei denen der Zusammenhang WIRKLICH belegt ist.
    echt = [
        ("In Downloads liegen 19 Modelldateien für die lokale "
         "Bildgenerierung.", modelle),
        ("ComfyUI und SwarmUI werden über Starter aufgerufen und dienen der "
         "lokalen Bildgenerierung.", starter),
    ]
    for satz, dateien in echt:
        pruefe(bestand.ungegruendet(satz, dateien) is None,
               "durchgelassen, weil die Dateien es belegen: %s" % satz[:58])

    # Ein Satz ohne Zweckbehauptung wird nie daran gemessen.
    pruefe(bestand.ungegruendet(
        "In Downloads liegen zwölf Archive, elf ZIP und ein 7z.", audio)
        is None, "ohne Zweckbehauptung gibt es nichts zu belegen")

    print("\nEine Restegruppe kann kein Muster haben")
    reste = [DOWNLOADS / "x.smap", DOWNLOADS / "y.dat", DOWNLOADS / "z.bin2",
             DOWNLOADS / "w.tmp"]
    for p in reste:
        p.write_bytes(b"x" * 30)
    m = Modell()
    erkenntnisse, _ = bestand.zusammenschau(reste, {}, fragen=m)
    kategorien = [e["kategorie"] for e in erkenntnisse]
    pruefe("sonstiges" not in kategorien,
           "ueber `sonstiges` wird nicht gefragt: %s" % kategorien)
    for p in reste:
        p.unlink(missing_ok=True)


def probe_falscher_ort() -> None:
    print("\nDer Fakt darf die Dateien nicht an den falschen Ort legen")
    # Drei Saetze, die gpt-oss am 12.09. wirklich geliefert hat - alle drei
    # fuer Gruppen aus Downloads, alle drei mit "Auf dem Desktop".
    for satz in ("Auf dem Desktop liegen 17 Dateien, darunter 13 animierte "
                 "GIFs.",
                 "Auf dem Desktop liegen 16 Dokumente mit "
                 "Konfigurationsdateien.",
                 "Auf dem Desktop liegen fünf Starterdateien für Audacity."):
        grund = bestand.falscher_ort(satz, "Downloads")
        pruefe(grund is not None, "zurueckgehalten: %s" % satz[:60])

    for satz, ort_ in (
            ("Zwölf Archive im Downloads-Ordner bestehen aus Zip-Dateien.",
             "Downloads"),
            ("Auf dem Desktop liegen acht Spielstarter, meist Horror.",
             "Desktop"),
            ("Die 34 Installationsprogramme bestehen aus 31 .exe-Dateien.",
             "Downloads"),
            ("Im Downloadbereich liegen zwölf Archive.", "Downloads")):
        pruefe(bestand.falscher_ort(satz, ort_) is None,
               "durchgelassen [%s]: %s" % (ort_, satz[:52]))

    # Nennt er BEIDE Orte, ist es in Ordnung - dann vergleicht er.
    pruefe(bestand.falscher_ort(
        "Anders als auf dem Desktop liegen in Downloads vor allem "
        "Installationsprogramme.", "Downloads") is None,
        "beide Orte genannt, der eigene dabei: durch")

    # Und der ganze Weg: die Ortswache greift in satz_fuer().
    dl_bilder = [p for p in DOWNLOADS.iterdir()
                 if bestand.kategorie(p) == "archiv"]
    m = Modell("Auf dem Desktop liegen drei Archive.")
    satz, grund = bestand.satz_fuer("Downloads", "archiv", dl_bilder,
                                    fragen=m)
    pruefe(satz == "" and "falschen Ort" in grund,
           "satz_fuer() haelt ihn zurueck: %s" % grund)
    pruefe(m.aufrufe == 2, "und fragt vorher einmal nach: %d" % m.aufrufe)


def probe_ueberblick() -> None:
    print("\nSechs Gruppen, sechsmal 'vorwiegend' ueber denselben Ordner")

    # Genau die sechs Saetze vom 12.09. - jeder urteilte ueber Downloads.
    for satz in ("Im Downloads-Ordner liegen vorwiegend Audiodateien.",
                 "In Downloads liegen überwiegend animierte GIFs.",
                 "Im Download-Ordner liegen hauptsächlich Tokenizer-Dateien.",
                 "Im Downloadbereich liegen meist Archive."):
        grund = bestand.ueber_den_ordner(satz)
        pruefe(grund is not None, "zurueckgehalten: %s" % satz)

    # Ein Satz ueber die GRUPPE ist richtig und muss durch.
    for satz in ("Die zwölf Archive in Downloads sind überwiegend ZIP-Pakete.",
                 "Die 34 Installationsprogramme in Downloads sind "
                 "hauptsächlich Systemwerkzeuge.",
                 "Auf dem Desktop liegen acht Spielverknüpfungen, "
                 "überwiegend Horror."):
        pruefe(bestand.ueber_den_ordner(satz) is None,
               "durchgelassen: %s" % satz[:62])

    # Und der Ueberblick DARF es - er sieht alle Gruppen.
    g = bestand.gruppieren(ALLE, bilder)
    gut = ("In Downloads liegen vorwiegend Installationsprogramme, dazu "
           "Modelldateien und Archive.")
    m = Modell(gut)
    satz, grund = bestand.ueberblick_fuer("Downloads", g, fragen=m)
    pruefe(satz == gut,
           "der Ueberblick darf 'vorwiegend' sagen: %s" % (grund or "ok"))
    pruefe("11x" in m.prompts[0] or "Installationsprogramme" in m.prompts[0],
           "er bekommt die Zaehlung aller Gruppen zu sehen")

    # Bei nur einer Gattung braucht es keinen.
    eine = {("Desktop", "spiel"): [DESKTOP / "Prey.url"]}
    satz, grund = bestand.ueberblick_fuer("Desktop", eine, fragen=Modell())
    pruefe(satz == "" and "eine Gattung" in grund,
           "bei einer Gattung kein Ueberblick: %s" % grund)

    # Im ganzen Durchgang: je Ort genau EIN Ueberblick.
    def je_gruppe(nachrichten):
        text = nachrichten[-1]["content"]
        if text.startswith("Ordner:"):
            ort_ = text.split("\n")[0].split(":", 1)[1].strip()
            return f"In {ort_} liegen vorwiegend Dateien mehrerer Gattungen."
        kopf = text.split("Gattung:")[1].split(",")[0].strip()
        return f"Im Bestand liegen {kopf} in nennenswerter Zahl."

    erkenntnisse, _ = bestand.zusammenschau(ALLE, bilder,
                                            fragen=Modell(je_gruppe))
    ueberblicke = [e for e in erkenntnisse if e["kategorie"] == "ueberblick"]
    orte = {e["ort"] for e in ueberblicke}
    pruefe(len(ueberblicke) == len(orte) == 2,
           "je Ort genau ein Ueberblick: %d fuer %s"
           % (len(ueberblicke), sorted(orte)))
    pruefe(erkenntnisse[0]["kategorie"] == "ueberblick",
           "und er steht vorn, vor den Gruppen")


def probe_satz_fuer() -> None:
    print("\nEin Satz je Gruppe - und die Wachen davor")
    spiele = [p for p in DESKTOP.iterdir()
              if bestand.kategorie(p) == "spiel"]

    # Eine zu kleine Gruppe fragt das Modell GAR NICHT.
    m = Modell()
    satz, grund = bestand.satz_fuer("Desktop", "spiel", spiele[:2], fragen=m)
    pruefe(satz == "" and m.aufrufe == 0,
           "zwei Dateien sind kein Muster - Modell nicht gefragt: %s" % grund)

    # Eine grosse schon.
    gut = ("Auf dem Desktop liegen dreizehn Spielverknuepfungen, ueberwiegend "
           "Survival und Horror.")
    m = Modell(gut)
    satz, grund = bestand.satz_fuer("Desktop", "spiel", spiele, fragen=m)
    pruefe(satz == gut and m.aufrufe == 1, "der Satz steht: %s" % satz)
    pruefe("Dying Light The Beast.url" in m.prompts[0]
           and "Gattung" in m.prompts[0],
           "die Namensliste und die Gattung stehen im Prompt")
    pruefe(str(len(spiele)) in m.prompts[0],
           "und die Anzahl - das Modell soll das Ueberwiegende nennen")

    # Die Wache gegen Vorlieben. Zweimal dasselbe -> endgueltig zurueck.
    m = Modell(f"{NAME} mag vor allem Horrorspiele.")
    satz, grund = bestand.satz_fuer("Desktop", "spiel", spiele, fragen=m)
    pruefe(satz == "" and "Vorlieben" in grund,
           f"'{NAME} mag' wird zurueckgehalten: %s" % grund)
    pruefe(m.aufrufe == 2 and "auch nach Nachfrage" in grund,
           "und zwar erst nach einer Nachfrage: %d Aufrufe" % m.aufrufe)

    # EINE Nachfrage rettet den Satz, wenn nur der Anfang nicht taugte. Genau
    # das ist mit gpt-oss passiert: "Diese vier Elemente ..." fiel aus,
    # obwohl der Inhalt stimmte - und damit die groesste Gruppe ganz.
    class Zweimal:
        def __init__(self):
            self.aufrufe = 0

        def __call__(self, nachrichten):
            self.aufrufe += 1
            if self.aufrufe == 1:
                return {"satz": "Diese dreizehn Spiele sind meist Horror."}
            return {"satz": "Auf dem Desktop liegen dreizehn Spiele, "
                            "meist Horror."}

    z = Zweimal()
    satz, grund = bestand.satz_fuer("Desktop", "spiel", spiele, fragen=z)
    pruefe(satz.startswith("Auf dem Desktop") and z.aufrufe == 2,
           "nach der Nachfrage steht er: %s" % (satz or grund))

    # Die Wache gegen erfundene Zahlen - aber die RICHTIGE Anzahl muss durch.
    satz, grund = bestand.satz_fuer(
        "Desktop", "spiel", spiele,
        fragen=Modell("Auf dem Desktop liegen 99 Spielverknuepfungen."))
    pruefe(satz == "" and "99" in grund,
           "99 bei 13 Dateien wird zurueckgehalten: %s" % grund)
    richtig = (f"Auf dem Desktop liegen {len(spiele)} "
           f"Spielverknuepfungen, meist Horror.")
    satz, grund = bestand.satz_fuer("Desktop", "spiel", spiele,
                                    fragen=Modell(richtig))
    pruefe(satz == richtig,
           "die richtige Anzahl darf genannt werden: %s" % (grund or satz))

    # Stumm ist kein Absturz.
    import httpx
    satz, grund = bestand.satz_fuer(
        "Desktop", "spiel", spiele,
        fragen=Modell(httpx.ConnectError("kein Ollama")))
    pruefe(satz == "" and "stumm" in grund.lower(),
           "ein stummes Modell gibt einen Grund, keinen Absturz: %s" % grund)

    # Und eine Erzaehlung ueber 400 Zeichen nicht.
    satz, grund = bestand.satz_fuer("Desktop", "spiel", spiele,
                                    fragen=Modell("Spiele. " * 80))
    pruefe(satz == "" and grund, "zu lang wird zurueckgehalten: %s" % grund)


def probe_zusammenschau() -> None:
    print("\nAus vierzig Funden werden ein paar Saetze, nicht vierzig")

    def je_gruppe(nachrichten):
        # Antwortet mit der Gattung, damit sich die Saetze unterscheiden.
        # Der Ueberblick bekommt keinen "Gattung:"-Kopf, sondern "Ordner:".
        text = nachrichten[-1]["content"]
        if text.startswith("Ordner:"):
            ort_ = text.splitlines()[0].split(":", 1)[1].strip()
            return f"In {ort_} liegen Dateien mehrerer Gattungen."
        kopf = text.split("Gattung:")[1].split(",")[0].strip()
        return f"Im Bestand liegen {kopf} in nennenswerter Zahl."

    m = Modell(je_gruppe)
    erkenntnisse, zurueck = bestand.zusammenschau(ALLE, bilder, fragen=m)

    pruefe(len(ALLE) == 33, "Material: %d Dateien" % len(ALLE))
    pruefe(len(erkenntnisse) <= 8,
           "daraus hoechstens acht Saetze: %d" % len(erkenntnisse))
    pruefe(len(erkenntnisse) >= 5,
           "aber mehr als einer - je Gruppe einer: %d" % len(erkenntnisse))
    pruefe(m.aufrufe == len(erkenntnisse) + len(zurueck),
           "ein Modellaufruf je Gruppe, die gross genug ist: %d Aufrufe, "
           "%d Saetze" % (m.aufrufe, len(erkenntnisse)))

    # Vorn die Ueberblicke, dann die groesste Gruppe - dort steht, was am
    # meisten sagt.
    nur_gruppen = [e for e in erkenntnisse if e["kategorie"] != "ueberblick"]
    pruefe(erkenntnisse[0]["kategorie"] == "ueberblick",
           "der Ueberblick steht vorn: %s" % erkenntnisse[0]["kategorie"])
    pruefe(nur_gruppen[0]["kategorie"] == "spiel"
           and nur_gruppen[0]["anzahl"] == 13,
           "und danach die groesste Gruppe: %s (%d)"
           % (nur_gruppen[0]["kategorie"], nur_gruppen[0]["anzahl"]))

    # Jede Erkenntnis traegt ihren Gruppenschluessel - daran haengt das
    # Ueberholen.
    pruefe(all(e["schluessel"].startswith("zuhause:") for e in erkenntnisse),
           "jede traegt einen Gruppenschluessel: %s"
           % erkenntnisse[0]["schluessel"])
    pruefe(len({e["schluessel"] for e in erkenntnisse}) == len(erkenntnisse),
           "und zwar einen eigenen")

    # KEIN Satz zaehlt Dateinamen auf - das waere Stufe 1 in neu.
    pruefe(not any(".url" in e["satz"] or ".exe" in e["satz"]
                   for e in erkenntnisse),
           "kein Satz nennt Dateiendungen")


def probe_nur_was_neu_ist() -> None:
    print("\nC.1: festgehalten wird, was NEU ist")
    ort_zustand = probenort.ablage("bestand_zustand")
    echt_zustand, echt_werkstatt = bestand.ZUSTAND, bestand.WERKSTATT
    try:
        bestand.ZUSTAND = ort_zustand / "bestand.json"
        bestand.WERKSTATT = ort_zustand

        g = Gedaechtnis()
        m = Modell("Auf dem Desktop liegen viele Spielverknuepfungen.")
        b1 = bestand.durchgang(jetzt=1000.0, fragen=m, merken=g,
                               dateien=ALLE, saetze=bilder)
        pruefe(b1["gemerkt"] > 0, "der erste Durchgang merkt: %d"
               % b1["gemerkt"])
        pruefe(all(e["art"] == "zuhause" for e in g.eintraege),
               "als Art `zuhause` - ein Fakt ueber sein Zuhause")
        pruefe(all(e["quelle"].startswith("zuhause:") for e in g.eintraege),
               "mit dem Gruppenschluessel als Quelle")
        pruefe(all(e["ersetzt"] is None for e in g.eintraege),
               "beim ersten Mal wird nichts ueberholt")
        erster = len(g.eintraege)

        # Zweiter Durchgang, GLEICHE Saetze: nichts Neues.
        b2 = bestand.durchgang(jetzt=2000.0, fragen=Modell(m.antwort),
                               merken=g, dateien=ALLE, saetze=bilder)
        pruefe(b2["gemerkt"] == 0,
               "derselbe Satz wird NICHT noch einmal gemerkt: %d"
               % b2["gemerkt"])
        pruefe(b2["unveraendert"] == erster,
               "sondern als unveraendert gezaehlt: %d" % b2["unveraendert"])
        pruefe(len(g.eintraege) == erster,
               "das Gedaechtnis ist nicht gewachsen: %d" % len(g.eintraege))

        # Dritter Durchgang, GEAENDERTER Satz: er ERSETZT den alten.
        neu = "Auf dem Desktop liegen inzwischen noch mehr Spiele."
        spiel_schluessel = bestand.schluessel_fuer("Desktop", "spiel")

        def nur_spiele_anders(nachrichten):
            text = nachrichten[-1]["content"]
            if text.startswith("Ordner:"):
                return "Im Ordner liegen Dateien mehrerer Gattungen."
            if "spiel" in text.split("Gattung:")[1][:40].lower():
                return neu
            return "Im Bestand liegt weiterhin anderes Material."

        vorher_ids = {e["quelle"]: e["id"] for e in g.eintraege}
        b3 = bestand.durchgang(jetzt=3000.0, fragen=Modell(nur_spiele_anders),
                               merken=g, dateien=ALLE, saetze=bilder)
        ersetzend = [e for e in g.eintraege[erster:]
                     if e["quelle"] == spiel_schluessel]
        pruefe(b3["gemerkt"] >= 1, "ein geaenderter Satz wird gemerkt: %d"
               % b3["gemerkt"])
        pruefe(len(ersetzend) == 1 and ersetzend[0]["text"] == neu,
               "und traegt den neuen Wortlaut")
        pruefe(ersetzend and ersetzend[0]["ersetzt"] == vorher_ids.get(
                   spiel_schluessel),
               "er UEBERHOLT den alten, statt daneben zu treten: ersetzt=%s"
               % (ersetzend[0]["ersetzt"] if ersetzend else None))
    finally:
        bestand.ZUSTAND, bestand.WERKSTATT = echt_zustand, echt_werkstatt
        probenort.wegraeumen(ort_zustand)


def probe_trockenlauf() -> None:
    print("\nEin Trockenlauf, der den Zustand aendert, ist keiner")
    ort_zustand = probenort.ablage("bestand_trocken")
    echt_zustand, echt_werkstatt = bestand.ZUSTAND, bestand.WERKSTATT
    try:
        bestand.ZUSTAND = ort_zustand / "bestand.json"
        bestand.WERKSTATT = ort_zustand

        # Ohne merken= ist es ein Trockenlauf. Er hat den Zustand
        # fortgeschrieben und "7 gemerkt" gemeldet, obwohl nichts gemerkt
        # wurde - der naechste echte Lauf hielt alle sieben fuer
        # "unveraendert" und legte sie NIE ins Gedaechtnis.
        b = bestand.durchgang(jetzt=1000.0, fragen=Modell(), dateien=ALLE,
                              saetze=bilder)
        pruefe(b["trocken"] is True, "er weiss, dass er trocken laeuft")
        pruefe(b["gemerkt"] == 0, "gemerkt ist 0, nicht 7: %d" % b["gemerkt"])
        pruefe(b["waere_gemerkt"] > 0,
               "aber er sagt, was er gemerkt HAETTE: %d" % b["waere_gemerkt"])
        pruefe(not bestand.ZUSTAND.exists(),
               "und schreibt den Zustand NICHT fort")

        # Und danach merkt der echte Lauf wirklich alles.
        g = Gedaechtnis()
        b2 = bestand.durchgang(jetzt=2000.0, fragen=Modell(), merken=g,
                               dateien=ALLE, saetze=bilder)
        pruefe(b2["trocken"] is False, "der echte Lauf ist nicht trocken")
        pruefe(b2["gemerkt"] == b["waere_gemerkt"],
               "er merkt genau so viele, wie der Trockenlauf angesagt hat: "
               "%d von %d" % (b2["gemerkt"], b["waere_gemerkt"]))
        pruefe(len(g.eintraege) == b2["gemerkt"],
               "und sie liegen im Gedaechtnis: %d" % len(g.eintraege))
        pruefe(bestand.ZUSTAND.exists(), "jetzt steht der Zustand da")
    finally:
        bestand.ZUSTAND, bestand.WERKSTATT = echt_zustand, echt_werkstatt
        probenort.wegraeumen(ort_zustand)


def probe_verschwundene_gruppe() -> None:
    print("\nEine Gruppe, die es nicht mehr gibt, behaelt ihren Fakt nicht")
    ort_zustand = probenort.ablage("bestand_veraltet")
    echt_zustand, echt_werkstatt = bestand.ZUSTAND, bestand.WERKSTATT
    try:
        bestand.ZUSTAND = ort_zustand / "bestand.json"
        bestand.WERKSTATT = ort_zustand

        # Genau der Fall vom 12.09.: `sonstiges` wird seit heute nicht mehr
        # gefragt. Der Satz "vorwiegend Audiodateien, die fuer die lokale
        # Bildgenerierung verwendet werden" waere fuer immer stehen geblieben,
        # weil ihn nie wieder etwas ersetzt.
        bestand._zustand_schreiben({"anzahl": 0, "gruppen": {
            "zuhause:downloads:sonstiges": {
                "satz": "Im Downloads-Ordner liegen vorwiegend Audiodateien, "
                        "die für die lokale Bildgenerierung verwendet werden.",
                "id": 42}}})

        veraltet = []
        g = Gedaechtnis()
        b = bestand.durchgang(jetzt=1000.0, fragen=Modell(), merken=g,
                              veralten=veraltet.append,
                              dateien=ALLE, saetze=bilder)
        pruefe("zuhause:downloads:sonstiges" in b["veraltet"],
               "die verschwundene Gruppe wird gemeldet: %s" % b["veraltet"])
        pruefe(veraltet == [42],
               "und ihre Erinnerung ueberholt - Kennung 42: %s" % veraltet)

        import json as _json
        z = _json.loads(bestand.ZUSTAND.read_text(encoding="utf-8"))
        pruefe("zuhause:downloads:sonstiges" not in (z.get("gruppen") or {}),
               "sie steht danach nicht mehr im Zustand")

        # Ein Trockenlauf ueberholt NICHTS.
        bestand._zustand_schreiben({"anzahl": 0, "gruppen": {
            "zuhause:downloads:sonstiges": {"satz": "x", "id": 43}}})
        trocken = []
        b = bestand.durchgang(jetzt=2000.0, fragen=Modell(),
                              veralten=trocken.append, dateien=ALLE,
                              saetze=bilder)
        pruefe(trocken == [] and "zuhause:downloads:sonstiges" in b["veraltet"],
               "der Trockenlauf meldet sie, ueberholt aber nichts: %s"
               % trocken)
    finally:
        bestand.ZUSTAND, bestand.WERKSTATT = echt_zustand, echt_werkstatt
        probenort.wegraeumen(ort_zustand)


def probe_faellig() -> None:
    print("\nWann zusammengeschaut wird - nicht mitten in den Lernlauf hinein")
    ort_zustand = probenort.ablage("bestand_faellig")
    echt_zustand, echt_werkstatt = bestand.ZUSTAND, bestand.WERKSTATT
    try:
        bestand.ZUSTAND = ort_zustand / "bestand.json"
        bestand.WERKSTATT = ort_zustand

        pruefe(bestand.faellig(150, jetzt=1000.0, letzte_aenderung=0.0),
               "beim ersten Mal mit 150 Dateien: ja")
        pruefe(not bestand.faellig(150, jetzt=1000.0, letzte_aenderung=999.0),
               "aber NICHT, solange gerade noch Dateien dazukommen")
        pruefe(not bestand.faellig(2, jetzt=1000.0, letzte_aenderung=0.0),
               "und nicht fuer zwei Dateien")

        bestand._zustand_schreiben({"anzahl": 150, "gruppen": {
            "zuhause:desktop:spiel": {"satz": "x", "id": 7}}})
        pruefe(not bestand.faellig(152, jetzt=2000.0, letzte_aenderung=0.0),
               "zwei neue Dateien loesen keine neue Zusammenschau aus")
        pruefe(bestand.faellig(160, jetzt=2000.0, letzte_aenderung=0.0),
               "zehn neue schon")

        # Liegengebliebenes wird nachgeholt, auch ohne Zuwachs. Sonst bleiben
        # sieben Gruppen, die ein Trockenlauf vermerkt hat, fuer immer liegen.
        bestand._zustand_schreiben({"anzahl": 150, "gruppen": {
            "zuhause:desktop:spiel": {"satz": "x", "id": None}}})
        pruefe(bestand.faellig(150, jetzt=2000.0, letzte_aenderung=0.0),
               "eine Gruppe ohne Kennung ist liegengebliebene Arbeit")
        pruefe(not bestand.faellig(150, jetzt=2000.0, letzte_aenderung=1999.0),
               "aber auch sie wartet, bis es ruhig ist")

        # Und ein Satz ohne Kennung gilt nicht als gemerkt.
        g = Gedaechtnis()
        b = bestand.durchgang(jetzt=3000.0, fragen=Modell(), merken=g,
                              dateien=ALLE, saetze=bilder)
        pruefe(b["gemerkt"] > 0 and b["unveraendert"] == 0,
               "ein Eintrag ohne Kennung wird nachgemerkt, nicht uebersprungen:"
               " %d gemerkt, %d unveraendert" % (b["gemerkt"],
                                                 b["unveraendert"]))
    finally:
        bestand.ZUSTAND, bestand.WERKSTATT = echt_zustand, echt_werkstatt
        probenort.wegraeumen(ort_zustand)


def probe_echt() -> None:
    print("\nEinmal wirklich gpt-oss - der Pruefstein aus Stufe 3")
    spiele = [p for p in DESKTOP.iterdir()
              if bestand.kategorie(p) == "spiel"]
    satz, grund = bestand.satz_fuer("Desktop", "spiel", spiele)
    print(f"    {satz or '(zurueckgehalten: %s)' % grund}")
    pruefe(bool(satz), "ein Satz kommt zurueck: %s" % (grund or "ok"))
    if satz:
        unten = satz.lower()
        pruefe(not any(e in unten for e in (".url", ".lnk", ".exe")),
               "er zaehlt keine Dateinamen auf")
        pruefe(bestand.vermutet(satz) is None,
               "und behauptet nichts ueber Vorlieben")
        genre = ("horror", "survival", "zombie", "ueberleben", "grusel",
                 "schrecken", "action")
        pruefe(any(w in unten for w in genre),
               "und nennt das Ueberwiegende, nicht nur die Zahl: %s" % satz)

    werkzeuge = [p for p in DESKTOP.iterdir()
                 if bestand.kategorie(p) == "werkzeug"]
    satz, grund = bestand.satz_fuer("Desktop", "werkzeug", werkzeuge)
    print(f"    {satz or '(zurueckgehalten: %s)' % grund}")
    if satz:
        unten = satz.lower()
        pruefe(any(w in unten for w in ("bild", "diffusion", "generier",
                                        "sprachmodell", "modell")),
               "er sagt, WOZU ComfyUI und SwarmUI da sind: %s" % satz)


def main() -> int:
    probe_gruppieren()
    probe_vermutet()
    probe_erfundene_zahlen()
    probe_erfundener_zweck()
    probe_falscher_ort()
    probe_ueberblick()
    probe_satz_fuer()
    probe_zusammenschau()
    probe_nur_was_neu_ist()
    probe_trockenlauf()
    probe_verschwundene_gruppe()
    probe_faellig()
    if "--echt" in sys.argv:
        probe_echt()

    probenort.wegraeumen(ablage)
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
