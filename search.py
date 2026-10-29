"""Step 2: keyword search (BM25) over the chunks. Runs fully on this PC.

Run:  python search.py "what voltage for core frame test"
      python search.py            (asks questions in a loop)

Spelling variants and typos are fixed through synonyms.txt, e.g.
  megger = meggar, megar
"""
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
STOP = set("a an the of to for in on at by and or is are be it this that with as from what how why "
           "which when do does should can i we you my our".split())


def load_synonyms():
    """'megger = meggar, megar'  ->  {'meggar': 'megger', 'megar': 'megger'}"""
    table = {}
    f = HERE / "synonyms.txt"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                main, others = line.split("=", 1)
                for w in others.split(","):
                    table[w.strip().lower()] = main.strip().lower()
    return table


SYN = load_synonyms()


def stem(w):
    # ponytail: crude suffix strip (tightening -> tighten, stacks -> stack).
    # Good enough for English SOPs; swap for a real stemmer if matches are missed.
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def tokens(text):
    text = text.lower().replace("%", " percent ")  # "50 %" must match "percentage"
    words = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text)
    return [stem(SYN.get(w, w)) for w in words if w not in STOP]


class Index:
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.docs = [tokens(c["text"]) for c in chunks]
        self.avg = sum(map(len, self.docs)) / len(self.docs)
        n = len(self.docs)
        df = {}
        for d in self.docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        # Rule 2: a word found in few chunks is worth more.
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query, top=3):
        q = set(tokens(query))
        results = []
        for chunk, d in zip(self.chunks, self.docs):
            score = 0.0
            for t in q:
                tf = d.count(t)  # Rule 1: how often the word appears in this chunk
                if tf:
                    # Rule 3: normalise by chunk length.
                    score += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            if score > 0:
                results.append((round(score, 2), chunk))
        results.sort(key=lambda r: -r[0])
        return results[:top]


def load_index():
    return Index(json.loads((HERE / "index" / "chunks.json").read_text(encoding="utf-8")))


def show(index, question):
    hits = index.search(question)
    if not hits:
        print("  Nothing found in the SOPs.\n")
    for score, c in hits:
        where = f"{c['doc_no']} Step {c['step']}" if c["step"] is not None else c["id"]
        print(f"  [{score:>5}] {where} (rev {c['rev'] or '?'})\n          {c['text'][:200]}")
        for img in c["images"]:
            print(f"          image: index/{img}")
    print()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    index = load_index()
    if len(sys.argv) > 1:
        show(index, " ".join(sys.argv[1:]))
    else:
        while (q := input("Question (blank to quit): ").strip()):
            show(index, q)
