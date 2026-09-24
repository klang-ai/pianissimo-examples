"""Ask a finished episode a question.

The question is matched against the transcript's thirty second pieces, and the
local model answers from the best few only, citing where in the episode each
part of the answer comes from. It never sees the whole transcript, which keeps
the answer quick and narrows what it can draw on. The prompt tells it to say
when the pieces do not answer the question. It can still get things wrong, so
the page always lists the pieces it was given.
"""

import math
import re
import unicodedata
from collections import Counter

TOP = 6
# Swedish inflects heavily: skatt, skatten, skatter, skatterna. Comparing the
# first five letters is a crude stem, and good enough to find the right minute.
STEM = 5
STOP = set("""
att och det som en ett är på i av för med till den de dom har inte om vi jag du han hon
man kan ska så men vad hur när var eller också bara mycket här där nu då ju väl sig
vara blir blev finns sagt säger sa ha hade får fick alla något någon många mer mest
""".split())

PROMPT = """Du svarar på en fråga om ett svenskt poddavsnitt. Du får några utdrag ur det
automatiska transkriptet, vart och ett med tidsstämpel [mm:ss].

Svara på svenska, kort, i högst fyra meningar. Sätt tidsstämpeln för utdraget du bygger på
direkt efter påståendet, till exempel [12:30]. Svara bara utifrån utdragen. Står svaret
inte i dem, säg det rakt ut: "Det sägs inte i avsnittet." Transkriptet har ingen
talaruppdelning, så gissa aldrig vem som säger vad."""


def _stems(text):
    words = re.findall(r"\w+", unicodedata.normalize("NFKC", text).lower())
    return [w[:STEM] for w in words if w not in STOP and len(w) > 1]


def search(pieces, question, top=TOP, ordered=True):
    """The pieces most likely to hold the answer. BM25.

    In episode order by default, which is how the model should read them;
    best first with ordered=False, which is how a search result should list them.
    """
    docs = [Counter(_stems(t)) for _, t in pieces]
    if not docs:
        return []
    avg = sum(sum(d.values()) for d in docs) / len(docs) or 1
    q = set(_stems(question))
    df = {s: sum(1 for d in docs if s in d) for s in q}
    scores = []
    for i, d in enumerate(docs):
        length = sum(d.values()) or 1
        score = 0.0
        for s in q:
            if not d.get(s):
                continue
            idf = math.log(1 + (len(docs) - df[s] + 0.5) / (df[s] + 0.5))
            tf = d[s]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))
        scores.append((score, i))
    best = sorted([s for s in scores if s[0] > 0], reverse=True)[:top]
    return sorted(i for _, i in best) if ordered else [i for _, i in best]


def excerpt(pieces, indices, stamp):
    return "\n\n".join(f"[{stamp(pieces[i][0])}] {pieces[i][1]}" for i in indices)
