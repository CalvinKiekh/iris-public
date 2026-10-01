"""C.2 - wie "morgen" zu einem Datum wird. Reine Rechnung, kein Modell.

DAS RISKANTESTE STUECK DES PLANS, und zwar aus einem Grund: Ein falsches Datum
weckt Calvin nachts. Ein vergessener Termin ist aergerlich, ein erfundener ist
schlimmer. Darum rechnet hier alles, nichts wird geraten, und jede Regel, die
eine Falle ist, steht ausdruecklich da.

DER BEZUGSPUNKT IST DIE AEUSSERUNG, nicht die Auswertung. Sagt Calvin um 23:50
"morgen" und der Auszug laeuft um 00:05, ist "morgen" NICHT der Tag nach der
Auswertung. Die Sitzung liefert den Zeitpunkt (`letzte_frage` des Paares, in
dem es stand) - ohne sie waere dieser Fehler unvermeidbar. `bezug` ist darum
ein Pflichtparameter und hat keine Voreinstellung.

VIER RUECKGABEN, nicht zwei (B10 des Mac). `datetime | None` genuegt nicht,
weil "unklar" und "kein Termin" verschieden behandelt werden muessen:

    (datetime, "")          ein Datum
    (None, "unklar")        Terminabsicht, Monat oder Jahr offen -> RUECKFRAGE
    (None, "kein_termin")   "gestern" - keine Terminabsicht, stillschweigend
    (None, "nichts")        gar kein Zeitwort drin

Der Unterschied zwischen den beiden Nones ist der ganze Punkt. "am 3." am 20.
ist eine Terminabsicht mit offenem Monat: Umgangssprachlich ist meist der
naechste Dritte gemeint - aber "meist" ist kein Grund, einen Termin zu
erfinden, also Rueckfrage. "gestern" dagegen will nichts vormerken, und eine
Rueckfrage waere albern.

UND DER UNTERSCHIED ZWISCHEN ZEITPUNKT UND DAUER. "in drei Tagen" ist ein
Zeitpunkt, "drei Stunden" ist eine Dauer. Wer das verwechselt, legt Termine
fuer Dinge an, die keine sind:

    "Er hat 14 Tage Urlaub"   findet() == False
    "Das dauert 3 Stunden"    findet() == False

Deshalb gibt es `findet()` ueberhaupt: D.2 braucht es, um vergessene Termine
zu vermuten, und eine Vermutung, die auf jeder Dauerangabe anschlaegt, ist
wertlos. Aus demselben Grund ist "Guten Morgen" kein Zeitwort - sonst
vermutete D.2 in jedem Gruss einen Termin.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

# Ohne Uhrzeit ist ein Termin ein Tagestermin. Neun Uhr ist die Erinnerung
# dazu, nicht die Behauptung, dass es um neun stattfindet.
STANDARDSTUNDE = 9

# Tageszeitwoerter. B10 des Mac: Anhang 2 prueft sie, die Liste in C.2 kannte
# sie nicht - wer nach der Liste baut, faellt ueber den Anhang.
TAGESZEIT = {
    "früh": 8, "frueh": 8, "morgens": 8, "vormittags": 10,
    "mittags": 12, "nachmittags": 15,
    "abends": 19, "abend": 19, "nachts": 22,
}

# Zahlwoerter. Sie stehen HIER und nicht in bestand.py, obwohl bestand sie
# zuerst gebraucht hat: Zwei Listen, die gleich zu halten sind, laufen
# auseinander, und die eine verfaellt, sobald jemand die andere erweitert.
ZAHLWORT = {
    "null": 0, "ein": 1, "eine": 1, "einer": 1, "eins": 1, "zwei": 2,
    "drei": 3, "vier": 4, "fuenf": 5, "fünf": 5, "sechs": 6, "sieben": 7,
    "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwoelf": 12, "zwölf": 12,
    "dreizehn": 13, "vierzehn": 14, "fuenfzehn": 15, "fünfzehn": 15,
    "sechzehn": 16, "siebzehn": 17, "achtzehn": 18, "neunzehn": 19,
    "zwanzig": 20, "dreissig": 30, "dreißig": 30, "vierzig": 40,
    "fuenfzig": 50, "fünfzig": 50, "sechzig": 60, "siebzig": 70,
    "achtzig": 80, "neunzig": 90, "hundert": 100,
    # "ein Dutzend" ist eine Zahl, auch wenn sie wie ein Wort aussieht.
    "dutzend": 12,
}
_EINER = [(w, z) for w, z in ZAHLWORT.items() if 1 <= z <= 9]
_ZEHNER = [(w, z) for w, z in ZAHLWORT.items()
           if z in (20, 30, 40, 50, 60, 70, 80, 90)]

WOCHENTAGE = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonnabend": 5, "sonntag": 6,
    # Die Spracherkennung kuerzt.
    "mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6,
}

MONATE = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

# Tageswoerter und ihr Abstand zu heute.
TAGESWORT = {"heute": 0, "morgen": 1, "übermorgen": 2, "uebermorgen": 2,
             "gestern": -1, "vorgestern": -2}

# Eine Zeitabsicht ohne Datum. Eine Rueckfrage lohnt hier - er WILL etwas
# vormerken, er hat nur nicht gesagt wann.
VAGE = ("bald", "demnächst", "demnaechst", "irgendwann", "später", "spaeter",
        "die tage", "in naher zukunft")

# "Guten Morgen" ist ein Gruss, kein Zeitwort. Ohne diese Zeile vermutete D.2
# in jedem Gruss einen vergessenen Termin.
GRUSS = re.compile(r"\bguten\s+(morgen|abend|tag)\b|\bmorgen\s*[!,]\s*$",
                   re.IGNORECASE)


def zahl_aus(wort: str) -> int | None:
    """Eine Zahl aus Ziffern ODER einem Zahlwort."""
    w = str(wort or "").strip().lower().rstrip(".")
    if w.isdigit():
        return int(w)
    for e_wort, e_zahl in _EINER:
        for z_wort, z_zahl in _ZEHNER:
            if w == f"{e_wort}und{z_wort}":
                return z_zahl + e_zahl
    return ZAHLWORT.get(w)


def zahlen_ausgeschrieben(satz: str) -> set[int]:
    """Welche Zahlen stehen als WORT in diesem Satz?

    bestand.py prueft damit, ob das Modell eine Anzahl erfunden hat - als
    Ziffer faellt "23" auf, als "dreiundzwanzig" nicht.
    """
    unten = " ".join(str(satz or "").split()).lower()
    gefunden = set()
    for e_wort, e_zahl in _EINER:
        for z_wort, z_zahl in _ZEHNER:
            if f"{e_wort}und{z_wort}" in unten:
                gefunden.add(z_zahl + e_zahl)
    for wort, zahl in ZAHLWORT.items():
        if re.search(rf"\b{wort}\b", unten):
            gefunden.add(zahl)
    return gefunden


# ----------------------------------------------------------------- Uhrzeit

_ZAHLWORT_ODER_ZIFFER = (r"\d{1,2}|"
                         + "|".join(sorted((re.escape(w) for w in ZAHLWORT),
                                           key=len, reverse=True)))

# "um 9", "um 9 Uhr", "9:30", "um halb zehn" faellt bewusst heraus - halb,
# viertel und dreiviertel sind mehrdeutig genug, um eine Rueckfrage zu
# verdienen, und sie stehen in keinem Pruefstein.
UHRZEIT = re.compile(
    rf"\b(?:um\s+)?({_ZAHLWORT_ODER_ZIFFER})\s*(?::|\.)\s*(\d{{2}})\s*"
    rf"(?:uhr)?\b"
    rf"|\bum\s+({_ZAHLWORT_ODER_ZIFFER})\s*(?:uhr)?\b"
    rf"|\b({_ZAHLWORT_ODER_ZIFFER})\s*uhr\b", re.IGNORECASE)


def uhrzeit_aus(text: str) -> tuple[int, int] | None:
    """(Stunde, Minute) - oder None, wenn keine Uhrzeit darin steht."""
    for treffer in UHRZEIT.finditer(str(text or "")):
        stunde_roh = treffer.group(1) or treffer.group(3) or treffer.group(4)
        minute_roh = treffer.group(2)
        stunde = zahl_aus(stunde_roh)
        if stunde is None:
            continue
        minute = int(minute_roh) if minute_roh else 0
        if not (0 <= stunde <= 23 and 0 <= minute <= 59):
            continue
        return stunde, minute
    return None


# ---------------------------------------------------------------- Erkennen

# "in N Tagen/Wochen/Stunden/Minuten" - MIT "in", denn das macht den
# Unterschied zwischen Zeitpunkt und Dauer. "drei Stunden" ist eine Dauer,
# "in drei Stunden" ein Zeitpunkt.
RELATIV = re.compile(
    rf"\bin\s+({_ZAHLWORT_ODER_ZIFFER})\s+"
    rf"(minuten?|stunden?|tagen?|tage|wochen?|monaten?)\b", re.IGNORECASE)

# "am 14.", "am 14.9.", "am 14. September", "am 14.09.2026"
DATUM_PUNKT = re.compile(
    r"\b(?:am\s+)?(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})?", re.IGNORECASE)
DATUM_MONATSNAME = re.compile(
    r"\b(?:am\s+)?(\d{1,2})\.?\s+(" + "|".join(MONATE) + r")\b",
    re.IGNORECASE)
DATUM_NUR_TAG = re.compile(r"\bam\s+(\d{1,2})\.(?!\s*\d)", re.IGNORECASE)

NAECHSTE_WOCHE = re.compile(r"\b(nächste|naechste|kommende)n?\s+woche\b",
                            re.IGNORECASE)
WOCHENTAG = re.compile(
    r"\b(?:(?:am|nächsten|naechsten|kommenden|nächste|naechste)\s+)?("
    + "|".join(sorted(WOCHENTAGE, key=len, reverse=True)) + r")\b",
    re.IGNORECASE)


def findet(text: str) -> bool:
    """Steckt ein Zeitwort MIT TERMINABSICHT darin?

    Nicht jede Zeitangabe ist eine: "Das dauert 3 Stunden" nennt eine Dauer,
    "Guten Morgen" einen Gruss. D.2 vermutet anhand dieser Funktion vergessene
    Termine - schlaegt sie auf jeder Dauer an, ist die Vermutung wertlos.
    """
    _, grund = _zerlegen(str(text or ""))
    return grund != "nichts"


def _zerlegen(text: str) -> tuple[dict, str]:
    """Was an Zeitangaben darin steckt, und ob es ueberhaupt welche sind."""
    roh = " ".join(str(text or "").split())
    unten = roh.lower()

    # Der Gruss zuerst: "Guten Morgen" darf "morgen" nicht treffen.
    ohne_gruss = GRUSS.sub(" ", unten)

    teile: dict = {}
    if any(w in ohne_gruss for w in VAGE):
        teile["vage"] = True

    for wort, abstand in TAGESWORT.items():
        if re.search(rf"\b{wort}\b", ohne_gruss):
            teile["tageswort"] = (wort, abstand)
            break

    for wort, stunde in TAGESZEIT.items():
        if re.search(rf"\b{wort}\b", ohne_gruss):
            teile["tageszeit"] = stunde
            break

    treffer = RELATIV.search(ohne_gruss)
    if treffer:
        menge = zahl_aus(treffer.group(1))
        if menge is not None:
            teile["relativ"] = (menge, treffer.group(2).lower())

    if NAECHSTE_WOCHE.search(ohne_gruss):
        teile["naechste_woche"] = True
    else:
        treffer = WOCHENTAG.search(ohne_gruss)
        if treffer:
            teile["wochentag"] = WOCHENTAGE[treffer.group(1).lower()]

    treffer = DATUM_MONATSNAME.search(ohne_gruss)
    if treffer:
        teile["datum"] = (int(treffer.group(1)),
                          MONATE[treffer.group(2).lower()], None)
    else:
        treffer = DATUM_PUNKT.search(ohne_gruss)
        if treffer:
            jahr = int(treffer.group(3)) if treffer.group(3) else None
            teile["datum"] = (int(treffer.group(1)), int(treffer.group(2)),
                              jahr)
        else:
            treffer = DATUM_NUR_TAG.search(ohne_gruss)
            if treffer:
                teile["nur_tag"] = int(treffer.group(1))

    uhr = uhrzeit_aus(ohne_gruss)
    if uhr:
        teile["uhrzeit"] = uhr

    # Eine Uhrzeit ALLEIN ist ein Zeitwort ("um 18 Uhr"), eine Dauer nicht.
    if not teile:
        return {}, "nichts"
    # Nur eine Tageszeit ohne Tag ("abends") ist eine Absicht ohne Datum.
    return teile, ""


# ---------------------------------------------------------------- Aufloesen


def aufloesen(text: str, bezug: datetime) -> tuple[datetime | None, str]:
    """Aus einem Zeitwort ein Datum - bezogen auf den Zeitpunkt der Aeusserung.

    `bezug` ist Pflicht und hat bewusst keine Voreinstellung: Ein
    `datetime.now()` als Standard waere genau der Fehler, den C.2 ausschliesst.
    Die Zeitzone kommt von `lage.ortszeit()`, nie von `datetime.now()` - sonst
    stehen im Journal zwei Uhrzeiten.
    """
    teile, grund = _zerlegen(text)
    if grund == "nichts":
        return None, "nichts"

    uhr = teile.get("uhrzeit")

    # 1. Ein Tageswort in der Vergangenheit ist keine Terminabsicht.
    if "tageswort" in teile:
        wort, abstand = teile["tageswort"]
        if abstand < 0:
            return None, "kein_termin"

    # 2. Ein ausgeschriebenes Datum.
    if "datum" in teile:
        tag, monat, jahr = teile["datum"]
        wann = _bauen(bezug, jahr or bezug.year, monat, tag, uhr, teile)
        if wann is None:
            return None, "unklar"
        if jahr is None and wann < bezug:
            # Ohne Jahresangabe und in der Vergangenheit: naechstes Jahr waere
            # geraten. Rueckfrage.
            spaeter = _bauen(bezug, bezug.year + 1, monat, tag, uhr, teile)
            return (spaeter, "") if spaeter else (None, "unklar")
        return wann, ""

    # 3. "am 14." - Monat ergaenzt, solange es nach vorn zeigt.
    if "nur_tag" in teile:
        tag = teile["nur_tag"]
        wann = _bauen(bezug, bezug.year, bezug.month, tag, uhr, teile)
        if wann is None:
            return None, "unklar"
        if wann < bezug:
            # "am 3." am 12. - Terminabsicht, Monat offen. NICHT raten.
            return None, "unklar"
        return wann, ""

    # 4. "in N Tagen" - relative Angaben behalten die Uhrzeit des Bezugs.
    if "relativ" in teile:
        menge, einheit = teile["relativ"]
        wann = _verschieben(bezug, menge, einheit)
        if wann is None:
            return None, "unklar"
        if uhr:
            wann = wann.replace(hour=uhr[0], minute=uhr[1], second=0,
                                microsecond=0)
        elif "tageszeit" in teile:
            wann = wann.replace(hour=teile["tageszeit"], minute=0, second=0,
                                microsecond=0)
        return wann, ""

    # 5. "nächste Woche" ist ihr Anfang, also der Montag darauf.
    if "naechste_woche" in teile:
        tage = 7 - bezug.weekday()
        wann = (bezug + timedelta(days=tage))
        return _stunde_setzen(wann, uhr, teile), ""

    # 6. Ein Wochentag - immer der NAECHSTE, ab morgen gerechnet.
    if "wochentag" in teile:
        ziel = teile["wochentag"]
        tage = (ziel - bezug.weekday()) % 7
        if tage == 0:
            # "Dienstag" an einem Dienstag heisst naechster Dienstag. Wer
            # heute meint, sagt "heute".
            tage = 7
        wann = bezug + timedelta(days=tage)
        return _stunde_setzen(wann, uhr, teile), ""

    # 7. heute / morgen / übermorgen
    if "tageswort" in teile:
        _, abstand = teile["tageswort"]
        wann = bezug + timedelta(days=abstand)
        return _stunde_setzen(wann, uhr, teile), ""

    # 8. Nur eine Uhrzeit: heute, wenn sie noch kommt, sonst morgen.
    if uhr:
        wann = bezug.replace(hour=uhr[0], minute=uhr[1], second=0,
                             microsecond=0)
        if wann < bezug:
            wann += timedelta(days=1)
        return wann, ""

    # 9. Nur eine Tageszeit ("abends"): heute, wenn sie noch kommt.
    if "tageszeit" in teile:
        wann = bezug.replace(hour=teile["tageszeit"], minute=0, second=0,
                             microsecond=0)
        if wann < bezug:
            wann += timedelta(days=1)
        return wann, ""

    # 10. "bald", "irgendwann" - Absicht ohne Datum.
    if teile.get("vage"):
        return None, "unklar"

    return None, "nichts"


def _stunde_setzen(wann: datetime, uhr, teile: dict) -> datetime:
    """Die Uhrzeit schlaegt das Tageszeitwort, das schlaegt die Standardstunde.

    "morgen frueh um zehn" ist zehn Uhr, nicht acht.
    """
    if uhr:
        return wann.replace(hour=uhr[0], minute=uhr[1], second=0,
                            microsecond=0)
    if "tageszeit" in teile:
        return wann.replace(hour=teile["tageszeit"], minute=0, second=0,
                            microsecond=0)
    return wann.replace(hour=STANDARDSTUNDE, minute=0, second=0,
                        microsecond=0)


def _bauen(bezug: datetime, jahr: int, monat: int, tag: int, uhr,
           teile: dict) -> datetime | None:
    try:
        wann = bezug.replace(year=jahr, month=monat, day=tag)
    except ValueError:
        # Den 31. Februar gibt es nicht - das ist nicht "unklar", das ist
        # falsch gehoert. Rueckfrage.
        return None
    return _stunde_setzen(wann, uhr, teile)


def _verschieben(bezug: datetime, menge: int, einheit: str) -> datetime | None:
    if einheit.startswith("minut"):
        return bezug + timedelta(minutes=menge)
    if einheit.startswith("stund"):
        return bezug + timedelta(hours=menge)
    if einheit.startswith("tag"):
        return bezug + timedelta(days=menge)
    if einheit.startswith("woch"):
        return bezug + timedelta(weeks=menge)
    if einheit.startswith("monat"):
        # Monate sind ungleich lang. Dreissig Tage sind eine Annahme, und eine
        # Annahme ueber einen Termin ist genau das, was hier nicht passieren
        # soll.
        return None
    return None


def jetzt() -> datetime:
    """Die Ortszeit - dieselbe Quelle wie Antrag und Lagebild.

    Nie `datetime.now()`: Im Journal stuenden sonst zwei Uhrzeiten, und bei
    der Zeitumstellung waeren Termine eine Stunde falsch.
    """
    try:
        import lage
        return lage.ortszeit()
    except Exception:
        return datetime.now()
