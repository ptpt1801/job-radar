"""Merge duplicates across sources: same company + normalized title + city, posted <= 14 days apart."""
from __future__ import annotations

import datetime as dt

from .text import norm_title

PRIORITY = {"workday": 0, "smartrecruiters": 1, "custom": 2, "greenhouse": 2, "lever": 2, "ashby": 2,
            "ybox": 3, "vietnamworks": 4, "topcv": 4}


def _date(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def dedupe(jobs: list[dict]) -> tuple[list[dict], int]:
    groups: dict[tuple, list[dict]] = {}
    for j in jobs:
        groups.setdefault((j["company_id"], norm_title(j["title"]), j["city"]), []).append(j)
    out, merged = [], 0
    for _, g in groups.items():
        g.sort(key=lambda j: (PRIORITY.get(j["source"], 9), j.get("posted_at") or ""))
        clusters: list[list[dict]] = []
        for j in g:
            for c in clusters:
                a, b = _date(c[0].get("posted_at")), _date(j.get("posted_at"))
                same_source = c[0]["source"] == j["source"]
                if same_source:
                    continue  # different requisitions on the same ATS are different jobs
                if a is None or b is None or abs((a - b).days) <= 14:
                    c.append(j)
                    break
            else:
                clusters.append([j])
        for c in clusters:
            keep = c[0]
            for other in c[1:]:
                merged += 1
                keep.setdefault("also_on", [])
                if other.get("url") and other["url"] not in keep["also_on"]:
                    keep["also_on"].append(other["url"])
                for k, v in other.items():  # fill only null fields (often salary)
                    if keep.get(k) in (None, [], "") and v not in (None, [], ""):
                        keep[k] = v
            out.append(keep)
    return out, merged
