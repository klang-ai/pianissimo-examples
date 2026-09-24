#!/usr/bin/env python3
"""Two local Pianissimo apps on one server.

    .venv/bin/python examples/offline/server.py

Then open http://127.0.0.1:8765 and pick one:

  /podcast    Transcript of an episode, then a vertical clip of any sentence.
  /dictation  Swedish speech to text as you speak.

Inference runs on this machine. The model and this server bind to 127.0.0.1 and
read the weights from the local cache. Finding and downloading an episode needs
the network; transcribing, clipping and dictating do not. First run with
--online to download the weights.
"""

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--device", help="cuda, mps or cpu (default: the fastest available)")
ap.add_argument("--online", action="store_true",
                help="allow Hugging Face downloads, for the first run only")
ap.add_argument("--verbose", action="store_true")
args = ap.parse_args()

if args.online:
    os.environ["HF_HUB_OFFLINE"] = "0"

import numpy as np  # noqa: E402
from aiohttp import WSMsgType, web  # noqa: E402

import asr  # noqa: E402
import clip  # noqa: E402
import fetch  # noqa: E402

RATE = asr.RATE
# Pieces transcribed per step of a podcast job. Larger batches run faster in
# total; smaller ones let the page show progress. Eight pieces is four minutes
# of audio per step.
PODCAST_STEP = 8


# ---- podcast -----------------------------------------------------------------

def decode_to_wav(src, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1",
                    "-ar", str(RATE), "-c:a", "pcm_s16le", dest], check=True)


def podcast_job(app, path, emit, meta=None):
    """Runs in a worker thread. emit() sends one event to the page.

    The finished episode is kept in app["jobs"], with its audio and transcript,
    so that clips can be made from it afterwards without transcribing it again.
    """
    engine = app["engine"]
    t_start = time.monotonic()
    # The decoded audio stays next to the original, for clips later on.
    wav = os.path.join(os.path.dirname(path), "audio.wav")
    try:
        decode_to_wav(path, wav)
    except subprocess.CalledProcessError:
        emit({"type": "error", "message": "ffmpeg could not read that file."})
        return None
    audio = asr.load_wav(wav)
    seconds = len(audio) / RATE
    t_decoded = time.monotonic()
    job = {"id": os.path.basename(os.path.dirname(path)), "path": path, "wav": wav,
           "media": "/media/" + os.path.relpath(path, app["media"]), "seconds": seconds,
           "title": (meta or {}).get("title"), "show": (meta or {}).get("show"),
           "pieces": []}
    app["jobs"][job["id"]] = job
    emit({"type": "job", "id": job["id"], "media": job["media"]})
    emit({"type": "start", "audioSeconds": seconds,
          "decodeSeconds": t_decoded - t_start, "device": engine.device})

    pieces = engine.pieces(audio)
    texts = job["pieces"]
    for i in range(0, len(pieces), PODCAST_STEP):
        batch = pieces[i:i + PODCAST_STEP]
        out = engine.transcribe([clip for _, clip in batch], batch_size=PODCAST_STEP)
        for (start, _), text in zip(batch, out):
            texts.append((start, text))
            emit({"type": "piece", "start": start, "text": text})
        emit({"type": "progress", "done": min(i + PODCAST_STEP, len(pieces)),
              "total": len(pieces), "elapsed": time.monotonic() - t_decoded})
    t_end = time.monotonic()
    words = sum(len(t.split()) for _, t in texts)
    emit({"type": "done", "seconds": t_end - t_decoded, "words": words,
          "audioSeconds": seconds, "totalSeconds": t_end - t_start})
    return job


async def stream_events(request, job):
    """Run job(emit) in a worker thread and stream what it emits as NDJSON."""
    resp = web.StreamResponse(headers={"Content-Type": "application/x-ndjson",
                                       "Cache-Control": "no-store"})
    await resp.prepare(request)
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def emit(event):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def guarded():
        try:
            job(emit)
        except Exception as e:  # the page should hear about it, not a stack trace
            emit({"type": "error", "message": str(e) or type(e).__name__})

    task = loop.run_in_executor(None, guarded)
    task.add_done_callback(lambda _: loop.call_soon_threadsafe(queue.put_nowait, None))
    while (event := await queue.get()) is not None:
        await resp.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
    await task
    await resp.write_eof()
    return resp


async def podcast(request):
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file":
        return web.json_response({"error": "send the audio as a form field named file"},
                                 status=400)
    suffix = os.path.splitext(field.filename or "")[1] or ".audio"
    app = request.app
    # Kept until the server stops, like a downloaded episode.
    path = os.path.join(tempfile.mkdtemp(dir=app["media"]), "episode" + suffix)
    with open(path, "wb") as f:
        while chunk := await field.read_chunk(1 << 20):
            f.write(chunk)
    meta = {"title": os.path.splitext(field.filename or "Episode")[0]}
    return await stream_events(request, lambda emit: podcast_job(app, path, emit, meta))


async def resolve(request):
    """Whatever was pasted, as a list of episodes to choose from."""
    q = ((await request.json()).get("q") or "").strip()
    if not q:
        return web.json_response({"error": "Paste a link or type an episode name."}, status=400)
    try:
        items = await asyncio.get_running_loop().run_in_executor(None, fetch.resolve, q)
    except fetch.NotFound as e:
        return web.json_response({"error": str(e)}, status=404)
    except Exception as e:
        return web.json_response({"error": f"Could not read that: {e}"}, status=502)
    return web.json_response({"items": items})


async def podcast_url(request):
    """Download the chosen episode, then run the same job as a dropped file."""
    item = (await request.json()).get("item") or {}
    if not item.get("audio"):
        return web.json_response({"error": "no episode chosen"}, status=400)
    app = request.app

    def job(emit):
        # Kept until the server stops, so the page can play and seek the episode
        # from this machine after the Wi-Fi is off.
        folder = tempfile.mkdtemp(dir=app["media"])
        t0 = time.monotonic()
        last = [0.0]

        def progress(done, total):
            now = time.monotonic()
            if now - last[0] > 0.15:
                last[0] = now
                emit({"type": "download", "done": done, "total": total})

        path = fetch.download(item, folder, progress)
        emit({"type": "downloaded", "bytes": os.path.getsize(path),
              "seconds": time.monotonic() - t0,
              "media": "/media/" + os.path.relpath(path, app["media"])})
        podcast_job(app, path, emit, item)

    return await stream_events(request, job)


async def make_clip(request):
    """A vertical video of one quote from a finished episode."""
    body = await request.json()
    job = request.app["jobs"].get(body.get("job"))
    if not job:
        return web.json_response({"error": "That episode is no longer on the server."}, status=404)
    loop = asyncio.get_running_loop()
    try:
        out = await loop.run_in_executor(None, lambda: clip.make(
            request.app["engine"], job, text=body.get("text"), start=body.get("start"),
            out_dir=os.path.dirname(job["path"])))
    except LookupError as e:
        return web.json_response({"error": str(e)}, status=422)
    except subprocess.CalledProcessError as e:
        return web.json_response({"error": "ffmpeg failed: " + (e.stderr or "")[-300:]}, status=500)
    out["url"] = "/media/" + os.path.relpath(out.pop("file"), request.app["media"])
    return web.json_response(out)


# ---- dictation ---------------------------------------------------------------

# Re-transcribe the open segment each time this much new audio has arrived.
PARTIAL_EVERY = 0.4
# A segment closes after this much quiet, or when it reaches the maximum.
ENDPOINT_SILENCE = 0.6
MIN_SEGMENT = 0.8
MAX_SEGMENT = 12.0
FRAME = RATE // 10


class Dictation:
    """One microphone session: the open segment, its energy, and its text."""

    def __init__(self):
        self.audio = np.zeros(0, dtype=np.float32)
        self.frame_rms = []
        self.since_partial = 0
        self.segment = 0
        # Recent frame energies across segments, for the room's noise floor.
        self.recent = []

    def add(self, pcm16):
        samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        self.audio = np.concatenate([self.audio, samples])
        self.since_partial += len(samples)
        for i in range(0, len(samples) - FRAME + 1, FRAME):
            rms = float(np.sqrt(np.mean(samples[i:i + FRAME] ** 2)))
            self.frame_rms.append(rms)
            self.recent = (self.recent + [rms])[-100:]

    @property
    def seconds(self):
        return len(self.audio) / RATE

    def speech_threshold(self):
        # The quiet end of the last ten seconds is the room, not the speaker.
        noise = float(np.percentile(self.recent, 15)) if self.recent else 0.003
        return max(noise * 3.0, 0.008)

    def has_speech(self):
        thr = self.speech_threshold()
        return sum(r > thr for r in self.frame_rms) >= 3

    def ended(self):
        if self.seconds >= MAX_SEGMENT:
            return True
        if self.seconds < MIN_SEGMENT or not self.has_speech():
            return False
        tail = self.frame_rms[-int(ENDPOINT_SILENCE * 10):]
        return len(tail) >= int(ENDPOINT_SILENCE * 10) and max(tail) < self.speech_threshold()

    def reset(self):
        self.audio = np.zeros(0, dtype=np.float32)
        self.frame_rms = []
        self.since_partial = 0
        self.segment += 1


async def dictate(request):
    ws = web.WebSocketResponse(max_msg_size=1 << 22)
    await ws.prepare(request)
    engine = request.app["engine"]
    loop = asyncio.get_running_loop()
    session = Dictation()
    busy = False

    async def run(clip, final, segment):
        nonlocal busy
        busy = True
        t0 = time.monotonic()
        try:
            text = (await loop.run_in_executor(None, engine.transcribe, [clip], 1))[0]
        finally:
            busy = False
        if not ws.closed:
            # The page drops a partial whose segment has already been finalised.
            await ws.send_json({"type": "final" if final else "partial", "text": text,
                                "segment": segment,
                                "audioSeconds": len(clip) / RATE,
                                "ms": round((time.monotonic() - t0) * 1000)})

    async def close_segment():
        clip, speech, segment = session.audio.copy(), session.has_speech(), session.segment
        session.reset()
        if speech:
            await run(clip, True, segment)
        elif not ws.closed:
            await ws.send_json({"type": "final", "text": "", "segment": segment})

    async for msg in ws:
        if msg.type == WSMsgType.BINARY:
            session.add(msg.data)
            if session.ended():
                await close_segment()
            elif (not busy and session.has_speech()
                  and session.since_partial >= PARTIAL_EVERY * RATE):
                session.since_partial = 0
                loop.create_task(run(session.audio.copy(), False, session.segment))
            elif not session.has_speech() and session.seconds > 3:
                # Keep only the last second of silence so the buffer stays small.
                session.audio = session.audio[-RATE:]
                session.frame_rms = session.frame_rms[-10:]
        elif msg.type == WSMsgType.TEXT:
            if json.loads(msg.data).get("type") == "stop":
                await close_segment()
                # The page closes the socket on this, not on a timer, so the
                # last segment is never cut off by a slow or busy model.
                if not ws.closed:
                    await ws.send_json({"type": "stopped"})
    return ws


# ---- pages and status --------------------------------------------------------

def online():
    """True if this machine can reach the internet right now."""
    for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection(host, timeout=0.6):
                return True
        except OSError:
            continue
    return False


async def status(request):
    is_online = await asyncio.get_running_loop().run_in_executor(None, online)
    return web.json_response({
        "online": is_online,
        "device": request.app["engine"].device,
        "model": asr.MODEL,
    })


@web.middleware
async def same_origin(request, handler):
    """Refuse requests that a different web page sent.

    The server listens on 127.0.0.1, but any page open in the browser can still
    reach it: a form post or a text/plain fetch is sent without a CORS preflight,
    and a WebSocket is not covered by CORS at all. Without this, any site could
    make this machine download a URL of its choosing or open the microphone
    socket. Browsers always send Origin on those requests; curl and scripts on
    this machine send none and are let through.
    """
    origin = request.headers.get("Origin")
    if origin and origin not in request.app["origins"]:
        raise web.HTTPForbidden(text="cross-origin request refused")
    return await handler(request)


async def media(request):
    root = request.app["media"]
    path = os.path.realpath(os.path.join(root, request.match_info["path"]))
    if not path.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(path):
        raise web.HTTPNotFound()
    return web.FileResponse(path)


def page(name):
    async def handler(_):
        return web.FileResponse(os.path.join(HERE, "static", name))
    return handler


def main():
    print(f"loading {asr.MODEL} from the local cache", file=sys.stderr)
    try:
        engine = asr.Engine(device=args.device, verbose=args.verbose)
    except Exception as e:  # the most likely cause by far is a missing download
        sys.exit(f"could not load {asr.MODEL}: {e}\n"
                 "If this is the first run, start once with --online to download it.")
    asr.warm_up(engine)
    print(f"ready on {engine.device}, loaded in {engine.load_seconds:.1f} s", file=sys.stderr)

    app = web.Application(client_max_size=1 << 31, middlewares=[same_origin])
    app["origins"] = {f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"}
    app["engine"] = engine
    app["media"] = tempfile.mkdtemp(prefix="pianissimo-")
    app["jobs"] = {}
    app.router.add_get("/", page("index.html"))
    app.router.add_get("/podcast", page("podcast.html"))
    app.router.add_get("/dictation", page("dictation.html"))
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/podcast", podcast)
    app.router.add_post("/api/resolve", resolve)
    app.router.add_post("/api/podcast-url", podcast_url)
    app.router.add_post("/api/clip", make_clip)
    app.router.add_get("/ws/dictate", dictate)
    app.router.add_get("/media/{path:.+}", media)
    app.router.add_static("/static", os.path.join(HERE, "static"))
    async def clean_up(_):
        shutil.rmtree(app["media"], ignore_errors=True)
    app.on_shutdown.append(clean_up)

    print(f"open http://127.0.0.1:{args.port}", file=sys.stderr)
    web.run_app(app, host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
