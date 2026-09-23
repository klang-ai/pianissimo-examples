# Offline: a podcast summary and live dictation

Two small apps on one local server, both running Pianissimo on your own machine.
Turn the Wi-Fi off before you start. They work the same.

- **Podcast summary.** Drop in an episode and get the full transcript, a summary,
  chapters with timestamps you can click, and a quote checked against the transcript.
- **Offline dictation.** Talk, and the text appears while you speak.

Nothing is uploaded. The browser talks to a server on `127.0.0.1`, the server
reads both models from the local cache, and a badge in the corner shows whether
the machine can reach the internet at all. That check opens a connection to
1.1.1.1 and sends nothing over it; no audio or text ever leaves the machine.

## Setup

Python 3.10 or later, ffmpeg, and llama.cpp for the summary.

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]" aiohttp soundfile
brew install ffmpeg llama.cpp
```

Download both models once, with the network on:

```bash
hf download KlangAI/pianissimo-sv
hf download unsloth/Qwen3-4B-Instruct-2507-GGUF Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

That is 2.34 GB for Pianissimo and 2.5 GB for the summary model.

## Run

```bash
.venv/bin/python examples/offline/server.py
```

Open http://127.0.0.1:8765. The first start takes a few seconds while both
models load; after that the server is ready.

## How the summary stays fast

Pianissimo turns speech into text and stops there. The summary comes from a
small instruction model, Qwen3 4B, run by llama.cpp on the same machine.

A small model slows down a lot on long input, so it never sees the whole
transcript at once. Each chapter of a few minutes is summarised as soon as it
is transcribed, while the next one is still being transcribed, and the episode
summary is written from the chapters. That is also why the chapter timestamps
are real: they are where each piece of audio starts, not a guess by the model.

A quote is only shown if it appears word for word in the transcript.

## What it measured

On a MacBook Pro with an M5 and 24 GB, a 51 minute episode of Ekots
lördagsintervju: transcribed in 55 s with the summary model running alongside,
summary ready 11 s later, 69 s from dropping the file to done. Transcription
alone runs at about 105 times real time on the M5's GPU.

Dictation shows new text every 0.4 s, and each update takes 130 to 350 ms.

## Limits

- No speaker separation. The summary says what was said, not who said it,
  unless a name is spoken.
- The chapters are cut by time, a few minutes each, not by topic.
- Dictation re-reads the open sentence as you speak, so the last few words can
  change until you pause.
