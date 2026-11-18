"""Workday CXS public JSON API (POST list, GET detail)."""
from __future__ import annotations

from ..text import html_to_text
from .base import Adapter, looks_vn, register

VN_COUNTRY_ID = "db69e8c8446c11de98360015c5e6daf6"  # Workday global ID for Vietnam
PAGE = 20


def _walk(facets, param=None):
    for f in facets or []:
        p = f.get("facetParameter", param)
        for v in f.get("values") or []:
            if "values" in v:
                yield from _walk([v], p)
            else:
                yield p, v


def vn_facets(facets) -> dict:
    """Prefer a country facet with the VN id; otherwise collect VN-looking location values."""
    country, locs = {}, {}
    for p, v in _walk(facets):
        if v.get("id") == VN_COUNTRY_ID:
            country.setdefault(p, []).append(v["id"])
        elif looks_vn(v.get("descriptor")) and p and "location" in p.lower():
            locs.setdefault(p, []).append(v["id"])
    if country:
        k = next(iter(country))
        return {k: country[k]}
    if locs:  # use the most specific single parameter to avoid AND-ing facets
        k = max(locs, key=lambda x: len(locs[x]))
        return {k: locs[k]}
    return {}


@register("workday")
class WorkdayAdapter(Adapter):
    source = "workday"

    def fetch(self, company, known_ids=None, reuse=None):
        w = company["workday"]
        base = f"https://{w['tenant']}.{w['wd']}.myworkdayjobs.com"
        api = f"{base}/wday/cxs/{w['tenant']}/{w['site']}"
        body = {"appliedFacets": {}, "limit": PAGE, "offset": 0, "searchText": ""}
        first = self.http.post_json(f"{api}/jobs", json=body, headers={"Accept": "application/json"})
        applied = vn_facets(first.get("facets"))
        if not applied:
            return []
        postings, offset, total = [], 0, None
        while True:
            body = {"appliedFacets": applied, "limit": PAGE, "offset": offset, "searchText": ""}
            j = self.http.post_json(f"{api}/jobs", json=body, headers={"Accept": "application/json"})
            if total is None:
                total = j.get("total") or 0
            batch = j.get("jobPostings") or []
            postings += batch
            offset += PAGE
            if not batch or offset >= total or offset >= 400:
                break
        out = []
        for p in postings:
            path = p.get("externalPath")
            if not path:
                continue
            jid = (p.get("bulletFields") or [path.rsplit("_", 1)[-1]])[0]
            url = f"{base}/{w['site']}{path}"
            if known_ids and jid in known_ids and reuse:
                prev = reuse(jid)
                if prev:
                    prev = dict(prev)
                    prev.update(posted_text=p.get("postedOn"), is_open=True)
                    out.append(prev)
                    continue
            try:
                d = self.http.get_json(f"{api}/job{path.removeprefix('/job')}", headers={"Accept": "application/json"})
            except Exception:
                d = {}
            info = d.get("jobPostingInfo") or {}
            loc = info.get("jobRequisitionLocation") or {}
            cc = ((loc.get("country") or {}).get("alpha2Code")) or None
            addl = info.get("additionalLocations") or []
            out.append({
                "source": "workday",
                "source_job_id": str(info.get("jobReqId") or jid),
                "title": info.get("title") or p.get("title"),
                "url": info.get("externalUrl") or url,
                "location_raw": " | ".join([info.get("location") or p.get("locationsText") or ""] + addl),
                "address_raw": loc.get("descriptor") or info.get("location") or p.get("locationsText"),
                "country_code": cc,
                "description": html_to_text(info.get("jobDescription")),
                "posted_at": (info.get("startDate") + "T00:00:00Z") if info.get("startDate") else None,
                "posted_text": p.get("postedOn") or info.get("postedOn"),
                "deadline": (info.get("endDate") or None),
                "employment_type_raw": info.get("timeType") or p.get("timeType"),
                "remote_raw": info.get("remoteType"),
                "is_open": bool(info.get("posted", True)) if info else True,
            })
        return out
