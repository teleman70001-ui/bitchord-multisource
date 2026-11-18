#!/usr/bin/env python3
"""BitChord multisource addon: Internet Archive + optional Tidal (hifi-api).

Addon protocol (https://bitchord.kushagrasingh.in/docs):
GET /manifest.json | /search?q=&quality= | /stream/{id}?quality=  (+ /health)
Python 3.9+, stdlib only.
ponytail: single file; split providers into modules when a third source lands.
"""
import base64
import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
TIDAL_API_URL = os.environ.get("TIDAL_API_URL", "").rstrip("/")
TIMEOUT = float(os.environ.get("PROVIDER_TIMEOUT", "8"))
UA = {"User-Agent": "bitchord-multisource/0.1"}

MANIFEST = {
    "id": "teleman70001.multisource",
    "name": "Multisource (Internet Archive + Tidal)",
    "version": "0.1.0",
    "resources": ["search", "stream"],
    "settings": [
        {
            "key": "quality",
            "type": "select",
            "default": "lossless",
            "options": [
                {"label": "Lossless", "value": "lossless"},
                {"label": "High", "value": "high"},
                {"label": "Low", "value": "low"},
            ],
        }
    ],
}


def fetch_json(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def duration_to_seconds(value):
    """IA/Tidal lengths arrive as '215.37', '3:35' or '1:02:03'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if ":" in s:
        try:
            total = 0.0
            for part in s.split(":"):
                total = total * 60 + float(part)
            return int(total)
        except ValueError:
            return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _clean_query(q):
    return re.sub(r"\s+", " ", re.sub(r'[":()\[\]]', " ", q)).strip()


# ── Provider: Internet Archive ────────────────────────────────────────────
LOSSLESS_FMT = ("Flac",)
LOSSY_FMT = {
    "high": ("320Kbps MP3", "VBR MP3"),
    "low": ("128Kbps MP3", "64Kbps MP3"),
}
_META_CACHE = {}


def _audio_files(files, quality):
    if quality == "lossless":
        want_fmt, want_ext = LOSSLESS_FMT, ".flac"
    else:
        want_fmt, want_ext = LOSSY_FMT.get(quality, ()), ".mp3"
    names_exact = {f.get("name") for f in files if f.get("format") in want_fmt}
    picked = [f for f in files if f.get("name") in names_exact]
    if want_ext:
        picked += [
            f for f in files
            if f.get("name", "").lower().endswith(want_ext) and f.get("name") not in names_exact
        ]
    return picked


def _file_title(name, files_by_name):
    meta = files_by_name.get(name, {})
    if meta.get("title"):
        return str(meta["title"]).strip()
    base = re.sub(r"\.\w+$", "", name).replace("_", " ")
    base = re.sub(r"^\s*\d{1,3}[\s.\-]+", "", base).strip()
    return base or name


def _cached_meta(ident):
    now = time.time()
    hit = _META_CACHE.get(ident)
    if hit and now - hit[0] < 300:
        return hit[1]
    meta = fetch_json(f"https://archive.org/metadata/{ident}")
    _META_CACHE[ident] = (now, meta)
    if len(_META_CACHE) > 256:
        for k in list(_META_CACHE)[:-128]:
            _META_CACHE.pop(k, None)
    return meta


def _item_rows(doc, tokens, quality):
    ident = doc.get("identifier")
    if not ident:
        return []
    try:
        meta = _cached_meta(ident)
    except Exception:
        return []
    files_by_name = {f.get("name"): f for f in meta.get("files", []) if f.get("name")}
    files = _audio_files(list(files_by_name.values()), quality)

    def score(f):
        base = re.sub(r"\.\w+$", "", f.get("name", "")).lower().replace("_", " ").replace("-", " ")
        return len(tokens & set(base.split()))

    files.sort(key=score, reverse=True)
    creator = doc.get("creator") or meta.get("metadata", {}).get("creator") or ""
    if isinstance(creator, list):
        creator = ", ".join(str(c) for c in creator)
    if isinstance(creator, dict):
        creator = creator.get("name", "")
    item_title = doc.get("title") or meta.get("metadata", {}).get("title") or ident
    if isinstance(item_title, list):
        item_title = ", ".join(str(t) for t in item_title)
    fmt, tier = ("flac", "LOSSLESS") if quality == "lossless" else ("mp3", quality.upper())
    rows = []
    for f in files[:2]:
        name = f["name"]
        rows.append({
            "id": f"archive:{ident}:{name}",
            "title": _file_title(name, files_by_name),
            "artist": str(creator).strip(),
            "album": str(item_title).strip(),
            "duration": duration_to_seconds(f.get("length")),
            "artworkURL": f"https://archive.org/services/img/{ident}",
            "format": fmt,
            "audioQuality": tier,
        })
    return rows


def archive_search(q, quality):
    terms = _clean_query(q)
    if not terms:
        return []
    rows_cap = int(os.environ.get("ARCHIVE_ROWS", "10"))
    query = f"title:({terms}) AND mediatype:audio"
    url = (
        "https://archive.org/advancedsearch.php?q=" + urllib.parse.quote(query)
        + "&fl%5B%5D=identifier&fl%5B%5D=title&fl%5B%5D=creator"
        + f"&rows={rows_cap}&page=1&output=json"
    )
    docs = fetch_json(url).get("response", {}).get("docs", [])
    tokens = set(terms.lower().split())
    with ThreadPoolExecutor(max_workers=6) as pool:
        batches = list(pool.map(lambda doc: _item_rows(doc, tokens, quality), docs))
    return [row for batch in batches for row in batch]


def archive_stream(tid, quality):
    try:
        _, ident, name = tid.split(":", 2)
    except ValueError:
        return None
    try:
        meta = _cached_meta(ident)
    except Exception:
        return None
    files = meta.get("files", [])
    pinned = next((f for f in files if f.get("name") == name), None)
    if not pinned:
        return None
    stem = re.sub(r"\.\w+$", "", name).lower()
    alt = next(
        (f for f in _audio_files(files, quality)
         if re.sub(r"\.\w+$", "", f.get("name", "")).lower() == stem),
        None,
    )
    pick = alt or pinned
    ext = pick["name"].rsplit(".", 1)[-1].lower()
    codec = "flac" if ext == "flac" else "mp3"
    return {
        "url": f"https://archive.org/download/{ident}/{urllib.parse.quote(pick['name'])}",
        "format": codec,
        "codec": codec,
        "container": codec,
        "manifest": "none",
        "encrypted": False,
    }


# ── Provider: Tidal via self-hosted hifi-api (binimum/hifi-api) ──────────
TIDAL_QUALITY = {"lossless": "LOSSLESS", "high": "HIGH", "low": "LOW"}
TIDAL_FORMAT = {"LOSSLESS": ("flac", "LOSSLESS"), "HIGH": ("aac", "HIGH"), "LOW": ("mp3", "LOW")}


def tidal_search(q, quality):
    if not TIDAL_API_URL:
        return []
    tier = TIDAL_QUALITY.get(quality, "LOSSLESS")
    fmt, label = TIDAL_FORMAT[tier]
    data = fetch_json(f"{TIDAL_API_URL}/search/?query={urllib.parse.quote(q)}&limit=20")
    out = []
    for t in data.get("tracks", []):
        artist = (t.get("artist") or {}).get("name", "")
        album = t.get("album") or {}
        cover = album.get("cover") or album.get("coverArtUuid")
        art = (
            "https://resources.tidal.com/images/"
            + str(cover).replace("-", "/")
            + "/640x640.jpg"
        ) if cover else None
        out.append({
            "id": f"tidal:{t.get('id')}",
            "title": t.get("title", ""),
            "artist": artist,
            "album": album.get("title", ""),
            "duration": duration_to_seconds(t.get("duration")),
            "artworkURL": art,
            "format": fmt,
            "audioQuality": label,
        })
    return out


def tidal_stream(tid, quality):
    if not TIDAL_API_URL:
        return None
    tier = TIDAL_QUALITY.get(quality, "LOSSLESS")
    data = fetch_json(f"{TIDAL_API_URL}/track/{tid}?quality={tier}")
    manifest = data.get("manifest")
    if not manifest:
        return None
    info = json.loads(base64.b64decode(manifest))
    if str(info.get("encryptionType", "")).upper() != "NONE":
        return None  # explicit non-DRM only; no decryption here
    urls = info.get("urls") or []
    if not urls:
        return None
    mime = str(info.get("mimeType", "")).lower()
    codec = "flac" if "flac" in mime else ("aac" if ("mp4" in mime or "aac" in mime) else "")
    return {
        "url": urls[0],
        "format": codec,
        "codec": codec,
        "container": codec,
        "manifest": "none",
        "encrypted": False,
    }


# ── Aggregation ───────────────────────────────────────────────────────────
def search(q, quality):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {"archive": pool.submit(archive_search, q, quality),
                   "tidal": pool.submit(tidal_search, q, quality)}
        rows = []
        for name, fut in futures.items():
            try:
                rows += fut.result()
            except Exception as exc:
                print(f"[search] {name} failed: {exc}", flush=True)
    seen, out = set(), []
    for row in rows:
        key = (row.get("title", "").lower(), row.get("artist", "").lower())
        if row.get("id") and row.get("title") and key not in seen:
            seen.add(key)
            out.append(row)
    return out


def resolve(tid, quality):
    if tid.startswith("archive:"):
        return archive_stream(tid, quality)
    if tid.startswith("tidal:"):
        return tidal_stream(tid.split(":", 1)[1], quality)
    return None


def health():
    return {
        "status": "ok",
        "providers": {
            "archive": {"enabled": True},
            "tidal": {
                "enabled": bool(TIDAL_API_URL),
                "backend": TIDAL_API_URL or None,
                "note": None if TIDAL_API_URL else "set TIDAL_API_URL to a self-hosted binimum/hifi-api",
            },
        },
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        try:
            if path == "/manifest.json":
                return self._send(200, MANIFEST)
            if path == "/health":
                return self._send(200, health())
            if path == "/search":
                q = params.get("q", [""])[0].strip()
                quality = params.get("quality", ["lossless"])[0]
                if not q:
                    return self._send(400, {"error": "missing q"})
                return self._send(200, {"tracks": search(q, quality)})
            if path.startswith("/stream/"):
                tid = urllib.parse.unquote(path[len("/stream/"):])
                quality = params.get("quality", ["lossless"])[0]
                result = resolve(tid, quality)
                if not result:
                    return self._send(404, {"error": "no rendition for that id"})
                return self._send(200, result)
            return self._send(404, {"error": "not found"})
        except Exception as exc:
            print(f"[error] {path}: {exc}", flush=True)
            return self._send(502, {"error": str(exc)})


if __name__ == "__main__":
    print(f"bitchord-multisource on :{PORT} (tidal {'on' if TIDAL_API_URL else 'off'})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
