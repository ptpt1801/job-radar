"""Eightfold AI career sites (PCS). Uses the public JSON endpoints the site itself calls and that
robots.txt explicitly allows (Allow: /api/pcsx):
  /api/pcsx/search?domain=<d>&query=&location=Vietnam&start=<n>
  /api/pcsx/position_details?position_id=<id>&domain=<d>&hl=en"""
from __future__ import annotations

import datetime as dt

from ...text import html_to_text, looks_vn
from ..base import Adapter, register


def _ts(v) -> str | None:
    try:
        return dt.datetime.fromtimestamp(int(v), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError):
        return None


def _vn_locs(p: dict) -> list[str]:
    std = p.get("standardizedLocations") or []
    locs = p.get("locations") or []
    vn = [l for l in locs if looks_vn(l)]
    if not vn and any(str(s).strip().endswith("VN") for s in std):
        vn = [s for s in std if str(s).strip().endswith("VN")]
    return vn


@register("eightfold")
class EightfoldAdapter(Adapter):
    source = "custom"

    def fetch(self, company, known_ids=None, reuse=None):
        host, domain = company["eightfold"]["host"], company["eightfold"]["domain"]
        root = f"https://{host}"
        positions, start = [], 0
        while start < 400:
            j = self.http.get_json(root + "/api/pcsx/search",
                                   params={"domain": domain, "query": "", "location": "Vietnam", "start": start})
            d = j.get("data") or {}
            batch = d.get("positions") or []
            positions += batch
            start += len(batch)
            if not batch or start >= (d.get("count") or 0):
                break

        out, seen = [], set()
        for p in positions:
            vn = _vn_locs(p)
            pid = str(p.get("id") or "")
            if not vn or not pid or pid in seen:
                continue
            seen.add(pid)
            url = root + (p.get("positionUrl") or f"/careers/job/{pid}")
            if known_ids and pid in known_ids and reuse:
                prev = reuse(pid)
                if prev:
                    out.append(dict(prev, is_open=True))
                    continue
            desc, extra = "", {}
            try:
                det = self.http.get_json(root + "/api/pcsx/position_details",
                                         params={"position_id": pid, "domain": domain, "hl": "en"})
                extra = det.get("data") or {}
                desc = html_to_text(extra.get("jobDescription"))
            except Exception:  # noqa: BLE001  detail is optional; keep the listing
                pass
            emp = extra.get("efcustomTextEmploymentType")
            out.append({
                "source": "custom",
                "source_job_id": pid,
                "title": p.get("name"),
                "url": extra.get("publicUrl") or url,
                "location_raw": " | ".join(vn),
                "country_code": "VN",
                "description": desc,
                "posted_at": _ts(p.get("postedTs") or p.get("creationTs")),
                "employment_type_raw": " ".join(emp) if isinstance(emp, list) else emp,
                "function_raw": p.get("department"),
                "work_mode": {"onsite": "onsite", "hybrid": "hybrid", "remote": "remote"}.get(str(p.get("workLocationOption") or "").lower()),
                "is_open": True,
            })
        return out
