"""Avature career portals (e.g. jobs.siemens.com/externaljobs). Server-rendered HTML."""
from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup

from ..base import Adapter, looks_vn, register

QUERIES = ["Vietnam", "Viet Nam", "Hanoi", "Ho Chi Minh"]


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    res = []
    for a in soup.select("article"):
        link = a.select_one("a[href*='JobDetail']")
        if not link:
            continue
        href = link["href"].split("?")[0]
        m = re.search(r"/JobDetail/(?:[^/]+/)?(\d+)$", href)
        if not m:
            continue
        title_el = a.select_one("h3 a, h2 a, .article__header__text__title a") or link
        strings = [s.strip() for s in a.stripped_strings]
        res.append({"id": m.group(1), "url": href, "title": title_el.get_text(" ", strip=True),
                    "text": " ".join(strings)})
    return res


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    fields, body = {}, []
    for f in soup.select(".article__content__view__field"):
        lab = f.select_one(".article__content__view__field__label")
        val = f.select_one(".article__content__view__field__value")
        if lab:
            fields[lab.get_text(" ", strip=True)] = (val or f).get_text(" ", strip=True)
        else:
            t = f.get_text("\n", strip=True)
            if t:
                body.append(t)
    return {"fields": fields, "description": "\n".join(body)}


def _date(s):
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).strftime("%Y-%m-%dT00:00:00Z")
        except (ValueError, TypeError):
            pass
    return None


LEVELS = {"student": "internship", "intern": "internship", "graduate": "graduate", "early professional": "graduate",
          "entry": "graduate", "experienced": "experienced", "professional": "experienced", "senior": "experienced",
          "manager": "manager", "leader": "manager", "executive": "manager"}


@register("avature")
class AvatureAdapter(Adapter):
    source = "custom"

    def fetch(self, company, known_ids=None, reuse=None):
        portal = company["career_url"].rstrip("/")     # e.g. https://jobs.siemens.com/en_US/externaljobs
        seen: dict[str, dict] = {}
        for q in QUERIES:
            offset = 0
            while offset < 300:
                r = self.http.get(f"{portal}/SearchJobs/", params={"search": q, "folderRecordsPerPage": 6, "folderOffset": offset})
                if r.status_code != 200:
                    break
                items = parse_list(r.text)
                for it in items:
                    seen.setdefault(it["id"], it)
                if len(items) < 6:
                    break
                offset += 6
        out = []
        for jid, it in seen.items():
            if not (looks_vn(it["text"]) or "multiple locations" in it["text"].lower()):
                continue
            if known_ids and jid in known_ids and reuse:
                prev = reuse(jid)
                if prev:
                    out.append(dict(prev, is_open=True))
                    continue
            r = self.http.get(it["url"])
            if r.status_code != 200:
                continue
            d = parse_detail(r.text)
            f = d["fields"]
            locs = f.get("Location(s)") or f.get("Location") or ""
            if not looks_vn(locs):
                continue
            lvl = (f.get("Experience level") or "").lower()
            mode = (f.get("Work mode") or "").lower()
            out.append({
                "source": "custom",
                "source_job_id": jid,
                "title": it["title"],
                "url": it["url"],
                "company_name_raw": f.get("Company"),
                "location_raw": locs,
                "address_raw": locs,
                "country_code": "VN",
                "description": d["description"],
                "posted_at": _date(f.get("Posted since")),
                "employment_type_raw": f.get("Job type"),
                "level_raw": next((v for k, v in LEVELS.items() if k in lvl), None),
                "function_raw": f.get("Field of work"),
                "work_mode": "remote" if "remote" in mode else ("hybrid" if ("hybrid" in mode or "flex" in mode) else ("onsite" if mode else None)),
                "is_open": True,
            })
        return out
