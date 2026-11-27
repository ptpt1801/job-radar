from pipeline import health

CFG = {"drop_pct_alert": 30, "schema_errors_pct_alert": 5}


def _h(comps):
    return {"sources": {}, "total_open": 1, "companies": comps, "schema_errors_pct": 0}


def test_rate_limited_companies_do_not_alert():
    comps = {"a": {"ok": False, "error": "HTTPError: 429 Too Many Requests"}, "b": {"ok": True}}
    assert health.alerts(_h(comps), [], CFG) == []


def test_real_failures_still_alert():
    comps = {"a": {"ok": False, "error": "HTTPError: 429"}, "b": {"ok": False, "error": "Timeout"}, "c": {"ok": True}}
    assert health.alerts(_h(comps), [], CFG) == ["1/2 companies failed to fetch (e.g. b)."]


def test_source_zero_from_rate_limit_does_not_alert():
    h = _h({"a": {"ok": False, "adapter": "workday", "error": "HTTPError: 429"}})
    h["sources"] = {"workday": {"jobs_found": 0}}
    assert health.alerts(h, [{"sources": {"workday": 800}, "total_open": 1}], CFG) == []


def test_source_zero_without_rate_limit_alerts():
    h = _h({"a": {"ok": True, "adapter": "workday"}})
    h["sources"] = {"workday": {"jobs_found": 0}}
    assert health.alerts(h, [{"sources": {"workday": 800}, "total_open": 1}], CFG) == ["Source `workday` returned 0 jobs (7-run average 800.0)."]
