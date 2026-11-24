"""Merge duplicates: same company + normalized title + city.

- across sources: posted <= 14 days apart
- same source (several requisitions for one role, e.g. 3x "Officer, Cash Management Operations"):
  only when the descriptions are near-identical, so different teams/roles stay separate.
  The kept job gets `openings` = number of postings merged into it."""
from __future__ import annotations

import datetime as dt
import re
from difflib import SequenceMatcher

from .text import norm_title

PRIORITY = {"workday": 0, "smartrecruiters": 1, "custom": 2, "greenhouse": 2, "lever": 2, "ashby": 2,
            "ybox": 3, "vietnamworks": 4, "topcv": 4}


def _date(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


SAME_DESC_RATIO = 0.9


def _words(j: dict) -> list[str]:
    return re.findall(r"\w+", (j.get("_desc") or "").lower())


def same_posting(a: dict, b: dict) -> bool:
    wa, wb = _words(a), _words(b)
    if len(wa) < 40 or len(wb) < 40:
        return False  # too little text to be sure
    sm = SequenceMatcher(None, wa, wb, autojunk=False)
    return sm.real_quick_ratio() >= SAME_DESC_RATIO and sm.quick_ratio() >= SAME_DESC_RATIO and sm.ratio() >= SAME_DESC_RATIO


def dedupe(jobs: list[dict]) -> tuple[list[dict], int]:
    groups: dict[tuple, list[dict]] = {}
    for j in jobs:
        groups.setdefault((j["company_id"], norm_title(j["title"]), j["city"]), []).append(j)
    out, merged = [], 0
    for _, g in groups.items():
        # stable choice of the kept card: best source, earliest posted, lowest id
        g.sort(key=lambda j: (PRIORITY.get(j["source"], 9), j.get("posted_at") or "", str(j.get("source_job_id") or j["id"])))
        clusters: list[list[dict]] = []
        for j in g:
            for c in clusters:
                a, b = _date(c[0].get("posted_at")), _date(j.get("posted_at"))
                same_source = c[0]["source"] == j["source"]
                if same_source:
                    if all(same_posting(x, j) for x in c if x["source"] == j["source"]):
                        c.append(j)  # same role posted several times (several openings)
                        break
                    continue  # different requisitions on the same ATS are different jobs
                if a is None or b is None or abs((a - b).days) <= 14:
                    c.append(j)
                    break
            else:
                clusters.append([j])
        for c in clusters:
            keep = c[0]
            n_same = sum(1 for o in c if o["source"] == keep["source"])
            if n_same > 1:
                keep["openings"] = n_same
            keep["_merged_ids"] = [o["id"] for o in c[1:]]
            for other in c[1:]:
                merged += 1
                if other["source"] == keep["source"]:
                    continue  # same ATS: nothing new to link or fill
                keep.setdefault("also_on", [])
                if other.get("url") and other["url"] not in keep["also_on"]:
                    keep["also_on"].append(other["url"])
                for k, v in other.items():  # fill only null fields (often salary)
                    if keep.get(k) in (None, [], "") and v not in (None, [], ""):
                        keep[k] = v
            out.append(keep)
    return out, merged
