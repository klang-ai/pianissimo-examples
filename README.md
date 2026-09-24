# Pianissimo examples

Examples built on [Pianissimo](https://huggingface.co/KlangAI/pianissimo-sv), Klang's open
Swedish speech-to-text model.

| Example | What it does | Runs |
|---|---|---|
| [`examples/subtitles/`](examples/subtitles/) | Swedish audio or video in, `.srt` out | Locally |
| [`examples/local/`](examples/local/) | Transcribes one WAV file. Start here to check your setup | Locally |
| [`examples/berget-realtime/`](examples/berget-realtime/) | Streams a file or the microphone and prints text as it arrives | Berget AI |

Local examples run the open weights on your own machine: no API key, and the audio stays on
the machine. The hosted example streams audio to Berget AI's realtime endpoint, the only
hosted endpoint these examples support, and needs a Berget API key.

[![Varje dag en världsrevy (1937), subtitled by Pianissimo on a laptop CPU](examples/subtitles/sattmaskinen.gif)](examples/subtitles/)

## Install

```bash
git clone https://github.com/klang-ai/pianissimo-examples && cd pianissimo-examples
python3 -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
.venv/bin/python examples/local/transcribe-offline.py samples/counting-sv.wav
```

`nemo_toolkit[asr]` pulls PyTorch, about 1.7 GB. The first run downloads the model, 2.34 GB,
and caches it. `samples/counting-sv.wav` is a 12-second Swedish clip.

## Built something on it?

Open an issue with a link to your project.

## License

MIT for the example code. The model weights are CC BY 4.0, see the
[model card](https://huggingface.co/KlangAI/pianissimo-sv).

Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme).
