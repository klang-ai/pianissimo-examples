"""A local language model that writes the podcast summary.

Pianissimo turns speech into text and stops there. The summary comes from a
small instruction model run by llama.cpp's llama-server on this machine, on
the GPU through Metal. The server is started on demand and bound to
127.0.0.1, so like the rest of the app it works with the network off.
"""

import glob
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request

SUMMARY_REPO = "unsloth/Qwen3-4B-Instruct-2507-GGUF"
SUMMARY_FILE = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
PORT = 8099
# Each chapter is a few minutes of talk, so a short context is enough, and a
# short context is what keeps a small model fast: reading 16,000 tokens at once
# runs at well under half the speed of reading 4,000. Two slots let one
# chapter be summarised while the next is still being transcribed.
CONTEXT = 8192
SLOTS = 2
CHAPTER_PROMPT = """Här är några minuter ur ett automatiskt transkript av ett svenskt poddavsnitt.
Svara med exakt tre rader och inget annat:

Rubrik: <kapitelrubrik, högst åtta ord>
Innehåll: <en mening om vad som sägs>
Citat: <en kort mening kopierad ordagrant ur texten>

Skriv bara det som faktiskt sägs. Nämn en person vid namn bara om namnet står i texten."""

SUMMARY_PROMPT = """Här är kapitlen ur ett svenskt poddavsnitt, i ordning, med tidsstämpel, rubrik och innehåll.
Svara exakt i det här formatet och inget annat:

# <rubrik för hela avsnittet, högst tio ord>

<två meningar om vad avsnittet handlar om>

## Det viktigaste
- <punkt>
- <punkt>
- <punkt>
- <punkt>
- <punkt>

Punkterna ska vara slutsatser om hela avsnittet med egna ord, inte kapitlen upprepade.
Skriv bara det som står i kapitlen. Hitta inte på namn eller siffror."""

def find_model():
    """The GGUF in the Hugging Face cache, or None if it was never downloaded."""
    cache = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    folder = "models--" + SUMMARY_REPO.replace("/", "--")
    hits = glob.glob(os.path.join(cache, folder, "snapshots", "*", SUMMARY_FILE))
    return hits[0] if hits else None


def _up():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


class Summarizer:
    def __init__(self):
        self.proc = None
        self.model_path = find_model()
        self.binary = shutil.which("llama-server")

    @property
    def problem(self):
        if not self.binary:
            return "llama-server not found. Install llama.cpp: brew install llama.cpp"
        if not self.model_path:
            return (f"Summary model not downloaded. Run once with the network on: "
                    f"hf download {SUMMARY_REPO} {SUMMARY_FILE}")
        return None

    def start(self):
        if self.problem or _up():
            return
        self.proc = subprocess.Popen(
            [self.binary, "-m", self.model_path, "-c", str(CONTEXT * SLOTS), "-np", str(SLOTS),
             "-ngl", "99",
             "-fa", "on", "--host", "127.0.0.1", "--port", str(PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def wait(self, timeout=90):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if _up():
                return True
            if self.proc and self.proc.poll() is not None:
                return False
            time.sleep(0.3)
        return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def _request(self, system, user, max_tokens, stream):
        body = {"messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.2, "max_tokens": max_tokens, "stream": stream}
        return urllib.request.Request(
            f"http://127.0.0.1:{PORT}/v1/chat/completions",
            json.dumps(body).encode(), {"Content-Type": "application/json"})

    def chapter(self, text):
        """Title, one line of content and a verbatim quote for a few minutes of talk."""
        with urllib.request.urlopen(self._request(CHAPTER_PROMPT, text, 160, False),
                                    timeout=300) as r:
            answer = json.load(r)["choices"][0]["message"]["content"]
        fields = {}
        for line in answer.splitlines():
            key, _, value = line.partition(":")
            if value.strip():
                fields[key.strip().lower()] = value.strip().strip('"”“')
        quote = fields.get("citat", "")
        return {
            "title": fields.get("rubrik", "").rstrip("."),
            "gist": fields.get("innehåll", ""),
            # A small model will sometimes paraphrase and call it a quote. Keep
            # it only if it really is in the transcript.
            "quote": quote if quote and _normal(quote) in _normal(text) else "",
        }

    def stream(self, chapters):
        """Yield the episode summary a few characters at a time."""
        outline = "\n".join(f"[{stamp(c['start'])}] {c['title']}: {c['gist']}" for c in chapters)
        yield from self.stream_text(SUMMARY_PROMPT, outline, 450)

    def stream_text(self, system, user, max_tokens):
        """Yield any answer from the local model as it is written."""
        with urllib.request.urlopen(self._request(system, user, max_tokens, True),
                                    timeout=300) as r:
            for raw in r:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield delta


def _normal(s):
    return " ".join("".join(c for c in s.lower() if c.isalnum() or c.isspace()).split())


def stamp(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def online():
    """True if this machine can reach the internet right now."""
    for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection(host, timeout=0.6):
                return True
        except OSError:
            continue
    return False
