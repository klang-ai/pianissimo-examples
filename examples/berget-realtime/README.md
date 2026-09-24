# Stream audio to the hosted endpoint

Text back while the audio is still playing. This is the example to start from if you would
rather call an endpoint than install PyTorch, or if you need live text at all. Runs hosted:
`klang/pianissimo` on [Berget AI](https://berget.ai)'s realtime endpoint, over a WebSocket.

Three small programs and one reproduction:

| | |
|---|---|
| `cli/transcribe-file.mjs` | Streams a WAV file and prints text as it arrives |
| `browser/` | Streams the microphone from a web page, through the relay |
| `relay/server.mjs` | Holds the API key and forwards WebSocket frames between browser and Berget |
| `repro/first-word.mjs` | Reproduces a first-word loss in the streaming path |
| `lib/` | The session messages and a WAV reader, shared by the three above |

## Setup

Node 20 or later, and a Berget API key. The trial starts with 5 EUR of credit and requires a
card at signup. At the current rate that covers roughly 24 hours of audio.

From the repo root:

```bash
npm install
export BERGET_API_KEY=sk_ber_...
```

## Transcribe a file

Input: uncompressed PCM16 mono WAV, any sample rate.

```bash
node examples/berget-realtime/cli/transcribe-file.mjs your-audio.wav
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

## Transcribe the microphone

```bash
node examples/berget-realtime/relay/server.mjs
open http://localhost:8787
```

Press Start, speak Swedish, press Stop.

## What we ran into

Written down so you do not have to find them again.

### The browser cannot connect directly

Berget authenticates with an `Authorization` header, and browsers cannot set headers on a
WebSocket. Query string and subprotocol auth both return 401, including OpenAI's
`openai-insecure-api-key.<key>` convention; we tried six variants.

So a web client needs a server that holds the key. `relay/server.mjs` forwards frames
verbatim in both directions, which means the browser code is what you would write against
Berget, minus the credential. Forward frames as text: the `ws` library sends a Buffer as a
binary frame, and the endpoint does not answer those.

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
BERGET_API_KEY=sk_ber_... node examples/berget-realtime/repro/first-word.mjs
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

---

Part of [pianissimo-examples](../../). Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme-berget-realtime).
