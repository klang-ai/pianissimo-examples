# Pianissimo examples

Pianissimo is Klang's open Swedish speech-to-text model. What it is, how it was trained and
how it measures is on the [model card](https://huggingface.co/KlangAI/pianissimo-sv). This
repo is what we have built on it so far.

Every example is a folder under `examples/` with its own README: what it does, how to run
it, what we measured, and where it breaks. There are two ways to run the model, and each
example says which one it uses.

- **Locally.** The open weights on your own machine. No API key, and the audio stays on the
  machine. Slower than a GPU server.
- **Hosted.** A realtime endpoint, streaming over a WebSocket, which gives you text back
  while the audio is still playing. Today that is Berget AI, and it needs a key.

| Example | What it does | Runs |
|---|---|---|
| [`examples/subtitles/`](examples/subtitles/) | Subtitles a Swedish video: audio or video in, `.srt` out | Locally |
| [`examples/local/`](examples/local/) | Transcribes one WAV file with the weights. Start here to check your setup | Locally |
| [`examples/offline/`](examples/offline/) | Four local apps: podcast transcripts and summaries with clips and questions, dictation, a searchable podcast archive, and a comparison of two episodes | Locally |
| [`examples/berget-realtime/`](examples/berget-realtime/) | Streams a file or the microphone and prints text as it arrives. Also our notes on the realtime API | Hosted |

[![Varje dag en världsrevy (1937), subtitled by Pianissimo on a laptop CPU](examples/subtitles/sattmaskinen.gif)](examples/subtitles/)

## Run it locally

From a clone of this repo:

```bash
git clone https://github.com/klang-ai/pianissimo-examples && cd pianissimo-examples
python3 -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
.venv/bin/python examples/local/transcribe-offline.py examples/berget-realtime/repro/counting-sv.wav
```

The clip is 12 seconds of Swedish that ships with the repo. Swap in your own file once that
works.

The first run downloads 2.34 GB of weights and caches them. `nemo_toolkit[asr]` pulls
PyTorch, about 1.7 GB.

## Run it hosted

Node 20 or later, and a Berget API key from [berget.ai](https://berget.ai).

```bash
npm install
export BERGET_API_KEY=sk_ber_...
node examples/berget-realtime/cli/transcribe-file.mjs examples/berget-realtime/repro/counting-sv.wav
```

## Built something on it?

Open an issue with a link to your project.

## License

MIT, see `LICENSE`. It covers the example code only; no weights ship with this repository.

The model weights are licensed CC BY 4.0; see the
[model card](https://huggingface.co/KlangAI/pianissimo-sv).

Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme).
