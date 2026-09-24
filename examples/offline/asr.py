"""Pianissimo loaded once and shared by both apps.

The model is loaded from the local Hugging Face cache with HF_HUB_OFFLINE set,
so once the weights are on disk nothing here touches the network. On a Mac
with Apple silicon it runs on the GPU through Metal (mps); elsewhere it uses
CUDA when there is one and the CPU when there is not.
"""

import os
import sys
import threading
import time
import warnings

import numpy as np

# Set before huggingface_hub is imported anywhere, or it is read too late.
# server.py clears it with --online for the one run that downloads weights.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

MODEL = "KlangAI/pianissimo-sv"
RATE = 16000

# Long audio is cut into pieces this long and transcribed as a batch. A batch
# of short pieces keeps the GPU busy; one hour-long tensor does not, and it
# needs far more memory. Thirty seconds is short enough to batch well and long
# enough that a cut rarely lands mid-sentence in a way the model cares about.
PIECE_SECONDS = 30


class _QuietStream:
    """Drops NeMo's startup chatter and keeps everything else."""

    NOISE = ("[NeMo W", "[NeMo I", "OneLogger:", "No exporters were provided")

    def __init__(self, stream):
        self._stream = stream
        self._muting = False

    def write(self, text):
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            if stripped.startswith(self.NOISE):
                self._muting = True
                continue
            if self._muting and (line.startswith((" ", "\t")) or not stripped):
                continue
            self._muting = False
            self._stream.write(line)

    def flush(self):
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _text(hypothesis):
    return (getattr(hypothesis, "text", hypothesis) or "").strip()


class Engine:
    def __init__(self, device=None, verbose=False):
        if not verbose:
            warnings.filterwarnings("ignore")
            # NeMo's loggers bind to sys.stdout and sys.stderr at import time.
            sys.stderr = _QuietStream(sys.stderr)
            sys.stdout = _QuietStream(sys.stdout)
        import torch
        from nemo.collections.asr.models import ASRModel
        from nemo.utils import logging as nemo_logging
        if not verbose:
            nemo_logging.set_verbosity(nemo_logging.ERROR)

        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.device = device
        self._torch = torch
        # One inference at a time. The dictation loop and a podcast job share
        # one model, and interleaving them on one GPU only makes both slower.
        self.lock = threading.Lock()

        t0 = time.monotonic()
        self.model = ASRModel.from_pretrained(
            model_name=MODEL, map_location=torch.device(device)).eval()
        self.load_seconds = time.monotonic() - t0

    def transcribe(self, clips, batch_size=16):
        """Transcribe a list of float32 mono 16 kHz arrays, in order."""
        if not clips:
            return []
        with self.lock, self._torch.inference_mode():
            result = self.model.transcribe(audio=clips, batch_size=batch_size,
                                           verbose=False)
        if isinstance(result, tuple):
            result = result[0]
        return [_text(h) for h in result]

    def words(self, clip, offset=0.0):
        """Word level timings for one clip, in seconds from offset."""
        with self.lock, self._torch.inference_mode():
            result = self.model.transcribe(audio=[clip], batch_size=1, return_hypotheses=True,
                                           timestamps=True, verbose=False)
        if isinstance(result, tuple):
            result = result[0]
        stamps = getattr(result[0], "timestamp", None) or {}
        out = []
        for w in stamps.get("word", []):
            text = (w.get("word") or w.get("char") or "").strip()
            if text:
                out.append({"word": text, "start": float(w["start"]) + offset,
                            "end": float(w["end"]) + offset})
        return out

    def pieces(self, audio):
        """Cut long audio into pieces, each with its start time in seconds."""
        step = PIECE_SECONDS * RATE
        return [(i / RATE, audio[i:i + step]) for i in range(0, len(audio), step)]


def load_wav(path):
    import soundfile as sf
    audio, rate = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != RATE:
        raise ValueError(f"expected {RATE} Hz, got {rate}")
    return np.ascontiguousarray(audio)


def warm_up(engine):
    """The first call on a fresh model is several times slower than the rest.

    Paying for it at startup keeps it out of the first thing anyone times.
    """
    engine.transcribe([np.zeros(RATE * 2, dtype=np.float32)])

