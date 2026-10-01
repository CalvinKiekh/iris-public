"""Canned prompts, kept on the bridge so every client shows the same list.

On a headset there is no keyboard: the wheel scrolls this list and one press
sends it. That makes these the primary input, not a convenience, so they live
in a file the user can edit rather than being baked into a client.
"""
import json
import os

from . import config

PATH = os.path.join(config.CONFIG_DIR, "shortcuts.json")

DEFAULTS = [
    {"label": "Weiter",          "text": "Mach weiter."},
    {"label": "Stand?",          "text": "Was ist der aktuelle Stand? Kurz, in drei Sätzen."},
    {"label": "Was zuletzt?",    "text": "Was hast du zuletzt gemacht und warum?"},
    {"label": "Tests",           "text": "Führe die Tests aus und berichte nur das Ergebnis."},
    {"label": "Build",           "text": "Baue das Projekt und berichte nur Fehler."},
    {"label": "Status",          "text": "Zeig mir git status und die geänderten Dateien."},
    {"label": "Diff",            "text": "Fasse die aktuellen Änderungen zusammen."},
    {"label": "Commit",          "text": "Committe die Änderungen mit einer passenden Nachricht."},
    {"label": "Erklär das",      "text": "Erklär mir kurz, was du da gerade gebaut hast."},
    {"label": "Aufräumen",       "text": "Räum auf, was du angelegt hast, und fasse zusammen."},
    {"label": "Abbrechen",       "text": "Stopp. Lass den aktuellen Ansatz und warte auf Anweisung."},
]


def load():
    if not os.path.exists(PATH):
        save(DEFAULTS)
        return list(DEFAULTS)
    try:
        data = config.read_json(PATH)
        rows = [r for r in data if isinstance(r, dict) and r.get("text")]
        return rows or list(DEFAULTS)
    except (OSError, json.JSONDecodeError):
        return list(DEFAULTS)


def save(rows):
    os.makedirs(config.CONFIG_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, PATH)
