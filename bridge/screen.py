"""Claude's text as the terminal shows it, read from the Terminal.app tab.

Neither of the other two sources is complete. The transcript leaves out most
sentences written between tool calls. The display hook (MessageDisplay)
carries them, but in long sessions it arrives late or stops arriving
altogether. The terminal itself always shows them - it is what the person at
the Mac reads - and Terminal.app hands out a tab's whole scrollback in a
fifth of a second. So for a session in Terminal.app the text comes from
there, and only from there: one source per piece of information.

What the screen looks like (Claude Code 2.1):

    ❯ the prompt, wrapped
      at the terminal width
    ⏺ A sentence Claude wrote, wrapped
      with a two-space indent.

      - a list item
    ⏺ Bash(ls -la)
      ⎿  output of the tool
      Read 1 file (ctrl+o to expand)
    ✻ Worked for 16s · done 15:00

Tools and results are left alone - the transcript has them in full.
"""
import re

# "⏺ Bash(", "⏺ Read(", "⏺ Update(", "⏺ claude-in-chrome - navigate (MCP)("
_TOOL = re.compile(r"^⏺ [\w.:-]+(?: - [^()\n]+?(?: \(MCP\))?)?\(")
# A tool call as the terminal draws it, "Bash(", "Read(", "Update(",
# "claude-in-chrome - navigate (MCP)(" - also without its bullet: the ⏺ of a
# running call blinks, and a look at the wrong moment sees only the rest.
_CALL = re.compile(r"^[A-Z][\w.:-]*(?: - [^()\n]+?(?: \(MCP\))?)?\(")
# A new line inside a paragraph that is not a wrapped continuation.
_ITEM = re.compile(r"^(?:[-*•] |\d+[.)] |[│|┃])")
# What closes a block for certain: the next block or tool call, the prompt,
# a tool result, or the line at the end of a turn ("✻ Worked for 16s · …").
# Anything else - the spinner, the input box's border drawn right under text
# that is still streaming - leaves it open.
_DONE = re.compile(r"^\S+ \S+ for \d+(?:\.\d+)?[smh]\b(?!.*…)")


def _closes(line):
    # "(ctrl+o to expand)": the folded summary of the tool calls that came
    # right after the text ("Read 1 file", "Called claude-in-chrome 2 times").
    return (line.startswith(("⏺", "❯")) or line.lstrip().startswith("⎿")
            or "(ctrl+o to expand)" in line or bool(_DONE.match(line)))


# Lines with a bullet that are not Claude's text: the folded summary of a
# run of tool calls ("Searching for 1 pattern, reading 1 file… (ctrl+o to
# expand)") - which Claude Code rewrites once the calls are through, so a
# block made of it would not be found again - and notices of work that ran on
# its own ("Background command "…" completed (exit code 0)").
_NOT_TEXT = re.compile(r"^⏺ (?:.*\(ctrl\+o to expand\)\s*$"
                       r"|(?:Background command|Agent|Task) \".*\" (?:completed|failed|was stopped|killed))")


def blocks(history):
    """Every text block on the screen, oldest first: [(text, complete)].

    A block is complete once something follows it - a tool call, the next
    block, the prompt, the "Worked for" line. Followed only by a spinner it
    may still be growing."""
    out = []
    cur = None
    for raw in history.split("\n"):
        line = raw.rstrip()
        if _NOT_TEXT.match(line):
            if cur is not None and any(l.strip() for l in cur):
                out.append((cur, True))
            cur = None
            continue
        if line.startswith("⏺ ") and not _TOOL.match(line):
            if cur is not None:
                out.append((cur, True))
            cur = [line[2:]]
            continue
        if cur is None:
            continue
        if line.startswith("      ") or _CALL.match(line[2:] if line.startswith("  ") else line):
            # Six spaces or more: a tool's command or output drawn under its
            # header - prose wraps with two, list items with four, also after
            # a blank line. And a line that starts like a tool call is one.
            if any(l.strip() for l in cur):
                out.append((cur, True))
            cur = None
            continue
        if line == "" or (line.startswith("  ") and not line.lstrip().startswith("⎿")
                          and "(ctrl+o to expand)" not in line):
            cur.append(line[2:] if line.startswith("  ") else "")
            continue
        out.append((cur, _closes(line)))
        cur = None
    if cur is not None:
        out.append((cur, False))
    return [(_join(lines), done) for lines, done in out if _join(lines)]


_BORDER = ("┌", "├", "└")


def _tables(lines):
    """Tables the terminal drew with box lines, back to Markdown.

    On screen a table is ┌─┬─┐, rows between │, a ├─┼─┤ between every two
    rows, └─┴─┘ at the end - and a cell too long for its column wraps onto a
    further line at the same │ positions. Read as prose it came out as a
    heap of dashes. Here the lines of each row are merged per cell; the first
    row is the header."""
    out, i = [], 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("┌"):
            out.append(lines[i])
            i += 1
            continue
        rows, group = [], []
        i += 1
        while i < len(lines):
            t = lines[i].strip()
            if t.startswith("│"):
                group.append([c.strip() for c in t.strip("│").split("│")])
            elif t.startswith(_BORDER):
                if group:
                    width = max(len(g) for g in group)
                    rows.append([" ".join(g[k] for g in group if k < len(g) and g[k]).strip()
                                 for k in range(width)])
                    group = []
                if t.startswith("└"):
                    i += 1
                    break
            else:
                break
            i += 1
        if rows:
            out.append("| " + " | ".join(rows[0]) + " |")
            out.append("|" + "|".join("---" for _ in rows[0]) + "|")
            out.extend("| " + " | ".join(r) + " |" for r in rows[1:])
    return out


def _join(lines):
    """Undo the wrapping at the terminal width; keep paragraphs and items."""
    lines = _tables(lines)
    paragraphs, cur = [], []
    for line in lines + [""]:
        if not line.strip():
            if cur:
                paragraphs.append("\n".join(cur))
                cur = []
            continue
        stripped = line.strip()
        if not cur or _ITEM.match(stripped):
            cur.append(stripped)
        else:
            cur[-1] += " " + stripped
    return "\n\n".join(paragraphs).strip()


def since(history, anchor, anchor_count, take_last=False):
    """The complete blocks after the last one already taken.

    `anchor` is that block's text and `anchor_count` how often it occurred
    up to it - text can repeat ("Fertig."), and the scrollback may have lost
    its oldest lines, so a position alone would not do. Returns (new blocks,
    new anchor, new count).

    `take_last` counts the last block as done even with only a spinner
    after it - when the transcript already says a tool call followed it,
    the sentence is finished, the screen just has not drawn the call yet."""
    found = blocks(history)
    if take_last and found:
        found[-1] = (found[-1][0], True)
    done = [text for text, complete in found if complete]
    start = 0
    if anchor is not None:
        seen = 0
        for i, text in enumerate(done):
            if text == anchor:
                seen += 1
                if seen == anchor_count:
                    start = i + 1
                    break
        else:
            # The anchor scrolled out of the history: the last occurrence
            # is the best guess, never a replay of everything.
            hits = [i for i, t in enumerate(done) if t == anchor]
            start = hits[-1] + 1 if hits else len(done)
        if not any(t == anchor for t in done):
            # Taken while it was still being drawn: the block has grown since.
            # Carry on from it, and only its rest is new.
            grown = [i for i, t in enumerate(done) if t.startswith(anchor)]
            if grown:
                i = grown[-1]
                rest = done[i][len(anchor):].strip()
                later = done[i + 1:]
                last = done[-1]
                return ([rest] if rest else []) + later, last, sum(1 for t in done if t == last)
    new = done[start:]
    if not done:
        return [], anchor, anchor_count
    last = done[-1]
    return new, last, sum(1 for t in done if t == last)
