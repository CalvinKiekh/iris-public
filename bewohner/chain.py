"""
Kette: lokales Modell (gpt-oss) beauftragt Claude Code ueber die iris-Bruecke.

    Du  ->  gpt-oss:20b  ->  iris-Bruecke  ->  eigene Claude-Code-Sitzung
                                                (dauerhaft, mit Kontext)

Gegenueber einem 'claude -p' pro Auftrag bringt der Weg ueber die Bruecke:
  - einen durchgehenden Prozess, der den Gespraechsverlauf behaelt
  - Wiederaufnahme nach Neustart ueber resume
  - Freigaben landen auf dem iPhone statt blind akzeptiert zu werden

gpt-oss selbst hat keinen Dateizugriff. Sein einziges Werkzeug ist der
Auftrag an die Sitzung.

Beenden mit  exit  oder  Strg+C.
"""

import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

# ---------------------------------------------------------------- Einstellungen

OLLAMA_URL = "http://localhost:11434/api/chat"
MODELL = "gpt-oss:20b"

BRUECKE = "http://127.0.0.1:8780"
IRIS_CONFIG = Path.home() / ".config" / "iris" / "config.json"

# Ordner, in dem die Claude-Code-Sitzung arbeitet.
WERKSTATT = Path(__file__).parent / "werkstatt"

# Merkt sich die Sitzung ueber Neustarts hinweg.
ZUSTAND = Path(__file__).parent / "chain-state.json"

MAX_AUFTRAEGE = 3          # Auftraege pro Frage
WARTE_MAX = 900            # Sekunden, die ein Auftrag dauern darf
WARTE_TAKT = 2.0           # Abfrageintervall

SYSTEM_PROMPT = f"""Du bist ein Assistent ohne eigenen Dateizugriff.
Fuer alles, was Dateien, Code oder Texte betrifft, benutzt du das Werkzeug 'claude_code'.

Wichtig:
- Die Sitzung dahinter ist dauerhaft und erinnert sich an frueheren Auftraege.
  Du darfst dich also auf Vorheriges beziehen.
- Sie arbeitet im Ordner {WERKSTATT}.
- Hoechstens {MAX_AUFTRAEGE} Auftraege pro Frage.
- Berichte danach kurz auf Deutsch, was erledigt wurde.
"""

WERKZEUGE = [
    {
        "type": "function",
        "function": {
            "name": "claude_code",
            "description": (
                "Schickt einen Auftrag an eine laufende Claude-Code-Sitzung, die "
                "Dateien lesen und schreiben kann. Die Sitzung kennt ihre eigenen "
                "frueheren Auftraege, aber nicht dein Gespraech mit dem Nutzer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "auftrag": {
                        "type": "string",
                        "description": "Der Auftrag, klar und vollstaendig formuliert.",
                    }
                },
                "required": ["auftrag"],
            },
        },
    }
]


# ---------------------------------------------------------------- Bruecke


class Bruecke:
    def __init__(self) -> None:
        if not IRIS_CONFIG.exists():
            sys.exit(f"iris-Konfiguration nicht gefunden: {IRIS_CONFIG}")
        # Der Schluessel wird zur Laufzeit gelesen, nie im Skript gespeichert.
        self.token = json.loads(IRIS_CONFIG.read_text(encoding="utf-8")).get("token", "")
        if not self.token:
            sys.exit("Kein Token in der iris-Konfiguration.")
        self.http = httpx.Client(timeout=60.0)
        self.key: str | None = None

    # -- kleine Helfer ------------------------------------------------------

    def _ohne_token(self, text: str) -> str:
        """httpx haengt die volle URL in die Fehlermeldung - samt ?token=...
        Die landet sonst im Journal, in der App und im Vorgelesenen."""
        return text.replace(self.token, "***") if self.token else text

    def _get(self, pfad: str, **params):
        params["token"] = self.token
        r = self.http.get(f"{BRUECKE}{pfad}", params=params)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as fehler:
            raise httpx.HTTPStatusError(
                self._ohne_token(str(fehler)),
                request=fehler.request, response=fehler.response) from None
        return r.json()

    def _post(self, pfad: str, daten: dict):
        r = self.http.post(f"{BRUECKE}{pfad}", params={"token": self.token}, json=daten)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
        return r.json()

    # -- Anhaenge -----------------------------------------------------------

    # Groesse und Arten, die eine Datei haben darf, bevor sie mitgeht. Die
    # Bruecke hat ihre eigene Grenze; diese hier ist die des Bewohners, und sie
    # ist enger: Er soll nicht aus Versehen ein Gigabyte hochschieben, weil
    # eine Messung entgleist ist.
    ANHANG_MAX = 5 * 1024 * 1024
    ANHANG_ARTEN = {".txt", ".md", ".json", ".jsonl", ".log", ".csv", ".py",
                    ".png", ".jpg", ".jpeg", ".webp", ".pdf"}

    def hochladen(self, pfad) -> str:
        """Eine Datei AUS DER WERKSTATT an die Sitzung haengen.

        NUR AUS DER WERKSTATT, und das ist keine Formsache. Der Bewohner
        entscheidet selbst, was er mitschickt; ohne diese Grenze koennte aus
        "schick die Datei mit" ein beliebiger Pfad auf Calvins Platte werden -
        seine Steuererklaerung, ein Schluesselbund. Was er nicht sehen darf,
        darf er auch nicht weitergeben.

        Gibt den Verweis zurueck, den `beauftrage` als `attachments` mitgibt.
        """
        from pathlib import Path as _P
        datei = _P(pfad).expanduser().resolve()
        werkstatt = (_P(__file__).parent / "werkstatt").resolve()
        if werkstatt not in datei.parents:
            raise ValueError(f"nur aus der Werkstatt, nicht {datei}")
        if not datei.is_file():
            raise ValueError(f"gibt es nicht: {datei}")
        if datei.suffix.lower() not in self.ANHANG_ARTEN:
            raise ValueError(f"diese Art haenge ich nicht an: {datei.suffix}")
        groesse = datei.stat().st_size
        if groesse > self.ANHANG_MAX:
            raise ValueError(f"zu gross: {groesse // 1024} KB")

        key = self.key or self.sitzung_sichern()
        r = self.http.post(
            f"{BRUECKE}/api/sessions/{key}/upload",
            params={"token": self.token},
            content=datei.read_bytes(),
            headers={"X-Filename": quote(datei.name),
                     "Content-Type": "application/octet-stream"})
        if r.status_code >= 400:
            raise RuntimeError(self._ohne_token(f"{r.status_code}: {r.text[:200]}"))
        antwort = r.json()
        if antwort.get("error"):
            raise RuntimeError(str(antwort["error"]))
        return antwort["path"]

    # -- Sitzung ------------------------------------------------------------

    def _gemerkt(self) -> dict:
        if ZUSTAND.exists():
            try:
                return json.loads(ZUSTAND.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {}

    def _merken(self, key: str, claude_id: str | None) -> None:
        ZUSTAND.write_text(
            json.dumps({"key": key, "claude_session_id": claude_id}, indent=2),
            encoding="utf-8",
        )

    def sitzung_sichern(self) -> str:
        """Vorhandene Sitzung weiterbenutzen, sonst eine neue erzeugen."""
        alt = self._gemerkt()
        key = alt.get("key")

        if key:
            try:
                info = self._get(f"/api/sessions/{key}")["session"]
                # Sicherung: niemals eine Terminal-Sitzung bespielen. Das waere
                # womoeglich die Sitzung, die dieses Skript gerade steuert.
                if info.get("terminal"):
                    raise RuntimeError("gemerkte Sitzung ist eine Terminal-Sitzung")
                if not info.get("exited"):
                    self.key = key
                    print(f"Sitzung fortgesetzt: {key}")
                    return key
            except (httpx.HTTPStatusError, RuntimeError, KeyError):
                pass

        WERKSTATT.mkdir(parents=True, exist_ok=True)
        daten = {"cwd": str(WERKSTATT)}
        # Nach einem Neustart am selben Verlauf weitermachen.
        if alt.get("claude_session_id"):
            daten["resume"] = alt["claude_session_id"]

        try:
            neu = self._post("/api/sessions", daten)["session"]
        except RuntimeError as fehler:
            if "resume" in daten:
                print(f"Wiederaufnahme fehlgeschlagen ({fehler}), starte frisch.")
                daten.pop("resume")
                neu = self._post("/api/sessions", daten)["session"]
            else:
                raise

        self.key = neu["key"]
        # Beim Anlegen kennt die Bruecke die claude_session_id noch nicht - die
        # entsteht erst, wenn Claude Code hochgefahren ist. Ohne sie schlaegt
        # spaeter jedes resume fehl, also kurz nachfassen.
        claude_id = neu.get("claude_session_id")
        if not claude_id:
            for _ in range(10):
                time.sleep(1.0)
                try:
                    info = self._get(f"/api/sessions/{self.key}")["session"]
                except (httpx.HTTPError, KeyError):
                    continue
                if info.get("claude_session_id"):
                    claude_id = info["claude_session_id"]
                    break
        self._merken(self.key, claude_id)
        print(f"Neue Sitzung: {self.key}   ({neu.get('permission_label', '?')})"
              + (f"   claude={claude_id[:8]}…" if claude_id else "   (ohne claude-ID)"))
        return self.key

    # -- Auftrag ------------------------------------------------------------

    def beauftrage(self, auftrag: str, dateien=None) -> str:
        """Auftrag abschicken und den Ereignisstrom bis 'done' mitlesen.

        Die Karten der Bruecke:
          sent  - die Nachricht ist angekommen
          ready - die Sitzung nimmt den Zug auf
          say   - Text von Claude Code    <- das wollen wir
          done  - Zug beendet, mit Kosten und Dauer
        """
        key = self.key or self.sitzung_sichern()
        # Startet die Bruecke neu, ist der gemerkte Schluessel tot - self.key
        # zeigt aber weiter darauf, und jeder Auftrag scheiterte mit 404, bis
        # der Bewohner selbst neu startete. Einmal neu sichern und weiter.
        try:
            vorher = int(self._get(f"/api/sessions/{key}")["session"].get("seq", 0))
        except (httpx.HTTPStatusError, KeyError):
            print(f"Sitzung {key} gibt es nicht mehr - neue wird gesichert.")
            self.key = None
            key = self.sitzung_sichern()
            vorher = int(self._get(f"/api/sessions/{key}")["session"].get("seq", 0))

        # Die Anhaenge zuerst - ein Auftrag ohne die Datei, von der er
        # handelt, ist eine Frage ins Leere. Scheitert einer, geht der Auftrag
        # trotzdem raus, aber MIT dem Hinweis: Eine Antwort auf eine Datei,
        # die nie ankam, ist schlimmer als keine.
        anhaenge, misslungen = [], []
        for d in (dateien or []):
            try:
                anhaenge.append(self.hochladen(d))
            except Exception as f:
                misslungen.append(f"{d}: {f}")
        if misslungen:
            auftrag += ("\n\n[Diese Dateien konnte ich NICHT mitschicken: "
                        + "; ".join(misslungen) + ". Antworte nicht so, als "
                        + "haettest du sie gesehen.]")
        nachricht = {"text": auftrag}
        if anhaenge:
            nachricht["attachments"] = anhaenge
        self._post(f"/api/sessions/{key}/message", nachricht)

        texte: list[str] = []
        frist = time.time() + WARTE_MAX
        gemeldet = False

        try:
            with self.http.stream(
                "GET",
                f"{BRUECKE}/api/sessions/{key}/events",
                params={"token": self.token, "since": vorher, "detail": "card"},
                # Keepalives kommen alle 20s; 45s Lesefrist ist reichlich.
                timeout=httpx.Timeout(15.0, read=45.0),
            ) as strom:
                for zeile in strom.iter_lines():
                    if time.time() > frist:
                        texte.append(f"(Zeitlimit von {WARTE_MAX}s erreicht)")
                        break
                    if not zeile.startswith("data: "):
                        continue
                    try:
                        karte = json.loads(zeile[6:])
                    except json.JSONDecodeError:
                        continue

                    art = karte.get("kind")
                    if art == "say":
                        texte.append(str(karte.get("text", "")))
                    elif art in ("ask", "permission", "approval") and not gemeldet:
                        print("  [wartet auf Freigabe -- schau aufs iPhone]")
                        gemeldet = True
                    elif art == "done":
                        dauer = float(karte.get("duration_ms") or 0) / 1000
                        kosten = karte.get("cost_usd")
                        hinweis = f"  [claude] {dauer:.1f}s"
                        if kosten:
                            hinweis += f", {float(kosten):.3f} USD"
                        if str(karte.get("is_error")) == "True":
                            hinweis += "  (Fehler)"
                        print(hinweis)
                        break
                    elif art in ("exit", "closed"):
                        texte.append("Die Sitzung wurde beendet.")
                        break
        except httpx.ReadTimeout:
            texte.append("(keine weiteren Ereignisse)")
        except httpx.HTTPError as fehler:
            return f"Verbindungsfehler zur Bruecke: {self._ohne_token(str(fehler))}"

        # Die claude_session_id entsteht erst, wenn die Sitzung wirklich einen
        # Zug gelaufen ist - beim Anlegen ist sie noch None. sitzung_sichern()
        # hat nur dort nachgefasst und dann null gespeichert; nach einem
        # Brueckenneustart gab es deshalb nie etwas zum Wiederaufnehmen.
        # Also nach jedem Auftrag nachtragen.
        try:
            claude_id = self._get(f"/api/sessions/{key}")["session"].get(
                "claude_session_id")
            if claude_id and self._gemerkt().get("claude_session_id") != claude_id:
                self._merken(key, claude_id)
                print(f"  [claude-ID nachgetragen: {claude_id[:8]}…]")
        except (httpx.HTTPError, KeyError):
            pass

        antwort = "\n".join(t for t in texte if t).strip()
        return antwort[:4000] if antwort else "(keine Textantwort erhalten)"

    def aufraeumen(self) -> None:
        self.http.close()


# ---------------------------------------------------------------- Ollama


def frage_ollama(client: httpx.Client, nachrichten: list) -> dict:
    r = client.post(
        OLLAMA_URL,
        json={"model": MODELL, "messages": nachrichten, "tools": WERKZEUGE, "stream": False},
        timeout=600.0,
    )
    r.raise_for_status()
    return r.json()["message"]


# ---------------------------------------------------------------- Hauptschleife


def main() -> None:
    bruecke = Bruecke()
    bruecke.sitzung_sichern()

    print(f"\nDirigent   : {MODELL}  (kein Dateizugriff)")
    print(f"Handwerker : Claude Code ueber die iris-Bruecke")
    print(f"Werkstatt  : {WERKSTATT}")
    print("\nFrag etwas. Beenden mit 'exit'.\n")

    nachrichten = [{"role": "system", "content": SYSTEM_PROMPT}]

    with httpx.Client() as http:
        while True:
            try:
                eingabe = input("Du > ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not eingabe:
                continue
            if eingabe.lower() in ("exit", "quit", "ende"):
                break

            nachrichten.append({"role": "user", "content": eingabe})

            for _ in range(MAX_AUFTRAEGE):
                nachricht = frage_ollama(http, nachrichten)
                nachrichten.append(nachricht)

                aufrufe = nachricht.get("tool_calls") or []
                if not aufrufe:
                    print(f"\nKI > {nachricht.get('content', '').strip()}\n")
                    break

                for aufruf in aufrufe:
                    argumente = aufruf["function"]["arguments"]
                    if isinstance(argumente, str):
                        argumente = json.loads(argumente)
                    auftrag = argumente.get("auftrag", "")

                    print(f"\n  [Auftrag]\n  {auftrag}\n")
                    try:
                        ergebnis = bruecke.beauftrage(auftrag)
                    except Exception as fehler:
                        ergebnis = f"Fehler: {fehler}"
                    kurz = ergebnis if len(ergebnis) <= 500 else ergebnis[:500] + " ..."
                    print(f"  [Rueckmeldung]\n  {kurz}\n")

                    nachrichten.append(
                        {"role": "tool", "content": ergebnis, "tool_name": "claude_code"}
                    )
            else:
                print(f"\nKI > Abgebrochen nach {MAX_AUFTRAEGE} Auftraegen.\n")

    bruecke.aufraeumen()
    print("Beendet.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
