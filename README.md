# bitchord-multisource

[BitChord](https://github.com/kushagrasinghx/BitChord) addon: one source that searches **Internet Archive** (free, no account) and, optionally, **Tidal** through a self-hosted [binimum/hifi-api](https://github.com/binimum/hifi-api) instance.

BitChord tries sources top to bottom — put this below your own library addons and above nothing you trust more.

## Endpoints

| Route | Purpose |
|---|---|
| `GET /manifest.json` | addon identity + quality picker (Lossless / High / Low) |
| `GET /search?q=&quality=` | merged results; per-provider timeout, one provider failing never blocks the other |
| `GET /stream/{id}?quality=` | resolves `archive:…` or `tidal:…` ids to a direct audio URL |
| `GET /health` | which providers are enabled/configured |

Track ids are provider-namespaced: `archive:<identifier>:<file>`, `tidal:<id>`. No DRM handling anywhere — Tidal rows only stream when the backend returns an explicit non-DRM URL.

## Run

```bash
python3 server.py            # stdlib only, no pip install
# or
docker compose up --build -d
```

Config (env):

| Var | Default | Meaning |
|---|---|---|
| `PORT` | `8080` | listen port |
| `TIDAL_API_URL` | _(unset = off)_ | base URL of your hifi-api instance |
| `PROVIDER_TIMEOUT` | `8` | per-provider fetch timeout (s) |
| `ARCHIVE_ROWS` | `10` | archive.org items per search |
| `BITCHORD_AUTH` | `log` | `log` = verify + log failures, serve everyone · `enforce` = 401 for non-official clients · `off` |
| `BITCHORD_AUTH_HOSTS` | _(unset)_ | comma-separated public hostnames (required for real verification) |

## Downloads and the Opus question

BitChord's **Standard** download tier never asks any source — by app design
(`SourceResolver.forDownload` returns null for `StreamRequest.Capped`; "YouTube's
ladder is the only one that can be capped") — so Standard downloads are always
YouTube Opus, from every addon. To download this addon's FLAC, set
**Settings → Downloads → Download quality** to **High** or **Lossless**.

Internet Archive is a catalogue of live concerts, 78rpm transfers and archives —
modern studio tracks are mostly absent, and those downloads will come from
YouTube. That is catalog reality, not a bug.

## Addon auth

The manifest declares `bitchordAuth: true`, which clears BitChord's "Outdated
addon" note. The official verifier (`bitchord_addon_auth.py`, vendored unchanged)
checks the app's hardware-backed proof:

- `BITCHORD_AUTH=log` (default): verify, log `would refuse: <code>`, serve everyone — official rollout step 1.
- `BITCHORD_AUTH=enforce`: only the official BitChord Android app gets through (rooted phones, emulators, desktop and curl get 401).
- Needs `pip install cryptography` (Docker image already includes it).

## Add to BitChord

BitChord requires HTTPS. Terminate TLS with Caddy/nginx or use a Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://localhost:8080
```

Then: **Settings → Sources → Add an addon** → paste `https://your-host/`.

## Status / honesty

- **Internet Archive**: search + stream resolution verified live (search → stream URL → HTTP 206 `fLaC`). Playback matching happens inside BitChord on-device.
- **Addon auth**: manifest flag live-verified; verifier behavior tested — log mode serves + logs `would refuse: missing`, enforce mode answers `401` with the `WWW-Authenticate: BitChord` challenge for missing and forged credentials.
- **Tidal adapter**: written against hifi-api's documented `/search/` + `/track/` endpoints, **not exercised end-to-end** here (needs a Tidal account + hifi-api deployment). Code path returns 404/no-rendition until `TIDAL_API_URL` is set.
- 78rpm/live-concert metadata on archive.org is uneven; BitChord's duration/title matching filters bad rows.

## License

MIT
