# Transcribe a file with the weights

The smallest example in the repo, and the place to start if you want to see the model run
before building anything on it. One script, one WAV file in, text out. Runs locally: no API
key, and no network after the first run.

## Setup

Python 3.10 or later.

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
```

The first run downloads 2.34 GB of weights and caches them. `nemo_toolkit[asr]` pulls
PyTorch, about 1.7 GB.

## Run

```bash
.venv/bin/python examples/local/transcribe-offline.py your-audio.wav
```

Input: mono 16 kHz PCM16 WAV. The model was trained at that rate, and the script refuses
anything else rather than resampling quietly.

## What we measured

M-series MacBook, CPU only, 45.8 seconds of Swedish speech:

| | |
|---|---|
| Model load, first run | 181 s, including the 2.34 GB download |
| Model load, cached | 5.7 s |
| Transcription | 1.4 to 1.6 s, about 30x realtime |

The launch figures are from an H100. A laptop CPU is a different machine; the numbers above
are what you should expect from one.

## Limits

- Swedish only. The model is monolingual.
- One file, transcribed in one pass and held in memory. For long files, look at how
  [`examples/subtitles/`](../subtitles/) and [`examples/offline/`](../offline/) cut the audio
  into pieces first.

---

Part of [pianissimo-examples](../../). Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme-local).
