"""Gespraeche als zeitgebundene Sitzungen - Schritt A aus PLAN-SITZUNGEN.md.

    python sitzung.py            zeigt die letzten Sitzungen
    python sitzung_test.py       die Probe

Reine Messung. Hier wird mit Zeitstempeln gerechnet und sonst nichts: kein
Modell, keine Leitung, nur Standardbibliothek. Das Zusammenfassen (B), das
Ableiten (C) und die naechtliche Gegenpruefung (D) bauen darauf auf und
gehoeren nicht hierher - wer sie hier einbaut, macht aus der Zuordnung einer
Frage einen Modellaufruf, und Calvin wartet dann darauf.

WARUM AUF DER PLATTE und nicht im Arbeitsspeicher: `Gespraech.verlauf` ist
nach jedem Neustart leer, und an einem Vormittag mit fuenf Neustarts ist das
der Normalfall (A.2). Eine Sitzung gehoert Calvin, nicht dem Prozess.

Zwei Dateien, und die Aufteilung hat einen Grund (A.4):

    werkstatt/sitzungen.jsonl        der Kopf - eine Zeile je Sitzung
    werkstatt/sitzungen/s-<ts>.json  der Wortlaut dieser Sitzung

Der Kopf muss sich ueberfliegen lassen (welche ist offen? welche war heute?),
der Wortlaut ist gross und wird selten gebraucht - nur beim Reinrutschen und
bei der Gegenpruefung. Er verfaellt nicht: A.6 verlangt, dass Calvin Tage
spaeter in ein Thema wieder einsteigen kann, und ein geloeschter Wortlaut ist
weg, ohne dass es jemand merkt. Es gibt deshalb absichtlich kein
`aufraeumen()` - wer es baut, zerstoert genau die Anforderung, fuer die A.6
da ist (B2 des Mac).
"""
from __future__ import annotations

from einstellungen import NUTZER
import json
import os
import threading
import time
from datetime import datetime, date
from pathlib import Path

HIER = Path(__file__).resolve().parent
WERKSTATT = HIER / "werkstatt"
KOEPFE = WERKSTATT / "sitzungen.jsonl"
ORDNER = WERKSTATT / "sitzungen"

# RUHE_MIN   So lange muss geschwiegen werden, damit die Sitzung zu Ende ist.
#            Gemessen wird das Schweigen seit der letzten Frage, NICHT die
#            Gesamtdauer (A.1): Ein Gespraech, in dem Calvin eine Stunde lang
#            alle zwei Minuten etwas fragt, ist EIN Gespraech. Es nach zehn
#            Minuten zu zerschneiden wuerde mitten im Zusammenhang trennen und
#            "und davor?" kaputtmachen. wissen.py misst heute 8 Minuten; 10
#            ist Calvins Richtwert.
# DAUER_MAX_H Eine Obergrenze braucht es trotzdem. Ohne sie laeuft eine
#            Sitzung tagelang, wenn Calvin regelmaessig fragt - und die
#            Zusammenfassung eines Tagesgespraechs ist keine mehr. Wird sie
#            ueberschritten, wird geschlossen und sofort eine Nachfolgerin
#            geoeffnet, mit `fortsetzung_von`.
# ANSCHLUSS_MIN Redet er nach einer Pause weiter, ist das eine neue Sitzung -
#            aber eine, die auf die alte verweist. Spaeter als das ist es ein
#            neues Gespraech, kein Anschluss.
RUHE_MIN, DAUER_MAX_H, ANSCHLUSS_MIN = 10, 6, 90

# Die vier Marken aus A.4. Jede Stufe setzt ihre eigene; daran erkennt die
# naechste, was noch zu tun ist, und die Nacht, was liegengeblieben ist. Ein
# Neustart mitten in B verliert nichts - die Marke steht noch auf null, also
# wird es wiederholt.
MARKEN = ("geschlossen", "zusammenfassung", "abgeleitet", "geprueft")

# Lesen, aendern, schreiben ist nicht atomar. Im Bewohner laufen der
# Gespraechsfaden, der Abschlussfaden (B) und die Nacht (D) nebeneinander und
# wuerden einander die Koepfe ueberschreiben. Die Datei selbst wird immer im
# Ganzen und ueber os.replace getauscht, also sieht ein Leser nie eine halbe
# Datei - auch nicht aus einem anderen Prozess.
_SPERRE = threading.RLock()


# ------------------------------------------------------------------ Ablage


def _zeilen_lesen() -> list[dict]:
    """Alle Koepfe. Kaputte Zeilen werden uebersprungen, wie bei journal.jsonl.

    Eine halb geschriebene Zeile darf nicht den ganzen Bestand unlesbar
    machen; dann waere eine einzige abgebrochene Schreiboperation das Ende
    aller Sitzungen (Anhang 3).
    """
    try:
        roh = KOEPFE.read_text(encoding="utf-8")
    except OSError:
        return []
    koepfe = []
    for zeile in roh.splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            k = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        if isinstance(k, dict) and k.get("id"):
            koepfe.append(k)
    return koepfe


def _zeilen_schreiben(koepfe: list[dict]) -> None:
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    # Mit der Prozessnummer im Namen, aus demselben Grund wie in
    # haus.schreiben(): Zwei Prozesse mit demselben vorlaeufigen Namen tauschen
    # einander die halbe Datei unter den Fuessen weg. Der Austausch ist atomar,
    # das Schreiben davor nicht.
    tmp = KOEPFE.with_suffix(".jsonl.%d.tmp" % os.getpid())
    tmp.write_text(
        "".join(json.dumps(k, ensure_ascii=False) + "\n" for k in koepfe),
        encoding="utf-8")
    os.replace(tmp, KOEPFE)


def lesen() -> list[dict]:
    """Die Koepfe, in der Reihenfolge, in der sie angelegt wurden."""
    with _SPERRE:
        return _zeilen_lesen()


def kopf(sid: str) -> dict | None:
    for k in lesen():
        if k.get("id") == sid:
            return k
    return None


def _aendern(sid: str, wie) -> dict | None:
    """Einen Kopf unter der Sperre aendern. `wie` bekommt den Kopf und aendert
    ihn an Ort und Stelle."""
    with _SPERRE:
        koepfe = _zeilen_lesen()
        for k in koepfe:
            if k.get("id") == sid:
                wie(k)
                _zeilen_schreiben(koepfe)
                return dict(k)
    return None


def _wortlaut_pfad(sid: str) -> Path:
    return ORDNER / f"{sid}.json"


def paare(sid: str, letzte: int | None = None) -> list[dict]:
    """Der Wortlaut einer Sitzung - oder die letzten `letzte` Paare davon.

    Der Deckel steht beim Aufrufer und nicht hier: Eine Sitzung mit 200
    Paaren sprengt jeden Prompt (Anhang 3), aber wer nachsieht, ob die
    Zusammenfassung etwas unterschlagen hat, braucht alles.
    """
    if not sid:
        return []
    try:
        d = json.loads(_wortlaut_pfad(sid).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    # Eine reine Liste wird auch gelesen - falls der Wortlaut je anders
    # geschrieben wurde als heute.
    p = d if isinstance(d, list) else d.get("paare") or []
    p = [x for x in p if isinstance(x, dict)]
    return p[-letzte:] if letzte else p


def paar_anhaengen(sid: str, frage: str | None, antwort: str,
                   ts: float | None = None) -> None:
    """Ein Frage/Antwort-Paar an die Sitzung haengen.

    `frage` darf None sein - dann ist es eine Ansprache, also etwas, das ER
    von sich aus gesagt hat (B9 des Mac).

    `sid is None` ist kein Fehler, sondern der Normalfall bei Testfragen
    (A.5 Regel 0). Der Aufrufer soll nicht pruefen muessen.
    """
    if not sid:
        return
    ts = time.time() if ts is None else ts
    with _SPERRE:
        ORDNER.mkdir(parents=True, exist_ok=True)
        pfad = _wortlaut_pfad(sid)
        try:
            d = json.loads(pfad.read_text(encoding="utf-8"))
            if isinstance(d, list):
                d = {"id": sid, "paare": d}
        except (OSError, json.JSONDecodeError):
            d = {"id": sid, "paare": []}
        d.setdefault("paare", []).append(
            {"frage": frage, "antwort": antwort, "ts": ts})
        tmp = pfad.with_suffix(".json.%d.tmp" % os.getpid())
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, pfad)
        anzahl = len(d["paare"])

        def wie(k: dict) -> None:
            k["paare"] = anzahl
            k["letzte_frage"] = max(k.get("letzte_frage") or 0, ts)
            # Eine Antwort, die nach dem Schliessen fertig wird: Das Paar
            # gehoert trotzdem dazu, und die Zusammenfassung kennt es noch
            # nicht. Also wird sie ueberholt, nicht das Paar verworfen.
            if k.get("geschlossen") and k.get("zusammenfassung") is not None:
                k["zusammenfassung"] = None
                k["abgeleitet"] = None

        _aendern(sid, wie)


# ------------------------------------------------------------------ Anlegen


def _id_neu(ts: float, koepfe: list[dict]) -> str:
    """`s-<Sekunde>`, und bei Gleichstand mit Zusatz.

    Zwei Absender koennen in derselben Sekunde anfangen; zwei Sitzungen mit
    derselben Kennung waeren eine, und der Wortlaut beider landete in einer
    Datei.
    """
    basis = "s-%d" % int(ts)
    da = {k.get("id") for k in koepfe}
    if basis not in da:
        return basis
    for i in range(1, 1000):
        kandidat = "%s-%d" % (basis, i)
        if kandidat not in da:
            return kandidat
    return "%s-%06d" % (basis, int((ts % 1) * 1e6))


def _anlegen(ts: float, von: str, fortsetzung_von: str | None = None) -> dict:
    with _SPERRE:
        koepfe = _zeilen_lesen()
        kopf = {"id": _id_neu(ts, koepfe),
                "von": str(von or NUTZER).lower(),
                "begonnen": ts,
                "letzte_frage": ts,
                "geschlossen": None,
                "paare": 0,
                "fortsetzung_von": fortsetzung_von,
                "zusammenfassung": None,
                "abgeleitet": None,
                "geprueft": None}
        koepfe.append(kopf)
        _zeilen_schreiben(koepfe)
        return dict(kopf)


# ------------------------------------------------------------------ Zustand


def _offen_alle(von: str | None = None) -> list[dict]:
    """Alles, was nicht geschlossen ist - auch das, was schon ruht.

    Die ruhenden braucht `faellig()`; wer eine Frage zuordnet, will sie nicht.
    """
    koepfe = [k for k in lesen() if not k.get("geschlossen")]
    if von is not None:
        v = str(von).lower()
        koepfe = [k for k in koepfe if str(k.get("von") or NUTZER) == v]
    return koepfe


def offene(jetzt: float, von: str | None = None) -> list[dict]:
    """Die Sitzungen, in die eine Frage JETZT noch faellt.

    Offen heisst hier nicht nur "Marke geschlossen ist null", sondern auch
    "die letzte Frage ist weniger als RUHE_MIN her und die Obergrenze ist
    nicht ueberschritten". Genau das ist die Bedingung aus A.5 Regel 2, und
    sie steht hier an einer Stelle, damit die Zuordnung und der
    Abschlussfaden nicht zwei verschiedene Vorstellungen von "offen" haben.
    """
    lebt = []
    for k in _offen_alle(von):
        if jetzt - (k.get("letzte_frage") or 0) >= RUHE_MIN * 60:
            continue
        if jetzt - (k.get("begonnen") or 0) >= DAUER_MAX_H * 3600:
            continue
        lebt.append(k)
    lebt.sort(key=lambda k: k.get("letzte_frage") or 0, reverse=True)
    return lebt


def faellig(jetzt: float) -> dict | None:
    """EINE Sitzung, die zu schliessen ist - die aelteste. Sonst None.

    Eine, nicht alle (B11 des Mac): Nach einem Ausfall liegen mehrere da, und
    der Faden wuerde sie hintereinander zusammenfassen - mehrere
    Modellaufrufe am Stueck, waehrend Calvin vielleicht gerade redet. Er
    sieht jede Minute nach; der Rest kommt beim naechsten Mal.

    Einen Sonderfall fuer den Start braucht es dadurch nicht (B.2): Wer
    hochfaehrt, findet die offene Sitzung von vorhin einfach als faellig vor.
    Ist ihre letzte Frage noch frisch, bleibt sie offen - vielleicht hat
    Calvin nur einen Neustart angestossen und redet gleich weiter.
    """
    reif = [k for k in _offen_alle()
            if jetzt - (k.get("letzte_frage") or 0) >= RUHE_MIN * 60
            or jetzt - (k.get("begonnen") or 0) >= DAUER_MAX_H * 3600]
    if not reif:
        return None
    reif.sort(key=lambda k: k.get("begonnen") or 0)
    return reif[0]


def schliessen(sid: str, jetzt: float | None = None) -> dict:
    """Die Marke `geschlossen` setzen - VOR der Arbeit, nicht danach.

    Sie ist der Anspruch auf die Sitzung. Setzte sie erst, wer fertig ist,
    griffen zwei Faeden dieselbe Sitzung und es entstuenden zwei
    Zusammenfassungen (Anhang 3). Eine schon geschlossene Sitzung wird nicht
    noch einmal geschlossen; der Zeitpunkt des ersten Mals gilt.
    """
    jetzt = time.time() if jetzt is None else jetzt

    def wie(k: dict) -> None:
        if not k.get("geschlossen"):
            k["geschlossen"] = jetzt

    return _aendern(sid, wie) or {}


def marke_setzen(sid: str, feld: str, wert) -> None:
    """Eine der vier Marken aus A.4 setzen.

    Nur diese vier: Ein Tippfehler wuerde sonst ein neues Feld anlegen, das
    niemand liest, und die Stufe liefe jede Nacht wieder.
    """
    if feld not in MARKEN:
        raise ValueError("keine Marke: %s (erlaubt: %s)"
                         % (feld, ", ".join(MARKEN)))

    def wie(k: dict) -> None:
        k[feld] = wert

    _aendern(sid, wie)


# ------------------------------------------------------------------ Zuordnen


def _anschluss_an(ts: float, von: str) -> str | None:
    """Die Sitzung, an die eine neue anschliesst - oder None.

    Gemessen ab der letzten FRAGE der alten, nicht ab ihrem Schliessen: "nach
    zwanzig Minuten weiterreden" heisst zwanzig Minuten, nachdem Calvin
    zuletzt etwas gesagt hat (A.3).
    """
    v = str(von or NUTZER).lower()
    kandidaten = [k for k in lesen()
                  if str(k.get("von") or NUTZER) == v
                  and (k.get("letzte_frage") or 0) <= ts
                  and ts - (k.get("letzte_frage") or 0) <= ANSCHLUSS_MIN * 60]
    if not kandidaten:
        return None
    kandidaten.sort(key=lambda k: k.get("letzte_frage") or 0)
    return kandidaten[-1].get("id")


def sitzung_fuer(ts: float, von: str, gewuenscht: str | None = None) -> str | None:
    """Zu welcher Sitzung gehoert diese Frage? Reine Zeitrechnung.

    Regel 0: `von == "test"` bekommt KEINE Sitzung (B6 des Mac). Ohne diese
        Regel als erste wuerden die Pruefläufe des Mac zusammengefasst und zu
        Fakten abgeleitet, zwoelf Fragen je Lauf. `_gespraech_merken` steigt
        bei Testfragen schon aus, aber der Sitzungsfaden ist ein anderer Weg
        und erbt das nicht. Die Regel steht VOR der Zuordnung, damit keine
        Testsitzung erst entsteht und dann gefiltert werden muss.
    Regel 1: Traegt die Frage ein Feld `sitzung`, gilt das - Calvin rutscht in
        ein altes Gespraech zurueck. Ist dabei eine andere offen, wird die
        geschlossen: Sie ist zu Ende, sonst haette er nicht gewechselt (B5).
    Regel 2: Sonst die offene Sitzung desselben Absenders. Desselben - zwei
        Geraete duerfen ihre Fragen nicht vermischen (Anhang 3).
    Regel 3: Sonst eine neue, mit `fortsetzung_von`, wenn sie innerhalb von
        ANSCHLUSS_MIN auf eine aeltere folgt.
    """
    if str(von or "").lower() == "test":
        return None

    with _SPERRE:
        if gewuenscht and kopf(gewuenscht):
            for k in _offen_alle(von):
                if k.get("id") != gewuenscht:
                    schliessen(k["id"], ts)
            wieder_aufnehmen(gewuenscht, ts)
            return gewuenscht

        lauft = offene(ts, von)
        if lauft:
            sid = lauft[0]["id"]
            _aendern(sid, lambda k: k.__setitem__("letzte_frage", ts))
            return sid

        # Ueber der Obergrenze oder lange still: beides wird hier geschlossen,
        # damit nicht zwei offene Sitzungen je Absender zurueckbleiben. Der
        # Abschlussfaden findet sie danach ueber die Marke.
        for k in _offen_alle(von):
            schliessen(k["id"], ts)
        return _anlegen(ts, von, _anschluss_an(ts, von))["id"]


def ansprache_eroeffnet(anlass: str, ts: float | None = None,
                        von: str = NUTZER) -> str:
    """Wenn ER anfaengt: die Ansprache eroeffnet die Sitzung (B9 des Mac).

    Eine unaufgeforderte Ansprache ist keine Frage und faellt durch alle drei
    Regeln. Antwortet Calvin darauf, begaenne die Sitzung mit seiner Antwort -
    und der Anlass, worum es ueberhaupt ging, stuende nicht drin. Die
    Zusammenfassung waere eine Antwort ohne Frage.

    Sie ist das erste Paar, mit `frage: null` und dem Anlass als Antwort.
    Damit traegt die Sitzung den Anlass auch dann, wenn Calvin nie antwortet;
    antwortet er, faellt seine Antwort nach Regel 2 von allein hinein.

    Redet er gerade ohnehin mit ihm, wird nichts Neues eroeffnet: Was er
    mitten im Gespraech von sich aus sagt, gehoert in dieses Gespraech. Es
    gibt eine offene Sitzung je Absender, nicht zwei.
    """
    ts = time.time() if ts is None else ts
    with _SPERRE:
        lauft = offene(ts, von)
        sid = lauft[0]["id"] if lauft else _anlegen(ts, von)["id"]
        paar_anhaengen(sid, None, anlass, ts)
        return sid


def wieder_aufnehmen(sid: str, jetzt: float | None = None) -> dict:
    """Ein Thema Tage spaeter wieder aufnehmen - dieselbe Sitzung, keine neue.

    Calvin: "Wenn ich ueber irgendein Thema mit ihm gegruebelt habe, will ich
    spaeter wieder in dieses Thema einsteigen koennen." (A.6)

    Die Zusammenfassung bleibt stehen: Sie ist der Kurzzeitkontext, mit dem er
    wieder einsteigt, und sie wird beim naechsten Ende ueberholt, nicht
    geloescht - korrigieren statt loeschen. Die Arbeitsmarken dagegen fallen
    weg, denn es kommt neuer Inhalt dazu, der noch nicht abgeleitet und noch
    nicht geprueft ist.
    """
    jetzt = time.time() if jetzt is None else jetzt

    def wie(k: dict) -> None:
        k["geschlossen"] = None
        k["letzte_frage"] = jetzt
        k["abgeleitet"] = None
        k["geprueft"] = None

    return _aendern(sid, wie) or {}


# ------------------------------------------------------------------ Finden


def _woerter(text: str) -> list[str]:
    roh = "".join(c.lower() if c.isalnum() else " " for c in text).split()
    return [w for w in roh if len(w) > 3]


def suchen(begriff: str, n: int = 5) -> list[dict]:
    """Sitzungen nach Thema - ueber ihre Zusammenfassungen (A.6 Punkt 2).

    Ohne Modell und ohne Datenbank: Die Zusammenfassung steht im Kopf, und
    mehr als Wortvergleich braucht "Was war das mit dem Kinderarzt?" nicht.
    Im Gedaechtnis liegt sie zusaetzlich als Art `sitzung`; das ist der Weg
    fuer die unscharfe Suche, dieser hier der fuer die schnelle.
    """
    gesucht = _woerter(begriff)
    if not gesucht:
        return []
    treffer = []
    for k in lesen():
        z = str(k.get("zusammenfassung") or "")
        if not z:
            continue
        zl = z.lower()
        wie_viele = sum(1 for w in gesucht if w in zl)
        if wie_viele:
            treffer.append((wie_viele, k.get("begonnen") or 0,
                            {"id": k.get("id"), "begonnen": k.get("begonnen"),
                             "zusammenfassung": z}))
    treffer.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [t[2] for t in treffer[:n]]


def am_tag(datum: date | datetime | str) -> list[dict]:
    """Alle Sitzungen eines Tages - fuer "Worueber haben wir gestern geredet?".

    Ortszeit, weil der Tag in Ortszeit gemeint ist: fromtimestamp() rechnet
    in der Zeitzone des Rechners, und der steht bei Calvin.
    """
    if isinstance(datum, str):
        datum = datetime.strptime(datum[:10], "%Y-%m-%d").date()
    elif isinstance(datum, datetime):
        datum = datum.date()
    treffer = [k for k in lesen()
               if datetime.fromtimestamp(k.get("begonnen") or 0).date() == datum]
    treffer.sort(key=lambda k: k.get("begonnen") or 0)
    return treffer


# ------------------------------------------------------------------ Anzeige


def main() -> int:
    jetzt = time.time()
    koepfe = lesen()
    if not koepfe:
        print("noch keine Sitzung.")
        return 0
    print("%d Sitzungen, %d offen\n" % (len(koepfe), len(_offen_alle())))
    lebt = {k["id"] for k in offene(jetzt)}
    for k in koepfe[-20:]:
        begonnen = datetime.fromtimestamp(k.get("begonnen") or 0)
        zustand = "zu"
        if not k.get("geschlossen"):
            zustand = "offen" if k.get("id") in lebt else "faellig"
        print("%s  %s  %-7s %2d Paare%s%s"
              % (k.get("id"), begonnen.strftime("%d.%m. %H:%M"), zustand,
                 k.get("paare") or 0,
                 "  < %s" % k["fortsetzung_von"] if k.get("fortsetzung_von")
                 else "",
                 "  %s" % str(k.get("zusammenfassung"))[:60]
                 if k.get("zusammenfassung") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
