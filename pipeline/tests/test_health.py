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
