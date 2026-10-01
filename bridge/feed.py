"""Sequenced ring buffer with a reduction per subscriber.

Shared by the sessions the bridge hosts and the terminal sessions it only
watches, so a client never needs to know which of the two it is looking at.

The ring holds *raw* events, not finished cards, so every client can be
served at its own detail level from the same history. A workstation wants
the full tool input; the glasses want four lines. Reducing once for everyone
would mean the richest client could never catch up.

Clients on a headset drop off constantly, so every card gets a sequence
number and stays in the ring for replay.
"""
import queue
import threading
import time

from . import protocol

RING_SIZE = 500


class Feed:
    def _feed_init(self):
        self._seq = 0
        self._ring = []                    # [(seq, entry)]
        self._subscribers = []             # [(queue, detail)]
        self._lock = threading.Lock()

    def _store(self, entry):
        """Append to the ring and fan out. Returns the assigned sequence."""
        with self._lock:
            self._seq += 1
            seq = self._seq
            self._ring.append((seq, entry))
            size = getattr(self, "_ring_size", RING_SIZE)
            if len(self._ring) > size:
                del self._ring[:len(self._ring) - size]
            subs = list(self._subscribers)
        for q, detail in subs:
            for card in self._render(entry, seq, detail):
                try:
                    q.put_nowait(card)
                except queue.Full:
                    pass
        return seq

    def _render(self, entry, seq, detail):
        """Turn a ring entry into cards at the requested detail level."""
        if "card" in entry:
            cards = [dict(entry["card"])]
        else:
            cards = protocol.reduce_event(entry["raw"], detail)
        stamped = []
        for c in cards:
            c["seq"] = seq
            c.setdefault("ts", entry.get("ts", time.time()))
            stamped.append(c)
        return stamped

    def _emit(self, card):
        """Emit a card iris made up itself (sent, ask, mode, closed, ...).

        Returns its seq, which is how a later card can say it supersedes
        this one."""
        return self._store({"card": card, "ts": time.time()})

    def _emit_raw(self, raw):
        """Emit an event straight from Claude Code, kept whole for later."""
        self._store({"raw": raw, "ts": time.time()})

    def subscribe(self, since=0, detail="card"):
        """Return (queue, backlog) so a reconnecting client misses nothing."""
        if detail not in protocol.LEVELS:
            detail = "card"
        q = queue.Queue(maxsize=2000)
        with self._lock:
            # A client that knows a higher number than this feed ever gave
            # out is from before a restart of the bridge: everything here is
            # new to it. Without this it would wait for the count to catch up.
            if since > self._seq:
                since = 0
            entries = [(s, e) for s, e in self._ring if s > since]
            self._subscribers.append((q, detail))
        backlog = []
        for s, e in entries:
            backlog.extend(self._render(e, s, detail))
        return q, backlog

    def watchers(self):
        """How many clients are looking right now."""
        with self._lock:
            return len(self._subscribers)

    def unsubscribe(self, q):
        with self._lock:
            self._subscribers = [(sq, d) for sq, d in self._subscribers
                                 if sq is not q]
