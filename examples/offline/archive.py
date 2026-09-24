"""A whole show, transcribed in the background and searchable on this machine.

Episodes are queued, then downloaded and transcribed one at a time by a worker
thread. Each finished episode is written to disk as JSON next to its audio, so
the archive survives a restart and can be left running overnight. Search runs
over every thirty second piece of every episode, with the same stems as the
question box, and a hit plays from its own second.

Nothing here needs the summary model. Transcription alone is the fast part.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time

import ask
import asr
import fetch

ROOT = os.environ.get("PIANISSIMO_ARCHIVE") or os.path.expanduser("~/.cache/pianissimo/archive")
BATCH = 16


def _id(item):
    return hashlib.sha1((item.get("audio") or "").encode()).hexdigest()[:12]


class Archive:
    def __init__(self, engine):
        self.engine = engine
        self.episodes = {}
        self.lock = threading.Lock()
        self.worker = None
        os.makedirs(ROOT, exist_ok=True)
        for name in os.listdir(ROOT):
            if name.endswith(".json"):
                with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                    ep = json.load(f)
                # Anything cut short by a restart goes back in the queue.
                if ep["status"] in ("downloading", "transcribing"):
                    ep["status"] = "queued"
                self.episodes[ep["id"]] = ep
        self._kick()

    def _save(self, ep):
        path = os.path.join(ROOT, ep["id"] + ".json")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(ep, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)

    def add(self, items):
        added = 0
        with self.lock:
            for item in items:
                if not item.get("audio"):
                    continue
                eid = _id(item)
                if eid in self.episodes and self.episodes[eid]["status"] != "error":
                    continue
                ep = {"id": eid, "title": item.get("title"), "show": item.get("show"),
                      "duration": item.get("duration"), "image": item.get("image"),
                      "page": item.get("page"), "source": item, "status": "queued",
                      "added": time.time(), "pieces": [], "audio": None}
                self.episodes[eid] = ep
                self._save(ep)
                added += 1
        self._kick()
        return added

    def _kick(self):
        if self.worker and self.worker.is_alive():
            return
        if not any(e["status"] == "queued" for e in self.episodes.values()):
            return
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _next(self):
        with self.lock:
            queued = [e for e in self.episodes.values() if e["status"] == "queued"]
            return min(queued, key=lambda e: e["added"]) if queued else None

    def _run(self):
        while ep := self._next():
            try:
                self._process(ep)
            except Exception as e:  # one bad episode must not stop the night's work
                ep["status"], ep["error"] = "error", str(e) or type(e).__name__
                self._save(ep)

    def _process(self, ep):
        folder = os.path.join(ROOT, "media", ep["id"])
        os.makedirs(folder, exist_ok=True)
        ep["status"], ep["progress"] = "downloading", 0.0
        t0 = time.monotonic()

        def progress(done, total):
            ep["progress"] = done / total if total else 0.0

        path = fetch.download(ep["source"], folder, progress)
        ep["audio"] = os.path.relpath(path, os.path.join(ROOT, "media"))
        ep["status"], ep["progress"] = "transcribing", 0.0
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, "audio.wav")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vn", "-ac", "1",
                            "-ar", str(asr.RATE), "-c:a", "pcm_s16le", wav], check=True)
            audio = asr.load_wav(wav)
        pieces = self.engine.pieces(audio)
        out = []
        t1 = time.monotonic()
        for i in range(0, len(pieces), BATCH):
            batch = pieces[i:i + BATCH]
            texts = self.engine.transcribe([c for _, c in batch], batch_size=BATCH)
            out += [[s, t] for (s, _), t in zip(batch, texts)]
            ep["progress"] = len(out) / len(pieces)
        ep.update(pieces=out, status="done", seconds=len(audio) / asr.RATE,
                  transcribeSeconds=time.monotonic() - t1, totalSeconds=time.monotonic() - t0,
                  words=sum(len(t.split()) for _, t in out), doneAt=time.time(), progress=1.0)
        self._save(ep)

    def status(self):
        eps = sorted(self.episodes.values(), key=lambda e: e["added"])
        keep = ("id", "title", "show", "duration", "image", "status", "progress", "error",
                "seconds", "transcribeSeconds", "words", "audio")
        return [{k: e.get(k) for k in keep} for e in eps]

    def search(self, question, top=30):
        """Best pieces across every finished episode, best first."""
        docs, refs = [], []
        for e in self.episodes.values():
            if e["status"] != "done":
                continue
            for start, text in e["pieces"]:
                docs.append((start, text))
                refs.append(e)
        hits = ask.search(docs, question, top=top, ordered=False)
        return [{"id": refs[i]["id"], "show": refs[i]["show"], "title": refs[i]["title"],
                 "audio": refs[i]["audio"], "start": docs[i][0], "text": docs[i][1]}
                for i in hits]
