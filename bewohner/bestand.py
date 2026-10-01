"""Was auf dem Rechner liegt - als Erkenntnis, nicht als Verzeichnis.

CALVINS EINWAND, und er traf den Kern: "Gehst du auch an, dass die Funde
Muell waren? Er zieht ja keine Erkenntnis daraus."

Bis hierher beschrieb der Bewohner jede Datei einzeln, schickte den Satz ins
Journal - und vergass ihn sofort, denn jeder Fund traegt `nicht_erinnern`. Am
naechsten Tag fing er bei null an und beschrieb dieselben vierzig Dateien
wieder. Vierzig Saetze sind kein Wissen, auch wenn jeder einzelne stimmt.

Dieselbe Regel wie in B und C, nur fuer Dateien statt fuer Gespraeche:

  Ein Fund        ist Rohmaterial. Journal, sonst nichts - kein Ereignis,
                  keine Erinnerung, keine Mitteilung.
  Die Zusammenschau ist die Erkenntnis. Die gehoert ins Gedaechtnis.

DREI STUFEN, am selben Material - und nur die dritte ist etwas wert:

  1  "Eine Datei namens Prey.url, 0 Kilobyte, Art unbekannt."   vierzig Mal
  2  "Auf dem Desktop liegen ein Dutzend Spielverknuepfungen."  nur gezaehlt
  3  "Calvins Spiele sind ueberwiegend Survival und Horror - Dying Light,
      Prey, The Mound. Fuer Bilder nutzt er ComfyUI und SwarmUI, also lokale
      Bilderzeugung."

Stufe 3 sagt etwas ueber CALVIN, nicht ueber die Dateien. Das ist der
Unterschied, und es ist das Ziel: "Er soll sein Zuhause kennen. Was gibt es,
was bedeutet es, was kann es? Welche Bedeutung hat es fuer den User?"

UND DIE GRENZE, die genauso wichtig ist. Zwoelf Horrorspiele auf der Platte
heissen "er HAT zwoelf Horrorspiele", nicht "er MAG Horror lieber als alles
andere". Beobachten, nicht behaupten - dieselbe Grenze wie beim erfundenen
Bildschirminhalt. `vermutet()` haelt Saetze zurueck, die ueber Vorlieben
reden, und `wissen.mangel()` die, die Zahlen erfinden.

WARUM DER GANZE BESTAND UND NICHT DER DURCHGANG: Ein Muster zeigt sich an
zwoelf Verknuepfungen, nicht an den drei, die dieser Durchgang angefasst hat.
Gruppiert wird darum alles, was `wahrnehmung.bekannte_dateien()` kennt. Das
Gruppieren rechnet, das Modell formuliert - es bekommt eine Namensliste und
soll EINEN Satz ueber das Muster schreiben.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS
import json
import os
import re
import time
from pathlib import Path

import httpx

import wahrnehmung
import wissen
import zeitwort

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
ZUSTAND = WERKSTATT / "bestand.json"

OLLAMA = "http://localhost:11434/api/chat"
MODELL = "gpt-oss:20b"

# Eine Zusammenschau ist laenger als ein Fakt, aber kuerzer als eine
# Erzaehlung. Derselbe Grund wie in archiv.py.
ZUSAMMENSCHAU_ZEICHEN_MAX = 400

# Unter so vielen Dateien ist eine Gruppe kein Muster, sondern ein Zufall.
# Zwei .url-Dateien sagen nichts darueber, wofuer er den Rechner benutzt.
GRUPPE_MIN = 3

# So viele Namen bekommt das Modell je Gruppe zu sehen. Mehr hilft nicht und
# kostet nur Zeit - das Muster steht in den ersten vierzig.
NAMEN_HOECHSTENS = 40

# So lange muss es ruhig sein, bevor zusammengeschaut wird. Waehrend er noch
# dreissig Dateien abarbeitet, waere jede Zusammenschau von gestern.
RUHE_S = 120.0

# Und so viele Dateien muessen dazugekommen sein, damit es sich lohnt.
ZUWACHS_MIN = 5


# ------------------------------------------------------------- Gruppieren

# Was eine Verknuepfung zu einer Spielverknuepfung macht. Im Ziel, nicht im
# Namen: "Prey.url" sieht nach nichts aus, `steam://rungameid/3970` ist
# eindeutig.
SPIEL_MARKEN = ("steam://", "steampowered", "epicgames", "com.epicgames",
                "gog.com", "goggalaxy", "origin://", "uplay://", "ubisoft",
                "battlenet://", "blizzard", "rockstar games", "ea app",
                "xboxgames", "gamepass", "itch.io")

# Und was eine Arbeitsoberflaeche ausmacht. Diese Namen verraten die Art
# Arbeit, nicht nur die Dateiart - das ist Calvins "was kann es".
WERKZEUG_MARKEN = ("comfyui", "swarmui", "automatic1111", "a1111", "forge",
                   "stable-diffusion", "stablediffusion", "webui", "ollama",
                   "lm studio", "lmstudio", "koboldcpp", "llama", "whisper",
                   "blender", "obs studio", "ffmpeg", "davinci", "audacity",
                   "visual studio", "vscode", "pycharm", "git", "docker",
                   "node", "cuda", "anaconda", "miniconda")

MODELL_ENDUNGEN = {".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".h5",
                   ".onnx", ".bin"}
ARCHIV_ENDUNGEN = {".zip", ".7z", ".rar", ".tar", ".gz", ".iso"}

# Wie eine Gruppe im Satz heisst. Der Schluessel ist die Gattung, der Wert
# steht im Prompt - "Spielverknuepfungen" liest sich besser als "spiel".
GRUPPENNAME = {
    "spiel": "Spielverknuepfungen und Spielstarter",
    "werkzeug": "Starter und Verknuepfungen fuer Programme, mit denen "
                "gearbeitet wird",
    "programm": "Installationsprogramme",
    "modell": "Modelldateien fuer neuronale Netze",
    "bildschirmfoto": "Bildschirmfotos",
    "bild": "Bilder und Fotos",
    "dokument": "Dokumente und Texte",
    "archiv": "Archive",
    "verknuepfung": "Verknuepfungen",
    "sonstiges": "Dateien verschiedener Art",
}

# Was je Gattung das UEBERWIEGENDE ist - Calvins eigentliche Frage: "welche
# Kategorie Games ich hauptsaechlich installiert habe". Ohne diese Zeile
# antwortete gpt-oss "dreizehn Spielstarter fuer verschiedene Spiele" - die
# Zahl stimmte, das Muster fehlte. Das ist Stufe 2, und Stufe 2 ist zu wenig.
WAS_UEBERWIEGT = {
    "spiel": "Welches GENRE ueberwiegt? Du kennst die Titel - ordne sie ein: "
             "Survival, Horror, Shooter, Aufbau, Rennspiel, Rollenspiel, "
             "Indie, Koop. Das Genre steht am ANFANG des Satzes, die Anzahl "
             "danach: \"Die Spiele sind ueberwiegend Horror und Shooter, dazu "
             "zwei Aufbauspiele - acht Verknuepfungen auf dem Desktop.\" "
             "Nenne das haeufigste zuerst, das zweithaeufigste danach.",
    "werkzeug": "Welche Art ARBEIT verraten sie? Bildgenerierung, "
                "Sprachmodelle, Entwicklung, Videoschnitt, Tonbearbeitung. "
                "Sag, wozu die Programme da sind - nicht, dass es Skripte "
                "sind.",
    "programm": "Was fuer Programme sind das, und wofuer? Systemwerkzeuge, "
                "Fernwartung, Treiber, Aufnahme.",
    "modell": "Fuer welche Art Arbeit sind diese Modelle da? Bilderzeugung, "
              "Sprache, Ton.",
    "bildschirmfoto": "Wovon sind die Bildschirmfotos? Oberflaechen, "
                      "Messwerte, Gespraeche, Fehlermeldungen.",
    "bild": "Was zeigen die Bilder ueberwiegend? Fotos, erzeugte Bilder, "
            "Aufnahmen von Landschaften oder Menschen.",
    "dokument": "Worum geht es in ihnen ueberwiegend?",
    "archiv": "Was steckt darin, soweit die Namen es sagen?",
}

# Die Ausweichwoerter. Sie sehen nach einer Antwort aus und sind keine:
# "dreizehn Spielstarter fuer verschiedene Spiele" nennt kein Muster, es sagt
# nur, dass es mehrere sind. Genau das ist Stufe 2.
UNGENAU = ("verschiedene", "verschiedener", "verschiedenen", "verschiedenster",
           "unterschiedliche", "unterschiedlichen", "unterschiedlichster",
           "diverse", "diversen", "allerlei", "aller art", "jeglicher art",
           "mehrere arten", "alle moeglichen")


def ort(pfad) -> str:
    """Wo es liegt, wie Calvin es nennen wuerde."""
    p = Path(pfad)
    for teil in p.parts:
        unten = teil.lower()
        if unten == "desktop":
            return "Desktop"
        if unten == "downloads":
            return "Downloads"
    if "eingang" in (t.lower() for t in p.parts):
        return "Eingang"
    return "sonstwo"


def _ziel(p: Path) -> str:
    """Worauf eine Verknuepfung zeigt - leer, wenn es keine ist."""
    endung = p.suffix.lower()
    if endung == ".url":
        return wahrnehmung._url_ziel(p)
    if endung == ".lnk":
        return wahrnehmung._lnk_ziel(p)
    return ""


def _enthaelt(heuhaufen: str, marken) -> bool:
    unten = heuhaufen.lower()
    return any(m in unten for m in marken)


def kategorie(pfad, satz: str = "") -> str:
    """In welche Gruppe gehoert diese Datei?

    Gerechnet, nicht gefragt. Das Modell formuliert spaeter den Satz ueber die
    Gruppe - aber WELCHE Gruppe es ist, darf nicht von seiner Laune abhaengen,
    sonst steht dieselbe Datei morgen in einer anderen.

    `satz` ist die schon vorhandene Beschreibung, falls es eine gibt. Nur sie
    unterscheidet ein Bildschirmfoto von einem Foto - am Dateinamen ist das
    nicht zu sehen.
    """
    p = Path(pfad)
    endung = p.suffix.lower()

    if endung in MODELL_ENDUNGEN:
        return "modell"
    if endung in ARCHIV_ENDUNGEN:
        return "archiv"

    art = wahrnehmung.art(p)

    if art == "verknuepfung":
        spur = f"{p.stem} {_ziel(p)}"
        if _enthaelt(spur, SPIEL_MARKEN):
            return "spiel"
        if _enthaelt(spur, WERKZEUG_MARKEN):
            return "werkzeug"
        return "verknuepfung"

    if art == "skript":
        # Ein Startskript IST ein Werkzeug, egal was es startet. Wenn der Name
        # ein Spiel verraet, gehoert es trotzdem zu den Spielen.
        spur = f"{p.stem} {_anlesen(p)}"
        if _enthaelt(spur, SPIEL_MARKEN):
            return "spiel"
        return "werkzeug"

    if art == "programm":
        if _enthaelt(p.stem, SPIEL_MARKEN):
            return "spiel"
        if _enthaelt(p.stem, WERKZEUG_MARKEN):
            return "werkzeug"
        return "programm"

    if art == "bild":
        # "Ein Bildschirmfoto, das ..." - genau so faengt die Beschreibung an,
        # die wahrnehmung.verstehen() vom Bildmodell verlangt.
        if satz and "bildschirmfoto" in satz.lower()[:40]:
            return "bildschirmfoto"
        return "bild"

    if art in ("dokument", "text"):
        return "dokument"
    if art == "grafik":
        return "bild"

    return "sonstiges"


def _anlesen(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return ""


def gruppieren(dateien, saetze: dict | None = None) -> dict:
    """Nach Ort und Gattung. Schluessel ist (ort, kategorie)."""
    saetze = saetze or {}
    gruppen: dict = {}
    for pfad in dateien:
        p = Path(pfad)
        schluessel = (ort(p), kategorie(p, saetze.get(str(p), "")))
        gruppen.setdefault(schluessel, []).append(p)
    return gruppen


# ------------------------------------------------------- Die Wache davor

# Saetze ueber Calvins Vorlieben statt ueber seinen Bestand. Genau die Grenze,
# die beim erfundenen Bildschirminhalt ueberschritten wurde: Zwoelf
# Horrorspiele heissen "er hat zwoelf Horrorspiele", nicht "er mag Horror".
VORLIEBE = ("mag ", "mag\n", "liebt", "bevorzugt", "am liebsten", "vorliebe",
            "lieblings", "begeistert", "fan von", "interessiert sich",
            "leidenschaft", "schwaermt", "steht auf", "praeferenz",
            "praeferiert", "findet gefallen")

# Und Saetze, die raten statt zu beobachten.
VERMUTUNG = ("vermutlich", "wahrscheinlich", "offenbar", "anscheinend",
             "scheint zu", "scheint er", "duerfte", "koennte darauf",
             "vermutet", "ich nehme an", "wohl eher", "moeglicherweise",
             "das deutet darauf", "laesst vermuten", "spricht dafuer, dass er")


# Zahlwoerter stehen in zeitwort.py, nicht hier. Sie werden an zwei Stellen
# gebraucht - dort fuer "in drei Tagen", hier gegen erfundene Anzahlen - und
# zwei Listen, die gleich zu halten sind, laufen auseinander. Gefunden hat das
# gpt-oss mit "insgesamt dreiundzwanzig Spielstarter", wo dreizehn lagen:
# wissen.mangel() sucht mit \d+ nach ZIFFERN und lief daran vorbei.
ZAHLWORT = zeitwort.ZAHLWORT
zahlen_ausgeschrieben = zeitwort.zahlen_ausgeschrieben


def zu_viele(satz: str, anzahl: int) -> str | None:
    """Nennt der Satz mehr Dinge, als es gibt?

    Ueber eine Gruppe von dreizehn Dateien kann man nicht dreiundzwanzig
    Aussagen treffen. Untergruppen DUERFEN kleiner sein - "dazu zwei
    Aufbauspiele" ist richtig und gehoert zu Stufe 3 -, aber nichts darf die
    Gruppe uebersteigen.
    """
    ziffern = {int(z) for z in re.findall(r"\b\d{1,6}\b", str(satz or ""))}
    for zahl in sorted(ziffern | zahlen_ausgeschrieben(satz)):
        if zahl > anzahl:
            return (f"nennt {zahl}, aber die Gruppe hat nur {anzahl} Dateien")
    return None


# Ein Satz, der ohne seinen Prompt nicht mehr steht. Er landet im Gedaechtnis
# und wird spaeter vorgelesen - "Sie stellen dreizehn Spielstarter bereit"
# sagt dann nicht mehr, wer "sie" sind.
OHNE_ANFANG = re.compile(
    r"^(sie|es|diese|dieser|dieses|der ordner|die gruppe|die dateien|"
    r"die liste|hier)\b", re.IGNORECASE)


def unvollstaendig(satz: str) -> str | None:
    """Steht dieser Satz auch allein, ein halbes Jahr spaeter?"""
    s = " ".join(str(satz or "").split())
    if OHNE_ANFANG.match(s):
        return (f"faengt mit einem Wort an, das sich auf den Prompt bezieht: "
                f"{s.split()[0]!r} - allein vorgelesen sagt es nichts")
    return None


# Zwecke, die er behaupten KANN - und die Spuren, die einen Zweck belegen.
# Steht keine dieser Spuren in den Dateinamen, ist der Zweck erfunden.
#
# Gemessen am 12.09.: "Im Downloads-Ordner liegen vorwiegend Audiodateien, die
# FUER DIE LOKALE BILDGENERIERUNG verwendet werden." Audiodateien werden nicht
# fuer Bildgenerierung verwendet. Dazu "animierte GIFs ... die die Vielfalt
# lokaler Bildgenerierung" und "12 Archive ... fuer lokale Bildbearbeitung".
# Der Zusammenhang stimmt bei den .safetensors und den ComfyUI-Startern - und
# genau deshalb haengt das Modell ihn ueberall an.
ZWECK_BELEG = {
    "bildgenerierung": ("comfyui", "swarmui", "diffusion", "stable", "sd_",
                        "sdxl", "safetensors", "lora", "vae", "a1111",
                        "forge", "automatic1111", "ckpt", "unet", "clip"),
    "bilderzeugung": ("comfyui", "swarmui", "diffusion", "stable", "sd_",
                      "sdxl", "safetensors", "lora", "vae", "ckpt"),
    "bildbearbeitung": ("photoshop", "gimp", "affinity", "krita", "paint",
                        "lightroom", "comfyui", "swarmui"),
    "sprachmodell": ("ollama", "llama", "gguf", "gpt", "mistral", "qwen",
                     "kobold", "lmstudio", "lm-studio", "claude", "mcp"),
    "videoschnitt": ("davinci", "premiere", "resolve", "vegas", "shotcut",
                     "ffmpeg", "obs"),
    "tonbearbeitung": ("audacity", "reaper", "ableton", "cubase", "wav",
                       "mp3", "flac", "whisper", "chatterbox"),
    "entwicklung": ("git", "python", "node", "vscode", "visual", "pycharm",
                    "docker", "compiler", "sdk", "runtime", "npm", "cargo"),
    "spiele": ("steam", "epic", "gog", "rockstar", "ubisoft", "launcher",
               "game"),
}


def ungegruendet(satz: str, dateien) -> str | None:
    """Behauptet der Satz einen Zweck, den die Dateien nicht hergeben?

    Eine Gruppe DARF benannt werden. Wozu sie DIENT, nur wenn es aus den
    Dateien selbst hervorgeht - sonst ist es erfundene Kausalitaet, dieselbe
    Grenze wie beim erfundenen Bildschirminhalt.
    """
    unten = " ".join(str(satz or "").split()).lower()
    spur = " ".join(Path(p).name for p in dateien).lower()
    for zweck, belege in ZWECK_BELEG.items():
        if zweck not in unten:
            continue
        if not any(b in spur for b in belege):
            return (f"behauptet {zweck!r}, aber keine der Dateien belegt es - "
                    f"erfundener Zusammenhang")
    return None


# Ein Satz, der ueber DEN ORDNER urteilt, statt ueber seine Gruppe. Sechs
# Gruppen in Downloads ergaben sechs Saetze, die alle "vorwiegend" ueber
# Downloads sagten - und jeder etwas anderes: vorwiegend Audiodateien,
# vorwiegend Installationsprogramme, ueberwiegend animierte GIFs. Jede Aussage
# hebt die vorige auf, also kann Calvin keiner glauben.
# Am ANFANG verankert, und das Mengenwort muss direkt auf das Verb folgen.
# Sonst faengt die Wache auch richtige Gruppensaetze: "Die zwoelf Archive in
# Downloads sind ueberwiegend ZIP-Pakete" redet ueber die Gruppe, nicht ueber
# den Ordner, und "Auf dem Desktop liegen acht Spielverknuepfungen,
# ueberwiegend Horror" nennt erst die Gruppe und dann ihr Ueberwiegendes.
UEBER_DEN_ORDNER = re.compile(
    r"^(im|in|in den|in der|auf dem)\s+[\w-]*"
    r"(downloads?|desktop|downloadbereich)[\w-]*\s+"
    r"(liegen|liegt|befinden sich|gibt es|enthält|enthaelt|sind)\s+"
    r"(vorwiegend|überwiegend|ueberwiegend|hauptsächlich|hauptsaechlich|"
    r"meist|mehrheitlich|in der mehrheit)",
    re.IGNORECASE)


def ueber_den_ordner(satz: str) -> str | None:
    """Urteilt dieser Satz ueber den ganzen Ordner, statt ueber seine Gruppe?

    Nur der Ueberblicksatz darf das - er sieht alle Gruppen. Ein Gruppensatz
    sieht nur seine eigene und kann darum nicht wissen, was ueberwiegt.
    """
    if UEBER_DEN_ORDNER.search(" ".join(str(satz or "").split())):
        return ("urteilt ueber den ganzen Ordner, kennt aber nur seine eigene "
                "Gruppe - das widerspricht den anderen Gruppen desselben Ortes")
    return None


# Wie ein Ort im Satz vorkommen kann. Der Ort steht im Auftrag, und trotzdem
# hat gpt-oss fuer drei Gruppen aus Downloads "Auf dem Desktop liegen ..."
# geschrieben - 17 GIFs, 16 Dokumente und 5 Starter auf den falschen Ordner
# gelegt. Plausibel, selbstbewusst, falsch.
ORTSWORTE = {
    "Desktop": ("desktop",),
    "Downloads": ("downloads", "download-ordner", "downloadordner",
                  "downloadbereich"),
    "Eingang": ("eingang",),
}


def falscher_ort(satz: str, ort_: str) -> str | None:
    """Nennt der Satz einen ANDEREN Ort als den, um den es geht?"""
    unten = " ".join(str(satz or "").split()).lower()
    eigene = ORTSWORTE.get(ort_, ())
    nennt_eigenen = any(w in unten for w in eigene)
    for fremd, woerter in ORTSWORTE.items():
        if fremd == ort_:
            continue
        if any(w in unten for w in woerter) and not nennt_eigenen:
            return (f"sagt {fremd!r}, aber die Gruppe liegt in {ort_!r} - "
                    f"der Fakt wuerde die Dateien an den falschen Ort legen")
    return None


def ungenau(satz: str) -> str | None:
    """Weicht der Satz aus, statt das Muster zu nennen?

    "Dreizehn Spielstarter fuer verschiedene Spiele" ist richtig und nuetzt
    nichts - es ist die Zahl ohne die Erkenntnis. Zurueckhalten ist hier
    besser als behalten: Beim naechsten Durchgang wird noch einmal gefragt,
    und bis dahin steht lieber nichts im Gedaechtnis als Stufe 2.
    """
    unten = " ".join(str(satz or "").split()).lower()
    for wort in UNGENAU:
        if wort in unten:
            return (f"weicht aus, statt das Ueberwiegende zu nennen: "
                    f"{wort!r} - das ist Stufe 2")
    return None


def saeubern(satz: str) -> str:
    """Anfuehrungszeichen und Auszeichnungen weg - der Satz wird vorgelesen."""
    s = " ".join(str(satz or "").split())
    s = re.sub(r'[*`_#]+', "", s)
    # Ein uebriggebliebenes Anfuehrungszeichen am Rand kam in der ersten
    # echten Antwort vor und wuerde mitgesprochen.
    return s.strip().strip('"“„”«»\'').strip()


def vermutet(satz: str) -> str | None:
    """Warum dieser Satz eine Behauptung statt einer Beobachtung ist.

    Das Modell soll sagen, WAS DA IST und WOZU es da ist. Es soll nicht aus
    einem Bestand auf einen Charakter schliessen. Der Systemtext sagt das
    auch - aber eine Regel im Systemtext ist eine Bitte, eine Wache davor ist
    eine Zusage. Dieselbe Bauart wie wissen.mangel().
    """
    unten = " ".join(str(satz or "").split()).lower()
    for wort in VORLIEBE:
        if wort in unten:
            return f"redet ueber {NAMENS} Vorlieben, nicht ueber den Bestand: {wort.strip()!r}"
    for wort in VERMUTUNG:
        if wort in unten:
            return f"vermutet, statt zu beobachten: {wort.strip()!r}"
    return None


# ------------------------------------------------------------- Das Modell

SYSTEM = f"""Du schreibst EINEN Satz ueber eine Gruppe von Dateien auf {NAMENS}
Rechner. Nicht ueber die einzelnen Dateien - ueber das MUSTER.

Was der Satz leisten muss:
  Was ist das, zusammengenommen?
  Was UEBERWIEGT darin? Das ist die Hauptsache. "Verschiedene", "diverse"
  oder "unterschiedliche" sind keine Antwort - sie sagen nur, dass es
  mehrere sind. Benenne das Muster.

  UND ES STEHT ZUERST, vor der Zahl. Der Satz wird spaeter auf zwei
  verschiedene Fragen hin vorgelesen: "Was liegt auf meinem Desktop?" und
  "Welche Art Spiele habe ich?". Faengt er mit "Auf dem Desktop liegen acht
  Dateien ..." an, bekommt {NAME} auf beide dieselbe Antwort, und auf die
  zweite eine falsche - er hat nach der ART gefragt, nicht nach der Anzahl.
  Also "Die Spiele sind ueberwiegend Horror und Shooter; es sind acht
  Verknuepfungen auf dem Desktop." und nicht umgekehrt.
  WOZU sind die Dinge da - aber NUR, wenn die Dateien selbst es hergeben.
  ComfyUI und SwarmUI sind Oberflaechen fuer lokale Bilderzeugung, kein
  "zwei bat-Dateien". Steht der Zweck NICHT in den Namen, sag nur, was es
  ist. Audiodateien werden nicht fuer Bildgenerierung verwendet, und ein
  Archiv ist kein Bildwerkzeug, bloss weil daneben eines liegt.

Du sprichst ueber DIESE Gruppe, nicht ueber den Ordner. Nicht "im Downloads-
Ordner liegen vorwiegend Archive" - du siehst nur deine Gruppe und weisst
nicht, was sonst dort liegt. Also: "Die zwoelf Archive in Downloads sind ..."

Was der Satz NICHT tun darf - das ist die wichtigere Haelfte:
  KEINE Aussage darueber, was {NAME} mag, bevorzugt oder liebt. Zwoelf
  Horrorspiele heissen "er hat zwoelf Horrorspiele", nicht "er mag Horror".
  Du siehst einen Bestand, keinen Charakter.
  KEIN vermutlich, wahrscheinlich, offenbar, scheint. Beobachten, nicht raten.
  KEINE Aufzaehlung der Dateinamen. Hoechstens drei als Beispiel.
  KEINE Zahl, die groesser ist als die Anzahl der Dateien. Zaehl nicht
  ungefaehr - die Anzahl steht im Auftrag, nimm sie von dort, und schreib
  keine andere, auch nicht ausgeschrieben.

Der Satz muss ALLEIN stehen. Er wird Monate spaeter vorgelesen, ohne diesen
Auftrag daneben. Fang darum nicht mit "Sie", "Es", "Diese", "Hier" oder "Die
Gruppe" an, sondern nenne die Sache: "Auf dem Desktop liegen ...",
"ComfyUI und SwarmUI sind ...".

Hoechstens zwei Saetze, schlichtes Deutsch, keine Auszeichnungen und keine
Anfuehrungszeichen - er wird vorgelesen.

Antworte als JSON: {{"satz": "..."}}"""


def _fragen(nachrichten: list) -> dict:
    r = httpx.post(OLLAMA, timeout=300, json={
        "model": MODELL, "stream": False, "keep_alive": "5m",
        "think": "low", "format": "json", "messages": nachrichten})
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


def _namen(dateien) -> str:
    namen = [Path(p).name for p in dateien[:NAMEN_HOECHSTENS]]
    rest = len(dateien) - len(namen)
    text = "\n".join(f"  {n}" for n in namen)
    if rest > 0:
        text += f"\n  ... und {rest} weitere"
    return text


def _endungen(dateien) -> str:
    """Wie viele wovon - damit das Modell nicht abzaehlen muss."""
    zaehler: dict = {}
    for p in dateien:
        e = Path(p).suffix.lower() or "(ohne Endung)"
        zaehler[e] = zaehler.get(e, 0) + 1
    return ", ".join(f"{n}x {e}" for e, n
                     in sorted(zaehler.items(), key=lambda x: -x[1]))


def _quelle(ort_: str, kat: str, dateien) -> str:
    """Das Material, gegen das die Wachen pruefen.

    Die Anzahl gehoert hinein: wissen.mangel() laesst keine Zahl durch, die
    nicht in der Quelle steht - und "zwoelf Spielverknuepfungen" ist eine
    richtige Zahl, die der Bestand hergibt.
    """
    moegliche = " ".join(str(i) for i in range(len(dateien) + 1))
    return (f"Ort {ort_}, Gattung {kat}, {len(dateien)} Dateien.\n"
            f"Zulaessige Zahlen: {moegliche}\n{_namen(dateien)}")


UEBERBLICK = f"""Du ordnest einen Ordner auf {NAMENS} Rechner als GANZES ein.

Du bekommst, was darin liegt, nach Gattung gezaehlt. Schreibe EINEN Satz: was
ueberwiegt, was kommt danach. Hier DARFST du "vorwiegend" sagen - du siehst
alle Gruppen. Nenne die zwei oder drei groessten, nicht alle.

Keine erfundenen Zwecke: Sag, was da ist, nicht wozu es gut sein koennte.
Keine Aussage darueber, was {NAME} mag. Keine Zahl, die nicht dasteht.
Der Satz muss allein stehen - nenne den Ordner beim Namen.

Antworte als JSON: {{"satz": "..."}}"""


def ueberblick_fuer(ort_: str, gruppen: dict, fragen=None) -> tuple[str, str]:
    """EIN Satz, der den Ordner als Ganzes einordnet.

    Den braucht es, weil ein Gruppensatz es NICHT darf: Sechs Gruppen in
    Downloads ergaben sechs Saetze, die alle "vorwiegend" ueber Downloads
    urteilten - sechsmal etwas anderes. Nur wer alle Gruppen sieht, kann
    sagen, was ueberwiegt.
    """
    zaehlung = sorted(((kat, len(d)) for (o, kat), d in gruppen.items()
                       if o == ort_), key=lambda x: -x[1])
    if len(zaehlung) < 2:
        return "", "nur eine Gattung - dafuer braucht es keinen Ueberblick"
    gesamt = sum(n for _, n in zaehlung)
    liste = "\n".join(f"  {n}x {GRUPPENNAME.get(k, k)}" for k, n in zaehlung)
    quelle = (f"Ordner {ort_}, {gesamt} Dateien.\n"
              f"Zulaessige Zahlen: "
              f"{' '.join(str(i) for i in range(gesamt + 1))}\n{liste}")
    auftrag = f"Ordner: {ort_}\n{gesamt} Dateien insgesamt.\n\n{liste}"

    stelle = fragen or _fragen
    try:
        antwort = stelle([{"role": "system", "content": UEBERBLICK},
                          {"role": "user", "content": auftrag}])
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as f:
        return "", f"Modell stumm ({type(f).__name__})"

    satz = saeubern((antwort or {}).get("satz") or "")
    if not satz:
        return "", "Modell ohne Satz"
    # ueber_den_ordner() gilt hier NICHT - das ist genau seine Aufgabe.
    for wache in (vermutet, unvollstaendig):
        grund = wache(satz)
        if grund:
            return "", grund
    grund = zu_viele(satz, gesamt)
    if grund:
        return "", grund
    grund = wissen.mangel(satz, quelle, zeichen_max=ZUSAMMENSCHAU_ZEICHEN_MAX)
    if grund:
        return "", grund
    return satz, ""


def satz_fuer(ort_: str, kat: str, dateien, fragen=None) -> tuple[str, str]:
    """Ein Satz ueber diese Gruppe - oder ("", Grund).

    `fragen` wird hereingegeben, nicht ueber die Leitung geholt. Der Grund
    steht in archiv.zusammenfassen() und war ein echter Fehler: Eine Probe
    meldete monatelang "bestanden" fuer einen Aufruf, den es im Betrieb nicht
    gab.
    """
    if len(dateien) < GRUPPE_MIN:
        return "", f"nur {len(dateien)} Dateien - ein Zufall, kein Muster"

    quelle = _quelle(ort_, kat, dateien)
    auftrag = (f"{len(dateien)} Dateien, Gattung: "
               f"{GRUPPENNAME.get(kat, kat)}, Ort: {ort_}.\n"
               # Die Zusammensetzung ausdruecklich, nicht zum Abzaehlen
               # ueberlassen: gpt-oss schrieb "vier Startskripte und eine
               # Verknuepfung" fuer drei Skripte und eine Verknuepfung.
               f"Zusammensetzung: {_endungen(dateien)}\n\n"
               f"{WAS_UEBERWIEGT.get(kat, 'Was ueberwiegt darin?')}\n\n"
               f"Namen:\n{_namen(dateien)}")
    stelle = fragen or _fragen

    def pruefen(satz: str) -> str | None:
        for wache in (vermutet, unvollstaendig, ungenau, ueber_den_ordner):
            grund = wache(satz)
            if grund:
                return grund
        for grund in (zu_viele(satz, len(dateien)),
                      ungegruendet(satz, dateien),
                      falscher_ort(satz, ort_)):
            if grund:
                return grund
        # wissen.mangel() prueft ausserdem Laenge, Saetze ueber sich selbst und
        # Ziffern, die in der Quelle fehlen. Die Quelle nennt darum
        # ausdruecklich alle Zahlen von 0 bis zur Gruppengroesse: Eine
        # Untergruppe ("dazu zwei Aufbauspiele") ist eine richtige Zahl, die
        # der Bestand hergibt, und zu_viele() hat schon abgefangen, was
        # darueber liegt.
        return wissen.mangel(satz, quelle,
                             zeichen_max=ZUSAMMENSCHAU_ZEICHEN_MAX)

    # EINMAL nachfragen, wenn eine Wache zuschlaegt. Zurueckhalten ist besser
    # als einen falschen Fakt behalten - aber die groesste Gruppe ganz zu
    # verlieren, weil das Modell mit "Diese" angefangen hat, ist zu teuer.
    # Genau das ist passiert: der Satz ueber dreizehn Spielverknuepfungen fiel
    # aus, obwohl nur der Satzanfang nicht taugte.
    letzter_grund = ""
    nachrichten = [{"role": "system", "content": SYSTEM},
                   {"role": "user", "content": auftrag}]
    for versuch in (1, 2):
        try:
            antwort = stelle(nachrichten)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError,
                ValueError) as f:
            # Stumm geblieben. Die Marke bleibt offen, damit es ein naechstes
            # Mal gibt - die Unterscheidung zwischen "" und null aus B.
            return "", f"Modell stumm ({type(f).__name__})"

        satz = saeubern((antwort or {}).get("satz") or "")
        if not satz:
            return "", "Modell ohne Satz"
        letzter_grund = pruefen(satz) or ""
        if not letzter_grund:
            return satz, ""
        if versuch == 2:
            break
        nachrichten = nachrichten + [
            {"role": "assistant", "content": satz},
            {"role": "user",
             "content": f"Dieser Satz geht so nicht: {letzter_grund}. "
                        f"Schreib ihn neu und halte dich genau daran. "
                        f"Derselbe Inhalt, nur richtig."}]
    return "", f"{letzter_grund} (auch nach Nachfrage)"


def zusammenschau(dateien, saetze: dict | None = None,
                  fragen=None) -> tuple[list[dict], list[str]]:
    """Aus dem ganzen Bestand ein paar Saetze. Einer je Gruppe.

    Gibt (erkenntnisse, zurueckgehalten) zurueck. Eine Erkenntnis traegt ihren
    Gruppenschluessel mit - daran haengt das Ueberholen im Gedaechtnis.
    """
    gruppen = gruppieren(dateien, saetze)
    erkenntnisse, zurueck = [], []

    # Erst EIN Ueberblick je Ort. Er sieht alle Gruppen und darf darum sagen,
    # was ueberwiegt - was kein Gruppensatz darf.
    for ort_ in sorted({o for o, _ in gruppen}):
        satz, grund = ueberblick_fuer(ort_, gruppen, fragen=fragen)
        if satz:
            erkenntnisse.append({
                "ort": ort_, "kategorie": "ueberblick", "satz": satz,
                "anzahl": sum(len(d) for (o, _), d in gruppen.items()
                              if o == ort_),
                "schluessel": schluessel_fuer(ort_, "ueberblick")})

    # Die groessten Gruppen zuerst: Dort steht das Muster, das am meisten sagt.
    for (ort_, kat), dateien_der_gruppe in sorted(
            gruppen.items(), key=lambda g: -len(g[1])):
        if kat == "sonstiges":
            # Eine Restegruppe heisst "nicht einzuordnen". Ueber sie kann es
            # kein Muster geben, und genau dort hat das Modell eines erfunden:
            # "vorwiegend Audiodateien, die fuer die lokale Bildgenerierung
            # verwendet werden". Also gar nicht fragen.
            continue
        satz, grund = satz_fuer(ort_, kat, dateien_der_gruppe, fragen=fragen)
        if satz:
            erkenntnisse.append({
                "ort": ort_, "kategorie": kat, "satz": satz,
                "anzahl": len(dateien_der_gruppe),
                "schluessel": schluessel_fuer(ort_, kat)})
        elif len(dateien_der_gruppe) >= GRUPPE_MIN:
            # Kleine Gruppen sind kein Fehlschlag, die muessen nicht gemeldet
            # werden. Eine zurueckgehaltene grosse schon.
            zurueck.append(f"{ort_}/{kat} ({len(dateien_der_gruppe)}): {grund}")
    return erkenntnisse, zurueck


def schluessel_fuer(ort_: str, kat: str) -> str:
    """Der Gruppenschluessel, unter dem die Erkenntnis im Gedaechtnis liegt.

    Stabil, weil das Ueberholen daran haengt: Wird die Gruppe spaeter groesser,
    soll die neue Erkenntnis die alte ERSETZEN, nicht neben sie treten.
    """
    return f"zuhause:{ort_.lower()}:{kat}"


# --------------------------------------------------------------- Durchgang


def _zustand() -> dict:
    try:
        return json.loads(ZUSTAND.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _zustand_schreiben(d: dict) -> None:
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    t = ZUSTAND.with_suffix(".json.tmp")
    t.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(t, ZUSTAND)


def faellig(anzahl_jetzt: int, jetzt: float | None = None,
            letzte_aenderung: float | None = None) -> bool:
    """Lohnt eine Zusammenschau?

    Zwei Bedingungen, und beide sind noetig:
      - es sind genug Dateien dazugekommen (ZUWACHS_MIN), und
      - es ist eine Weile ruhig (RUHE_S).

    Ohne die Ruhe schaut er mitten in den Lernlauf hinein und fasst drei von
    hundertfuenfzig Dateien zusammen. Ohne den Zuwachs fragt er das Modell
    fuer jede einzelne neue Datei noch einmal nach allen Gruppen.
    """
    jetzt = time.time() if jetzt is None else jetzt
    z = _zustand()
    # Die Ruhe gilt immer. Auch liegengebliebene Arbeit wird nicht mitten in
    # einen laufenden Durchgang hinein nachgeholt.
    if letzte_aenderung is not None and jetzt - letzte_aenderung < RUHE_S:
        return False
    # Liegt etwas im Zustand, das nie im Gedaechtnis angekommen ist? Dann gibt
    # es Arbeit, ganz gleich ob Dateien dazugekommen sind. Ohne diese Zeile
    # blieben die sieben Gruppen, die ein Trockenlauf vermerkt hat, fuer immer
    # liegen: Der Zuwachs war null, also wurde nie wieder zusammengeschaut.
    for eintrag in (z.get("gruppen") or {}).values():
        if not (eintrag or {}).get("id"):
            return True
    vorher = int(z.get("anzahl") or 0)
    return anzahl_jetzt - vorher >= ZUWACHS_MIN


def durchgang(jetzt: float | None = None, fragen=None, merken=None,
              journal=None, dateien=None, saetze=None,
              veralten=None) -> dict:
    """Einmal zusammenschauen und das Ergebnis ins Gedaechtnis legen.

    Nach der Regel aus C.1: festgehalten wird, was NEU ist. Derselbe Satz
    zweimal legt nichts an (das faengt gedaechtnis.merken woertlich ab), und
    ein geaenderter Satz ERSETZT den alten derselben Gruppe, statt neben ihn
    zu treten - ueberholen, nicht loeschen.
    """
    jetzt = time.time() if jetzt is None else jetzt
    if dateien is None:
        dateien = wahrnehmung.bekannte_dateien()
    if saetze is None:
        saetze = _beschreibungen()

    erkenntnisse, zurueck = zusammenschau(dateien, saetze, fragen=fragen)

    # Ohne `merken` ist das ein TROCKENLAUF: rechnen, zeigen, nichts behalten.
    # Hier wurde erst der Zustand fortgeschrieben und dabei "7 gemerkt"
    # gemeldet, obwohl nichts gemerkt wurde - der naechste echte Lauf haette
    # alle sieben fuer "unveraendert" gehalten und NIE ins Gedaechtnis gelegt.
    # Ein Trockenlauf, der den Zustand aendert, ist keiner.
    trocken = merken is None
    z = _zustand()
    bekannt = dict(z.get("gruppen") or {})
    gemerkt, unveraendert = 0, 0

    for e in erkenntnisse:
        schluessel = e["schluessel"]
        alt = bekannt.get(schluessel) or {}
        if alt.get("satz") == e["satz"] and alt.get("id"):
            # Wortgleich UND wirklich im Gedaechtnis - nichts Neues. C.1.
            unveraendert += 1
            continue
        # Ohne Kennung ist der Satz nie angekommen: Ein Trockenlauf hat ihn
        # vermerkt, oder merken() ist gescheitert. Dann gilt er nicht als
        # bekannt, sonst stuende er fuer immer im Zustand und nie im
        # Gedaechtnis. Genau das ist am 12.09. passiert.
        kennung = None
        if not trocken:
            # Die Kennung MUSS mitgeschrieben werden. Ohne sie stand beim
            # naechsten Mal `ersetzt=None` im Aufruf, und die neue Erkenntnis
            # trat neben die alte statt sie zu ueberholen - nach einer Woche
            # lagen sieben Saetze ueber denselben Desktop im Gedaechtnis.
            kennung = merken("zuhause", e["satz"], schluessel, alt.get("id"))
        gemerkt += 1
        bekannt[schluessel] = {"satz": e["satz"], "anzahl": e["anzahl"],
                               "ts": jetzt, "id": kennung}

    # Eine Gruppe, die es nicht mehr gibt, darf ihren Fakt nicht behalten.
    # `sonstiges` wird seit heute gar nicht mehr gefragt - der Satz "vorwiegend
    # Audiodateien, die fuer die lokale Bildgenerierung verwendet werden" waere
    # sonst fuer immer stehen geblieben, weil ihn nie wieder etwas ersetzt.
    # Ueberholen, nicht loeschen: dieselbe Marke wie in F.1.
    noch_da = {e["schluessel"] for e in erkenntnisse}
    veraltet = []
    for schluessel, eintrag in list(bekannt.items()):
        if schluessel in noch_da:
            continue
        veraltet.append(schluessel)
        if not trocken:
            if veralten is not None and (eintrag or {}).get("id"):
                veralten(eintrag["id"])
            bekannt.pop(schluessel, None)

    if not trocken:
        z["gruppen"] = bekannt
        z["anzahl"] = len(dateien)
        z["zuletzt"] = jetzt
        _zustand_schreiben(z)

    bericht = {"dateien": len(dateien), "gruppen": len(erkenntnisse),
               "gemerkt": 0 if trocken else gemerkt,
               "waere_gemerkt": gemerkt,
               "unveraendert": unveraendert, "trocken": trocken,
               "veraltet": veraltet,
               "zurueckgehalten": zurueck,
               "erkenntnisse": [e["satz"] for e in erkenntnisse]}
    if journal is not None:
        for e in erkenntnisse:
            journal("bestand", e["satz"])
        for grund in zurueck:
            journal("bestand_zurueck", grund)
    return bericht


def _beschreibungen() -> dict:
    """Die schon vorhandenen Saetze ueber einzelne Dateien, nach Pfad.

    Nur sie unterscheiden ein Bildschirmfoto von einem Foto. Fehlen sie,
    landen beide in "bild" - schlechter, aber nicht falsch.

    Zwei Quellen, und das ist Absicht: Die Datei ist der Weg von heute an.
    Das Gedaechtnis wird noch mitgelesen, weil dort aus der Zeit vor dieser
    Aenderung Saetze der Art `datei` liegen - die sollen nicht verfallen, nur
    weil der Weg sich geaendert hat. Neue kommen dort nicht mehr hinzu.
    """
    alle: dict = {}
    try:
        import gedaechtnis
        with gedaechtnis._verbindung() as v:
            zeilen = v.execute(
                "SELECT quelle, text FROM erinnerung WHERE art='datei' "
                "AND quelle <> '' AND ersetzt_durch IS NULL").fetchall()
        alle.update({str(q): str(t) for q, t in zeilen})
    except Exception:
        pass
    alle.update(wahrnehmung.beschreibungen())
    return alle


def merker(gedaechtnis_modul=None):
    """Der Weg ins Gedaechtnis - mit Ueberholen statt Danebenlegen."""
    if gedaechtnis_modul is None:
        import gedaechtnis as gedaechtnis_modul

    def merken(art, text, quelle, ersetzt=None):
        return gedaechtnis_modul.merken(art, text, quelle=quelle,
                                       ersetzt=ersetzt)
    return merken


def veralter(gedaechtnis_modul=None):
    """Setzt die Marke aus F.1 - ueberholt, ohne Nachfolger, nicht geloescht."""
    if gedaechtnis_modul is None:
        import gedaechtnis as gedaechtnis_modul

    def veralten(kennung):
        with gedaechtnis_modul._sperre, gedaechtnis_modul._verbindung() as v:
            v.execute("UPDATE erinnerung SET ersetzt_durch=0 "
                      "WHERE id=? AND ersetzt_durch IS NULL", (int(kennung),))
    return veralten


def main() -> int:
    """Von Hand: einmal zusammenschauen und zeigen, ohne etwas zu merken."""
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--merken", action="store_true",
                   help="das Ergebnis wirklich ins Gedaechtnis legen")
    a = p.parse_args()

    dateien = wahrnehmung.bekannte_dateien()
    print(f"{len(dateien)} bekannte Dateien")
    gruppen = gruppieren(dateien, _beschreibungen())
    for (ort_, kat), d in sorted(gruppen.items(), key=lambda g: -len(g[1])):
        zeichen = "->" if len(d) >= GRUPPE_MIN else "  "
        print(f"  {zeichen} {ort_:10} {kat:16} {len(d):4}")

    bericht = durchgang(merken=merker() if a.merken else None,
                        veralten=veralter() if a.merken else None)
    print()
    for satz in bericht["erkenntnisse"]:
        print(f"  {satz}")
    for grund in bericht["zurueckgehalten"]:
        print(f"  (zurueckgehalten) {grund}")
    if bericht["trocken"]:
        print(f"\nTROCKENLAUF: {bericht['waere_gemerkt']} waeren gemerkt "
              f"worden, nichts geschrieben. Mit --merken wirklich merken.")
    else:
        print(f"\n{bericht['gemerkt']} gemerkt, "
              f"{bericht['unveraendert']} unveraendert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
