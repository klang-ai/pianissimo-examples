#!/usr/bin/env python3
"""Subtitle a Swedish video with Klang Pianissimo, on your own machine.

    python examples/subtitles/subtitle.py talk.mp4

Writes talk.srt next to the input. No API key, no account, no upload: the
weights are downloaded from Hugging Face once and everything after that runs
locally, so the audio never leaves the machine.

Takes any file ffmpeg can read. Audio is extracted to mono 16 kHz internally,
which is the rate the model was trained at.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import warnings
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cues as cuelib


class _QuietStderr:
    """Drops NeMo's startup chatter and keeps everything else.

    NeMo logs its dataloader config, a CUDA note and an NVIDIA telemetry line on
    every single run. That is right for a training job and wrong for a tool with
    one job. Errors and tracebacks are untouched, and --verbose skips this
    entirely when something needs debugging.
    """

    NOISE = ("[NeMo W", "[NeMo I", "OneLogger:", "No exporters were provided")

    def __init__(self, stream):
        self._stream = stream
        self._muting = False

    def write(self, text):
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            if stripped.startswith(self.NOISE):
                self._muting = True
                continue
            # NeMo wraps long log messages onto indented continuation lines.
            if self._muting and (line.startswith((" ", "\t")) or not stripped):
                continue
            self._muting = False
            self._stream.write(line)

    def flush(self):
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


MODEL = "KlangAI/pianissimo-sv"
RATE = 16000
# Files longer than CHUNK_SECONDS are transcribed in pieces, which uses less
# memory and runs faster on recordings of an hour or more. Shorter files are one
# piece and come out exactly as before. The pieces are long on purpose: the
# model's output depends on how much context it gets, and short pieces change it.
# Pieces overlap, and each word is kept from the piece where its midpoint falls
# inside the non-overlapping part, so a word cut at a boundary is kept once.
CHUNK_SECONDS = 1200
OVERLAP_SECONDS = 10


def probe(path):
    """Duration in seconds, and a clear error if there is no audio to work on."""
    if not os.path.exists(path):
        sys.exit(f"{path}: no such file")

    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format",
             "-of", "json", path],
            capture_output=True, text=True, check=True,
        ).stdout
    except FileNotFoundError:
        sys.exit("ffprobe not found. Install ffmpeg: brew install ffmpeg")
    except subprocess.CalledProcessError as e:
        sys.exit(f"{path}: ffprobe could not read this file\n{e.stderr.strip()}")

    info = json.loads(out)
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        sys.exit(f"{path}: no audio stream, nothing to transcribe")

    return float(info["format"]["duration"])


def extract_audio(path, dest):
    """Down to mono 16 kHz PCM16, which is what the model expects."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", path,
         "-vn", "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", dest],
        check=True,
    )


def split_audio(wav, dest_dir):
    """Cut the extracted audio into overlapping pieces.

    Returns (path, offset, keep_from, keep_to) per piece, in seconds. A word is
    kept when its midpoint falls in [keep_from, keep_to).
    """
    with wave.open(wav, "rb") as src:
        params = src.getparams()
        total = src.getnframes()
        chunk = CHUNK_SECONDS * RATE
        half = OVERLAP_SECONDS * RATE // 2
        pieces = []
        start = 0
        while start < total:
            end = min(start + chunk, total)
            lo = max(start - half, 0)
            hi = min(end + half, total)
            src.setpos(lo)
            path = os.path.join(dest_dir, f"piece-{len(pieces):04d}.wav")
            with wave.open(path, "wb") as out:
                out.setparams(params)
                out.writeframes(src.readframes(hi - lo))
            pieces.append((path, lo / RATE, start / RATE, end / RATE))
            start = end
    return pieces


def word_timings(hypothesis):
    """Pull word level timings out of whatever shape this NeMo version returns.

    Word timings are the whole point here: segment level stamps would give
    cues that break where the model decided, not where the sentence does.
    """
    stamps = getattr(hypothesis, "timestamp", None)
    if not stamps or "word" not in stamps:
        sys.exit(
            "This model build returned no word timestamps, so there is nothing "
            "to build cues from. Check that nemo_toolkit is current."
        )

    words = []
    for w in stamps["word"]:
        text = (w.get("word") or w.get("char") or "").strip()
        if not text:
            continue
        words.append({"word": text, "start": float(w["start"]), "end": float(w["end"])})
    return words


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="video or audio file, anything ffmpeg reads")
    ap.add_argument("-o", "--output", help="where to write the .srt (default: next to the input)")
    ap.add_argument("--verbose", action="store_true",
                    help="keep NeMo's own logging, which is loud but useful when something fails")
    args = ap.parse_args()

    seconds = probe(args.input)
    out_path = args.output or os.path.splitext(args.input)[0] + ".srt"
    print(f"{args.input}: {seconds:.1f} s of audio", file=sys.stderr)

    # Imported here so the file checks above fail in a second rather than after
    # the twenty it takes to import torch.
    if not args.verbose:
        # NeMo logs its decoder config and a CUDA warning on every load. That is
        # the right default for training and the wrong one for a tool with one
        # job, so it is off unless you ask.
        warnings.filterwarnings("ignore")
        # NeMo's loggers bind to whatever sys.stderr is when the module loads,
        # so the swap has to happen before the import, not after.
        # NeMo splits its chatter across both streams: INFO to stdout,
        # warnings to stderr. Both get filtered, and both bind at import time.
        sys.stderr = _QuietStderr(sys.stderr)
        sys.stdout = _QuietStderr(sys.stdout)
    import torch
    from nemo.collections.asr.models import ASRModel
    if not args.verbose:
        from nemo.utils import logging as nemo_logging
        nemo_logging.set_verbosity(nemo_logging.ERROR)

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "audio.wav")
        extract_audio(args.input, wav)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"loading {MODEL} on {device.type}", file=sys.stderr)
        t0 = time.monotonic()
        model = ASRModel.from_pretrained(model_name=MODEL, map_location=device).eval()
        print(f"loaded in {time.monotonic() - t0:.1f} s", file=sys.stderr)

        pieces = split_audio(wav, tmp)
        t0 = time.monotonic()
        with torch.inference_mode():
            result = model.transcribe(audio=[p[0] for p in pieces], batch_size=1,
                                      return_hypotheses=True, timestamps=True,
                                      verbose=args.verbose)
        elapsed = time.monotonic() - t0

    # Some versions hand back (hypotheses, all_hypotheses).
    if isinstance(result, tuple):
        result = result[0]

    words = []
    for (_, offset, keep_from, keep_to), hypothesis in zip(pieces, result):
        for w in word_timings(hypothesis):
            w["start"] += offset
            w["end"] += offset
            if keep_from <= (w["start"] + w["end"]) / 2 < keep_to:
                words.append(w)
    if not words:
        sys.exit("No speech found in the audio.")

    cues = cuelib.fit_timings(cuelib.split_into_cues(words))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(cuelib.to_srt(cues))

    print(f"transcribed in {elapsed:.1f} s, {seconds / elapsed:.0f}x realtime",
          file=sys.stderr)
    print(f"{len(words)} words in {len(cues)} cues -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
