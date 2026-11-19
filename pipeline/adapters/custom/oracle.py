"""Oracle Recruiting Cloud (Candidate Experience) public REST API.

1. keyword search "Vietnam" with the LOCATIONS facet -> find the facet id of Vietnam
2. list requisitions with selectedLocationsFacet=<id> (falls back to keyword results filtered by country)
3. detail per new requisition (recruitingCEJobRequisitionDetails)"""
from __future__ import annotations

from ...text import html_to_text
from ..base import Adapter, register

PAGE = 25


@register("oracle")
class OracleAdapter(Adapter):
    source = "custom"

    def _list(self, host, site, extra, offset=0):
        url = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        finder = f"findReqs;siteNumber={site},limit={PAGE},offset={offset},facetsList=LOCATIONS,{extra}"
        j = self.http.get_json(url, params={"onlyData": "true", "expand": "requisitionList.secondaryLocations", "finder": finder})
        return (j.get("items") or [{}])[0]

    def fetch(self, company, known_ids=None, reuse=None):
        host, site = company["oracle"]["host"], company["oracle"]["site"]
        first = self._list(host, site, 'keyword="Vietnam"')
        vn = next((f["Id"] for f in first.get("locationsFacet") or []
                   if (f.get("Name") or "").lower().replace(" ", "") == "vietnam"), None)
        reqs = []
        if vn:
            offset = 0
            while offset < 400:
                it = self._list(host, site, f"selectedLocationsFacet={vn}", offset)
                batch = it.get("requisitionList") or []
                reqs += batch
                offset += PAGE
                if len(batch) < PAGE or offset >= (it.get("TotalJobsCount") or 0):
                    break
        else:
            reqs = first.get("requisitionList") or []

        def is_vn(x):
            return x.get("PrimaryLocationCountry") == "VN" or any(
                (s.get("CountryCode") == "VN") for s in x.get("secondaryLocations") or [])

        out = []
        for x in reqs:
            if not is_vn(x):
                continue
            jid = str(x["Id"])
            url = f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{jid}"
            if known_ids and jid in known_ids and reuse:
                prev = reuse(jid)
                if prev:
                    out.append(dict(prev, is_open=True))
                    continue
            try:
                d = self.http.get_json(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails",
                                       params={"expand": "all", "onlyData": "true", "finder": f'ById;Id="{jid}",siteNumber={site}'})
                d = (d.get("items") or [{}])[0]
            except Exception:
                d = {}
            desc = "\n".join(html_to_text(d.get(k)) for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr") if d.get(k))
            out.append({
                "source": "custom",
                "source_job_id": jid,
                "title": x.get("Title"),
                "url": url,
                "location_raw": (x.get("PrimaryLocation") or "") + " Vietnam",
                "address_raw": x.get("PrimaryLocation"),
                "country_code": "VN",
                "description": desc,
                "posted_at": (x["PostedDate"] + "T00:00:00Z") if x.get("PostedDate") else None,
                "deadline": (d.get("ExternalPostedEndDate") or "")[:10] or None,
                "employment_type_raw": d.get("JobSchedule") or d.get("ContractType"),
                "function_raw": d.get("JobFunction") or x.get("JobFamily"),
                "work_mode": {"Hybrid": "hybrid", "Remote": "remote", "On-site": "onsite", "Onsite": "onsite"}.get(x.get("WorkplaceType") or ""),
                "is_open": True,
            })
        return out
