# Stream audio to Berget AI

Streams a WAV file or the microphone to Pianissimo on [Berget AI](https://berget.ai)'s realtime
endpoint and prints text as it arrives. The model runs on Berget, not on your machine, and you
need a Berget API key.

## Install

Node 20 or later, and an API key from [berget.ai](https://berget.ai). From the repo root:

```bash
npm install
export BERGET_API_KEY=sk_ber_...
```

## Transcribe a file

```bash
node examples/berget-realtime/cli/transcribe-file.mjs samples/counting-sv.wav
```

Input is PCM16 mono WAV. The server resamples rates other than 16 kHz.

| Flag | Effect |
|---|---|
| `--chunk-seconds N` | Seconds of speech per server segment. Default 1 |
| `--server-default` | Use the server's segment length, 28 s. Shorter audio returns as one transcript at the end |
| `--fast` | Sends audio faster than realtime, for testing |

## Transcribe the microphone

```bash
node examples/berget-realtime/relay/server.mjs
open http://localhost:8787
```

Press Start, speak Swedish, press Stop. The relay in `relay/` holds the API key, since a browser
cannot send it on a WebSocket. It listens on 127.0.0.1 only.

---

Part of [pianissimo-examples](../../). Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme-berget-realtime).
