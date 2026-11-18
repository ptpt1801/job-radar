"""SmartRecruiters official Posting API (public, documented)."""
from __future__ import annotations

from ..text import html_to_text
from .base import Adapter, register

API = "https://api.smartrecruiters.com/v1/companies/{cid}/postings"

LEVEL_MAP = {"internship": "internship", "entry_level": "graduate", "associate": "experienced",
             "mid_senior_level": "experienced", "director": "manager", "executive": "manager"}


@register("smartrecruiters")
class SmartRecruitersAdapter(Adapter):
    source = "smartrecruiters"

    def fetch(self, company, known_ids=None, reuse=None):
        cid = company["ats_id"]
        url = API.format(cid=cid)
        items, offset = [], 0
        while True:
            j = self.http.get_json(url, params={"country": "vn", "limit": 100, "offset": offset})
            batch = j.get("content") or []
            items += batch
            offset += 100
            if not batch or offset >= (j.get("totalFound") or 0) or offset >= 400:
                break
        out = []
        for p in items:
            pid = str(p["id"])
            loc = p.get("location") or {}
            base = {
                "source": "smartrecruiters",
                "source_job_id": pid,
                "title": p.get("name"),
                "url": f"https://jobs.smartrecruiters.com/{cid}/{pid}",
                "company_name_raw": (p.get("company") or {}).get("name"),
                "location_raw": loc.get("fullLocation") or loc.get("city"),
                "city_raw": loc.get("city"),
                "address_raw": ", ".join(x for x in [loc.get("address"), loc.get("city")] if x) or None,
                "country_code": (loc.get("country") or "").upper() or None,
                "posted_at": p.get("releasedDate"),
                "employment_type_raw": (p.get("typeOfEmployment") or {}).get("label"),
                "level_raw": LEVEL_MAP.get((p.get("experienceLevel") or {}).get("id")),
                "function_raw": (p.get("function") or {}).get("label"),
                "work_mode": "remote" if loc.get("remote") else ("hybrid" if loc.get("hybrid") else "onsite"),
                "is_open": True,
            }
            if known_ids and pid in known_ids and reuse:
                prev = reuse(pid)
                if prev:
                    out.append(dict(prev, is_open=True))
                    continue
            try:
                d = self.http.get_json(f"{url}/{pid}")
            except Exception:
                d = {}
            if d:
                base["url"] = d.get("postingUrl") or base["url"]
                base["is_open"] = d.get("active", True) is not False
                secs = (d.get("jobAd") or {}).get("sections") or {}
                parts = []
                for key in ("jobDescription", "qualifications", "additionalInformation"):
                    s = secs.get(key) or {}
                    if s.get("text"):
                        parts.append((s.get("title") or key) + "\n" + html_to_text(s["text"]))
                base["description"] = "\n".join(parts)
                base["lang_hint"] = ((d.get("language") or {}).get("code") or "")[:2] or None
            out.append(base)
        return out
