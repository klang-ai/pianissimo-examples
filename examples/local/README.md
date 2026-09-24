# Pianissimo, local: transcribe a file with the weights

The smallest local example. One script, one WAV file in, text out, on your own machine. No
API key, and no network after the first run.

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
.venv/bin/python examples/local/transcribe-offline.py your-audio.wav
```

Input: mono 16 kHz PCM16 WAV.

Size: `nemo_toolkit[asr]` pulls PyTorch, about 1.7 GB, and the weights are 2.34 GB, downloaded
once and cached.

Measured on an M-series MacBook, CPU only, 45.8 seconds of Swedish speech:

| | |
|---|---|
| Model load, first run | 181 s, including the 2.34 GB download |
| Model load, cached | 5.7 s |
| Transcription | 1.4 to 1.6 s, about 30x realtime |

The launch figures are from an H100.

For something built on top of this, see [`examples/subtitles/`](../subtitles/).
