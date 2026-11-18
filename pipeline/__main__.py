"""python -m pipeline [--only-new | --rescore-all | --dry-run] [--limit-companies N] [--companies a,b]"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import time
from collections import defaultdict
from urllib.parse import urlparse

from . import dedupe, enrich_rules, filter as jfilter, health, score, stats, store
from .adapters import REGISTRY, adapter_for
from .config import companies, settings, taxonomy
from .http import client
from .normalize import normalize
from .text import scrub
from .config import CONFIG
import hashlib

RULES_VERSION = "2026-11-18.2"   # bump when enrich_rules logic changes -> re-enrich from cache


def rules_hash() -> str:
    h = hashlib.sha1(RULES_VERSION.encode())
    h.update((CONFIG / "taxonomy.yaml").read_bytes())
    return h.hexdigest()[:12]
from .validate import errors as schema_errors

CLOSED_PHRASES = ("no longer available", "no longer accepting", "position has been filled", "job is closed",
                  "không còn nhận hồ sơ", "đã hết hạn", "this job has expired")


def iso(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def next_run(now: dt.datetime) -> dt.datetime:
    n = now.replace(hour=19, minute=0, second=0, microsecond=0)
    return n if n > now else n + dt.timedelta(days=1)


def export_taxonomy():
    t = taxonomy()
    out = {}
    for sec in ("levels", "functions", "industries", "cities", "regions", "work_modes", "sources",
                "languages", "skills", "countries", "benefits_common"):
        out[sec] = {k: {"vi": v["vi"], "en": v["en"]} for k, v in (t.get(sec) or {}).items()}
    store.write_site_json("i18n/taxonomy.json", out)


def fetch_company(c: dict, prev_by_raw: dict) -> tuple[dict, list[dict], dict]:
    key = adapter_for(c)
    cls = REGISTRY.get(key)
    t0 = time.time()
    rep = {"ok": False, "adapter": key, "jobs_found": 0, "error": None}
    if not cls:
        rep["error"] = f"no adapter '{key}'"
        return c, [], rep
    known = prev_by_raw.get(c["id"], {})
    try:
        raws = cls().fetch(c, known_ids=set(known), reuse=known.get)
        rep.update(ok=True, jobs_found=len(raws))
    except Exception as e:  # one company must never stop the pipeline
        raws = []
        rep["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    rep["duration_s"] = round(time.time() - t0, 1)
    return c, raws, rep


def weekly_url_check(jobs: list[dict]) -> set[str]:
    http = client()
    closed = set()

    def chk(j):
        try:
            r = http.get(j["url"], allow_redirects=True)
            if r.status_code in (404, 410):
                return j["id"]
            if r.ok and any(p in r.text[:200000].lower() for p in CLOSED_PHRASES):
                return j["id"]
        except Exception:
            return None
        return None

    by_host = defaultdict(list)
    for j in jobs:
        by_host[urlparse(j["url"]).hostname].append(j)
    with cf.ThreadPoolExecutor(8) as ex:
        for res in ex.map(chk, jobs):
            if res:
                closed.add(res)
    return closed


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline")
    ap.add_argument("--only-new", action="store_true", help="reuse stored details for known jobs (daily default)")
    ap.add_argument("--rescore-all", action="store_true", help="only recompute match scores")
    ap.add_argument("--dry-run", action="store_true", help="fetch + process, print stats, write nothing")
    ap.add_argument("--limit-companies", type=int)
    ap.add_argument("--companies", help="comma-separated company ids")
    ap.add_argument("--check-urls", action="store_true", help="force the weekly URL check")
    ap.add_argument("--reenrich", action="store_true", help="re-apply extraction rules to stored jobs from the cache")
    a = ap.parse_args(argv)

    cfg = settings()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    db = store.load()
    profile = score.load_profile()
    show_tags = bool(cfg.get("SHOW_SKILL_TAGS", True))
    problems = []
    if (s := health.stale_alert(db["meta"], now, cfg["health"]["stale_hours_alert"])):
        problems.append(s)

    if a.rescore_all:
        jobs = db["jobs"]
        score.apply(jobs, profile, show_tags)
        meta = dict(db["meta"], cv_version=(profile or {}).get("cv_version"), rescored_at=iso(now),
                    has_profile=bool(profile))
        if not a.dry_run:
            store.write_jobs(jobs, iso(now), cfg["details_split_mb"])
            store.write("meta.json", meta)
            store.write("stats.json", stats.build(jobs, db["archive"], now))
        print(f"rescored {len(jobs)} jobs; profile={'yes' if profile else 'no'}")
        return 0

    cos = [c for c in companies() if c.get("active")]
    if a.companies:
        want = set(a.companies.split(","))
        cos = [c for c in cos if c["id"] in want]
    if a.limit_companies:
        cos = cos[: a.limit_companies]
    if cfg.get("ybox", {}).get("enabled") and not (a.companies and "ybox" not in a.companies.split(",")) and not a.limit_companies:
        cos.append({"id": "ybox", "name": "Ybox.vn", "ats": "ybox", "active": True, "pages": cfg["ybox"].get("pages", 8)})
    all_cos = {c["id"]: c for c in companies()}

    prev_open = {j["id"]: j for j in db["jobs"]}
    pending = db["state"].get("pending", {})
    prev_all = dict(prev_open)
    prev_all.update({k: v["job"] for k, v in pending.items()})
    prev_by_raw: dict[str, dict] = defaultdict(dict)
    if a.only_new:
        for j in prev_all.values():
            prev_by_raw[j["company_id"]][j["source_job_id"].split(":", 1)[1]] = j

    desc_cache = store.load_desc()
    rh = rules_hash()
    reenrich = a.reenrich or db["meta"].get("rules_hash") != rh
    reports, collected, drops = {}, [], defaultdict(int)
    by_company = {c["id"]: c for c in cos}
    with cf.ThreadPoolExecutor(cfg["limits"]["max_workers"]) as ex:
        for c, raws, rep in ex.map(lambda c: fetch_company(c, prev_by_raw), cos):
            reports[c["id"]] = rep
            kept = 0
            for raw in raws[: cfg["limits"]["max_jobs_per_company"]]:
                if "first_seen_at" in raw:                       # reused stored job
                    j = {k: v for k, v in raw.items() if k != "is_open"}
                    j["last_seen_at"] = iso(now)
                    if raw.get("is_open") is False:
                        drops["status_closed"] += 1
                        continue
                    if j.get("deadline") and j["deadline"] < jfilter.today_vn(now).isoformat():
                        drops["deadline_passed"] += 1
                        continue
                    j["_reused"] = True
                    hint = desc_cache.get(j["id"])
                    if reenrich and hint:
                        j.update(_desc=hint.get("d") or "", _level_raw=hint.get("lv"), _function_raw=hint.get("fn"), _salary=hint.get("sal"))
                        enrich_rules.enrich(j)
                else:
                    cc = all_cos.get(raw.get("company_id_override"), c)
                    j = normalize(raw, cc, now)
                    why = jfilter.reason_to_drop(j, cc, now)
                    if why:
                        drops[why] += 1
                        continue
                    enrich_rules.enrich(j)
                    desc_cache[j["id"]] = {"d": (scrub(j["_desc"]) or "")[:8000], "lv": j.get("_level_raw"),
                                           "fn": j.get("_function_raw"), "sal": j.get("_salary")}
                    old = prev_all.get(j["id"])
                    if old:
                        j["first_seen_at"] = old["first_seen_at"]
                kept += 1
                collected.append(j)
            rep["jobs_kept"] = kept
            print(f"  {c['id']:<22} {rep['adapter']:<16} {'ok ' if rep['ok'] else 'ERR'} found={rep['jobs_found']:<4} kept={kept:<4} {rep['duration_s']}s {rep['error'] or ''}", flush=True)

    if cfg.get("EXTRACTOR") == "claude" and os.environ.get("ANTHROPIC_API_KEY"):
        from . import enrich_claude
        llm = enrich_claude.run([j for j in collected if not j.get("_reused")], cfg)
    else:
        llm = {"mode": "rules", "jobs": 0, "input_tokens": 0, "output_tokens": 0, "est_cost_usd": 0}

    jobs, merged = dedupe.dedupe(collected)
    seen = {j["id"] for j in jobs}

    # carry over jobs of companies whose fetch failed (do not count them as missing)
    failed = {cid for cid, r in reports.items() if not r["ok"]}
    scanned_ok = {cid for cid, r in reports.items() if r["ok"]}
    sk = lambda j: "ybox" if j.get("source") == "ybox" else j["company_id"]
    for j in prev_open.values():
        if sk(j) in failed and j["id"] not in seen:
            jobs.append(j); seen.add(j["id"])

    # closing logic
    new_pending, closed_now = {}, []
    miss_limit = cfg["closing"]["missing_runs_to_close"]
    for jid, j in prev_all.items():
        if jid in seen:
            continue
        if sk(j) not in scanned_ok and sk(j) in by_company:
            if jid in pending:
                new_pending[jid] = pending[jid]
            continue
        if (a.companies or a.limit_companies) and sk(j) not in by_company:
            if jid in prev_open:
                jobs.append(j); seen.add(jid)
            elif jid in pending:
                new_pending[jid] = pending[jid]
            continue
        if j.get("source") == "ybox" and sk(j) in scanned_ok:
            # Ybox lists only its ~50 newest posts; older ones scroll off without closing.
            # Keep them until the deadline passes (weekly URL check catches removals).
            if not j.get("deadline") or j["deadline"] >= jfilter.today_vn(now).isoformat():
                jobs.append(j); seen.add(jid)
                continue
        runs = pending.get(jid, {}).get("missing_runs", 0) + 1
        if runs >= miss_limit:
            closed_now.append(dict(j, status="closed", closed_at=iso(now)))
        else:
            new_pending[jid] = {"job": j, "missing_runs": runs}

    # weekly URL check (Sunday, Vietnam time)
    if a.check_urls or (jfilter.today_vn(now).weekday() == cfg["closing"]["weekly_url_check_weekday"] and not a.dry_run):
        dead = weekly_url_check(jobs)
        for j in [j for j in jobs if j["id"] in dead]:
            closed_now.append(dict(j, status="closed", closed_at=iso(now)))
        jobs = [j for j in jobs if j["id"] not in dead]

    score.apply(jobs, profile, show_tags)
    published, bad = [], 0
    for j in jobs:
        cj = store.clean(j)
        errs = schema_errors(cj)
        if errs:
            bad += 1
            print("  schema:", cj.get("id"), errs[:2], file=sys.stderr)
            continue
        published.append(cj)

    new_ids = [j["id"] for j in published if j["id"] not in prev_all]
    archive_cut = iso(now - dt.timedelta(days=cfg["closing"]["archive_days"]))
    archive = [store.clean(x) for x in closed_now] + [x for x in db["archive"] if (x.get("closed_at") or "") >= archive_cut]
    archive = list({x["id"]: x for x in archive}.values())

    # health
    http_stats = client().stats
    src = defaultdict(lambda: {"ok": True, "jobs_found": 0, "jobs_kept": 0, "http_errors": 0, "duration_s": 0.0, "companies": 0})
    comp_health = {}
    for cid, r in reports.items():
        c = by_company[cid]
        s = src[c["ats"] if c["ats"] != "custom" else "custom"]
        s["companies"] += 1
        s["jobs_found"] += r["jobs_found"]
        s["jobs_kept"] += r.get("jobs_kept", 0)
        s["duration_s"] = round(s["duration_s"] + r["duration_s"], 1)
        s["ok"] = s["ok"] and r["ok"]
        comp_health[cid] = {k: r.get(k) for k in ("ok", "adapter", "jobs_found", "jobs_kept", "duration_s", "error")}
    health_doc = {
        "run_at": iso(now),
        "total_open": len(published),
        "new": len(new_ids),
        "closed": len(closed_now),
        "pending_missing": len(new_pending),
        "merged_duplicates": merged,
        "dropped": dict(drops),
        "schema_errors_pct": round(100 * bad / max(1, len(jobs)), 2),
        "llm_tokens": {"input": llm["input_tokens"], "output": llm["output_tokens"], "est_cost_usd": llm["est_cost_usd"], "mode": llm["mode"]},
        "sources": dict(src),
        "companies": comp_health,
        "hosts": {h: dict(v) for h, v in http_stats.items()},
        "ybox_rejected": [],
    }
    if "ybox" in REGISTRY:
        from .adapters import ybox as ybox_mod
        health_doc["ybox_rejected"] = getattr(ybox_mod, "LAST_REJECTED", [])
    problems += health.alerts(health_doc, db["health_history"], cfg["health"])
    health_doc["alerts"] = problems

    meta = {
        "last_run_at": iso(now),
        "next_run_at": iso(next_run(now)),
        "cv_version": (profile or {}).get("cv_version"),
        "has_profile": bool(profile),
        "extractor": llm["mode"],
        "show_skill_tags": show_tags,
        "total_open": len(published),
        "companies_active": len(cos),
        "companies_with_jobs": len({j["company_id"] for j in published}),
        "last_run": {"new": len(new_ids), "closed": len(closed_now)},
        "rules_hash": rh,
    }

    print(f"\nopen={len(published)} new={len(new_ids)} closed={len(closed_now)} pending={len(new_pending)} "
          f"merged={merged} schema_bad={bad} dropped={dict(drops)}")
    print("by source:", dict(src and {k: v['jobs_kept'] for k, v in src.items()}))
    if problems:
        print("alerts:", problems)
    if a.dry_run:
        return 0

    store.write_jobs(published, iso(now), cfg["details_split_mb"])
    store.write("archive.json", {"generated_at": iso(now), "jobs": archive}, compact=True)
    store.write("state.json", {"pending": new_pending})
    keep_ids = {j["id"] for j in published} | set(new_pending)
    store.save_desc({k: v for k, v in desc_cache.items() if k in keep_ids})
    store.write("meta.json", meta)
    store.write("stats.json", stats.build(published, archive, now))
    store.write("health.json", health_doc)
    hist = db["health_history"] + [{"run_at": iso(now), "total_open": len(published),
                                    "sources": {k: v["jobs_found"] for k, v in src.items()}}]
    store.write("health_history.json", hist[-30:])
    export_taxonomy()
    if problems and os.environ.get("GITHUB_ACTIONS"):
        run_url = f"{os.environ.get('GITHUB_SERVER_URL')}/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ.get('GITHUB_RUN_ID')}"
        print("issue:", health.open_or_update_issue(problems, run_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
