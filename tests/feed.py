"""The numbers on the cards: they must never fall back.

A client reads a number that is smaller than the last one as "the bridge
lost its record and started counting afresh" - it throws away the
conversation it holds and loads it again. So a feed whose numbers fall back
puts the app into a reload loop and it shows nothing at all. That happened:
a second bridge (a test one on the real state folder) wrote into the same
feed file with a counter of its own.

Costs no quota - no Claude runs here.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = tempfile.mkdtemp(prefix="iris-feed-")
# Before the import: the paths are read when the module is loaded.
os.environ["IRIS_TERMINALS_PATH"] = os.path.join(STATE, "terminals.json")

sys.path.insert(0, ROOT)
from bridge import terminals            # noqa: E402

ok_count = 0
fail = []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
        print(f"  ok   {name}")
    else:
        fail.append(name)
        print(f"  FAIL {name} {detail}")


def write_feed(sid, rows):
    os.makedirs(terminals.FEEDS_DIR, mode=0o700, exist_ok=True)
    path = os.path.join(terminals.FEEDS_DIR, sid + ".jsonl")
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def row(seq, text):
    return {"seq": seq, "entry": {"card": {"kind": "say", "text": text}, "ts": 0},
            "off": 0, "until": 0, "anchor": None, "anchor_n": 0}


def main():
    print("zwei Bridges auf einer Datei")
    # What it looks like on disk: one bridge wrote 1..4, a second one came
    # along and wrote its own 3..5 in between.
    sid = "11111111-2222-3333-4444-555555555555"
    mixed = [row(1, "a"), row(2, "b"), row(3, "c"), row(3, "fremd-c"),
             row(4, "d"), row(4, "fremd-d"), row(5, "fremd-e"), row(5, "e")]
    path = write_feed(sid, mixed)

    s = terminals.TerminalSession(sid, STATE, "", lambda _s: None)
    seqs = [n for n, _ in s._ring]
    check("Ring steigt an", all(b > a for a, b in zip(seqs, seqs[1:])), f"({seqs})")
    check("Nichts vom ersten Schreiber verloren", seqs == [1, 2, 3, 4, 5], f"({seqs})")
    texts = [(e.get("card") or {}).get("text") for _, e in s._ring]
    check("Die Karten des ersten Schreibers bleiben",
          texts == ["a", "b", "c", "d", "fremd-e"], f"({texts})")

    healed = [json.loads(l) for l in open(path) if l.strip()]
    check("Datei ist danach in Ordnung",
          [r["seq"] for r in healed] == [1, 2, 3, 4, 5],
          f"({[r['seq'] for r in healed]})")

    print("was der Strom liefert")
    _q, backlog = s.subscribe(since=0)
    nums = [c["seq"] for c in backlog]
    check("Keine Nummer im Strom springt zurück",
          all(b >= a for a, b in zip(nums, nums[1:])), f"({nums})")
    check("Ein bekannter Stand liefert nur Neueres",
          [c["seq"] for c in s.subscribe(since=3)[1]] == [4, 5])

    print("nur eine Bridge schreibt")
    check("Diese Bridge hat die Sperre", terminals.owns_feeds() is True)
    other = subprocess.run(
        [sys.executable, "-c",
         "import os,sys; sys.path.insert(0, %r);"
         "from bridge import terminals as t; print(t.owns_feeds())" % ROOT],
        cwd=ROOT, capture_output=True, text=True,
        env=dict(os.environ, IRIS_TERMINALS_PATH=os.environ["IRIS_TERMINALS_PATH"]))
    check("Eine zweite Bridge bekommt sie nicht",
          other.stdout.strip().endswith("False"), f"({other.stdout.strip()!r})")
    check("Und sagt es",
          "gehört Bridge" in other.stdout, f"({other.stdout.strip()!r})")

    # And it stays out of the file: the row count does not move.
    before = len(open(path).readlines())
    subprocess.run(
        [sys.executable, "-c",
         "import os,sys; sys.path.insert(0, %r);"
         "from bridge import terminals as t;"
         "s = t.TerminalSession(%r, '', '', lambda _s: None);"
         "s._emit({'kind': 'say', 'text': 'von der zweiten Bridge'})" % (ROOT, sid)],
        cwd=ROOT, capture_output=True, text=True)
    check("Die zweite Bridge schreibt nichts hinein",
          len(open(path).readlines()) == before,
          f"({before} -> {len(open(path).readlines())})")

    print(f"\n{ok_count} ok, {len(fail)} fehlgeschlagen")
    if fail:
        print("fehlgeschlagen:", ", ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        import shutil
        shutil.rmtree(STATE, ignore_errors=True)
