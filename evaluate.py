"""Step 4: the scoreboard. Runs every question in golden.csv and scores the answers.

Run:  python evaluate.py
Edit golden.csv in Excel to add questions. Columns:
  question | doc | step | value | lang
  - leave doc/step/value empty when the SOPs do NOT cover it (expect "not in SOP")
  - value: text that must appear in the answer (e.g. 2500, ±2, F-KCA-007)
  - lang: en / ta (Tamil) / hi (Hindi)

Every answer is scored on 3 things:
  SOURCE   cites the right doc and step (or says not-in-SOP when it should)
  VALUE    contains the correct value, and no number that isn't in the SOP
  LANGUAGE written in the asker's language
"""
import csv
import re
import sys
import time
from pathlib import Path

from answer import MODEL, NOT_FOUND, answer
from search import load_index

HERE = Path(__file__).parent
SCRIPT = {"ta": r"[஀-௿]", "hi": r"[ऀ-ॿ]"}


def score(row, reply, unknown):
    refused = NOT_FOUND in reply
    if not row["doc"]:  # the SOPs don't cover this: the only right answer is "not in SOP"
        return {"source": refused, "value": refused, "language": True}
    cited = row["doc"] in reply and re.search(rf"Step\s*{row['step']}\b", reply) is not None
    # Judge only the first line (the actual answer). Later lines often quote the SOP,
    # so the right number can appear there even when the answer itself is wrong.
    first = reply.strip().splitlines()[0] if reply.strip() else ""
    value = not refused and row["value"].lower() in first.lower() and not unknown
    if row["lang"] in SCRIPT:
        # More than just a word or two: the sentence itself must be in that script.
        language = len(re.findall(SCRIPT[row["lang"]], reply)) >= 10
    else:
        language = True
    return {"source": cited, "value": value, "language": language}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    index = load_index()
    rows = list(csv.DictReader(open(HERE / "golden.csv", encoding="utf-8")))
    totals = {"source": 0, "value": 0, "language": 0}
    start = time.time()
    for i, row in enumerate(rows, 1):
        reply, _, unknown = answer(index, row["question"], [])
        s = score(row, reply, unknown)
        for k in totals:
            totals[k] += s[k]
        marks = " ".join(f"{k.upper()}:{'ok' if v else 'XX'}" for k, v in s.items())
        print(f"{i:>2}. {marks}  | {row['question']}")
        if not all(s.values()):
            print(f"      got: {reply[:200]!r}" + (f"  unknown numbers: {unknown}" if unknown else ""))
    n = len(rows)
    print(f"\nModel: {MODEL}   Questions: {n}   Time: {time.time() - start:.0f} s")
    for k, v in totals.items():
        print(f"  {k:<9} {v}/{n}  ({100 * v // n}%)")


if __name__ == "__main__":
    main()
