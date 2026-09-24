# Reviewing the offline apps

For someone reading this code cold, to review it rather than run it. The
[README](README.md) says what each app does. This file says how the code is put
together, which decisions were deliberate, and where the known weak spots are, so
the review can start where it matters.

## Map

About 3,000 lines, no dependencies beyond NeMo, aiohttp and soundfile in Python,
and none in the browser.

| File | Lines | Job |
|---|---:|---|
| `server.py` | 595 | aiohttp app: every route, the podcast job, dictation over a WebSocket, the Origin check |
| `asr.py` | 142 | Loads Pianissimo once. `transcribe()` for batches, `words()` for word timings, `pieces()` cuts audio into 30 s |
| `summary.py` | 207 | Starts `llama-server`, and every prompt: chapter, summary, compare. Also the online check |
| `fetch.py` | 370 | Turns a link or a name into an episode's audio URL, and downloads it |
| `clip.py` | 234 | Finds a quote, times its words, renders a 9:16 video with ffmpeg-full |
| `ask.py` | 67 | BM25 over the 30 s pieces, and the answer prompt |
| `archive.py` | 149 | Background queue, JSON on disk, search across episodes |
| `static/*.html` | ~830 | One page per app, plain ES modules, no build step |
| `static/style.css` | 204 | Shared tokens and components. System fonts only, so it renders offline |
| `test_offline.py` | ~150 | Stdlib unittest for everything that needs no model, network or ffmpeg |

## Routes

All on `127.0.0.1:8765`. Streaming routes answer with NDJSON, one event per line.

| Route | Method | Answers | Notes |
|---|---|---|---|
| `/api/status` | GET | JSON | Also runs the online check: a TCP connect to 1.1.1.1:443, then 8.8.8.8:53 if that fails, no payload. The page polls it every 3 s |
| `/api/resolve` | POST | JSON | `{q}` to a list of episodes. Network |
| `/api/podcast` | POST | NDJSON | Multipart file upload, then the podcast job |
| `/api/podcast-url` | POST | NDJSON | `{item}` from resolve: download, then the podcast job. Network |
| `/api/clip` | POST | JSON | `{job, text}` or `{job, start}`. Takes 5 to 20 s |
| `/api/ask` | POST | NDJSON | `{job, question}` |
| `/api/compare` | POST | NDJSON | `{a, b}` items. Two podcast jobs in a row, then the comparison |
| `/api/archive` | GET, POST | JSON | Status, or queue episodes by `{q, limit}` or `{items}` |
| `/api/archive/search` | GET | JSON | `?q=` |
| `/ws/dictate` | WS | JSON messages | Binary PCM16 frames in, `partial` and `final` out |
| `/media/…`, `/archive-media/…` | GET | files | Downloaded episodes and clips, with range requests |

## How an episode moves through it

1. **In.** A file upload is written to a fresh folder under the server's media dir.
   A link goes through `fetch.resolve` and `fetch.download` into the same kind of folder.
2. **Decode.** ffmpeg to mono 16 kHz WAV, kept next to the original, because clips
   need it later.
3. **Job.** `podcast_job` registers `app["jobs"][id]` straight away and emits
   `{type: "job"}`, so the page can refer to it before anything else is done.
4. **Transcribe.** 30 s pieces, eight at a time, each emitted as it lands.
5. **Chapters, overlapped.** Whenever a chapter's worth of pieces is done, it goes
   to a two-worker pool that asks the language model for a title, one line and a
   quote. That runs while the next pieces are still being transcribed.
6. **Summary.** From the chapter list, not the transcript, streamed token by token.
7. **After.** The job stays in memory, with its pieces and chapters, until the
   server stops. Clip, ask and compare all read it from there.

## Decisions worth checking

These were chosen on purpose. Each one is the thing to challenge if it looks wrong.

- **The summary model never sees the whole transcript.** A 4B model on the M5
  reads about 850 tokens a second at 4k of context and 350 at 16k. The first
  version fed it the full transcript: 109 s for an hour, and chapters with invented
  timestamps one minute apart. Chapter-first brought it to 69 s, and the
  timestamps are real because they are where each piece of audio starts.
- **Chapters are cut by time, not by topic.** Real topic boundaries would need a
  pass over the whole transcript, which is the thing we avoid.
- **A quote is kept only if it appears in the transcript**, compared after
  lowercasing and stripping punctuation (`summary._normal`). The small model
  paraphrases and calls it a quote often enough that this matters.
- **Spotify and yt-dlp are behind `--any-link`** (`fetch.ANY_LINK`). Spotify's page
  is scraped for show and title, and YouTube downloads are against its terms, so both
  are off unless the person running the server turns them on. With the flag, a
  Spotify link is resolved to show and title, then to the show's public RSS feed
  through Apple's directory, and the episode is matched by title with length as a
  tiebreak (`fetch.match_in_feed`, threshold 0.6 word overlap). Spotify is never
  asked for audio.
- **Sveriges Radio goes through its open API** because its pages answer 403 to
  both plain requests and yt-dlp from this machine.
- **ffmpeg runs without `DYLD_LIBRARY_PATH`** (`clip._env`). The NeMo import sets it
  to `/opt/homebrew/lib`, and ffmpeg-full then loads the plain ffmpeg's libraries
  and dies on a missing symbol. It fails only after the model has loaded, which is
  why it looked like a missing libass at first.
- **Dictation re-reads the whole open segment** every 0.4 s rather than streaming.
  Pianissimo is an offline model; this is the simplest way to get live text out of
  it. Segments close on 0.6 s of quiet or at 12 s, so the cost stays bounded.
- **The Origin check** (`server.same_origin`). Without it, any page open in the
  browser could make the server fetch a URL of its choosing or open the dictation
  socket, because a text/plain POST skips the CORS preflight and WebSockets are not
  covered by CORS. Requests with no Origin, like curl, are let through.

## Known weak spots

Not fixed, and known. Listed so a review does not have to rediscover them.

1. **Tests cover the parts that need no model.** `test_offline.py` checks `fetch`,
   `ask`, `summary` and `clip`, the `--any-link` check at download, the yt-dlp
   deadline, and the archive worker picking up an episode added while it was leaving.
   The routes, the dictation page and everything that touches a model are verified
   only by running them.
2. **Nothing is ever cleaned up while the server runs.** Jobs stay in memory and
   downloads in the media dir until shutdown. An evening of long episodes is
   gigabytes.
3. **The server will download any URL it is given**, including ones on the local
   network. The Origin check stops other web pages from doing it; anything
   running on this machine still can.
4. **"Oense" in a comparison** is the small model's weakest output. It often lists
   something only one episode says. The prompt forbids it and it still happens.
5. **A clip's captions can differ slightly from the transcript**, because the
   stretch is transcribed a second time to get word timings, and the second pass
   can hear a word differently. `clip.span` tolerates the drift by scoring how many
   words line up rather than demanding all of them.
6. **YouTube through yt-dlp and Spotify's page** are off by default and behind
   `--any-link`, checked both when a link is resolved and when a download starts.
   Turning the flag on is the operator's choice, and the source's terms still apply.
   Neither belongs in a hosted feature.
7. **An orphaned `llama-server`.** It is started detached. If the Python server is
   killed hard, it keeps running on port 8099, and the next start reuses it.
8. **The archive has no cancel and no retry.** A failed episode is marked and left;
   adding it again requeues it. A yt-dlp download is killed after 30 minutes; a plain
   download has a 60 s timeout per read.
9. **Answers can attribute.** The prompts say never to guess who is speaking, but a
   name spoken in the transcript can end up attached to the wrong claim.
10. **Audio playback in the page was not seen working** in the automated Chrome
    used during development, where media elements never loaded. The server's range
    responses were checked with curl (206, correct type).
11. **Cover images load from the podcast's own servers.** The episode list and the
    archive show `image` URLs from the feed directly, so opening those pages fetches
    them, also after the audio is on disk.
12. **The server does not check `Host`.** The Origin check stops other pages, but a
    DNS-rebinding page could still reach it. Low risk for a local demo; would need a
    Host allowlist before anything else.

## How to verify each part

Without the server, from the repo root:

```bash
python3 examples/offline/test_offline.py
```

With the server running (`.venv/bin/python examples/offline/server.py`):

```bash
# Resolve: expect 404 and a message naming --any-link
curl -s -X POST localhost:8765/api/resolve -H 'Content-Type: application/json' \
  -d '{"q":"https://open.spotify.com/episode/7t5EYXfU6usMYduhVBS9nQ"}'
# Started with --any-link: expect one item, "Spotify, then the show's public RSS feed", 1317 s

# Origin check: expect 403, then 200
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8765/api/resolve \
  -H 'Origin: https://example.com' -H 'Content-Type: text/plain' -d '{"q":"x"}'
curl -s -o /dev/null -w '%{http_code}\n' localhost:8765/api/status
```

The rest is quickest in the browser: `/podcast` with `sommar i p1` in the box, then
ask it something it does not cover (expect "Det sägs inte i avsnittet"), then select
a sentence in the transcript and clip it.
