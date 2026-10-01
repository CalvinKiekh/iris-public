#!/usr/bin/env python3
"""Turn a .dc.html artboard into a plain page, so it can be looked at.

The canvas editor does not render outside the published artifact, which is
how a bad draft slipped through unseen. An artboard is ordinary HTML under
the wrapper, so stripping the wrapper is enough to see it.
"""
import re
import sys
from pathlib import Path


def plain(src: str) -> str:
    src = src.replace('<script src="./support.js"></script>', "")
    # <helmet> holds the head content; lift it out of the body.
    head = ""
    m = re.search(r"<helmet>(.*?)</helmet>", src, re.S)
    if m:
        head = m.group(1)
        src = src.replace(m.group(0), "")
    src = re.sub(r"</?x-dc>", "", src)
    body = re.search(r"<body>(.*?)</body>", src, re.S)
    body = body.group(1) if body else src
    return f"""<!doctype html><html><head><meta charset="utf-8">{head}
<style>html,body{{margin:0;padding:0;background:#111}}</style>
</head><body>{body}</body></html>"""


if __name__ == "__main__":
    parts = []
    for name in sys.argv[1:]:
        # Scaled down so a whole artboard fits in one screenshot - looking at
        # a cropped draft is how the last bad one slipped through.
        doc = plain(Path(name).read_text()).replace(chr(34), "&quot;")
        parts.append(
            f'<div style="width:{int(600*0.62)}px;height:{int(880*0.62)}px;'
            f'display:inline-block;vertical-align:top;overflow:hidden;margin:0 10px 0 0">'
            f'<iframe srcdoc="{doc}" style="width:600px;height:880px;border:0;'
            f'transform:scale(.62);transform-origin:top left"></iframe></div>')
    Path("../web/_vorschau.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Vorschau</title>'
        '<style>body{margin:0;background:#111;white-space:nowrap;overflow-x:auto}</style>'
        + "".join(parts))
    print("geschrieben:", len(sys.argv) - 1, "Artboard(s)")
