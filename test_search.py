"""Does the right step come back first? Run: python test_search.py
Grow this list with your golden questions. It becomes the scoreboard for Step 4."""
from search import load_index

index = load_index()

# (question, expected doc, expected step)
CASES = [
    ("what voltage for core to frame megger test", "WI-KCA-01", 20),
    ("how long to dry core pad insulation in oven", "WI-KCA-01", 3),
    ("stack height tolerance", "WI-KCA-01", 12),
    ("polyglass tape overlap percentage", "P-KCA-005", 4),
    # Same "Frame setting" step exists in the 3-limb and 5-limb instructions.
    ("how to check squareness of frame diagonals", ("WI-KCA-01", "WI-KCA-02"), (5, 7)),
]

failed = 0
for q, doc, step in CASES:
    hits = index.search(q)
    top = hits[0][1] if hits else None
    ok = top is not None and (top["doc_no"], top["step"]) in (
        zip(doc, step) if isinstance(doc, tuple) else [(doc, step)])
    failed += not ok
    got = f"{top['doc_no']} step {top['step']}" if top else "nothing"
    print(f"{'PASS' if ok else 'FAIL'}  {q!r} -> {got}")

assert index.search("zzz qqq") == [], "nonsense must return nothing"
print(f"\n{len(CASES) - failed}/{len(CASES)} correct")
assert failed == 0
