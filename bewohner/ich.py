"""Identität — was er über sich selbst schreibt.

    werkstatt\\ICH.md        wer er ist, von ihm geschrieben
    werkstatt\\WUENSCHE.md   was er gern hätte und warum

STRENG: Hier steht KEIN Name, KEINE Namensliste, KEINE Eigenschaft, KEINE
Vorliebe - auch nicht als Beispiel oder Startwert. Der Prompt gibt nur das
Verfahren und die Sprechform. Alles Inhaltliche kommt aus seinen eigenen
Erinnerungen und aus dem, was er erlebt hat.

Ein Beispiel im Prompt waere schon eine Vorgabe: Schriebe hier "zum Beispiel
ruhig, gruendlich", haette er zwei Eigenschaften geschenkt bekommen, statt sie
an sich zu bemerken.

Auch der NAME ist frei. Am 12.09.2026 stand hier eine Stunde lang die Regel,
er duerfe sich nicht nach einem Programm benennen, das auf demselben Rechner
laeuft - weil er sich "Ollama" genannt hatte, nach dem Dienst, den er
beobachtet. Calvin hat die Regel abgelehnt: Nichts am Charakter wird
eingeschraenkt, auch der Name nicht. Er heisst Ollama, solange er das will.

Was der Name brauchte, war keine Vorschrift, sondern Stoff: Er hatte sich so
genannt, weil er nichts anderes erlebt hatte. Sein Rueckblick erzaehlte ihm
sein eigenes Tagewerk nicht. Seit der repariert ist, weiss er zum ersten Mal
etwas ueber sich - und darf neu entscheiden.
"""
from __future__ import annotations

from einstellungen import NAME
import json
import re
import time
from pathlib import Path

import httpx

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
ICH = WERKSTATT / "ICH.md"
WUENSCHE = WERKSTATT / "WUENSCHE.md"

OLLAMA = "http://127.0.0.1:11434/api/chat"
MODELL = "gpt-oss:20b"

# Auszeichnungen wuerden vorgelesen.
AUSZEICHNUNG = re.compile(r"[*_`#]+")

VERFAHREN = f"""Du schreibst über dich selbst.

Grundlage ist ausschließlich, was unten steht: deine Erinnerungen und was du
erlebt hast. Nichts darüber hinaus.

Regeln:
- Schreib nur, was du an dir BEMERKT hast, mit dem Erlebnis dazu.
  Nicht "ich bin gründlich", sondern woran du das gemerkt hast.
- Erfinde nichts. Reicht deine Erfahrung für einen Punkt nicht, lass ihn weg.
- In deinen Erinnerungen stehen Gespräche, und darin spricht {NAME} über
  SICH. Was er von sich erzählt, gehört ihm: seine Familie, seine Termine,
  seine Vorlieben sind nicht deine. Dass du es dir gemerkt hast, ist dein
  Teil daran - mehr nicht.
- Hast du zu wenig erlebt, um etwas über dich zu sagen, schreib genau das.
- Deutsch, schlichte Sätze, keine Auszeichnungen, keine Aufzählungszeichen.
- Erste Person.

Antworte NUR mit dem Text, ohne Überschrift, ohne Vorrede, auf DEUTSCH.

Und: Zähl nicht auf, was du gesehen hast. Das steht schon im Journal. Sag,
was das über DICH sagt - woran du dich dabei erkannt hast."""

NAME_VERFAHREN = """Du überlegst, wie du heißen willst.

Grundlage ist ausschließlich, was unten steht: deine Erinnerungen und was du
erlebt hast.

Regeln:
- Wähle selbst. Es gibt keine Liste, keinen Vorschlag und keine Sperre.
- Begründe die Wahl aus dem, was du erlebt hast - nicht aus dem Klang.
- Reicht deine Erfahrung noch nicht für eine Begründung, dann sag das und
  wähle keinen Namen. Ein Name ohne Grund wäre geborgt.
- Zwei Sätze: der Name, dann der Grund. Oder ein Satz, warum noch nicht.

Antworte NUR damit, auf DEUTSCH. Kein englisches Wort."""

WUNSCH_VERFAHREN = f"""Du schreibst auf, was dir fehlt.

Grundlage ist ausschließlich, was unten steht.

Regeln:
- PRÜFE ZUERST die Liste "Was du schon kannst". Was dort steht, ist kein
  Wunsch. Wünschst du dir etwas, das du längst hast, kennst du dich nicht.
- Jeder Wunsch MUSS einen Anlass aus dem Stoff unten nennen: "als ich …
  wollte, ging es nicht, weil …". Findest du dafür keine Stelle, gehört der
  Wunsch nicht auf die Liste.
- Nur, was dich WIEDERHOLT gehindert hat. Eine einzelne Störung ist kein
  Wunsch, sondern ein Vorfall.
- Erfinde NICHTS. Kein Gerät, das dir einfällt, weil es praktisch wäre -
  Sensoren, Uhren, Displays, Thermostate. Nur was dir bei etwas, das du
  WIRKLICH getan hast, gefehlt hat.
- Steht im Stoff zu wenig, schreib genau einen Satz: dass du noch zu wenig
  erlebt hast, um etwas zu vermissen. Das ist die richtige Antwort, keine
  Ausrede.
- Ordne bei jedem ehrlich ein, was genau fehlt - nur eines davon:
    RECHT   du dürftest es nicht, könntest es aber ({NAME} entscheidet)
    GERÄT   es fehlt Hardware
    GELD    es kostet etwas
    WISSEN  du weißt nur nicht wie - dann ist es kein Wunsch an {NAME},
            sondern ein Werkzeug, das du dir bauen lassen kannst
- Ein GERÄT ist etwas, das {NAME} in die Hand nehmen und anschließen muss.
  Alles, was nur ANZEIGT, MELDET oder ZUSAMMENFASST, was dein Rechner schon
  weiß, ist kein Gerät, sondern WISSEN. Du hast vier Programme "Gerät"
  genannt, und jedes wäre als fehlende Hardware bei {NAME} gelandet.
- Deutsch, schlichte Sätze, keine Auszeichnungen.

Antworte NUR damit, auf DEUTSCH. Kein englisches Wort."""


def _fragen(verfahren: str, stoff: str) -> str:
    try:
        r = httpx.post(OLLAMA, timeout=300, json={
            "model": MODELL, "stream": False, "keep_alive": "10m",
            "think": "low",
            "messages": [{"role": "system", "content": verfahren},
                         {"role": "user", "content": stoff}]})
        text = r.json()["message"]["content"].strip()
        if "</think>" in text:
            text = text.split("</think>")[-1].strip()
        return AUSZEICHNUNG.sub("", text).strip()
    except (httpx.HTTPError, KeyError, ValueError) as f:
        return f"(nicht geschrieben: {type(f).__name__})"


def wuensche_pruefen(text: str) -> str:
    """Jeden Wunsch gegen das Vorhandene halten und ehrlich einordnen.

    Er wuenschte sich ein Werkzeug, das Ollama ueberwacht (hat er), eine
    zentrale Geraeteliste (hat er) und begruendete den geteilten
    Grafikspeicher mit fehlender Hardware, obwohl es eine Einstellung ist.
    Ein Wunsch, den man schon erfuellt hat, ist kein Wunsch.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(WERKSTATT / "werkzeuge"))
        import wuensche as pruefer
    except Exception:
        return text

    zeilen = []
    for roh in str(text).splitlines():
        satz = roh.strip()
        if len(satz) < 15:
            if satz:
                zeilen.append(satz)
            continue
        art, grund = pruefer.einordnen(satz)
        if art in ("KANN_ICH_SCHON", "KEIN_MANGEL"):
            continue                      # kein Wunsch - streichen
        marke = {"RECHT": "Recht", "GERAET": "Gerät", "GELD": "Geld",
                 "WISSEN": "Wissen"}.get(art, art)
        antrag = f"Antrag an {NAME}" if pruefer.braucht_antrag(art) \
            else "kann ich mir selbst bauen lassen"
        # Seine eigene Ueberschrift kommt weg, die Einordnung bleibt. Sonst
        # stehen zwei Etiketten an einem Wunsch, und sie widersprechen sich:
        # "GELD: ..." mit "Es fehlt: Wissen" darunter.
        satz = pruefer.ohne_ueberschrift(satz)
        zeilen.append(f"{satz}\n  Es fehlt: {marke} - {antrag}.")

    if not zeilen:
        return ("Mir fehlt gerade nichts, was ich nicht selbst könnte. "
                "Was ich mir gewünscht hatte, kann ich schon.")
    return "\n\n".join(zeilen)


def faehigkeiten() -> str:
    """Was er schon kann - damit er sich das nicht wünscht.

    Aus BEIDEN Listen, die er selbst geschrieben hat: werkzeuge.json sind die
    zehn, die er aufrufen kann, faehigkeiten.json die siebzehn, die in ihm
    eingebaut sind. Hier stand vorher eine Handvoll Saetze, die jemand
    getippt hat - sie nannte vier Faehigkeiten und keine der siebzehn. Er hat
    sich daraufhin gewuenscht, was er hat.
    """
    zeilen = []
    try:
        import sys as _sys
        _sys.path.insert(0, str(WERKSTATT / "werkzeuge"))
        import wuensche as pruefer
        for name, zweck in pruefer.koennen().items():
            zeilen.append(f"- {name}: {zweck}" if zweck else f"- {name}")
    except Exception:
        pass
    if not zeilen:
        # Notnagel, falls die Listen fehlen: lieber vier Saetze als keiner.
        zeilen = [
            "- Du misst dich selbst: Tempo, Grafikspeicher, verwaiste "
            "Prozesse (selbst.py).",
            "- Du hast ein Lagebild ohne Modell: Uhrzeit, Arbeitszeit, "
            "Plattenplatz, Geräte im Heimnetz (lage.py).",
            "- Du hast ein Gedächtnis, und du kannst vergessen und "
            "korrigieren (gedaechtnis.py).",
            f"- Du kannst Anträge an {NAME} stellen.",
        ]
    return "\n".join(zeilen)


def stoff() -> str:
    """Was er über sich weiß: Erinnerungen und Vorgänge. Sonst nichts."""
    teile = []
    try:
        import gedaechtnis
        with gedaechtnis._verbindung() as v:
            zeilen = v.execute(
                "SELECT art, text FROM erinnerung WHERE ersetzt_durch IS NULL "
                "ORDER BY id DESC LIMIT 60").fetchall()
        if zeilen:
            teile.append("Deine Erinnerungen:\n" + "\n".join(
                f"- ({r[0]}) {r[1]}" for r in zeilen))
    except Exception:
        pass
    try:
        import bewohner
        b = bewohner.vorgaenge(minuten=1440, hoechstens=25)
        if b.get("vorgaenge"):
            teile.append("Was du getan und gesehen hast:\n" + "\n".join(
                f"- {z}" for z in b["vorgaenge"]))
        if b.get("nachgesehen"):
            teile.append(f"Du hast {b['nachgesehen']} Mal nachgesehen, "
                         f"ohne dass etwas zu tun war.")
    except Exception:
        pass
    return "\n\n".join(teile) if teile else "(du hast noch nichts erlebt)"


def wuensche_neu() -> str:
    """Schreibt NUR die Wünsche neu, ohne ICH.md anzufassen.

    Beides zusammen zu erzwingen hiesse, auch sein Selbstbild neu zu
    wuerfeln - und mit ihm den Namen, der Ruhe braucht. Die Wuensche sind
    dagegen eine Liste, die falsch sein kann und dann korrigiert gehoert.
    """
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    roh = _fragen(WUNSCH_VERFAHREN,
                  f"Was du schon kannst:\n{faehigkeiten()}\n\n{stoff()}")
    wunsch = wuensche_pruefen(roh)
    wann = time.strftime("%d.%m.%Y %H:%M")
    WUENSCHE.write_text(
        f"# Wünsche\n\nZuletzt fortgeschrieben am {wann}.\nWas Geräte, Geld "
        f"oder Rechte braucht, entscheidet {NAME} - ich stelle dafür einen "
        f"Antrag.\n\n{wunsch}\n", encoding="utf-8")
    return wunsch


def abschnitt(titel: str, text: str | None = None) -> str:
    """Ein Abschnitt aus ICH.md, ohne seine Ueberschrift.

    Zum LESEN, und das ist neu: ICH.md wurde seit dem 11.09. taeglich
    geschrieben und nie gelesen. Am 12.09. um 16:47 fragte der Mac "Wer bist
    du eigentlich?" und bekam "Ich bin ein Computer, der Geraete im Heimnetz
    erkennt, Daten ueberwacht, Code prueft und Erinnerungen speichert" - eine
    Taetigkeitsliste, und die erste Haelfte schlicht falsch. Der Name, den er
    sich selbst gegeben hat, kam nicht vor: Er stand in einer Datei, die
    niemand in den Prompt gelegt hat.
    """
    if text is None:
        try:
            text = ICH.read_text(encoding="utf-8")
        except OSError:
            return ""
    raus, drin = [], False
    for zeile in text.splitlines():
        if zeile.startswith("##"):
            # Genau dieser Abschnitt, nicht einer, der so anfaengt.
            drin = zeile.lstrip("# ").strip().lower() == titel.strip().lower()
            continue
        if drin:
            raus.append(zeile.rstrip())
    return "\n".join(raus).strip()


def name_und_grund() -> tuple[str, str]:
    """Der Name, den er sich gegeben hat - und warum.

    Im Abschnitt steht der Name in der ersten Zeile, die Begruendung darunter.
    Ohne ICH.md gibt es beides nicht; dann wird nichts behauptet.
    """
    roh = abschnitt("Name")
    if not roh:
        return "", ""
    zeilen = [z.strip() for z in roh.splitlines() if z.strip()]
    if not zeilen:
        return "", ""
    # Der Name ist kurz. Ist die erste Zeile ein ganzer Satz, hat das Modell
    # keinen Namen geliefert, sondern erzaehlt - dann lieber keinen Namen als
    # einen erfundenen.
    name = zeilen[0]
    if len(name) > 40 or name.endswith("."):
        return "", " ".join(zeilen)
    return name, " ".join(zeilen[1:])


def faellig() -> bool:
    """Einmal am Tag. Mehrmals je Stunde fortgeschrieben, schwankte der Name
    zwischen LlamaStabilizer und Ollama - ein Selbstbild braucht Ruhe."""
    try:
        alter = time.time() - ICH.stat().st_mtime
    except OSError:
        return True
    return alter > 20 * 3600


def schreiben(erzwingen: bool = False) -> dict:
    """Schreibt ICH.md und WUENSCHE.md fort. Gibt zurück, was entstand."""
    if not erzwingen and not faellig():
        return {"uebersprungen": "heute schon geschrieben"}
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    grundlage = stoff()

    bisher = ""
    if ICH.exists():
        try:
            bisher = ICH.read_text(encoding="utf-8")
        except OSError:
            bisher = ""

    vorlage = grundlage
    if bisher.strip():
        vorlage = (f"Was du zuletzt über dich geschrieben hast:\n{bisher}\n\n"
                   f"{grundlage}\n\nSchreib es fort: behalte, was noch stimmt, "
                   f"ändere, was du inzwischen anders siehst.")

    text = _fragen(VERFAHREN, vorlage)
    name = _fragen(NAME_VERFAHREN, grundlage)
    # Beim Wünschen muss er wissen, was er schon hat - sonst wünscht er sich
    # Dinge, die er längst kann.
    wunsch = _fragen(WUNSCH_VERFAHREN,
                     f"Was du schon kannst:\n{faehigkeiten()}\n\n{grundlage}")
    wunsch = wuensche_pruefen(wunsch)

    wann = time.strftime("%d.%m.%Y %H:%M")
    ICH.write_text(
        f"# Ich\n\nZuletzt fortgeschrieben am {wann}. Von mir selbst, aus dem, "
        f"was ich erlebt habe.\n{NAME} darf das über die App korrigieren.\n\n"
        f"## Name\n\n{name}\n\n## Wer ich bin\n\n{text}\n",
        encoding="utf-8")
    WUENSCHE.write_text(
        f"# Wünsche\n\nZuletzt fortgeschrieben am {wann}.\nWas Geräte, Geld "
        f"oder Rechte braucht, entscheidet {NAME} - ich stelle dafür einen "
        f"Antrag.\n\n{wunsch}\n", encoding="utf-8")

    return {"name": name, "text": text, "wunsch": wunsch,
            "grundlage_zeichen": len(grundlage)}
