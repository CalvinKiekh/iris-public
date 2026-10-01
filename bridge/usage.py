"""The plan's limits: how much of the five-hour and the weekly window is
used, and whether one is used up.

Terminal sessions report the figures through their status line (see
hooks/iris_hook.py --statusline), sessions this bridge hosts through
rate_limit_event. A window used up shows in the transcript as an API error
with quotaLimits - then the phone is told at once, with the time it is free
again: from afar, a session that just stops answering looks like a hang.
"""
import json
import os
import threading
import time

from . import config, push

PATH = os.path.join(config.CONFIG_DIR, "usage.json")
WARN_AT = (80, 95)                     # percent of a window: tell the phone once each
NAMES = {"five_hour": "5-Stunden-Fenster", "seven_day": "Wochenlimit",
         "seven_day_opus": "Wochenlimit (Opus)", "seven_day_sonnet": "Wochenlimit (Sonnet)"}
_lock = threading.Lock()


def _load():
    try:
        d = config.read_json(PATH)
        return {"five_hour": d.get("five_hour"), "seven_day": d.get("seven_day"),
                "limited": d.get("limited"), "updated": d.get("updated") or 0,
                "warned": list(d.get("warned") or [])[-40:]}
    except (OSError, ValueError, AttributeError):
        return {"five_hour": None, "seven_day": None, "limited": None, "updated": 0, "warned": []}


state = _load()


def _save():
    try:
        os.makedirs(config.CONFIG_DIR, exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, PATH)
    except OSError:
        pass


def clock(ts):
    """18:40, or with the day when it is not today."""
    if not ts:
        return "?"
    t = time.localtime(float(ts))
    now = time.localtime()
    if t.tm_yday == now.tm_yday and t.tm_year == now.tm_year:
        return time.strftime("%H:%M", t)
    days = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
    return f"{days[t.tm_wday]} {time.strftime('%H:%M', t)}"


def message(window, resets_at):
    return (f"Limit erreicht: {NAMES.get(window, 'Nutzungslimit')} aufgebraucht, wieder frei "
            f"um {clock(resets_at)}. Bis dahin bearbeitet Claude nichts – was du jetzt "
            f"schickst, danach noch einmal senden.")


def snapshot():
    with _lock:
        lim = state.get("limited")
        if lim and (lim.get("resets_at") or 0) < time.time():
            state["limited"] = None
        # A window whose end has passed says nothing about now. On 12.09. the
        # PC reported 40 % against a window that had ended at 10:50, while the
        # Mac stood at 2 % in the current one - the same account, two hours
        # apart, and the stale figure looked exactly like a measurement.
        # Nobody sends a "reset" event; the end time is what we have.
        jetzt = time.time()
        for name in ("five_hour", "seven_day"):
            w = state.get(name)
            if isinstance(w, dict) and (w.get("resets_at") or 0) and w["resets_at"] < jetzt:
                state[name] = {"used": 0.0, "resets_at": None, "veraltet_seit": w["resets_at"]}
        return {k: state.get(k) for k in ("five_hour", "seven_day", "limited", "updated")}


def cards():
    """The figures as the phone's "usage" card (fractions, like the stream's)."""
    s = snapshot()
    windows = {n: s[n] for n in ("five_hour", "seven_day") if s.get(n)}
    return {"kind": "usage", "windows": windows, "limited": s.get("limited")}


def report(rate_limits, used_as_fraction=False):
    """New figures: {"five_hour": {"used_percentage", "resets_at"}, ...}.
    True if something changed."""
    if not isinstance(rate_limits, dict):
        return False
    changed = False
    with _lock:
        for name in ("five_hour", "seven_day"):
            w = rate_limits.get(name)
            if not isinstance(w, dict):
                continue
            used = w.get("used_percentage", w.get("used", w.get("utilization")))
            if used is None:
                continue
            frac = float(used) if used_as_fraction else float(used) / 100
            new = {"used": round(frac, 3), "resets_at": w.get("resets_at")}
            # Innerhalb eines Fensters kann der Verbrauch nur steigen. Jede
            # Sitzung meldet ihren eigenen Stand, und eine aeltere mit
            # veralteter Zahl liess die Anzeige zurueckfallen - 95 Prozent
            # wurden wieder 89. Nur beim Fensterwechsel faengt es neu an.
            alt = state.get(name) or {}
            gleiches_fenster = alt.get("resets_at") == new["resets_at"]
            if gleiches_fenster and (alt.get("used") or 0) > new["used"]:
                new["used"] = alt["used"]
            if new != alt:
                state[name] = new
                changed = True
        state["updated"] = time.time()
        lim = state.get("limited")
        if lim and (lim.get("resets_at") or 0) < time.time():
            state["limited"] = None
            changed = True
    for name in ("five_hour", "seven_day"):
        _warn(name)
    if changed:
        _save()
    return changed


def _warn(name):
    w = state.get(name) or {}
    pct = (w.get("used") or 0) * 100
    level = max((lv for lv in WARN_AT if pct >= lv), default=None)
    if level is None:
        return
    tag = f"{name}:{w.get('resets_at')}:{level}"
    with _lock:
        if tag in state["warned"]:
            return
        # The lower level counts as told too - no 80 % after the 95 %.
        state["warned"] += [f"{name}:{w.get('resets_at')}:{lv}" for lv in WARN_AT if lv <= level]
        state["warned"] = state["warned"][-40:]
    _save()
    # Every computer of this account says the same; one collapse id keeps it
    # one notification on the phone.
    push.send({"aps": {"alert": {"title": "Claude-Abo",
                                 "subtitle": f"{NAMES.get(name, name)} zu {int(pct)} % verbraucht",
                                 "body": f"Wieder frei ab {clock(w.get('resets_at'))}."},
                       "sound": "default", "thread-id": "abo"},
               "iris": {"kind": "usage", "machine": config.machine_name()}},
              collapse=f"abo-{tag}"[:64])


def hit(window, resets_at, title="", key=""):
    """A window is used up - told once per window and reset time."""
    with _lock:
        lim = state.get("limited") or {}
        if lim.get("resets_at") == resets_at and lim.get("window") == window:
            return False
        state["limited"] = {"window": window, "resets_at": resets_at, "since": time.time()}
    _save()
    push.send({"aps": {"alert": {"title": title or "Claude", "subtitle": "Limit erreicht",
                                 "body": f"{NAMES.get(window, 'Nutzungslimit')} aufgebraucht – "
                                         f"wieder frei um {clock(resets_at)}."},
                       "sound": "default", "thread-id": key or "abo",
                       "interruption-level": "time-sensitive"},
               "iris": {"kind": "limit", "key": key, "machine": config.machine_name()}},
              collapse=f"limit-{window}-{resets_at}"[:64])
    return True


def limit_record(rec):
    """(window, resets_at) if this transcript record says a limit is used up."""
    if rec.get("type") != "assistant" or not rec.get("isApiErrorMessage"):
        return None
    q = rec.get("quotaLimits") or {}
    if rec.get("error") != "rate_limit" and q.get("status") != "rejected":
        return None
    return q.get("rateLimitType") or "five_hour", q.get("resetsAt")
