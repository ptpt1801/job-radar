"""Rule-based extraction (0 cost): skills, level, function, experience, salary, benefits, languages."""
from __future__ import annotations

import functools
import re

from .config import taxonomy
from .text import fold, kw_pattern, scrub

LEVEL_ORDER = ["internship", "graduate", "experienced", "manager"]


@functools.lru_cache
def _pats(section: str) -> dict[str, re.Pattern]:
    out = {}
    for k, v in taxonomy()[section].items():
        p = kw_pattern(v.get("keywords") or [])
        if p:
            out[k] = p
    return out


def detect_level(title: str, desc: str, level_raw: str | None, employment_type: str | None) -> str:
    t = fold(title)
    p = _pats("levels")
    if p["internship"].search(t) or employment_type == "internship":
        return "internship"
    if level_raw in LEVEL_ORDER:
        return level_raw
    if p["graduate"].search(t):
        return "graduate"
    if p["manager"].search(t):
        return "manager"
    return "experienced"


FUNC_PRIORITY = ["it", "supply_chain", "finance", "hr", "legal", "marketing", "business", "sales", "engineering", "operations"]


def detect_function(title: str, function_raw: str | None, desc: str) -> str:
    p = _pats("functions")
    for text in (fold(title), fold(function_raw or "")):
        if not text:
            continue
        for k in FUNC_PRIORITY:
            if k in p and p[k].search(text):
                return k
    d = fold(desc[:1500])
    best, n = "other", 0
    for k in FUNC_PRIORITY:
        if k in p:
            c = len(p[k].findall(d))
            if c > n:
                best, n = k, c
    return best if n >= 2 else "other"


@functools.lru_cache
def _skill_scope() -> dict:
    return {k: set(v["only_functions"]) for k, v in taxonomy()["skills"].items() if v.get("only_functions")}


def detect_skills(title: str, desc: str, lang: str, function: str | None = None) -> list[str]:
    s = fold(title + "\n" + desc)
    scope = _skill_scope()
    found = [k for k, p in _pats("skills").items() if p.search(s) and (k not in scope or function in scope[k])]
    if "english" not in found and (lang == "en" or re.search(r"\benglish\b", s)):
        found.insert(0, "english")
    return found[:12]


def detect_languages(desc: str, lang: str) -> list[str]:
    s = fold(desc)
    found = [k for k, p in _pats("languages").items() if p.search(s)]
    if lang == "en" and "english" not in found:
        found.insert(0, "english")
    return found


EXP_RE = re.compile(r"(?:at least|minimum|min\.?|tối thiểu|toi thieu|over|trên|tren)?\s*(\d{1,2})\s*\+?\s*(?:-|–|to|~)?\s*(?:\d{1,2})?\s*\+?\s*(?:years?|yrs?|năm|nam)\b", re.I)


def detect_experience(desc: str) -> int | None:
    vals = []
    for m in EXP_RE.finditer(desc or ""):
        ctx = (desc[m.end():m.end() + 60]).lower()
        if any(w in ctx for w in ("experience", "kinh nghiệm", "kinh nghiem", "of relevant", "in a", "in the", "working")):
            v = int(m.group(1))
            if 0 <= v <= 30:
                vals.append(v)
    return min(vals) if vals else None


NUM = r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
SAL_RE = re.compile(
    NUM + r"\s*(triệu|trieu|tr|million|mil|m|k)?\s*(?:-|–|to|đến|den|~)\s*" + NUM +
    r"\s*(triệu|trieu|tr|million|mil|m|k)?\s*(vnd|vnđ|đ|usd|\$|eur|€)?", re.I)
CUR_NEAR = re.compile(r"(vnd|vnđ|usd|\$|eur|€|triệu|trieu|million)", re.I)
PERIOD_RE = re.compile(r"(/\s*(?:month|tháng|thang)|per month|mỗi tháng|monthly|/\s*(?:year|năm)|per year|annual|/\s*hour|per hour)", re.I)


def _num(s: str) -> float:
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        return float(re.sub(r"[.,]", "", s))
    return float(s.replace(",", "."))


def detect_salary(desc: str) -> dict | None:
    """Only when an explicit amount + currency/unit is stated near a salary keyword."""
    if not desc:
        return None
    for kw in re.finditer(r"(salary|lương|luong|mức lương|compensation|allowance|trợ cấp|phụ cấp|pay range|base pay)", desc, re.I):
        window = desc[kw.start(): kw.start() + 160]
        m = SAL_RE.search(window)
        if not m:
            continue
        unit1, unit2, cur = (m.group(2) or ""), (m.group(4) or ""), (m.group(5) or "")
        unit = (unit2 or unit1).lower()
        if not (cur or unit in ("triệu", "trieu", "tr", "million")) and not CUR_NEAR.search(window):
            continue
        lo, hi = _num(m.group(1)), _num(m.group(3))
        mult = 1_000_000 if unit in ("triệu", "trieu", "tr", "million", "mil", "m") else (1000 if unit == "k" else 1)
        lo, hi = lo * mult, hi * mult
        near = CUR_NEAR.search(window)
        cl = (cur or (near.group(1) if near else "vnd")).lower()   # "15-20 tr" with no currency word = VND
        currency = "USD" if cl in ("usd", "$") else ("EUR" if cl in ("eur", "€") else "VND")
        if currency == "VND" and hi < 100_000:
            continue  # implausible
        pm = PERIOD_RE.search(window)
        p = (pm.group(1).lower() if pm else "")
        period = "year" if ("year" in p or "năm" in p or "annual" in p) else ("hour" if "hour" in p else "month")
        return {"min": lo, "max": hi, "currency": currency, "period": period,
                "is_allowance": bool(re.search(r"allowance|trợ cấp|phụ cấp", kw.group(1), re.I)),
                "raw": re.sub(r"\s+", " ", window[: m.end()]).strip()[:160]}
    return None


BEN_HDR = re.compile(r"^\s*(?:[#*•\-]\s*)?(benefits?|what we offer|what you('| wi)ll get|why join us|our offer|we offer|perks|phúc lợi|quyền lợi|chế độ đãi ngộ|what's in it for you)\b", re.I)
HDR_LIKE = re.compile(r"^[A-ZÀ-Ỹ][^.!?]{2,60}:?$")


def detect_benefits(desc: str) -> list[str]:
    lines = [l.strip() for l in (desc or "").split("\n")]
    out, on = [], False
    for l in lines:
        if not l:
            continue
        if BEN_HDR.match(l):
            on = True
            tail = BEN_HDR.sub("", l).strip(" :–-")
            if len(tail) > 15 and not out:
                pass
            continue
        if on:
            is_bullet = l.startswith(("•", "-", "*", "·", "–", "+"))
            if not is_bullet and HDR_LIKE.match(l) and len(out) > 0:
                break
            item = l.lstrip("•-*·–+ ").strip()
            if len(item) < 4:
                continue
            if not is_bullet and len(item) > 200:
                break
            if len(item) > 120:
                item = item[:117].rstrip() + "…"
            out.append(item)
            if len(out) >= 6:
                break
    return out


def excerpt(desc: str, n: int = 600) -> str | None:
    if not desc:
        return None
    s = re.sub(r"\s+", " ", desc).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def enrich(job: dict) -> dict:
    desc = job.get("_desc") or ""
    job["level"] = detect_level(job["title"], desc, job.get("_level_raw"), job.get("employment_type"))
    job["function"] = detect_function(job["title"], job.get("_function_raw"), desc)
    job["skills"] = detect_skills(job["title"], desc, job.get("lang", "en"), job["function"])
    job["languages_required"] = detect_languages(desc, job.get("lang", "en"))
    job["experience_min_years"] = detect_experience(desc)
    job["salary"] = job.get("_salary") or detect_salary(desc)
    job["benefits"] = [scrub(b) for b in detect_benefits(desc)]
    job["description_excerpt"] = scrub(excerpt(desc))
    return job
