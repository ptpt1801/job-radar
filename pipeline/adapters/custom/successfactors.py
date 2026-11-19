"""SAP SuccessFactors Career Site Builder portals (jobs.<company>.com/search/...). Server-rendered HTML.

List: /search/?q=&locationsearch=Vietnam&startrow=N (tr.data-row). Location search is fuzzy, so each
row is confirmed as Vietnam from the row or, failing that, from the detail page."""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...text import html_to_text, looks_vn
from ..base import Adapter, register


def parse_list(html: str, base: str) -> tuple[list[dict], int | None]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    seen_href = set()
    for tr in soup.select("tr.data-row, li.job-tile"):          # table layout and tile layout
        a = tr.select_one("a.jobTitle-link") or tr.select_one('a[href*="/job/"]')
        raw_href = a["href"] if a else tr.get("data-url")
        if not raw_href:
            continue
        href = urljoin(base + "/", raw_href)
        if href in seen_href:
            continue
        seen_href.add(href)
        m = re.search(r"/(\d+)/?$", href)
        t = tr.select_one(".tiletitle a, .tiletitle") if not a else a
        title = (t.get_text(" ", strip=True) if t else "").removeprefix("Title").strip()
        loc = tr.select_one(".jobLocation, [id*='location-value'], [id*='desktop-section-location-value']")
        date = tr.select_one(".jobDate, [id*='date-value']")
        rows.append({"id": m.group(1) if m else href, "url": href, "title": title,
                     "location": loc.get_text(" ", strip=True) if loc else "", "date": date.get_text(" ", strip=True) if date else ""})
    total = None
    lab = soup.select_one(".paginationLabel")
    if lab:
        m = re.search(r"of\s+(\d+)", lab.get_text(" ", strip=True))
        total = int(m.group(1)) if m else None
    return rows, total


def _date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%a %b %d %H:%M:%S UTC %Y", "%b %d, %Y", "%d %b %Y", "%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            pass
    return None


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    dp = soup.select_one('[itemprop="datePosted"]')
    desc = soup.select_one('[itemprop="description"]') or soup.select_one(".jobdescription")
    locs = [x.get_text(" ", strip=True) for x in soup.select(".jobGeoLocation, [data-careersite-propertyid=location]")]
    return {"posted": (dp.get("content") or dp.get_text(strip=True)) if dp else None,
            "description": html_to_text(str(desc)) if desc else "",
            "location": locs[0] if locs else ""}


@register("successfactors")
class SuccessFactorsAdapter(Adapter):
    source = "custom"

    def fetch(self, company, known_ids=None, reuse=None):
        base = company["career_url"].rstrip("/")
        rows, start = {}, 0
        while start < 300:
            params = {"q": "", "locationsearch": "Vietnam"}
            if start:
                params["startrow"] = start  # some sites return nothing for startrow=0
            r = self.http.get(f"{base}/search/", params=params)
            if r.status_code != 200:
                break
            batch, total = parse_list(r.text, base)
            new = [b for b in batch if b["id"] not in rows]
            for b in new:
                rows[b["id"]] = b
            start += len(batch) or 25
            if not new or total is None or start >= total:
                break
        out = []
        for jid, b in rows.items():
            slug_vn = looks_vn(b["location"], b["url"].replace("-", " "))
            if known_ids and jid in known_ids and reuse and slug_vn:
                prev = reuse(jid)
                if prev:
                    out.append(dict(prev, is_open=True))
                    continue
            r = self.http.get(b["url"])
            if r.status_code != 200:
                continue
            d = parse_detail(r.text)
            loc = d["location"] or b["location"]
            if not (looks_vn(loc) or re.search(r"\bVN\b", loc)):
                continue
            out.append({
                "source": "custom",
                "source_job_id": jid,
                "title": b["title"],
                "url": b["url"],
                "location_raw": loc + " Vietnam",
                "address_raw": loc,
                "country_code": "VN",
                "description": d["description"],
                "posted_at": _date(d["posted"]) or _date(b["date"]),
                "is_open": True,
            })
        return out
