"""Wo Tests, die einen echten zweiten Rechner brauchen, ihn finden.

Aus rechner.env in der Wurzel, wie die Skripte in tools/ - mit demselben
Vorrang: eine gesetzte Umgebungsvariable gewinnt. Ohne Eintrag bricht ein
solcher Test mit einem Satz ab, statt still einen fremden Rechner zu raten.
"""
import os
import shlex

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def werte():
    """rechner.env als dict, Umgebungsvariablen obenauf."""
    w = {}
    try:
        with open(os.path.join(WURZEL, "rechner.env"), encoding="utf-8") as fh:
            for zeile in fh:
                zeile = zeile.strip()
                if not zeile or zeile.startswith("#") or "=" not in zeile:
                    continue
                k, _, v = zeile.partition("=")
                w[k.strip()] = " ".join(shlex.split(v)) if v.strip() else ""
    except OSError:
        pass
    w.update({k: v for k, v in os.environ.items() if k.startswith("IRIS_")})
    return w


def brauche(name, was):
    wert = werte().get(name, "")
    if not wert:
        raise SystemExit(f"{name} fehlt. In rechner.env eintragen "
                         f"(Vorlage: rechner.env.beispiel) - {was}")
    return wert
