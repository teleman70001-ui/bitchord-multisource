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

## Add to BitChord

BitChord requires HTTPS. Terminate TLS with Caddy/nginx or use a Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://localhost:8080
```

Then: **Settings → Sources → Add an addon** → paste `https://your-host/`.

## Status / honesty

- **Internet Archive**: search + stream resolution verified live (search → stream URL → HTTP 200 `audio/flac`). Playback matching happens inside BitChord on-device.
- **Tidal adapter**: written against hifi-api's documented `/search/` + `/track/` endpoints, **not exercised end-to-end** here (needs a Tidal account + hifi-api deployment). Code path returns 404/no-rendition until `TIDAL_API_URL` is set.
- Manifest does not declare `bitchordAuth`, so BitChord shows an "Outdated addon" note — cosmetic; the addon works (per official docs).
- 78rpm/live-concert metadata on archive.org is uneven; BitChord's duration/title matching filters bad rows.

## License

MIT
