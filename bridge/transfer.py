"""Eine grosse Datei auf einen anderen Rechner bringen, am Repository vorbei.

Der normale Weg einer Uebergabe ist git: das Ziel klont oder zieht, und alles
ist da. Was GitHub nicht annimmt - eine 124-MB-Tabelle, ein Messdatensatz -
faellt dabei heraus. Dafuer ist diese Datei da.

Die Datei reist versiegelt. Nicht weil der Weg unsicher waere - er laeuft ueber
Tailscale und einen Token -, sondern weil sie unterwegs zwischengelagert wird:
ein abgebrochener Transfer, ein Rest im Spool, ein Backup, das ihn mitnimmt.
Versiegelt liegt dort Rauschen.

Was das NICHT schuetzt, damit sich niemand in einem Jahr darauf verlaesst:
ein uebernommenes Zielgeraet, eine uebernommene Bruecke, und die Datei selbst,
sobald sie abgelegt ist - danach liegt sie im Klartext wie jede andere. Der
Schluessel reist ueber dieselbe token-gesicherte Verbindung wie die Daten, es
ist also EIN Schloss, nicht zwei. Wer den Token hat, bekommt beides.

Die sechs Regeln, die beim Bauen nicht verhandelbar waren:

  1. Zaehler-Nonce. GCM stirbt an einem wiederholten Nonce unter demselben
     Schluessel - nicht "wird schwaecher", sondern gibt den Authentisierungs-
     schluessel preis. Der Nonce ist hier der Blockzaehler, nie gewuerfelt,
     und jeder Schluessel sieht genau eine Datei.
  2. Siegel vor Verwendung. GCM liefert Klartext, bevor es die Pruefsumme
     prueft. Nichts damit tun, bevor der Tag stimmt: erst vollstaendig in
     die Temp-Datei, dann umbenennen. Faellt die Pruefung durch: loeschen.
  3. Ziel auf das Arbeitsverzeichnis begrenzt. Der Dateiname kommt von der
     Gegenseite und ist gefaehrlicher als der Schluessel.
  4. Schluessel nach Gebrauch weg, nicht nach Ablauf. Sonst laesst sich
     derselbe Klotz spaeter noch einmal einspielen.
  5. Der Aufkleber wird vom Ziel selbst gebaut, nie aus dem uebernommen,
     was der Absender behauptet - sonst ist er Dekoration.
  6. Der Schluessel geht nie in eine Karte, eine Spur oder eine Push-Nutzlast.
     Genau dort liegen die Sitzungskennungen heute im Klartext.
"""
import os
import secrets
import shutil
import threading
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config

# 1 MiB plain per block. Small enough that a failed transfer wastes little,
# large enough that the per-block tag (16 bytes) costs nothing worth naming.
BLOCK = 1024 * 1024
TAG = 16
# A ceiling, so a sender cannot fill the disk. Well above what anyone hands
# over by hand, well below what would hurt.
MAX_BYTES = 2 * 1024 * 1024 * 1024
# How long a key waits for its blob. Short: the app sends both in one go.
TICKET_TTL = 300
# How long a sealed blob may lie in the spool before it is swept.
SPOOL_TTL = 3600

AUSGANG = os.path.join(config.CONFIG_DIR, "ausgang")


def _aad(sitzung, ziel, name, i, n):
    """The label sealed along with each block.

    Length-prefixed, so no field can be made to look like another by putting
    a separator in a filename. Carries the block number and the total: a
    stream cut short is missing blocks, and every remaining block says how
    many there should have been.
    """
    teile = [b"iris-transfer-1", sitzung.encode(), ziel.encode(),
             name.encode(), str(i).encode(), str(n).encode()]
    return b"".join(len(t).to_bytes(2, "big") + t for t in teile)


def sicherer_name(name):
    """The filename reduced to something that cannot leave a directory.

    Basename only, no separators, no leading dot, no exotic length. This is
    the rule that matters most here - a path from another machine is the
    classic way to write where nobody meant to.
    """
    name = os.path.basename((name or "").strip().replace("\\", "/").split("/")[-1])
    if not name or name in (".", "..") or name.startswith("."):
        return ""
    if len(name.encode()) > 200 or "\x00" in name:
        return ""
    return name


def _fegen(ordner, ttl):
    """Leftovers from transfers that never finished."""
    try:
        jetzt = time.time()
        for f in os.listdir(ordner):
            p = os.path.join(ordner, f)
            try:
                if jetzt - os.path.getmtime(p) > ttl:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


# ---------- Absenderseite: versiegeln ----------

def versiegeln(cwd, sitzung, ziel, pfad):
    """Seal one file out of a session's working directory.

    Hands the key back ONCE, to the caller, and keeps no copy of it - not on
    disk, not in a card, not in the log. The sealed blob goes to the spool;
    without the key it is noise (rule 6).
    """
    name = sicherer_name(pfad)
    if not name:
        return {"ok": False, "grund": "Unbrauchbarer Dateiname"}
    if not (ziel or "").strip():
        return {"ok": False, "grund": "Kein Zielrechner genannt"}

    # Read, not written - but still only from inside the session. A handover
    # is not a file browser. realpath on both sides, so a symlink pointing
    # out of the tree does not count as inside it.
    wurzel = os.path.realpath(cwd)
    quelle = os.path.realpath(os.path.join(cwd, pfad))
    if quelle != wurzel and not quelle.startswith(wurzel + os.sep):
        return {"ok": False, "grund": "Datei liegt nicht im Arbeitsverzeichnis"}
    if not os.path.isfile(quelle):
        return {"ok": False, "grund": "Datei gibt es nicht"}
    gross = os.path.getsize(quelle)
    if not gross:
        return {"ok": False, "grund": "Datei ist leer"}
    if gross > MAX_BYTES:
        return {"ok": False, "grund": "Datei ist groesser als %d GiB"
                                      % (MAX_BYTES // (1024 ** 3))}

    os.makedirs(AUSGANG, exist_ok=True)
    _fegen(AUSGANG, SPOOL_TTL)

    bloecke = (gross + BLOCK - 1) // BLOCK
    schluessel = secrets.token_bytes(32)
    gcm = AESGCM(schluessel)
    kennung = secrets.token_hex(16)
    ablage = os.path.join(AUSGANG, kennung + ".bin")

    try:
        with open(quelle, "rb") as ein, open(ablage, "wb") as aus:
            for i in range(bloecke):
                stueck = ein.read(BLOCK)
                if not stueck:
                    break
                # Rule 1: the nonce is the block counter, never rolled, and
                # this key will not see a second file.
                siegel = gcm.encrypt(i.to_bytes(12, "big"), stueck,
                                     _aad(sitzung, ziel, name, i, bloecke))
                aus.write(len(siegel).to_bytes(4, "big"))
                aus.write(siegel)
    except OSError as e:
        try:
            os.remove(ablage)
        except OSError:
            pass
        return {"ok": False, "grund": "Lesen fehlgeschlagen: %s" % e}

    return {"ok": True, "id": kennung, "name": name, "bytes": gross,
            "bloecke": bloecke, "versiegelt": os.path.getsize(ablage),
            "ziel": ziel, "schluessel": schluessel.hex()}


def ausgang_pfad(kennung):
    """The sealed blob for a handle, if it is still in the spool."""
    if not kennung or len(kennung) != 32 or \
       not all(c in "0123456789abcdef" for c in kennung):
        return ""
    p = os.path.join(AUSGANG, kennung + ".bin")
    return p if os.path.isfile(p) else ""


def ausgang_weg(kennung):
    """Once it has travelled, it has no reason to lie around."""
    p = ausgang_pfad(kennung)
    if p:
        try:
            os.remove(p)
        except OSError:
            pass


# ---------- Empfaengerseite: Schluessel entgegennehmen ----------

_karten = {}
_schloss = threading.Lock()


def schluessel_annehmen(sitzung, name, bloecke, schluessel_hex):
    """Take a key and hand back a ticket to send the blob against.

    The key goes nowhere near the disk - it waits in memory for its blob and
    is gone afterwards, used or not.
    """
    name = sicherer_name(name)
    if not name:
        return {"ok": False, "grund": "Unbrauchbarer Dateiname"}
    try:
        roh = bytes.fromhex(schluessel_hex or "")
    except ValueError:
        roh = b""
    if len(roh) != 32:
        return {"ok": False, "grund": "Schluessel hat die falsche Laenge"}
    try:
        bloecke = int(bloecke)
    except (TypeError, ValueError):
        bloecke = 0
    if not 0 < bloecke <= (MAX_BYTES // BLOCK) + 1:
        return {"ok": False, "grund": "Unglaubwuerdige Blockzahl"}

    ticket = secrets.token_hex(16)
    with _schloss:
        jetzt = time.time()
        for t in [t for t, e in _karten.items() if e["bis"] < jetzt]:
            _karten.pop(t, None)
        _karten[ticket] = {"schluessel": roh, "sitzung": sitzung, "name": name,
                           "bloecke": bloecke, "bis": jetzt + TICKET_TTL}
    return {"ok": True, "ticket": ticket, "name": name,
            "gueltig": TICKET_TTL}


def _ticket_ziehen(ticket):
    """Rule 4: one use, then gone - not gone on expiry.

    Taken out of the store before the blob is even read, so the same sealed
    file cannot be played in a second time later over a file that has since
    been worked on.
    """
    with _schloss:
        eintrag = _karten.pop(ticket, None)
    if not eintrag:
        return None
    if eintrag["bis"] < time.time():
        return None
    return eintrag


def _freier_name(ordner, name):
    """A name that does not overwrite anything.

    Landing on top of a file somebody is working on is worse than an ugly
    name. lexists, not exists: a dangling symlink also counts as taken.
    """
    ziel = os.path.join(ordner, name)
    if not os.path.lexists(ziel):
        return ziel
    stamm, endung = os.path.splitext(name)
    for i in range(2, 100):
        ziel = os.path.join(ordner, "%s (%d)%s" % (stamm, i, endung))
        if not os.path.lexists(ziel):
            return ziel
    return ""


def oeffnen(ticket, strom, cwd):
    """Unseal a blob into a session's working directory.

    `strom` is read block by block, so a large file never sits in memory
    whole. Nothing is put where it belongs until every seal has checked out
    (rule 2): GCM hands over plaintext before it verifies the tag, so the
    plaintext lands under a temporary name first and is renamed only at the
    end. Anything that fails leaves nothing behind.
    """
    eintrag = _ticket_ziehen(ticket)
    if not eintrag:
        return {"ok": False, "grund": "Ticket ist unbekannt oder abgelaufen"}

    name, bloecke = eintrag["name"], eintrag["bloecke"]
    gcm = AESGCM(eintrag["schluessel"])
    # Rule 5: the label is built from what this machine already knows - its
    # own name, the session it was told about, the name it sanitised itself.
    # Sealed for another machine or another session, and the tag fails.
    ziel_name = config.machine_name()
    sitzung = eintrag["sitzung"] or ""

    if not os.path.isdir(cwd):
        return {"ok": False, "grund": "Arbeitsverzeichnis gibt es nicht"}
    roh = os.path.join(cwd, ".iris-eingang-%s.teil" % secrets.token_hex(8))

    gelesen = 0
    try:
        # O_EXCL so nothing existing is taken over, O_NOFOLLOW so a symlink
        # planted under that name cannot redirect the write.
        fd = os.open(roh, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as aus:
            for i in range(bloecke):
                kopf = _genau(strom, 4)
                if len(kopf) < 4:
                    raise InvalidTag("Strom endet vor Block %d" % i)
                laenge = int.from_bytes(kopf, "big")
                if not TAG < laenge <= BLOCK + TAG:
                    raise InvalidTag("Block %d hat eine unglaubwuerdige Laenge" % i)
                siegel = _genau(strom, laenge)
                if len(siegel) < laenge:
                    raise InvalidTag("Block %d ist abgeschnitten" % i)
                klar = gcm.decrypt(i.to_bytes(12, "big"), siegel,
                                   _aad(sitzung, ziel_name, name, i, bloecke))
                aus.write(klar)
                gelesen += len(klar)
        # Nothing may follow the last block: a sender that appends is not
        # sending the file that was announced.
        if _genau(strom, 1):
            raise InvalidTag("Nach dem letzten Block steht noch etwas")
    except (InvalidTag, OSError, ValueError) as e:
        try:
            os.remove(roh)
        except OSError:
            pass
        grund = "Siegel passt nicht" if isinstance(e, InvalidTag) else str(e)
        return {"ok": False, "grund": grund}

    fertig = _freier_name(cwd, name)
    if not fertig:
        os.remove(roh)
        return {"ok": False, "grund": "Kein freier Name im Arbeitsverzeichnis"}
    try:
        os.replace(roh, fertig)
    except OSError as e:
        try:
            os.remove(roh)
        except OSError:
            pass
        return {"ok": False, "grund": "Ablegen fehlgeschlagen: %s" % e}
    return {"ok": True, "name": os.path.basename(fertig), "bytes": gelesen,
            "pfad": os.path.relpath(fertig, cwd)}


def _genau(strom, n):
    """Read exactly n bytes, or as many as there are.

    A socket hands over what has arrived, not what was asked for; a single
    read would cut blocks apart and every seal after it would fail.
    """
    teile, fehlt = [], n
    while fehlt > 0:
        stueck = strom.read(fehlt)
        if not stueck:
            break
        teile.append(stueck)
        fehlt -= len(stueck)
    return b"".join(teile)


class Begrenzt:
    """A stream that ends where the request body ends.

    Needed for the check that nothing follows the last block: reading one
    byte past a body whose length matched exactly would sit and wait on a
    connection the client is keeping open. Here that read returns empty,
    which is the answer the check wants.
    """

    def __init__(self, strom, laenge):
        self.strom = strom
        self.uebrig = max(0, int(laenge))

    def read(self, n=-1):
        if self.uebrig <= 0:
            return b""
        if n is None or n < 0:
            n = self.uebrig
        stueck = self.strom.read(min(n, self.uebrig))
        self.uebrig -= len(stueck)
        return stueck
