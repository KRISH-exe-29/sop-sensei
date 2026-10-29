"""Step 1: read SOP files and split them into chunks.

A chunk is the smallest piece the assistant can search and quote:
  - one procedure step (What / How / Why) from a Word work instruction
  - one slide from a PowerPoint method sheet
  - one block of general text (scope, safety, tools...)

Every chunk carries its doc number, revision and images, so an answer can
always say exactly where it came from.

Run:  python sop_reader.py Resources
Out:  index/chunks.json  (for the program)
      index/chunks.md    (for you to read and check)
      index/images/...   (images, one folder per document)
"""
import json
import re
import sys
from pathlib import Path

import docx  # python-docx

OUT = Path(__file__).parent / "index"
IMG = OUT / "images"
BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def doc_no_from_name(path):
    # "WI-KCA-01 WORK INSTRUCTION..." -> "WI-KCA-01"
    m = re.match(r"[A-Z]+-[A-Z]+-\d+", path.stem)
    return m.group(0) if m else path.stem


def find_rev(text):
    m = re.search(r"REV\s*[:.\-]?\s*(\d+)", text, re.I)
    return m.group(1) if m else None


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


# ---------- Word (.docx) ----------

def save_images(element, document, folder, prefix):
    """Save every picture inside a table cell / paragraph, return file paths."""
    paths = []
    for i, blip in enumerate(element.iter(BLIP)):
        part = document.part.related_parts[blip.get(EMBED)]
        ext = Path(part.partname).suffix
        f = folder / f"{prefix}_{i + 1}{ext}"
        f.write_bytes(part.blob)
        paths.append(f.relative_to(OUT).as_posix())
    return paths


def read_docx(path):
    document = docx.Document(path)
    doc_no = doc_no_from_name(path)
    folder = IMG / doc_no
    folder.mkdir(parents=True, exist_ok=True)

    chunks, loose_text, loose_imgs = [], [], []

    def flush_text():
        # Paragraphs between tables become one "general" chunk.
        text = clean(" ".join(loose_text))
        if loose_imgs and not text:
            text = "[image only, no text]"  # the checker asks you to caption these
        if text:
            chunks.append({"kind": "text", "step": None, "text": text, "images": loose_imgs[:]})
        loose_text.clear()
        loose_imgs.clear()

    for n, block in enumerate(document.element.body.iterchildren()):
        tag = block.tag.split("}")[1]
        if tag == "p":
            loose_text.append("".join(t.text or "" for t in block.iter() if t.tag.endswith("}t")))
            loose_imgs += save_images(block, document, folder, f"para{n}")
            continue
        if tag != "tbl":
            continue
        flush_text()
        table = docx.table.Table(block, document)
        cols = None  # column positions of What/How/Why, found from the header row
        for r, row in enumerate(table.rows):
            cells = [clean(c.text) for c in row.cells]
            low = [c.lower() for c in cells]
            if "what" in low and "how" in low:
                cols = {k: low.index(k) for k in ("what", "how", "why") if k in low}
                continue
            if cols and cells and re.fullmatch(r"\d+", cells[0]):
                step = int(cells[0])
                imgs = save_images(row._tr, document, folder, f"step{step}")
                part = {k: cells[i] for k, i in cols.items()}
                chunks.append({
                    "kind": "step", "step": step, **part,
                    "text": f"Step {step}: {part.get('what', '')}. How: {part.get('how', '')}. Why: {part.get('why', '')}",
                    "images": imgs,
                })
            else:
                # Not a procedure row (PPE, tools, approval block...): keep as plain text.
                text = clean(" | ".join(dict.fromkeys(c for c in cells if c)))  # merged cells repeat
                if text:
                    imgs = save_images(row._tr, document, folder, f"table{n}_row{r}")
                    chunks.append({"kind": "text", "step": None, "text": text, "images": imgs})
    flush_text()

    full = " ".join(c["text"] for c in chunks)
    return finish(chunks, doc_no, path, find_rev(full))


# ---------- PowerPoint (.ppt / .pptx) ----------

def shape_texts(shape):
    if shape.Type == 6:  # group: look inside
        for s in shape.GroupItems:
            yield from shape_texts(s)
    elif shape.HasTable:
        t = shape.Table
        for r in range(1, t.Rows.Count + 1):
            yield " | ".join(t.Cell(r, c).Shape.TextFrame.TextRange.Text for c in range(1, t.Columns.Count + 1))
    elif shape.HasTextFrame and shape.TextFrame.HasText:
        yield shape.TextFrame.TextRange.Text


def read_ppt(path):
    # ponytail: uses the installed PowerPoint app (Windows only). Works for old .ppt
    # without converting. Switch to python-pptx if this must run on a server.
    import win32com.client

    doc_no = doc_no_from_name(path)
    folder = IMG / doc_no
    folder.mkdir(parents=True, exist_ok=True)
    app = win32com.client.Dispatch("PowerPoint.Application")
    pres = app.Presentations.Open(str(path.resolve()), True, False, False)  # read-only, no window
    chunks, all_text = [], []
    try:
        title = None
        for slide in pres.Slides:
            lines = [clean(t) for s in slide.Shapes for t in shape_texts(s)]
            all_text += lines
            title = title or (lines[0] if lines else None)
            # Drop the repeated header/footer lines (title, doc no, page, date/rev).
            body = [l for l in lines if l and l != title and l != doc_no
                    and not re.fullmatch(r"page|\d+ / \d+|date.*rev.*", l, re.I)]
            png = folder / f"slide{slide.SlideIndex}.png"
            slide.Export(str(png.resolve()), "PNG", 1280, 720)  # whole slide: photos + callouts
            m = re.match(r"(\d+)\.", body[0]) if body else None
            chunks.append({
                "kind": "slide", "step": int(m.group(1)) if m else None,
                "slide": slide.SlideIndex, "text": " ".join(body),
                "images": [png.relative_to(OUT).as_posix()],
            })
    finally:
        pres.Close()
    return finish(chunks, doc_no, path, find_rev(" ".join(all_text)))


# ---------- common ----------

def finish(chunks, doc_no, path, rev):
    for i, c in enumerate(chunks):
        c.update(id=f"{doc_no}#{i + 1}", doc_no=doc_no, rev=rev, source=path.name)
    return chunks


READERS = {".docx": read_docx, ".ppt": read_ppt, ".pptx": read_ppt}


def read_folder(folder):
    chunks = []
    for path in sorted(Path(folder).iterdir()):
        reader = READERS.get(path.suffix.lower())
        if reader and not path.name.startswith("~$"):  # skip Office lock files
            chunks += reader(path)
    return chunks


def write_markdown(chunks, f):
    doc = None
    for c in chunks:
        if c["doc_no"] != doc:
            doc = c["doc_no"]
            f.write(f"\n# {doc}  (rev: {c['rev'] or 'MISSING'})  -  {c['source']}\n\n")
        label = f"Step {c['step']}" if c["step"] is not None else c["kind"]
        f.write(f"**{c['id']}  [{label}]**  {c['text']}\n")
        for img in c["images"]:
            f.write(f"\n![]({img})\n")
        f.write("\n---\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    chunks = read_folder(sys.argv[1] if len(sys.argv) > 1 else "Resources")
    OUT.mkdir(exist_ok=True)
    (OUT / "chunks.json").write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(OUT / "chunks.md", "w", encoding="utf-8") as f:
        write_markdown(chunks, f)
    print(f"{len(chunks)} chunks from {len({c['doc_no'] for c in chunks})} documents -> {OUT}")
