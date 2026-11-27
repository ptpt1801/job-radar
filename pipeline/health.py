"""data/health.json + GitHub Issue alerts (0 tokens)."""
from __future__ import annotations

import datetime as dt
import os

import requests

ISSUE_LABEL = "health"


def stale_alert(meta: dict, now: dt.datetime, hours: int) -> str | None:
    last = meta.get("last_run_at")
    if not last:
        return None
    try:
        t = dt.datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return None
    age = (now - t).total_seconds() / 3600
    return f"Pipeline had not run for {age:.0f} hours (last run {last})." if age > hours else None


def alerts(health: dict, history: list[dict], cfg: dict) -> list[str]:
    out = []
    comps = health.get("companies", {})
    # HTTP 429 = rate limit (Workday blocks GitHub runner IPs); expected and covered by the owner-PC
    # run + stale hiding, so it does not count as a broken source.
    limited = {c for c, v in comps.items() if not v.get("ok") and "429" in str(v.get("error") or "")}
    by_adapter: dict[str, set] = {}
    for c, v in comps.items():
        by_adapter.setdefault(v.get("adapter"), set()).add(c)
    all_limited = {a for a, cs in by_adapter.items() if cs and cs <= limited}
    recent = history[-7:]
    if recent:
        for src, h in health["sources"].items():
            if src in all_limited:
                continue
            avg = sum(r.get("sources", {}).get(src, 0) for r in recent) / len(recent)
            if h["jobs_found"] == 0 and avg > 0:
                out.append(f"Source `{src}` returned 0 jobs (7-run average {avg:.1f}).")
        avg_total = sum(r.get("total_open", 0) for r in recent) / len(recent)
        if avg_total and health["total_open"] < avg_total * (1 - cfg["drop_pct_alert"] / 100):
            out.append(f"Open jobs dropped to {health['total_open']} (7-run average {avg_total:.0f}).")
    failed = [c for c, v in comps.items() if not v.get("ok") and c not in limited]
    base = len(comps) - len(limited)
    if base and len(failed) / base > 0.2:
        out.append(f"{len(failed)}/{base} companies failed to fetch (e.g. {', '.join(failed[:5])}).")
    if health["schema_errors_pct"] > cfg["schema_errors_pct_alert"]:
        out.append(f"Schema errors at {health['schema_errors_pct']}% of jobs.")
    return out


def open_or_update_issue(problems: list[str], run_url: str | None = None) -> str | None:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo and problems):
        return None
    title = "Job Radar health alert"
    body = "Automated check found:\n\n" + "\n".join(f"- {p}" for p in problems)
    if run_url:
        body += f"\n\nRun: {run_url}"
    body += "\n\nSee `data/health.json` for per-source details."
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}"
    try:
        r = requests.get(f"{api}/issues", params={"state": "open", "labels": ISSUE_LABEL}, headers=h, timeout=20)
        existing = next((i for i in r.json() if i.get("title") == title), None) if r.ok else None
        if existing:
            requests.patch(f"{api}/issues/{existing['number']}", json={"body": body}, headers=h, timeout=20)
            return f"updated #{existing['number']}"
        r = requests.post(f"{api}/issues", json={"title": title, "body": body, "labels": [ISSUE_LABEL]}, headers=h, timeout=20)
        return f"opened #{r.json().get('number')}" if r.ok else f"issue create failed {r.status_code}"
    except requests.RequestException as e:
        return f"issue error {e}"


def close_issue_if_healthy() -> str | None:
    """Close the open health issue after a full run with no problems."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return None
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}"
    try:
        r = requests.get(f"{api}/issues", params={"state": "open", "labels": ISSUE_LABEL}, headers=h, timeout=20)
        for i in (r.json() if r.ok else []):
            if i.get("title") == "Job Radar health alert":
                requests.post(f"{api}/issues/{i['number']}/comments", json={"body": "Full run healthy again; closing automatically."}, headers=h, timeout=20)
                requests.patch(f"{api}/issues/{i['number']}", json={"state": "closed"}, headers=h, timeout=20)
                return f"closed #{i['number']}"
    except requests.RequestException as e:
        return f"issue error {e}"
    return None
