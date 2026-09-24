# Pianissimo examples

Runnable examples for [Pianissimo](https://huggingface.co/KlangAI/pianissimo-sv), Klang's open
Swedish speech-to-text model. Two ways to run it: locally on your own machine with the open
weights, no API key, or streamed live through Berget AI's hosted realtime endpoint.

[![A 1937 Swedish newsreel with subtitles generated on a laptop](examples/subtitles/sattmaskinen.gif)](examples/subtitles/)

| Directory | What it does | Runs |
|---|---|---|
| [`examples/subtitles/`](examples/subtitles/) | Subtitles a Swedish video: audio or video in, `.srt` out | Locally, no API key |
| `python/` | Transcribes a WAV file with the weights | Locally, no API key |
| `cli/` | Streams a WAV file and prints text as it arrives | Against Berget AI's realtime endpoint |
| `browser/` | Streams the microphone, through the relay in `relay/` | Against Berget AI's realtime endpoint |
| `repro/` | Reproduces a first-word loss in the streaming path | Against Berget AI's realtime endpoint |

## Local: run the weights yourself

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
.venv/bin/python python/transcribe-offline.py your-audio.wav
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

## Hosted: the realtime endpoint on Berget

Node 20 or later, and a Berget API key from [berget.ai](https://berget.ai). The trial starts
with 5 EUR of credit and requires a card at signup. At the current rate that covers roughly
24 hours of audio.

```bash
npm install
export BERGET_API_KEY=sk_ber_...
```

### Transcribe a file

Input: uncompressed PCM16 mono WAV, any sample rate.

```bash
node cli/transcribe-file.mjs your-audio.wav
```

```
your-audio.wav: 14.0 s, PCM16 mono @ 16000 Hz
chunk_seconds=1: expect partial text while the audio streams
  0.65s session ready, model=klang/pianissimo chunk_seconds=1
hem till radhus och då säger Jag har blivit av med jobbet. Det blir ingen skidresa i vinter. ...
  3.91s complete, billed 14 s of audio
first text after 1.40 s
```

| Flag | Effect |
|---|---|
| `--chunk-seconds N` | Seconds of speech per server segment. Default 1. |
| `--server-default` | Leave `chunk_seconds` unset and use the server default. |
| `--fast` | Send audio faster than realtime. For testing, not for live input. |

### Transcribe the microphone

```bash
node relay/server.mjs
open http://localhost:8787
```

Press Start, speak Swedish, press Stop.

## Notes on the realtime API

Things we ran into while building the streaming examples. Each one cost an hour or so to find.

### The browser cannot connect directly

Berget authenticates with an `Authorization` header, and browsers cannot set headers on a
WebSocket. Query string and subprotocol auth both return 401, including OpenAI's
`openai-insecure-api-key.<key>` convention; six variants were tried.

A web client therefore needs a server that holds the key. `relay/server.mjs` forwards frames
verbatim in both directions, so the browser code is what you would write against Berget, minus
the credential. Forward frames as text: the `ws` library sends a Buffer as a binary frame, and
the endpoint does not answer those.

### `chunk_seconds` controls whether text streams

The default is 28 seconds. Speak for less than that and the transcript arrives in one piece at
the end. Set it explicitly, under `transcription`:

```js
session: {
  type: 'transcription',
  audio: {
    input: {
      format: { type: 'audio/pcm', rate: 16000 },
      transcription: {
        model: 'klang/pianissimo',
        languages: ['sv'],
        chunk_seconds: 1,        // here, under transcription
      },
    },
  },
}
```

Set anywhere else, it is dropped without an error. `session.updated` echoes the configuration
the server applied, so read it back to check.

### A lower `chunk_seconds` gives earlier text and more errors

Same 14 seconds of Swedish debate audio, one run each:

| Setting | First text | Transcript |
|---|---|---|
| `chunk_seconds` unset (28 s) | 4.21 s | "till radhuset och säger" ... "Jimmie Åkesson" |
| `chunk_seconds: 1` | 1.40 s | "hem till radhus och då säger" ... "Jimmy Åkesson" |

Live captions: 1. A transcript read afterwards: a higher value, or the default.

### Audio format

- PCM16 little endian, mono. Also accepted: `audio/pcmu` and `audio/pcma` (G.711, 8 kHz).
- The format and rate lock after the first `input_audio_buffer.append`.
- The default rate is 24000 Hz. Send what you have and declare it; the server resamples.
- The model is trained at 16 kHz.

### Turn handling

- Without `turn_detection`, commit turns yourself with `input_audio_buffer.commit`.
- With `turn_detection: { type: 'server_vad' }`, turns commit on speech pauses. Continuous
  speech with no pause never commits, so set `chunk_seconds` too if you want text meanwhile.
- `semantic_vad` is not implemented.
- Sessions survive across turns but are not resumable. Close codes 1012 and 1013 mean the node
  is draining for a deploy: reconnect and start a new session.

### Batch transcription is a different endpoint

`POST /v1/audio/transcriptions` does not serve `klang/pianissimo`, and the realtime endpoint
serves only `klang/pianissimo`. For finished recordings, Berget offers other models on the
batch endpoint.

## Reproducing the first-word loss

`repro/first-word.mjs` runs one audio file through two sessions that differ only in
`chunk_seconds`. Audio, pacing, sample rate and model are identical.

```bash
BERGET_API_KEY=sk_ber_... node repro/first-word.mjs
```

```
--- run A: chunk_seconds unset (server applied 28)
    opening word: KEPT
    1. Stockholm är Sveriges huvudstad. 2. Göteborg ligger på västkusten. ...

--- run B: chunk_seconds 3 (server applied 3)
    opening word: LOST
    Stockholm är Sveriges huvudstad. Två. Göteborg ligger på V. Tre. ...
```

The clip is 12.2 s, shorter than the 28 s default, so run A is never segmented by the timer
and its turn closes on commit. Run B segments every 3 s and loses the opening word. The same
weights run locally keep the word, so the loss is in the streaming path, not in the model.

Berget reported a fix on 23 September 2026 that keeps the opening word at 3 s and 1 s chunks,
with a release planned the same day. The output above is from before the fix.
`repro/make-audio.sh` regenerates the clip with macOS text to speech.

## License

MIT, see `LICENSE`. It covers the example code only; no weights ship with this repository.

The model is published as `cc-by-4.0` on Hugging Face and listed as `Apache 2.0` in Berget's
model catalog. Check which applies before building on it commercially.
