#!/usr/bin/env python3
"""Transcribe a WAV file with Klang Pianissimo running locally.

No API key, no network after the first run: the weights are downloaded from
Hugging Face once and cached.

    python examples/local/transcribe-offline.py audio.wav

Input must be mono 16 kHz. The model was trained at that rate.
"""

import argparse
import sys
import time
import wave

MODEL = "KlangAI/pianissimo-sv"
RATE = 16000


def check_audio(path):
    """Fail early with a clear message rather than deep inside the model."""
    try:
        with wave.open(path, "rb") as w:
            channels, width, rate, frames = (
                w.getnchannels(),
                w.getsampwidth(),
                w.getframerate(),
                w.getnframes(),
            )
    except wave.Error as e:
        sys.exit(f"{path}: not a readable WAV file ({e})")

    problems = []
    if channels != 1:
        problems.append(f"{channels} channels, needs mono")
    if rate != RATE:
        problems.append(f"{rate} Hz, needs {RATE}")
    if width != 2:
        problems.append(f"{width * 8}-bit, needs 16-bit PCM")
    if problems:
        sys.exit(f"{path}: " + "; ".join(problems))

    return frames / rate


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("audio", help="path to a mono 16 kHz WAV file")
    args = ap.parse_args()

    seconds = check_audio(args.audio)
    print(f"{args.audio}: {seconds:.1f} s, mono {RATE} Hz", file=sys.stderr)

    # Imported here so the audio check above fails fast, before the several
    # seconds it takes to import torch.
    import nemo.collections.asr as nemo_asr

    print(f"loading {MODEL}", file=sys.stderr)
    t0 = time.monotonic()
    model = nemo_asr.models.ASRModel.from_pretrained(MODEL)
    model.eval()
    print(f"loaded in {time.monotonic() - t0:.1f} s", file=sys.stderr)

    t0 = time.monotonic()
    result = model.transcribe([args.audio])
    elapsed = time.monotonic() - t0

    # NeMo returns either strings or Hypothesis objects depending on version.
    first = result[0]
    text = getattr(first, "text", first)

    print(f"transcribed in {elapsed:.2f} s, {seconds / elapsed:.0f}x realtime", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
