# Transcribe a WAV file locally

Transcribes one WAV file with the open weights on your own machine. Start here to check your
setup. Install from the [repo root](../../#install).

```bash
.venv/bin/python examples/local/transcribe-offline.py samples/counting-sv.wav
```

The transcript goes to stdout, load and transcription times to stderr.

## Input

Mono 16 kHz PCM16 WAV, the rate the model was trained at. The script rejects anything else. To
convert:

```bash
ffmpeg -i input.m4a -ac 1 -ar 16000 -c:a pcm_s16le input.wav
```

Swedish only.

---

Part of [pianissimo-examples](../../). Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme-local).
