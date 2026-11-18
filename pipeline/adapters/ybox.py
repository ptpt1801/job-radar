"""Ybox.vn: recruitment section only, with rules that separate real company jobs from
student-club / project / ambassador posts (BUILD_PROMPT 5.5, docs/01 section 3).

Ybox is not per-company: one pass over the listing pages, then each kept post is
attributed to a whitelist company via `company_id_override`."""
from __future__ import annotations

import json
import re
import unicodedata

from bs4 import BeautifulSoup
from rapidfuzz import fuzz

from ..config import companies
from ..filter import excluded_company
from ..text import fold, html_to_text
from .base import Adapter, register

BASE = "https://ybox.vn"
LIST_URL = BASE + "/tuyen-dung"

# ASCII words are matched on accent-folded text; Vietnamese words with diacritics are matched
# exactly (lowercase), so that "mùa" (season) does not hit "thu mua" (purchasing).
REJECT_ASCII = ["clb", "btc", "ctv", "season", "volunteer", "ambassador", "ybox"]
REJECT_VI = ["câu lạc bộ", "dự án", "ban tổ chức", "mùa", "tuyển thành viên", "cộng tác viên", "tình nguyện",
             "đại sứ", "chương trình", "cuộc thi", "học bổng", "sự kiện"]
_REJECT = re.compile(r"(?<![a-z0-9])(?:" + "|".join(map(re.escape, REJECT_ASCII)) + r")(?![a-z0-9])")
_REJECT_VI = re.compile(r"(?<!\w)(?:" + "|".join(sorted(map(re.escape, REJECT_VI), key=len, reverse=True)) + r")(?!\w)")


def reject_word(title: str) -> str | None:
    m = _REJECT_VI.search(unicodedata.normalize("NFC", (title or "").lower())) or _REJECT.search(fold(title))
    return m.group(0) if m else None


LEGAL = re.compile(r"(cong ty|tnhh|co\.?,? ?ltd|jsc|gmbh|\bvietnam\b|viet nam|\bltd\b|limited|corporation|tap doan)")
GENERIC = {"cong", "ty", "tnhh", "co", "ltd", "limited", "jsc", "gmbh", "vietnam", "viet", "nam", "vn", "group", "tap", "doan",
           "corporation", "corp", "inc", "chi", "nhanh", "van", "phong", "dai", "dien", "ngan", "hang", "tai", "the", "and", "&",
           "global", "international", "mot", "thanh", "vien", "plc", "sa", "ag", "se", "nv", "bv", "lien", "doanh"}
TITLE_RE = re.compile(r"^\s*\[(?P<loc>[^\]]*)\]\s*(?P<emp>.+?)\s+tuy[eể]n\s+d[uụ]ng\s+(?P<role>.+)$", re.I)

LAST_REJECTED: list[dict] = []


def parse_title(t: str) -> dict:
    m = TITLE_RE.match(t or "")
    if not m:
        return {"loc": None, "employer": None, "role": t}
    return {"loc": m.group("loc"), "employer": m.group("emp"), "role": m.group("role")}


def _core(name: str) -> str:
    toks = [x for x in re.split(r"[^a-z0-9&]+", fold(name)) if x]
    return " ".join(x for x in toks if x not in GENERIC)


def _names(c: dict) -> list[str]:
    base = re.sub(r"\(.*?\)", "", c["name"])
    return [base, *(c.get("aliases") or [])]


def match_whitelist(employer: str | None, cos: list[dict] | None = None) -> tuple[dict | None, int]:
    """Fuzzy-match an employer to the whitelist. The employer's *core* name (legal words removed)
    must match a company name with ratio >= 90 - a brand merely appearing inside a longer
    name ("Citi Complex Hospitality") does not count."""
    if not employer:
        return None, 0
    core = _core(employer)
    if not core:
        return None, 0
    best, score = None, 0
    for c in cos if cos is not None else companies():
        for n in _names(c):
            cn = _core(n)
            if not cn:
                continue
            s = fuzz.ratio(core, cn)
            if s > score:
                best, score = c, s
    return (best, int(score)) if score >= 90 else (None, int(score))


def classify(title: str, cos: list[dict] | None = None) -> tuple[str, str, dict | None]:
    """-> (decision 'keep'|'reject', reason, company)"""
    p = parse_title(title)
    w = reject_word(title)
    if w:
        return "reject", f"keyword:{w}", None
    emp = p["employer"]
    if not emp:
        return "reject", "no_employer", None
    if excluded_company(emp):
        return "reject", "excluded_company", None
    c, s = match_whitelist(emp, cos)
    if c:
        return "keep", f"whitelist:{c['id']}({s})", c
    if LEGAL.search(fold(emp)):
        # legal entity, but we cannot confirm a European/American HQ without the LLM tier
        return "reject", "ambiguous_legal_entity_no_llm", None
    return "reject", "not_whitelisted", None


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    seen = {}
    for a in soup.select('a[href^="/tuyen-dung/"]'):
        href = a["href"].split("#")[0]
        t = a.get_text(" ", strip=True)
        if href.count("/") < 2 or not t or len(t) < 15:
            continue
        seen.setdefault(href, t)
    return [{"url": BASE + h, "title": t, "id": h.rstrip("/").rsplit("-", 1)[-1]} for h, t in seen.items()]


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    for s in soup.select('script[type="application/ld+json"]'):
        try:
            d = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = d if isinstance(d, list) else d.get("@graph", [d]) if isinstance(d, dict) else []
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "JobPosting":
                return it
    return {}


def salary_from_ld(ld: dict) -> dict | None:
    bs = ld.get("baseSalary") or {}
    v = bs.get("value") or {}
    lo, hi = v.get("minValue"), v.get("maxValue")
    if lo is None and hi is None and v.get("value") is None:
        return None
    unit = (v.get("unitText") or "MONTH").lower()
    cur = (bs.get("currency") or "VND").upper()
    if cur not in ("VND", "USD", "EUR"):
        return None
    try:
        lo = float(lo) if lo is not None else (float(v["value"]) if v.get("value") is not None else None)
        hi = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        return None
    if not lo and not hi:
        return None
    return {"min": lo, "max": hi, "currency": cur, "period": "year" if "year" in unit else ("hour" if "hour" in unit else "month"),
            "is_allowance": False, "raw": f"{lo or ''}-{hi or ''} {cur}/{unit}"}


@register("ybox")
class YboxAdapter(Adapter):
    source = "ybox"

    def fetch(self, company, known_ids=None, reuse=None):
        pages = int(company.get("pages", 1))
        cos = companies()
        LAST_REJECTED.clear()
        posts = {}
        for page in range(1, pages + 1):
            r = self.http.get(LIST_URL, params={"page": page} if page > 1 else None)
            if r.status_code != 200:
                break
            batch = parse_list(r.text)
            new = [b for b in batch if b["id"] not in posts]
            for b in new:
                posts[b["id"]] = b
            if not new:
                break  # Ybox has no server-side pagination: page 2+ repeat page 1
        out = []
        for pid, p in posts.items():
            decision, reason, c = classify(p["title"], cos)
            if decision != "keep":
                LAST_REJECTED.append({"title": p["title"][:160], "reason": reason})
                continue
            r = self.http.get(p["url"])
            if r.status_code != 200:
                continue
            ld = parse_detail(r.text)
            loc = ld.get("jobLocation") or {}
            loc = loc[0] if isinstance(loc, list) and loc else loc
            addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
            addr_raw = ", ".join(x for x in [addr.get("streetAddress"), addr.get("addressLocality"), addr.get("addressRegion")] if isinstance(x, str) and x) or None
            parsed = parse_title(p["title"])
            out.append({
                "source": "ybox",
                "source_job_id": pid,
                "company_id_override": c["id"],
                "title": parsed["role"] or ld.get("title") or p["title"],
                "url": p["url"],
                "company_name_raw": ((ld.get("hiringOrganization") or {}).get("name")) or parsed["employer"],
                "location_raw": " ".join(x for x in [parsed["loc"] or "", addr_raw or ""] if x) + " Vietnam",
                "address_raw": addr_raw or parsed["loc"],
                "country_code": "VN",
                "description": html_to_text(ld.get("description")),
                "posted_at": ld.get("datePosted"),
                "deadline": (ld.get("validThrough") or None) and str(ld["validThrough"])[:10],
                "employment_type_raw": ld.get("employmentType") if isinstance(ld.get("employmentType"), str) else " ".join(ld.get("employmentType") or []),
                "salary": salary_from_ld(ld),
                "lang_hint": "vi",
                "is_open": True,
            })
        return out
