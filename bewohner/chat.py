"""
Kleiner MCP-Client fuer lokale Modelle ueber Ollama.

Startet einen MCP-Server als Unterprozess, holt dessen Werkzeugliste,
uebersetzt sie in das Format von Ollama und fuehrt ein Gespraech, in dem
das Modell die Werkzeuge tatsaechlich benutzen kann.

Beenden mit  exit  oder  Strg+C.
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ---------------------------------------------------------------- Einstellungen

OLLAMA_URL = "http://localhost:11434/api/chat"
MODELL = "gpt-oss:20b"

# Ordner, auf den der Dateisystem-Server beschraenkt bleibt.
SPIELPLATZ = Path(__file__).parent / "spielplatz"

# Der MCP-Server, der gestartet werden soll.
# Zum Austauschen: einfach eine andere npx-Zeile eintragen, zum Beispiel
#   ["-y", "@modelcontextprotocol/server-sequential-thinking"]
SERVER_ARGS = ["-y", "@modelcontextprotocol/server-filesystem", str(SPIELPLATZ)]

# Wie oft das Modell hintereinander Werkzeuge aufrufen darf, bevor abgebrochen
# wird. Schuetzt vor Endlosschleifen, wenn sich das Modell festfaehrt.
MAX_WERKZEUG_RUNDEN = 8

SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Assistent mit Zugriff auf Werkzeuge. "
    "Benutze die Werkzeuge, wenn du echte Daten brauchst, statt zu raten. "
    "Antworte auf Deutsch und fasse dich kurz."
)

# ---------------------------------------------------------------- Hilfsfunktionen


def finde_npx() -> str:
    """npx heisst unter Windows npx.cmd - das findet der PATH nicht immer selbst."""
    for name in ("npx.cmd", "npx"):
        pfad = shutil.which(name)
        if pfad:
            return pfad
    sys.exit("npx wurde nicht gefunden. Ist Node.js installiert?")


def nach_ollama_format(mcp_tools) -> list:
    """MCP beschreibt Werkzeuge anders als Ollama. Hier die Uebersetzung."""
    werkzeuge = []
    for t in mcp_tools:
        # MCP 1.x nannte das Feld inputSchema, ab 2.x heisst es input_schema.
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
        werkzeuge.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": schema or {"type": "object", "properties": {}},
                },
            }
        )
    return werkzeuge


def text_aus_ergebnis(ergebnis) -> str:
    """Ein MCP-Werkzeug antwortet mit Inhaltsbloecken, nicht mit einem String."""
    teile = []
    for block in ergebnis.content:
        if getattr(block, "type", None) == "text":
            teile.append(block.text)
        else:
            teile.append(f"[{getattr(block, 'type', 'unbekannt')}-Inhalt]")
    return "\n".join(teile) if teile else "(leeres Ergebnis)"


async def frage_ollama(client: httpx.AsyncClient, nachrichten: list, werkzeuge: list) -> dict:
    antwort = await client.post(
        OLLAMA_URL,
        json={
            "model": MODELL,
            "messages": nachrichten,
            "tools": werkzeuge,
            "stream": False,
        },
        timeout=600.0,
    )
    antwort.raise_for_status()
    return antwort.json()["message"]


# ---------------------------------------------------------------- Hauptschleife


async def main() -> None:
    SPIELPLATZ.mkdir(parents=True, exist_ok=True)

    server = StdioServerParameters(command=finde_npx(), args=SERVER_ARGS)

    print("Starte MCP-Server ...")
    async with stdio_client(server) as (lesen, schreiben):
        async with ClientSession(lesen, schreiben) as sitzung:
            await sitzung.initialize()

            liste = await sitzung.list_tools()
            werkzeuge = nach_ollama_format(liste.tools)

            print(f"\nModell : {MODELL}")
            print(f"Ordner : {SPIELPLATZ}")
            print(f"\n{len(werkzeuge)} Werkzeuge verfuegbar:")
            for w in werkzeuge:
                beschreibung = w["function"]["description"].split("\n")[0][:70]
                print(f"   - {w['function']['name']:<28} {beschreibung}")
            print("\nFrag etwas. Beenden mit 'exit'.\n")

            nachrichten = [{"role": "system", "content": SYSTEM_PROMPT}]

            async with httpx.AsyncClient() as http:
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

                    for runde in range(MAX_WERKZEUG_RUNDEN):
                        nachricht = await frage_ollama(http, nachrichten, werkzeuge)
                        nachrichten.append(nachricht)

                        aufrufe = nachricht.get("tool_calls") or []
                        if not aufrufe:
                            print(f"\nKI > {nachricht.get('content', '').strip()}\n")
                            break

                        for aufruf in aufrufe:
                            name = aufruf["function"]["name"]
                            argumente = aufruf["function"]["arguments"]
                            if isinstance(argumente, str):
                                argumente = json.loads(argumente)

                            print(f"  [Werkzeug] {name}({json.dumps(argumente, ensure_ascii=False)})")

                            try:
                                ergebnis = await sitzung.call_tool(name, arguments=argumente)
                                inhalt = text_aus_ergebnis(ergebnis)
                            except Exception as fehler:
                                inhalt = f"Fehler beim Aufruf: {fehler}"

                            gekuerzt = inhalt if len(inhalt) <= 200 else inhalt[:200] + " ..."
                            print(f"  [Ergebnis] {gekuerzt}")

                            nachrichten.append(
                                {"role": "tool", "content": inhalt, "tool_name": name}
                            )
                    else:
                        print(
                            f"\nKI > Abgebrochen nach {MAX_WERKZEUG_RUNDEN} Werkzeugrunden.\n"
                        )

    print("Beendet.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
