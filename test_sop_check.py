"""Proves the checker catches each kind of problem. Run: python test_sop_check.py"""
from sop_check import check


def chunk(step, text, rev="0", doc="WI-X-01"):
    return {"doc_no": doc, "id": f"{doc}#{step}", "step": step, "text": text, "rev": rev}


good = [chunk(1, "Study the drawing."), chunk(2, "Tolerance ±2 mm.")]
assert check(good, ["ACME"]) == [], check(good, ["ACME"])

bad = [
    chunk(1, "Tolerance �2 mm.", rev=None),
    chunk(4, "Prepared by J.Doe, Ref: ACME-IMSP-36"),
]
problems = check(bad, ["ACME"])
found = " ".join(p[3] for p in problems)
assert {p[0] for p in problems if "banned" in p[3] or "name" in p[3]} == {"BLOCK"}
assert "corrupted character" in found
assert "J.Doe" in found
assert "banned word: ACME" in found
assert "no revision" in found
assert "missing step numbers: [2, 3]" in found

print("all checks passed")
