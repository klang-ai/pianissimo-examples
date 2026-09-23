# Pianissimo realtime examples

Runnable examples for [Klang Pianissimo](https://huggingface.co/KlangAI/pianissimo-sv), an open
Swedish speech-to-text model, streaming through [Berget AI](https://berget.ai).

Two examples, same endpoint:

- `cli/` streams a WAV file and prints text as it arrives. No browser, no build step.
- `browser/` streams your microphone. Needs the relay in `relay/`, for the reason below.

Everything here is verified against the live endpoint, not written from the spec.

## Requirements

- Node 20 or later
- A Berget API key. Sign up at [berget.ai](https://berget.ai). The trial has no monthly cost and
  starts with 5 EUR of credit, but a card is required at signup. At the current rate that credit
  covers roughly 24 hours of audio.

```bash
npm install
export BERGET_API_KEY=sk_ber_...
```

## Transcribe a file

Input must be uncompressed PCM16 mono WAV. Any sample rate works.

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

Flags:

| Flag | Effect |
|---|---|
| `--chunk-seconds N` | Seconds of speech per server segment. Default 1. |
| `--server-default` | Leave `chunk_seconds` unset and use the server default. |
| `--fast` | Send audio faster than realtime. Useful for testing, not for live input. |

## Transcribe the microphone

```bash
node relay/server.mjs
open http://localhost:8787
```

Press Start, speak Swedish, press Stop.

## Transcribe offline, no API key

The weights are open. You can skip the hosted endpoint and run the model yourself.

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
.venv/bin/python python/transcribe-offline.py your-audio.wav
```

Input must be mono 16 kHz PCM16 WAV.

Be honest with yourself about the cost before you start: `nemo_toolkit[asr]` pulls PyTorch and
lands at about 1.7 GB, and the weights are another 2.34 GB downloaded once and cached. That is a
different proposition from the realtime path, which is an API key and a few lines.

Measured on an M-series MacBook, CPU only, 45.8 seconds of Swedish speech:

| | |
|---|---|
| Model load, first run | 181 s, including the 2.34 GB download |
| Model load, cached | 5.7 s |
| Transcription | 1.4 to 1.6 s, about 30x realtime |

The launch figures are from an H100. A laptop is two orders of magnitude slower and still
transcribes three quarters of a minute of speech in under two seconds.

## What to know before you build

### The browser cannot connect directly

Berget authenticates with an `Authorization` header. Browsers cannot set headers on a WebSocket.
Query string and subprotocol auth both return 401, including OpenAI's
`openai-insecure-api-key.<key>` convention. Verified against all six variants.

So any web client needs a server that holds the key. `relay/server.mjs` is the smallest one that
works: it forwards frames verbatim in both directions, so the browser code is the same code you
would write against Berget, minus the credential. One detail matters. Forward frames as text.
The `ws` library sends a Buffer as a binary frame, and the endpoint never answers those.

### `chunk_seconds` decides whether you get streaming at all

The default is **28 seconds**. Speak for less than that and you get one transcript at the end,
which looks like the stream is broken. It is not.

Set it explicitly, and set it in the right place:

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

Put `chunk_seconds` anywhere else and it is dropped silently, with no error. Read it back from
`session.updated`, which echoes the configuration the server actually applied. That is the only
way to see that it was ignored.

### Faster text is worse text

Same 14 seconds of Swedish debate audio, one run each:

| Setting | First text | Transcript |
|---|---|---|
| `chunk_seconds` unset (28 s) | 4.21 s | "till radhuset och säger" ... "Jimmie Åkesson" |
| `chunk_seconds: 1` | 1.40 s | "hem till radhus och då säger" ... "Jimmy Åkesson" |

Pick the value for your use case. Live captions want 1. A meeting transcript that is read
afterwards wants a higher value or the default.

### Audio format

- PCM16 little endian, mono. Also accepted: `audio/pcmu` and `audio/pcma` (G.711, 8 kHz).
- The format and rate lock after the first `input_audio_buffer.append`. Decide up front.
- The default rate is 24000 Hz. Send what you have and declare it, the server handles the rest.
- The model itself is trained at 16 kHz.

### Turn handling

- Without `turn_detection`, commit turns yourself with `input_audio_buffer.commit`.
- With `turn_detection: { type: 'server_vad' }`, turns commit on speech pauses. On continuous
  speech with no pause, nothing commits, so set `chunk_seconds` too if you want text meanwhile.
- `semantic_vad` is not implemented.
- Sessions survive across turns but are not resumable. On close codes 1012 and 1013 the node is
  draining for a deploy: reconnect and start a new session.

### Batch transcription is a different endpoint

`POST /v1/audio/transcriptions` does not serve `klang/pianissimo`. The realtime endpoint serves
only `klang/pianissimo` and rejects everything else. Pianissimo is a streaming model here; for
finished recordings Berget offers other models on the batch endpoint.

## Reproducing the first-word loss

`repro/first-word.mjs` runs one audio file through two sessions. The only difference between them
is `chunk_seconds`. Audio, pacing, sample rate and model are identical.

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

The clip is 12.2 s, shorter than the 28 s default, so run A is never segmented by the timer and
its turn closes on commit. Run B segments every 3 s and loses the opening word.

The same weights run locally keep the word, so this sits in the streaming path rather than in the
model. `repro/make-audio.sh` regenerates the clip with macOS text to speech if you want your own.

## License

MIT, matching [`klang-ai/klang-sdk-ts`](https://github.com/klang-ai/klang-sdk-ts). See `LICENSE`.

This covers the example code only. It ships no model weights and calls the API over HTTP, so the
model's own license governs the model, not this repository.

One thing worth knowing if you go on to download the weights: the model is published as
`cc-by-4.0` on Hugging Face and listed as `Apache 2.0` in Berget's model catalog. Check which
applies before you build on it commercially.
