# Offline: a podcast summary and live dictation

Reviewing the code rather than running it? Start with [REVIEW.md](REVIEW.md).

Two small apps on one local server, both running Pianissimo on your own machine.
Turn the Wi-Fi off before you start. They work the same.

- **Podcast summary.** Paste a link, type the name of an episode, or drop in a
  file. Get the full transcript, a summary, chapters with timestamps you can
  click, and a quote checked against the transcript.
- **Offline dictation.** Talk, and the text appears while you speak.

And three things made from a finished episode:

- **Clip.** Select any sentence in the transcript, or take the quote, and get a
  9:16 video where each word lights up as it is spoken. Ready for LinkedIn.
- **Ask the episode.** A question in Swedish, an answer with the minutes it came from.
- **Show archive** (`/archive`). Paste a show, and every episode is transcribed in the
  background and kept on disk. Then search all of them and play from the hit.
- **Compare** (`/compare`). Two episodes on one subject: what they agree on,
  where they differ, and what only one of them brings up.

Nothing is uploaded. The browser talks to a server on `127.0.0.1`, the server
reads both models from the local cache, and a badge in the corner shows whether
the machine can reach the internet at all. That check opens a connection to
1.1.1.1 and sends nothing over it; no audio or text ever leaves the machine.

## Setup

Python 3.10 or later, ffmpeg, and llama.cpp for the summary.

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]" aiohttp soundfile
brew install ffmpeg llama.cpp yt-dlp
brew install ffmpeg-full   # only for clips: it has libass, which burns captions in
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

## How each part works

**Clip.** The selected text is found in the transcript, that stretch of audio is
transcribed again with a timing for every word, and ffmpeg draws the frame: the show
at the top, a waveform, and captions where each word fills in as it is said
(ASS karaoke tags). A second pass can hear a word slightly differently from the
first, and the captions follow the second pass, because that is the one the timings
belong to.

**Ask.** The question is ranked against the transcript's thirty second pieces with
BM25 on five-letter stems (Swedish inflects: skatt, skatten, skatterna). The model
gets the best six and is told to say "Det sägs inte i avsnittet" when they do not
answer it. The page always lists the pieces as timestamps, whether or not the model
cited them.

**Archive.** One worker thread takes the queue in order: download, transcribe,
write `<id>.json` next to the audio in `~/.cache/pianissimo/archive`
(`PIANISSIMO_ARCHIVE` to move it). Anything cut short by a restart goes back in
the queue.

**Compare.** Both episodes go through the podcast job, chapters included, and the
model compares the two chapter lists. Each point ends in `[A mm:ss]` or `[B mm:ss]`,
which the page turns into buttons that play that episode from there.

## What the other parts measured

On the same M5: a 7 s clip in about 9 s. An answer in 4 to 5 s. Five episodes of
Livet på lätt svenska, 1.9 hours, downloaded and transcribed in 76 s. Two
episodes of 25 and 29 minutes compared in about 100 s.

## Limits

- No speaker separation. The summary says what was said, not who said it,
  unless a name is spoken.
- The chapters are cut by time, a few minutes each, not by topic.
- Dictation re-reads the open sentence as you speak, so the last few words can
  change until you pause.
- The small model is weakest at disagreement. Under "Oense" it sometimes lists
  something only one episode says, which belongs under "Bara i". A larger model
  in `summary.py` fixes that and costs speed.
- A Spotify exclusive has no public feed and cannot be fetched.
