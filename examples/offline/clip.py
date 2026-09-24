"""Cut a quote out of an episode as a vertical video with burned-in captions.

The quote is found in the transcript, that stretch of audio is transcribed
again with a timing for every word, and each word lights up as it is spoken.
The picture is drawn by ffmpeg: the show and episode at the top, a waveform,
and the captions in the middle. Everything is rendered on this machine.

Burning captions in needs an ffmpeg built with libass. The standard Homebrew
bottle is not, so this looks for ffmpeg-full first.
"""

import os
import re
import shutil
import subprocess
import unicodedata
import uuid

RATE = 16000
MAX_SECONDS = 60.0
LEAD_IN = 0.25
TAIL = 0.7
# Vertical video is read on a phone at arm's length, so the lines are much
# shorter than broadcast subtitles: about three words.
LINE_CHARS = 18
CUE_CHARS = 34
PAUSE_BREAK = 0.6

W, H = 1080, 1920
FONT = "Avenir Next"
# Named by family, libass picks the first matching face on macOS, which is an
# italic. The Demi Bold family has an upright face of its own.
CAPTION_FONT = "Avenir Next Demi Bold"
INK = "000052"  # Klang navy, as RRGGBB


def _env():
    """The environment without DYLD_LIBRARY_PATH.

    Something in the NeMo import sets it to /opt/homebrew/lib, which makes
    ffmpeg-full load the plain ffmpeg's libraries and die on a missing symbol.
    """
    env = dict(os.environ)
    env.pop("DYLD_LIBRARY_PATH", None)
    return env


def ffmpeg():
    for path in (os.environ.get("FFMPEG"), "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
                 shutil.which("ffmpeg")):
        if path and os.path.exists(path):
            out = subprocess.run([path, "-hide_banner", "-filters"], capture_output=True,
                                 text=True, env=_env()).stdout
            if " ass " in out and " drawtext " in out:
                return path
    return None


def _tokens(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.findall(r"\w+", s)


def locate(job, text=None, start=None):
    """The stretch of the episode that holds the quote: (start, end) in seconds."""
    pieces = job["pieces"]
    if text:
        want = " ".join(_tokens(text))
        head = " ".join(_tokens(text)[:6])
        for i, (s, t) in enumerate(pieces):
            window = " ".join(_tokens(t + " " + (pieces[i + 1][1] if i + 1 < len(pieces) else "")))
            if want in window or head in window:
                return s, min(s + 60.0, job["seconds"])
        raise LookupError("That text is not in the transcript.")
    start = max(0.0, float(start or 0))
    return start, min(start + 30.0, job["seconds"])


def span(words, text):
    """First and last word of the quote within the word timings."""
    if not text:
        return 0, len(words) - 1
    want = _tokens(text)
    have = [(_tokens(w["word"]) or [""])[0] for w in words]
    n = len(want)
    best, score = None, -1
    for i in range(len(have)):
        # Score how many of the quote's words line up from here. The model can
        # split or join a word differently on a second pass, so it need not be all.
        s = sum(1 for k in range(min(n, len(have) - i)) if have[i + k] == want[k])
        if s > score:
            best, score = i, s
    if best is None or score < max(2, n // 3):
        raise LookupError("Could not line the quote up with the audio.")
    last = min(len(words) - 1, best + n - 1)
    # Walk the end onto the quote's last word if the counts drifted by one or two.
    for j in range(max(best, last - 3), min(len(words), last + 4)):
        if have[j] == want[-1]:
            last = j
    return best, last


def cues(words):
    """Short caption groups, broken at sentence ends, pauses and width."""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and len(" ".join(x["word"] for x in cur + [w])) > CUE_CHARS:
            out.append(cur)
            cur = []
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or nxt["start"] - w["end"] >= PAUSE_BREAK or \
                (w["word"].endswith((".", "!", "?")) and len(" ".join(x["word"] for x in cur)) > 10):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _ass_time(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _wrap(ws):
    """Two balanced lines, as ASS text with a karaoke tag on each word."""
    text = " ".join(w["word"] for w in ws)
    split = len(ws)
    if len(text) > LINE_CHARS and len(ws) > 1:
        # The break that makes the two lines closest in length.
        split = min(range(1, len(ws)), key=lambda k: abs(
            len(" ".join(w["word"] for w in ws[:k])) - len(" ".join(w["word"] for w in ws[k:]))))
    parts = []
    for i, w in enumerate(ws):
        nxt = ws[i + 1]["start"] if i + 1 < len(ws) else w["end"]
        cs = max(1, round((nxt - w["start"]) * 100))
        word = w["word"].replace("{", "(").replace("}", ")")
        parts.append(("\\N" if i == split else (" " if i else "")) + f"{{\\kf{cs}}}{word}")
    return "".join(parts)


def ass(words, t0):
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 2", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Spoken words fill to white; the ones still to come wait at a third.
        f"Style: Cap,{CAPTION_FONT},100,&H00FFFFFF,&HAAFFFFFF,&H00000000,&H00000000,0,0,0,0,"
        "100,100,0,0,1,0,0,5,80,80,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    groups = cues(words)
    for i, g in enumerate(groups):
        start = g[0]["start"] - t0
        end = (groups[i + 1][0]["start"] - t0) if i + 1 < len(groups) else g[-1]["end"] - t0 + TAIL
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{_wrap(g)}")
    return "\n".join(lines) + "\n"


def _drawtext_escape(s):
    return (s or "").replace("\\", "\\\\").replace(":", "\\:").replace("'", "’") \
        .replace("%", "\\%").replace(",", "\\,")


def render(job, words, out_path):
    """Write the vertical clip. Returns its length in seconds."""
    bin_ = ffmpeg()
    if not bin_:
        raise RuntimeError("No ffmpeg with libass here. On macOS: brew install ffmpeg-full")
    t0 = max(0.0, words[0]["start"] - LEAD_IN)
    t1 = min(job["seconds"], words[-1]["end"] + TAIL)
    folder = os.path.dirname(out_path)
    sub = os.path.join(folder, os.path.splitext(os.path.basename(out_path))[0] + ".ass")
    with open(sub, "w", encoding="utf-8") as f:
        f.write(ass(words, t0))

    show = _drawtext_escape((job.get("show") or "").upper())
    title = _drawtext_escape(job.get("title") or "")
    if len(title) > 44:
        title = title[:42].rstrip() + "…"
    credit = _drawtext_escape("Transcribed on a laptop with Pianissimo, offline")
    font = "font='Avenir Next Medium'"
    graph = (
        f"color=c=0x{INK}:s={W}x{H}:r=30[bg];"
        # A soft glow behind the captions, so the frame is not flat navy.
        f"color=c=0x212bfa:s={W}x{H}:r=30,format=rgba,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='90*exp(-((X-{W // 2})^2+(Y-{H // 2})^2)/260000)'[glow];"
        "[bg][glow]overlay[base];"
        # showwaves ignores alpha in its colour, so the fade is done afterwards.
        f"[0:a]showwaves=s={W - 160}x220:mode=cline:scale=sqrt:rate=30:colors=0xFFFFFF,format=rgba,"
        "lutrgb=r=255:g=255:b=255,colorchannelmixer=aa=1.6[wave];"
        f"[base][wave]overlay=80:{H - 520}[v1];"
        f"[v1]drawtext={font}:text='{show}':fontcolor=white@0.6:fontsize=38:x=(w-text_w)/2:y=190,"
        f"drawtext={font}:text='{title}':fontcolor=white:fontsize=52:x=(w-text_w)/2:y=250,"
        f"drawtext={font}:text='{credit}':fontcolor=white@0.55:fontsize=34:x=(w-text_w)/2:y={H - 200},"
        f"ass='{sub}'[v]"
    )
    subprocess.run([
        bin_, "-v", "error", "-y", "-ss", f"{t0:.2f}", "-t", f"{t1 - t0:.2f}", "-i", job["path"],
        "-filter_complex", graph, "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", out_path,
    ], check=True, capture_output=True, text=True, env=_env())
    return t1 - t0


def make(engine, job, text=None, start=None, out_dir=None):
    """Find, time and render a clip. Returns a dict for the page."""
    a, b = locate(job, text, start)
    import soundfile as sf
    chunk, _ = sf.read(job["wav"], start=int(a * RATE), stop=int(b * RATE), dtype="float32")
    words = engine.words(chunk, offset=a)
    if not words:
        raise LookupError("No speech in that part of the episode.")
    i, j = span(words, text)
    words = words[i:j + 1]
    while len(words) > 1 and words[-1]["end"] - words[0]["start"] > MAX_SECONDS:
        words.pop()
    # A random name, not a count: two clips made at once would count the same.
    out = os.path.join(out_dir, f"clip-{uuid.uuid4().hex[:8]}.mp4")
    length = render(job, words, out)
    return {"file": out, "seconds": length, "start": words[0]["start"],
            "text": " ".join(w["word"] for w in words)}
