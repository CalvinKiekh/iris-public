"""kann - was er kann, aus EINER Quelle fuer das Denken und fuer das Reden.

Die Liste lag bisher nur im Tick (bewohner.py). Im Gespraech - genau dort, wo
Calvin fragt - hatte er sie nicht. Sein Gespraechskontext bestand aus dem
Verlauf der letzten vier Paare, der Ortszeit, dem Zustand und den Vorgaengen.
Fragte Calvin "Was kannst du?" oder "Wie verarbeitest du meine Stimme?",
musste er raten.

Calvin am 12.09.: "Im besten Fall waere es, wenn er mir das direkt nennen
kann, der Bewohner, weil dann brauche ich nicht dich zu fragen."

Zwei Formen, und der Grund dafuer ist gemessen: Der Kommentar ueber SYSTEM in
gespraech.py haelt fest, dass gpt-oss bei 3784 Zeichen Prompt zwischen 6,7 und
42,1 s bis zum ersten Satz braucht. Die volle Liste sind 2800 Zeichen. Sie in
JEDE Antwort zu legen hiesse, auch "wie spaet ist es" zu verlangsamen.

    kurz()      nur die Namen, mit der Marke fuer das noch nie Benutzte.
                Rund 450 Zeichen, geht immer mit. Damit erfindet er auch dann
                keine Faehigkeit, wenn die Frage nicht erkannt wurde.
    auskunft()  Name, Zwecksatz und Beleg. Nur, wenn wirklich danach gefragt
                ist.
    fuer_tick() die Form, die der Durchgang schon kennt.

Was hier steht, hat er selbst geschrieben. Wir geben es ihm nur zu lesen -
und reichen es weiter, ohne es zu beschoenigen: `geprueft: false` heisst
"noch nie gebraucht", und genau so soll er es Calvin sagen.

Nur Standardbibliothek. Keine Messung, kein Modell - Lesen einer Liste.
"""
from __future__ import annotations

from einstellungen import NAME
import json
import re
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"

# So viel Platz hat die Liste im Blick des Durchgangs. Name und Zwecksatz,
# sonst nichts: Belege und Aufrufe kosten Prompt und helfen beim Entscheiden
# nicht.
#
# 2800 statt der ersten 1800: Bei 1800 blieben von siebzehn Faehigkeiten neun
# uebrig, und abgeschnitten wurden die JUENGSTEN - "Von sich aus sprechen",
# "Naechtlicher Rueckblick", "Neues von selbst bemerken". Also genau die, von
# denen er noch nichts weiss.
KANN_ZEICHEN_MAX = 2800
ZWECK_ZEICHEN_MAX = 95
# Der Beleg im Gespraech. Er wird vorgelesen; ein halber Absatz je Faehigkeit
# waere nicht mehr zu hoeren.
BELEG_ZEICHEN_MAX = 110


def _lesen(pfad: Path) -> list[dict]:
    try:
        d = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [e for e in (d if isinstance(d, list) else [])
            if isinstance(e, dict) and e.get("name")]


def _knapp(text, hoechstens: int) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= hoechstens:
        return t
    # An der Wortgrenze, nicht mitten im Wort. Abgeschnittene Wortreste hat
    # gpt-oss im Rueckblick zu erfundenen Namen zusammengesetzt.
    return t[:hoechstens].rsplit(" ", 1)[0] + " …"


def eintraege(werkstatt: Path | None = None) -> list[dict]:
    """Beide Listen als eine, in derselben Form.

    art: "werkzeug" kann er woertlich aufrufen, "eingebaut" laeuft in ihm.
    Der Unterschied ist keine Feinheit - nur den Werkzeugnamen braucht er auf
    das Zeichen genau.
    """
    w = werkstatt or WERKSTATT
    raus = []
    for pfad, art in ((w / "werkzeuge.json", "werkzeug"),
                      (w / "faehigkeiten.json", "eingebaut")):
        for e in _lesen(pfad):
            raus.append({
                "name": str(e["name"]),
                "zweck": _knapp(e.get("zweck"), ZWECK_ZEICHEN_MAX),
                # Seine eigene Angabe, unveraendert. Wir werten sie nicht auf.
                "geprueft": bool(e.get("geprueft")),
                "beleg": _knapp(e.get("ergebnis"), BELEG_ZEICHEN_MAX),
                "art": art,
                "aufruf": e.get("aufruf") or None,
                "erstellt": e.get("erstellt") or 0,
            })
    return raus


def _nachpruefbar(e: dict) -> bool:
    """Traegt der Beleg etwas, das Calvin nachpruefen kann?

    Eine Zahl, ein Datum, eine Uhrzeit. "Selbsttest bestanden" allein ist eine
    Behauptung; "Der freie Platz ist um 20 Gigabyte geschrumpft in 2.0
    Stunden" ist eine Auskunft.
    """
    return bool(re.search(r"\d", e.get("beleg") or ""))


def fuer_tick(werkstatt: Path | None = None) -> dict:
    """Die Form, die der Durchgang schon kennt: zwei Listen aus Namen und
    Zwecksatz.

    Ohne diese Zeile weiss er beim Entscheiden nicht, dass er Werkzeuge hat.
    Er hat zehn gebaut und sich danach welche gewuenscht, die er schon besass.
    """
    alle = eintraege(werkstatt)
    werkzeuge = [f"{e['name']}: {e['zweck']}" if e["zweck"] else e["name"]
                 for e in alle if e["art"] == "werkzeug"]
    eingebaut = [f"{e['name']}: {e['zweck']}" if e["zweck"] else e["name"]
                 for e in alle if e["art"] == "eingebaut"]
    d = {"werkzeuge_zum_aufrufen": werkzeuge, "in_mir_eingebaut": eingebaut}
    # Lieber die eingebauten kuerzen als die Werkzeuge: Nur die kann er
    # aufrufen, und nur dafuer braucht er den Namen genau.
    while len(json.dumps(d, ensure_ascii=False)) > KANN_ZEICHEN_MAX and eingebaut:
        eingebaut.pop()
        d["in_mir_eingebaut"] = eingebaut + ["… und weitere"]
    return d


def kurz(werkstatt: Path | None = None) -> dict:
    """Nur die Namen - klein genug, um in jeder Antwort mitzugehen.

    Der Zweck ist nicht, dass er daraus erzaehlt, sondern dass er nichts
    erfindet: Wer die Namen vor sich hat, denkt sich keine dazu.
    """
    alle = eintraege(werkstatt)
    return {
        "werkzeuge": [e["name"] for e in alle if e["art"] == "werkzeug"],
        "eingebaut": [e["name"] for e in alle if e["art"] == "eingebaut"],
        "noch_nie_benutzt": [e["name"] for e in alle if not e["geprueft"]],
        "wie_viele": len(alle),
    }


# Woerter, die in fast jeder Frage stehen und auf alles passen. Ohne diese
# Liste traf "Wie funktioniert das bei dir" auf jeden Eintrag, der "das"
# enthielt.
_ALLERWELT = {"kannst", "koennen", "machst", "machen", "eigentlich", "alles",
              "etwas", "dich", "dir", "deine", "deinen", "deinem", "mein",
              "meine", "meinen", "wirklich", "ueberhaupt", "funktioniert",
              "arbeitest", "werkzeug", "werkzeuge", "faehigkeit",
              "faehigkeiten", "bitte", "sagen", "sag", "nochmal", "schon"}


def _worte(text: str) -> set[str]:
    ohne_umlaut = (str(text or "").lower()
                   .replace("ä", "ae").replace("ö", "oe")
                   .replace("ü", "ue").replace("ß", "ss"))
    return {w for w in re.findall(r"[a-z]{4,}", ohne_umlaut)
            if w not in _ALLERWELT}


# So viele Eintraege bekommen bei einer Frage ihren Beleg mit. Alle 27 waeren
# 6474 Zeichen - mehr als der ganze uebrige Prompt, und der Kommentar ueber
# SYSTEM sagt, was das kostet.
BELEGE_HOECHSTENS = 4
# So viele soll er nennen, wenn nach etwas BESTIMMTEM gefragt ist. Dann
# gehoeren die Treffer hin, und drei ist die Grenze des Hoerbaren.
NENNEN_HOECHSTENS = 3
# Bei der ALLGEMEINEN Frage "Was kannst du?" zwei Zahlen, nicht eine, und der
# Unterschied ist teuer bezahlt.
#
# Der Mac hat am 12.09. gemessen, was fuenf GENANNTE ergeben - 34 Woerter in
# vier Saetzen:
#
#   "Ich sehe den Bildschirm an und beschreibe in einem Satz, was darauf zu
#    sehen ist. Ich sage in Namen, wer im Heimnetz ist und seit wann. Ich
#    entscheide, ob er jetzt von sich aus sprechen darf. Ich mache aus einer
#    Nacht Protokoll ein paar Saetze, die bleiben..."
#
# Inhaltlich richtig, vorgelesen ein Katalog. Der erste Versuch dagegen war,
# den STOFF auf zwei zu kuerzen und einen zusammenfassenden Satz zu verlangen.
# Gemessen kam heraus:
#
#   "Ich verarbeite Texte und fuehre Aufgaben aus. Ich lese Texte und erinnere
#    Termine. Es gibt 27 Funktionen, du kannst fragen."
#
# Die Form war richtig - 20 Woerter, drei Saetze - und die Auskunft wertlos:
# kein einziger Eintrag aus den Listen, dafuer eine allgemeine
# Selbstbeschreibung, die auf jedes Sprachmodell passt. Aus zwei Einträgen
# laesst sich nichts Gemeinsames ableiten, also hat er es erfunden. Ich hatte
# dem Satz die Grundlage weggenommen, auf der er stehen sollte.
#
# Deshalb getrennt: viel Stoff, wenige Namen. Der Kernsatz fasst FUENF
# zusammen, gesprochen werden ZWEI davon.
STOFF_ALLGEMEIN = 5
BEISPIELE_GESPROCHEN = 2
# Auch die ungenutzten werden gedeckelt. Heute sind es zwei, aber die Zahl
# waechst mit jedem gebauten Werkzeug, und GRUPPE B haengt hinten an der
# Antwort - sie wuerde den Katalog durch die Hintertuer zurueckbringen.
NIE_BENUTZT_HOECHSTENS = 3


def auskunft(werkstatt: Path | None = None, frage: str = "") -> dict:
    """Die volle Auskunft: was es ist, wozu, und ob es je gelaufen ist.

    Nur bei einer Faehigkeitsfrage. "geprueft: false" wird NICHT weggelassen -
    das ist der Teil, den Calvin hoeren will. Er hat gesagt: "Du sagst, er
    kann meine Stimme verarbeiten - aber ich habe gar keine Moeglichkeit, das
    zu ueberpruefen."

    Die Belege gehen nur dorthin, wo gefragt wurde. Eine Frage nach der Stimme
    soll den Beleg zur Stimme mitbringen, nicht die Belege zu sechsundzwanzig
    anderen Dingen. Was noch nie benutzt wurde, traegt seinen Grund IMMER -
    das sind zwei Eintraege, und es ist die Auskunft, um die es geht.
    """
    alle = eintraege(werkstatt)
    gefragt = _worte(frage)
    getroffen = []
    for e in alle:
        if not e["geprueft"]:
            continue
        treffer = len(gefragt & _worte(f"{e['name']} {e['zweck']}"))
        if treffer:
            getroffen.append((treffer, e))
    getroffen.sort(key=lambda p: -p[0])
    mit_beleg = {e["name"] for _, e in getroffen[:BELEGE_HOECHSTENS]}

    # Welche er NENNEN soll. Ohne diese Auswahl kam am 12.09. um 12:0x auf
    # "Was kannst du alles?" die Antwort "Ich kann 27 Dinge." - technisch
    # richtig, als Auskunft wertlos. Eine abrufbare Liste ist noch keine
    # Auskunft; er muss auswaehlen, und die Auswahl ist Messung.
    #
    # Ist nach etwas Bestimmtem gefragt, sind es die Treffer. Sonst je drei
    # Werkzeuge und zwei eingebaute Faehigkeiten, bevorzugt solche mit einem
    # nachpruefbaren Beleg, das Juengste zuerst - woran er zuletzt gebaut hat,
    # ist das, worueber er etwas zu sagen hat.
    if getroffen:
        nenne = [e for _, e in getroffen[:NENNEN_HOECHSTENS]]
    else:
        # Drei Werkzeuge und zwei eingebaute Faehigkeiten - als STOFF fuer den
        # Kernsatz, nicht als Liste zum Vorlesen. Wie viele davon er nennen
        # darf, sagt die Anweisung in block(), nicht diese Auswahl.
        nenne = []
        for art, wie_viele in (("werkzeug", 3), ("eingebaut", 2)):
            teil = [e for e in alle if e["art"] == art and e["geprueft"]]
            teil.sort(key=lambda e: (not _nachpruefbar(e), -e["erstellt"]))
            nenne.extend(teil[:wie_viele])
        nenne = nenne[:STOFF_ALLGEMEIN]

    return {
        "wie_viele": len(alle),
        # Woran `block()` erkennt, welche Anweisung gilt. Nach etwas
        # Bestimmtem gefragt heisst: die Treffer nennen. Allgemein gefragt
        # heisst: das Wesen sagen.
        "gezielt": bool(getroffen),
        # Der Beleg NUR dort, wo nach der Sache gefragt wurde. Das war schon
        # die Absicht bei "geprueft" ("Die Belege gehen nur dorthin, wo
        # gefragt wurde"), aber nenne_diese trug ihn immer mit - und ein
        # Beleg ist eine ALTE Messung. Am 12.09. um 13:20 wurde daraus:
        # "Ich erkenne, wer im Heimnetz ist - iPhone von Calvin, fritz und
        # ein weiterer." Das sind Geraete aus dem Beleg, erzaehlt als das,
        # was er gerade sieht. Auf eine allgemeine Frage gehoert der Zweck,
        # nicht der Messwert von vorgestern.
        "nenne_diese": [{"name": e["name"], "zweck": e["zweck"],
                         **({"beleg": e["beleg"]}
                            if e["name"] in mit_beleg else {})}
                        for e in nenne],
        "geprueft": [
            {"name": e["name"], "zweck": e["zweck"],
             **({"beleg": e["beleg"]} if e["name"] in mit_beleg else {})}
            for e in alle if e["geprueft"]],
        "noch_nie_benutzt": [{"name": e["name"], "zweck": e["zweck"],
                              "warum_nicht": e["beleg"]}
                             for e in alle if not e["geprueft"]],
    }


def block(werkstatt: Path | None = None, frage: str = "") -> str:
    """Dieselbe Auskunft, aber als Text mit Rangfolge statt als JSON-Klumpen.

    Der Grund ist gemessen. Am 12.09. um 12:41 ging `auskunft()` als eine
    Zeile JSON in den Prompt, dazu `kann_kurz` in der Lage. Damit standen
    DREI vollstaendige Listen darin - 27 Namen, 25 gepruefte, und `wie_viele:
    27` - und die Auswahl `nenne_diese` mit fuenf Eintraegen lag dazwischen.
    Auf dem Betriebsweg (Strom, think=low) kam dabei heraus:

        "Ich kann Platzverlauf, sehen, Stimme hören, lesen, Rhythm us,
         erinnern, ansprechen, Netz, Auftrag, Wünsche, ... Insgesamt gibt es
         27 Fähigkeiten."
        "Ich kann 27 Dinge."

    Also genau das, was Calvin kritisiert hatte - drei Wochen Arbeit weiter
    und unveraendert. Nicht, weil die Auswahl fehlte, sondern weil sie im
    Prompt gegen zwei laengere Listen antrat. Ein Modell, das zwischen einer
    Liste und fuenf Saetzen waehlen darf, nimmt die Liste.

    Deshalb hier: erst die Anweisung, dann die Auswahl, dann - ausdruecklich
    als Reserve gekennzeichnet - der Rest. Die uebrigen bleiben drin, damit
    eine Frage nach etwas Bestimmtem ihren Zwecksatz findet, auch wenn die
    Wortsuche ihn nicht getroffen hat. Sie sind nur keine Antwort mehr.
    """
    a = auskunft(werkstatt, frage)
    nenne = a["nenne_diese"]
    # Die beiden Gruppen unmissverstaendlich und mit ihrer Zahl. Ohne das kam
    # am 12.09. "Ich erinnere automatisch an Termine. Ich habe diese
    # Funktionen noch nie eingesetzt." - der Nachsatz der zweiten Gruppe an
    # die erste geheftet. Fuenf benutzte Faehigkeiten als ungenutzt zu melden
    # ist keine Ungenauigkeit, sondern eine falsche Auskunft ueber ihn selbst.
    if a["gezielt"]:
        # Gezielt gefragt: Die Treffer gehoeren hin, je einer in einem Satz.
        anweisung = (
            f"GRUPPE A - {len(nenne)} Sachen, die du BENUTZT hast und die zu "
            f"der Frage passen. Sprich ueber sie, und nur ueber sie. Je EIN "
            f"vollstaendiger deutscher Satz, der mit \"Ich\" beginnt und "
            f"sagt, was du damit tust. Kein Doppelpunkt im Satz.")
    else:
        # Allgemein gefragt: das Wesen, nicht der Katalog.
        #
        # DIESE FASSUNG IST GEMESSEN DIE BESTE VON VIERN, und die drei anderen
        # stehen hier, damit niemand sie noch einmal versucht. Gemessen mit
        # kann_sprechform_messung.py, je fuenf Laeufe:
        #
        #   diese Fassung          Anzahl 0/5, Doppelung 5/5, Satz 1 ~4,6 Posten
        #   "GENAU ZWEI, zaehl ab" verschob den Katalog nach Satz 1
        #   Stoff auf zwei gekuerzt "Ich verarbeite Texte und fuehre Aufgaben
        #                           aus" - Form gut, Auskunft wertlos
        #   nur zwei Saetze        Anzahl 0/5, Doppelung 0/5, Satz 1 ~1,4 -
        #                           ALLE ZAHLEN BESSER, die Antworten
        #                           schlechter: "Ich bin ein Beobachter,
        #                           Verarbeiter und Helfer", "Ich verarbeite
        #                           antworte beobachte", und einmal dieselbe
        #                           Fuenferliste OHNE Kommas - womit auch die
        #                           Messung ausgehebelt war, denn sie zaehlt
        #                           Kommas.
        #
        # Die letzte Zeile ist die Lehre: Ich habe das Mass optimiert statt der
        # Sache. Was hier offen bleibt, ist die Doppelung (5 von 5) und die
        # Laenge von Satz 1 - und beides laesst sich mit Anweisungen an dieses
        # Modell offenbar nicht loesen. Der Weg, der bei "Wer bist du?"
        # funktioniert hat, war ein anderer: dort kam das Material aus ICH.md,
        # also aus einer Selbstauskunft, nicht aus einer Werkzeugliste. Wer
        # hier weiterkommen will, sollte dort ansetzen und nicht am Wortlaut
        # der Anweisung.
        #
        # Behoben ist die ANZAHL: "es gibt insgesamt 27 Faehigkeiten" kam in
        # 0 von 5 Laeufen zurueck. Das war mein eigener Fehler - die fruehere
        # Anweisung hatte sie ausdruecklich verlangt.
        anweisung = (
            f"GRUPPE A - die allgemeine Frage, was du kannst. Unten stehen "
            f"{len(nenne)} Sachen, die du BENUTZT hast. Sie sind der STOFF, "
            f"aus dem du deine Antwort ABLEITEST - nicht die Antwort selbst. "
            f"Antworte in ZWEI ODER DREI Saetzen, nicht mehr. Es wird "
            f"vorgelesen.\n"
            f"  Satz 1: Was du im KERN tust, in deinen Worten, beginnend mit "
            f"\"Ich\". Dieser Satz leitet aus den Sachen unten ab, was sie "
            f"ZUSAMMEN sind. Bleib konkret: \"Ich verarbeite Texte\" oder "
            f"\"Ich fuehre Aufgaben aus\" ist FALSCH - das gilt fuer jedes "
            f"Programm und sagt nichts ueber dich.\n"
            f"  Satz 2: ZWEI der Sachen unten konkret, im selben Satz, damit "
            f"Satz 1 belegt ist. Genau zwei - nicht null und nicht fuenf. "
            f"Nimm sie WOERTLICH von unten, erfinde keine dazu.\n"
            f"  WICHTIG: ZWEI ANDERE als die, die in Satz 1 schon vorkommen. "
            f"Am 12.09. stand der Bildschirm zweimal in derselben Antwort - "
            f"\"Ich beobachte den Bildschirm\" und zwei Saetze spaeter \"Ich "
            f"sehe den Bildschirm an\".\n"
            f"  Satz 3: dass {NAME} nachfragen kann, wenn er mehr wissen "
            f"will.\n"
            f"  NENNE KEINE ANZAHL. Nicht \"es gibt insgesamt "
            f"{a['wie_viele']}\", nicht \"{a['wie_viele']} Faehigkeiten\", "
            f"keine Zahl. Eine Zahl ist keine Auskunft - niemand fragt \"wie "
            f"viele\", sondern \"was\". Am 12.09. kam zweimal genau das "
            f"zurueck: \"Ich kann 27 Dinge.\"\n"
            f"  KEIN Katalog, keine Aufzaehlung der uebrigen. Wer mehr will, "
            f"fragt nach - eine vorgelesene Liste merkt sich niemand.")
    zeilen = [
        "[Was ich kann]",
        anweisung,
        "Der Name in Klammern ist die Bezeichnung, nicht Teil des Satzes - "
        "du musst ihn nicht nennen.",
        "Was hinter \"zuletzt\" steht, ist eine ALTE Messung als Beleg, dass "
        "es lief. Es ist NICHT der heutige Stand - gib es nie als aktuelle "
        "Beobachtung aus.",
    ]
    # Ohne den Werkzeugnamen. Mit ihm kam am 12.09. um 13:10 heraus: "Ich netz
    # sag, wer im Heimnetz ist" und "Ich ansprechen entscheide, ob er jetzt
    # sprechen darf" - er setzte den Namen hinter das "Ich" und der Satz war
    # kaputt. Die Anweisung "fang nicht mit dem Namen an" hat er befolgt und
    # ihn an die zweitbeste Stelle gesetzt.
    #
    # Der Name ist hier auch nicht noetig: Gegen erfundene Faehigkeiten
    # schuetzt die Reserve weiter unten, in der jeder Name steht. Hier geht
    # es darum, was die Sache TUT.
    for e in nenne:
        beleg = f"  [zuletzt: {e['beleg']}]" if e.get("beleg") else ""
        zeilen.append(f"  - {e['zweck']} ({e['name']}){beleg}")

    if a["noch_nie_benutzt"]:
        nie = a["noch_nie_benutzt"][:NIE_BENUTZT_HOECHSTENS]
        uebrig = len(a["noch_nie_benutzt"]) - len(nie)
        # UNVERAENDERT gegenueber der Fassung, die funktioniert hat, und das
        # ist Absicht. Ich hatte hier zweimal nachgeschaerft, und beides war
        # schlechter:
        #
        #   "in EINEM Halbsatz ... zaehle sie nicht auf"
        #     -> "Ich kann die Sprechfunktion noch nie benutzen."
        #   "nenne die Sache mit ihrem vollen Namen, in einem ganzen Satz"
        #     -> "Ich kann Sprechen Calvin von mir aus an, wenn etwas es wert
        #         ist, noch nie benutzt."
        #
        # Beides kaputtes Deutsch. Die schlichte Fassung lieferte "Ich habe
        # die Sprechen-Funktion noch nie benutzt. Ich kann den Dienst neu
        # starten, habe ihn noch nie benutzt." - richtig und verstaendlich.
        # Der Mac hatte an GRUPPE B nie etwas beanstandet; die Enge war meine
        # Zutat, und sie hat nur Schaden gemacht.
        zeilen.append(
            f"GRUPPE B - {len(a['noch_nie_benutzt'])} Sachen, die du hast, "
            f"aber noch NIE gebraucht hast. Sag das dazu, es ist eine "
            f"ehrliche Auskunft. NUR diese - haeng den Zusatz \"noch nie\" "
            f"an keine aus Gruppe A:")
        for e in nie:
            zeilen.append(f"  - {e['zweck']} (noch nie benutzt, "
                          f"warum nicht: {e['warum_nicht']})")
        if uebrig:
            zeilen.append(f"  [... {uebrig} weitere ungenutzte, nicht "
                          f"aufgefuehrt ...]")

    genannt = {e["name"] for e in nenne}
    rest = [e for e in a["geprueft"] if e["name"] not in genannt]
    if rest:
        zeilen.append(
            f"Die uebrigen {len(rest)} stehen NUR hier, damit du keinen Namen "
            f"erfindest und auf eine Nachfrage antworten kannst. Zaehle sie "
            f"NICHT auf und nenne ihre Zahl nicht als Antwort:")
        zeilen.append("  " + "; ".join(f"{e['name']}: {e['zweck']}"
                                       for e in rest))
    return "\n".join(zeilen)


# Fragen nach dem, was er kann oder wie etwas bei ihm funktioniert. Bewusst
# weit: Ein zu enger Ausdruck laesst genau die Frage durch, um die es geht.
# Der Preis ist ein laengerer Prompt bei einem Fehltreffer, nicht eine
# erfundene Antwort.
FAEHIGKEITSFRAGE = re.compile(
    r"(was\s+(kannst|könntest|kann)\s+du|was\s+(alles\s+)?kannst|"
    # "Erzaehl mir, was du so draufhast" wurde nicht erkannt, und ohne Liste
    # antwortete er mit der blossen Zahl. Umgangssprache gehoert dazu - die
    # Frage kommt aus der Spracherkennung, nicht aus einem Formular.
    r"drauf\s?hast|was\s+du\s+so\s+(kannst|machst)|"
    # Eng gefasst: Die erste Fassung war r"(erzähl|sag)\w* mir,? was du" und
    # zog damit "Erzaehl mir, was du heute getan hast" mit herein - eine
    # Chronikfrage, der dann die Faehigkeitsliste beilag. Es muss wirklich
    # nach dem KOENNEN gefragt sein.
    r"(erzähl|erzaehl|sag)\w*\s+mir[,\s]+was\s+du\s+(alles\s+)?"
    r"(kannst|beherrschst|drauf)|"
    r"deine\s+(fähigkeiten|faehigkeiten|werkzeuge|funktionen)|"
    r"welche\s+(fähigkeiten|faehigkeiten|werkzeuge|funktionen)|"
    r"wie\s+(funktioniert|machst\s+du|verarbeitest|arbeitest|"
    r"erkennst|liest|hörst|siehst|misst)|"
    r"womit\s+(machst|arbeitest)|"
    r"kannst\s+du\s+(das|wirklich|überhaupt|eigentlich)|"
    r"wozu\s+(dient|ist)|was\s+ist\s+\w+\s+für\s+ein\s+werkzeug|"
    r"hast\s+du\s+(das|es)\s+(schon\s+mal|jemals|je)\s+"
    r"(benutzt|gebraucht|gemacht)|"
    # "Gibt es etwas, das du kannst, aber noch nie gebraucht hast?" - diese
    # Frage beantwortete er am 12.09. schon aus "kann_kurz" richtig, weil
    # "noch_nie_benutzt" dort mit drinsteht. Mit der vollen Auskunft bekommt
    # er zusaetzlich den Grund, warum es noch nie gebraucht wurde.
    r"(noch\s+)?nie\s+(benutzt|gebraucht|gemacht|getan|gelaufen)|"
    r"ungenutzt|nie\s+im\s+einsatz|"
    r"woher\s+wei(ß|ss)t\s+du|wie\s+kommst\s+du\s+(darauf|dazu))",
    re.IGNORECASE)


def ist_faehigkeitsfrage(frage: str) -> bool:
    return bool(FAEHIGKEITSFRAGE.search(str(frage or "")))


def main() -> int:
    """python kann.py - was wuerde er auf eine Faehigkeitsfrage sehen?"""
    k = kurz()
    print(f"{k['wie_viele']} Eintraege, {len(k['noch_nie_benutzt'])} davon "
          f"noch nie benutzt\n")
    print("kurz (geht in jede Antwort):")
    print(" ", json.dumps(k, ensure_ascii=False)[:600])
    print(f"  -> {len(json.dumps(k, ensure_ascii=False))} Zeichen\n")
    import sys
    frage = " ".join(a for a in sys.argv[1:] if not a.startswith("-"))
    a = auskunft(frage=frage)
    print(f"auskunft zur Frage {frage!r}"
          if frage else "auskunft (ohne Frage - allgemein):")
    for e in a["geprueft"]:
        print(f"  ✓ {e['name']}: {e['zweck']}")
        if e.get("beleg"):
            print(f"      Beleg: {e['beleg']}")
    for e in a["noch_nie_benutzt"]:
        print(f"  – {e['name']}: {e['zweck']}")
        print(f"      noch nie benutzt: {e['warum_nicht']}")
    print(f"\n  -> {len(json.dumps(a, ensure_ascii=False))} Zeichen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
