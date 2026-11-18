"""Lever public postings API."""
from __future__ import annotations

import datetime as dt

from ..text import html_to_text
from .base import Adapter, looks_vn, register


@register("lever")
class LeverAdapter(Adapter):
    source = "lever"

    def fetch(self, company, known_ids=None, reuse=None):
        token = company["ats_id"]
        jobs = self.http.get_json(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
        out = []
        for p in jobs:
            cats = p.get("categories") or {}
            locs = " | ".join([cats.get("location") or ""] + (cats.get("allLocations") or []))
            if not (p.get("country") == "VN" or looks_vn(locs)):
                continue
            desc = (p.get("descriptionPlain") or "") + "\n" + "\n".join(
                (l.get("text") or "") + "\n" + html_to_text(l.get("content")) for l in p.get("lists") or [])
            created = p.get("createdAt")
            out.append({
                "source": "lever",
                "source_job_id": p["id"],
                "title": p.get("text"),
                "url": p.get("hostedUrl"),
                "location_raw": locs,
                "address_raw": cats.get("location"),
                "country_code": p.get("country") or "VN",
                "description": desc.strip(),
                "posted_at": dt.datetime.fromtimestamp(created / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z") if created else None,
                "employment_type_raw": cats.get("commitment"),
                "function_raw": cats.get("team") or cats.get("department"),
                "work_mode": {"remote": "remote", "hybrid": "hybrid", "on-site": "onsite"}.get(p.get("workplaceType")),
                "is_open": True,
            })
        return out
