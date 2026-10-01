"""Read a past conversation off disk and hand it back as cards.

Resuming a session used to open an empty screen: the conversation existed,
but nothing of it was visible. Claude Code keeps the full transcript as
JSONL, and those records carry the same shape as the live stream, so the
same reducer turns them into the same cards.

Read-only. iris never writes into a transcript.
"""
import time
import json
import os
import re

from . import config, protocol

# Bookkeeping records that carry no conversation content.
SKIP_TYPES = {
    "mode", "permission-mode", "bridge-session", "file-history-snapshot",
    "atis-latch", "last-prompt", "ai-title", "queue-operation", "attachment",
    "summary",
}


def transcript_path(project_id, session_id):
    return os.path.join(config.CLAUDE_PROJECTS, project_id, f"{session_id}.jsonl")


def find_transcript(session_id):
    """Locate a transcript by session id across all projects."""
    root = config.CLAUDE_PROJECTS
    if not os.path.isdir(root):
        return None
    for name in os.listdir(root):
        p = os.path.join(root, name, f"{session_id}.jsonl")
        if os.path.isfile(p):
            return p
    return None


# The summary Claude Code writes when the context runs full. Can be long.
MAX_SUMMARY = 60000


def _plain(content):
    """Text of a prompt that may come as parts (text plus pasted images),
    without the "[Image #3]" marks the input line puts in for pictures."""
    if isinstance(content, list):
        content = "\n".join(c.get("text", "") for c in content
                            if isinstance(c, dict) and c.get("type") == "text")
    if not isinstance(content, str):
        return ""
    return re.sub(r"\[Image #\d+\]\s*", "", content).strip()


def queued_prompt(rec):
    """What a person typed while Claude was working. Claude Code does not
    write that as a user record: it is an attachment of type queued_command,
    taken in after the step that was running. Returns the text, or None."""
    att = rec.get("attachment") if rec.get("type") == "attachment" else None
    if not isinstance(att, dict) or att.get("type") != "queued_command":
        return None
    if (att.get("origin") or {}).get("kind", "human") != "human":
        return None
    return _plain(att.get("prompt")) or None


def queue_operation(rec):
    """Claude Code's own queue of what was typed while it worked: enqueue
    when it went in, remove or dequeue when Claude took it (or it was pulled
    back to the input). Returns (operation, text) or None."""
    if rec.get("type") != "queue-operation":
        return None
    text = _plain(rec.get("content"))
    if not text or _is_injected(text):
        return None
    return rec.get("operation"), text


_ARTIFACT_URL = re.compile(rb"https://claude\.ai/code/artifact/[0-9a-f-]{36}")


def page_title(path):
    """The <title> of a page on disk, or None."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8192).decode("utf-8", errors="replace")
    except (OSError, TypeError):
        return None
    m = re.search(r"<title>\s*(.*?)\s*</title>", head, re.S | re.I)
    return m.group(1) if m else None


def artifact_url(text):
    m = _ARTIFACT_URL.search((text or "").encode())
    return m.group(0).decode() if m else None


def artifacts(path, until=None):
    """The pages published with the Artifact tool in a transcript: url ->
    {url, title, icon, ts}. Only lines that mention it are parsed - the file
    runs to tens of megabytes."""
    calls, out = {}, {}
    try:
        fh = open(path, "rb")
    except (OSError, TypeError):
        return out
    with fh:
        read = 0
        for line in fh:
            read += len(line)
            if until is not None and read > until:
                break
            if b'"Artifact"' not in line and b"claude.ai/code/artifact/" not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            content = rec.get("message", {}).get("content")
            for c in content if isinstance(content, list) else []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use" and c.get("name") == "Artifact":
                    if (c.get("input") or {}).get("action") in (None, "publish"):
                        calls[c.get("id")] = c.get("input") or {}
                elif c.get("type") == "tool_result" and c.get("tool_use_id") in calls \
                        and not c.get("is_error"):
                    item = artifact_item(calls.pop(c["tool_use_id"]),
                                         protocol._result_text(c.get("content")),
                                         out, _stamp(rec.get("timestamp")))
                    if item:
                        out[item["url"]] = item
    return out


def artifact_item(inp, result, known, ts):
    """One published page from the call and its answer, or None."""
    url = artifact_url(result)
    if not url or not result.lstrip().startswith("Published"):
        return None
    old = known.get(url, {})
    path = inp.get("file_path")
    title = inp.get("title") or page_title(path) or old.get("title") \
        or os.path.splitext(os.path.basename(path or ""))[0] or "Seite"
    return {"url": url, "title": title, "icon": inp.get("favicon") or old.get("icon") or "",
            "ts": ts}


def _stamp(iso):
    import datetime
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def compact_summary(rec):
    """The summary Claude Code puts in place of the conversation when the
    context ran full - without the framing written for the model: the lead-in
    before "Summary:" and the instructions after it. Returns it, or None."""
    if rec.get("type") != "user" or not rec.get("isCompactSummary"):
        return None
    text = _plain(rec.get("message", {}).get("content"))
    head = text.find("Summary:")
    if head != -1:
        text = text[head + len("Summary:"):]
    tail = text.find("\nIf you need specific details from before compaction")
    if tail != -1:
        text = text[:tail]
    return text.strip() or None


def relevant(rec):
    """Does a transcript record carry conversation content?"""
    if queued_prompt(rec):
        return True
    if rec.get("type") in SKIP_TYPES:
        return False
    # Sidechains are subagent traffic - not this conversation.
    if rec.get("isSidechain") or rec.get("isMeta"):
        return False
    return rec.get("type") in ("user", "assistant")


def load(session_id, limit=120, until_offset=None):
    """Return the tail of a conversation as cards, oldest first.

    `limit` counts cards, not records: a single turn can produce many.
    `until_offset` stops at a byte position - a terminal session serves its
    live part from a tail that starts there, so the two never overlap.
    """
    path = find_transcript(session_id)
    if not path:
        return []
    try:
        with open(path, "rb") as fh:
            data = fh.read(until_offset) if until_offset is not None else fh.read()
    except OSError:
        return []

    cards = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not relevant(rec):
            continue
        if rec.get("type") == "user" or queued_prompt(rec):
            cards.extend(_user_cards(rec))
        else:
            cards.extend(protocol.reduce_event(rec))

    cards = cards[-limit:]
    for i, c in enumerate(cards, start=1):
        c["seq"] = -len(cards) + i - 1     # negative: history, never live seq
        c["historic"] = True
    return cards


def _user_cards(rec):
    """A user record is either something the person typed or a tool result -
    and a queued command is something typed while Claude worked. The
    summary after the context ran full is none of those: a card of its own."""
    summary = compact_summary(rec)
    if summary:
        return [{"kind": "summary", "text": protocol._clip(summary, MAX_SUMMARY)}]
    queued = queued_prompt(rec)
    if queued:
        return [] if _is_injected(queued) else [
            {"kind": "sent", "text": protocol._clip(queued, protocol.MAX_TEXT)}]
    content = rec.get("message", {}).get("content")

    if isinstance(content, str):
        text = content.strip()
        if _is_injected(text):
            return []
        return [{"kind": "sent", "text": protocol._clip(text, protocol.MAX_TEXT)}]

    if isinstance(content, list):
        out = []
        typed = []
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_result":
                out.append({
                    "kind": "result",
                    "ok": not c.get("is_error"),
                    "tool_use_id": c.get("tool_use_id"),
                    "text": protocol._clip(protocol._result_text(c.get("content")),
                                           protocol.MAX_RESULT),
                })
            elif c.get("type") == "text":
                typed.append(c.get("text", ""))
        # No "[Image #3]" marks for pictures pasted at the Mac - the phone
        # shows the words.
        text = _plain("\n".join(t for t in typed if t))
        if text and not _is_injected(text):
            out.insert(0, {"kind": "sent",
                           "text": protocol._clip(text, protocol.MAX_TEXT)})
        return out
    return []


def _is_injected(text):
    """Filter context the harness injects; it was never typed by the user."""
    head = text.lstrip()[:80]
    return head.startswith((
        "<local-command", "<command-name", "<system-reminder", "<user-prompt",
        "Caveat:", "[Request interrupted", "[Your previous response",
        "<task-notification", "<bash-input", "<bash-stdout", "<bash-stderr",
    ))


def ai_title(project_id, session_id):
    """The title Claude Code generated for a conversation, if there is one."""
    path = transcript_path(project_id, session_id)
    if not os.path.isfile(path):
        return ""
    title = ""
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                if '"ai-title"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "ai-title" and rec.get("aiTitle"):
                    title = rec["aiTitle"]        # keep the last one
    except OSError:
        pass
    return title


# Public name: terminals.py turns live transcript records into cards with it.
user_cards = _user_cards


# How full the context is: what the last answer was sent with. The
# transcript names no window size, so it comes from the model setting -
# "[1m]" there, or more than 200k already in use, means the million.
WINDOW = 200_000
BIG_WINDOW = 1_000_000
_setting = {"at": 0.0, "model": ""}


def context_tokens(rec):
    """Tokens the answer in this record was sent with, or None."""
    if rec.get("type") != "assistant" or rec.get("isSidechain"):
        return None
    u = (rec.get("message") or {}).get("usage") or {}
    n = sum(u.get(k) or 0 for k in
            ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return n or None


def last_context(path, tail=400_000):
    """The context of the newest answer near the end of a transcript."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - tail))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return None
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            n = context_tokens(json.loads(line))
        except ValueError:
            continue
        if n:
            return n
    return None


def context_window(tokens):
    if tokens and tokens > WINDOW:
        return BIG_WINDOW
    if time.time() - _setting["at"] > 60:
        model = os.environ.get("ANTHROPIC_MODEL", "")
        try:
            with open(os.path.join(os.path.expanduser("~"), ".claude", "settings.json"),
                      encoding="utf-8") as f:
                model = model or (json.load(f).get("model") or "")
        except (OSError, ValueError, AttributeError):
            pass
        _setting.update(at=time.time(), model=str(model).lower())
    return BIG_WINDOW if "[1m]" in _setting["model"] else WINDOW
