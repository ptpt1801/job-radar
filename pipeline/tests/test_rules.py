import datetime as dt

import pytest

from pipeline import dedupe, enrich_rules as er, filter as jf, score
from pipeline.adapters import ybox
from pipeline.normalize import detect_city, normalize, posted_from_text
from pipeline.text import scrub

NOW = dt.datetime(2026, 11, 18, 3, 0, tzinfo=dt.timezone.utc)
CO = {"id": "acme", "name": "Acme", "hq_country": "DE", "region": "europe", "industry": "industrial_automation"}


def raw(**kw):
    base = {"source": "workday", "source_job_id": "R1", "title": "Supply Chain Intern", "url": "https://x.example/j/1",
            "location_raw": "Hanoi, Vietnam", "country_code": "VN", "description": "We need English and Excel."}
    base.update(kw)
    return base


# ---------- normalize ----------
def test_id_is_stable_12_hex():
    a, b = normalize(raw(), CO, NOW), normalize(raw(), CO, NOW)
    assert a["id"] == b["id"] and len(a["id"]) == 12
    assert normalize(raw(source_job_id="R2"), CO, NOW)["id"] != a["id"]


@pytest.mark.parametrize("loc,city", [
    ("Vietnam - Ho Chi Minh City", "hcmc"), ("Thu Duc City, , Vietnam", "hcmc"), ("Ha Noi - Vietnam", "hanoi"),
    ("Ben Cat Binh Duong", "binh_duong"), ("VNM - Dong Nai - Loc An", "dong_nai"), ("Bac Ninh, Viet Nam", "bac_ninh"),
    ("VNM.Da Nang", "da_nang"), ("Vietnam - Can Tho", "other_vn")])
def test_city(loc, city):
    assert detect_city(loc) == city


def test_posted_text():
    assert posted_from_text("Posted 3 Days Ago", NOW) == "2026-11-15T00:00:00Z"
    assert posted_from_text("Posted Today", NOW) == "2026-11-18T00:00:00Z"
    assert posted_from_text("Posted 30+ Days Ago", NOW) == "2026-10-19T00:00:00Z"


# ---------- filter ----------
def test_filter_keeps_open_vn():
    j = normalize(raw(), CO, NOW)
    assert jf.reason_to_drop(j, CO, NOW) is None


def test_filter_drops_non_vn_and_expired_and_closed():
    assert jf.reason_to_drop(normalize(raw(country_code="SG", location_raw="Singapore"), CO, NOW), CO, NOW) == "not_vietnam"
    assert jf.reason_to_drop(normalize(raw(deadline="2026-11-17"), CO, NOW), CO, NOW) == "deadline_passed"
    assert jf.reason_to_drop(normalize(raw(deadline="2026-11-18"), CO, NOW), CO, NOW) is None  # today (VN) still open
    assert jf.reason_to_drop(normalize(raw(is_open=False), CO, NOW), CO, NOW) == "status_closed"


def test_filter_exclusions():
    food = dict(CO, industry="beverage")
    assert jf.reason_to_drop(normalize(raw(), food, NOW), food, NOW) == "excluded_industry"
    nestle = dict(CO, name="Nestlé Vietnam")
    assert jf.reason_to_drop(normalize(raw(), nestle, NOW), nestle, NOW) == "excluded_company"
    abbott = dict(CO, exclude_keywords=["nutrition"])
    j = normalize(raw(description="DIVISION: ANI International Nutrition"), abbott, NOW)
    assert jf.reason_to_drop(j, abbott, NOW) == "excluded_keyword"


# ---------- dedupe ----------
def test_dedupe_cross_source_keeps_higher_priority_and_fills_salary():
    a = normalize(raw(), CO, NOW); a["posted_at"] = "2026-11-10T00:00:00Z"; a["salary"] = None
    b = normalize(raw(source="ybox", source_job_id="y1", url="https://ybox.vn/x"), CO, NOW)
    b["posted_at"] = "2026-11-15T00:00:00Z"; b["salary"] = {"min": 1, "max": 2, "currency": "VND", "period": "month"}
    out, merged = dedupe.dedupe([b, a])
    assert merged == 1 and len(out) == 1
    assert out[0]["source"] == "workday" and out[0]["also_on"] == ["https://ybox.vn/x"] and out[0]["salary"]["max"] == 2


def test_dedupe_same_source_not_merged_and_far_dates_not_merged():
    a = normalize(raw(), CO, NOW); b = normalize(raw(source_job_id="R9"), CO, NOW)
    assert len(dedupe.dedupe([a, b])[0]) == 2
    c = normalize(raw(source="ybox", source_job_id="y2"), CO, NOW)
    a["posted_at"], c["posted_at"] = "2026-10-01T00:00:00Z", "2026-11-15T00:00:00Z"
    assert len(dedupe.dedupe([a, c])[0]) == 2


# ---------- enrich ----------
def test_level_rules():
    assert er.detect_level("Finance Intern", "", None, None) == "internship"
    assert er.detect_level("Management Trainee 2026", "", None, None) == "graduate"
    assert er.detect_level("Head of Procurement", "", None, None) == "manager"
    assert er.detect_level("Buyer", "", None, None) == "experienced"
    assert er.detect_level("Buyer", "", "graduate", None) == "graduate"  # source field wins


def test_skills_and_experience():
    d = "Requirements: at least 2 years of experience in logistics. Good English, Excel and SAP. Tối thiểu 3 năm kinh nghiệm."
    sk = er.detect_skills("Logistics Specialist", d, "en")
    assert {"english", "excel", "sap", "logistics"} <= set(sk)
    assert er.detect_experience(d) == 2


def test_function_title_first():
    assert er.detect_function("Senior Procurement Engineer", None, "") == "supply_chain"
    assert er.detect_function("Software Developer", None, "") == "it"
    assert er.detect_function("Accountant", None, "") == "finance"


def test_salary_only_when_explicit():
    assert er.detect_salary("Competitive salary and benefits") is None
    s = er.detect_salary("Mức lương: 15 - 20 triệu/tháng")
    assert s["min"] == 15_000_000 and s["max"] == 20_000_000 and s["currency"] == "VND" and s["period"] == "month"
    s = er.detect_salary("Salary range: 1,000 - 1,500 USD per month")
    assert s["currency"] == "USD" and s["max"] == 1500
    assert er.detect_salary("Allowance: 4 - 5 million VND") ["is_allowance"] is True


def test_benefits_section():
    d = "About us\nBenefits\n• Health insurance\n• 13th month bonus\n• Hybrid working\nHow to apply\nSend CV"
    assert er.detect_benefits(d) == ["Health insurance", "13th month bonus", "Hybrid working"]


def test_scrub_contacts():
    s = scrub("Call 0" + "912 345 678 or +84 " + "912345678, mail hr.person" + "@" + "acme.com")
    assert "0912" not in s and "acme.com" not in s


# ---------- score ----------
PROFILE = {"skills": ["english", "excel"], "target_levels": ["internship", "graduate"],
           "target_functions": ["supply_chain", "operations"], "target_cities": ["hanoi"]}


def test_match_formula():
    job = {"skills": ["english", "excel", "sap", "logistics"], "level": "internship", "function": "supply_chain", "city": "hanoi"}
    m, have, missing = score.score(job, PROFILE)
    assert m == round(25 + 22 + 18 + 10) and have == ["english", "excel"] and missing == ["sap", "logistics"]
    job2 = {"skills": [], "level": "experienced", "function": "operations", "city": "hcmc", "work_mode": None}
    assert score.score(job2, PROFILE)[0] == 25 + 12 + 12 + 2
    job3 = {"skills": [], "level": "manager", "function": "it", "city": "hcmc", "work_mode": "remote"}
    assert score.score(job3, PROFILE)[0] == 25 + 0 + 0 + 10
    assert score.score(job, None) == (None, [], [])


def test_match_capped_99():
    job = {"skills": ["english"], "level": "internship", "function": "supply_chain", "city": "hanoi"}
    assert score.score(job, PROFILE)[0] == 99


def test_apply_hides_tags_when_disabled():
    jobs = [{"skills": ["english"], "level": "internship", "function": "supply_chain", "city": "hanoi"}]
    score.apply(jobs, PROFILE, show_tags=False)
    assert "have" not in jobs[0] and jobs[0]["match"] == 99


# ---------- Ybox rules (>= 10 cases) ----------
WL = [{"id": "bosch", "name": "Bosch"}, {"id": "dhl", "name": "DHL Group", "aliases": ["DHL Express", "DHL Supply Chain"]},
      {"id": "loreal", "name": "L'Oréal"}, {"id": "pwc", "name": "PwC Vietnam"}, {"id": "citi", "name": "Citi"},
      {"id": "decathlon", "name": "Decathlon"}]

COMPANY_POSTS = [
    ("[HCM] Công Ty TNHH Bosch Việt Nam Tuyển Dụng Thực Tập Sinh Kế Toán Full-time 2026", "bosch"),
    ("[HN] Công Ty DHL Express Việt Nam Tuyển Dụng Nhân Viên Xuất Nhập Khẩu Full-time 2026", "dhl"),
    ("[HCM] Công Ty L'Oréal Việt Nam Tuyển Dụng Management Trainee Full-time 2026", "loreal"),
    ("[HN/HCM] PwC Việt Nam Tuyển Dụng Thực Tập Sinh Kiểm Toán Full-time 2026", "pwc"),
    ("[HCM] Decathlon Vietnam Tuyển Dụng Sports Advisor Part-time 2026", "decathlon"),
]
STUDENT_POSTS = [
    "[HN] CLB Kinh Tế Đối Ngoại Tuyển Thành Viên Gen 10",
    "[HCM] Dự Án Mùa Hè Xanh Tuyển Tình Nguyện Viên 2026",
    "[Online] Ban Tổ Chức Cuộc Thi Marketing Arena Tuyển Dụng Cộng Tác Viên Truyền Thông",
    "[HN] Ybox Tuyển Dụng Đại Sứ Sinh Viên Season 5",
    "[HCM] Chương Trình Student Ambassador Tuyển Dụng Thành Viên 2026",
]


@pytest.mark.parametrize("title,cid", COMPANY_POSTS)
def test_ybox_keeps_whitelisted_company_jobs(title, cid):
    decision, reason, c = ybox.classify(title, WL)
    assert decision == "keep", reason
    assert c["id"] == cid


@pytest.mark.parametrize("title", STUDENT_POSTS)
def test_ybox_rejects_student_projects(title):
    assert ybox.classify(title, WL)[0] == "reject"


def test_ybox_brand_inside_longer_name_is_not_a_match():
    d, reason, _ = ybox.classify("[HCM] Công Ty Citi Complex Hospitality Tuyển Dụng Thực Tập Sinh Thu Mua Full-time 2026", WL)
    assert d == "reject"


def test_ybox_ambiguous_legal_entity_rejected_without_llm():
    d, reason, _ = ybox.classify("[HN] Công Ty TNHH Unknown Trading Tuyển Dụng Nhân Viên Kinh Doanh Full-time 2026", WL)
    assert d == "reject" and reason == "ambiguous_legal_entity_no_llm"


def test_ybox_excluded_company():
    d, reason, _ = ybox.classify("[HCM] Công Ty Nestlé Việt Nam Tuyển Dụng Thực Tập Sinh Full-time 2026", WL + [{"id": "n", "name": "Nestlé"}])
    assert d == "reject" and reason == "excluded_company"


def test_ybox_mua_is_not_mua():
    # "Thu Mua" (purchasing) must not be rejected as "mùa" (season)
    d, reason, _ = ybox.classify("[HCM] Công Ty TNHH Bosch Việt Nam Tuyển Dụng Thực Tập Sinh Thu Mua Full-time 2026", WL)
    assert d == "keep", reason
    assert ybox.classify("[HN] Bosch Tuyển Dụng Thực Tập Sinh Mùa Hè 2026", WL)[0] == "reject"
