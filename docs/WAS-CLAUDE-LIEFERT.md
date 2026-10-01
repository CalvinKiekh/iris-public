# Was Claude Code hergibt

Bestandsaufnahme vom 09.09.2026, Claude Code 2.1.263. Alles hier ist
**nachgemessen**, nicht aus Dokumentation übernommen. Grundlage für die
Entscheidung, was die iris-API anbieten kann.

## 1. Der Steuerkanal (`control_request` über stdin)

Der wichtigste Fund. Im stream-json-Modus nimmt die CLI Steuerbefehle
entgegen und antwortet mit `control_response`. Alle Kandidaten wurden scharf
durchprobiert:

| Subtyp | geht | liefert |
|---|---|---|
| `initialize` | **ja** | Modelle, Slash-Befehle, Agenten, Konto, Modus, PID, Zustand |
| `get_context_usage` | **ja** | vollständige Kontextaufschlüsselung, siehe unten |
| `set_permission_mode` | **ja** | schaltet den Modus im Betrieb um |
| `set_model` | **ja** | wechselt das Modell im Betrieb |
| `interrupt` | **ja** | bricht den Zug ab, meldet was noch in der Schlange stand |
| `get_binary_version` | **ja** | Version und Bauzeit |
| `mcp_message` | **ja** | (leere Antwort, für MCP-Verkehr) |
| `status`, `compact`, `set_effort`, `get_commands`, `get_command`, `get_project`, `get_device_info`, `hook_callback` | nein | „Unsupported control request subtype" |

Ein unbekannter Subtyp wird sauber abgelehnt — so wurde diese Liste
überhaupt erst ermittelt.

### `initialize`

```
models                 5 Einträge, je value / resolvedModel / displayName / description
commands               147 Einträge, je name + description
agents                 5 Einträge (claude, Explore, general-purpose, Plan, statusline-setup)
account                email, organization, subscriptionType, apiProvider
output_style           aktuell + available_output_styles (default, Proactive, Concise, …)
current_permission_mode, session_state, pid
remote_control_available, remote_control_auto_enable
fast_mode_state, fast_mode_disabled_reason
```

### `get_context_usage`

Das, was im Terminal am undurchsichtigsten ist:

```
totalTokens / maxTokens / rawMaxTokens / percentage
autoCompactThreshold / isAutoCompactEnabled / autocompactSource
categories[]           System prompt, System tools, MCP tools (deferred),
                       Skills, Messages, Free space — je mit Tokenzahl
messageBreakdown       toolCallTokens, toolResultTokens, attachmentTokens,
                       assistantMessageTokens, userMessageTokens, …
mcpTools[]             Name, Server, Tokens, isLoaded
skills[]               Name, Quelle, Tokens je Skill
slashCommands          totalCommands, includedCommands, Tokens
memoryFiles[], agents[], model
gridRows               fertige Kachel-Darstellung, falls man sie mag
```

## 2. Der Ereignisstrom (stdout)

| Typ | Inhalt |
|---|---|
| `system/init` | session_id, cwd, model, Werkzeugliste. **Kommt erst mit der ersten Nachricht.** |
| `system/status` | permissionMode nach einem Wechsel |
| `system/thinking_tokens` | Denk-Fortschritt, laufende Schätzung |
| `assistant` | Textblöcke und `tool_use` mit **vollständigem Input** |
| `user` | `tool_result` je Aufruf, mit `is_error` |
| `rate_limit_event` | `unifiedWindows`: five_hour und seven_day mit Auslastung und Reset |
| `result` | stop_reason, Dauer, Kosten, detaillierte Token-Nutzung je Modell |
| `control_response` | Antwort auf einen Steuerbefehl |

## 3. Was auf der Platte liegt

| Ort | Inhalt |
|---|---|
| `~/.claude/projects/<dir>/<session>.jsonl` | vollständiges Transcript, inkl. `ai-title` |
| `~/.claude/file-history/<session>/<hash>@v<N>` | versionierte Dateikopien — **nur bei Terminal-Sitzungen**, siehe unten |
| `~/.claude/plans/`, `sessions/`, `session-env/`, `jobs/` | weitere Zustände, noch nicht ausgewertet |
| `/tmp/cc-socks/<pid>.sock` | je laufender Sitzung ein Socket (nur PID, keine Session-ID) |

### Einschränkung bei der Datei-Historie

`file-history` wird **nur für interaktive Sitzungen** (`entrypoint: cli`)
geschrieben. Nachgemessen: eine von iris gehostete Print-Sitzung ändert
Dateien per Edit und Write, es entsteht kein Historien-Verzeichnis. Alle
20 vorhandenen gehören zu Terminal-Sitzungen.

Folge für Diffs:

- **fortgesetzte Terminal-Unterhaltungen**: echte Diffs verfügbar, auch für
  Änderungen per Shell-Skript
- **von iris gestartete Sitzungen**: nichts vorhanden — iris müsste selbst
  sichern

**Gelöst** durch `bridge/tracking.py`: iris sichert selbst. Zwei
Haltepunkte, weil einer allein nicht reicht — der Berechtigungs-Broker (er
sieht jeden Aufruf vor der Ausführung) und der `tool_use`-Block im
Ereignisstrom (für Modi wie `acceptEdits`, die den Broker überspringen).
Beide sind gefahrlos doppelt: der erste Schnappschuss gewinnt.

Gesichert wird als `v0` der Stand *vor* der ersten Änderung, danach nach
jedem Zug eine neue Version, sofern sich etwas geändert hat. Eine Datei, die
es noch nicht gab, bekommt ein leeres `v0` — die Neuanlage erscheint dann
als vollständige Hinzufügung.

**Was auch das nicht erfasst:** Änderungen durch Shell-Befehle. Bash nennt
keinen Pfad, den man vorher sichern könnte.

## 3b. System-Prompt im laufenden Betrieb

Austauschbar — über `set_model` mit dem **aktuellen** Modell und dem Feld
`system_prompt`:

```json
{"type":"control_request","request_id":"x","request":{
  "subtype":"set_model","model":"<aktuelles Modell>",
  "system_prompt":"Du bist …"}}
```

**Falle:** Das Feld heißt `system_prompt` in snake_case. `systemPrompt` in
camelCase wird mit `success` quittiert und tut **nichts** — nachgemessen:
der Prompt blieb unverändert. Die interne Beschreibung sagt es selbst
(„Transports that do not implement it … ack success without applying it"),
also darf man der Erfolgsmeldung hier nicht trauen.

Es gibt **keinen Weg zurück** zum eingebauten Prompt; ein leerer Wert wird
von iris deshalb abgelehnt statt gesendet. Wirksam ab dem nächsten Zug.

## 3c. Konfiguration, die Claude Code mitliest

| Ebene | Datei | Inhalt |
|---|---|---|
| Benutzer | `~/.claude/settings.json` | Modell, Hooks, Plugins, Auto-Modus |
| Benutzer | `~/.claude/settings.local.json` | Berechtigungen (allow/deny) |
| Benutzer | `~/.claude/CLAUDE.md` | gilt für alle Projekte |
| Benutzer | `~/.claude.json` | globaler Zustand, groß, besser nur lesen |
| Benutzer | `~/.claude/agents/`, `commands/`, `skills/` | Subagenten, eigene Befehle, Skills |
| Projekt | `CLAUDE.md`, `.claude/settings*.json`, `.mcp.json` | projektbezogen |
| Erinnerungen | `~/.claude/projects/<dir>/memory/*.md` | Auto-Memory samt `MEMORY.md` |
| Firma | `/Library/Application Support/ClaudeCode/managed-settings.json` | hier nicht vorhanden |

Ein Projekt, das im Home-Verzeichnis liegt, teilt sich die Benutzerdateien —
Projekt- und Benutzerebene zeigen dann auf dieselbe Datei.

## 4. Nicht auslesbar

- **Session-ID eines fremden laufenden Prozesses.** macOS gibt die Umgebung
  nur beschnitten heraus, das Transcript wird nicht offen gehalten, der
  Socket trägt nur die PID.
- **Berechtigungsanfragen einer Terminal-Sitzung.** Sie erscheinen in der
  Oberfläche, nicht im Transcript in beantwortbarer Form. Das ist der Grund,
  warum ein Rückkanal in eine laufende Terminal-Sitzung nicht trägt.

## 5. Was davon in der iris-API steckt

| Endpunkt | Quelle |
|---|---|
| `GET /api/sessions/<k>/context` | `get_context_usage` |
| `GET /api/sessions/<k>/capabilities` | `initialize` |
| `GET /api/sessions/<k>/files` und `…/files/<id>/diff` | file-history (Einschränkung oben) |
| `POST /api/sessions/<k>/mode` | `set_permission_mode` |
| `POST /api/sessions/<k>/model` | `set_model` |
| `POST /api/sessions/<k>/interrupt` | `interrupt` |
| `POST /api/sessions/<k>/control` | beliebiger Steuerbefehl, roh |
| `POST /api/sessions/<k>/system-prompt` | `set_model` + `system_prompt` |
| `GET/POST /api/config`, `/api/config/file` | Konfigurationsflächen lesen und ändern |
| `GET /api/config/backups` | was iris vor dem Überschreiben gesichert hat |
| `GET /api/sessions/<k>/events?detail=…` | Ereignisstrom in drei Verdichtungsgraden |

Der rohe Steuerkanal ist Absicht: Wenn eine künftige Claude-Code-Version
einen neuen Subtyp bekommt, ist er sofort nutzbar, ohne die Bridge zu ändern.
