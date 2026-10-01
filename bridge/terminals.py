"""Terminal sessions: Claude Code conversations running in a terminal, seen
and steered through hooks.

For a long time this looked impossible. The session id of a terminal session
cannot be read from outside - macOS trims the environment of other people's
processes, and the transcript is not held open. But the session reports
itself when asked: hooks in ~/.claude/settings.json fire in every session,
and SessionStart carries the id and the transcript path before the first
prompt. Everything here hangs off that.

One source per piece of information:
  - what Claude says         -> the Terminal.app tab itself (see screen);
                                elsewhere MessageDisplay, else the transcript
  - what was done            -> the transcript, tailed live
  - approvals and durations  -> the hooks
  - busy / done / closed     -> the hooks
  - what runs in background  -> the hooks (tool calls, subagents, Stop)

Text comes from the terminal's own scrollback when the session runs in
Terminal.app: the transcript leaves out most sentences written between tool
calls, and the display hook arrives late in long sessions or stops arriving.
Elsewhere the display hook is used once a session sends it, and the
transcript's text until then.

Everything a terminal session shows is also written to disk (feeds/, next to
terminals.json), together with where reading stopped. After a restart the
bridge picks up where it was, so opening the app brings every message since -
not only those that happened while the bridge was running.
The transcript is only ever read. Hooks only ever answer.

A message from the phone reaches the session by being typed into its
Terminal.app tab or Windows console (see typist): at once when the session sits at its prompt,
right after the turn when Claude is still working. It stands in the terminal
as a normal prompt. A session in another terminal program cannot be typed
into; there the message rides along with the next prompt typed at the Mac,
or with the end of the running turn.

A running turn is stopped the same way, with Ctrl+C in its tab.

The mode is switched with Shift+Tab, reading the status line after each
step. What cannot be done: switch the model - /model would save it as the
default for every new session as well.
"""
import collections
import json
import os
import re
import threading
import time
import uuid

from . import config, history, protocol, push, screen, typist, uploads, names, usage, wachen
from .feed import Feed
from .session import MODE_LABELS

AWAY_PATH = os.environ.get("IRIS_AWAY_PATH") or os.path.join(
    config.CONFIG_DIR, "away.json")

# The sessions the bridge knew, so a restart does not forget them: until a
# session sent its next hook, the phone would get "unknown session".
STATE_PATH = os.environ.get("IRIS_TERMINALS_PATH") or os.path.join(
    config.CONFIG_DIR, "terminals.json")
REVIVE_WITHIN = 12 * 3600

# Every card of a terminal session, on disk - beside the state, so a test
# bridge with its own state never writes into the real one.
FEEDS_DIR = os.path.join(os.path.dirname(STATE_PATH), "feeds")

# ... and this makes sure of it instead of trusting whoever starts the second
# bridge. Two bridges on one feeds folder each count for themselves, so the
# same number ends up on different cards; the app reads a number that falls
# back as "the bridge started counting afresh", throws its conversation away
# and loads it again - without end. The lock is held for the life of the
# process; a bridge that does not get it watches, but writes nothing.
FEED_OWNER_PATH = os.path.join(FEEDS_DIR, ".owner")
_owner_fd = None
_owns_feeds = None

# A terminal session keeps more than a hosted one: this is its whole
# conversation as far as the phone is concerned.
TERMINAL_RING = 3000

# While Claude works, the screen is read this often for new text.
SCREEN_EVERY = 1.5

# How often the list of running claude processes is read again.
DISCOVER_EVERY = 4.0

# A session without a process of its own (a `claude -p` run, one remembered
# from before a restart) that has been silent this long is not running.
GONE_AFTER = 120

# The scratch sessions iris' own tests open are not yours: the bridge you
# use leaves them out. A test bridge (IRIS_DISCOVER_TESTS) sees only them -
# it has no business reading your tabs.
TEST_ROOT = os.path.expanduser("~/Library/Caches/iris-test")
SHOW_TESTS = bool(os.environ.get("IRIS_DISCOVER_TESTS"))

# Wie oft nachgefasst wird, wenn eine Nachricht mit Anhang noch in der
# Eingabe steht: alle drei Sekunden, also gut eine halbe Minute. So lange
# kann Claude Code an einem grossen Foto lesen, bevor es den Return annimmt.
ANHANG_VERSUCHE = 10
# Wie lange je Versuch auf die leere Eingabe gewartet wird, und wie oft dabei
# hingesehen wird. Als Konstanten, damit tests/anhang.py dieselbe Logik in
# Millisekunden prueft statt in halben Minuten - an der Entscheidung aendert
# die Dauer nichts, sie kostete nur Wartezeit bei jedem `make check`.
ANHANG_FENSTER = 3
ANHANG_TAKT = 0.3
# Wie lange abgewartet wird, dass das Eingefuegte ueberhaupt auf dem
# Bildschirm steht, bevor ueberhaupt geurteilt wird. Aus demselben Grund eine
# Konstante wie die beiden darueber.
ANHANG_ANKUNFT = 6

# Held any longer and Claude Code's own 600 s hook limit cuts in first -
# after which the tool runs as though nobody had been asked.
HOLD_SECONDS = 570

# Tools that never wait for the phone. They only look, or they only ask:
# being asked on the phone whether Claude may read a file is noise, not
# safety. Questions (AskUserQuestion) take their own way, see _on_question.
PASS_THROUGH = frozenset({
    "Read", "Glob", "Grep", "LS", "NotebookRead", "TodoWrite", "WebSearch",
    "ToolSearch", "BashOutput", "TaskOutput", "Task", "Agent", "Skill",
    "ExitPlanMode", "EnterPlanMode", "ListMcpResourcesTool",
    "ReadMcpResourceTool",
})
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

# Modes in which whoever sits at the terminal already decided not to be
# asked, or in which nothing runs at all. The phone does not overrule that.
NO_HOLD_MODES = frozenset({"bypassPermissions", "dontAsk", "auto", "plan"})

# A display message whose last piece arrived waits this long for pieces that
# overtook each other - the hook runs detached, so order is not promised.
SETTLE_SECONDS = 0.3

# A message is typed this long after the Stop hook answered, so the prompt is
# back on screen when it arrives.
TYPE_AFTER_STOP = 0.8


# Claude Code's working line: "✽ Prestidigitating… (10m 32s · ↓ 28.0k tokens)".
# The glyph turns, the word stays for the turn, the brackets say what goes on.
_SPINNER = re.compile(r"^[^\w\s(]\s(\S[^()]*?…)\s+\(([^()]*)\)\s*$")


# Die fluechtige Taetigkeitszeile: "Reading 1 file, running 1 shell command…"
# oder "Running 1 shell command · 2s…". Sie steht waehrend eines Schritts da
# und wird von der eigentlichen Antwort ersetzt - auf dem Bildschirm. In der
# App blieb sie als Nachricht stehen, mit Sternchen und "Antwort kopieren",
# als haette Claude das gesagt.
#
# Eng gefasst mit Absicht: erstes Wort aus einer festen Liste, eine Zeile,
# kurz, und am Ende die Auslassungspunkte. Ein echter Absatz, der so anfaengt
# UND so endet, ist selten genug - und faellt hier nur einmal weg, nicht
# dauerhaft, weil das Transkript ihn ohnehin nachliefert.
_TAETIGKEIT = re.compile(
    r"^(?:\S+\s+)?(?:Running|Reading|Writing|Editing|Searching|Fetching|"
    r"Creating|Listing|Updating|Deleting|Analyzing|Checking)\b"
    r"[^\n]{0,110}?(?:·\s*\d+[.,]?\d*\s*[ms]s?\s*)?(?:\.\.\.|…)$")


def _ist_taetigkeit(text):
    zeile = " ".join((text or "").split())
    return "\n" not in (text or "").strip() and bool(_TAETIGKEIT.match(zeile))


def _ist_fork(pfad):
    """Gehoert dieses Transkript einem Agenten aus `/fork`?

    Claude Code gibt jedem geforkten Agenten eine eigene Sitzungskennung,
    und seine Hooks kommen damit an. Ohne diese Frage macht iris daraus
    eine eigene Sitzung - mit dem geerbten Titel, weil der Agent das ganze
    Gespraech kennt. Am 23.09. standen so vier Eintraege fuer eine Sache,
    drei davon Geister ohne laufenden Prozess.

    Die Marke steht in der ersten Zeile des Transkripts:
    {"type":"history-suppression", ..., "cause":"fork_inherit"}

    Ein Fork, den jemand spaeter wirklich in einem Terminal fortsetzt,
    kommt ueber die Prozess-Suche herein und nicht hier - der laeuft dann
    als eigene interaktive Sitzung und gehoert auch in die Liste.
    """
    if not pfad or not os.path.isfile(pfad):
        return False
    try:
        with open(pfad, encoding="utf-8", errors="replace") as fh:
            for _ in range(5):
                zeile = fh.readline()
                if not zeile:
                    break
                if "history-suppression" in zeile and "fork_inherit" in zeile:
                    return True
    except OSError:
        pass
    return False


def _only_watches(task):
    """A task that waits for something to happen - a monitor, a live
    subscription to a published page - is not work in the background."""
    kind = (task.get("type") or "").lower()
    what = (task.get("description") or task.get("command") or "").lower()
    return kind in ("monitor", "watch", "subscription") or what.startswith(("monitor ", "watch "))


def _norm(text):
    return " ".join((text or "").split())[:200]


def _core(text):
    """What is left to compare of a message once Claude Code has had it: a
    pasted image path becomes "[Image #3]", so neither the marker nor the
    path behind "Anhang:" can be matched."""
    text = re.sub(r"\[Image #\d+\]", " ", text or "")
    text = re.sub(r"Anhang:[^\n]*", " ", text)
    return " ".join(text.split())


NOT_POSSIBLE = ("Bei einer Terminal-Sitzung nicht möglich: das Modell stellt, "
                "wer am Terminal sitzt – /model würde es für alle neuen Sitzungen "
                "mit umstellen.")

# A second Ctrl+C at an idle prompt quits claude - so never two in a row.
INTERRUPT_GAP = 5.0


def _background_id(response):
    """The task id Claude Code hands back when a call went to the background -
    as a field, or in the sentence it answers with after Ctrl+B.

    The sentence only counts at the very start of the output. Searched for
    anywhere, every log that merely quoted it - a task's output being read
    back - became another phantom task in the background."""
    if isinstance(response, dict):
        for key in ("backgroundTaskId", "taskId", "shellId", "bash_id"):
            if response.get(key):
                return str(response[key])
        response = response.get("stdout") or ""
    if isinstance(response, str):
        m = re.match(r"\s*Command (?:was manually backgrounded by user|running in background)"
                     r" with ID:\s*([A-Za-z0-9_-]{4,})", response)
        if m:
            return m.group(1)
    return None


def needs_phone(tool, mode):
    """Would this call wait for an answer from the phone?"""
    if mode in NO_HOLD_MODES:
        return False
    if tool in PASS_THROUGH or tool.startswith("mcp__iris"):
        return False
    if mode == "acceptEdits" and tool in EDIT_TOOLS:
        return False
    return True


def _decision(verdict, reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": verdict,
                                   "permissionDecisionReason": reason}}


def _freigabe(verdict, reason):
    """Dasselbe Urteil, wie PermissionRequest es verlangt.

    Nicht `permissionDecision` wie bei PreToolUse, sondern ein
    `decision`-Objekt - Claude Code sagt es selbst deutlich:
    "PermissionRequest decision must be {"behavior": "allow"} or
    {"behavior": "deny", "message": "..."}". Ein "ask" gibt es dort nicht,
    und der Grund reist nur bei einer Ablehnung mit.
    """
    entscheidung = {"behavior": verdict}
    if verdict == "deny":
        entscheidung["message"] = reason
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                   "decision": entscheidung}}


def _size(path):
    try:
        return os.path.getsize(path) if path else 0
    except OSError:
        return 0


def _cwd_of(transcript):
    """The working directory a transcript last recorded."""
    try:
        size = os.path.getsize(transcript)
        with open(transcript, "rb") as fh:
            fh.seek(max(0, size - 200_000))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("cwd"):
            return rec["cwd"]
    return ""


def owns_feeds():
    """True when this bridge may write the feeds. Taken once, kept until it
    exits. A test bridge points IRIS_TERMINALS_PATH somewhere else and gets
    its own folder; one that shares this folder reads only."""
    global _owner_fd, _owns_feeds
    if _owns_feeds is not None:
        return _owns_feeds
    _owns_feeds = False
    try:
        os.makedirs(FEEDS_DIR, mode=0o700, exist_ok=True)
        fd = os.open(FEED_OWNER_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return _owns_feeds
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        held = ""
        try:
            held = os.read(fd, 32).decode().strip()
        except OSError:
            pass
        os.close(fd)
        print(f"iris: {FEEDS_DIR} gehört Bridge {held or '?'} - diese schreibt "
              "keine Terminal-Karten. Eigener Ordner: IRIS_TERMINALS_PATH=…")
        return _owns_feeds
    # Who holds it, for the next person who reads the folder.
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
    except OSError:
        pass
    _owner_fd = fd                     # closing it would drop the lock
    _owns_feeds = True
    return _owns_feeds


def _load_away():
    try:
        with open(AWAY_PATH) as fh:
            return bool(json.load(fh).get("away"))
    except (OSError, ValueError):
        return False


def _save_away(on):
    os.makedirs(os.path.dirname(AWAY_PATH), exist_ok=True)
    with open(AWAY_PATH, "w") as fh:
        json.dump({"away": bool(on), "since": time.time()}, fh)


class TerminalSession(Feed):
    kind = "terminal"

    def __init__(self, sid, cwd, transcript, on_change):
        self._feed_init()
        self._ring_size = TERMINAL_RING
        self.claude_session_id = sid
        self.key = "t-" + sid
        self.cwd = cwd or ""
        self.transcript = transcript or history.find_transcript(sid) or ""
        self.on_change = on_change
        self.title = ""
        self.permission_mode = "default"
        self.created = time.time()
        self.last_active = self.created
        self.last_event = self.created
        self.busy = False
        self.exited = False
        self.exit_reason = ""
        self.turn_started = None
        self.acts = 0
        self.failed = 0
        self.turn_acts_start = 0
        self.background = {}               # id -> task running on its own
        self._announced = []               # waiting in Claude Code's queue, shown greyed
        self._said = set()                 # every paragraph the feed holds, normalized
        self._taken = []                   # waiting messages already reported as taken
        self._view_shown = False           # the phone knows a view holds the tab
        self.artifacts = {}                # url -> page published in this session
        self._artifact_calls = {}          # tool_use id -> Artifact input, until answered
        self._artifacts_read = False
        self._activity = None              # (word, thinking) of the working line
        self._texts = {}                   # message_id -> {index: delta}
        self._tlock = threading.Lock()
        # Text comes from the display hook once this session sends it, and
        # from the transcript until then. What was shown either way is
        # remembered, so the handover never shows a sentence twice.
        self.display_seen = False
        self._shown = collections.deque(maxlen=40)
        # The say cards of the running turn, by seq. The screen shows a
        # paragraph without its markdown; the transcript has it whole and
        # says which cards it stands in for.
        self._turn_says = []
        self._said_seq = {}                # message id -> seqs of its say cards
        self._queue = []
        self._qlock = threading.Lock()
        self._open_asks = {}               # request_id -> card
        self._slots = {}                   # request_id -> waiting answer
        self._question = None              # the question on screen right now
        # Where the session runs, so a message can be typed into its tab:
        # its claude process and that one's tty, found from a hook's parent.
        self.pid = None
        self.tty = None
        self._ppid = None
        self.type_error = ""
        self._interrupted_at = 0.0
        self._settling = False             # after a stop, until the input is clean
        self._typed = collections.deque(maxlen=20)   # what iris typed there
        # The last display events and what became of them - for when text
        # goes missing (GET /api/hooks/stats?session=<id>).
        self.text_log = collections.deque(maxlen=60)
        self._type_lock = threading.Lock()
        # Text read from the terminal: whether the session has one to read
        # (None = not known yet), and the last block taken from it.
        self.screen_source = None
        self._anchor, self._anchor_n = None, 0
        self._screen_at = 0.0
        self._screen_retry = 0.0           # after a failed look, not before this
        self._screen_due = 0.0             # the transcript grew: look again then
        self._screen_lock = threading.Lock()
        self._persisted = 0
        # Everything before this byte is history and served by /history;
        # the live tail starts here, so nothing appears twice. A session
        # this bridge watched before carries on where it stopped reading.
        self.start_offset = _size(self.transcript)
        self._offset = self.start_offset
        self.context_tokens = history.last_context(self.transcript)
        self.context_line = None           # from the status line, when it runs
        self._restore()
        self._load_queue()
        self._tail_stop = threading.Event()
        self._refresh_title()
        threading.Thread(target=self._tail, daemon=True).start()

    # ---------- transcript ----------

    def _tail(self):
        buf = b""
        while not self._tail_stop.is_set():
            if not self.transcript:
                self.transcript = history.find_transcript(
                    self.claude_session_id) or ""
            size = _size(self.transcript)
            if self.transcript and not self._artifacts_read:
                self._read_artifacts()
            if size < self._offset:
                # Rewritten underneath us: pick up from the new end rather
                # than replaying a conversation that is already on screen.
                self._offset, buf = size, b""
            if size > self._offset:
                try:
                    with open(self.transcript, "rb") as fh:
                        fh.seek(self._offset)
                        chunk = fh.read(size - self._offset)
                except OSError:
                    chunk = b""
                self._offset += len(chunk)
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for line in lines:
                    try:
                        self._ingest(line)
                    except Exception as exc:          # noqa: BLE001
                        # One bad record must never end the reading of the
                        # transcript - the phone would go quiet for good.
                        self.text_log.append({"t": round(time.time(), 2), "ingest_error": repr(exc)[:200]})
                if lines and self.tty:
                    # Something happened - even in a session that sends no
                    # hooks. What Claude wrote with it is on screen shortly.
                    self._screen_due = time.time() + 0.8
            if self.exited and time.time() - self.last_event > 5 \
                    and _size(self.transcript) == self._offset:
                return
            if self.busy and time.time() - self._screen_at > SCREEN_EVERY:
                self._sync_screen()
            elif self._screen_due and time.time() >= self._screen_due:
                self._screen_due = 0.0
                self._sync_screen()
            self._tail_stop.wait(0.4)

    def _ingest(self, line):
        try:
            rec = json.loads(line)
        except ValueError:
            return
        op = history.queue_operation(rec)
        if op:
            self._queue_op(*op)
            return
        if not history.relevant(rec):
            return
        limit = usage.limit_record(rec)
        if limit:
            self._on_limit(*limit)
        if rec.get("type") == "assistant":
            self.context_tokens = history.context_tokens(rec) or self.context_tokens
            content = rec.get("message", {}).get("content") or []
            if any(
                    isinstance(c, dict) and c.get("type") == "tool_use" for c in content):
                # What Claude wrote before this call is on screen by now; it
                # goes first, so the order is the terminal's.
                self._sync_screen(tool_follows=True)
            texts = [c for c in content if isinstance(c, dict) and c.get("type") == "text"]
            if texts and self.screen_source:
                self._complete_from_transcript(texts)
            elif texts and self.display_seen:
                self._markdown_from_transcript(rec.get("message", {}).get("id"), texts)
            if texts and (self.display_seen or self.screen_source
                          or all((c.get("text") or "").strip() in self._shown for c in texts)):
                content = [c for c in content if c not in texts]
                if not content:
                    return
                rec = {**rec, "message": {**rec.get("message", {}), "content": content}}
            else:
                for c in texts:
                    self._shown.append((c.get("text") or "").strip())
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    self.acts += 1
                    if c.get("name") == "Artifact" and \
                            (c.get("input") or {}).get("action") in (None, "publish"):
                        self._artifact_calls[c.get("id")] = c.get("input") or {}
            self._emit_raw(rec)
        else:
            self._check_interrupt(rec)
            for card in history.user_cards(rec):
                if card.get("kind") == "sent" and (
                        self._was_announced(card.get("text")) | self._was_typed(card.get("text"))):
                    continue               # on the phone already: as its message, or as waiting
                if card.get("kind") == "result" and not card.get("ok"):
                    self.failed += 1
                if card.get("kind") == "result" and card.get("tool_use_id") in self._artifact_calls:
                    inp = self._artifact_calls.pop(card["tool_use_id"])
                    item = card.get("ok") and history.artifact_item(
                        inp, card.get("text"), self.artifacts, time.time())
                    if item:
                        self.artifacts[item["url"]] = item
                        self._artifacts_changed()
                self._emit(card)
        self.last_active = time.time()

    # ---------- text from the terminal ----------

    def _sync_screen(self, tool_follows=False):
        """Take the text blocks that appeared on the terminal since the last
        look. The first look only marks where the screen stands: what was
        there before belongs to the history, not to the live feed."""
        if not self.tty or time.time() < self._screen_retry:
            return
        with self._screen_lock:
            self._screen_at = time.time()
            h = typist.screen_history(self.tty)
            if h is None:
                # No tab to read (another terminal program) or a look that
                # failed: try again later, meanwhile the other sources speak.
                self.screen_source = None
                self._screen_retry = time.time() + 30
                return
            if self.screen_source is None:
                self.screen_source = True
                if self._anchor is None:
                    done = [t for t, complete in screen.blocks(h) if complete]
                    if done:
                        self._anchor, self._anchor_n = done[-1], done.count(done[-1])
                    return
            self._note_activity(h)
            new, self._anchor, self._anchor_n = screen.since(
                h, self._anchor, self._anchor_n, take_last=tool_follows)
            for text in new:
                if self._schon_gesagt(text):
                    continue
                n = _kern(text)
                if _ist_taetigkeit(text):
                    # Die fluechtige Zeile eines laufenden Schritts. Auf dem
                    # Bildschirm wird sie ersetzt, in der App blieb sie als
                    # Nachricht stehen.
                    continue
                self._said.add(n)
                self._shown.append(text)
                sq = self._emit({"kind": "say", "text": protocol._clip(text, protocol.MAX_TEXT)})
                if sq:
                    self._turn_says.append(sq)
                self.last_active = time.time()

    def _schon_gesagt(self, text):
        """Ob dieser Absatz schon im Feed steht - gleich, auf welchem Weg er
        hereinkam: vom Bildschirm, aus der Abschrift oder beim Neuladen.

        Stand als zwei Bedingungen mitten in der Schleife, jede mit ihrer
        eigenen Normalisierung. Hier ist es eine, und sie laesst sich von
        aussen pruefen (tests/markdown.py).

        Ein ganzer Absatz Wort fuer Wort noch einmal ist eine Wiederholung,
        nie etwas Neues: der Bildschirm ist unter dem Anker weggerutscht.
        Kurze ("Fertig.") duerfen dagegen zweimal kommen.
        """
        n = _kern(text)
        if n in {_kern(t) for t in self._shown}:
            return True                    # kam vor dem Bildschirm anders herein
        return len(n) >= 40 and n in self._said

    def _markdown_from_transcript(self, mid, texts):
        """The display hook hands over the text as Claude Code draws it: no
        ## before a heading, no fences, no | in a table. The transcript has
        the same message whole. Sent again, saying which cards it stands in
        for - so nothing has to be recognised by its first characters."""
        seqs = self._said_seq.pop(mid, None)
        raw = "\n\n".join((c.get("text") or "").strip() for c in texts).strip()
        if not seqs:
            # Zu dieser Nachricht gibt es gar keine Bildschirmkarte. Frueher
            # endete es hier - und damit fiel die ganze Nachricht weg, obwohl
            # sie vollstaendig vorlag. Das passiert, wenn ein langer Absatz
            # aus dem sichtbaren Fenster gescrollt ist, bevor der Bildschirm
            # gelesen wurde: uebrig blieb ein Schnipsel vom Ende, gemeldet von
            # Calvin am 25.09.
            #
            # Also selbst schicken - und sich so merken, wie es der Bildschirm
            # tun wuerde: kommt spaeter ein laengerer Stand derselben
            # Nachricht, ersetzt er diese Karte ueber den Weg unten, statt
            # daneben zu stehen.
            if not raw or self._schon_gesagt(raw):
                return
            self._said.add(_kern(raw))
            self._shown.append(raw)
            sq = self._emit({"kind": "say", "text": protocol._clip(raw, protocol.MAX_TEXT),
                             "message_id": mid})
            if sq:
                self._said_seq[mid] = [(sq, len(_kern(raw)))]
            self.text_log.append({"mid": (mid or "?")[:8], "nachgereicht": len(raw)})
            return
        if not raw or not _has_markup(raw):
            return                         # came out right as it was
        # The record can be written while the message is still growing. A
        # shorter text would take the whole answer away and leave a stump -
        # the end of it went missing that way, reported by Calvin.
        hatte = sum(n for _, n in seqs)
        if len(_kern(raw)) + 2 < hatte:
            self.text_log.append({"mid": (mid or "?")[:8], "kuerzer": hatte})
            self._said_seq[mid] = seqs     # a later, whole record may still come
            return
        seqs = [sq for sq, _ in seqs]
        self._said.add(_kern(raw))
        self._shown.append(raw)
        self._emit({"kind": "say", "text": protocol._clip(raw, protocol.MAX_TEXT),
                    "message_id": mid, "replaces": seqs})
        self.text_log.append({"mid": (mid or "?")[:8], "markdown": len(raw)})

    def _complete_from_transcript(self, texts):
        """The screen was read while a paragraph was still being drawn - the
        tool call right after it made the bridge look early, and the part
        went out as if whole ("... geteilt wird. Dann"). The transcript has
        the whole text. Sent again with the same beginning, longer: the
        phone replaces the part instead of showing both."""
        full = " ".join(" ".join(_plain_md(c.get("text") or "").split()) for c in texts).strip()
        if len(full) < 20:
            return
        # The transcript holds the markdown the screen drew away: headings,
        # fences, quotes, tables. Send it whole and say which of this turn's
        # cards it stands in for - then nothing has to be recognised by its
        # first characters, which stopped matching the moment the ** and the
        # # came back.
        raw = "\n\n".join((c.get("text") or "").strip() for c in texts).strip()
        # Only the cards since the record before this one: a turn can hold
        # several messages - text, a tool call, text again - and each record
        # carries one of them. Standing in for the whole turn would drop
        # everything the other messages said.
        says, self._turn_says = self._turn_says, []
        if says and raw and _has_markup(raw):
            shown = " ".join(" ".join(t.split()) for t in list(self._shown)[-len(says):])
            if len(full) >= len(shown) - 2:
                self._said.add(_kern(raw))
                self._shown.append(raw)
                self._emit({"kind": "say", "text": protocol._clip(raw, protocol.MAX_TEXT),
                            "replaces": list(says)})
                self.text_log.append({"t": round(time.time(), 2), "markdown": len(raw)})
                return
        # Nur der LETZTE gezeigte Absatz kann angeschnitten sein - was davor
        # steht, ist fertig. Vorher wurden die letzten vier durchsucht, und
        # bei zwei Absaetzen in einem Zug passte der ERSTE als Anfang des
        # Gesamttextes: daraus wurde "Absatz 1 + Absatz 2" als neue Karte.
        # Das Handy ersetzte damit Absatz 1, Absatz 2 blieb daneben stehen -
        # und stand zusaetzlich in der zusammengefassten Karte. Doppelt
        # gelesen, gemeldet von Calvin am 12.09.
        for text in list(self._shown)[-1:]:
            part = " ".join(text.split())
            if len(part) < 20 or not full.startswith(part) or len(full) <= len(part) + 3:
                continue
            whole = text.rstrip() + full[len(part):]
            n = _kern(whole)
            if n in self._said:
                return
            self._said.add(n)
            self._shown.append(whole)
            self._emit({"kind": "say", "text": protocol._clip(whole, protocol.MAX_TEXT)})
            self.text_log.append({"t": round(time.time(), 2), "completed": len(full) - len(part)})
            return

    def _note_activity(self, h):
        """What Claude is doing right now, from its working line - the word
        it shows for the turn and whether it thinks. Sent when that changes,
        not with every tick of its clock."""
        now = None
        if self.busy:
            for line in reversed(h.splitlines()[-40:]):
                m = _SPINNER.match(line)
                if m:
                    parts = m.group(2).lower()
                    now = (m.group(1), "think" in parts or "thought" in parts)
                    break
        if now and now != self._activity:
            self._emit({"kind": "activity", "verb": now[0], "thinking": now[1]})
        self._activity = now

    # ---------- on disk ----------

    def _feed_path(self):
        return os.path.join(FEEDS_DIR, self.claude_session_id + ".jsonl")

    def _store(self, entry):
        seq = super()._store(entry)
        if not owns_feeds():
            return seq                 # another bridge owns this folder
        # Where reading stood goes with every card, so a restart resumes
        # exactly here: transcript offset, screen anchor, history boundary.
        row = {"seq": seq, "entry": entry, "off": self._offset, "until": self.start_offset,
               "anchor": self._anchor, "anchor_n": self._anchor_n}
        try:
            os.makedirs(FEEDS_DIR, mode=0o700, exist_ok=True)
            # Whole conversations: readable by this user only.
            fd = os.open(self._feed_path(), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            self._persisted += 1
            if self._persisted > 2 * TERMINAL_RING:
                self._compact()
        except OSError:
            pass
        return seq

    def _compact(self):
        """Keep the file at what the ring holds."""
        path = self._feed_path()
        with open(path) as fh:
            lines = fh.readlines()[-TERMINAL_RING:]
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.writelines(lines)
        os.replace(path + ".tmp", path)
        self._persisted = len(lines)

    def _ascending(self, rows):
        """Only rows whose number grows, in the order they were written.

        A feed that two bridges wrote carries the same numbers twice, in
        their own order - and a ring built from that hands the app numbers
        that fall back, which it reads as a bridge that lost its record.
        What is dropped here was written by the other bridge, which saw the
        same session; the cards are the same ones. Said out loud, not
        swallowed, and the file is put right so the damage ends here.
        """
        clean, last = [], 0
        for r in rows:
            seq = r.get("seq")
            if not isinstance(seq, int) or seq <= last:
                continue
            clean.append(r)
            last = seq
        if len(clean) != len(rows):
            print(f"iris: {os.path.basename(self._feed_path())}: "
                  f"{len(rows) - len(clean)} von {len(rows)} Karten stammen "
                  "von einer zweiten Bridge - werden übersprungen.")
            if owns_feeds():
                self._rewrite(clean)
        return clean

    def _rewrite(self, rows):
        """Put the file back to what the ring holds - one writer, ascending."""
        path = self._feed_path()
        try:
            fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            os.replace(path + ".tmp", path)
            self._persisted = len(rows)
        except OSError:
            pass

    def _restore(self):
        """Bring back the feed of a session this bridge watched before."""
        try:
            with open(self._feed_path()) as fh:
                lines = fh.readlines()
        except OSError:
            return
        rows = []
        for line in lines[-TERMINAL_RING:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        rows = self._ascending(rows)
        if not rows:
            return
        self._ring = [(r["seq"], r["entry"]) for r in rows]
        self._seq = rows[-1]["seq"]
        self._persisted = len(lines)
        last = rows[-1]
        self.start_offset = min(rows[0].get("until") or 0, _size(self.transcript))
        self._offset = min(last.get("off") or self.start_offset, _size(self.transcript))
        self._anchor, self._anchor_n = last.get("anchor"), last.get("anchor_n") or 0
        for _, e in self._ring:
            raw = e.get("raw") or {}
            for c in raw.get("message", {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    self.acts += 1
            card = e.get("card") or {}
            if card.get("kind") == "artifacts":
                self.artifacts = {a["url"]: a for a in card.get("items") or [] if a.get("url")}
            if card.get("kind") == "say":
                self._shown.append((card.get("text") or "").strip())
                self._said.add(_kern(card.get("text")))
        self.turn_acts_start = self.acts

    def _queue_path(self):
        return os.path.join(FEEDS_DIR, self.claude_session_id + ".queue.json")

    def _save_queue(self):
        """What waits for this session, on disk: a restart of the bridge
        used to take the queue with it - messages gone without a word."""
        try:
            with self._qlock:
                waiting = list(self._queue)
            path = self._queue_path()
            if not waiting:
                if os.path.exists(path):
                    os.remove(path)
                return
            os.makedirs(FEEDS_DIR, mode=0o700, exist_ok=True)
            fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                json.dump(waiting, fh, ensure_ascii=False)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def _load_queue(self):
        try:
            with open(self._queue_path()) as fh:
                waiting = json.load(fh)
        except (OSError, ValueError):
            return
        if isinstance(waiting, list):
            with self._qlock:
                self._queue = [m for m in waiting if isinstance(m, str)] + self._queue

    def forget_feed(self):
        try:
            os.remove(self._feed_path())
        except OSError:
            pass

    def _check_interrupt(self, rec):
        """Esc at the terminal ends a turn without a Stop hook; the transcript
        is the only place that says so."""
        content = rec.get("message", {}).get("content")
        texts = [content] if isinstance(content, str) else [
            c.get("text") or "" for c in content or []
            if isinstance(c, dict) and c.get("type") == "text"]
        if self.busy and any(t.lstrip().startswith("[Request interrupted by user")
                             for t in texts):
            self.busy = False
            self.turn_started = None
            self._emit({"kind": "interrupted"})
            self.on_change(self)
            if not self._settling:         # stopped at the Mac, not by iris
                self._type_soon()

    def _queue_op(self, op, text):
        """Typed while Claude worked - at the Mac or from the phone: Claude
        Code queues it and takes it after the running step. Until then the
        app shows it greyed, as the terminal does; taken, it becomes a turn
        of its own."""
        n = _norm(text)
        if op == "enqueue":
            self._announced.append(n)
            del self._announced[:-50]
            self._emit({"kind": "pending", "text": protocol._clip(text, protocol.MAX_TEXT)})
        elif op in ("remove", "dequeue") and n in self._announced:
            self._take(n, text)

    def _take(self, n, text):
        """Once per waiting message, whichever record says so first: the
        queue's remove, or the queued command itself."""
        if n in self._taken:
            return
        self._taken.append(n)
        del self._taken[:-50]
        self._emit({"kind": "taken", "text": protocol._clip(text, protocol.MAX_TEXT)})

    def _was_announced(self, text):
        """Shown as waiting already - the record of it being taken is not a
        second message, only the sign that it was taken."""
        n = _norm(text)
        if n in self._announced:
            self._announced.remove(n)
            self._take(n, text)
            return True
        return False

    def _was_typed(self, text):
        n = _norm(text)
        for t in list(self._typed):
            if n and (t.startswith(n.rstrip(" …")) or n.startswith(t)):
                self._typed.remove(t)
                return True
        # Claude Code puts what was typed while it worked into one prompt,
        # and turns pasted image paths into "[Image #…]": several phone
        # messages then come back as one text that matches none of them.
        # It is theirs when what the phone typed makes up all of it.
        rest = _core(text)
        found = [t for t in self._typed if _core(t) and _core(t) in rest]
        for t in found:
            rest = rest.replace(_core(t), " ", 1)
        if found and not re.sub(r"[\W_]+", "", rest):
            for t in found:
                self._typed.remove(t)
            return True
        return False

    def _refresh_title(self):
        if not self.transcript:
            return
        project_id = os.path.basename(os.path.dirname(self.transcript))
        t = history.ai_title(project_id, self.claude_session_id)
        if t:
            self.title = t

    # ---------- hooks ----------

    def touch(self, payload):
        self.last_event = time.time()
        if payload.get("permission_mode"):
            self.permission_mode = payload["permission_mode"]
        if payload.get("cwd"):
            self.cwd = payload["cwd"]
        if payload.get("transcript_path") and not self.transcript:
            self.transcript = payload["transcript_path"]

    def on_prompt(self, payload):
        # A message typed while Claude works comes through here too - the
        # turn goes on, and so does its clock.
        if not self.busy or not self.turn_started:
            self.turn_started = time.time()
            self.turn_acts_start = self.acts
            self._turn_says = []
        self.busy = True
        self.last_active = time.time()
        if not self.title:
            self.title = " ".join((payload.get("prompt") or "").split())[:48]
        self._emit({"kind": "think"})
        if self.screen_source is None and self.tty:
            # Settle the text source before the turn's first sentence.
            self._sync_screen()
        # With a tab to type into, whatever waits is typed after this turn and
        # stands in the terminal; otherwise it rides along, unseen there.
        text = "" if self.typable() and not self.type_error else self._deliver("prompt")
        self.on_change(self)
        if not text:
            return None
        return {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "Zusätzlich kam über iris vom Handy:\n\n" + text}}

    def on_pre_tool(self, payload, away):
        tool = payload.get("tool_name") or "?"
        if tool == "AskUserQuestion":
            return self._on_question(payload, away)
        mode = payload.get("permission_mode") or self.permission_mode
        if not away or not needs_phone(tool, mode):
            return None
        return self._halten(payload, tool, _decision)

    def on_permission_request(self, payload, away):
        """Claude Code will eine Freigabe - hier faengt iris sie ab.

        Der Unterschied zu `on_pre_tool` ist genau einer, und er ist der
        Punkt der ganzen Sache: `needs_phone` wird nicht gefragt. Im
        Auto-Modus haelt iris sonst nichts (NO_HOLD_MODES), weil der
        Auto-Modus ja selbst entscheidet - er entscheidet aber nur *fast*
        alles selbst und bleibt stehen, wenn es ernst wird. Genau dann ging
        die Anfrage an iris vorbei und tauchte dort auf, wo Calvin sonst
        angemeldet ist. Dass dieses Ereignis feuert, heisst schon, dass ein
        Mensch gebraucht wird; da gibt es nichts mehr abzuwaegen.
        """
        tool = payload.get("tool_name") or "?"
        # Die Frage mit Antwortmoeglichkeiten laeuft ueber PreToolUse, und
        # iris' eigene Werkzeuge sind kein Fall fuer eine Freigabe.
        if tool == "AskUserQuestion" or tool.startswith("mcp__iris"):
            return None
        if not away:
            return None                 # am Mac zeigt der Dialog sie selbst
        return self._halten(payload, tool, _freigabe)

    def _halten(self, payload, tool, formen):
        """Eine Karte aufs Telefon und darauf warten - fuer beide Ereignisse.

        `formen` macht aus dem Urteil die Antwort, die das jeweilige Ereignis
        erwartet: PreToolUse und PermissionRequest sprechen nicht dieselbe
        Sprache, sonst ist der Ablauf derselbe.
        """
        tin = payload.get("tool_input") or {}
        rid = "t" + uuid.uuid4().hex[:11]
        card = {"kind": "ask", "request_id": rid, "tool": tool,
                "detail": protocol._describe_tool(tool, tin),
                "input": tin, "terminal": True,
                "change": protocol.change_summary(tool, tin)}
        slot = {"event": threading.Event(), "allow": None, "message": ""}
        self._slots[rid] = slot
        self._open_asks[rid] = card
        self._emit(card)
        # Held only while away, so it always goes to the phone.
        push.ask(self.title or self.label(), self.key, card, watched=False)
        self.last_active = time.time()
        self.on_change(self)

        answered = slot["event"].wait(HOLD_SECONDS)
        self._slots.pop(rid, None)
        self._open_asks.pop(rid, None)
        self.on_change(self)
        if not answered:
            # Same rule as iris' own approvals: no answer, nothing happens.
            self._emit({"kind": "answered", "request_id": rid, "allow": False,
                        "reason": "Keine Antwort"})
            push.settled(rid)
            return formen("deny", "Über iris kam innerhalb von 9½ Minuten "
                                  "keine Antwort - abgelehnt.")
        if slot["allow"] is None:
            # The bridge is going down. Hand the decision back to the
            # terminal's own dialog instead of deciding for anyone.
            return None
        if slot["allow"]:
            return formen("allow", "Über iris erlaubt")
        return formen("deny", slot["message"] or "Über iris abgelehnt")

    def _on_question(self, payload, away):
        """A question with options, answerable from the phone either way.

        Away: held here like an approval, and the answer goes back as
        updatedInput.answers - Claude carries on as if it had been answered
        at the terminal, and the terminal shows it that way. No answer in
        time: the question goes to the terminal's own dialog after all.
        At the Mac: the dialog shows as always, and the question stands on
        the phone as well; an answer from there is typed into the dialog.
        """
        tin = payload.get("tool_input") or {}
        rid = "q" + uuid.uuid4().hex[:11]
        card = {"kind": "ask", "request_id": rid, "tool": "AskUserQuestion",
                "detail": protocol._describe_tool("AskUserQuestion", tin),
                "input": tin, "terminal": True}
        self._open_asks[rid] = card
        self._question = {"rid": rid, "input": tin, "held": away}
        self._emit(card)
        if away:
            push.ask(self.title or self.label(), self.key, card, watched=False)
        self.last_active = time.time()
        self.on_change(self)
        if not away:
            return None
        slot = {"event": threading.Event(), "allow": None, "message": "", "answers": None}
        self._slots[rid] = slot
        answered = slot["event"].wait(HOLD_SECONDS)
        self._slots.pop(rid, None)
        if not answered or slot["allow"] is None:
            self._question["held"] = False     # the terminal dialog takes it
            return None
        self._open_asks.pop(rid, None)
        self._question = None
        self.on_change(self)
        if not slot["allow"]:
            return _decision("deny", slot["message"] or "Über iris abgelehnt")
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "allow",
            "permissionDecisionReason": "Über iris beantwortet",
            "updatedInput": dict(tin, answers=slot["answers"] or {})}}

    def _frage_verfallen(self, questions):
        """Steht der Dialog am Terminal nicht mehr - oder nie wieder?

        Ohne Tab kann iris ihn nie beantworten, also ist die Karte auch dann
        nichts mehr wert. Laesst sich der Bildschirm nicht lesen, wird nichts
        behauptet: dann gilt sie als offen, und es bleibt beim alten Weg.
        """
        if not self.typable():
            return True
        shown = typist.screen_now(self.tty)
        if shown is None:
            return False
        frage = (questions[0].get("question") or "") if questions else ""
        return not (frage and frage in shown and "Enter to select" in shown)

    def _frage_verwerfen(self):
        """Die veraltete Karte fallenlassen, auf dem Telefon wie in der App."""
        q = self._question
        rid = q["rid"] if q else ""
        self._question = None
        self._open_asks.pop(rid, None)
        self._emit({"kind": "answered", "request_id": rid, "allow": False,
                    "reason": "Die Frage steht am Rechner nicht mehr offen."})
        push.settled(rid)
        self.on_change(self)
        return False, "Die Frage war nicht mehr offen - Karte entfernt."

    def _answer_in_dialog(self, answers, allow):
        """Type the phone's answer into the question dialog at the terminal:
        the option's number, or "Type something" and then the text. Only
        while exactly that dialog is on screen - a "2" typed into the prompt
        would go out as a message."""
        q = self._question
        questions = (q["input"].get("questions") or []) if q else []
        # Steht die Frage ueberhaupt noch? Wenn nicht, ist die Karte veraltet
        # und muss weg - egal ob jemand sie erlauben oder ablehnen wollte.
        #
        # Bis zum 28.09. konnte man sie ueberhaupt nicht loswerden: Ablehnen
        # wurde gleich hier abgewiesen, und Erlauben scheiterte weiter unten
        # an "steht gerade nicht offen", ohne die Karte zu entfernen. Sie
        # stand dann fuer immer auf dem Telefon - gemeldet von Calvin, nachdem
        # ein Neustart der Bruecke eine Frage ueberholt hatte.
        if self._frage_verfallen(questions):
            return self._frage_verwerfen()
        if not allow:
            return False, "Ablehnen geht bei einer Frage am Terminal nicht – dort mit Esc."
        if len(questions) != 1 or questions[0].get("multiSelect"):
            return False, "Mehrere Fragen oder Mehrfachauswahl: bitte am Rechner beantworten."
        if not self.typable():
            return False, "In diese Sitzung kann iris nicht tippen (kein Terminal.app, keine Windows-Konsole)."
        question = questions[0]
        shown = typist.screen_now(self.tty) or ""
        if question.get("question", "") not in shown or "Enter to select" not in shown:
            return False, "Die Frage steht am Rechner gerade nicht offen."
        pick = (answers or {}).get(question.get("question")) or ""
        labels = [o.get("label") for o in question.get("options") or []]
        if pick in labels:
            ok = typist._run(self.tty, str(labels.index(pick) + 1), "raw") == "ok"
        else:
            # Free text: "Type something" follows the options.
            ok = typist._run(self.tty, str(len(labels) + 1), "raw") == "ok"
            time.sleep(0.8)
            ok = ok and typist.type_into(self.tty, pick) == "ok"
        return (True, "") if ok else (False, "Eintippen ging nicht.")

    def on_post_tool(self, payload):
        if payload.get("tool_name") == "AskUserQuestion" and self._question:
            # Answered - at the terminal, or from the phone. The phone learns
            # what was picked, and the question leaves it.
            rid = self._question["rid"]
            resp = payload.get("tool_response")
            answers = resp.get("answers") if isinstance(resp, dict) else None
            answers = answers or (payload.get("tool_input") or {}).get("answers")
            self._question = None
            if self._open_asks.pop(rid, None) is not None:
                card = {"kind": "answered", "request_id": rid, "allow": True}
                if isinstance(answers, dict):
                    card["answers"] = answers
                self._emit(card)
                push.settled(rid)
                self.on_change(self)
        tu, ms = payload.get("tool_use_id"), payload.get("duration_ms")
        if tu and ms is not None:
            self._emit({"kind": "timing", "tool_use_id": tu,
                        "duration_ms": ms})
        # Sent to the background - asked for, or pushed there with Ctrl+B
        # while it ran. Either way it keeps running after this call returned.
        ti = payload.get("tool_input") or {}
        tid = _background_id(payload.get("tool_response"))
        if ti.get("run_in_background") or tid:
            tid = tid or tu or uuid.uuid4().hex[:8]
            self.background[tid] = {
                "id": tid, "type": "shell", "status": "running",
                "description": ti.get("description") or "",
                "command": ti.get("command") or "", "since": time.time()}
            self._background_changed()

    # ---------- text as it appears ----------

    def on_text(self, payload):
        mid = payload.get("message_id") or "?"
        if self.screen_source:
            # The terminal is the source here; this would only repeat it.
            self.text_log.append({"mid": mid[:8], "flush": "Bildschirm ist Quelle"})
            return
        self.display_seen = True
        self.text_log.append({"t": round(time.time(), 2), "mid": mid[:8],
                              "index": payload.get("index"), "final": payload.get("final"),
                              "turn": (payload.get("turn_id") or "")[:8],
                              "len": len(payload.get("delta") or "")})
        with self._tlock:
            self._texts.setdefault(mid, {})[int(payload.get("index") or 0)] = payload.get("delta") or ""
        if payload.get("final"):
            threading.Timer(SETTLE_SECONDS, self._flush_text, args=(mid,)).start()

    def _flush_text(self, mid):
        with self._tlock:
            parts = self._texts.pop(mid, None)
        if not parts:
            return
        text = "".join(parts[i] for i in sorted(parts)).strip()
        if text in self._shown:
            self.text_log.append({"mid": mid[:8], "flush": "schon gezeigt", "head": text[:40]})
            return                         # already on screen from the transcript
        self.text_log.append({"mid": mid[:8], "flush": "gezeigt" if text else "leer",
                              "head": text[:40]})
        self._shown.append(text)
        if text:
            sq = self._emit({"kind": "say", "text": protocol._clip(text, protocol.MAX_TEXT),
                             "message_id": mid})
            if sq:
                # With its length: a card is only ever replaced by one that
                # holds at least as much.
                self._said_seq.setdefault(mid, []).append(
                    (sq, len(" ".join(_plain_md(text).split()))))
            self.last_active = time.time()

    # ---------- in the background ----------

    def on_subagent(self, payload, started):
        aid = payload.get("agent_id")
        if not aid:
            return
        if started:
            self.background[aid] = {"id": aid, "type": "agent", "status": "running",
                                    "description": payload.get("agent_type") or "Agent",
                                    "command": "", "since": time.time()}
        else:
            self.background.pop(aid, None)
        self._background_changed()

    def _artifacts_changed(self):
        """The pages this session published, newest first - to open from
        the phone. A page published again moves up."""
        items = sorted(self.artifacts.values(), key=lambda a: -(a.get("ts") or 0))
        self._emit({"kind": "artifacts", "items": items})

    def _read_artifacts(self):
        """Pages published before the bridge watched: once, from the
        transcript up to where the live reading starts."""
        self._artifacts_read = True
        found = history.artifacts(self.transcript, until=self._offset)
        if found and {u: a.get("title") for u, a in found.items()} != \
                {u: a.get("title") for u, a in self.artifacts.items()}:
            self.artifacts = {**found, **self.artifacts}
            self._artifacts_changed()

    def _background_changed(self):
        self._emit({"kind": "background", "tasks": list(self.background.values())})
        self.on_change(self)

    def on_stop(self, payload):
        if self.tty:
            # The last words of the turn are on screen now; one more look a
            # moment later catches a line still being drawn.
            self._sync_screen()
            threading.Timer(0.8, self._sync_screen).start()
        for mid in list(self._texts):
            self._flush_text(mid)          # whatever never got its last piece
        # A session that sends no display text (started before that hook
        # existed) and whose transcript skipped the answer still has this:
        # the last thing Claude said in the turn.
        last = (payload.get("last_assistant_message") or "").strip()
        if last and not self.display_seen and not self.screen_source \
                and last not in self._shown:
            self._shown.append(last)
            self._emit({"kind": "say", "text": protocol._clip(last, protocol.MAX_TEXT)})
        # The list at the end of a turn is what is really still running.
        tasks = payload.get("background_tasks")
        if isinstance(tasks, list):
            now = time.time()
            known = self.background
            self.background = {
                str(t.get("id")): {
                    "id": str(t.get("id")), "type": t.get("type") or "shell",
                    "status": t.get("status") or "running",
                    "description": t.get("description") or "",
                    "command": t.get("command") or "",
                    "since": known.get(str(t.get("id")), {}).get("since", now)}
                for t in tasks if isinstance(t, dict) and t.get("id")
                and (t.get("status") or "running") in ("running", "pending")
                and not _only_watches(t)}
            self._background_changed()
        typed_later = bool(self._queue) and self.typable()
        text = "" if typed_later else self._deliver("stop")
        if text:
            # Claude carries on with this as its next instruction. The turn
            # is not over, so no 'done' yet.
            self.on_change(self)
            return {"decision": "block",
                    "reason": "Nachricht über iris vom Handy:\n\n" + text}
        ms = int((time.time() - self.turn_started) * 1000) \
            if self.turn_started else None
        self.busy = False
        self.turn_started = None
        self.last_active = time.time()
        self._emit({"kind": "done", "stop_reason": "end_turn",
                    "duration_ms": ms})
        # Endet der Zug mit einer Frage, ist das keine Fertigmeldung, sondern
        # eine Bitte um Antwort - und die geht ohne Mindestdauer raus. Im
        # Auto-Modus ist das der haeufigste Fall: keine Freigabe noetig, die
        # Aufgabe ist abgearbeitet, und die letzte Zeile will etwas von dir.
        zuletzt = self._shown[-1] if self._shown else ""
        # Haengt eine Wache an dieser Sitzung, ist ihr Vorarbeiter jetzt dran.
        wachen.nach_zug(self.key, zuletzt)
        if push._endet_mit_frage(zuletzt):
            push.wartet(self.title or self.label(), self.key, zuletzt, watched=True)
        else:
            # Whoever sits at the terminal saw it end; only away needs a note.
            push.done(self.title or self.label(), self.key, (ms or 0) / 1000,
                      self.acts - self.turn_acts_start, watched=True,
                      text=zuletzt)
        self._refresh_title()
        self.on_change(self)
        if typed_later:
            self._type_soon()
        return None

    def on_end(self, payload):
        self.exited = True
        self.busy = False
        self.exit_reason = {"clear": "mit /clear geleert",
                            "logout": "abgemeldet"}.get(
            payload.get("reason"), "am Terminal beendet")
        self.release_all()
        self._emit({"kind": "closed", "reason": self.exit_reason})
        self.on_change(self)

    # ---------- from the phone ----------

    def send(self, text, attachments=None):
        """Take a message from the phone.

        Typed into the terminal tab at once if the session sits at its
        prompt; typed right after the turn if Claude is working. Without a
        tab to type into it waits for the end of the turn or the next prompt
        typed at the Mac. Attachments go by path - Claude reads them itself.
        """
        if self.exited:
            return False, "Sitzung ist beendet"
        attachments = attachments or []
        # Claude Code's own record knows better than what the hooks left us
        # with - a Stop missed over a restart, a turn begun before it.
        status = typist.status(self.claude_session_id)
        if self.busy and status == "idle":
            self.busy = False
            self.turn_started = None
        elif not self.busy and status == "busy":
            self.busy = True
            self.turn_started = self.turn_started or time.time()
        with self._qlock:
            self._queue.append("\n\n".join(t for t in (text, uploads.mention(attachments)) if t))
        typable = self.typable()
        # now: typed this instant · turn: when the running turn ends ·
        # prompt: with the next prompt typed at the Mac
        # Typed at once, also while Claude works: Claude Code takes what is
        # typed during a turn after the step it is on - the same as typing at
        # the Mac, or the Claude app. Waiting for the end of the turn left
        # messages hanging for hours in a long one.
        delivery = "turn" if self._settling or (self.busy and not typable) \
            else "now" if typable else "prompt"
        card = {"kind": "queued", "text": text, "busy": self.busy,
                "delivery": delivery}
        if attachments:
            card["attachments"] = [uploads.describe(p) for p in attachments]
        self._emit(card)
        self.last_active = time.time()
        self._save_queue()
        if delivery == "now":
            self._type_queue()
        self.on_change(self)
        return True, ""

    def waiting(self):
        return len(self._queue)

    def queued_note(self):
        """Says what happens with a message that was not typed at once -
        what is true, not what would be convenient."""
        if not self._queue:
            return "Im Terminal eingegeben."
        if self._settling:
            return "Der Zug wird gerade angehalten. Die Nachricht kommt direkt danach dran."
        if self.busy:
            return ("Am Terminal ist gerade ein Dialog offen – die Nachricht wird "
                    "eingetippt, sobald er zu ist." if self.typable() else
                    "Claude arbeitet noch. Die Nachricht geht am Ende dieses Zugs mit.")
        if self.type_error:
            return (f"Eintippen ging nicht: {self.type_error}. Die Nachricht geht "
                    "mit der nächsten Eingabe am Rechner mit.")
        return ("In diese Sitzung kann iris nicht tippen (kein Terminal.app, keine "
                "Windows-Konsole). Die Nachricht geht mit der nächsten Eingabe am Rechner mit.")

    # ---------- typing into the tab ----------

    def locate(self, ppid):
        """Find the claude process and tab from a hook's parent."""
        found = typist.find_claude(int(ppid))
        tty = found[1] if found else None
        if tty != self.tty:
            self.screen_source = None      # another tab: look again
        self.pid, self.tty = found if found else (None, None)

    def typable(self):
        """Can a message be typed into this session's tab right now?"""
        if self.exited:
            return False
        if self.pid and self.tty and typist.alive(self.pid, self.tty):
            return True
        found = typist.by_session(self.claude_session_id)
        self.pid, self.tty = found if found else (None, None)
        return bool(found)

    def _dialog_open(self):
        """A dialog at the terminal - an approval, a question - would take
        typed text as its answer. Then the message waits a moment."""
        shown = typist.screen_now(self.tty) or ""
        return ("Enter to select" in shown or "Do you want to" in shown
                or re.search(r"^\s*❯ 1\. ", shown, re.M) is not None)

    def _type_queue(self):
        with self._type_lock:
            if self.busy and self._dialog_open():
                threading.Timer(2.0, self._type_queue).start()
                return
            if self.tty and self._view_open():
                # A view is open in the tab (/status, /config ...): typed text
                # would land in it and never be sent. What waits goes once it
                # is closed - by Esc from the phone or at the Mac.
                with self._qlock:
                    waiting = bool(self._queue)
                if waiting:
                    self._note_view(True)
                return
            with self._qlock:
                msgs, self._queue = self._queue, []
            self._save_queue()
            if not msgs:
                return
            text = "\n\n".join(msgs)
            why = typist.type_into(self.tty, text) if self.tty else "kein Tab bekannt"
            if why != "ok":
                with self._qlock:
                    self._queue = msgs + self._queue
                self._save_queue()
                self.type_error = why
                self._emit({"kind": "error", "text": "Nicht eingetippt: " + why})
                self.on_change(self)
                return
            self.type_error = ""
            self._typed.append(_norm(typist.clean(text)))
            # An attachment changes what "sent" means, so the check has to
            # know. Read back off the text rather than carried alongside:
            # the queue is saved to disk as plain lines, and a second field
            # would have to survive a restart for no gain.
            anhang = bool(re.search(r"(?m)^Anhang: ", text))
            threading.Thread(target=self._confirm_typed,
                             args=(len(msgs), self.busy, anhang),
                             daemon=True).start()

    def _confirm_typed(self, count, during_turn=False, mit_anhang=False):
        """Typed is not sent. A pasted image path becomes an attachment in
        Claude Code and the Return that followed is lost; the text then just
        sits in the input. So: sent is when the turn began or the input is
        empty - otherwise one more Return, and if that does not do it either,
        say so instead of claiming it arrived."""
        if during_turn and not mit_anhang:
            # Mid-turn, Claude Code queues what is typed and takes it after
            # the step it is on; until then it stands in the input. That is
            # delivered - pressing Return again, or warning, would be wrong.
            self._emit({"kind": "delivered", "count": count, "via": "terminal"})
            self.on_change(self)
            return

        if mit_anhang:
            # Erst abwarten, dass das Eingefuegte ueberhaupt dasteht.
            #
            # Ohne das war die Pruefung ein Wettlauf, und sie verlor ihn: Die
            # leere Eingabe unmittelbar nach dem Tippen heisst nicht
            # "abgeschickt", sondern "noch nicht angekommen". Am 23.09. stand
            # deshalb um 12:03:16 ein "queued" und in derselben Sekunde ein
            # "delivered" - und die Nachricht stand trotzdem noch im Terminal.
            # Die zehn Nachdruecker darunter kamen nie zum Zug.
            #
            # Steht nach dieser Frist nichts da, war es wirklich sofort weg.
            bis = time.time() + ANHANG_ANKUNFT
            angekommen = False
            while time.time() < bis:
                if not typist.input_empty(typist.screen_now(self.tty) or ""):
                    angekommen = True
                    break
                if self.busy and self._view_open():
                    break
                time.sleep(ANHANG_TAKT)
            if not angekommen:
                self._emit({"kind": "delivered", "count": count, "via": "terminal"})
                self.on_change(self)
                return

        def sent():
            # With an attachment the running turn says nothing: the paste
            # became a chip and ate the Return, so Claude Code queued
            # nothing at all. Only the input line tells the truth, and it
            # empties on a real send whether a turn runs or not. Without an
            # attachment the old rule stands, so a mid-turn message is not
            # pressed at a second time.
            if not mit_anhang and (self.busy
                                   or typist.status(self.claude_session_id) == "busy"):
                return True
            return typist.input_empty(typist.screen_now(self.tty) or "")
        # Zweimal drücken reichte nicht. Claude Code liest das Bild ein und
        # macht eine Kachel daraus, und ein 5-MB-Foto braucht dafür länger
        # als die sechs Sekunden, die hier einmal vorgesehen waren - der
        # Return kam an, nur zu früh, und Calvin musste am Rechner selbst
        # drücken. Also weiter nachfassen statt schneller: alle drei
        # Sekunden, solange der Text noch in der Eingabe steht.
        versuche = ANHANG_VERSUCHE if mit_anhang else 2
        for attempt in range(versuche):
            end = time.time() + ANHANG_FENSTER
            while time.time() < end:
                if sent():
                    self._emit({"kind": "delivered", "count": count, "via": "terminal"})
                    self.on_change(self)
                    return
                if self._view_open():
                    # What was typed opened a view (/status ...): it was sent.
                    # Another Return now would pick something in it.
                    self._emit({"kind": "delivered", "count": count, "via": "terminal"})
                    self._note_view(True)
                    return
                time.sleep(ANHANG_TAKT)
            if attempt < versuche - 1:
                # Nur der Return. Trifft er eine leere Eingabe, tut er
                # nichts - deshalb ist mehrfaches Nachfassen harmlos.
                typist._run(self.tty, "", "raw")
        self._emit({"kind": "error", "text": "Eingetippt, aber nicht abgeschickt – die "
                    "Nachricht steht am Rechner noch in der Eingabe."})
        self.on_change(self)

    def _type_soon(self):
        if self._queue and self.typable():
            threading.Timer(TYPE_AFTER_STOP, self._type_queue).start()

    def _deliver(self, via):
        with self._qlock:
            msgs, self._queue = self._queue, []
        self._save_queue()
        if not msgs:
            return ""
        self._emit({"kind": "delivered", "count": len(msgs), "via": via})
        return "\n\n".join(msgs)

    def answer_permission(self, req_id, allow, message="", answers=None):
        slot = self._slots.get(req_id)
        q = self._question
        if not slot and q and q["rid"] == req_id and not q["held"]:
            return self._answer_in_dialog(answers, allow)
        if not slot or slot["event"].is_set():
            return False, "Anfrage nicht mehr offen"
        slot["allow"] = bool(allow)
        slot["message"] = message or ""
        slot["answers"] = answers
        slot["event"].set()
        self._emit({"kind": "answered", "request_id": req_id,
                    "allow": bool(allow)})
        push.settled(req_id)
        self.last_active = time.time()
        return True, ""

    def release_all(self):
        for slot in list(self._slots.values()):
            slot["allow"] = None
            slot["event"].set()

    def label(self):
        return os.path.basename(self.cwd.rstrip("/")) or "Terminal"

    def open_asks(self):
        return list(self._open_asks.values())

    # What the control channel would answer for a hosted session. A terminal
    # session has none, so these say so instead of pretending.

    def context_usage(self):
        # No control channel, but the transcript says what each answer was
        # sent with - that is the context in use.
        n = self.context_tokens
        if not n:
            return None, NOT_POSSIBLE
        w = history.context_window(n)
        return {"totalTokens": n, "maxTokens": w, "percentage": round(100 * n / w, 1)}, ""

    def _on_limit(self, window, resets_at):
        """A limit is used up: Claude answers nothing until it resets. Said
        in the conversation and pushed - from afar it would look like a hang."""
        usage.hit(window, resets_at, self.title or self.label(), self.key)
        self._emit({"kind": "error", "text": usage.message(window, resets_at)})
        self._emit(usage.cards())
        self.on_change(self)

    def on_statusline(self, payload):
        """What Claude Code hands its status line: the plan's limits and the
        exact context in use."""
        cw = payload.get("context_window") or {}
        pct = cw.get("used_percentage")
        if isinstance(pct, (int, float)):
            frac = round(min(max(pct / 100, 0), 1), 4)
            if frac != self.context_line:
                self.context_line = frac
                self.on_change(self)
        if usage.report(payload.get("rate_limits")):
            self._emit(usage.cards())

    def _context(self):
        if self.context_line is not None:
            return self.context_line
        n = self.context_tokens
        return round(min(n / history.context_window(n), 1.0), 4) if n else None

    def capabilities(self):
        return None, NOT_POSSIBLE

    def set_permission_mode(self, mode):
        """Switch the mode as Shift+Tab at the Mac would, reading the status
        line after every step - at most one round through the modes. Only
        at an empty input while Claude is not working: every keystroke
        brings a Return along, which would send whatever stands there."""
        want = "default" if mode in ("manual", "default") else mode
        if want not in ("default", "acceptEdits", "plan", "auto", "bypassPermissions", "dontAsk"):
            return False, f"Unbekannter Modus: {mode}"
        if not self.typable():
            return False, "In diese Sitzung kann iris nicht tippen – den Modus stellt, wer dort sitzt."
        if typist.status(self.claude_session_id) == "busy":
            return False, "Claude arbeitet gerade. Den Modus nach diesem Zug umstellen."
        text = typist.screen_now(self.tty)
        if not typist.input_empty(text):
            return False, ("Am Rechner steht etwas in der Eingabe – ein Entwurf oder ein grauer "
                           "Vorschlag von Claude. Umgestellt wird nur bei leerer Eingabe, sonst "
                           "würde das mitgeschickte Return sie abschicken.")
        for _ in range(7):
            now = typist.mode_on_screen(text)
            if now == want:
                self.permission_mode = want
                self._emit({"kind": "mode", "mode": want})
                self.on_change(self)
                return True, ""
            if typist.shift_tab(self.tty) != "ok":
                break
            time.sleep(0.5)
            text = typist.screen_now(self.tty)
        now = typist.mode_on_screen(text)
        if now:
            self.permission_mode = now
            self.on_change(self)
        return False, f"{MODE_LABELS.get(want, want)} ist in dieser Sitzung nicht wählbar."

    # Views a command opens in the terminal (/status, /config, a list): the
    # phone sees the screen and has the keys that work through `do script` -
    # Esc, Return, and words with a Return. Arrow keys do not: each would
    # come with a Return, and in a list that picks.
    VIEW_MARKS = ("esc to cancel", "esc to close", "esc to exit", "esc to go back",
                  "enter to select", "enter to confirm")

    def _view_open(self):
        shown = (typist.screen_now(self.tty) or "").lower() if self.tty else ""
        return any(m in shown for m in self.VIEW_MARKS)

    def _note_view(self, is_open):
        """Tell the phone a view in the tab holds what it sends - and when it
        is gone, closed at the Mac or by Esc from the phone."""
        if is_open == self._view_shown:
            return
        self._view_shown = is_open
        self._emit({"kind": "view", "open": is_open})
        self.on_change(self)
        if is_open:
            threading.Thread(target=self._watch_view, daemon=True).start()

    def _watch_view(self):
        while self._view_shown and not self.exited:
            time.sleep(2)
            if not self._view_open():
                self._note_view(False)
                self._type_soon()          # what waited behind it goes now
                return

    def screen_view(self):
        """What the tab shows right now, and whether a view is open."""
        if not self.tty or not self.typable():
            return None
        text = typist.screen_now(self.tty)
        if text is None:
            return None
        low = text.lower()
        return {"text": text, "view": any(m in low for m in self.VIEW_MARKS)}

    def press(self, key="", text=""):
        """A key for a view in the tab: esc, enter - or words and a Return."""
        if not self.typable():
            return False, "Kein Tab, in den iris tippen kann"
        if key == "esc":
            r = typist.escape(self.tty)
            # A view with a search field takes the first Esc to clear what
            # was typed into it; the next closes it. Sent again only while
            # the view is still open, and a moment later - a second Esc at an
            # empty prompt, right after the first, would open the rewind menu.
            for _ in range(2):
                if r != "ok":
                    break
                time.sleep(1.2)
                if not self._view_open():
                    break
                r = typist.escape(self.tty)
        elif key == "enter":
            r = typist.enter(self.tty)
        elif key == "background":
            # Only while something runs: at an idle prompt Ctrl+B does
            # nothing, and the phone would be told it worked.
            if not self.busy:
                return False, "Gerade läuft nichts"
            r = typist.background(self.tty)
        elif text.strip():
            r = typist.type_into(self.tty, text.strip())
        else:
            return False, "keine Taste"
        self.last_active = time.time()
        # Kept for /api/hooks/stats: whether a key from the phone arrived and
        # what the tab answered - requests themselves are not logged.
        self.text_log.append({"t": round(time.time(), 2), "key": key or "text", "result": r})
        if r == "ok" and key == "esc":
            self._type_soon()              # what waited behind the view can go now
        return r == "ok", ("" if r == "ok" else r)

    def interrupt(self):
        """Stop the running turn, as Ctrl+C at the Mac would. Only while
        Claude Code itself says the session is busy, and never twice within
        a few seconds: a Ctrl+C that reached an idle prompt would arm quitting,
        and the next one would end the session."""
        now = time.time()
        if now - self._interrupted_at < INTERRUPT_GAP:
            return False, "Gerade eben schon angehalten – einen Moment warten."
        # Die Statuszeile im Terminal, nicht das busy der Bruecke: die beiden
        # koennen auseinanderlaufen, und hier zaehlt, was am Rechner steht.
        # Ein Ctrl+C an einem Prompt, der nicht arbeitet, schaltet das Beenden
        # scharf - deshalb die strengere Quelle, auch wenn die App schon
        # "arbeitet" anzeigt.
        if typist.status(self.claude_session_id) != "busy":
            return False, "Claude arbeitet dort gerade nicht – es ist nichts anzuhalten."
        if not self.typable():
            return False, ("In diese Sitzung kann iris nicht tippen – angehalten wird, "
                           "wo jemand sitzt.")
        self._interrupted_at = now
        self._settling = True
        grund = typist.interrupt(self.tty)
        if grund != "ok":
            self._settling = False
            return False, grund
        threading.Thread(target=self._after_interrupt, daemon=True).start()
        return True, ""

    def _after_interrupt(self):
        """Claude puts a stopped request back into the input, at times - what
        is typed next would be glued to it. Once the turn is over, one more
        Ctrl+C empties the input. (At an input that is empty already it only
        arms quitting, which lapses by itself; nothing sends a third.) Only
        then goes what the phone sent meanwhile."""
        try:
            end = time.time() + 10
            while typist.status(self.claude_session_id) != "idle":
                if time.time() > end:
                    return
                time.sleep(0.3)
            time.sleep(0.5)
            typist.interrupt(self.tty)
            time.sleep(0.8)
        finally:
            self._settling = False
        self._type_queue()

    # ---------- view ----------

    def describe(self):
        return {
            "key": self.key,
            "cwd": self.cwd,
            "label": os.path.basename(self.cwd.rstrip("/")) or self.cwd,
            # A name given from the phone or the Mac wins over the made-up one.
            "title": names.get(self) or self.title,
            "claude_session_id": self.claude_session_id,
            "model": None,
            "permission_mode": self.permission_mode,
            "permission_label": MODE_LABELS.get(self.permission_mode,
                                                self.permission_mode),
            "profile": None,
            "resume": None,
            "fork": False,
            "busy": self.busy,
            # When the turn began - an app opened mid-turn shows the real
            # running time, not the time since it opened.
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
            "terminal": True,
            "queued": len(self._queue),
            "typable": bool(self.tty),
            "acts": self.acts,
            "failed": self.failed,
            "background": len(self.background),
            "context": self._context(),
        }


def _has_markup(text):
    """Whether a text carries anything the screen would have drawn away. A
    plain paragraph is already right as it came and is not sent twice."""
    return re.search(r"(?m)^\s*(#{1,6} |```|> |\||[-*] |\d+\. )|\*\*|`", text) is not None


def _plain_md(text):
    """Markdown as the terminal draws it: no ** or backticks, no # before a
    heading - so a screen text can be found at the start of the transcript's."""
    text = re.sub(r"\*\*|__|`", "", text)
    return re.sub(r"^#{1,6}\s*", "", text, flags=re.M)


def _kern(text):
    """Woran zwei Fassungen desselben Absatzes als derselbe zu erkennen sind:
    ohne Markdown, ohne die Zeilenumbrueche der Terminalbreite.

    Verglichen wurde vorher an drei Stellen mit drei Normalisierungen - der
    Bildschirm ohne Markdown (er hat keins), die Abschrift mit _plain_md, und
    der neu geladene Feed roh, also mit Backticks und Sternen. Nach einem
    Neuladen erkannte die Bruecke ihren eigenen Absatz deshalb nicht wieder
    und schickte ihn ein zweites Mal: in der App stand dieselbe Antwort
    zweimal, einmal gesetzt und einmal roh. Gemeldet von Calvin am 25.09.
    """
    return " ".join(_plain_md(text or "").split())


class Registry:
    """All terminal sessions the hooks have told us about."""

    def __init__(self, on_change=None):
        self.sessions = {}                 # key -> TerminalSession
        self._by_sid = {}
        self._lock = threading.Lock()
        self.on_change = on_change or (lambda s: None)
        self.away = _load_away()
        # Say at start-up who owns the feeds, not at the first card that
        # goes missing.
        owns_feeds()
        self._saved = self._load_saved()
        # Which hook events arrive, and from which session - when something
        # does not show up, this says whether it was never sent.
        self.stats = {}
        self._discovered = 0.0
        self.discover(force=True)

    # ---------- every running session, not only the talkative ones ----------

    def discover(self, force=False):
        """Every interactive claude running on this Mac, from Claude Code's
        own records: also the ones sitting idle that have not sent a single
        hook since the bridge started - which, before this, were missing.
        And a session whose process is gone without a SessionEnd (the window
        was closed) is closed here."""
        now = time.time()
        if not force and now - self._discovered < DISCOVER_EVERY:
            return
        self._discovered = now
        live = typist.running()
        changed = False
        for sid, d in live.items():
            pid = d.get("pid")
            if not isinstance(pid, int) or not typist.is_claude(pid):
                continue                   # a record left behind by a crash
            if SHOW_TESTS != (d.get("cwd") or "").startswith(TEST_ROOT):
                continue
            with self._lock:
                s = self._by_sid.get(sid)
                if s is None:
                    path = history.find_transcript(sid) or ""
                    s = TerminalSession(sid, d.get("cwd"), path, self.on_change)
                    started = (d.get("startedAt") or 0) / 1000
                    s.created = started or s.created
                    s.last_active = s.last_event = (
                        os.path.getmtime(path) if path else started or now)
                    s.busy = d.get("status") == "busy"
                    self._by_sid[sid] = s
                    self.sessions[s.key] = s
                    changed = True
            if not s.pid:
                found = typist.by_session(sid)
                if found:
                    s.pid, s.tty = found
                    changed = True
            if s._queue and not s._settling and s.typable():
                # Something waits and the tab is there: never let it hang -
                # after a restart, after a dialog, after a failed try.
                threading.Thread(target=s._type_queue, daemon=True).start()
            if s.tty and s.screen_source is None:
                # Off the caller's path: at start-up this runs for every
                # session, and each look at a tab takes a fifth of a second.
                threading.Thread(target=s._sync_screen, daemon=True).start()
            if s.exited:
                s.exited = False
                changed = True
            if s.busy and d.get("status") == "idle" and now - s.last_event > 3:
                # The turn ended and no Stop reached us - Esc, a bridge
                # restart in between, or a session without hooks. Its last
                # words are on screen by now.
                s.busy = False
                s.turn_started = None
                s.on_change(s)
                if s.tty:
                    threading.Thread(target=s._sync_screen, daemon=True).start()
            elif not s.busy and d.get("status") == "busy":
                # A turn that began before the bridge (re)started: no prompt
                # hook told us. Typing into it at once would be wrong.
                s.busy = True
                s.turn_started = s.turn_started or now
                s.on_change(s)
        for s in list(self.sessions.values()):
            if s.exited or s.claude_session_id in live:
                continue
            # Its process is gone (the window was closed), or - remembered
            # from before a restart, without a pid - it has neither a running
            # process nor said anything for a while.
            gone = (not typist.is_claude(s.pid)) if s.pid else now - s.last_event > GONE_AFTER
            if gone:
                s.on_end({"reason": "gone"})
                s.exit_reason = "läuft nicht mehr"
                changed = True
        if changed:
            self.save()

    # ---------- surviving a restart ----------

    def _load_saved(self):
        """Bring back what the last bridge knew. Sessions that ended stay
        ended; ones silent for longer than REVIVE_WITHIN are left behind."""
        try:
            with open(STATE_PATH) as fh:
                rows = {r["sid"]: r for r in json.load(fh) if r.get("sid")}
        except (OSError, ValueError, KeyError, TypeError):
            return {}
        now = time.time()
        for sid, r in rows.items():
            if not r.get("exited") and now - r.get("last_event", 0) < REVIVE_WITHIN:
                self._revive(sid, r)
        return rows

    def _revive(self, sid, row):
        # Auch hier, nicht nur beim Anlegen: ein Fork, der vor diesem Riegel
        # entstanden ist, stand sonst weiter in der Liste. Die Aufraeumfrist
        # von zwei Minuten fasst ihn nicht - solange der Agent laeuft,
        # schickt er Hooks, und jeder frischt die Sitzung wieder auf.
        if _ist_fork(row.get("transcript")):
            return None
        s = TerminalSession(sid, row.get("cwd"), row.get("transcript"), self.on_change)
        s.title = row.get("title") or s.title
        s.permission_mode = row.get("mode") or s.permission_mode
        s.last_event = row.get("last_event") or s.last_event
        s.exited = bool(row.get("exited"))
        s.pid, s.tty = row.get("pid"), row.get("tty")
        self._by_sid[sid] = s
        self.sessions[s.key] = s
        return s

    def save(self):
        rows = [{"sid": s.claude_session_id, "cwd": s.cwd, "transcript": s.transcript,
                 "title": s.title, "mode": s.permission_mode,
                 "last_event": s.last_event, "exited": s.exited,
                 "pid": s.pid, "tty": s.tty}
                for s in list(self.sessions.values())]
        try:
            os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(rows, fh)
            os.replace(tmp, STATE_PATH)
        except OSError:
            pass

    def set_away(self, on):
        self.away = bool(on)
        _save_away(self.away)
        return self.away

    def _session(self, payload, create):
        sid = payload.get("session_id")
        if not sid:
            return None
        created = False
        with self._lock:
            s = self._by_sid.get(sid)
            if s is None and create:
                # Ein Agent aus /fork bekommt keine eigene Sitzung. Er
                # gehoert zu der, die ihn gestartet hat, und steht dort
                # ueber SubagentStart in den Hintergrundaufgaben.
                if _ist_fork(payload.get("transcript_path")):
                    return None
                # Created on the first event of any kind, not only on
                # SessionStart: sessions that were already running when the
                # hooks went in announce themselves with their next tool call.
                s = TerminalSession(sid, payload.get("cwd"),
                                    payload.get("transcript_path"),
                                    self.on_change)
                self._by_sid[sid] = s
                self.sessions[s.key] = s
                created = True
        if s:
            s.touch(payload)
            ppid = payload.get("iris_ppid")
            if ppid and ppid != s._ppid:
                # First word from this process: find its tab, off the hook's
                # path - ps over every process takes a few milliseconds.
                s._ppid = ppid
                threading.Thread(target=self._locate, args=(s, ppid),
                                 daemon=True).start()
            if s.exited and payload.get("hook_event_name") != "SessionEnd":
                s.exited = False           # remembered as ended, but it is talking
        if created:
            self.save()
        return s

    def _locate(self, s, ppid):
        s.locate(ppid)
        # Settle the text source now, before the next sentence - not at the
        # first tool call, when one may already have come another way.
        s._sync_screen()
        self.save()
        s.on_change(s)

    def handle(self, payload):
        """Answer one hook call. None means: carry on as if we were not here."""
        ev = payload.get("hook_event_name")
        st = self.stats.setdefault(ev or "?", {"count": 0, "sessions": {}})
        st["count"] += 1
        st["last"] = time.time()
        st["sessions"][(payload.get("session_id") or "?")[:8]] = time.time()
        st["last_keys"] = sorted(payload.keys())
        if ev == "Stop":
            st["last_background"] = payload.get("background_tasks", "fehlt")
        if ev == "StatusLine":
            usage.report(payload.get("rate_limits"))
            s = self._by_sid.get(payload.get("session_id"))
            if s:
                s.on_statusline(payload)
            return None
        # A session we never saw does not need an entry just to say goodbye.
        s = self._session(payload, create=ev != "SessionEnd")
        if not s:
            return None
        if ev == "UserPromptSubmit":
            return s.on_prompt(payload)
        if ev == "PermissionRequest":
            return s.on_permission_request(payload, self.away)
        if ev == "PreToolUse":
            return s.on_pre_tool(payload, self.away)
        if ev in ("PostToolUse", "PostToolUseFailure"):
            s.on_post_tool(payload)
            return None
        if ev == "MessageDisplay":
            s.on_text(payload)
            return None
        if ev in ("SubagentStart", "SubagentStop"):
            s.on_subagent(payload, started=ev == "SubagentStart")
            return None
        if ev == "Stop":
            return s.on_stop(payload)
        if ev == "SessionEnd":
            s.on_end(payload)
            self.save()
        return None

    def get(self, key):
        """A session by key - brought back from its transcript if the phone
        asks for one this bridge has not heard from yet."""
        s = self.sessions.get(key)
        if s or not key.startswith("t-"):
            return s
        self.discover(force=True)
        if key in self.sessions:
            return self.sessions[key]
        sid = key[2:]
        with self._lock:
            if sid in self._by_sid:
                return self._by_sid[sid]
            row = self._saved.get(sid)
            if row is None:
                path = history.find_transcript(sid)
                if not path or time.time() - os.path.getmtime(path) > REVIVE_WITHIN:
                    return None
                row = {"cwd": _cwd_of(path), "transcript": path}
            return self._revive(sid, row)

    def list(self):
        self.discover()
        # Erst eine Abschrift, dann aufzaehlen. Die Bruecke beantwortet
        # Anfragen nebenlaeufig: fragt die App die Liste ab, waehrend ein Hook
        # gerade eine Sitzung eintraegt oder entfernt, bricht die Aufzaehlung
        # mit `dictionary changed size during iteration` ab - die Anfrage
        # scheitert, und in der App sieht es aus, als waere die Verbindung
        # weg. Unvorhersehbar und lastabhaengig, gemeldet von Calvin am 26.09.
        return [s.describe() for s in list(self.sessions.values())]

    def reap(self):
        """Forget sessions that ended, and ones that went silent for good.

        A terminal killed hard never sends SessionEnd; after twelve hours
        without a single hook it is not coming back.
        """
        now = time.time()
        with self._lock:
            for key, s in list(self.sessions.items()):
                gone = s.exited and now - s.last_event > 900
                silent = not s.exited and now - s.last_event > 12 * 3600
                if gone or silent:
                    s._tail_stop.set()
                    s.forget_feed()
                    self.sessions.pop(key, None)
                    self._by_sid.pop(s.claude_session_id, None)
        self.save()

    def shutdown(self):
        self.save()
        for s in list(self.sessions.values()):
            s.release_all()
            s._tail_stop.set()
