"""Polite HTTP client: per-host rate limit, robots.txt, retry with backoff, request stats."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from urllib.parse import urlparse

import requests

from .config import settings
from .robots import Robots


class RobotsDisallowed(Exception):
    pass


# Hosts that are subdomains of one shared platform share a single rate limit.
SHARED_PLATFORMS = ("myworkdayjobs.com",)


def rate_key(host: str) -> str:
    for d in SHARED_PLATFORMS:
        if host == d or host.endswith("." + d):
            return d
    return host


class PoliteClient:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or settings()["http"]
        self.ua = cfg["user_agent"]
        self.timeout = cfg.get("timeout_s", 20)
        self.min_interval = float(cfg.get("min_interval_s", 1.0))
        self.retries = int(cfg.get("retries", 3))
        self.exempt = set(cfg.get("robots_exempt_hosts") or [])
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.ua, "Accept-Language": "en-US,en;q=0.8,vi;q=0.6"})
        self._host_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._last: dict[str, float] = {}
        self._robots: dict[str, Robots | None] = {}
        self._delay: dict[str, float] = {}
        self._glock = threading.Lock()
        self.stats = defaultdict(lambda: {"requests": 0, "errors": 0})

    # ---- robots ---------------------------------------------------------
    def _robots_for(self, scheme: str, host: str):
        with self._glock:
            if host in self._robots:
                return self._robots[host]
        rp: Robots | None
        url = f"{scheme}://{host}/robots.txt"
        try:
            self._wait(host)
            r = self.session.get(url, timeout=self.timeout)
            self.stats[host]["requests"] += 1
            ctype = r.headers.get("content-type", "")
            if r.status_code == 200 and "html" not in ctype.lower():
                rp = Robots(r.text)
            elif r.status_code in (401, 403):
                rp = Robots(disallow_all=True)
            else:
                rp = None  # no robots.txt -> everything allowed
        except requests.RequestException:
            rp = None
        delay = 0.0
        if rp is not None:
            try:
                delay = float(rp.crawl_delay(self.ua) or 0)
            except Exception:
                delay = 0.0
        with self._glock:
            self._robots[host] = rp
            self._delay[host] = max(self.min_interval, delay)
        return rp

    def allowed(self, url: str) -> bool:
        u = urlparse(url)
        if u.hostname in self.exempt:
            self._delay.setdefault(u.hostname, self.min_interval)
            return True
        rp = self._robots_for(u.scheme, u.hostname)
        return True if rp is None else rp.can_fetch(self.ua, url)

    # ---- rate limit -----------------------------------------------------
    def _wait(self, host: str):
        interval = self._delay.get(host, self.min_interval)
        key = rate_key(host)
        with self._host_locks[key]:
            last = self._last.get(key, 0.0)
            now = time.monotonic()
            if now - last < interval:
                time.sleep(interval - (now - last))
            self._last[key] = time.monotonic()

    # ---- request --------------------------------------------------------
    def request(self, method: str, url: str, **kw) -> requests.Response:
        host = urlparse(url).hostname
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        kw.setdefault("timeout", self.timeout)
        last_exc = None
        for attempt in range(self.retries + 1):
            self._wait(host)
            self.stats[host]["requests"] += 1
            try:
                r = self.session.request(method, url, **kw)
            except requests.RequestException as e:
                last_exc = e
                self.stats[host]["errors"] += 1
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                self.stats[host]["errors"] += 1
                last_exc = requests.HTTPError(f"{r.status_code} for {url}")
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = float(retry_after)
                elif r.status_code == 429:
                    if attempt >= 1:                 # give up fast; the caller retries the company later
                        break
                    wait = 10.0
                else:
                    wait = 2 ** (attempt + 1)
                time.sleep(min(wait, 120))
                continue
            if r.status_code >= 400:
                self.stats[host]["errors"] += 1
            return r
        raise last_exc or RuntimeError(url)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def get_json(self, url, **kw):
        r = self.get(url, **kw)
        r.raise_for_status()
        return r.json()

    def post_json(self, url, **kw):
        r = self.post(url, **kw)
        r.raise_for_status()
        return r.json()


_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient()
    return _client
