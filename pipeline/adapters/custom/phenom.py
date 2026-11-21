"""Phenom People career sites (careers.<company>.com/<country>/<lang>).

The site's own front-end calls POST /widgets (ddoKey=refineSearch) for search results; robots.txt
allows it (only */px-widgets, */apply, ... are disallowed). Detail text comes from the job page's
embedded `phApp.ddo` JSON (/job/<jobId>)."""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from ...text import html_to_text, looks_vn
from ..base import Adapter, register

PAGE = 10
COUNTRY_NAMES = ["Vietnam", "Viet Nam", "Việt Nam"]
DDO_RE = re.compile(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.", re.S)


def ddo(html: str) -> dict:
    m = DDO_RE.search(html or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def site_parts(career_url: str) -> tuple[str, str, str]:
    """https://careers.dhl.com/global/en -> (base, lang 'en_global', country 'global')."""
    u = urlparse(career_url)
    seg = [s for s in u.path.split("/") if s]
    country, lang = (seg[0], seg[1]) if len(seg) >= 2 else ("global", "en")
    base = f"{u.scheme}://{u.netloc}/{country}/{lang}"
    return base, f"{lang}_{country}", country


def _iso(s) -> str | None:
    s = str(s or "")
    return (s[:10] + "T00:00:00Z") if re.match(r"\d{4}-\d{2}-\d{2}", s) else None


def _is_vn(j: dict) -> bool:
    locs = j.get("multi_location") or []
    locs = [l if isinstance(l, str) else " ".join(str(v) for v in (l or {}).values()) for l in locs]
    return looks_vn(j.get("country"), j.get("cityStateCountry"), *locs)


@register("phenom")
class PhenomAdapter(Adapter):
    source = "custom"

    def _search(self, host_root, lang, country, cname, start):
        body = {"lang": lang, "deviceType": "desktop", "country": country, "pageName": "search-results",
                "ddoKey": "refineSearch", "from": start, "size": PAGE, "jobs": True, "counts": True,
                "clearAll": False, "jdsource": "facets", "siteType": "external", "keywords": "", "global": True,
                "selected_fields": {"country": [cname]}}
        j = self.http.post_json(host_root + "/widgets", json=body)
        rs = j.get("refineSearch") or {}
        return (rs.get("data") or {}).get("jobs") or [], rs.get("totalHits") or 0

    def fetch(self, company, known_ids=None, reuse=None):
        base, lang, country = site_parts(company["career_url"])
        u = urlparse(base)
        host_root = f"{u.scheme}://{u.netloc}"
        jobs, total, start = [], 0, 0
        for cname in COUNTRY_NAMES:
            jobs, total = self._search(host_root, lang, country, cname, 0)
            if jobs:
                break
        start = len(jobs)
        while jobs and start < min(total, 400):
            batch, _ = self._search(host_root, lang, country, cname, start)
            if not batch:
                break
            jobs += batch
            start += len(batch)

        out, seen = [], set()
        for j in jobs:
            jid = str(j.get("jobId") or j.get("reqId") or "")
            if not jid or jid in seen or not _is_vn(j):
                continue
            seen.add(jid)
            url = f"{base}/job/{jid}"
            if known_ids and jid in known_ids and reuse:
                prev = reuse(jid)
                if prev:
                    out.append(dict(prev, is_open=True))
                    continue
            desc = ""
            r = self.http.get(url)
            if r.status_code == 200:
                d = ((ddo(r.text).get("jobDetail") or {}).get("data") or {}).get("job") or {}
                desc = html_to_text(d.get("description"))
            locs = [l if isinstance(l, str) else (l or {}).get("cityState") or "" for l in (j.get("multi_location") or [])]
            loc = " | ".join(x for x in locs if x) or j.get("cityStateCountry") or "Vietnam"
            out.append({
                "source": "custom",
                "source_job_id": jid,
                "title": j.get("title"),
                "url": url,
                "location_raw": loc if looks_vn(loc) else loc + ", Vietnam",
                "city_raw": j.get("city"),
                "country_code": "VN",
                "description": desc or html_to_text(j.get("descriptionTeaser")),
                "posted_at": _iso(j.get("postedDate") or j.get("dateCreated")),
                "employment_type_raw": " ".join(x for x in [j.get("type"), j.get("contractType1"), j.get("workHours")] if x) or None,
                "level_raw": None,
                "function_raw": " ".join(j.get("multi_category") or []) or j.get("category"),
                "is_open": True,
            })
        return out
