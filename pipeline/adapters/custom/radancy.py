"""Radancy / TalentBrew career sites (jobs.<company>.com).

Radancy sites usually disallow /search-jobs/ in robots.txt, so this adapter reads the public
sitemap (allowed), keeps /job/<vietnam-city>/... URLs and reads each posting's JSON-LD."""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from ...text import html_to_text, looks_vn
from ..base import Adapter, register

VN_SLUG = re.compile(r"/job/(?:ho-chi-minh|hcm|hanoi|ha-noi|viet-?nam|da-nang|danang|hai-phong|haiphong|binh-duong|dong-nai|"
                     r"bac-ninh|bien-hoa|thu-duc|can-tho|long-an|vung-tau|ba-ria|hai-duong|hung-yen|vinh-phuc|thai-nguyen)[^/]*/")


def job_ld(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    for s in soup.select('script[type="application/ld+json"]'):
        try:
            d = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for it in (d if isinstance(d, list) else [d]):
            if isinstance(it, dict) and it.get("@type") == "JobPosting":
                return it
    return {}


def _loc(ld: dict) -> tuple[str, str | None]:
    locs = ld.get("jobLocation") or []
    locs = locs if isinstance(locs, list) else [locs]
    parts, cc = [], None
    for l in locs:
        a = (l or {}).get("address") or {}
        parts.append(", ".join(x for x in [a.get("addressLocality"), a.get("addressRegion"), a.get("addressCountry")] if isinstance(x, str) and x))
        if str(a.get("addressCountry") or "").upper() in ("VN", "VIETNAM", "VIET NAM"):
            cc = "VN"
    return " | ".join(p for p in parts if p), cc


@register("radancy")
class RadancyAdapter(Adapter):
    source = "custom"

    def _sitemap_urls(self, base: str) -> list[str]:
        urls, queue, seen = [], [base + "/sitemap.xml"], set()
        while queue and len(seen) < 20:
            sm = queue.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            r = self.http.get(sm)
            if r.status_code != 200:
                continue
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text):
                if loc.endswith(".xml"):
                    queue.append(loc)
                elif "/job/" in loc:
                    urls.append(loc)
        return urls

    def fetch(self, company, known_ids=None, reuse=None):
        base = company["career_url"].rstrip("/")
        cands = [u for u in self._sitemap_urls(base) if VN_SLUG.search(u.lower())]
        out = []
        for u in cands:
            jid = u.rstrip("/").rsplit("/", 1)[-1]
            if known_ids and jid in known_ids and reuse:
                prev = reuse(jid)
                if prev:
                    out.append(dict(prev, is_open=True))
                    continue
            r = self.http.get(u)
            if r.status_code != 200:
                continue
            ld = job_ld(r.text)
            loc, cc = _loc(ld)
            if not (cc == "VN" or looks_vn(loc, u.replace("-", " "))):
                continue
            emp = ld.get("employmentType")
            out.append({
                "source": "custom",
                "source_job_id": jid,
                "title": ld.get("title") or BeautifulSoup(r.text, "lxml").title.get_text(strip=True),
                "url": u,
                "location_raw": (loc or u) + " Vietnam",
                "address_raw": loc or None,
                "country_code": "VN",
                "description": html_to_text(ld.get("description")),
                "posted_at": (str(ld["datePosted"])[:10] + "T00:00:00Z") if ld.get("datePosted") else None,
                "deadline": str(ld.get("validThrough") or "")[:10] or None,
                "employment_type_raw": " ".join(emp) if isinstance(emp, list) else emp,
                "is_open": True,
            })
        return out
