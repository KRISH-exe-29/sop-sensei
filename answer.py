"""Step 3: answer a question from the SOPs using Ollama Cloud.

Flow:  question -> search (local) -> cloud gate -> AI answer -> number check
Run:   python answer.py "what voltage for core frame test"
       python answer.py            (asks questions in a loop)

Default: local Ollama on this PC (free, nothing leaves the plant).
To switch to Ollama Cloud later (needs credits), set two variables once:
  setx AI_URL "https://ollama.com/api/chat"
  setx AI_MODEL "gpt-oss:120b"
plus OLLAMA_API_KEY (set with setx, never in code).
"""
import json
import os
import re
import sys
import urllib.request

from search import load_index
from sop_check import load_banned, secrets_in

URL = os.environ.get("AI_URL", "http://localhost:11434/api/chat")
MODEL = os.environ.get("AI_MODEL", "gemma3:4b")
IS_CLOUD = "localhost" not in URL and "127.0.0.1" not in URL
NOT_FOUND = "NOT_IN_SOP"

RULES = f"""You answer questions from transformer factory staff using ONLY the SOP excerpts given.
Rules:
1. Use only facts written in the excerpts. Never add values, steps or advice from general knowledge.
2. Copy every number and unit exactly as written in the excerpt (e.g. 2500 volts, ±2 mm, 50 %).
3. End each fact with its source in square brackets, e.g. [WI-KCA-01 Step 20].
4. If the excerpts do not answer the question, reply with exactly: {NOT_FOUND}
5. Reply in the same language as the question (English, Tamil or Hindi). Keep doc numbers, numbers and units unchanged.
6. Be short: the answer first, then the reason (the "Why") if the excerpt gives one."""


class Blocked(Exception):
    pass


def ask_ai(messages):
    headers = {"Content-Type": "application/json"}
    if IS_CLOUD:
        key = os.environ.get("OLLAMA_API_KEY")
        if not key:
            sys.exit("OLLAMA_API_KEY is not set. Run: setx OLLAMA_API_KEY \"your-key\" and open a new terminal.")
        headers["Authorization"] = f"Bearer {key}"
    # temperature 0 = same question, same answer. We want facts, not creativity.
    body = json.dumps({"model": MODEL, "messages": messages, "stream": False,
                       "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(URL, body, headers)
    with urllib.request.urlopen(req, timeout=300) as r:  # a small PC can take a while
        return json.load(r)["message"]["content"].strip()


def language_of(text):
    # Decided by code, not left to the model: Tamil / Hindi script letters in the question.
    if re.search(r"[஀-௿]", text):
        return "Tamil"
    if re.search(r"[ऀ-ॿ]", text):
        return "Hindi"
    return "English"


def numbers(text):
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def answer(index, question, banned):
    hits = index.search(question)
    if not hits:
        return NOT_FOUND, [], []
    chunks = [c for _, c in hits]
    excerpts = "\n\n".join(f"[{c['doc_no']} Step {c['step']}]\n{c['text']}" if c["step"] is not None
                           else f"[{c['id']}]\n{c['text']}" for c in chunks)

    # Guardrail 1: nothing with names or banned words leaves this PC.
    leaks = secrets_in(question + "\n" + excerpts, banned) if IS_CLOUD else []
    if leaks:
        raise Blocked("; ".join(leaks))

    reply = ask_ai([
        {"role": "system", "content": RULES},
        {"role": "user", "content": f"SOP excerpts:\n{excerpts}\n\nQuestion: {question}\n\n"
                                    f"Write the answer in English. "
                                    f"Keep numbers, units and [doc Step] references exactly as in the excerpts."},
    ])

    # Two small jobs beat one hard job: answer in English first, then translate.
    lang = language_of(question)
    if lang != "English" and NOT_FOUND not in reply:
        # The translator never sees the [doc Step] references, so it can't change them.
        refs = list(dict.fromkeys(re.findall(r"\[[^\]]*\]", reply)))
        plain = re.sub(r"\s*\[[^\]]*\]", "", reply)
        reply = ask_ai([{"role": "user", "content":
                         f"Translate this into {lang}. Keep every number, unit and symbol exactly unchanged. "
                         f"Output only the translation.\n\n{plain}"}]) + "\n" + " ".join(refs)

    # Guardrail 2: every number in the answer must exist in what we sent (or the question).
    sources = re.sub(r"\[[^\]]*\]", "", reply)  # ignore numbers inside [WI-KCA-01 Step 20]
    unknown = sorted(numbers(sources) - numbers(excerpts) - numbers(question))
    return reply, chunks, unknown


def show(index, question, banned):
    try:
        reply, chunks, unknown = answer(index, question, banned)
    except Blocked as e:
        print(f"  BLOCKED, nothing sent to the cloud: {e}\n")
        return
    if NOT_FOUND in reply:
        # Guardrail 3: honest "don't know".
        print("  Not covered in the SOPs. Please ask your supervisor.\n")
        return
    print(f"\n{reply}\n")
    if unknown:
        print(f"  WARNING: these numbers are NOT in the SOP text, do not trust them: {unknown}")
    for c in chunks:
        if c["doc_no"] in reply and (c["step"] is None or f"Step {c['step']}" in reply):
            for img in c["images"]:
                print(f"  see image: index/{img}")
    print()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    index, banned = load_index(), load_banned()
    if len(sys.argv) > 1:
        show(index, " ".join(sys.argv[1:]), banned)
    else:
        while (q := input("Question (blank to quit): ").strip()):
            show(index, q, banned)
