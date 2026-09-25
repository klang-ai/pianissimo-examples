# Subtitle a Swedish video

Creates an `.srt` file from Swedish audio or video on your own machine. Pianissimo gives a
timing for every word, and `cues.py` groups the words into subtitle lines.

![A 1937 Swedish newsreel with subtitles generated on a laptop](sattmaskinen.gif)

*Varje dag en världsrevy (AB Svensk Filmindustri, 1937), public domain via Wikimedia Commons,
cut to the parts with speech. Subtitled on a laptop CPU.*

## Install

Python 3.10 or later. Install from the [repo root](../../#install), then ffmpeg:

```bash
brew install ffmpeg
```

## Run

```bash
.venv/bin/python examples/subtitles/subtitle.py talk.mp4
```

Writes `talk.srt` next to the input. Takes any file ffmpeg reads. `sample.srt` is the output
for `samples/counting-sv.wav`. `--verbose` shows NeMo's own logging.

Cues are at most 2 lines of 42 characters, 17 characters per second, 1 to 6 seconds long, and
break on 0.7 s of silence. Start times are never moved, so a subtitle never appears before the
word is spoken. The rules are at the top of `cues.py`.

## Burn the text into the picture

```bash
./examples/subtitles/burn-in.sh talk.mp4 talk.srt
```

Writes `talk-subtitled.mp4`, for platforms that ignore a separate subtitle file. Needs an
ffmpeg with libass: `brew install ffmpeg-full`. The script finds it without a change to `PATH`.

## Limits

- Cues are never shortened, so fast speech can exceed 17 characters per second.
- Recordings longer than 20 minutes are transcribed in 20-minute pieces. A two-hour recording
  used 16 GB of memory on an Apple M5 CPU.
- Music and overlapping speech shift the timings.
- No speaker labels. Swedish only.

---

Part of [pianissimo-examples](../../). Pianissimo is made by [Klang](https://klang.ai/pianissimo/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme-subtitles).
