"""Bounded requests, cached successful responses, and short failure backoff.

The optional fetch function lets the Teamarr adapter use its native proxy policy.
Never log URLs/response bodies: widget query strings can contain public tokens.
"""

import logging
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict

LOG = logging.getLogger(__name__)
MAX_BYTES = 8 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; TeamarrDanishFootball/0.1; fixture reader)"


class SourceError(RuntimeError):
    pass


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise SourceError("Response exceeds size limit")
            return body.decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        raise SourceError(f"Fixture source HTTP {exc.code}") from None
    except (OSError, UnicodeError) as exc:
        raise SourceError(f"Fixture source transport failure ({type(exc).__name__})") from None


class CachedHTTP:
    def __init__(self, fetch=fetch_url, clock=time.monotonic, ttl=900, failure_ttl=60):
        self.fetch = fetch
        self.clock = clock
        self.ttl = ttl
        self.failure_ttl = failure_ttl
        self.cache = OrderedDict()
        self.failures = {}
        self.lock = threading.RLock()

    def get(self, url, ttl=None):
        # Single flight: concurrent Teamarr workers share one schedule download.
        with self.lock:
            now = self.clock()
            entry = self.cache.get(url)
            if entry and entry[0] > now:
                self.cache.move_to_end(url)
                return entry[1]
            if self.failures.get(url, 0) > now:
                raise SourceError("Fixture source temporarily unavailable (retry deferred)")
            try:
                value = self.fetch(url)
            except Exception:
                self.failures[url] = now + self.failure_ttl
                if len(self.failures) > 256:
                    self.failures = {k: v for k, v in self.failures.items() if v > now}
                # Do not present old kickoff times as fresh after an upstream failure.
                raise SourceError("Fixture source fetch failed; no stale fallback used") from None
            self.failures.pop(url, None)
            self.cache[url] = (self.clock() + (self.ttl if ttl is None else ttl), value)
            self.cache.move_to_end(url)
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
            return value

    def invalidate(self, url):
        with self.lock:
            self.cache.pop(url, None)
