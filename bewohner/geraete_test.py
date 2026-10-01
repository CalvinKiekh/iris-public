"""Probe fuer lage.unterschiede() - kommt und geht ein Geraet wirklich an?

Der Anlass: Calvin nennt "ein Geraet im Netz, das vorher nicht da war" als
Redeanlass. In 1603 Journalzeilen stand nie eines. Der Grund war nicht die
Wahrnehmung, sondern eine Bedingung, die nicht wahr werden konnte:

    mac not in alte and gesehen >= DA_BIS_NEU and war_weg

Wer gerade auftaucht, hat gesehen == 1; beim zweiten Mal steht er in alte.
Und war_weg war immer False, weil geraete() einen Eintrag wegwirft, sobald
fehlt >= FEHLT_BIS_WEG - gespeicherte Eintraege erreichen den Wert nie.

Geprueft wird hier die Logik, nicht die ARP-Tabelle: unterschiede() bekommt
zwei Lagebilder und sagt, was dazwischen passiert ist.
"""
import lage


def lagebild(geraete, uhrzeit="11:30"):
    """Ein Lagebild in der Form, die lage.bauen() WIRKLICH schreibt.

    Hier stand "geraete", und damit hat diese Probe am 12.09. einen echten
    Fehler verdeckt: unterschiede() las ebenfalls "geraete", bauen() schreibt
    aber "netz". Beide Seiten waren sich einig - nur nicht mit dem Betrieb.
    Im Betrieb sah unterschiede() also immer zwei leere Listen und hat weder
    Ankunft noch Abschied gemeldet.

    Eine Probe, die ihre Eingabe selbst baut, muss sie so bauen wie die
    Quelle. Sonst prueft sie die Logik und nie den Weg - genau der Fehler,
    den kann_test.py monatelang gemacht hat.
    """
    return {"uhrzeit": uhrzeit, "netz": geraete}


def lagebild_alt(geraete, uhrzeit="11:30"):
    """Die alte Form, mit "geraete" - fuer den Rueckfall."""
    return {"uhrzeit": uhrzeit, "geraete": geraete}


def g(mac, name="", gesehen=5, fehlt=0):
    return {"mac": mac, "ip": "192.168.0.19", "name": name,
            "hostname": "", "gesehen": gesehen, "fehlt": fehlt,
            "seit": 1789200000.0}


def main():
    gesamt = fehler = 0

    def pruefe(bedingung, was):
        nonlocal gesamt, fehler
        gesamt += 1
        print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
        if not bedingung:
            fehler += 1

    print("Probe Geraete-Ereignisse")

    fritz = g("aa-aa-aa-aa-aa-aa", "fritz")
    mac = g("bb-bb-bb-bb-bb-bb", "Mac", gesehen=1)

    # Der Fall, der es nie ins Journal geschafft hat.
    raus = lage.unterschiede(lagebild([fritz]), lagebild([fritz, mac]))
    pruefe(len(raus) == 1 and "Mac" in raus[0] and "aufgetaucht" in raus[0],
           "ein neues Geraet wird gemeldet: %s" % (raus or "NICHTS"))

    # Beim zweiten Blick ist es bekannt und darf nicht noch einmal kommen.
    mac_bekannt = g("bb-bb-bb-bb-bb-bb", "Mac", gesehen=2)
    raus = lage.unterschiede(lagebild([fritz, mac]),
                             lagebild([fritz, mac_bekannt]))
    pruefe(raus == [], "und beim naechsten Blick nicht noch einmal")

    # Der erste Blick ueberhaupt: kein Vorher, also keine Ankunft.
    raus = lage.unterschiede({}, lagebild([fritz, mac]))
    pruefe(raus == [],
           "beim allerersten Lagebild ist nichts neu (sonst meldet er beim "
           "Start das ganze Haus): %s" % (raus or "nichts"))
    raus = lage.unterschiede(lagebild([]), lagebild([fritz, mac]))
    pruefe(raus == [], "auch bei leerer Geraeteliste vorher")

    # Ein einzelnes Aussetzen der ARP-Tabelle ist kein Ereignis. geraete()
    # laesst ein Geraet mit fehlt < FEHLT_BIS_WEG in der Liste, es bleibt in
    # beiden Bildern - unterschiede() sieht es gar nicht erst.
    mac_blinzelt = g("bb-bb-bb-bb-bb-bb", "Mac", gesehen=0, fehlt=1)
    raus = lage.unterschiede(lagebild([fritz, mac_bekannt]),
                             lagebild([fritz, mac_blinzelt]))
    pruefe(raus == [], "ein einzelnes Aussetzen ist kein Ereignis")

    # Weg ist weg - erst wenn es wirklich aus der Liste faellt.
    weg = g("bb-bb-bb-bb-bb-bb", "Mac", gesehen=0, fehlt=lage.FEHLT_BIS_WEG)
    raus = lage.unterschiede(lagebild([fritz, weg]), lagebild([fritz]))
    pruefe(len(raus) == 1 and "nicht mehr da" in raus[0],
           "ein Geraet, das lange fehlt, wird gemeldet: %s" % (raus or "NICHTS"))

    raus = lage.unterschiede(lagebild([fritz, mac_blinzelt]),
                             lagebild([fritz]))
    pruefe(raus == [], "eines, das erst einmal fehlte, noch nicht")

    # Ohne Namen nennt er die Adresse, nicht nichts.
    namenlos = g("cc-cc-cc-cc-cc-cc")
    raus = lage.unterschiede(lagebild([fritz]), lagebild([fritz, namenlos]))
    pruefe(len(raus) == 1 and raus[0].strip(),
           "auch ein namenloses Geraet ergibt einen Satz: %s" % (raus or "-"))

    # Der Weg, den der Betrieb geht: lage.bauen() schreibt "netz". Ohne diese
    # Pruefung war der Fehler vom 12.09. nicht zu sehen.
    echt_neu = {"uhrzeit": "11:30", "netz": [fritz, mac]}
    echt_alt = {"uhrzeit": "11:30", "netz": [fritz]}
    raus = lage.unterschiede(echt_alt, echt_neu)
    pruefe(len(raus) == 1 and "Mac" in raus[0],
           "mit dem Feldnamen aus bauen() - \"netz\": %s" % (raus or "NICHTS"))

    # Und der Rueckfall auf die alte Form, damit ein gespeichertes Lagebild
    # von vor der Umbenennung noch gelesen wird.
    raus = lage.unterschiede(lagebild_alt([fritz]), lagebild_alt([fritz, mac]))
    pruefe(len(raus) == 1 and "Mac" in raus[0],
           "und die alte Form \"geraete\" geht weiterhin: %s"
           % (raus or "NICHTS"))

    # Gemischt: gespeichert alt, frisch gemessen neu.
    raus = lage.unterschiede(lagebild_alt([fritz]), echt_neu)
    pruefe(len(raus) == 1 and "Mac" in raus[0],
           "auch gemischt, alt gespeichert gegen neu gemessen: %s"
           % (raus or "NICHTS"))

    # Tagesphase bleibt, wie sie war.
    raus = lage.unterschiede({"tagesphase": "Morgen", "netz": [fritz]},
                             {"tagesphase": "Vormittag", "netz": [fritz],
                              "uhrzeit": "10:00"})
    pruefe(any("begann der Vormittag" in z for z in raus),
           "die Tagesphase meldet er weiterhin")

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


if __name__ == "__main__":
    raise SystemExit(main())
