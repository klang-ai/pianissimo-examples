# Reviewing the offline apps

For someone reading this code cold, to review it rather than run it. The
[README](README.md) says what each page does. This file says how the code is put
together, which decisions were deliberate, and where the known weak spots are, so
the review can start where it matters.

## Map

About 1,400 lines, no dependencies beyond NeMo, aiohttp and soundfile in Python,
and none in the browser.

| File | Lines | Job |
|---|---:|---|
| `server.py` | ~410 | aiohttp app: every route, the podcast job, dictation over a WebSocket, the Origin check |
| `asr.py` | 142 | Loads Pianissimo once. `transcribe()` for batches, `words()` for word timings, `pieces()` cuts audio into 30 s |
| `fetch.py` | ~260 | Turns a link or a name into an episode's audio URL, and downloads it |
| `clip.py` | 237 | Finds a quote, times its words, renders a 9:16 video with ffmpeg-full |
| `static/*.html` | ~440 | One page per app, plain ES modules, no build step |
| `static/style.css` | ~150 | Shared tokens and components. System fonts only, so it renders offline |
| `test_offline.py` | ~110 | Stdlib unittest for everything that needs no model, network or ffmpeg |

## Routes

All on `127.0.0.1:8765`. Streaming routes answer with NDJSON, one event per line.

| Route | Method | Answers | Notes |
|---|---|---|---|
| `/api/status` | GET | JSON | Also runs the online check: a TCP connect to 1.1.1.1:443, then 8.8.8.8:53 if that fails, no payload. The page polls it every 3 s |
| `/api/resolve` | POST | JSON | `{q}` to a list of episodes. Network |
| `/api/podcast` | POST | NDJSON | Multipart file upload, then the podcast job |
| `/api/podcast-url` | POST | NDJSON | `{item}` from resolve: download, then the podcast job. Network |
| `/api/clip` | POST | JSON | `{job, text}` or `{job, start}`. Takes 5 to 20 s |
| `/ws/dictate` | WS | JSON messages | Binary PCM16 frames in, `partial` and `final` out |
| `/media/…` | GET | files | Downloaded episodes and clips, with range requests |

## How an episode moves through it

1. **In.** A file upload is written to a fresh folder under the server's media dir.
   A link goes through `fetch.resolve` and `fetch.download` into the same kind of folder.
2. **Decode.** ffmpeg to mono 16 kHz WAV, kept next to the original, because clips
   need it later.
3. **Job.** `podcast_job` registers `app["jobs"][id]` straight away and emits
   `{type: "job"}`, so the page can refer to it before anything else is done.
4. **Transcribe.** 30 s pieces, eight at a time, each emitted as it lands.
5. **After.** The job stays in memory, with its pieces, until the server stops.
   `/api/clip` reads it from there.

## Decisions worth checking

These were chosen on purpose. Each one is the thing to challenge if it looks wrong.

- **Only one model.** An earlier version also ran a small language model for
  summaries, chapters and questions. It was taken out so that the example shows
  Pianissimo and nothing else, and so that it runs on a machine without room for
  a second model. Everything left on the page comes from the speech model:
  the text, the timestamps and the word timings in the clips.
- **Only open sources.** Apple's public directory, RSS, Sveriges Radio's open API
  and pages with a player on them. Spotify is refused with a pointer to the show's
  feed; nothing goes through yt-dlp. Both were behind a flag in an earlier version
  and are now out, because neither belongs in something other people run.
- **Sveriges Radio goes through its open API** because its pages answer 403 to
  plain requests from this machine.
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

1. **Tests cover the parts that need no model.** `test_offline.py` checks `fetch`
   and `clip`. The routes, the dictation page and everything that touches the model
   are verified only by running them.
2. **Nothing is ever cleaned up while the server runs.** Jobs stay in memory and
   downloads in the media dir until shutdown. An evening of long episodes is
   gigabytes.
3. **The server will download any URL it is given**, including ones on the local
   network. The Origin check stops other web pages from doing it; anything
   running on this machine still can.
4. **A clip's captions can differ slightly from the transcript**, because the
   stretch is transcribed a second time to get word timings, and the second pass
   can hear a word differently. `clip.span` tolerates the drift by scoring how many
   words line up rather than demanding all of them.
5. **Words at a piece boundary.** The 30 s pieces do not overlap, so a word spoken
   across the cut can be split or dropped in the transcript. `clip.locate` searches
   across two pieces at a time so the clip still finds a sentence that straddles one.
6. **Audio playback in the page was not seen working** in the automated Chrome
   used during development, where media elements never loaded. The server's range
   responses were checked with curl (206, correct type).
7. **Cover images load from the podcast's own servers.** The episode list shows
   `image` URLs from the feed directly, so opening that list fetches them.
8. **The server does not check `Host`.** The Origin check stops other pages, but a
   DNS-rebinding page could still reach it. Low risk for a local demo; would need a
   Host allowlist before anything else.

## How to verify each part

Without the server, from the repo root:

```bash
python3 examples/offline/test_offline.py
```

With the server running (`.venv/bin/python examples/offline/server.py`):

```bash
# Resolve a Spotify link: expect 404 and a message pointing to the feed
curl -s -X POST localhost:8765/api/resolve -H 'Content-Type: application/json' \
  -d '{"q":"https://open.spotify.com/episode/7t5EYXfU6usMYduhVBS9nQ"}'

# Origin check: expect 403, then 200
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8765/api/resolve \
  -H 'Origin: https://example.com' -H 'Content-Type: text/plain' -d '{"q":"x"}'
curl -s -o /dev/null -w '%{http_code}\n' localhost:8765/api/status
```

The rest is quickest in the browser: `/podcast` with `sommar i p1` in the box, then
select a sentence in the transcript and clip it.
