"""Read/write data/*.json."""
from __future__ import annotations

import json
from pathlib import Path

from .config import DATA

TRANSIENT_PREFIX = "_"
SCHEMA_KEYS = None


def _read(name: str, default):
    p = DATA / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write(name: str, obj, compact: bool = False):
    p = DATA / name
    p.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(obj, ensure_ascii=False, indent=1)
    p.write_text(txt + "\n", encoding="utf-8")
    return p


def load():
    return {
        "jobs": _read("jobs.json", {}).get("jobs", []),
        "archive": _read("archive.json", {}).get("jobs", []),
        "meta": _read("meta.json", {}),
        "state": _read("state.json", {"pending": {}}),
        "health_history": _read("health_history.json", []),
    }


def clean(job: dict) -> dict:
    """Drop transient '_' fields and keys outside the schema."""
    from .validate import allowed_keys
    from .text import scrub
    keys = allowed_keys()
    out = {k: v for k, v in job.items() if not k.startswith(TRANSIENT_PREFIX) and k in keys}
    for k in ("title", "address_raw", "description_excerpt", "posted_text"):
        if isinstance(out.get(k), str):
            out[k] = scrub(out[k])
    if out.get("benefits"):
        out["benefits"] = [scrub(b) for b in out["benefits"]]
    return out


def write_jobs(jobs: list[dict], generated_at: str, split_mb: float = 2.0):
    jobs = sorted(jobs, key=lambda j: (j.get("posted_at") or "", j["id"]), reverse=True)
    payload = {"generated_at": generated_at, "count": len(jobs), "jobs": jobs}
    size = len(json.dumps(payload, ensure_ascii=False).encode())
    details_dir = DATA / "details"
    if size > split_mb * 1024 * 1024:
        details_dir.mkdir(exist_ok=True)
        slim = []
        for j in jobs:
            d = {k: j.get(k) for k in ("description_excerpt", "benefits") if j.get(k)}
            (details_dir / f"{j['id']}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            s = dict(j); s.pop("description_excerpt", None); s.pop("benefits", None); s["has_details"] = True
            slim.append(s)
        payload["jobs"] = slim
        payload["details_split"] = True
    _write("jobs.json", payload, compact=True)


def write(name: str, obj, compact=False):
    return _write(name, obj, compact)


def write_site_json(rel: str, obj):
    from .config import SITE
    p = SITE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---- description cache (scrubbed text + raw hints) so rules can be re-applied without refetching ----
import gzip  # noqa: E402

CACHE = DATA / "cache" / "descriptions.json.gz"


def load_desc() -> dict:
    if not CACHE.exists():
        return {}
    try:
        with gzip.open(CACHE, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_desc(cache: dict):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(CACHE, "wb", mtime=0) as g:
        g.write(json.dumps(cache, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
