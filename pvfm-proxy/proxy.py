#!/usr/bin/env python3
"""pvfm-proxy - same-origin metadata proxy for pvfm.deltaryz.com.

PVFM's PHP update dropped `Access-Control-Allow-Origin` from
https://ponyvillefm.com/data/nowplaying and /data/schedule, which broke the
web app (and the Play Store Bubblewrap build, which is the same page). Rather
than asking them to fix a header, Caddy serves /data/* on the app's own origin
and this process fetches upstream server-side, where CORS does not apply.

Design notes
------------
- Only the two endpoints the app actually fetches are proxied. Stream URLs and
  artwork images never needed CORS (plain <audio>/<img> loads), so they stay
  direct.
- Responses are passed through byte-for-byte, so any field PVFM adds later
  still reaches the app.
- A short TTL absorbs the app's 4-second poll interval (app.js:989).
- When upstream fails, the last good body keeps being served for
  STALE_HOLD_SECONDS (6 min), then a synthesized "Error: serverside timeout"
  payload takes over so the UI says something truthful instead of freezing on
  a stale song forever.
- Failed fetches are negatively cached (RETRY_AFTER_FAIL_SECONDS) so an
  upstream outage does not turn every client poll into a new upstream request.
- Stdlib only: runs on stock python:3.12-slim with no pip install.
"""

import json
import os
import threading
import time
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "https://ponyvillefm.com").rstrip("/")
PORT = int(os.environ.get("PORT", "8080"))
FETCH_TIMEOUT = float(os.environ.get("FETCH_TIMEOUT_SECONDS", "10"))
NOWPLAYING_TTL = float(os.environ.get("NOWPLAYING_TTL_SECONDS", "5"))
SCHEDULE_TTL = float(os.environ.get("SCHEDULE_TTL_SECONDS", "60"))
STALE_HOLD = float(os.environ.get("STALE_HOLD_SECONDS", "360"))
RETRY_AFTER_FAIL = float(os.environ.get("RETRY_AFTER_FAIL_SECONDS", "5"))
USER_AGENT = os.environ.get("USER_AGENT", "pvfm-proxy/1.0 (+https://pvfm.deltaryz.com)")

# Mount key in the upstream nowplaying document -> name shown to the user when
# upstream is dead. Keys match app.js (data.one / data.two / data.free /
# data.lunaradio).
STATIONS = {
    "one": "PonyvilleFM",
    "two": "PonyvilleFM2 Chill",
    "free": "PonyvilleFM3 No DJs",
    "lunaradio": "Luna Radio",
}


def log(msg):
    print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def synth_nowplaying():
    """Payload served once the stale window has expired.

    Shape mirrors upstream so app.js needs no special case: title is the
    message, artist carries the station name.
    """
    body = {"all": {"listeners": 0}}
    for key, name in STATIONS.items():
        body[key] = {
            "nowplaying": "",
            "artist": name,
            "album": "",
            "title": "Error: serverside timeout",
            "onair": "",
            "artwork": "/images/music/default.png",
            "listeners": 0,
        }
    return json.dumps(body).encode()


def synth_schedule():
    """Empty schedule. app.js keeps any schedule it already had in memory and
    simply leaves the event box alone when the list is empty."""
    return json.dumps({"result": []}).encode()


class Endpoint:
    """One cached upstream path."""

    def __init__(self, path, ttl, synth):
        self.path = path
        self.ttl = ttl
        self.synth = synth
        self.lock = threading.Lock()
        self.body = None          # last good body, bytes
        self.fetched_at = 0.0     # when body was fetched
        self.fetching = False     # a thread is talking to upstream right now
        self.next_attempt = 0.0   # negative-cache floor after a failure
        self.last_error = None
        self.last_error_at = 0.0

    def _fallback(self, now):
        """Body to serve when upstream is unavailable."""
        if self.body is not None and (now - self.fetched_at) <= STALE_HOLD:
            return self.body, "stale"
        return self.synth(), "timeout"

    def serve(self):
        """Returns (body_bytes, state) where state is hit|miss|stale|timeout."""
        now = time.time()
        with self.lock:
            if self.body is not None and (now - self.fetched_at) < self.ttl:
                return self.body, "hit"
            if self.fetching or now < self.next_attempt:
                body, state = self._fallback(now)
                return body, state
            self.fetching = True

        try:
            body = self._fetch()
        except Exception as exc:  # noqa: BLE001 - any upstream failure is the same here
            with self.lock:
                self.fetching = False
                self.last_error = "%s: %s" % (type(exc).__name__, exc)
                self.last_error_at = time.time()
                self.next_attempt = self.last_error_at + RETRY_AFTER_FAIL
            log("FAIL %s (%s) - serving fallback" % (self.path, self.last_error))
            with self.lock:
                body, state = self._fallback(time.time())
            return body, state

        with self.lock:
            self.fetching = False
            self.body = body
            self.fetched_at = time.time()
            self.last_error = None
        log("OK %s (%d bytes)" % (self.path, len(body)))
        return body, "miss"

    def _fetch(self):
        url = UPSTREAM + self.path
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Cache-Control": "no-cache",
            },
        )
        # No cookie jar and no redirect customisation: PVFM hands out a
        # laravel-session cookie on every hit and it means nothing to us.
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                raise RuntimeError("upstream status %s" % resp.status)
            raw = resp.read()
        # Validate before caching: a Cloudflare HTML error page must not be
        # stored as "last good metadata".
        json.loads(raw)
        return raw

    def status(self):
        now = time.time()
        with self.lock:
            return {
                "path": self.path,
                "has_body": self.body is not None,
                "age_seconds": round(now - self.fetched_at, 1) if self.body else None,
                "ttl_seconds": self.ttl,
                "stale_hold_seconds": STALE_HOLD,
                "serving": (
                    "fresh" if self.body and (now - self.fetched_at) < self.ttl
                    else "stale" if self.body and (now - self.fetched_at) <= STALE_HOLD
                    else "timeout-payload" if self.body
                    else "no-data-yet"
                ),
                "fetching": self.fetching,
                "last_error": self.last_error,
                "last_error_ago_seconds": (
                    round(now - self.last_error_at, 1) if self.last_error else None
                ),
            }


ENDPOINTS = {
    "/data/nowplaying": Endpoint("/data/nowplaying", NOWPLAYING_TTL, synth_nowplaying),
    "/data/schedule": Endpoint("/data/schedule", SCHEDULE_TTL, synth_schedule),
}

# Caddy v1 forwards the prefix, but accepting the bare path too keeps direct
# testing (curl http://pvfm-proxy:8080/nowplaying) simple.
ALIASES = {path[len("/data"):]: path for path in ENDPOINTS}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "pvfm-proxy/1.0"

    def _resolve(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ENDPOINTS:
            return path
        return ALIASES.get(path)

    def _send(self, status, body, content_type, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Same-origin from the app's point of view, but send it anyway so the
        # endpoint is usable from anywhere (and from old cached app.js builds
        # that still hit absolute URLs via a custom host).
        self.send_header("Access-Control-Allow-Origin", "*")
        # generous on purpose: the dev preview under the code-server path prefix
        # (and anything else) can pull this cross-origin and read the proxy headers
        self.send_header("Access-Control-Expose-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        raw = self.path.split("?", 1)[0].rstrip("/")
        if raw in ("/data/proxy-status", "/proxy-status"):
            body = json.dumps(
                {
                    "upstream": UPSTREAM,
                    "now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "endpoints": [ep.status() for ep in ENDPOINTS.values()],
                }
            ).encode()
            self._send(200, body, "application/json; charset=utf-8")
            return
        path = self._resolve()
        if path is None:
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        body, state = ENDPOINTS[path].serve()
        self._send(
            200,
            body,
            "application/json; charset=utf-8",
            {"X-Pvfm-Proxy": state},
        )

    do_HEAD = do_GET

    def log_message(self, fmt, *args):
        pass  # Endpoint.serve() already logs every state change


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    log(
        "listening on :%d, upstream %s (nowplaying ttl %ss, schedule ttl %ss, "
        "stale hold %ss)"
        % (PORT, UPSTREAM, NOWPLAYING_TTL, SCHEDULE_TTL, STALE_HOLD)
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
