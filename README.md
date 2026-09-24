# Pianissimo examples

Runnable examples for [Pianissimo](https://huggingface.co/KlangAI/pianissimo-sv), Klang's open
Swedish speech-to-text model. What the model is, how it was trained and how it measures is on
the model card. This repo is what we have built with it, in two ways: locally on your own
machine with the open weights, no API key, or streamed live through Berget AI's hosted realtime
endpoint.

| Example | What it does | Runs |
|---|---|---|
| [`examples/subtitles/`](examples/subtitles/) | Subtitles a Swedish video: audio or video in, `.srt` out | Locally, no API key |
| [`examples/local/`](examples/local/) | Transcribes a WAV file with the weights. The smallest local example | Locally, no API key |
| [`examples/berget-realtime/`](examples/berget-realtime/) | Streams a file or the microphone and prints text as it arrives, plus the notes on Berget's realtime API | Against Berget AI's hosted endpoint |

Each folder has its own README with setup, a run command, what was measured and the limits.

[![Varje dag en världsrevy (1937), subtitled by Pianissimo on a laptop CPU](examples/subtitles/sattmaskinen.gif)](examples/subtitles/)

## Run it locally

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
.venv/bin/python examples/local/transcribe-offline.py your-audio.wav
```

The first run downloads 2.34 GB of weights and caches them.

## Run it hosted

Node 20 or later, and a Berget API key from [berget.ai](https://berget.ai).

```bash
npm install
export BERGET_API_KEY=sk_ber_...
node examples/berget-realtime/cli/transcribe-file.mjs your-audio.wav
```

## License

MIT, see `LICENSE`. It covers the example code only; no weights ship with this repository.

The model is published as `cc-by-4.0` on Hugging Face and listed as `Apache 2.0` in Berget's
model catalog. Check which applies before building on it commercially.
