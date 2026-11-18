"""Keep only: Vietnam, still open, not excluded (company / industry / per-company keywords)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from .config import exclusions
from .text import fold, kw_pattern, looks_vn

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def today_vn(now: dt.datetime | None = None) -> dt.date:
    now = now or dt.datetime.now(dt.timezone.utc)
    return now.astimezone(VN_TZ).date()


def excluded_company(name: str | None) -> bool:
    if not name:
        return False
    n = fold(name)
    for aliases in exclusions()["companies"]:
        pat = kw_pattern(aliases)
        if pat and pat.search(n):
            return True
    return False


def reason_to_drop(job: dict, company: dict, now: dt.datetime) -> str | None:
    cc = (job.get("_country_code") or "").upper()
    if cc and cc != "VN" and not looks_vn(job.get("_location_raw"), job.get("address_raw")):
        return "not_vietnam"
    if not cc and not looks_vn(job.get("_location_raw"), job.get("address_raw")):
        return "not_vietnam"
    if job.get("_is_open") is False:
        return "status_closed"
    if job.get("deadline"):
        try:
            if dt.date.fromisoformat(job["deadline"]) < today_vn(now):
                return "deadline_passed"
        except ValueError:
            job["deadline"] = None
    if (job.get("industry") or "") in set(exclusions()["industries"]):
        return "excluded_industry"
    if excluded_company(job.get("company")) or excluded_company(job.get("_company_name_raw")):
        return "excluded_company"
    kws = company.get("exclude_keywords")
    if kws:
        pat = kw_pattern(kws)
        if pat and pat.search(fold(job.get("title", "") + " " + (job.get("_desc") or ""))):
            return "excluded_keyword"
    return None
