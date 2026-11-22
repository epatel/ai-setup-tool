"""The index of installed cards: a block in CARDS.md that CLAUDE.md imports.

A card is loaded only when an agent decides it is relevant, and the agent decides from the
index line. So an installed card without an index line is never read.
"""

from __future__ import annotations

import re
from pathlib import Path

INDEX_FILE = "CARDS.md"
IMPORT = f"@{INDEX_FILE}"
BEGIN = "<!-- ast:cards:begin - written by ast from ast.lock; edits between the markers are lost -->"
END = "<!-- ast:cards:end -->"

# Files in a source repo that may hold `- [name](cards/name.md) — when to read it` lines.
SOURCE_INDEX_FILES = ("CARDS.md", "CLAUDE.md", "AGENTS.md")
_INDEX_LINE = re.compile(
    r"^\s*[-*]\s*\[[^\]]*\]\((?:\./)?cards/([^)/]+)\.md\)\s*(?:—|–|--|-|:)\s*(\S.*?)\s*$", re.MULTILINE
)
_BLOCK = re.compile(re.escape("<!-- ast:cards:begin") + r".*?" + re.escape(END), re.DOTALL)

_NEW_FILE = """\
# Cards

Short reference files. Read a card when the situation after its dash matches the work.

"""


def source_triggers(texts: list[str]) -> dict[str, str]:
    """Card name -> trigger, from the index lines of a source repo. The first file wins."""
    found: dict[str, str] = {}
    for text in texts:
        for name, trigger in _INDEX_LINE.findall(text):
            found.setdefault(name, trigger)
    return found


def summary(card: Path, limit: int = 160) -> str:
    """Fallback trigger: the first paragraph of the card's text, cut to one short line."""
    paragraph: list[str] = []
    fenced = False
    for line in card.read_text(errors="replace").splitlines():
        text = line.strip()
        if text.startswith(("```", "~~~")):
            fenced = not fenced
        elif fenced or text.startswith(("#", ">", "|", "<!--")):
            continue
        elif text:
            paragraph.append(text)
        elif paragraph:
            break
    text = " ".join(paragraph) or "no description; add a line for this card to the source's CARDS.md"
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def write_index(root: Path, cards: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """Rewrite the ast block in CARDS.md for (name, path, trigger) cards; hook up CLAUDE.md.

    Text outside the markers is the project's own and is kept. Returns (verb, file) pairs
    for what changed.
    """
    done: list[tuple[str, str]] = []
    path = root / INDEX_FILE
    lines = [f"- [{name}]({dest}) — {trigger}" for name, dest, trigger in sorted(cards)]
    block = "\n".join([BEGIN, *lines, END])
    old = path.read_text() if path.exists() else None
    if old is None:
        new = _NEW_FILE + block + "\n" if cards else None
    elif _BLOCK.search(old):
        new = _BLOCK.sub(lambda _: block, old, count=1)
    else:
        new = old.rstrip("\n") + "\n\n" + block + "\n" if cards else None
    if new is not None and new != old:
        path.write_text(new)
        done.append(("indexed", INDEX_FILE))
    if not cards:
        return done

    hosts = [root / name for name in ("CLAUDE.md", "AGENTS.md") if (root / name).exists()]
    if any(IMPORT in host.read_text() for host in hosts):
        return done
    if hosts:
        host = hosts[0]
        host.write_text(host.read_text().rstrip("\n") + f"\n\n## Cards\n\n{IMPORT}\n")
    else:
        host = root / "CLAUDE.md"
        host.write_text(f"## Cards\n\n{IMPORT}\n")
    done.append(("linked", f"{host.name} (added {IMPORT})"))
    return done
