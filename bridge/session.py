"""One Claude Code process, driven over the stream-json protocol.

Design notes that came out of probing the real CLI:
  - `claude -p --input-format stream-json --output-format stream-json` is
    full duplex: stdin stays open across turns, so one process serves a
    whole conversation.
  - It runs on the Claude subscription (the stream carries five-hour
    rate-limit events), unlike the Python Agent SDK which bills the separate
    API balance. That is why we drive the CLI directly.
  - Permission decisions only reach us through --permission-prompt-tool.
    Harmless commands (echo, ls, ...) are auto-approved by Claude Code itself
    and never appear; that is by design, not a gap.
  - Clients on a headset drop off constantly; the ring buffer that replays
    what they missed lives in feed.py, shared with terminal sessions.
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid

from . import names, protocol, push, tone, tracking, uploads, usage, vorarbeiter, wachen
from .feed import Feed

CLAUDE_BIN = shutil.which("claude") or "/opt/homebrew/bin/claude"

# What the CLI accepts. `manual` is our default: every decision reaches the
# client instead of being settled by local auto-mode settings.
PERMISSION_MODES = ("manual", "default", "acceptEdits", "auto", "plan",
                    "dontAsk", "bypassPermissions")
MODE_LABELS = {
    "manual": "Alles fragen",
    "default": "Standard",
    "acceptEdits": "Änderungen ohne Nachfrage",
    "auto": "Auto",
    "plan": "Nur planen",
    "dontAsk": "Nicht fragen",
    "bypassPermissions": "Alles erlauben",
}
MCP_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "mcp_permission_server.py")
SITZUNGEN_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "mcp_sitzungen_server.py")


class Session(Feed):
    def __init__(self, key, cwd, broker, socket_path, *, model=None,
                 permission_mode="manual", resume=None, fork=False,
                 rolle="", on_change=None):
        self.key = key
        # Wofuer diese Sitzung da ist. Leer heisst: eine gewoehnliche, deine.
        # "vorarbeiter" heisst: sie fuehrt andere Sitzungen und bekommt dafuer
        # Werkzeuge, die keine gewoehnliche bekommen soll - wer beaufsichtigt,
        # darf beauftragen, und das ist nichts, was jede Sitzung koennen muss.
        self.rolle = rolle
        # Was diese Sitzung ueber jeden Geraetewechsel hinweg behaelt. Beim
        # Vorarbeiter ist das sein Charakter; bei einer gewoehnlichen Sitzung
        # ist es leer.
        self.grundlage = vorarbeiter.prompt() if rolle == "vorarbeiter" else ""
        self.cwd = cwd
        self.model = model
        self.permission_mode = permission_mode
        self.resume = resume
        # Forking gives a resumed conversation a fresh session id, so the
        # original - which may still be open in a terminal - is left alone.
        # The full history comes along; anything done here stays here.
        self.fork = fork
        self.broker = broker
        self.socket_path = socket_path
        self.on_change = on_change or (lambda s: None)

        self.claude_session_id = None
        self.title = ""
        # What the phone sent while Claude worked: (text, attachments), sent
        # as one message when the turn is over.
        self._queue = []
        self.system_prompt = ""
        # Der zuletzt gesagte Text - nur, um am Zugende zu erkennen, ob er
        # mit einer Frage endet. Mehr wird davon nicht gebraucht.
        self._zuletzt_gesagt = ""
        self.profile = tone.DEFAULT
        self.created = time.time()
        self.last_active = time.time()
        self.busy = False
        self.exited = False
        self.exit_reason = ""
        self.turn_started = None
        self.turn_acts = 0

        self._proc = None
        self._feed_init()
        self._open_asks = {}               # req_id -> card
        self._pending_control = {}         # request_id -> waiting slot

    # ---------- lifecycle ----------

    def start(self):
        cmd = [CLAUDE_BIN, "-p",
               "--input-format", "stream-json",
               "--output-format", "stream-json",
               "--verbose",
               "--permission-prompt-tool", "mcp__iris__approve",
               "--permission-mode", self.permission_mode,
               "--mcp-config", json.dumps(self._mcp_config())]
        if self.grundlage:
            # Beim Start, nicht erst beim ersten Geraetewechsel: sonst waere
            # der Vorarbeiter bis dahin eine gewoehnliche Sitzung.
            cmd += ["--append-system-prompt", self.grundlage]
        if self.rolle == "vorarbeiter":
            # Seine eigenen Werkzeuge braucht er nicht zu erbitten.
            #
            # Ein Assistent, der um Erlaubnis fragen muss, um die Liste der
            # Sitzungen anzusehen, ist keiner - Calvin am 25.09., als die
            # erste Freigabe-Frage auf dem Sperrbildschirm stand: „Wenn ich
            # alles erlauben muss, bringt der Assistent nichts."
            #
            # Nur diese sieben, und keins davon greift in etwas ein: sehen,
            # lesen, beauftragen, Messreihe fuehren. Alles andere - Dateien,
            # Befehle, was auch immer eine beaufsichtigte Sitzung tut - geht
            # weiter ueber die Freigaben.
            cmd += ["--allowedTools"] + [
                "mcp__iris-sitzungen__" + w for w in
                ("sitzungen", "sitzung_lesen", "sitzung_beauftragen",
                 "wache_anlegen", "wache_runde", "wachen", "wache_beenden")]
        if self.model:
            cmd += ["--model", self.model]
        if self.resume:
            cmd += ["--resume", self.resume]
            if self.fork:
                cmd += ["--fork-session"]

        env = dict(os.environ)
        env["IRIS_BRIDGE_SOCKET"] = self.socket_path
        env["IRIS_SESSION_KEY"] = self.key

        try:
            self._proc = subprocess.Popen(
                cmd, cwd=self.cwd, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1,
                # Claude writes UTF-8. Without this Windows reads it as cp1252
                # and "weiß" arrives as "weiÃŸ".
                encoding="utf-8", errors="replace")
        except OSError as exc:
            self.exited, self.exit_reason = True, f"Start fehlgeschlagen: {exc}"
            self._emit({"kind": "error", "text": self.exit_reason})
            return False

        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        return True

    def _mcp_config(self):
        # Our permission server is the only MCP server we inject; the
        # project's own servers still load from its settings.
        server = {"iris": {
            "command": sys.executable,
            "args": [MCP_SERVER],
            "env": {"IRIS_BRIDGE_SOCKET": self.socket_path,
                    "IRIS_SESSION_KEY": self.key},
        }}
        if self.rolle == "vorarbeiter":
            # Sitzungen fuehren, Wachen halten. Nur fuer diese Rolle: sonst
            # koennte jede Sitzung jeder anderen Auftraege schicken.
            server["iris-sitzungen"] = {
                "command": sys.executable,
                "args": [SITZUNGEN_SERVER],
                "env": {"IRIS_SESSION_KEY": self.key},
            }
        return {"mcpServers": server}

    def stop(self, reason="Vom Nutzer beendet"):
        self.exit_reason = reason
        self.broker.deny_session(self.key, "Session beendet")
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                if os.name == "nt":
                    # On Windows claude starts through claude.cmd: the child is
                    # cmd.exe, claude.exe runs below it. terminate() would end
                    # only cmd.exe and leave claude.exe running - the whole
                    # tree goes instead.
                    subprocess.run(["taskkill", "/PID", str(self._proc.pid), "/T", "/F"],
                                   capture_output=True, timeout=10)
                else:
                    self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    self._proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        # No 'closed' card here: the stdout reader emits exactly one when
        # the process actually ends, so clients never see it twice.
        self.exited = True

    def interrupt(self):
        """Stop the current turn without killing the conversation.

        Uses the control channel rather than SIGINT: the CLI answers with
        what was still queued, and the process is left in a clean state.
        """
        if not self._proc or self._proc.poll() is not None:
            return False, "Die Sitzung läuft nicht mehr."
        resp, err = self.control("interrupt", timeout=10)
        if err:
            return False, err
        self.busy = False
        self._emit({"kind": "interrupted",
                    "still_queued": (resp or {}).get("still_queued", [])})
        self.on_change(self)
        return True, ""

    # ---------- input ----------

    def send(self, text, attachments=None):
        """A message, optionally with files from the upload folder.

        Images go inline, as Claude sees a pasted photo; other files are
        named by path, and Claude reads them with its tools.
        """
        if self.exited or not self._proc or self._proc.poll() is not None:
            return False, "Session ist beendet"
        attachments = attachments or []
        if self.busy:
            # Claude is working: it waits here and goes when the turn is over.
            # Refused, the phone dropped it for good - a lost message.
            self._queue.append((text, list(attachments)))
            card = {"kind": "queued", "text": text, "busy": True, "delivery": "turn"}
            if attachments:
                card["attachments"] = [uploads.describe(p) for p in attachments]
            self._emit(card)
            self.last_active = time.time()
            self.on_change(self)
            return True, ""
        return self._write(text, attachments, announce=True)

    def _write(self, text, attachments, announce):
        """Hands a message to claude. `announce` shows it as sent; a queued
        one is on the phone already and is only marked delivered."""
        content = text
        if attachments:
            import base64
            content = [{"type": "text", "text": "\n\n".join(
                t for t in (text, uploads.mention(attachments)) if t)}]
            for path in attachments:
                mt = uploads.media_type(path)
                if mt in uploads.IMAGE_TYPES:
                    with open(path, "rb") as fh:
                        data = base64.b64encode(fh.read()).decode()
                    content.append({"type": "image", "source": {
                        "type": "base64", "media_type": mt, "data": data}})
        msg = {"type": "user", "message": {"role": "user", "content": content}}
        try:
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            return False, f"Schreiben fehlgeschlagen: {exc}"
        self.busy = True
        self.last_active = time.time()
        self.turn_started = time.time()
        self.turn_acts = 0
        if not self.title:
            self.title = " ".join(text.split())[:48] or "Anhang"
        if announce:
            card = {"kind": "sent", "text": text}
            if attachments:
                card["attachments"] = [uploads.describe(p) for p in attachments]
            self._emit(card)
        self.on_change(self)
        return True, ""

    def _send_queued(self):
        """What waited, as one message - the same as several lines typed at
        once. Only when the turn is over and claude still runs."""
        if not self._queue or self.busy:
            return
        if self.exited or not self._proc or self._proc.poll() is not None:
            self._drop_queue()
            return
        waiting, self._queue = self._queue, []
        text = "\n\n".join(t for t, _ in waiting if t)
        files = [f for _, fs in waiting for f in fs]
        ok, err = self._write(text, files, announce=False)
        if ok:
            self._emit({"kind": "delivered", "count": len(waiting), "via": "session"})
        else:
            self._queue = waiting + self._queue
            self._emit({"kind": "error", "text": "Nicht übergeben: " + err})

    def _drop_queue(self):
        """The session ended with messages still waiting - said out loud,
        never dropped in silence."""
        if not self._queue:
            return
        lost = " · ".join((t or "Anhang")[:60] for t, _ in self._queue)
        self._queue = []
        self._emit({"kind": "error", "text": "Nicht mehr gesendet, die Sitzung ist beendet: " + lost})

    def control(self, subtype, payload=None, timeout=20):
        """Send a control_request and wait for its answer.

        The CLI accepts a small set of these over stdin. Verified to work:
        initialize, get_context_usage, set_permission_mode, set_model,
        interrupt, get_binary_version, mcp_message. Anything else comes back
        as "Unsupported control request subtype", which is how the list above
        was established in the first place.
        """
        if self.exited or not self._proc or self._proc.poll() is not None:
            return None, "Session ist beendet"
        rid = f"c-{uuid.uuid4().hex[:10]}"
        waiter = threading.Event()
        self._pending_control[rid] = {"event": waiter, "response": None,
                                      "error": None}
        req = {"type": "control_request", "request_id": rid,
               "request": {"subtype": subtype, **(payload or {})}}
        try:
            self._proc.stdin.write(json.dumps(req) + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            self._pending_control.pop(rid, None)
            return None, f"Schreiben fehlgeschlagen: {exc}"

        if not waiter.wait(timeout):
            self._pending_control.pop(rid, None)
            return None, "Keine Antwort vom Steuerkanal"
        slot = self._pending_control.pop(rid, {})
        return slot.get("response"), slot.get("error") or ""

    def set_permission_mode(self, mode):
        """Switch the mode on the live session - no restart needed.

        Verified against the CLI: a control_request with subtype
        set_permission_mode is answered with success and the session then
        reports the new mode in a system/status event.
        """
        if mode not in PERMISSION_MODES:
            return False, f"Unbekannter Modus: {mode}"
        if self.exited or not self._proc or self._proc.poll() is not None:
            return False, "Session ist beendet"
        resp, err = self.control("set_permission_mode", {"mode": mode})
        if err:
            return False, err
        self.permission_mode = (resp or {}).get("mode", mode)
        self._emit({"kind": "mode", "mode": self.permission_mode})
        self.on_change(self)
        return True, ""

    def set_model(self, model):
        """Switch the model on a live session."""
        resp, err = self.control("set_model", {"model": model})
        if err:
            return False, err
        self.model = model
        self._emit({"kind": "model", "model": model})
        self.on_change(self)
        return True, ""

    def set_system_prompt(self, prompt):
        """Replace the custom system prompt from the next turn on.

        Carried by set_model with the *current* model. The field is
        `system_prompt` in snake_case - `systemPrompt` is acknowledged with
        success but silently does nothing, which is worth knowing before
        building on it. There is no way back to the built-in prompt, so an
        empty value is refused rather than sent.
        """
        prompt = (prompt or "").strip()
        if not prompt:
            return False, "Leerer System-Prompt wird nicht gesetzt"
        model = self.model or "default"
        resp, err = self.control("set_model",
                                 {"model": model, "system_prompt": prompt})
        if err:
            return False, err
        self.system_prompt = prompt
        self._emit({"kind": "system_prompt", "length": len(prompt)})
        return True, ""

    def set_profile(self, profile):
        """Ton auf das Gerät stellen, von dem gerade gelesen wird.

        Kein Wechsel, wenn sich nichts ändert - jeder Wechsel kostet einen
        Steuerbefehl und wirkt ohnehin erst ab dem nächsten Zug.
        """
        if profile not in tone.PROFILES:
            return False, f"Unbekanntes Profil: {profile}"
        if profile == self.profile:
            return True, ""
        ok, err = self.set_system_prompt(tone.prompt_for(profile, self.grundlage))
        if not ok:
            return False, err
        self.profile = profile
        self._emit({"kind": "profile", "profile": profile,
                    "label": tone.PROFILES[profile]["label"]})
        self.on_change(self)
        return True, ""

    def context_usage(self):
        """Full context breakdown - what the terminal never shows you."""
        return self.control("get_context_usage")

    def capabilities(self):
        """Models, slash commands, agents, account, permission mode."""
        return self.control("initialize")

    # ---------- permissions ----------

    def offer_permission(self, pending):
        """Surface a parked permission request as an `ask` card.

        Also the moment to snapshot: the tool has not run yet, so the file
        on disk is still the version before this change.
        """
        tracking.before_tool(self.key, pending.tool_name, pending.tool_input)
        card = {
            "kind": "ask",
            "request_id": pending.id,
            "tool": pending.tool_name,
            "detail": protocol._describe_tool(pending.tool_name, pending.tool_input),
            "input": pending.tool_input,
            # What is being approved, not only where: +/- lines of the change.
            "change": protocol.change_summary(pending.tool_name, pending.tool_input),
        }
        self._open_asks[pending.id] = card
        self._emit(card)
        push.ask(self.push_title(), self.key, card, self.watchers() > 0)
        self.last_active = time.time()

    def answer_permission(self, req_id, allow, message="", answers=None):
        """Settle a parked request.

        `answers` is for AskUserQuestion: {question text: chosen label(s)}.
        It goes back as the tool's own input, which is how the CLI hands the
        choice to the model - verified: Claude replies "Your questions have
        been answered" and carries on with the choice.
        """
        pending = self.broker.get(req_id)
        if not pending or pending.answered:
            return False, "Anfrage nicht mehr offen"
        if answers:
            pending.answer(True, updated_input={**pending.tool_input,
                                                "answers": answers})
        else:
            pending.answer(allow, message)
        self.broker.drop(req_id)
        self._open_asks.pop(req_id, None)
        self._emit({"kind": "answered", "request_id": req_id, "allow": allow})
        push.settled(req_id)
        self.last_active = time.time()
        return True, ""

    def push_title(self):
        """What a notification calls this session."""
        t = names.get(self) or self.title or os.path.basename(self.cwd.rstrip("/")) or "Sitzung"
        return t if len(t) < 46 else t[:t.rfind(" ")].rstrip(",.;:") + " …"

    def open_asks(self):
        return list(self._open_asks.values())

    # ---------- output ----------

    def _read_stdout(self):
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if raw.get("type") == "assistant":
                # Modes like acceptEdits skip the permission broker, so the
                # snapshot has to be taken here too. Both paths are safe to
                # hit: the first one to arrive wins, later ones are no-ops.
                for c in (raw.get("message", {}).get("content") or []):
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        self.turn_acts += 1
                        tracking.before_tool(self.key, c.get("name"),
                                             c.get("input"))
                    elif isinstance(c, dict) and c.get("type") == "text" \
                            and (c.get("text") or "").strip():
                        self._zuletzt_gesagt = c["text"]
            if raw.get("type") == "control_response":
                r = raw.get("response") or {}
                slot = self._pending_control.get(r.get("request_id"))
                if slot:
                    if r.get("subtype") == "success":
                        slot["response"] = r.get("response") or {}
                    else:
                        slot["error"] = str(r.get("error") or "abgelehnt")
                    slot["event"].set()
                continue
            if raw.get("type") == "system" and raw.get("subtype") == "init":
                self.claude_session_id = raw.get("session_id")
                if self.rolle == "vorarbeiter":
                    # Damit er nach dem naechsten Neustart dort weitermacht.
                    vorarbeiter.merken(self.claude_session_id)
            elif raw.get("type") == "system" and raw.get("subtype") == "status":
                mode = raw.get("permissionMode")
                if mode and mode != self.permission_mode:
                    self.permission_mode = mode
                    self._emit({"kind": "mode", "mode": mode})
                    self.on_change(self)
            if raw.get("type") == "result":
                self.busy = False
                # What the phone sent meanwhile goes now - a moment later, so
                # the end of this turn reaches the app first.
                threading.Timer(0.3, self._send_queued).start()
                self.last_active = time.time()
                tracking.after_turn(self.key)
                if self.turn_started:
                    # Dasselbe wie bei Terminal-Sitzungen: eine Frage am Ende
                    # ist keine Fertigmeldung. Der letzte Satz steht im
                    # Ringpuffer der Karten.
                    zuletzt = self._zuletzt_gesagt
                    wachen.nach_zug(self.key, zuletzt)
                    if self.rolle == "vorarbeiter":
                        # Er redet mit Calvin, nicht mit sich selbst.
                        push.assistent(self.push_title(), self.key, zuletzt)
                    elif push._endet_mit_frage(zuletzt):
                        push.wartet(self.push_title(), self.key, zuletzt,
                                    self.watchers() > 0)
                    else:
                        push.done(self.push_title(), self.key, time.time() - self.turn_started,
                                  self.turn_acts, self.watchers() > 0,
                                  text=zuletzt)
                    self.turn_started = None
                self.on_change(self)
            if raw.get("type") == "rate_limit_event":
                self._note_rate(raw.get("rate_limit_info") or {})
            # Store the event whole; each subscriber gets its own reduction.
            if protocol.reduce_event(raw, "full"):
                self._emit_raw(raw)
        # stdout closed => process is done
        self.busy = False
        self.exited = True
        code = self._proc.poll() if self._proc else None
        self.broker.deny_session(self.key, "Session beendet")
        self._drop_queue()
        self._emit({"kind": "closed",
                    "reason": self.exit_reason or f"Prozess beendet (Code {code})"})
        self.on_change(self)

    def _note_rate(self, info):
        """The stream's word on the plan's limits: into the shared figures,
        and a used-up window said at once - it would look like a hang."""
        windows = {name: {"used": w.get("utilization"), "resets_at": w.get("resetsAt")}
                   for name, w in (info.get("unifiedWindows") or {}).items() if isinstance(w, dict)}
        usage.report(windows, used_as_fraction=True)
        if info.get("status") == "rejected":
            window, resets = info.get("rateLimitType") or "five_hour", info.get("resetsAt")
            if usage.hit(window, resets, self.push_title(), self.key):
                self._emit({"kind": "error", "text": usage.message(window, resets)})

    def _read_stderr(self):
        for line in self._proc.stderr:
            line = line.rstrip()
            if line and "[iris-permission]" not in line:
                self._emit({"kind": "error", "text": line[:500]})

    # ---------- view ----------

    def describe(self):
        return {
            "key": self.key,
            "cwd": self.cwd,
            "label": os.path.basename(self.cwd.rstrip("/")) or self.cwd,
            # A name given from the phone or the Mac wins over the made-up one.
            "title": names.get(self) or self.title,
            "claude_session_id": self.claude_session_id,
            "model": self.model,
            "permission_mode": self.permission_mode,
            "permission_label": MODE_LABELS.get(self.permission_mode,
                                                self.permission_mode),
            "profile": self.profile,
            # Damit die App sie erkennt: ein Vorarbeiter gehoert nicht in die
            # Liste deiner Sitzungen, er ist keine Arbeit, er ist Aufsicht.
            "rolle": self.rolle,
            "resume": self.resume,
            "fork": self.fork,
            "busy": self.busy,
            "turn_started": self.turn_started,
            "exited": self.exited,
            "created": self.created,
            "last_active": self.last_active,
            "seq": self._seq,
            "open_asks": len(self._open_asks),
            # Nicht nur wie viele, sondern welche. Die App haelt ihre
            # Karten selbst und wirft sie erst weg, wenn ein "answered"
            # eintrifft - verpasst sie das, steht die Karte fuer immer.
            # Damit kann sie abgleichen statt zu glauben.
            "open_ask_ids": list(self._open_asks.keys()),
        }
