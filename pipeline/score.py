"""Deterministic match score from the skill profile in CV_PROFILE_JSON (never the CV itself)."""
from __future__ import annotations

import json
import os

LEVELS = ["internship", "graduate", "experienced", "manager"]


def load_profile() -> dict | None:
    raw = os.environ.get("CV_PROFILE_JSON")
    if not raw or not raw.strip():
        return None
    try:
        p = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return p if isinstance(p, dict) and p.get("skills") is not None else None


def score(job: dict, profile: dict | None) -> tuple[int | None, list[str], list[str]]:
    if not profile:
        return None, [], []
    req = list(dict.fromkeys(job.get("skills") or []))
    mine = set(profile.get("skills") or [])
    have = [s for s in req if s in mine]
    missing = [s for s in req if s not in mine]
    skill = 50 * len(have) / len(req) if req else 25

    targets = [t for t in (profile.get("target_levels") or []) if t in LEVELS]
    lvl = job.get("level")
    dist = min((abs(LEVELS.index(lvl) - LEVELS.index(t)) for t in targets), default=99) if lvl in LEVELS else 99
    level = 22 if dist == 0 else (12 if dist == 1 else 0)

    funcs = profile.get("target_functions") or []
    fn = job.get("function")
    func = 18 if funcs and fn == funcs[0] else (12 if fn in funcs[1:] else 0)

    city = 10 if (job.get("city") in (profile.get("target_cities") or []) or job.get("work_mode") == "remote") else 2
    return min(99, round(skill + level + func + city)), have, missing


def apply(jobs: list[dict], profile: dict | None, show_tags: bool) -> None:
    for j in jobs:
        m, have, missing = score(j, profile)
        j["match"] = m
        if show_tags and profile:
            j["have"], j["missing"] = have, missing
        else:
            j.pop("have", None)
            j.pop("missing", None)
