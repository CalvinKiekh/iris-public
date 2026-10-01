"""Keys into a Windows console and its screen as text - on Windows what
Terminal.app's AppleScript does on the Mac.

Every call is a process of its own (python -m bridge.wincon read|keys PID,
keys as JSON on stdin): attaching to a console belongs to the whole
process, and a bridge attached to someone's console would hand that
console to every program it starts in the meantime.
"""
import ctypes
import json
import sys
import time

if sys.platform == "win32":
    from ctypes import wintypes as w
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)

    class COORD(ctypes.Structure):
        _fields_ = [("X", w.SHORT), ("Y", w.SHORT)]

    class SMALL_RECT(ctypes.Structure):
        _fields_ = [("Left", w.SHORT), ("Top", w.SHORT), ("Right", w.SHORT), ("Bottom", w.SHORT)]

    class CSBI(ctypes.Structure):
        _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD), ("wAttributes", w.WORD),
                    ("srWindow", SMALL_RECT), ("dwMaximumWindowSize", COORD)]

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [("bKeyDown", w.BOOL), ("wRepeatCount", w.WORD), ("wVirtualKeyCode", w.WORD),
                    ("wVirtualScanCode", w.WORD), ("uChar", w.WCHAR), ("dwControlKeyState", w.DWORD)]

    class _EVENT(ctypes.Union):
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("_pad", ctypes.c_byte * 16)]

    class INPUT_RECORD(ctypes.Structure):
        _fields_ = [("EventType", w.WORD), ("Event", _EVENT)]

KEY_EVENT = 0x0001
CHUNK = 100                            # characters per write
PAUSE = 0.04                           # seconds between writes
SHIFT_PRESSED = 0x0010
LEFT_CTRL_PRESSED = 0x0008
# Named keys: virtual key and the character a console reader sees.
KEYS = {"enter": (0x0D, "\r"), "esc": (0x1B, "\x1b"), "tab": (0x09, "\t"),
        "backspace": (0x08, "\b")}


def _open(pid, name):
    k32.FreeConsole()
    if not k32.AttachConsole(int(pid)):
        raise OSError(f"AttachConsole {ctypes.get_last_error()}")
    k32.CreateFileW.restype = w.HANDLE
    h = k32.CreateFileW(name, 0xC0000000, 3, None, 3, 0, None)
    if h in (None, -1, ctypes.c_void_p(-1).value):
        raise OSError(f"CreateFile {ctypes.get_last_error()}")
    # As a HANDLE, not a Python int: ctypes would pass that as a 32-bit int.
    return w.HANDLE(h)


def read(pid):
    """The visible part of the console, line by line."""
    h = _open(pid, "CONOUT$")
    info = CSBI()
    if not k32.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
        raise OSError(f"GetConsoleScreenBufferInfo {ctypes.get_last_error()}")
    width, lines = info.dwSize.X, []
    for y in range(info.srWindow.Top, info.srWindow.Bottom + 1):
        buf, n = ctypes.create_unicode_buffer(width + 1), w.DWORD()
        k32.ReadConsoleOutputCharacterW(h, buf, width, COORD(0, y), ctypes.byref(n))
        lines.append(buf.value[:n.value].rstrip())
    return lines


def _record(vk, ch, state, down):
    r = INPUT_RECORD()
    r.EventType = KEY_EVENT
    e = r.Event.KeyEvent
    e.bKeyDown, e.wRepeatCount, e.wVirtualKeyCode = bool(down), 1, vk
    e.wVirtualScanCode = u32.MapVirtualKeyW(vk, 0) if vk else 0
    e.uChar, e.dwControlKeyState = ch, state
    return r


def _char(ch):
    scan = u32.VkKeyScanW(ch) if len(ch) == 1 else -1
    vk = scan & 0xFF if scan not in (-1, 0xFFFF) else 0
    return vk, ch, SHIFT_PRESSED if scan != -1 and scan & 0x100 else 0


def records(steps):
    """[{"text": ...} | {"key": name, "shift": bool, "ctrl": bool}] -> key
    events, down and up for each."""
    out = []
    for s in steps:
        if "text" in s:
            units = s["text"].encode("utf-16-le")
            chars = [units[i:i + 2].decode("utf-16-le", "surrogatepass") for i in range(0, len(units), 2)]
            pairs = [_char(c) for c in chars]
        elif s.get("key") == "ctrl-c":
            pairs = [(0x43, "\x03", LEFT_CTRL_PRESSED)]
        else:
            vk, ch = KEYS[s["key"]]
            pairs = [(vk, ch, SHIFT_PRESSED if s.get("shift") else 0)]
        for vk, ch, state in pairs:
            out += [_record(vk, ch, state, True), _record(vk, ch, state, False)]
    return out


def keys(pid, steps):
    h = _open(pid, "CONIN$")
    for s in steps:
        if s.get("wait"):
            time.sleep(float(s["wait"]))
            continue
        # Long text in pieces with a breath between: Claude Code on Windows
        # drops the beginning of a large burst (messages over ~1000 characters
        # arrived with only their end, 11.09.2026).
        text = s.get("text")
        parts = [{"text": text[i:i + CHUNK]} for i in range(0, len(text), CHUNK)] if text else [s]
        for n_part, part in enumerate(parts):
            if n_part:
                time.sleep(PAUSE)
            recs = records([part])
            arr = (INPUT_RECORD * len(recs))(*recs)
            n = w.DWORD()
            if not k32.WriteConsoleInputW(h, arr, len(recs), ctypes.byref(n)) or n.value != len(recs):
                raise OSError(f"WriteConsoleInput {ctypes.get_last_error()}")


def main(argv):
    op, pid = argv[1], int(argv[2])
    try:
        if op == "read":
            result = {"lines": read(pid)}
        elif op == "keys":
            keys(pid, json.loads(sys.stdin.read() or "[]"))
            result = {"ok": True}
        else:
            result = {"error": f"unbekannt: {op}"}
    except (OSError, KeyError, ValueError) as e:
        result = {"error": str(e)}
    finally:
        if sys.platform == "win32":
            k32.FreeConsole()
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main(sys.argv)
