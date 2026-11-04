# pvfm-proxy

Same-origin metadata proxy for `pvfm.deltaryz.com`.

## Why

Around 2026-10-21 PVFM's PHP update removed `Access-Control-Allow-Origin` from
`https://ponyvillefm.com/data/nowplaying` and `/data/schedule`. The app still
fetches fine when you `curl` it (curl does not enforce CORS), but the browser
refuses to hand the response to `app.js`, so the web app and the Play Store
build (a Bubblewrap wrapper around the same page) went blind.

Rather than asking PVFM to re-add a header, Caddy serves `/data/*` on the app's
own origin and this process does the fetch server-side, where CORS does not
apply. Same origin means no CORS dependency at all, ever again.

## What is proxied

Only the two endpoints the app fetches:

- `/data/nowplaying` (app.js:387)
- `/data/schedule` (app.js:539)

Stream URLs (`dj.bronyradio.com`, `luna.ponyvillefm.com`) and artwork images are
left alone: `<audio>` and `<img>` loads are not CORS-gated.

Plus `/data/proxy-status`, a JSON debug view of cache age and last error.

## Behaviour

- Responses pass through byte-for-byte after a JSON validity check, so fields
  PVFM adds later still reach the app. An HTML error page from Cloudflare is
  never cached as "last good metadata".
- Cached for `NOWPLAYING_TTL_SECONDS` (5) / `SCHEDULE_TTL_SECONDS` (60). The app
  polls every 4 seconds from every open client; this bounds upstream traffic.
- Upstream failure: the last good body keeps being served for
  `STALE_HOLD_SECONDS` (360 = 6 minutes), then a synthesized payload takes over
  with `title: "Error: serverside timeout"` and `artist` set to the station name
  (PonyvilleFM / PonyvilleFM2 Chill / PonyvilleFM3 No DJs / Luna Radio). That is
  why the app has a matching blacklist rule, so error frames never land in the
  song history log.
- Failed fetches are negatively cached for `RETRY_AFTER_FAIL_SECONDS` (5) so an
  outage does not turn every poll into a new upstream request.
- If several clients poll at once, only one thread talks to upstream; the others
  get whatever is in cache.

Every state change is logged to stdout (`docker logs pvfm-proxy`). The
`X-Pvfm-Proxy` response header says `hit` / `miss` / `stale` / `timeout`.

## Env

| var | default |
|---|---|
| `PORT` | `8080` |
| `UPSTREAM` | `https://ponyvillefm.com` |
| `FETCH_TIMEOUT_SECONDS` | `10` |
| `NOWPLAYING_TTL_SECONDS` | `5` |
| `SCHEDULE_TTL_SECONDS` | `60` |
| `STALE_HOLD_SECONDS` | `360` |
| `RETRY_AFTER_FAIL_SECONDS` | `5` |

Stdlib only (`python:3.12-slim`, no pip install).
