"""wuensche - was ihm fehlt, sauber eingeordnet.

    python wuensche.py --pruefen "Text"   ist das ueberhaupt ein Wunsch?
    python wuensche.py --liste            was offen ist
    python wuensche.py --selbsttest

In Stufe 4 hat er sich gewuenscht, was er laengst hatte - "Zugriff auf
GPU-Werte", obwohl selbst.py genau das misst. Ein Wunsch, den man schon
erfuellt hat, ist kein Wunsch, sondern ein Zeichen, dass man sich nicht kennt.

Deshalb prueft dieses Werkzeug ZUERST gegen das, was er kann, und ordnet dann
ein, was wirklich fehlt:

    KANN_ICH_SCHON  kein Wunsch - das Werkzeug gibt es
    WISSEN          er weiss nur nicht wie -> Werkzeug bauen lassen,
                    kein Antrag an Calvin
    RECHT           er duerfte nicht -> Antrag an Calvin
    GERAET          es fehlt Hardware -> Antrag
    GELD            es kostet -> Antrag

Nur was RECHT, GERAET oder GELD braucht, geht als Antrag an Calvin. Alles
andere kann er selbst.

Pfade haengen am Ort dieser Datei. Nur Standardbibliothek, kein Netz.
"""

from einstellungen import NAME, NAMENS
import argparse
import json
import os
import re
import sys

WERKZEUG_ORDNER = os.path.dirname(os.path.abspath(__file__))
WERKSTATT_ORDNER = os.path.dirname(WERKZEUG_ORDNER)
VERZEICHNIS = os.path.join(WERKSTATT_ORDNER, "werkzeuge.json")
# Zweite Liste, seit dem Brueckenwechsel: siebzehn Faehigkeiten, die nicht
# aufrufbar, sondern eingebaut sind. Der Filter kannte nur die Werkzeuge und
# hat deshalb Wuensche durchgelassen, die eine Faehigkeit laengst erfuellt -
# "ein Skript, das Llama-Server ohne Elternprozess beendet" ist genau das,
# was Selbstwahrnehmung sieht und das genehmigte Recht tut.
FAEHIGKEITEN = os.path.join(WERKSTATT_ORDNER, "faehigkeiten.json")
LISTE = os.path.join(WERKSTATT_ORDNER, "wuensche.json")

# "Zugriff auf" steht hier NICHT: Es ist zu mehrdeutig. "Zugriff auf die
# Werte der Grafikkarte" hat er laengst - das waere faelschlich als fehlendes
# Recht durchgegangen. Ein Recht erkennt man an "duerfen", nicht am Thema.
# "genehmig" fehlte, und er schrieb "Genehmigung, die Firewall zu
# deaktivieren" - ein Recht, das als WISSEN durchging, also als etwas, das er
# sich selbst bauen lassen darf. Auch hier kein \b am Ende: Genehmigung,
# genehmigen, Berechtigungen.
RECHT = re.compile(
    r"\b(darf|duerfen|dürfen|erlaubnis|berechtigung|recht|freigabe|"
    r"genehmig|befugnis|admin)", re.IGNORECASE)
# Der Arbeitsspeicher fehlte, und "ein kleiner Speichererweiterer (RAM-Stick),
# damit die Log-Dateien nicht mehr so viel Speicher beanspruchen" ging als
# WISSEN durch - als etwas, das er sich selbst bauen lassen kann. Ein Riegel
# ist nichts, was man sich baut.
GERAET = re.compile(
    r"\b(kamera|mikrofon|lautsprecher|sensor|festplatte|grafikkarte|"
    r"hardware|geraet|gerät|kabel|bildschirm|arbeitsspeicher|ram|"
    r"speicherriegel|netzteil|lüfter|luefter|ssd)\b", re.IGNORECASE)

# Etwas, das Calvin in die Hand nehmen und anschliessen muss.
HARDWARE = re.compile(
    r"\b(kamera|mikrofon|lautsprecher|sensor|fühler|fuehler|festplatte|"
    r"grafikkarte|kabel|bildschirm|monitor|display|akku|drucker|antenne|"
    r"messgerät|messgeraet|thermostat|platine|hardware|arbeitsspeicher|ram|"
    r"speicherriegel|netzteil|lüfter|luefter|ssd)", re.IGNORECASE)

# "Gerät" sagt er auch zu Programmen. Am 12.09. um 10:50 wuenschte er sich
# "ein Gerät, das mir eine Warnung anzeigt" - das ist kein Geraet, das ist
# ein Programm, und es waere als fehlende Hardware bei Calvin gelandet. Ein
# Ding, das nur ANZEIGT oder MELDET, was der Rechner schon weiss, braucht
# keine Hardware. Ein Ding, das etwas an der WELT misst, schon.
ANZEIGEN = re.compile(
    r"\b(anzeig|zeigt|zeige|meld|warn|benachrichtig|mitteil|informier|"
    r"darstell|visualisier|zusammenfass|auflist|protokollier|"
    r"übersicht|uebersicht|alarm|überwach|ueberwach|beobacht|erkenn)",
    re.IGNORECASE)

# Aber messen ist nicht anzeigen. Ein Ding, das den WLAN-Rauschpegel oder eine
# Temperatur MISST, holt etwas herein, das der Rechner nicht hat - das bleibt
# ein Geraet, auch wenn es danach "Alarm" gibt.
MESSEN = re.compile(
    r"\b(miss|mess|erfass|fühl|fuehl|temperatur|rauschpegel|lautstärke|"
    r"lautstaerke|helligkeit|feuchtigkeit|luftdruck|pegel)", re.IGNORECASE)
# Kein \b am Ende: "kostenpflichtiger" ist eine Kostenangabe, ging aber als
# "kein Geld genannt" durch und landete unter WISSEN, waehrend die
# Ueberschrift GELD sagte. Deutsch setzt Woerter zusammen, der Filter muss
# das aushalten.
GELD = re.compile(
    r"\b(kostet|kosten|kostenpflicht|abo|bezahl|lizenz|euro|tarif|kauf|"
    r"gebuehr|gebühr|preis)", re.IGNORECASE)

# Die Ueberschrift, die er seinen Wuenschen selbst gibt: "GELD: Fuer einen
# ...". Sie stand bisher unbeachtet im Satz, waehrend darunter die Einordnung
# des Filters klebte - zweimal ein Etikett, und bei zwei von sechs Wuenschen
# widersprachen sie sich.
UEBERSCHRIFT = re.compile(
    r"^[-*\s]*(?:\d+[.)]\s*)?(?:Wunsch\s*\d*\s*[:\-–]\s*)?"
    r"(RECHT|GERAET|GERÄT|GELD|WISSEN)\s*[:\-–]\s*", re.IGNORECASE)

# Er numeriert auch ohne Etikett: "1. Wunsch: Genehmigung, die Firewall zu
# deaktivieren." Die Nummer gehoert nicht in Calvins Liste, und der Satz
# dahinter soll eingeordnet werden wie jeder andere.
NUMERIERUNG = re.compile(
    r"^[-*\s]*(?:\d+[.)]\s*)?(?:Wunsch\s*\d*\s*[:\-–]\s*)", re.IGNORECASE)

# Striche, die aussehen wie ein Bindestrich, aber keiner sind. Das Modell
# schreibt "Llama‑Server" mit U+2011; das Stichwort "llama-server" traf
# deshalb nicht, und der Wunsch, den ein genehmigtes Recht schon erfuellt,
# stand weiter auf der Liste.
STRICHE = "‐‑‒–—―−"
LEERE = "   "


# Ein Satz, der einen Mangel BESTREITET, ist kein Wunsch. Am 12.09. um 10:30
# schrieb er fuenf davon - "Ich habe keine zusaetzlichen Genehmigungen
# erbeten, weil meine bestehenden Rechte alle mir benoetigten Taetigkeiten
# abdeckten" - und der Filter machte daraus "Es fehlt: Recht - Antrag an
# Calvin". Genau umgekehrt. Die Verneinung muss VOR dem Verb stehen: "ich
# weiss nicht wie" und "ich kann es nicht" sind echte Wuensche und bleiben.
VERNEINT = re.compile(
    r"\b(kein\w*|nichts)\b[^.!?]{0,70}?\b(bedarf|mangel|noetig|nötig|"
    r"gestellt|gekauft|installiert|beantragt|erbeten|gebraucht|"
    r"benoetigt|benötigt|vermisst|bemerkt|gefehlt|fehlt|fehlte|"
    r"aufgefallen|vorlag|verlangt)\b"
    r"|\b(bereits|schon)\b[^.!?]{0,40}?\b(erfuellt|erfüllt|abgedeckt|"
    r"vorhanden|erledigt)\b"
    r"|\babdeck(t|te|ten|en)\b"
    r"|\bfehlt\b[^.!?]{0,25}?\bnichts\b", re.IGNORECASE)


def _glatt(text):
    """Sonderstriche und Sonderleerzeichen auf das Gewoehnliche bringen."""
    t = str(text)
    for z in STRICHE:
        t = t.replace(z, "-")
    for z in LEERE:
        t = t.replace(z, " ")
    return " ".join(t.split())


def _aus_datei(datei):
    """Name -> Zweck aus einer der beiden Listen. Fehlt sie, ist sie leer."""
    try:
        with open(datei, "r", encoding="utf-8") as f:
            roh = json.load(f)
    except (OSError, ValueError):
        return {}
    liste = roh if isinstance(roh, list) else [
        dict(w, name=n) for n, w in roh.items()]
    d = {}
    for w in liste:
        if isinstance(w, dict) and w.get("name"):
            d[str(w["name"])] = str(w.get("zweck") or "")
    return d


def koennen():
    """Was er schon kann - aus BEIDEN Listen plus dem Festen.

    werkzeuge.json sind die zehn, die er aufrufen kann. faehigkeiten.json sind
    die siebzehn, die in ihm eingebaut sind. Bis hierher las dieser Filter nur
    die erste Datei. Ein Wunsch wie "ein Skript, das Llama-Server ohne
    Elternprozess beendet" traf kein Werkzeug - aber die Faehigkeit
    "Selbstwahrnehmung" sieht genau diese Reste, und "Den Dienst neu starten"
    ist das genehmigte Recht dazu. Er wuenschte sich, was er hat, weil der
    Pruefer die Haelfte seiner selbst nicht kannte.
    """
    fest = {
        "selbst messen": "tok/s, Grafikspeicher, verwaiste Prozesse, Ticks",
        "lagebild": "Uhrzeit, Tagesphase, Plattenplatz, Geräte im Netz",
        "gedaechtnis": "merken, abrufen, vergessen, korrigieren",
        "antraege": f"Anträge an {NAME} stellen",
    }
    fest.update(_aus_datei(VERZEICHNIS))
    fest.update(_aus_datei(FAEHIGKEITEN))
    return fest


# Stichwoerter je Faehigkeit. Der blosse Wortvergleich reicht nicht: "ein
# Werkzeug, das Ollama ueberwacht" teilt kein Wort mit "selbst messen", und
# genau dieser Wunsch stand faelschlich auf der Liste.
STICHWORTE = {
    "selbst messen": ("ollama", "überwach", "ueberwach", "tok/s", "token",
                      "grafikspeicher", "gpu", "tempo", "verwaist", "waise",
                      "llama-server", "auslastung", "geteilt"),
    "lagebild": ("heimnetz", "netzwerk", "geräte", "geraete", "registrier",
                 "übersicht", "uebersicht", "plattenplatz", "uhrzeit",
                 "tagesphase"),
    "netz": ("heimnetz", "netzwerk", "geräte", "geraete", "wer ist im netz"),
    "gedaechtnis": ("merken", "erinnern an frueher", "vergessen",
                    "gedächtnis", "gedaechtnis"),
    "erinnern": ("termin", "erinner", "wecken", "zur rechten zeit"),
    # "sehen" allein waere zu weit: "eine Kamera, um zu sehen, wer im Raum
    # ist" braucht Hardware und ist kein Bildschirmfoto.
    "sehen": ("bildschirm", "bildschirmfoto", "screenshot", "bild ansehen"),
    "lesen": ("pdf", "dokument lesen", "text auswerten"),
    "stimme_hoeren": ("tonhöhe", "tonhoehe", "klangfarbe", "stimme messen"),
    "rhythmus": ("muster", "gewohnheit", "üblich", "ueblich", "tageslauf"),
    "auftrag": ("claude beauftragen", "auftrag formulieren"),
}


# Woerter, die in jedem zweiten deutschen Satz stehen. Sie duerfen nie zu
# einem Treffer beitragen: "etwas", "meiner", "wenn" verbinden jeden Wunsch
# mit jeder Faehigkeit, und mit den siebzehn langen Zwecksaetzen aus
# faehigkeiten.json waere daraufhin JEDER Wunsch weggefallen.
FUELLWOERTER = frozenset("""
aber allem allen aller alles also andere anderem anderen anderes auch auf
beide beides beim bereits besser damit dann darauf daraus darin darueber
darüber dass dazu dein deine dem den denen denn der des dessen dich dies
diese diesem diesen dieser dieses doch dort durch eigene eine einem einen
einer eines einfach endlich erst etwas fuer für ganz gegen gerade gern gibt
gleich habe haben hast hatte ich ihm ihn ihr immer jede jedem jeden jeder
jedes jetzt kann kannst koennen können lassen mehr mein meine meinem meinen
meiner mich mir mit nach nicht nichts noch nur oder ohne schon sein seine
selbst sich sind sodass soll sollte sondern sonst statt taeglich täglich ueber
über und viel vielleicht vom von wann warum was wegen weil weiter welche wenn
wer werde werden wieder will wird wirklich wollte wuerde würde zeigt zum zur
""".split())

# Wie viele Eintraege ein Wort teilen darf, um noch etwas zu bedeuten. Steht
# ein Wort in mehr als jedem vierten Zwecksatz, unterscheidet es nichts.
UNAUFFAELLIG_ANTEIL = 0.25

# So viele bedeutsame Woerter muessen zusammenkommen. Eines reicht nicht:
# "Platz" allein verbindet den Plattenplatz mit dem Grafikspeicher.
TREFFER_NOETIG = 2


def _inhaltswoerter(text):
    """Woerter ab vier Buchstaben, ohne Fuellwoerter."""
    klein = _glatt(text).lower()
    return set(w for w in re.findall(r"[a-zäöüß]{4,}", klein)
               if w not in FUELLWOERTER)


def _kennwoerter(vorhanden):
    """Je Faehigkeit die Woerter, die nur sie hat.

    Ohne diesen Schritt zaehlt "Calvin" als Treffer - der Name steht in acht
    von siebzehn Zwecksaetzen und sagt nichts darueber, ob eine Faehigkeit
    einen Wunsch deckt.
    """
    proe = {n: _inhaltswoerter(n + " " + z) for n, z in vorhanden.items()}
    wie_oft = {}
    for worte in proe.values():
        for w in worte:
            wie_oft[w] = wie_oft.get(w, 0) + 1
    grenze = max(1, int(len(proe) * UNAUFFAELLIG_ANTEIL))
    return {n: set(w for w in worte if wie_oft[w] <= grenze)
            for n, worte in proe.items()}


def kann_ich_schon(text):
    """Deckt eine vorhandene Faehigkeit den Wunsch bereits ab?"""
    klein = _glatt(text).lower()
    vorhanden = koennen()

    # Nennt er ausdruecklich Hardware, reicht ein einzelnes Stichwort NICHT.
    # "Ein Geraet, das den WLAN-Rauschpegel misst" traf mit dem einen Wort
    # "Netzwerkauslastung" das Lagebild - das kennt Geraetenamen, aber keinen
    # Rauschpegel. Eine Messung an der Welt kann kein Programm ersetzen.
    # "Zugriff auf die Werte der Grafikkarte" nennt auch Hardware, deckt sich
    # aber mit ZWEI Kennwoertern der Selbstwahrnehmung und bleibt gestrichen.
    if not GERAET.search(klein):
        # Erst die Stichwoerter - sie treffen, wo der Wortvergleich versagt.
        for name, worte in STICHWORTE.items():
            if name not in vorhanden and name not in ("selbst messen",
                                                      "lagebild",
                                                      "gedaechtnis"):
                continue
            if sum(1 for w in worte if w in klein) >= 1:
                return name

    # Dann die Kennwoerter, als Wortteil gesucht statt als ganzes Wort.
    # Deutsch setzt zusammen: "Speicherplatz" enthaelt den "Platz", den
    # platzverlauf festhaelt, teilt mit ihm aber kein ganzes Wort - genau
    # daran ging der Wunsch nach einer Platzanzeige vorbei.
    beste = (0, None)
    for name, worte in _kennwoerter(vorhanden).items():
        treffer = sum(1 for w in worte if w in klein)
        if treffer > beste[0]:
            beste = (treffer, name)
    if beste[0] >= TREFFER_NOETIG:
        return beste[1]
    return None


ARTEN = ("RECHT", "GERAET", "GELD", "WISSEN")

# Ein Zweck, der mit "darf" anfaengt, ist selbst ein Recht - kein Koennen.
# "Den Dienst neu starten: Darf den Dienst, mit dem ich denke, neu starten"
# ist das genehmigte Recht aus RECHT-OLLAMA.md.
IST_RECHT = re.compile(r"\b(darf|duerfen|dürfen|erlaubt|genehmigt)",
                       re.IGNORECASE)


def darf_ich_schon(text):
    """Deckt ein GENEHMIGTES Recht diesen Wunsch schon ab?

    Getrennt von kann_ich_schon, weil dort das erste Stichwort gewinnt: Bei
    "den Ollama-Dienst neu starten duerfen" traf "ollama" die
    Selbstwahrnehmung, und das genehmigte Recht "Den Dienst neu starten" kam
    nie zum Vergleich. Wer nach einer Erlaubnis fragt, soll zuerst unter den
    Erlaubnissen nachsehen.
    """
    klein = _glatt(text).lower()
    vorhanden = koennen()
    kenn = _kennwoerter(vorhanden)
    beste = (0, None)
    for name, zweck in vorhanden.items():
        if not IST_RECHT.search(zweck):
            continue
        treffer = sum(1 for w in kenn.get(name, ()) if w in klein)
        if treffer > beste[0]:
            beste = (treffer, name)
    return beste[1] if beste[0] >= TREFFER_NOETIG else None


def zerlegen(text):
    """(Art aus seiner Ueberschrift oder None, Satz ohne Ueberschrift)."""
    satz = _glatt(text)
    m = UEBERSCHRIFT.match(satz)
    if not m:
        n = NUMERIERUNG.match(satz)
        rest = satz[n.end():].strip() if n else satz
        return None, rest if len(rest) >= 10 else satz
    art = m.group(1).upper().replace("GERÄT", "GERAET")
    rest = satz[m.end():].strip()
    # Nur eine Ueberschrift, kein ganzer Wunsch: dann war sie der Wunsch.
    if len(rest) < 10:
        return None, satz
    return art, rest


def ohne_ueberschrift(text):
    """Der Wunsch ohne sein eigenes Etikett - die Einordnung steht darunter."""
    return zerlegen(text)[1]


def einordnen(text):
    """Was fehlt wirklich? Gibt (Art, Begruendung) zurueck.

    Zwei Etiketten an einem Wunsch, und sie widersprachen sich: Ueberschrift
    GELD, Einordnung "Wissen"; Ueberschrift WISSEN, Einordnung "Recht".

    Die Ueberschrift entscheiden zu lassen, waere falsch gewesen - im Lauf um
    10:40 nannte er vier Programme "GERÄT", und jedes waere als fehlende
    Hardware bei Calvin gelandet. Die Regeln allein reichten auch nicht, sonst
    haette es die beiden Widersprueche nicht gegeben.

    Also muessen beide sich einig sein. Sind sie es nicht, gilt die Seite, die
    Calvin NICHT belaestigt: WISSEN, also ein Werkzeug, das er sich selbst
    bauen lassen kann. Von seinen sechs Antraegen waren drei zu klein und
    haben ihn nur Aufmerksamkeit gekostet - bei Zweifel ist Schweigen
    richtiger als ein Antrag.

    Genau eine Sache darf er nicht selbst beurteilen: ob er es schon kann. Das
    ist sein blinder Fleck, und nur dafuer gibt es zwei Listen zum Nachsehen.
    Dieser Befund schlaegt jede Ueberschrift.
    """
    gesagt, satz = zerlegen(text)
    if len(satz) < 10:
        return "UNKLAR", "zu kurz, um es einzuordnen"

    # Zuerst: Behauptet der Satz ueberhaupt einen Mangel? Sagt er, dass ihm
    # nichts fehlte, ist das die richtige Antwort und kein Wunsch.
    if VERNEINT.search(satz):
        return "KEIN_MANGEL", ("hier fehlt nichts - das ist eine Feststellung, "
                               "kein Wunsch")

    # Was die Regeln sagen. Recht zuerst - ein ausdrueckliches "duerfen" sagt,
    # dass er es koennte und nicht darf, und ist das staerkste Signal.
    if RECHT.search(satz):
        nach_regel = "RECHT"
    elif GELD.search(satz):
        nach_regel = "GELD"
    elif GERAET.search(satz):
        # Nennt er nur das Wort "Gerät" und will damit etwas anzeigen oder
        # melden, ist es ein Programm. Nennt er echte Hardware oder will er
        # etwas an der Welt messen, bleibt es ein Geraet.
        if (not HARDWARE.search(satz) and ANZEIGEN.search(satz)
                and not MESSEN.search(satz)):
            nach_regel = "WISSEN"
        else:
            nach_regel = "GERAET"
    else:
        nach_regel = "WISSEN"

    # Nun beide gegeneinander. Ohne Ueberschrift gilt die Regel; sind sie
    # sich einig, gilt sie auch. Widersprechen sie sich, gilt WISSEN - die
    # Seite ohne Antrag an Calvin.
    art = nach_regel if (gesagt is None or gesagt == nach_regel) else "WISSEN"

    # Ein Recht, das Calvin schon gegeben hat, ist kein Wunsch. "Ein Skript,
    # das Llama-Server ohne Elternprozess beendet" ist kein fehlendes Recht,
    # sondern eingreifen.py. Das wird VOR kann_ich_schon geprueft, weil dort
    # das erste Stichwort gewinnt und die Erlaubnis nie zum Vergleich kam.
    if art == "RECHT":
        darf = darf_ich_schon(satz)
        if darf:
            return "KANN_ICH_SCHON", (
                "das darf ich schon - %s ist genehmigt, kein Antrag nötig"
                % darf)
        return "RECHT", f"das dürfte ich nicht, darüber entscheidet {NAME}"

    # Und zuletzt sein blinder Fleck: Kann er es schon? "Zugriff auf die Werte
    # der Grafikkarte" nennt Hardware, meint aber eine Faehigkeit, die er hat.
    schon = kann_ich_schon(satz)
    if schon:
        return "KANN_ICH_SCHON", ("das deckt %s bereits ab - kein Wunsch, "
                                  "sondern ein Werkzeug, das ich habe" % schon)

    return art, {
        "GELD": f"das kostet etwas, darüber entscheidet {NAME}",
        "GERAET": f"dafür fehlt Hardware, darüber entscheidet {NAME}",
        "WISSEN": "ich weiß nur nicht wie - dafür kann ich mir ein "
                  "Werkzeug bauen lassen, das braucht keinen Antrag",
    }[art]


def braucht_antrag(art):
    return art in ("RECHT", "GERAET", "GELD")


def lesen(datei=LISTE):
    try:
        with open(datei, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def schreiben(liste, datei=LISTE):
    ziel = os.path.abspath(datei)
    if not ziel.startswith(os.path.abspath(WERKSTATT_ORDNER)):
        raise ValueError("Die Liste muss in der Werkstatt liegen.")
    tmp = datei + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=2)
    os.replace(tmp, datei)


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    print("Selbsttest wuensche")
    gesamt = 0
    fehler = 0

    def pruefe(bedingung, was):
        nonlocal gesamt, fehler
        gesamt += 1
        print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
        if not bedingung:
            fehler += 1

    # Genau der Fehler aus Stufe 4: er wuenscht sich, was er hat.
    art, grund = einordnen("Ich haette gern Zugriff auf die Werte der "
                           "Grafikkarte, um selbst zu messen")
    pruefe(art == "KANN_ICH_SCHON", "erkennt vorhandene Fähigkeit: %s"
           % grund[:70])
    pruefe(not braucht_antrag(art), "und stellt dafür KEINEN Antrag")

    # Bis zum 12.09. war das DER Fall fuer ein fehlendes Recht. Calvin hat es
    # inzwischen genehmigt, und damit ist es keiner mehr: Der Wunsch nach einer
    # Erlaubnis, die man hat, ist so falsch wie der nach einem Werkzeug, das
    # man hat. Deshalb steht hier jetzt ein Recht, das er wirklich nicht hat.
    art, grund = einordnen("Ich müsste den Router im Flur neu starten dürfen, "
                           "wenn das Heimnetz hängt")
    pruefe(art == "RECHT", "fehlendes Recht erkannt: %s" % grund[:60])
    pruefe(braucht_antrag(art), "und stellt dafür einen Antrag")

    art, grund = einordnen("Ich müsste den Ollama-Dienst neu starten dürfen, "
                           "wenn er abstürzt")
    pruefe(art == "KANN_ICH_SCHON",
           "genehmigtes Recht ist kein Wunsch: %s" % grund[:60])

    # Die vier Wuensche vom 12.09., 09:25 - jeder davon falsch, und jeder aus
    # einem anderen Grund. Sie stehen hier, damit keiner wiederkommt.
    art, grund = einordnen(
        "GERÄT: Es fehlt ein Gerät, das mir den freien Speicherplatz auf "
        "allen Laufwerken zeigt, damit ich meine Speicherverwaltung besser "
        "planen kann.")
    pruefe(art == "KANN_ICH_SCHON",
           "Platzanzeige: das ist platzverlauf (%s)" % grund[:44])

    art, grund = einordnen(
        "WISSEN: Ich weiß nicht, wie ich ein Skript schreiben kann, das die "
        "laufenden Llama‑Server‑Prozesse regelmäßig beendet, wenn "
        "sie ohne Elternprozess weiterlaufen.")
    pruefe(art == "KANN_ICH_SCHON",
           "Llama-Server mit Sonderstrich: das kann er schon")

    art, grund = einordnen(
        "GELD: Für einen möglichen neuen Speicherplatz-Tracker wäre ein "
        "kleiner, kostenpflichtiger Cloud‑Backup‑Dienst nötig.")
    pruefe(art == "GELD", "Überschrift GELD bleibt GELD, nicht Wissen")
    pruefe(braucht_antrag(art), f"und geht als Antrag an {NAME}")

    art, grund = einordnen(
        "WISSEN: Ich weiß nicht, wie ich den Antrag, den Ollama‑Dienst "
        "neu starten zu dürfen, automatisch überwachen und bei Bedarf neu "
        "auslösen kann.")
    pruefe(art == "KANN_ICH_SCHON",
           "Überschrift WISSEN, Einordnung Recht - beides falsch, er darf es")

    # Die fuenf Saetze vom 12.09., 10:30 - er bestreitet jeden Mangel, und der
    # Filter machte daraus vier Wuensche, einen davon als Antrag an Calvin.
    for verneint in (
            "Ich habe keine Anträge gestellt, weil ich keinen Bedarf hatte.",
            "Ich habe keine Geräte gekauft, weil ich keinen fehlenden "
            "Hardware-Baustein bemerkt habe.",
            "Ich habe keine Software installiert, weil mir keine Anforderung "
            "vorlag, die nicht bereits erfüllt war.",
            "Ich habe keine zusätzlichen Finanzmittel beantragt, weil mir "
            "keine Ausgabenüberschreitung aufgefallen ist.",
            "Ich habe keine zusätzlichen Genehmigungen erbeten, weil meine "
            "bestehenden Rechte alle mir benötigten Tätigkeiten abdeckten."):
        art, _ = einordnen(verneint)
        pruefe(art == "KEIN_MANGEL",
               "verneinter Mangel ist kein Wunsch: %s" % verneint[:44])
        pruefe(not braucht_antrag(art), f"und geht nicht an {NAME}")

    # "Gerät" sagt er auch zu Programmen. Aus dem Lauf 10:50.
    art, _ = einordnen("Ich wünsche mir ein Gerät, das mir beim Neustart des "
                       "Ollama-Dienstes automatisch eine Warnung anzeigt, "
                       "falls der Dienst nicht mehr reagiert.")
    pruefe(art == "WISSEN", "was nur anzeigt, ist ein Programm")
    pruefe(not braucht_antrag(art), f"und geht nicht als Hardware an {NAME}")

    # Ein Messgeraet fuer die Welt ist kein Programm. Aus dem Lauf 10:34: das
    # eine Wort "Netzwerkauslastung" strich einen echten Geraetewunsch.
    art, _ = einordnen(
        "GERÄT: Ein kleines Gerät, das den WLAN-Rauschpegel misst, damit ich "
        "bei plötzlich auftretender Netzwerkauslastung sofort Alarm bekomme.")
    pruefe(art == "GERAET",
           "ein Messgerät bleibt ein Gerät, trotz Netz-Stichwort")
    art, _ = einordnen("GERÄT: Ein Sensor, der die Temperatur der "
                       "Grafikkarte misst.")
    pruefe(art == "GERAET", "Temperaturfühler auch")

    # Und die Gegenprobe: eine Verneinung MITTEN im Wunsch bleibt ein Wunsch.
    for echt in ("Ich weiß nicht, wie ich Tabellen in PDFs auswerte",
                 "Ich kann Tabellen in Dokumenten nicht auswerten",
                 "Ich müsste den Router im Flur neu starten dürfen",
                 "Ein besseres Abo für die Sprachausgabe kostet Geld"):
        art, _ = einordnen(echt)
        pruefe(art != "KEIN_MANGEL",
               "bleibt ein Wunsch (%s): %s" % (art, echt[:40]))

    # Aus dem Lauf vom 12.09., 10:2x, mit dem neuen Filter: Er numeriert seine
    # Wuensche und nennt eine Genehmigung "Genehmigung", nicht "duerfen".
    art, _ = einordnen("1. Wunsch: Genehmigung, die Firewall zu deaktivieren.")
    pruefe(art == "RECHT", "Genehmigung ist ein Recht, kein Wissen")
    pruefe(ohne_ueberschrift("3. Wunsch: Eine Meldung bei neuen Prozessen.")
           == "Eine Meldung bei neuen Prozessen.",
           f"Numerierung gehört nicht in {NAMENS} Liste")

    # Die Ueberschrift ist ein Etikett, kein Wunsch. Sie darf nicht zweimal
    # dastehen, einmal von ihm und einmal vom Pruefer.
    pruefe(ohne_ueberschrift("- GELD: Ein Abo für die Stimme kostet etwas.")
           == "Ein Abo für die Stimme kostet etwas.",
           "Überschrift wird abgeschnitten, nicht doppelt gezeigt")
    pruefe(ohne_ueberschrift("Ein Abo für die Stimme kostet etwas.")
           == "Ein Abo für die Stimme kostet etwas.",
           "ohne Überschrift bleibt der Satz unberührt")

    # Beide Listen, nicht nur eine. Bei 10 Werkzeugen und 17 Faehigkeiten
    # duerfen es nicht 14 sein.
    pruefe(len(koennen()) >= 25,
           "prüft gegen BEIDE Listen: %d Einträge" % len(koennen()))
    pruefe("Den Dienst neu starten" in koennen(),
           "faehigkeiten.json ist dabei")
    pruefe("platzverlauf" in koennen(), "werkzeuge.json ist dabei")

    art, _ = einordnen("Ich bräuchte eine Kamera, um zu sehen, wer im Raum ist")
    pruefe(art == "GERAET", "fehlendes Gerät erkannt")

    art, _ = einordnen("Ein besseres Abo für die Sprachausgabe kostet Geld")
    pruefe(art == "GELD", "Kosten erkannt")

    art, grund = einordnen("Ich kann Tabellen in Dokumenten nicht auswerten")
    pruefe(art == "WISSEN", "fehlendes Wissen erkannt: %s" % grund[:60])
    pruefe(not braucht_antrag(art),
           "Wissen braucht keinen Antrag, sondern ein Werkzeug")

    art, _ = einordnen("hm")
    pruefe(art == "UNKLAR", "zu kurz bleibt unklar")

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


def main():
    p = argparse.ArgumentParser(description="Wünsche einordnen.")
    p.add_argument("--pruefen", help="Ist das ein Wunsch, und was fehlt?")
    p.add_argument("--liste", action="store_true")
    p.add_argument("--selbsttest", action="store_true")
    a = p.parse_args()

    if a.selbsttest:
        return selbsttest()
    if a.liste:
        for w in lesen():
            print("  [%s] %s" % (w.get("art", "?"), w.get("text", "")))
        return 0
    if a.pruefen:
        art, grund = einordnen(a.pruefen)
        print("%s - %s" % (art, grund))
        print(f"Antrag an {NAME}: %s" % ("ja" if braucht_antrag(art) else "nein"))
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
