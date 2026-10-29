"""Step 0: quality check. Find problems in the SOPs before the AI ever sees them.

Run after sop_reader.py:  python sop_check.py
It never changes your files. It only lists what you should fix by hand.

Add company names, customer names, plant codes etc. to banned_words.txt
(one per line). Anything listed there must not be sent to a cloud AI.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

# "J.Doe", "R. Smith", "Mary Ann.K"
NAME = re.compile(r"\b[A-Z]\.\s?[A-Z][a-z]{2,}|\b[A-Z][a-z]{2,}\.[A-Z]\b")


def load_banned():
    f = HERE / "banned_words.txt"
    return [w.strip() for w in f.read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.startswith("#")] if f.exists() else []


def secrets_in(text, banned):
    """BLOCKER check: names or banned words in any text about to leave this PC."""
    found = [f"possible person name: {n}" for n in NAME.findall(text)]
    found += [f"banned word: {w}" for w in banned if re.search(re.escape(w), text, re.I)]
    return found


def check(chunks, banned):
    """Return a list of (severity, doc_no, chunk_id, problem). severity: BLOCK or WARN.
    BLOCK = must not go to the cloud. WARN = fix when convenient."""
    problems = []
    docs = {}
    for c in chunks:
        docs.setdefault(c["doc_no"], []).append(c)
        if "�" in c["text"]:
            i = c["text"].index("�")
            problems.append(("WARN", c["doc_no"], c["id"], f"corrupted character (was it ± ° µ ?): ...{c['text'][max(0, i - 40):i + 15]}..."))
        if c["text"] == "[image only, no text]":
            problems.append(("WARN", c["doc_no"], c["id"], f"image with no text, add a caption so it can be found: {c['images']}"))
        for msg in secrets_in(c["text"], banned):
            problems.append(("BLOCK", c["doc_no"], c["id"], msg))

    for doc_no, doc_chunks in docs.items():
        if not doc_chunks[0]["rev"]:
            problems.append(("WARN", doc_no, "-", "no revision number found (needed to match the QA master list)"))
        steps = sorted({c["step"] for c in doc_chunks if c["step"] is not None})
        if steps:
            missing = sorted(set(range(1, steps[-1] + 1)) - set(steps))
            if missing:
                problems.append(("WARN", doc_no, "-", f"missing step numbers: {missing}"))
    return problems


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    chunks = json.loads((HERE / "index" / "chunks.json").read_text(encoding="utf-8"))
    problems = check(chunks, load_banned())
    for sev, doc_no, cid, msg in problems:
        print(f"{sev:<5} [{doc_no}] {cid:<14} {msg}")
    print(f"\n{len(problems)} problem(s) found." if problems else "Clean. Safe to index.")
