"""The resident: a local model on this computer that watches and acts on
its own (docs/PLAN.md section 6, the contract in docs/BEWOHNER.md).

It runs as a process of its own. The bridge only reads its workspace -
bewohner.json for the state, journal.jsonl for what happened, antraege/ for
requests - and puts files in for the app: STOP, WECKEN, a word from you
under zurufe/, a decision into a request. Files, because both sides can
restart without the other, and because you can read and fix every one.
"""
import base64
import json
import os
import queue
import re
import sqlite3
import threading
import time

from . import config, push

KEEP = 500                             # journal cards held for the phone
PROTOCOL = {"bewohner.json", "journal.jsonl", "STOP", "WECKEN"}
TEXT = (".md", ".txt", ".json", ".jsonl", ".log")


def _now():
    return time.time()


class Resident:
    def __init__(self, cfg):
        self.dir = os.path.abspath(cfg.get("resident_dir")
                                   or os.path.join(config.HOME, "mcp-test", "werkstatt"))
        self.cards = []
        self.seq = 0
        self._subs = []
        self._lock = threading.Lock()
        self._offset = None            # None: not read yet
        self._partial = b""
        self._requests_seen = None
        self._stopped_by_app = 0.0
        threading.Thread(target=self._watch, daemon=True).start()

    # ---------- reading ----------

    def present(self):
        return os.path.isdir(self.dir)

    def _path(self, rel):
        """A path inside the workspace, or None - nothing outside it."""
        full = os.path.abspath(os.path.join(self.dir, rel))
        if os.path.commonpath([full, self.dir]) != self.dir:
            return None
        return full

    def state(self):
        try:
            s = config.read_json(os.path.join(self.dir, "bewohner.json"))
            if not isinstance(s, dict):
                s = {}
        except (OSError, ValueError):
            s = {}
        seen = max(float(s.get("last_check") or 0), float(s.get("updated") or 0))
        s["stopped"] = os.path.exists(os.path.join(self.dir, "STOP"))
        s["waking"] = os.path.exists(os.path.join(self.dir, "WECKEN"))
        # Watching means checking at least once a minute; three quiet
        # minutes and it is not there.
        # He says himself how long his state stays good: gueltig_bis is two of
        # his own pulses plus a little. Without it, a fixed 180 s had to do -
        # and on 12.09. it reported "wach" for ninety seconds after the
        # process was gone.
        frist = s.get("gueltig_bis")
        if isinstance(frist, (int, float)) and frist > 0:
            lebt = _now() <= frist
        else:
            lebt = bool(seen) and _now() - seen < 180
        s["alive"] = lebt and s.get("state") != "beendet"
        if not lebt and s.get("state") not in ("beendet", None):
            # What the app shows must not claim more than we know.
            s["state_roh"] = s.get("state")
            s["state"] = "tot"
        s["seen"] = seen or None
        s["requests"] = self.requests()
        s["machine"] = config.machine_name()
        s["conversation"] = {"waiting": self.waiting()}
        return s

    def waiting(self):
        """Questions not answered yet, oldest first - the queue it works
        through. Only the last half hour: older ones are not waiting, they
        were lost."""
        d = os.path.join(self.dir, "gespraech")
        rows = []
        try:
            names = [n for n in os.listdir(d) if n.endswith(".json")]
        except OSError:
            return rows
        cut = _now() - 1800
        for n in names:
            full = os.path.join(d, n)
            try:
                if os.path.getmtime(full) < cut:
                    continue
                r = config.read_json(full)
            except (OSError, ValueError):
                continue
            if not isinstance(r, dict) or r.get("antwort") or r.get("status") != "offen":
                continue
            rows.append({"id": r.get("id") or n[:-5], "ts": r.get("ts"),
                         "von": r.get("von") or "app", "zu": r.get("zu")})
        rows.sort(key=lambda r: r.get("ts") or 0)
        return rows[:30]

    # How many earlier conversations the phone gets to choose from. More is a
    # list nobody reads; fewer and yesterday is already gone.
    GESPRAECHE_MAX = 25

    def gespraeche(self):
        """Calvins frühere Gespräche - das jüngste zuerst.

        DIE CHAT-ANSICHT ZEIGT NUR DAS LAUFENDE GESPRÄCH, seit sie bei zehn
        Minuten Stille abschneidet - sonst las Calvin am Abend noch die
        Nachrichten von gestern. Damit war aber auch der Weg zurück weg:
        "Ich kann keine Chats auswählen beim Bewohner." Hier ist er.

        Messungen kommen nicht vor: Eine Sitzung aus dem Testkanal ist kein
        Gespräch, das er geführt hat.
        """
        path = os.path.join(self.dir, "sitzungen.jsonl")
        rows = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        k = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(k, dict) or not k.get("id"):
                        continue
                    if str(k.get("von") or "").lower() in ("test", "probe"):
                        continue
                    rows.append({
                        "id": k["id"],
                        "begonnen": k.get("begonnen"),
                        "zuletzt": k.get("letzte_frage") or k.get("begonnen"),
                        "geschlossen": k.get("geschlossen"),
                        "paare": k.get("paare") or 0,
                        # Ohne Zusammenfassung ist es noch offen oder das
                        # Modell hat geschwiegen - beides ist kein Fehler,
                        # und die App sagt es dann selbst.
                        "zusammenfassung": k.get("zusammenfassung")})
        except OSError:
            return []
        rows.sort(key=lambda r: -(r.get("zuletzt") or 0))
        return rows[:self.GESPRAECHE_MAX]

    def gespraech(self, sid):
        """Ein Gespräch mit seinen Paaren - oder None."""
        if not re.fullmatch(r"s-\d{10,16}", str(sid or "")):
            return None
        full = self._path(os.path.join("sitzungen", str(sid) + ".json"))
        if not full or not os.path.isfile(full):
            return None
        try:
            d = config.read_json(full)
        except (OSError, ValueError):
            return None
        paare = d.get("paare") if isinstance(d, dict) else None
        if not isinstance(paare, list):
            return None
        kopf = next((k for k in self.gespraeche() if k["id"] == sid), None)
        return {"id": sid, "kopf": kopf,
                "paare": [{"frage": p.get("frage"), "antwort": p.get("antwort"),
                           "ts": p.get("ts")}
                          for p in paare if isinstance(p, dict)]}

    def requests(self):
        d = os.path.join(self.dir, "antraege")
        rows = []
        try:
            names = os.listdir(d)
        except OSError:
            return rows
        for n in names:
            if not n.endswith(".json"):
                continue
            try:
                r = config.read_json(os.path.join(d, n))
            except (OSError, ValueError):
                continue
            if isinstance(r, dict) and r.get("id"):
                rows.append(r)
        rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
        return rows[:30]

    def files(self):
        out = []
        for base, dirs, names in os.walk(self.dir):
            rel = os.path.relpath(base, self.dir)
            if rel.count(os.sep) >= 3:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for n in names:
                if n.startswith(".") or not n.endswith(TEXT):
                    continue
                full = os.path.join(base, n)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                path = os.path.normpath(os.path.join(rel, n)).replace(os.sep, "/")
                out.append({"path": path, "size": st.st_size, "mtime": st.st_mtime,
                            "editable": self._editable(path)})
        out.sort(key=lambda f: (f["path"].count("/"), f["path"]))
        return out

    def read(self, rel):
        full = self._path(rel)
        if not full or not os.path.isfile(full):
            return None, "Datei nicht gefunden"
        if os.path.getsize(full) > 256 * 1024:
            return None, "Datei ist zu groß für die App"
        with open(full, "rb") as fh:
            return fh.read().decode("utf-8", "replace"), ""

    # ---------- writing: what the app puts in ----------

    @staticmethod
    def _editable(rel):
        name = rel.replace("\\", "/").split("/")[-1]
        return (name not in PROTOCOL and not rel.startswith("antraege/")
                and name.endswith((".md", ".txt")))

    def _put(self, full, text):
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = full + ".iris.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, full)

    def write(self, rel, text):
        full = self._path(rel)
        if not full or not self._editable(rel.replace("\\", "/")):
            return False, "Diese Datei schreibt nur der Bewohner."
        self._put(full, text)
        return True, ""

    def stop(self, on):
        f = os.path.join(self.dir, "STOP")
        if on:
            self._stopped_by_app = _now()
            self._put(f, "angehalten über die App, " + time.strftime("%d.%m. %H:%M") + "\n")
        elif os.path.exists(f):
            os.remove(f)
        return True, ""

    def wake(self):
        self._put(os.path.join(self.dir, "WECKEN"), time.strftime("%d.%m. %H:%M") + "\n")
        return True, ""

    def say(self, text):
        text = (text or "").strip()
        if not text:
            return False, "Leerer Zuruf"
        self._put(os.path.join(self.dir, "zurufe", f"{int(_now() * 1000)}.md"), text + "\n")
        return True, ""

    def talk(self, text, gid=None, draft=False, zu=None, von=None, aufnahme=None,
             stimme=None):
        """A question for the resident - it answers in the journal
        ("frage", "antwort", then "stimme" with the recording).

        draft: what was said so far, while Calvin still speaks (status
        "entwurf"); the resident may start on it but answers only once the
        same id comes back as "offen". Only a draft can be rewritten.

        zu: an addition to an earlier question still being worked on - the
        resident takes both together. von: "test" for test questions, which
        wait behind Calvin's."""
        text = (text or "").strip()
        if not text:
            return None, "Nichts gesagt"
        if gid:
            full = self._path(os.path.join("gespraech", str(gid) + ".json"))
            try:
                ok = (re.fullmatch(r"g-\d{10,16}", str(gid)) and full
                      and config.read_json(full).get("status") == "entwurf")
            except (OSError, ValueError, AttributeError):
                ok = False
            if not ok:
                gid = None             # answered already, or never there: a new question
        if not gid:
            # Two in the same millisecond must not overwrite each other.
            ms = int(_now() * 1000)
            while os.path.exists(os.path.join(self.dir, "gespraech", f"g-{ms}.json")):
                ms += 1
            gid = f"g-{ms}"
        body = {"id": gid, "ts": _now(), "text": text[:2000], "status": "entwurf" if draft else "offen"}
        if zu and re.fullmatch(r"g-\d{10,16}", str(zu)) and str(zu) != gid:
            body["zu"] = str(zu)
        if von in ("app", "test"):
            body["von"] = von
        # Ob gesprochen werden soll. Ohne Angabe: ja - alte Fragen und die Uhr
        # sollen sich nicht ploetzlich anders verhalten. Mit `false` spart es
        # rund eine Sekunde JE SATZ, die niemand hoert.
        if stimme is False:
            body["stimme"] = False
        if aufnahme and not draft:
            # How it was said: a WAV beside the question, for the resident's
            # ears (docs/BEWOHNER.md, Stufe 7 "Stimme verstehen").
            try:
                raw = base64.b64decode(aufnahme, validate=True)
            except ValueError:
                raw = b""
            if 44 < len(raw) <= 5 * 1024 * 1024 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
                wav = os.path.join(self.dir, "gespraech", gid + ".wav")
                os.makedirs(os.path.dirname(wav), exist_ok=True)
                with open(wav + ".iris.tmp", "wb") as fh:
                    fh.write(raw)
                os.replace(wav + ".iris.tmp", wav)
                body["aufnahme"] = f"gespraech/{gid}.wav"
        self._put(os.path.join(self.dir, "gespraech", gid + ".json"), json.dumps(body, ensure_ascii=False))
        return gid, ""

    AUDIO = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav"}

    def audio(self, rel):
        """A recording of an answer: (bytes, media type) or (None, why)."""
        rel = (rel or "").replace("\\", "/")
        ext = os.path.splitext(rel)[1].lower()
        full = self._path(rel)
        if not rel.startswith("gespraech/") or ext not in self.AUDIO or not full:
            return None, "Keine Aufnahme"
        if not os.path.isfile(full) or os.path.getsize(full) > 20 * 1024 * 1024:
            return None, "Aufnahme nicht gefunden"
        with open(full, "rb") as fh:
            return fh.read(), self.AUDIO[ext]

    def decide(self, rid, allow):
        if not rid or any(c in rid for c in "/\\.") or len(rid) > 80:
            return False, "Ungültiger Antrag"
        full = os.path.join(self.dir, "antraege", rid + ".json")
        try:
            r = config.read_json(full)
        except (OSError, ValueError):
            return False, "Antrag nicht gefunden"
        if r.get("status") != "offen":
            return False, f"Antrag ist schon {r.get('status')}"
        r["status"] = "genehmigt" if allow else "abgelehnt"
        r["decided"] = _now()
        # Who said so. Without it, a decision in the file looks as if it came
        # from nowhere - it cost half an hour to establish that an approval
        # had come from the app and not from the resident itself.
        r["entschieden_von"] = "App"
        self._put(full, json.dumps(r, ensure_ascii=False, indent=1))
        push.settled(f"antrag-{rid}")
        return True, ""

    # ---------- who it is and what it sees ----------

    def _text(self, name):
        try:
            with open(os.path.join(self.dir, name), encoding="utf-8-sig") as fh:
                return fh.read()[:20000]
        except OSError:
            return None

    def _data(self, name):
        try:
            return config.read_json(os.path.join(self.dir, name))
        except (OSError, ValueError):
            return None

    def self_view(self):
        """Its own notes (ICH.md, WUENSCHE.md), the situation read without a
        model (lage.json), the tools it built (werkzeuge.json), what it can
        do at all (faehigkeiten.json) and what Calvin showed it (eingang/) -
        docs/BEWOHNER.md, "Wer er ist"."""
        lage = self._lage(self._data("lage.json"))
        tools = self._tools(self._data("werkzeuge.json"))
        # Same shape as the tools, so both lists read alike: a tool is called,
        # a capability is simply there (its "aufruf" stays empty).
        can = self._tools(self._data("faehigkeiten.json"))
        return {"ich": self._text("ICH.md"), "wuensche": self._text("WUENSCHE.md"),
                "lage": lage if isinstance(lage, dict) else None,
                "werkzeuge": tools,
                "faehigkeiten": can,
                "eingang": self._eingang()}

    @staticmethod
    def _tools(tools):
        """The tools it built, as a list with a name - the resident may write
        them as a list or as one entry per name."""
        if isinstance(tools, dict):
            inner = tools.get("werkzeuge")
            if isinstance(inner, list):
                tools = inner
            else:
                tools = [{"name": name, **t} for name, t in tools.items() if isinstance(t, dict)]
        if not isinstance(tools, list):
            return []
        out = []
        for t in tools:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            geprueft = t.get("geprueft")
            out.append({"name": str(t["name"]), "zweck": t.get("zweck"), "aufruf": t.get("aufruf"),
                        "erstellt": t.get("erstellt"), "ergebnis": t.get("ergebnis"),
                        "geprueft": bool(geprueft)})
        return out

    @staticmethod
    def _lage(lage):
        """The situation as the app reads it (docs/BEWOHNER.md): "netz" with
        name, ip, seit and "nutzer_zuletzt" as a time - also when the resident
        writes "geraete" or "zuletzt_gesprochen_vor_s"."""
        if not isinstance(lage, dict):
            return None
        lage = dict(lage)
        if "netz" not in lage and isinstance(lage.get("geraete"), list):
            lage["netz"] = [{"name": g.get("name") or g.get("hostname"), "ip": g.get("ip"),
                             "mac": g.get("mac"), "seit": g.get("seit")}
                            for g in lage["geraete"] if isinstance(g, dict)]
        # Bis zum 28.09.2026 hiess das Feld nach dem Nutzer ("<name>_zuletzt"),
        # und ein Bewohner mit altem Code schreibt es noch so. Die App kennt den
        # Namen nicht, darum hier auf den festen Namen gebracht.
        alt = config.nutzer().lower() + "_zuletzt"
        if lage.get("nutzer_zuletzt") is None and lage.get(alt) is not None:
            lage["nutzer_zuletzt"] = lage.pop(alt)
        ago = lage.get("zuletzt_gesprochen_vor_s")
        if lage.get("nutzer_zuletzt") is None and isinstance(ago, (int, float)) and isinstance(lage.get("ts"), (int, float)):
            lage["nutzer_zuletzt"] = lage["ts"] - ago
        return lage

    def _eingang(self):
        d = os.path.join(self.dir, "eingang")
        out = []
        try:
            names = os.listdir(d)
        except OSError:
            return out
        for n in names:
            full = os.path.join(d, n)
            if n.startswith(".") or not os.path.isfile(full):
                continue
            st = os.stat(full)
            out.append({"path": "eingang/" + n, "size": st.st_size, "mtime": st.st_mtime, "editable": False})
        out.sort(key=lambda f: f["mtime"], reverse=True)
        return out[:20]

    SHOW_MAX = 20 * 1024 * 1024

    def put_in(self, name, data):
        """Something Calvin shows it from the app: into eingang/, never over
        an existing file. What it is, the resident finds out itself."""
        name = os.path.basename((name or "").replace("\\", "/")).strip()
        if not name or name.startswith(".") or len(name) > 120:
            return False, "Ungültiger Dateiname"
        try:
            raw = base64.b64decode(data or "", validate=True)
        except ValueError:
            return False, "Datei nicht lesbar"
        if not raw:
            return False, "Leere Datei"
        if len(raw) > self.SHOW_MAX:
            return False, "Zu groß – höchstens 20 MB"
        d = os.path.join(self.dir, "eingang")
        os.makedirs(d, exist_ok=True)
        stem, ext = os.path.splitext(name)
        full, i = os.path.join(d, name), 2
        while os.path.exists(full):
            full = os.path.join(d, f"{stem} ({i}){ext}")
            i += 1
        tmp = full + ".iris.tmp"
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, full)
        return True, ""

    # ---------- memory: read the database, change it by file ----------

    MEMORY_KINDS = ("fakt", "gespraech", "ereignis", "tagesrueckblick", "datei")

    def _memory_db(self):
        path = os.path.join(self.dir, "gedaechtnis.db")
        if not os.path.isfile(path):
            return None
        # Read only: the resident is the one writer.
        uri = "file:" + path.replace("\\", "/").replace("?", "%3F") + "?mode=ro"
        db = sqlite3.connect(uri, uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        return db

    # The same kind, however it was spelled - SQLite's lower() folds only
    # ASCII, so the umlaut spellings are listed as they are stored, lowered.
    KIND_ALIASES = {"fakt": "fakt", "gespraech": "gespraech", "gespräch": "gespraech",
                    "ereignis": "ereignis", "datei": "datei",
                    "tagesrueckblick": "tagesrueckblick", "tagesrückblick": "tagesrueckblick",
                    "rueckblick": "tagesrueckblick", "rückblick": "tagesrueckblick"}

    @classmethod
    def _kind(cls, art):
        a = (art or "").lower()
        return cls.KIND_ALIASES.get(a, a)

    @staticmethod
    def _stamp(ts):
        if isinstance(ts, (int, float)):
            return float(ts) / (1000 if ts > 1e12 else 1)
        try:
            return time.mktime(time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S"))
        except (TypeError, ValueError):
            try:
                return float(ts)
            except (TypeError, ValueError):
                return None

    def _row(self, r):
        keys = r.keys()
        get = lambda k: r[k] if k in keys else None
        return {"id": str(get("id")), "ts": self._stamp(get("ts")), "art": self._kind(get("art")),
                "text": get("text") or "", "quelle": get("quelle"), "wichtig": get("wichtig"),
                "ersetzt_durch": None if get("ersetzt_durch") in (None, "") else str(get("ersetzt_durch"))}

    @staticmethod
    def _match(q):
        """What you typed as an FTS5 query: the words that carry meaning,
        any of them, as a prefix.

        Joined by a space, FTS5 reads them as AND - "Wie heißt meine Tochter"
        then demanded all four words in one memory and found nothing, while
        the resident itself answered the same question. It searches with OR
        and drops words of two letters or less; so does this now, and bm25
        still puts the memory that matches most on top.
        """
        words = [w for w in re.findall(r"\w+", q or "", re.UNICODE) if len(w) > 2]
        return " OR ".join('"%s"*' % w for w in words[:8])

    def memories(self, q="", art="", limit=80, replaced=False):
        """What it remembers, newest first, or the best matches for q."""
        limit = max(1, min(int(limit or 80), 300))
        out = {"present": False, "memories": [], "counts": {}, "pending": self.memory_changes()}
        try:
            db = self._memory_db()
        except sqlite3.Error as e:
            out["error"] = f"Gedächtnis nicht lesbar: {e}"
            return out
        if db is None:
            return out
        try:
            out["present"] = True
            live = "" if replaced else " AND (e.ersetzt_durch IS NULL OR e.ersetzt_durch = '')"
            for r in db.execute("SELECT art, count(*) n FROM erinnerung e WHERE 1=1" + live + " GROUP BY art"):
                k = self._kind(r["art"])
                out["counts"][k] = out["counts"].get(k, 0) + r["n"]
            where, args = "1=1" + live, []
            if art:
                kinds = sorted(k for k, v in self.KIND_ALIASES.items() if v == self._kind(art)) or [art.lower()]
                where += " AND lower(e.art) IN (%s)" % ",".join("?" * len(kinds))
                args += kinds
            rows = None
            match = self._match(q)
            if match:
                try:
                    # Linked by rowid (external content) or by an id column
                    # of its own - whichever way the resident built it.
                    cols = [c[1] for c in db.execute("PRAGMA table_info(erinnerung_fts)")]
                    on = "f.id = e.id" if "id" in cols else "e.rowid = f.rowid"
                    rows = db.execute(
                        "SELECT e.* FROM erinnerung_fts f JOIN erinnerung e ON " + on + " "
                        "WHERE erinnerung_fts MATCH ? AND " + where + " ORDER BY bm25(erinnerung_fts) LIMIT ?",
                        [match] + args + [limit]).fetchall()
                except sqlite3.Error:
                    rows = None        # no full text index (yet): plain search
                if rows is None:
                    like = ["%" + w + "%" for w in re.findall(r"\w+", q)[:8]]
                    rows = db.execute(
                        "SELECT e.* FROM erinnerung e WHERE " + where
                        + "".join(" AND e.text LIKE ?" for _ in like) + " ORDER BY e.ts DESC LIMIT ?",
                        args + like + [limit]).fetchall()
            else:
                rows = db.execute("SELECT e.* FROM erinnerung e WHERE " + where + " ORDER BY e.ts DESC LIMIT ?",
                                  args + [limit]).fetchall()
            out["memories"] = [self._row(r) for r in rows]
        except sqlite3.Error as e:
            out["error"] = f"Gedächtnis nicht lesbar: {e}"
        finally:
            db.close()
        return out

    def memory(self, mid):
        """One memory with what replaced it, one after the other."""
        db = self._memory_db()
        if db is None:
            return None
        try:
            chain, seen = [], set()
            while mid and mid not in seen and len(chain) < 20:
                seen.add(mid)
                r = db.execute("SELECT * FROM erinnerung WHERE id = ? OR id = ?",
                               (mid, int(mid) if str(mid).isdigit() else mid)).fetchone()
                if r is None:
                    break
                chain.append(self._row(r))
                mid = chain[-1]["ersetzt_durch"]
            return chain or None
        except sqlite3.Error:
            return None
        finally:
            db.close()

    def memory_changes(self):
        """Corrections and forgettings the resident has not taken in yet."""
        d = os.path.join(self.dir, "gedaechtnis", "aenderungen")
        rows = []
        try:
            names = os.listdir(d)
        except OSError:
            return rows
        for n in names:
            if not n.endswith(".json"):
                continue
            try:
                r = config.read_json(os.path.join(d, n))
            except (OSError, ValueError):
                continue
            if isinstance(r, dict) and r.get("status", "offen") == "offen":
                rows.append({"id": str(r.get("id") or n[:-5]), "aktion": r.get("aktion"),
                             "text": r.get("text"), "ts": r.get("ts")})
        return rows

    def change_memory(self, mid, aktion, text=""):
        mid = str(mid or "")
        if not mid or len(mid) > 80 or not re.fullmatch(r"[\w-]+", mid):
            return False, "Ungültige Erinnerung"
        if aktion not in ("vergessen", "korrigieren"):
            return False, "Nur vergessen oder korrigieren"
        text = (text or "").strip()
        if aktion == "korrigieren" and not text:
            return False, "Was stimmt stattdessen?"
        body = {"id": mid, "aktion": aktion, "ts": _now(), "status": "offen", "von": "app"}
        if aktion == "korrigieren":
            body["text"] = text[:2000]
        self._put(os.path.join(self.dir, "gedaechtnis", "aenderungen", mid + ".json"),
                  json.dumps(body, ensure_ascii=False))
        return True, ""

    # ---------- the journal as a stream ----------

    def subscribe(self, since):
        q = queue.Queue()
        with self._lock:
            backlog = [c for c in self.cards if c["seq"] > since]
            self._subs.append(q)
        return q, backlog

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def _add(self, entry, live):
        """`live` heisst: das ist gerade geschehen, nicht nachgelesen.

        Die Unterscheidung stand bisher nur hier und entschied ueber den Push.
        Sie muss aber MIT der Karte gehen: Beim Start liest die Bruecke die
        letzten 200 KB Journal nach, und wer sich in diesem Augenblick
        verbindet, bekommt zwoelfhundert alte Zeilen durch den Strom - fuer
        ihn nicht von frischen zu unterscheiden. Am 13.09. um 19:15 landeten
        so alle alten Ansprachen in der Abspielschlange des Telefons, und
        Calvins Antwort stand dahinter.
        """
        with self._lock:
            self.seq += 1
            card = {**entry, "seq": self.seq, "live": bool(live)}
            self.cards.append(card)
            del self.cards[:-KEEP]
            subs = list(self._subs)
        for q in subs:
            q.put(card)
        if live:
            # MELDEN UND MITLESEN SIND ZWEI DINGE. Scheitert der Push, darf
            # das den Wächter nicht mitreissen: Am 13.09. warf `_tell` bei
            # JEDER neuen Zeile, und damit stand der Strom zur App still -
            # sie zeigte den Stand vom letzten Neustart und sah aus wie
            # kaputt. Ein Fehler im Melden beendet nie das Mitlesen.
            try:
                self._tell(card)
            except Exception:          # noqa: BLE001
                import traceback
                print("PUSH fehlgeschlagen: " + traceback.format_exc(),
                      flush=True)

    def _watch(self):
        # The journal every 0.2 s: an answer's text and its sound each waited
        # up to a second here before - a conversation feels that. Requests,
        # which mean reading every file, stay at once a second.
        n = 0
        while True:
            try:
                if self.present():
                    self._read_journal()
                    if n % 5 == 0:
                        self._check_requests()
                    n += 1
            except Exception:          # noqa: BLE001 - a bad line must not end the watch
                # ABER NICHT STILL. Eine verschluckte Ausnahme hier hat am
                # 13.09. drei Stunden gekostet: Der Leser las die Zeilen einer
                # Antwort, und drei davon kamen trotzdem nie an - weil
                # mittendrin etwas warf und der Rest der Schleife ausfiel.
                # Was hier passiert, steht ab jetzt in bridge.log.
                import traceback
                print("WAECHTER: " + traceback.format_exc(), flush=True)
            time.sleep(0.2 if self.present() else 10.0)

    def _read_journal(self):
        path = os.path.join(self.dir, "journal.jsonl")
        # DIE GROESSE KOMMT AUS DEM OFFENEN GRIFF, nicht aus dem Dateinamen.
        #
        # `os.path.getsize` liest den Verzeichniseintrag, und Windows schreibt
        # den fuer eine Datei, an die ein ANDERER Prozess gerade anhaengt, nur
        # traege fort. Der Leser sah die letzte Zeile darum oft gar nicht - und
        # das traf jede Antwort: Der Bewohner schreibt seine Saetze einzeln als
        # "stimme" und eine Millisekunde spaeter die Zeile "antwort", die im
        # Chat steht. Sie war im Journal und fehlte im Strom. Calvin hoerte
        # seine Antwort und sah sie nie.
        #
        # Gemessen: Im selben Prozess stimmt getsize auf das Byte - deshalb
        # ging die erste Probe durch, und deshalb hat es so lange gedauert,
        # das zu finden. Aus einem fremden Prozess stimmt es nicht.
        try:
            fh = open(path, "rb")
        except OSError:
            return
        with fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            first = self._offset is None
            if first:
                # What happened before the bridge started: the last stretch,
                # shown but not pushed again.
                self._offset = max(0, size - 200_000)
            if size < self._offset:    # the file was started anew
                self._offset, self._partial = 0, b""
            if size == self._offset:
                return
            fh.seek(self._offset)
            # NICHT `self._partial + ...`: Der Stand zeigt seit dieser
            # Aenderung schon auf den Anfang des Bruchstuecks, es wird also
            # ohnehin mitgelesen. Beides zusammen haette es verdoppelt.
            # Bis zum echten Ende lesen: Was zwischen dem Messen und dem
            # Lesen noch dazukam, gehoert mit.
            data = fh.read()
            size = self._offset + len(data)
        lines = data.split(b"\n")
        self._partial = lines.pop()
        # DER STAND GEHT NUR BIS ZUR LETZTEN GANZEN ZEILE.
        #
        # Vorher stand hier `self._offset = size`, und ein Bruchstueck wartete
        # im `_partial` darauf, dass die Datei weiterwaechst. Waechst sie
        # nicht, wartet es fuer immer: `if size == self._offset: return`
        # kommt nie wieder an dieser Stelle vorbei.
        #
        # Genau das trifft JEDE Antwort. Der Bewohner schreibt seine Saetze
        # einzeln als "stimme" und ganz zuletzt die Zeile "antwort" - die,
        # die im Chat steht. Sie ist die letzte Schreiboperation, der Leser
        # sieht sie oft halb, und danach passiert minutenlang nichts mehr.
        # Gemessen am 13.09. um 20:05: Calvin hoerte die Antwort, sah aber
        # keinen Text; im Journal stand sie, im Strom fehlte sie.
        #
        # Jetzt zeigt der Stand auf den Anfang des Bruchstuecks. Der naechste
        # Durchgang liest es neu - und sobald die Zeile vollstaendig ist,
        # kommt sie an.
        self._offset = size - len(self._partial)
        if first and self._offset > 0 and lines and data[:1] != b"{":
            lines = lines[1:]          # started mid-line
        for raw in lines:
            try:
                entry = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get("kind"):
                self._add(entry, live=not first)

    def _check_requests(self):
        rows = self.requests()
        ids = {r["id"] for r in rows}
        if self._requests_seen is None:
            self._requests_seen = ids
            return
        for r in rows:
            if r["id"] not in self._requests_seen and r.get("status") == "offen":
                self._push_request(r)
        self._requests_seen = ids

    # ---------- telling the phone ----------

    def _name(self):
        try:
            return (config.read_json(os.path.join(self.dir, "bewohner.json")) or {}).get("name") or "Bewohner"
        except (OSError, ValueError, AttributeError):
            return "Bewohner"

    def _tell(self, card):
        kind = card.get("kind")
        if kind == "stop" and _now() - self._stopped_by_app < 30:
            return                     # you stopped it yourself
        # erinnerung: something Calvin asked to be reminded of, due now;
        # ansprache: something it wants to tell him on its own.
        subtitle = {"fund": "bemerkt", "fehler": "Fehler", "stop": "angehalten",
                    "erinnerung": "Erinnerung", "ansprache": "möchte dir etwas sagen"}.get(kind)
        if not subtitle:
            return
        # A finding straight from the situation picture is not news by itself:
        # a device arriving there also becomes an "ansprache", and Calvin got
        # the same thing twice. "10:00 begann der Vormittag" is of that kind
        # too, and nobody wants that as a notification. It all stays in the
        # journal, the memory and the review - only the push is dropped.
        # Ein Fund stoert das Telefon nur, wenn er KRITISCH ist. Am 12.09. um
        # 21:04 standen 55 Mitteilungen auf Calvins Sperrbildschirm: der
        # Bewohner ging seinen Desktop durch und meldete jede Datei einzeln -
        # Spielverknuepfungen, .url-Dateien, Bildschirmfotos, "0 Kilobyte, Art
        # unbekannt". Seine privaten Dateien, und keine davon eine Nachricht
        # wert. Umgekehrt gibt es Funde, die sofort stoeren duerfen: eine
        # volle Platte, ein toter Dienst, etwas Sicherheitsrelevantes.
        #
        # Entscheidend ist deshalb nicht die Art, sondern das Gewicht. Der
        # Bewohner setzt es selbst (kritisch/dringend), und wo er nichts sagt,
        # entscheiden Woerter, die keinen Zweifel lassen. Alles andere bleibt
        # im Journal, im Gedaechtnis, im Rueckblick und in der App sichtbar -
        # nur das Telefon bleibt still.
        if kind == "fund" and not _kritisch(card):
            return
        push.send({"aps": {"alert": {"title": self._name(), "subtitle": subtitle,
                                     "body": (card.get("text") or "")[:240]},
                           "sound": "default", "thread-id": "bewohner"},
                   "iris": {"kind": "resident", "machine": config.machine_name()}})

    def _push_request(self, r):
        rid = f"antrag-{r['id']}"
        push.send({"aps": {"alert": {"title": self._name(), "subtitle": "Antrag: " + (r.get("title") or ""),
                                     "body": (r.get("reason") or "")[:240]},
                           "sound": "default", "category": "ANTRAG", "thread-id": "bewohner",
                           "interruption-level": "time-sensitive"},
                   "iris": {"kind": "antrag", "id": r["id"], "request_id": rid,
                            "machine": config.machine_name()}},
                  collapse=rid[:64])
        push._pushed.add(rid)


# Woerter, die einen Fund zur Stoerung berechtigen. Bewusst kurz gehalten:
# was hier fehlt, bleibt still, und das ist der sichere Fall.
# Umlaute in beiden Schreibweisen: der Bewohner schreibt mal "laeuft", mal
# "laeuft" mit Umlaut - je nachdem, was durch die Kodierung kommt. Ein Muster,
# das nur eine Form kennt, laesst den Ernstfall durchrutschen.
_KRITISCH = re.compile(
    r"\b(kein Platz|Platte (ist )?voll|kaum noch|nur noch \d+ ?(MB|GB|Prozent|%)|"
    r"abgest(ü|ue|u)rzt|gestorben|antwortet nicht|reagiert nicht|"
    r"nicht mehr erreichbar|fehlgeschlagen|Datenverlust|besch(ä|ae|a)digt|"
    r"unbefugt|fremder Zugriff|Kennwort|Passwort|Schl(ü|ue|u)ssel)\b",
    re.IGNORECASE)


def _kritisch(card):
    """Darf dieser Fund das Telefon stoeren?

    Zuerst das, was der Bewohner selbst sagt - er kennt den Zusammenhang.
    Sagt er nichts, entscheidet der Wortlaut, und im Zweifel bleibt es still:
    Ein verpasster Hinweis steht im Journal, eine verpasste Nacht nicht.
    """
    for feld in ("kritisch", "dringend"):
        if card.get(feld):
            return True
    if str(card.get("gewicht") or "").lower() in ("kritisch", "dringend", "hoch"):
        return True
    # Bewusst OHNE Ausnahme fuer das Lagebild: "kein Platz mehr auf C" kommt
    # von dort und gehoert genau dann aufs Telefon. Das Lagebild war frueher
    # pauschal ausgenommen, weil daraus Doppelmeldungen wurden - dagegen
    # hilft jetzt, dass ueberhaupt nur Kritisches durchkommt.
    return bool(_KRITISCH.search(card.get("text") or ""))


_instance = None
_instance_lock = threading.Lock()


def get(cfg):
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = Resident(cfg)
        return _instance
