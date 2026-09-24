"""Turn whatever someone pastes into an episode's audio.

A link to Spotify, Apple Podcasts, YouTube, Acast, Sveriges Radio, SoundCloud,
an RSS feed, a plain web page with a player on it, or just the name of an
episode. This is the only part of the app that uses the network, and only to
fetch the audio. Once it is on disk, the Wi-Fi can go off.

Spotify does not hand out episode audio, and we do not try to get around that.
Almost every podcast on Spotify also publishes the same episode in its public
RSS feed, so a Spotify link is resolved to the show's name and the episode's
title, the feed is found in Apple's public podcast directory, and the matching
episode is taken from there. Shows that are exclusive to Spotify have no feed
and cannot be fetched.
"""

import html
import json
import os
import re
import shutil
import subprocess
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".mp4", ".webm")
MAX_LIST = 8
# Spotify's page and yt-dlp (YouTube and others) are read only when the server
# runs with --any-link. Both are fine for trying things on your own machine and
# wrong for a hosted service: Spotify's page is scraped, and downloading from
# YouTube is against its terms. Apple's directory, RSS, Sveriges Radio's API
# and plain pages with a player are always on.
ANY_LINK = False
# How many episodes a show or search returns. The podcast page wants a short
# list to pick from; the archive wants the whole back catalogue. Per thread,
# because each request is resolved on its own worker thread.
_limit = threading.local()


def _max():
    return getattr(_limit, "n", MAX_LIST)


class NotFound(Exception):
    pass


# ---- helpers -----------------------------------------------------------------

def get(url, timeout=20, limit=None, ua=UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Language": "sv,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit) if limit else r.read(), r.headers.get("Content-Type", ""), r.geturl()


def get_json(url):
    return json.loads(get(url)[0])


def normal(s):
    # NFKC, not NFKD: decomposed, "ö" becomes "o" plus a combining mark, the mark
    # is not \w, and every Swedish word with åäö splits in two.
    s = unicodedata.normalize("NFKC", html.unescape(s or "")).lower()
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


def similarity(a, b):
    """Word overlap between two titles, 0 to 1."""
    a, b = set(normal(a).split()), set(normal(b).split())
    return len(a & b) / max(1, min(len(a), len(b)))


def seconds(value):
    """itunes:duration is either seconds or h:mm:ss."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    parts = [int(p) for p in value.split(":") if p.isdigit()]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total or None


def meta(page, prop):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) +
                  r'["\'][^>]*content=["\']([^"\']*)["\']', page)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' +
                      re.escape(prop) + r'["\']', page)
    return html.unescape(m.group(1)) if m else None


def episode(title, audio, show=None, duration=None, image=None, via="", page=None, kind="direct"):
    return {"title": title, "show": show, "duration": duration, "image": image,
            "audio": audio, "via": via, "page": page, "kind": kind}


# ---- RSS ---------------------------------------------------------------------

def read_feed(url):
    body, _, _ = get(url, timeout=30)
    root = ET.fromstring(body)
    channel = root.find("channel")
    show = channel.findtext("title") if channel is not None else None
    image = None
    if channel is not None:
        img = channel.find(ITUNES + "image")
        image = img.get("href") if img is not None else channel.findtext("image/url")
    items = []
    for it in root.iter("item"):
        enc = it.find("enclosure")
        if enc is None or not enc.get("url"):
            continue
        img = it.find(ITUNES + "image")
        items.append(episode(
            it.findtext("title"), enc.get("url"), show=show,
            duration=seconds(it.findtext(ITUNES + "duration")),
            image=img.get("href") if img is not None else image,
            via="RSS feed", page=it.findtext("link")))
    return show, items


def match_in_feed(feed, title, duration=None):
    """The feed item that is this episode: title first, length as a tiebreak."""
    _, items = read_feed(feed)
    best, score = None, 0.0
    for item in items:
        s = similarity(title, item["title"])
        if duration and item["duration"] and abs(duration - item["duration"]) <= 5:
            s += 0.3
        if s > score:
            best, score = item, s
    return best if score >= 0.6 else None


def itunes_feeds(show):
    """Feeds for a show name. Swedish storefront first, then the default one."""
    q = urllib.parse.quote(show)
    seen, out = set(), []
    for country in ("&country=se", ""):
        found = get_json(f"https://itunes.apple.com/search?media=podcast&limit=5&term={q}{country}")
        for r in found.get("results", []):
            feed = r.get("feedUrl")
            if feed and feed not in seen and similarity(show, r.get("collectionName", "")) >= 0.6:
                seen.add(feed)
                out.append(r)
    return out


# ---- sources -----------------------------------------------------------------

def from_spotify(url):
    # With a full browser user agent Spotify serves its app shell, which has no
    # episode metadata in it. A plain one gets the page link previews are made from.
    page = get(url, ua="Mozilla/5.0 (Macintosh)")[0].decode("utf-8", "replace")
    title = meta(page, "og:title")
    desc = meta(page, "og:description") or ""
    duration = meta(page, "music:duration")
    duration = int(duration) if duration and duration.isdigit() else None
    if "/show/" in url:
        show = title
        feeds = itunes_feeds(show) if show else []
        if not feeds:
            raise NotFound(f"{show or 'This show'} has no public feed. It may be a Spotify exclusive.")
        _, items = read_feed(feeds[0]["feedUrl"])
        return [dict(i, via="Spotify, then the show's public RSS feed") for i in items[:_max()]]
    # og:description reads "Show name · Episode".
    show = desc.split(" · ")[0].strip() if " · " in desc else None
    if not (title and show):
        raise NotFound("Spotify did not say which show this episode belongs to.")
    for feed in itunes_feeds(show):
        hit = match_in_feed(feed["feedUrl"], title, duration)
        if hit:
            return [dict(hit, via="Spotify, then the show's public RSS feed")]
    raise NotFound(f"Found {show} on Spotify but not in a public feed. "
                   "It may be a Spotify exclusive.")


def from_apple(url):
    ep = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("i", [None])[0]
    show_id = re.search(r"/id(\d+)", url)
    # The storefront is in the path, /se/podcast/..., and a lookup outside it
    # returns nothing at all for shows that are only listed there.
    country = re.match(r"/([a-z]{2})/", urllib.parse.urlparse(url).path)
    country = "&country=" + country.group(1) if country else ""
    if ep and show_id:
        # Looking up an episode id directly returns nothing; the show's recent
        # episodes do include it.
        found = get_json(f"https://itunes.apple.com/lookup?id={show_id.group(1)}"
                         f"&entity=podcastEpisode&limit=200{country}")
        for r in found.get("results", []):
            if str(r.get("trackId")) == ep and r.get("episodeUrl"):
                return [episode(r.get("trackName"), r["episodeUrl"], show=r.get("collectionName"),
                                duration=(r.get("trackTimeMillis") or 0) // 1000 or None,
                                image=r.get("artworkUrl600"), via="Apple Podcasts",
                                page=r.get("trackViewUrl"))]
    if show_id:
        found = get_json(f"https://itunes.apple.com/lookup?id={show_id.group(1)}{country}")
        for r in found.get("results", []):
            if r.get("feedUrl"):
                _, items = read_feed(r["feedUrl"])
                return [dict(i, via="Apple Podcasts, then the RSS feed") for i in items[:_max()]]
    raise NotFound("Apple Podcasts did not return an episode for that link.")


def from_sr(url):
    """Sveriges Radio refuses plain requests to its pages, but its open API answers."""
    ep = re.search(r"/avsnitt/(\d+)", url) or re.search(r"[?&]artikel=(\d+)", url)
    if not ep:
        return None
    e = get_json(f"https://api.sr.se/api/v2/episodes/get?id={ep.group(1)}&format=json")["episode"]
    pod = e.get("downloadpodfile") or e.get("listenpodfile") or {}
    if not pod.get("url"):
        raise NotFound("Sveriges Radio has no downloadable file for this episode.")
    return [episode(e.get("title"), pod["url"], show=(e.get("program") or {}).get("name"),
                    duration=pod.get("duration"), image=e.get("imageurl"),
                    via="Sveriges Radio's open API", page=e.get("url"))]


def from_ytdlp(url):
    if not ANY_LINK or not shutil.which("yt-dlp"):
        return None
    run = subprocess.run(["yt-dlp", "-J", "--flat-playlist", "--no-warnings", url],
                         capture_output=True, text=True, timeout=60)
    if run.returncode != 0:
        return None
    info = json.loads(run.stdout)
    site = urllib.parse.urlparse(url).netloc.removeprefix("www.")
    if (info.get("extractor_key") or "").lower() == "generic":
        return None  # the HTML scan below does this better for podcast pages
    if info.get("entries"):
        return [episode(e.get("title"), e.get("url") or e.get("webpage_url"),
                        show=info.get("title"), duration=e.get("duration"),
                        via=f"{site}, through yt-dlp", page=e.get("url"), kind="ytdlp")
                for e in info["entries"][:_max()] if e.get("url") or e.get("webpage_url")]
    return [episode(info.get("title"), info.get("webpage_url") or url,
                    show=info.get("uploader") or info.get("channel") or info.get("series"),
                    duration=info.get("duration"), image=info.get("thumbnail"),
                    via=f"{site}, through yt-dlp", page=info.get("webpage_url"), kind="ytdlp")]


def from_page(url, page):
    """Any web page: an audio tag, og:audio, a link to a file, or a feed to look in."""
    title = meta(page, "og:title") or (re.search(r"<title>([^<]+)", page) or [None, None])[1]
    image = meta(page, "og:image")
    candidates = [meta(page, "og:audio"), meta(page, "og:audio:url"), meta(page, "twitter:player:stream")]
    candidates += re.findall(r'<(?:audio|source)[^>]+src=["\']([^"\']+)["\']', page)
    candidates += re.findall(r'["\'](https?://[^"\']+?\.(?:mp3|m4a|aac|ogg|opus)(?:\?[^"\']*)?)["\']', page)
    for c in candidates:
        if c and "spotifycdn.com/audio/clips" not in c:  # a 60 second preview, not the episode
            return [episode(html.unescape(title or "Episode").strip(), urllib.parse.urljoin(url, c),
                            image=image, via="the audio on the page", page=url)]
    feed = re.search(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)', page)
    if feed:
        feed_url = urllib.parse.urljoin(url, feed.group(1))
        hit = title and match_in_feed(feed_url, title)
        if hit:
            return [dict(hit, via="the page's RSS feed")]
        _, items = read_feed(feed_url)
        return [dict(i, via="the page's RSS feed") for i in items[:_max()]]
    return None


def search(text):
    q = urllib.parse.quote(text)
    found = get_json(f"https://itunes.apple.com/search?media=podcast&entity=podcastEpisode"
                     f"&country=se&limit={min(_max(), 200)}&term={q}")
    items = [episode(r.get("trackName"), r["episodeUrl"], show=r.get("collectionName"),
                     duration=(r.get("trackTimeMillis") or 0) // 1000 or None,
                     image=r.get("artworkUrl160"), via="search in Apple Podcasts",
                     page=r.get("trackViewUrl"))
             for r in found.get("results", []) if r.get("episodeUrl")]
    if not items:
        raise NotFound(f"No podcast episode matched “{text}”.")
    return items


def resolve(text, limit=MAX_LIST):
    """A list of episodes for whatever was pasted. Raises NotFound with a reason."""
    _limit.n = limit
    text = text.strip()
    if not re.match(r"https?://", text):
        if re.match(r"[\w-]+(\.[\w-]+)+/", text):
            text = "https://" + text
        else:
            return search(text)
    host = urllib.parse.urlparse(text).netloc.lower()
    if "spotify.com" in host:
        if not ANY_LINK:
            raise NotFound("Spotify links are off unless the server runs with --any-link. "
                           "Paste the show's Apple Podcasts link or RSS feed instead.")
        return from_spotify(text)
    if "podcasts.apple.com" in host:
        return from_apple(text)
    if "sverigesradio.se" in host:
        hit = from_sr(text)
        if hit:
            return hit
    if urllib.parse.urlparse(text).path.lower().endswith(AUDIO_EXT):
        return [episode(os.path.basename(urllib.parse.urlparse(text).path), text, via="a direct link")]

    try:
        body, ctype, final = get(text, limit=4 << 20)
    except urllib.error.HTTPError as e:
        # Some sites refuse plain requests but yt-dlp knows how to ask them.
        hit = from_ytdlp(text)
        if hit:
            return hit
        raise NotFound(f"The page answered {e.code}." + (
            "" if ANY_LINK else " Some sites open only through yt-dlp: start with --any-link."))
    if ctype.startswith(("audio/", "video/")):
        return [episode(os.path.basename(urllib.parse.urlparse(final).path), final, via="a direct link")]
    head = body[:400].decode("utf-8", "replace").lstrip()
    if "xml" in ctype or head.startswith("<?xml") or "<rss" in head:
        _, items = read_feed(final)
        return [dict(i, via="RSS feed") for i in items[:_max()]]

    hit = from_ytdlp(text)
    if hit:
        return hit
    hit = from_page(final, body.decode("utf-8", "replace"))
    if hit:
        return hit
    raise NotFound("Could not find any audio on that page.")


# ---- download ----------------------------------------------------------------

def download(item, dest_dir, progress):
    """Fetch the audio to dest_dir and return the path. progress(done, total) as it goes."""
    if item.get("kind") == "ytdlp":
        out = os.path.join(dest_dir, "episode.%(ext)s")
        proc = subprocess.Popen(
            ["yt-dlp", "-f", "bestaudio/best", "--no-playlist", "--newline", "--no-warnings",
             "--socket-timeout", "30",
             "--progress-template", "download:%(progress.downloaded_bytes)s %(progress.total_bytes_estimate)s",
             "-o", out, item["audio"]],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            parts = line.split()
            if len(parts) == 2 and parts[0].isdigit():
                total = float(parts[1]) if parts[1] not in ("NA", "None") else 0
                progress(int(parts[0]), int(total))
        # stdout is closed by now, so this only guards against a process that
        # stays up after its last line and would otherwise hold the archive
        # worker forever.
        if proc.wait(timeout=120) != 0:
            raise NotFound("yt-dlp could not download the audio.")
        files = [f for f in os.listdir(dest_dir) if f.startswith("episode.")]
        if not files:
            raise NotFound("yt-dlp finished without writing a file.")
        return os.path.join(dest_dir, files[0])

    req = urllib.request.Request(item["audio"], headers={"User-Agent": UA})
    path = os.path.join(dest_dir, "episode" + (os.path.splitext(urllib.parse.urlparse(item["audio"]).path)[1] or ".mp3"))
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 18):
            f.write(chunk)
            done += len(chunk)
            progress(done, total)
    return path
