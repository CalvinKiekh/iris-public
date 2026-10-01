"""Wie ausführlich Claude antwortet, hängt vom Gerät ab.

Auf einer Brille sind 44 Zeichen mal elf Zeilen alles, was es gibt - eine
Antwort in voller Länge ist dort nicht knapp, sondern unlesbar. Am Mac ist
das Gegenteil richtig. Die Sitzung ist aber dieselbe, also wird nicht die
Darstellung gekürzt, sondern die Antwort von vornherein passend erzeugt.

Möglich, weil `set_model` den System-Prompt zur Laufzeit ersetzt (Feld
`system_prompt`, snake_case - siehe docs/BEFUNDE.md). Wirkt ab dem
nächsten Zug.
"""

# Der Grundton gilt immer; das Gerät hängt nur seinen Absatz an. Es gibt
# keinen Weg zurück zum eingebauten Prompt, deshalb muss die Basis bei
# jedem Wechsel mitgeschickt werden.
BASE = (
    "Du arbeitest in einer Sitzung, die der Nutzer von wechselnden Geräten "
    "aus führt. Antworte auf Deutsch."
)

PROFILES = {
    "desktop": {
        "label": "Mac",
        "prompt": "",           # voller Umfang: nichts einschränken
    },
    "phone": {
        "label": "Handy",
        "prompt": (
            "Der Nutzer liest auf einem Telefon. Fasse dich: höchstens fünf "
            "Sätze, keine Tabellen, keine langen Aufzählungen. Nenne das "
            "Ergebnis zuerst, Einzelheiten nur auf Nachfrage."
        ),
    },
    "watch": {
        "label": "Uhr",
        "prompt": (
            "Der Nutzer liest auf einer Armbanduhr. Antworte in höchstens "
            "zwei kurzen Sätzen, zusammen unter 140 Zeichen. Keine "
            "Aufzählungen, kein Code, keine Pfade außer dem nötigsten. "
            "Nur das Ergebnis und, falls nötig, eine Frage."
        ),
    },
    "glasses": {
        "label": "Brille",
        "prompt": (
            "Der Nutzer liest auf einer Datenbrille: rund 44 Zeichen je "
            "Zeile, elf Zeilen, einfarbig. Antworte in höchstens drei kurzen "
            "Sätzen. Keine Aufzählungen, keine Tabellen, kein Markdown, "
            "keine langen Pfade - nur der Dateiname. Sag das Wichtigste "
            "zuerst; wenn etwas zu entscheiden ist, sag es in einem Satz."
        ),
    },
}

DEFAULT = "desktop"


def prompt_for(profile, grundlage=""):
    """Vollständiger System-Prompt für ein Gerät.

    `grundlage` ist, was die Sitzung selbst mitbringt und was jeder
    Gerätewechsel behalten muss - der Charakter eines Vorarbeiters zum
    Beispiel. Ohne diesen Weg wäre er nach dem ersten Blick von der Uhr aus
    weg: hier wird der ganze System-Prompt ersetzt, und einen Weg zurück zum
    eingebauten gibt es nicht. Deshalb trägt ihn die Sitzung und nicht dieses
    Modul.
    """
    p = PROFILES.get(profile or DEFAULT) or PROFILES[DEFAULT]
    teile = [BASE, (grundlage or "").strip(), p["prompt"]]
    return "\n\n".join(t for t in teile if t).strip()


def known():
    return [{"id": k, "label": v["label"]} for k, v in PROFILES.items()]
