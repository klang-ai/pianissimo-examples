"""Turn word timings into subtitle cues a human can actually read.

This is the part that makes subtitles subtitles rather than a transcript with
timestamps. The model gives one timing per word. A viewer needs lines that are
short enough to read, on screen long enough to read, and broken where the
sentence breaks rather than wherever the character count ran out.

The limits below follow the conventions broadcasters use. They are not
arbitrary, and changing them changes how the result reads:

  MAX_LINE       42 characters. Wider than this and the eye stops tracking.
  MAX_LINES      2. A third line covers the picture.
  MAX_CPS        17 characters per second, the usual adult reading speed.
  MIN_SECONDS    1.0. Anything shorter registers as a flicker.
  MAX_SECONDS    6.0. Longer and the viewer rereads it.
  PAUSE_BREAK    0.7 s of silence ends a cue even mid sentence, because the
                 speaker stopped and the subtitle should too.
"""

MAX_LINE = 42
MAX_LINES = 2
MAX_CPS = 17.0
MIN_SECONDS = 1.0
MAX_SECONDS = 6.0
PAUSE_BREAK = 0.7
MIN_GAP = 0.08

SENTENCE_END = (".", "!", "?", "…")
CLAUSE_END = (",", ";", ":")

MAX_CHARS = MAX_LINE * MAX_LINES


class Cue:
    def __init__(self, words):
        self.words = words

    @property
    def text(self):
        return " ".join(w["word"] for w in self.words)

    @property
    def start(self):
        return self.words[0]["start"]

    @property
    def end(self):
        return self.words[-1]["end"]


def split_into_cues(words):
    """Group words into cues, breaking at the strongest boundary available.

    Greedy on purpose. A global optimiser would balance cue lengths better, but
    it would also reorder where breaks land relative to the speech, and a
    subtitle that breaks in an unexpected place is worse than one that is a few
    characters short.
    """
    cues = []
    current = []

    for i, word in enumerate(words):
        # Close the cue *before* the word that would overflow it, not after.
        # Appending first and checking afterwards lets a cue run past what two
        # lines can hold, and then there is no legal place left to wrap it.
        # Natural speech has long words and few pauses, so this shows up there
        # and never on clean read-aloud audio.
        if current:
            prospective = " ".join(w["word"] for w in current) + " " + word["word"]
            too_wide = not fits(prospective)
            too_long = word["end"] - current[0]["start"] > MAX_SECONDS
            if too_wide or too_long:
                cues.append(Cue(current))
                current = []

        current.append(word)
        text_len = len(" ".join(w["word"] for w in current))

        last = word["word"]
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - word["end"]) if nxt else 0.0

        ends_sentence = last.endswith(SENTENCE_END)
        # A sentence end only breaks if the cue has enough in it to stand
        # alone. Otherwise "Ja." becomes its own cue and the screen stutters.
        long_enough = text_len >= MAX_LINE // 2

        must_break = (
            nxt is None
            or gap >= PAUSE_BREAK
        )
        wants_break = ends_sentence and long_enough

        if must_break or wants_break:
            cues.append(Cue(current))
            current = []

    if current:
        cues.append(Cue(current))
    return cues


def fit_timings(cues):
    """Stretch cues that are on screen too briefly to be read.

    Only ever borrows from the silence that follows. Never overlaps the next
    cue, and never moves a start time, because a subtitle that appears before
    the word is spoken reads as a mistake even when the text is right.
    """
    for i, cue in enumerate(cues):
        start, end = cue.start, cue.end
        chars = len(cue.text)

        needed = max(MIN_SECONDS, chars / MAX_CPS)
        if end - start >= needed:
            continue

        ceiling = cues[i + 1].start - MIN_GAP if i + 1 < len(cues) else start + needed
        cue.display_end = min(start + needed, max(end, ceiling))
    for cue in cues:
        if not hasattr(cue, "display_end"):
            cue.display_end = cue.end
    return cues


def fill(text, max_line=MAX_LINE):
    """Greedy line filling. Returns the lines, or None if a word is wider than a line.

    Greedy gives the fewest lines a text can occupy, so it is also the honest
    test of whether something fits in the cue budget at all.
    """
    lines, current = [], ""
    for word in text.split():
        if len(word) > max_line:
            return None
        candidate = word if not current else current + " " + word
        if len(candidate) <= max_line:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fits(text):
    """Can this text be shown as at most MAX_LINES lines of MAX_LINE characters."""
    lines = fill(text)
    return lines is not None and len(lines) <= MAX_LINES


def wrap(text):
    """Break one cue into at most two lines.

    Prefers a balanced break, and just after punctuation when that is close,
    because two lines of 20 read faster than one of 34 and one of 6. Falls back
    to greedy filling when no balanced split is legal, which happens whenever a
    long word sits near the middle.
    """
    if len(text) <= MAX_LINE:
        return text

    words = text.split()
    best = None
    for i in range(1, len(words)):
        head = " ".join(words[:i])
        tail = " ".join(words[i:])
        if len(head) > MAX_LINE or len(tail) > MAX_LINE:
            continue
        score = abs(len(head) - len(tail))
        if head.endswith(CLAUSE_END):
            score -= 12
        if best is None or score < best[0]:
            best = (score, head + "\n" + tail)

    if best:
        return best[1]

    # Never drop words: a wide line is a formatting problem, a missing word is a
    # wrong subtitle. The cue builder keeps this branch rare.
    lines = fill(text)
    return "\n".join(lines) if lines else text


def timestamp(seconds):
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues):
    blocks = []
    for n, cue in enumerate(cues, start=1):
        blocks.append(
            f"{n}\n"
            f"{timestamp(cue.start)} --> {timestamp(cue.display_end)}\n"
            f"{wrap(cue.text)}\n"
        )
    return "\n".join(blocks)
