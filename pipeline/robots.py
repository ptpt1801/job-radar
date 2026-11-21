"""robots.txt matching per RFC 9309: the most specific (longest) matching rule wins, Allow wins ties.

Python's urllib.robotparser applies rules in file order, so `Disallow: /` followed by
`Allow: /api/...` wrongly blocks the allowed path. Supports `*` and `$` wildcards and Crawl-delay."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse


def _rx(path: str) -> re.Pattern:
    end = path.endswith("$")
    p = re.escape(path[:-1] if end else path).replace(r"\*", ".*")
    return re.compile(p + ("$" if end else ""))


class Robots:
    def __init__(self, text: str = "", disallow_all: bool = False):
        self.disallow_all = disallow_all
        self.groups: list[tuple[list[str], list[tuple[bool, str]], float | None]] = []
        agents, rules, delay, in_rules = [], [], None, False
        for raw in (text or "").splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (s.strip() for s in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if in_rules:
                    self.groups.append((agents, rules, delay))
                    agents, rules, delay, in_rules = [], [], None, False
                agents.append(v.lower())
            elif k in ("allow", "disallow"):
                in_rules = True
                if v:
                    rules.append((k == "allow", v))
            elif k == "crawl-delay":
                in_rules = True
                try:
                    delay = float(v)
                except ValueError:
                    pass
        if agents:
            self.groups.append((agents, rules, delay))

    def _group(self, ua: str):
        token = ua.split("/", 1)[0].strip().lower()
        rules, delay, found = [], None, False
        for agents, r, d in self.groups:          # all groups naming our token are merged
            if any(a != "*" and a in token for a in agents):
                rules += r
                delay = d if d is not None else delay
                found = True
        if not found:
            for agents, r, d in self.groups:
                if "*" in agents:
                    rules += r
                    delay = d if d is not None else delay
        return rules, delay

    def can_fetch(self, ua: str, url: str) -> bool:
        if self.disallow_all:
            return False
        u = urlparse(url)
        path = unquote(u.path or "/") + (("?" + u.query) if u.query else "")
        best_len, best_allow = -1, True
        for allow, pat in self._group(ua)[0]:
            if _rx(unquote(pat)).match(path):
                n = len(pat)
                if n > best_len or (n == best_len and allow):
                    best_len, best_allow = n, allow
        return best_allow

    def crawl_delay(self, ua: str) -> float | None:
        return self._group(ua)[1]
