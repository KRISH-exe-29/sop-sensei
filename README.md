# SOP Sensei

Ask the shop floor's SOPs a question, get the exact answer with its source.

SOP Sensei answers questions from transformer core-shop staff using **only** the plant's SOPs
(work instructions and method sheets). Every answer cites its document and step
(e.g. `[WI-KCA-01 Step 20]`), shows the matching photo, and works in English, Tamil and Hindi.
If the SOPs don't cover it, it says so instead of guessing.

## How it works

```
Question
  -> search.py     BM25 keyword search over SOP chunks (local, offline)
  -> Guardrail 1   block names / banned words before anything goes to a cloud AI
  -> answer.py     AI answers in English from the excerpts only (temperature 0)
  -> translate     Tamil / Hindi questions get a second translate step; doc refs kept out of it
  -> Guardrail 2   warn on any number not present in the SOP text
  -> Guardrail 3   "Not covered in the SOPs, ask your supervisor"
```

| File | Purpose |
|---|---|
| `sop_reader.py` | Reads `.docx` / `.ppt` SOPs, splits into chunks (one step or slide each), saves images -> `index/` |
| `sop_check.py` | Quality check: corrupted characters, missing revisions, step gaps, uncaptioned images, names / banned words |
| `search.py` | BM25 search with typo / local-word mapping from `synonyms.txt` |
| `answer.py` | Search + AI answer + guardrails |
| `evaluate.py` | Scores answers against `golden.csv` (source, value, language) |
| `test_search.py`, `test_sop_check.py` | Quick self-checks |

## Setup

```bash
pip install python-docx pywin32        # PowerPoint must be installed (reads old .ppt via COM)
ollama pull gemma3:4b                  # default: local model, nothing leaves the PC
```

Optional, Ollama Cloud (needs an API key, never put it in code):

```bash
setx AI_URL "https://ollama.com/api/chat"
setx AI_MODEL "gpt-oss:120b"
setx OLLAMA_API_KEY "your-key"
```

## Usage

```bash
python sop_reader.py Resources                      # build the index
python sop_check.py                                 # fix what it flags, re-run
python search.py "stack height tolerance"           # search only
python answer.py "what voltage for core to frame megger test"
python answer.py                                    # interactive loop
```

## Quality

```bash
python test_search.py
python test_sop_check.py
python evaluate.py
```

Add every real question that got a wrong answer to `golden.csv`, typos to `synonyms.txt`,
and customer / plant / supplier names to `banned_words.txt`.

## Sanitized SOPs

`Resources/` holds sanitized copies of the 8 SOPs (5 method sheets, 3 work instructions):
logos removed, company names replaced with `[COMPANY]`, staff names with `[NAME]`,
document metadata stripped. The originals live in `Resources/WI_&_Methods_Original/`,
which is kept local and never committed. Only the top level of the folder passed to
`sop_reader.py` is read.

Copy `banned_words.example.txt` to `banned_words.txt` and fill in the real words.
That file is gitignored so the list itself never leaves your PC.

Internal use only. SOP documents are company property.
