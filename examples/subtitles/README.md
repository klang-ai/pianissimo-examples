# Subtitle a Swedish video

![A 1937 Swedish newsreel with subtitles generated on a laptop](sattmaskinen.gif)

*Varje dag en världsrevy (AB Svensk Filmindustri, 1937), public domain via Wikimedia Commons,
cut to the parts with speech. Subtitled by Pianissimo on a laptop CPU, network off.*

Audio or video in, a broadcast-shaped `.srt` out, running on your own machine.

No API key, no account, no upload. The weights come from Hugging Face once and
everything after that is local, so the audio never leaves the machine. That
matters for the footage you cannot send to a third party, and it makes the
per-minute cost zero once the model is on disk.

The full fourteen minute film took 17 seconds, 50 times faster than real time,
on a MacBook CPU.

## Setup

Python 3.10 or later, and ffmpeg.

```bash
python -m venv .venv && .venv/bin/pip install "nemo_toolkit[asr]"
brew install ffmpeg
```

First run downloads 2.34 GB of weights and caches them. `nemo_toolkit[asr]`
pulls PyTorch and lands at about 1.7 GB.

## Run

```bash
.venv/bin/python examples/subtitles/subtitle.py talk.mp4
```

Writes `talk.srt` next to the input. Takes any file ffmpeg reads; audio is
extracted to mono 16 kHz internally.

```
talk.mp4: 12.2 s of audio
loading KlangAI/pianissimo-sv on cpu
loaded in 5.6 s
transcribed in 0.8 s, 15x realtime
21 words in 4 cues -> talk.srt
```

Add `--verbose` when something fails. It restores NeMo's own logging, which is
loud but says what went wrong.

## Burn the text into the picture

```bash
./examples/subtitles/burn-in.sh talk.mp4 talk.srt
```

Writes `talk-subtitled.mp4`. Use it for social, where a sidecar subtitle file is
ignored or off by default. Keep the `.srt` for players that handle it, since
selectable text beats pixels.

Needs an ffmpeg built with libass. The plain Homebrew bottle is not, and it
reports the missing filter as a syntax error in the filter string. The script
checks first and names the real cause: `brew install ffmpeg-full`.

## What comes out

The clip above, as an `.srt`:

```
9
00:00:27,440 --> 00:00:31,028
skeppet. Allt går svindlande fort,
men ibland blir det stopp.
```

`sample.srt` in this directory is the real output for `repro/counting-sv.wav`,
which ships with the repo, so you can regenerate a result without supplying a
file of your own.

## How the cues are built

The model gives one timing per word. Subtitles need lines short enough to read,
on screen long enough to read, broken where the sentence breaks. `cues.py` does
that, and the limits follow broadcast convention:

| | |
|---|---|
| Line length | 42 characters, 2 lines maximum |
| Reading speed | 17 characters per second |
| Duration | 1.0 s minimum, 6.0 s maximum |
| Forced break | 0.7 s of silence |

Cues that are too brief to read borrow from the silence after them, never from
the next cue, and start times are never moved. A subtitle that appears before
the word is spoken reads as a mistake even when the text is right.

## Limits

- **Fast speech outruns the reading speed.** Cues are never condensed, so when
  someone talks faster than 17 characters per second the cue stays dense rather
  than losing words. On ten minutes of fast parliamentary debate, 34 of 148 cues
  exceed it. Broadcast subtitlers paraphrase to fix this. A transcript should
  not.
- **Long files are transcribed in one pass and held in memory.** Ten minutes of
  audio peaked at 8.5 GB of resident memory, and it scales with duration, so
  anything past roughly twenty minutes needs a machine to match. Cut the file
  first if you have a long one.
- Timings come from the model. Music and overlapping speech move them.
- No speaker labels. One speaker per cue is assumed.
- Swedish. The model is monolingual.

---

Pianissimo is made by [Klang](https://klang.ai/?utm_source=github&utm_medium=referral&utm_campaign=pianissimo-subtitles&utm_content=readme-subtitles). If you want your team's meetings transcribed
without running anything yourself, that is what Klang does.
