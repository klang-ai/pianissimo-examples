# Transcribe a file with the weights

Transcribe a Swedish WAV file with Pianissimo on your own machine. One script, one file in,
text out. Start here to check your setup before building anything on it. Runs locally: no
API key, and the audio stays on the machine.

## Setup

Python 3.10 or later.

Run everything from the repo root.

```bash
python3 -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
```

The first run downloads 2.34 GB of weights and caches them. `nemo_toolkit[asr]` pulls
PyTorch, about 1.7 GB.

## Run

```bash
.venv/bin/python examples/local/transcribe-offline.py examples/berget-realtime/repro/counting-sv.wav
```

That clip ships with the repo: a synthetic voice counting through four sentences about
Swedish cities, starting "Ett. Stockholm är Sveriges huvudstad." The transcript is printed
to stdout, load and transcription times to stderr.

Your own file: mono 16 kHz PCM16 WAV. The model was trained at that rate, and the script
refuses anything else rather than resampling quietly. To convert:

```bash
ffmpeg -i input.m4a -ac 1 -ar 16000 -c:a pcm_s16le your-audio.wav
```

## What we measured

Measured once, on an M-series MacBook, CPU only, 45.8 seconds of Swedish speech:

| | |
|---|---|
| Model load, first run | 181 s, including the 2.34 GB download |
| Model load, cached | 5.7 s |
| Transcription | 1.4 to 1.6 s, about 30x realtime |

The model card's throughput figures are from GPUs (an A100 for the table, an H100 for the
headline), so they are not comparable with these.

## Limits

- Swedish only. The model is monolingual.
- One file, transcribed in one pass and held in memory. Memory grows with the length of the
  file, so cut long recordings into pieces first.

---

Part of [pianissimo-examples](../../). Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme-local).
