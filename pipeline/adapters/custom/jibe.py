"""Jibe (iCIMS) career sites, e.g. careers.se.com (Schneider Electric). Public /api/jobs JSON."""
from __future__ import annotations

import datetime as dt

from ...text import html_to_text
from ..base import Adapter, register


def _date(s):
    if not s:
        return None
    for fmt in ("%B %d, %Y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            pass
    return None


@register("jibe")
class JibeAdapter(Adapter):
    source = "custom"

    def fetch(self, company, known_ids=None, reuse=None):
        site = company["career_url"].rstrip("/")          # e.g. https://careers.se.com
        site = site.removesuffix("/jobs")
        out, page = [], 1
        while page <= 10:
            j = self.http.get_json(f"{site}/api/jobs", params={
                "location": "Vietnam", "page": page, "limit": 100, "sortBy": "posted_date", "descending": "true", "internal": "false"})
            jobs = j.get("jobs") or []
            for x in jobs:
                d = x.get("data") or {}
                if (d.get("country_code") or "").upper() != "VN":
                    continue
                desc = "\n".join(html_to_text(d.get(k)) for k in ("description", "responsibilities", "qualifications") if d.get(k))
                out.append({
                    "source": "custom",
                    "source_job_id": str(d.get("req_id") or d.get("slug")),
                    "title": d.get("title"),
                    "url": f"{site}/jobs/{d.get('slug')}?lang={d.get('language') or 'en-us'}",
                    "location_raw": d.get("full_location") or d.get("location_name"),
                    "address_raw": d.get("full_location") or d.get("location_name"),
                    "city_raw": d.get("city"),
                    "country_code": "VN",
                    "description": desc,
                    "posted_at": _date(d.get("posted_date")),
                    "employment_type_raw": d.get("employment_type"),
                    "function_raw": " ".join(c.get("name", "") for c in d.get("categories") or [] if isinstance(c, dict)),
                    "is_open": d.get("applyable", True) is not False,
                })
            if len(jobs) < 100 or page * 100 >= (j.get("totalCount") or 0):
                break
            page += 1
        return out
