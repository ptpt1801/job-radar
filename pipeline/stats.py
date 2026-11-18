"""Aggregates for the market dashboard (data/stats.json)."""
from __future__ import annotations

import datetime as dt
from collections import Counter


def _week(s: str | None) -> str | None:
    if not s:
        return None
    try:
        d = dt.date.fromisoformat(s[:10])
    except ValueError:
        return None
    monday = d - dt.timedelta(days=d.weekday())
    return monday.isoformat()


def build(jobs: list[dict], archive: list[dict], now: dt.datetime) -> dict:
    c = lambda key: dict(Counter(j.get(key) for j in jobs if j.get(key)).most_common())
    skills = Counter(s for j in jobs for s in j.get("skills") or [])
    weeks = Counter(w for j in jobs + archive if (w := _week(j.get("posted_at"))))
    cutoff = (now - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    matches = [j["match"] for j in jobs if j.get("match") is not None]
    heat = Counter((j.get("function"), j.get("level")) for j in jobs)
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_open": len(jobs),
        "new_7d": sum(1 for j in jobs if (j.get("posted_at") or j["first_seen_at"]) >= cutoff),
        "with_salary_pct": round(100 * sum(1 for j in jobs if j.get("salary")) / len(jobs), 1) if jobs else 0,
        "match_ge70": sum(1 for m in matches if m >= 70) if matches else None,
        "companies": len({j["company_id"] for j in jobs}),
        "by_source": c("source"),
        "by_city": c("city"),
        "by_level": c("level"),
        "by_function": c("function"),
        "by_industry": c("industry"),
        "by_hq_country": c("hq_country"),
        "by_company": c("company"),
        "top_skills": dict(skills.most_common(15)),
        "weekly_new": dict(sorted(weeks.items())[-26:]),
        "match_hist": dict(sorted(Counter(min(9, m // 10) * 10 for m in matches).items())) if matches else {},
        "heatmap": [{"function": f, "level": l, "n": n} for (f, l), n in heat.items()],
    }
