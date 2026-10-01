"""Turn Claude Code's raw event stream into cards a headset can render.

The raw stream is far too heavy for a pair of glasses: single messages carry
full tool schemas, token accounting and thinking blocks. Every client we will
ever write - web, phone, RayNeo - wants the same short, flat cards, so the
reduction happens once, here, and not in each client.

Card kinds:
  ready   session is up, carries session_id and cwd
  say     assistant prose meant for the user
  think   a short note that the model is reasoning (no content)
  act     a tool call, condensed to one readable line
  result  outcome of a tool call (ok / error, truncated)
  ask     permission decision needed; carries options
  done    turn finished, carries cost and stop reason
  usage   rate-limit / quota information
  error   something went wrong
"""
import difflib
import json
import os

# How much of a card survives, per detail level.
#
#   full    - a workstation client: nothing is thrown away, the raw tool
#             input comes along so a diff or an explanation can be built
#   card    - phone and browser: readable, condensed to one line per call
#   minimal - glasses: only what a person must see to answer or read
#
# The reduction happens on the server, not in the client: the glasses reach
# us over BLE, and shipping 20 KB so the headset can render four lines
# would be the wrong trade.
LEVELS = ("full", "card", "minimal")

LIMITS = {
    "full":    {"text": 200_000, "result": 100_000, "detail": 4000},
    "card":    {"text": 4000,    "result": 600,     "detail": 200},
    "minimal": {"text": 1200,    "result": 160,     "detail": 80},
}

MAX_TEXT = LIMITS["card"]["text"]        # kept for callers that predate levels
MAX_RESULT = LIMITS["card"]["result"]


def _clip(text, limit):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …"


def _describe_tool(name, tool_input, limit=200):
    """One line a person can read at a glance, per tool.

    `limit` follows the detail level: a workstation client wants the whole
    command, a headset wants the first few words.
    """
    ti = tool_input if isinstance(tool_input, dict) else {}

    def short_path(p):
        p = str(p or "")
        home = os.path.expanduser("~")
        if p.startswith(home):
            p = "~" + p[len(home):]
        parts = p.split("/")
        return "/".join(parts[-3:]) if len(parts) > 3 else p

    if name == "Bash":
        return _clip(ti.get("command", ""), limit)
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        return short_path(ti.get("file_path") or ti.get("notebook_path"))
    if name == "Glob":
        return ti.get("pattern", "")
    if name == "Grep":
        pat = ti.get("pattern", "")
        where = short_path(ti.get("path", "")) if ti.get("path") else ""
        return f"{pat}" + (f"  in {where}" if where else "")
    if name in ("WebFetch", "WebSearch"):
        return _clip(ti.get("url") or ti.get("query", ""), limit)
    if name == "Task":
        return _clip(ti.get("description", ""), limit)
    if name == "AskUserQuestion":
        qs = ti.get("questions") or []
        return _clip(qs[0].get("question", ""), limit) if qs else ""
    if name.startswith("mcp__"):
        return _clip(json.dumps(ti, ensure_ascii=False), limit)
    # Fall back to whatever short string field the tool carries.
    for key in ("description", "query", "prompt", "command"):
        if isinstance(ti.get(key), str):
            return _clip(ti[key], limit)
    return _clip(json.dumps(ti, ensure_ascii=False), limit)


CHANGE_TOOLS = ("Edit", "MultiEdit", "Write")


def change_summary(name, tool_input, max_lines=8, width=200):
    """What a file change actually changes: counts plus the first lines.

    Enough to decide on, in the approval and in the conversation - without
    shipping the whole file. Edit inputs carry no line numbers, so there are
    none here either; the +/- markers are the information.
    """
    ti = tool_input if isinstance(tool_input, dict) else {}
    if name == "Write":
        lines = (ti.get("content") or "").splitlines()
        return {"added": len(lines), "removed": 0,
                "lines": [["+", ln[:width]] for ln in lines[:max_lines]]}
    if name == "Edit":
        pairs = [(ti.get("old_string") or "", ti.get("new_string") or "")]
    elif name == "MultiEdit":
        pairs = [(e.get("old_string") or "", e.get("new_string") or "")
                 for e in ti.get("edits") or [] if isinstance(e, dict)]
    else:
        return None
    added = removed = 0
    lines = []
    for old, new in pairs:
        for ln in difflib.ndiff(old.splitlines(), new.splitlines()):
            tag = ln[:1]
            if tag == "+":
                added += 1
            elif tag == "-":
                removed += 1
            else:
                continue                   # unchanged, or ndiff's '?' hints
            if len(lines) < max_lines:
                lines.append([tag, ln[2:][:width]])
    return {"added": added, "removed": removed, "lines": lines}


def _result_text(content):
    """Flatten a tool_result payload down to readable text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
                elif c.get("type") == "image":
                    parts.append("[Bild]")
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(p for p in parts if p)
    return ""


IMAGES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic")


def reduce_event(raw, detail="card"):
    """Map one raw Claude Code event to zero or more cards.

    `detail` decides how much survives - see LEVELS. The card *kinds* stay
    the same at every level, so a client never has to special-case them;
    only the payload gets richer or thinner.
    """
    lim = LIMITS.get(detail, LIMITS["card"])
    t = raw.get("type")

    if t == "system" and raw.get("subtype") == "init":
        return [{"kind": "ready",
                 "session_id": raw.get("session_id"),
                 "cwd": raw.get("cwd"),
                 "model": raw.get("model"),
                 "tools": len(raw.get("tools") or [])}]

    if t == "system" and raw.get("subtype") == "thinking_tokens":
        if detail == "minimal":
            return [{"kind": "think"}]
        return [{"kind": "think", "tokens": raw.get("estimated_tokens", 0)}]

    if t == "rate_limit_event":
        info = raw.get("rate_limit_info") or {}
        # unifiedWindows carries exactly what /usage reports: utilization per
        # window plus its reset time. On a subscription this - not a dollar
        # figure - is what actually constrains the user.
        windows = {}
        for name, w in (info.get("unifiedWindows") or {}).items():
            windows[name] = {"used": w.get("utilization"),
                             "resets_at": w.get("resetsAt")}
        return [{"kind": "usage",
                 "status": info.get("status"),
                 "window": info.get("rateLimitType"),
                 "resets_at": info.get("resetsAt"),
                 "using_overage": info.get("isUsingOverage"),
                 "windows": windows}]

    if t == "assistant":
        cards = []
        for c in (raw.get("message", {}).get("content") or []):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and c.get("text", "").strip():
                cards.append({"kind": "say", "text": _clip(c["text"], lim["text"])})
            elif c.get("type") == "tool_use":
                card = {"kind": "act",
                        "tool": c.get("name", "?"),
                        "detail": _describe_tool(c.get("name"), c.get("input"),
                                                 lim["detail"]),
                        "tool_use_id": c.get("id")}
                # A picture it read: the full path, so the phone can show it
                # (GET /api/sessions/<key>/image - only paths the transcript names).
                path = (c.get("input") or {}).get("file_path") if c.get("name") == "Read" else None
                if isinstance(path, str) and path.lower().endswith(IMAGES):
                    card["image"] = path
                # Files Claude handed over (SendUserFile): the phone shows
                # pictures and plays sound right in the line.
                if c.get("name") == "SendUserFile":
                    sent = (c.get("input") or {}).get("files")
                    if isinstance(sent, list):
                        card["files"] = [f for f in sent if isinstance(f, str)][:12]
                if c.get("name") in CHANGE_TOOLS:
                    ch = change_summary(c.get("name"), c.get("input"))
                    if ch and detail == "minimal":
                        ch = {"added": ch["added"], "removed": ch["removed"]}
                    card["change"] = ch
                if detail == "full":
                    # The whole input, so a client can show a diff, explain a
                    # shell command, or render the arguments properly.
                    card["input"] = c.get("input")
                cards.append(card)
        return cards

    if t == "user":
        cards = []
        content = raw.get("message", {}).get("content")
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    text = _result_text(c.get("content"))
                    card = {"kind": "result",
                            "ok": not c.get("is_error"),
                            "tool_use_id": c.get("tool_use_id"),
                            "text": _clip(text, lim["result"])}
                    if detail == "full":
                        card["truncated"] = len(text) > lim["result"]
                        card["full_length"] = len(text)
                    cards.append(card)
        return cards

    if t == "result":
        if detail == "minimal":
            return [{"kind": "done", "stop_reason": raw.get("stop_reason"),
                     "is_error": raw.get("is_error", False)}]
        return [{"kind": "done",
                 "stop_reason": raw.get("stop_reason"),
                 "subtype": raw.get("subtype"),
                 "cost_usd": raw.get("total_cost_usd"),
                 "duration_ms": raw.get("duration_api_ms"),
                 "is_error": raw.get("is_error", False)}]

    return []
