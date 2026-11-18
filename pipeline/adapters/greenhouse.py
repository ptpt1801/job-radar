"""Greenhouse public job-board API."""
from __future__ import annotations

import datetime as dt

from ..text import html_to_text
from .base import Adapter, looks_vn, register


@register("greenhouse")
class GreenhouseAdapter(Adapter):
    source = "greenhouse"

    def fetch(self, company, known_ids=None, reuse=None):
        token = company["ats_id"]
        j = self.http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"})
        out = []
        for p in j.get("jobs", []):
            locname = (p.get("location") or {}).get("name") or ""
            offices = " | ".join(o.get("name", "") + " " + (o.get("location") or "") for o in p.get("offices") or [])
            if not looks_vn(locname, offices):
                continue
            out.append({
                "source": "greenhouse",
                "source_job_id": str(p["id"]),
                "title": p.get("title"),
                "url": p.get("absolute_url"),
                "location_raw": locname or offices,
                "address_raw": locname,
                "country_code": "VN",
                "description": html_to_text(p.get("content")),
                "posted_at": p.get("first_published") or p.get("updated_at"),
                "function_raw": " ".join(d.get("name", "") for d in p.get("departments") or []),
                "is_open": True,
            })
        return out
