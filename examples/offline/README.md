# Offline: a podcast summary and live dictation

Two small apps on one local server, both running Pianissimo on your own machine.
Turn the Wi-Fi off before you start. They work the same.

- **Podcast summary.** Paste a link, type the name of an episode, or drop in a
  file. Get the full transcript, a summary, chapters with timestamps you can
  click, and a quote checked against the transcript.
- **Offline dictation.** Talk, and the text appears while you speak.

Nothing is uploaded. The browser talks to a server on `127.0.0.1`, the server
reads both models from the local cache, and a badge in the corner shows whether
the machine can reach the internet at all. That check opens a connection to
1.1.1.1 and sends nothing over it; no audio or text ever leaves the machine.

## Setup

Python 3.10 or later, ffmpeg, and llama.cpp for the summary.

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]" aiohttp soundfile
brew install ffmpeg llama.cpp yt-dlp
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

## Any link, or just a name

The box on the podcast page takes whatever you have:

| You paste | What happens |
|---|---|
| A Spotify episode or show | Spotify does not hand out episode audio, and this does not try to get around that. It reads the show name and episode title from the page, finds the show's public RSS feed in Apple's podcast directory, and takes the same episode from there. Spotify exclusives have no feed and are reported as such. |
| An Apple Podcasts link | Looked up in Apple's public directory. |
| Sveriges Radio | Its open API, since its pages refuse plain requests. |
| YouTube, Acast, SoundCloud and about a thousand other sites | [yt-dlp](https://github.com/yt-dlp/yt-dlp). |
| An RSS feed, or a page with a player on it | The feed's episodes, or the audio the page plays. |
| Just words, like `sommar i p1 zlatan` | A search for episodes in Apple's directory, Swedish storefront. |

Fetching the audio is the only thing that uses the network. The page says so
when the download is done, and the Wi-Fi can go off from there.

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
