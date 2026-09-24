# Any podcast, on your own machine

Paste a podcast, get the transcript, a summary with chapters, and a vertical clip of any
quote. Pianissimo does the speech to text; summaries and answers come from a small language
model, Qwen3 4B through llama.cpp. Both run on your machine, behind a local web server.
Download the models, and any episodes you want, before going offline.

![The podcast page: a 52 minute episode transcribed in 52 s, summary 10 s later](podcast-page.png)

![A frame from a clip: the quote fills in word by word over a waveform](clip-frame.png)

*Left: a 52 minute episode, transcribed in 52 s on a MacBook Pro M5, summary ready 10 s
later. Right: a clip made from one sentence of a P1 Kultur report, 8 minutes transcribed in
6 s. The captions light up word by word as it is spoken.*

The same server has three more pages: dictation, a searchable archive of a whole show, and
a comparison of two episodes.

Reviewing the code rather than running it? Start with [REVIEW.md](REVIEW.md).

- **Podcast summary.** Paste a link, type the name of an episode, or drop in a file. Full
  transcript, a summary, chapters with timestamps you can click, and a quote checked against
  the transcript. From a finished episode you can also **clip** any sentence as a 9:16 video
  with word-by-word captions, and **ask** it a question in Swedish and get the minutes the
  answer came from.
- **Dictation.** Swedish speech to text as you speak. The only one that never needs the
  internet; the others need it once, to fetch the episode.
- **Show archive** (`/archive`). Paste a show. Every episode is transcribed in the background
  and kept on disk. Search all of them and play from the hit.
- **Compare** (`/compare`). Two episodes on one subject: what they agree on, where they
  differ, and what only one of them brings up.

What uses the network:

- the link or search words you paste, sent to Apple's podcast directory or the site that
  hosts the episode, and the audio download itself;
- cover images, loaded from the podcast's own servers when a page shows them;
- the badge in the corner, which every 3 s opens a TCP connection to 1.1.1.1:443, or
  8.8.8.8:53 if that fails, and sends nothing over it.

What does not: anything you record, upload or transcribe. Transcription, summaries, clips,
answers and dictation run locally, and the browser only talks to the server on `127.0.0.1`.
The badge in the corner says whether the machine has internet right now; turn the Wi-Fi off
and it flips to "No internet. Still works", which is the point.

## Setup

Python 3.10 or later, ffmpeg, and llama.cpp for the summary.

Run everything from the repo root.

```bash
python3 -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]" aiohttp soundfile
brew install ffmpeg llama.cpp
brew install ffmpeg-full   # only for clips: it has libass, which burns captions in
```

Download both models once, with the network on:

```bash
.venv/bin/hf download KlangAI/pianissimo-sv
.venv/bin/hf download unsloth/Qwen3-4B-Instruct-2507-GGUF Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

That is 2.34 GB for Pianissimo and 2.5 GB for the summary model.

## Run

```bash
.venv/bin/python examples/offline/server.py
```

Open http://127.0.0.1:8765. The first start takes a few seconds while both models load;
after that the server is ready.

Tests for the parts that need no model:

```bash
python3 examples/offline/test_offline.py
```

## Any link, or just a name

The box on the podcast page takes:

| You paste | What happens |
|---|---|
| An Apple Podcasts link | Looked up in Apple's public directory. |
| Sveriges Radio | Its open API, since its pages refuse plain requests. |
| An RSS feed, or a page with a player on it | The feed's episodes, or the audio the page plays. |
| Just words, like `sommar i p1 zlatan` | A search for episodes in Apple's directory, Swedish storefront. |
| A Spotify episode or show | Only with `--any-link`. Spotify does not hand out episode audio. The show name and episode title are read from the page, the show's public RSS feed is found in Apple's directory, and the same episode is taken from there. Spotify exclusives have no feed. |
| YouTube, Acast, SoundCloud and about a thousand other sites | Only with `--any-link`, through [yt-dlp](https://github.com/yt-dlp/yt-dlp). Needs `brew install yt-dlp`. |

`--any-link` is for trying things on your own machine. Reading Spotify's page is scraping,
and downloading from YouTube is against its terms of service, so neither belongs in a hosted
service.

The page says when the download is done. From there the episode can be transcribed,
summed up, clipped and asked with the Wi-Fi off.

## How it works

**The summary stays fast by never reading the whole transcript.** Pianissimo turns speech
into text and stops there. The summary comes from a small instruction model, Qwen3 4B, run by
llama.cpp on the same machine. A small model slows down a lot on long input, so each chapter
of a few minutes is summarised as soon as it is transcribed, while the next one is still
being transcribed, and the episode summary is written from the chapters. That is also why
the chapter timestamps are real: they are where each piece of audio starts, not a guess by
the model. A quote is only shown if it appears word for word in the transcript.

**Clip.** The selected text is found in the transcript, that stretch of audio is transcribed
again with a timing for every word, and ffmpeg draws the frame: the show at the top, a
waveform, and captions where each word fills in as it is said (ASS karaoke tags). A second
pass can hear a word slightly differently from the first, and the captions follow the second
pass, because that is the one the timings belong to.

**Ask.** The question is ranked against the transcript's thirty second pieces with BM25 on
five-letter stems (Swedish inflects: skatt, skatten, skatterna). The model gets the best six
and is told to say "Det sägs inte i avsnittet" when they do not answer it. The page always
lists the pieces as timestamps, whether or not the model cited them.

**Archive.** One worker thread takes the queue in order: download, transcribe, write
`<id>.json` next to the audio in `~/.cache/pianissimo/archive` (`PIANISSIMO_ARCHIVE` to move
it). Anything cut short by a restart goes back in the queue.

**Compare.** Both episodes go through the podcast job, chapters included, and the model
compares the two chapter lists. Each point ends in `[A mm:ss]` or `[B mm:ss]`, which the page
turns into buttons that play that episode from there.

## What we measured

Each measured once, on a MacBook Pro with an M5 and 24 GB. A 51 minute episode of Ekots lördagsintervju: transcribed
in 55 s with the summary model running alongside, summary ready 11 s later, 69 s from
dropping the file to done. Transcription alone runs at about 105 times real time on the M5's
GPU.

Dictation shows new text every 0.4 s, and each update takes 130 to 350 ms.

On the same machine: a 7 s clip in about 9 s. An answer in 4 to 5 s. Five episodes of Livet
på lätt svenska, 1.9 hours, downloaded and transcribed in 76 s. Two episodes of 25 and 29
minutes compared in about 100 s.

## Limits

- No speaker separation. The summary says what was said, not who said it, unless a name is
  spoken.
- The chapters are cut by time, a few minutes each, not by topic.
- Dictation re-reads the open sentence as you speak, so the last few words can change until
  you pause. Stop waits up to 30 s for the last words; if the model is busy longer than that,
  the text already on screen is kept.
- The small model is weakest at disagreement. Under "Oense" it sometimes lists something only
  one episode says, which belongs under "Bara i". A larger model in `summary.py` may do better
  at the cost of speed; we have not tested one.
- A Spotify exclusive has no public feed and cannot be fetched.
- An archive job and a podcast job share one model, so a full queue slows the podcast page
  down until the queue is done.

---

Part of [pianissimo-examples](../../). Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme-offline).
