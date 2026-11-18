"""Ashby public job-board API."""
from __future__ import annotations

import datetime as dt

from ..text import html_to_text
from .base import Adapter, looks_vn, register


@register("ashby")
class AshbyAdapter(Adapter):
    source = "ashby"

    def fetch(self, company, known_ids=None, reuse=None):
        name = company["ats_id"]
        j = self.http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{name}", params={"includeCompensation": "true"})
        out = []
        for p in j.get("jobs", []):
            addr = ((p.get("address") or {}).get("postalAddress") or {})
            locs = " | ".join([p.get("location") or ""] + [s.get("location", "") for s in p.get("secondaryLocations") or []])
            if not (looks_vn(locs, addr.get("addressCountry")) and p.get("isListed", True)):
                continue
            out.append({
                "source": "ashby",
                "source_job_id": p.get("id") or p.get("jobUrl"),
                "title": p.get("title"),
                "url": p.get("jobUrl"),
                "location_raw": locs,
                "address_raw": ", ".join(x for x in [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")] if x) or None,
                "country_code": "VN",
                "description": p.get("descriptionPlain") or html_to_text(p.get("descriptionHtml")),
                "posted_at": p.get("publishedAt"),
                "employment_type_raw": p.get("employmentType"),
                "function_raw": p.get("department") or p.get("team"),
                "work_mode": {"Remote": "remote", "Hybrid": "hybrid", "OnSite": "onsite"}.get(p.get("workplaceType")),
                "is_open": True,
            })
        return out
