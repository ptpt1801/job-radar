"""Jobs of a company whose source keeps failing are hidden after stale_days, not closed."""
import datetime as dt
import json

from pipeline import __main__ as M, store
from pipeline.adapters.base import REGISTRY, Adapter


class Boom(Adapter):
    def fetch(self, company, known_ids=None, reuse=None):
        raise RuntimeError("source unavailable")  # not "429": avoids the 90 s retry passes


def _job(jid, seen):
    return {"id": jid, "source": "workday", "source_job_id": f"acme:{jid}", "company_id": "acme", "company": "Acme",
            "title": "Planner", "url": "https://x.example/j", "city": "hanoi", "status": "open", "level": "experienced",
            "function": "supply_chain", "skills": [], "first_seen_at": seen, "last_seen_at": seen}


def test_failed_source_hides_only_stale_jobs(tmp_path, monkeypatch):
    now = dt.datetime.now(dt.timezone.utc)
    fresh = (now - dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - dt.timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.write_jobs([_job("a" * 12, fresh), _job("b" * 12, old)], fresh)
    monkeypatch.setitem(REGISTRY, "boom", Boom)
    monkeypatch.setattr(M, "companies", lambda: [{"id": "acme", "name": "Acme", "ats": "boom", "active": True}])
    monkeypatch.setattr(M, "export_taxonomy", lambda: None)
    monkeypatch.delenv("CV_PROFILE_JSON", raising=False)
    M.main(["--only-new", "--companies", "acme"])
    shown = {j["id"] for j in json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))["jobs"]}
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["pending"]
    assert shown == {"a" * 12}                       # fresh job still shown
    assert state["b" * 12]["stale"] is True           # stale job hidden but kept
    assert not json.loads((tmp_path / "archive.json").read_text(encoding="utf-8"))["jobs"]  # nothing closed


def test_run_with_patched_data_does_not_touch_real_cache(tmp_path, monkeypatch):
    real = store.cache_path()
    before = real.read_bytes() if real.exists() else None
    test_failed_source_hides_only_stale_jobs(tmp_path, monkeypatch)
    assert (tmp_path / "cache" / "descriptions.json.gz").exists()
    assert (real.read_bytes() if real.exists() else None) == before
