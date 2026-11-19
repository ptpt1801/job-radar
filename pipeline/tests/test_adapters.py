"""Adapter tests against real (anonymised) responses saved in fixtures/. No network."""
import json
from pathlib import Path

from pipeline.adapters.custom.avature import AvatureAdapter
from pipeline.adapters.custom.jibe import JibeAdapter
from pipeline.adapters.greenhouse import GreenhouseAdapter
from pipeline.adapters.smartrecruiters import SmartRecruitersAdapter
from pipeline.adapters.workday import WorkdayAdapter, vn_facets
from pipeline.adapters import ybox

F = Path(__file__).parent / "fixtures"


def fx(name):
    p = F / name
    return json.loads(p.read_text(encoding="utf-8")) if p.suffix == ".json" else p.read_text(encoding="utf-8")


class Resp:
    def __init__(self, body, status=200):
        self.status_code, self._b = status, body
        self.text = body if isinstance(body, str) else json.dumps(body)
        self.ok = status < 400

    def json(self):
        return self._b if not isinstance(self._b, str) else json.loads(self._b)


class FakeHttp:
    """Routes (method, url-substring) -> fixture."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _find(self, method, url, kw):
        self.calls.append((method, url, kw))
        for (m, frag), body in self.routes:
            if m == method and frag(url, kw) if callable(frag) else (m == method and frag in url):
                return Resp(body() if callable(body) else body)
        return Resp({}, 404)

    def get(self, url, **kw): return self._find("GET", url, kw)
    def post(self, url, **kw): return self._find("POST", url, kw)
    def get_json(self, url, **kw): return self.get(url, **kw).json()
    def post_json(self, url, **kw): return self.post(url, **kw).json()


def test_workday_facets_and_fetch():
    first, lst, det = fx("workday_first.json"), fx("workday_list.json"), fx("workday_detail.json")
    fac = vn_facets(first["facets"])
    assert fac and all(fac.values())
    http = FakeHttp([
        (("POST", lambda u, kw: u.endswith("/jobs") and not kw["json"]["appliedFacets"]), first),
        (("POST", lambda u, kw: u.endswith("/jobs") and kw["json"]["appliedFacets"]), lst),
        (("GET", lambda u, kw: "/job/" in u), det),
    ])
    co = {"id": "nike", "workday": {"tenant": "nike", "wd": "wd1", "site": "nke"}}
    jobs = WorkdayAdapter(http).fetch(co)
    assert len(jobs) == 2
    j = jobs[0]
    assert j["source"] == "workday" and j["title"] and j["url"].startswith("https://nike.wd1.myworkdayjobs.com/nke/")
    assert j["country_code"] == "VN" and j["description"]
    assert all(c[0] == "POST" for c in http.calls if c[1].endswith("/jobs"))  # list must be POST


def test_workday_reuses_known_jobs_without_detail_call():
    first, lst = fx("workday_first.json"), fx("workday_list.json")
    http = FakeHttp([
        (("POST", lambda u, kw: u.endswith("/jobs") and not kw["json"]["appliedFacets"]), first),
        (("POST", lambda u, kw: u.endswith("/jobs") and kw["json"]["appliedFacets"]), lst),
    ])
    ids = {p["bulletFields"][0] for p in lst["jobPostings"]}
    prev = {i: {"id": "x" * 12, "first_seen_at": "2026-11-01T00:00:00Z"} for i in ids}
    jobs = WorkdayAdapter(http).fetch({"id": "nike", "workday": {"tenant": "nike", "wd": "wd1", "site": "nke"}},
                                      known_ids=set(ids), reuse=prev.get)
    assert len(jobs) == 2 and not [c for c in http.calls if c[0] == "GET"]


def test_smartrecruiters():
    lst, det = fx("sr_list.json"), fx("sr_detail.json")
    http = FakeHttp([(("GET", lambda u, kw: u.endswith("/postings")), lst), (("GET", lambda u, kw: "/postings/" in u), det)])
    jobs = SmartRecruitersAdapter(http).fetch({"id": "endava", "ats_id": "Endava"})
    assert len(jobs) == len(lst["content"]) >= 1
    assert jobs[0]["country_code"] == "VN" and jobs[0]["url"].startswith("https://jobs.smartrecruiters.com/")
    assert jobs[0]["description"]


def test_greenhouse_filters_vietnam():
    http = FakeHttp([(("GET", lambda u, kw: "boards-api.greenhouse.io" in u), fx("greenhouse.json"))])
    jobs = GreenhouseAdapter(http).fetch({"id": "flexport", "ats_id": "flexport"})
    assert len(jobs) == 2 and all(j["country_code"] == "VN" for j in jobs)


def test_jibe_keeps_only_vn():
    http = FakeHttp([(("GET", lambda u, kw: "/api/jobs" in u), fx("jibe_jobs.json"))])
    jobs = JibeAdapter(http).fetch({"id": "schneider_electric", "career_url": "https://careers.se.com"})
    raw = fx("jibe_jobs.json")["jobs"]
    assert len(jobs) == sum(1 for x in raw if x["data"]["country_code"] == "VN")
    assert all(j["url"].startswith("https://careers.se.com/jobs/") for j in jobs)
    assert jobs[0]["posted_at"].endswith("T00:00:00Z")


def test_avature_list_and_detail():
    from pipeline.adapters.custom.avature import parse_detail, parse_list
    items = parse_list(fx("avature_list.html"))
    assert len(items) >= 5 and all(i["id"].isdigit() for i in items)
    d = parse_detail(fx("avature_detail.html"))
    assert d["fields"]["Job ID"] and "Vietnam" in d["fields"]["Location(s)"]

    http = FakeHttp([(("GET", lambda u, kw: "SearchJobs" in u and kw["params"]["folderOffset"] == 0), fx("avature_list.html")),
                     (("GET", lambda u, kw: "JobDetail" in u), fx("avature_detail.html"))])
    jobs = AvatureAdapter(http).fetch({"id": "siemens", "career_url": "https://jobs.siemens.com/en_US/externaljobs"})
    assert jobs and all(j["country_code"] == "VN" for j in jobs)


def test_ybox_listing_and_detail_parse():
    items = ybox.parse_list(fx("ybox_list.html"))
    assert len(items) >= 30
    ld = ybox.parse_detail(fx("ybox_detail.html"))
    assert ld.get("@type") == "JobPosting" and ld.get("validThrough")
    p = ybox.parse_title(items[0]["title"])
    assert p["employer"] and p["role"]


def test_successfactors_table_and_tile_layouts():
    from pipeline.adapters.custom.successfactors import parse_detail, parse_list
    table = ('<span class="paginationLabel">Showing 1 to 1 of 1 Jobs</span><table><tr class="data-row">'
             '<td><a class="jobTitle-link" href="/job/Ha-Noi-Auditor/111/">Auditor</a></td>'
             '<td><span class="jobLocation">Ha Noi, VN</span></td></tr></table>')
    rows, total = parse_list(table, "https://careers.example.com")
    assert total == 1 and rows[0]["id"] == "111" and rows[0]["title"] == "Auditor" and "VN" in rows[0]["location"]
    tile = ('<ul><li class="job-tile" data-url="/job/Bien-Hoa-Engineer-810000/222/"><div class="tiletitle">'
            '<span class="sr-only">Title</span><a href="/job/Bien-Hoa-Engineer-810000/222/">Engineer</a></div></li></ul>')
    rows, _ = parse_list(tile, "https://jobs.example.com")
    assert rows[0]["id"] == "222" and rows[0]["title"] == "Engineer" and rows[0]["url"].startswith("https://jobs.example.com/job/")
    d = parse_detail('<meta itemprop="datePosted" content="Fri Oct 30 02:00:00 UTC 2026"><span class="jobGeoLocation">Bien Hoa, VN, 810000</span>'
                     '<span itemprop="description"><p>Quality role</p></span>')
    assert d["location"].startswith("Bien Hoa") and "Quality" in d["description"] and d["posted"]
