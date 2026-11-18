"""RawJob -> schema job (neutral keys)."""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from .config import taxonomy
from .text import fold, kw_pattern

_city_pats: list[tuple[str, re.Pattern]] | None = None


def _cities():
    global _city_pats
    if _city_pats is None:
        _city_pats = [(k, kw_pattern(v.get("keywords") or [])) for k, v in taxonomy()["cities"].items()]
    return _city_pats


def make_id(source: str, source_job_id: str) -> str:
    return hashlib.sha1(f"{source}:{source_job_id}".encode()).hexdigest()[:12]


def detect_city(*parts) -> str:
    s = fold(" ".join(p for p in parts if p))
    for key, pat in _cities():
        if key == "other_vn":
            continue
        if pat and pat.search(s):
            return key
    return "other_vn"


VI_CHARS = re.compile(r"[ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ]", re.I)


def detect_lang(title: str, desc: str) -> str:
    s = (title or "") + " " + (desc or "")[:3000]
    if not s.strip():
        return "en"
    letters = sum(c.isalpha() for c in s) or 1
    vi = len(VI_CHARS.findall(s))
    if vi / letters > 0.03:
        return "vi"
    ascii_ratio = sum(c.isascii() for c in s if c.isalpha()) / letters
    return "en" if ascii_ratio > 0.9 else "other"


def employment_type(raw: str | None, title: str = "") -> str | None:
    s = fold((raw or "") + " " + (title or ""))
    if re.search(r"\b(intern|internship|thuc tap)\b", s):
        return "internship"
    if not raw:
        return None
    s = fold(raw)
    if "part" in s:
        return "part_time"
    if any(k in s for k in ("contract", "temporary", "fixed", "limited", "temp")):
        return "contract"
    if "full" in s or "permanent" in s or "regular" in s:
        return "full_time"
    return None


def work_mode(raw_mode: str | None, *parts) -> str | None:
    if raw_mode in ("onsite", "hybrid", "remote"):
        return raw_mode
    s = fold(" ".join(p for p in parts if p))
    if re.search(r"\bhybrid\b", s):
        return "hybrid"
    if re.search(r"\b(remote|work from home|wfh)\b", s):
        return "remote"
    return None


POSTED_RE = re.compile(r"(\d+)\+?\s+days?\s+ago", re.I)


def posted_from_text(text: str | None, now: dt.datetime) -> str | None:
    if not text:
        return None
    t = text.lower()
    if "today" in t:
        d = now
    elif "yesterday" in t:
        d = now - dt.timedelta(days=1)
    else:
        m = POSTED_RE.search(t)
        if not m:
            return None
        d = now - dt.timedelta(days=int(m.group(1)))
    return d.strftime("%Y-%m-%dT00:00:00Z")


def iso_z(s: str | None) -> str | None:
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def content_hash(raw: dict) -> str:
    h = hashlib.sha1()
    for k in ("title", "description", "location_raw"):
        h.update((raw.get(k) or "").encode("utf-8", "ignore"))
    return h.hexdigest()[:16]


def normalize(raw: dict, company: dict, now: dt.datetime) -> dict:
    now_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sjid = f"{company['id']}:{raw['source_job_id']}"
    title = re.sub(r"\s+", " ", raw.get("title") or "").strip()
    desc = raw.get("description") or ""
    posted = iso_z(raw.get("posted_at")) or posted_from_text(raw.get("posted_text"), now)
    deadline = raw.get("deadline")
    if deadline:
        deadline = str(deadline)[:10]
    job = {
        "id": make_id(raw["source"], sjid),
        "source": raw["source"],
        "source_job_id": sjid,
        "company_id": company["id"],
        "company": company["name"],
        "hq_country": company.get("hq_country"),
        "region": company.get("region"),
        "industry": company.get("industry"),
        "title": title,
        "url": raw.get("url"),
        "lang": raw.get("lang_hint") if raw.get("lang_hint") in ("en", "vi") else detect_lang(title, desc),
        "city": detect_city(raw.get("city_raw"), raw.get("address_raw"), raw.get("location_raw")),
        "address_raw": raw.get("address_raw") or raw.get("location_raw"),
        "work_mode": work_mode(raw.get("work_mode"), raw.get("remote_raw"), raw.get("location_raw"), title),
        "employment_type": employment_type(raw.get("employment_type_raw"), title),
        "posted_at": posted,
        "posted_text": raw.get("posted_text"),
        "deadline": deadline,
        "first_seen_at": now_s,
        "last_seen_at": now_s,
        "closed_at": None,
        "status": "open",
        "content_hash": content_hash(raw),
        # transient fields (stripped before writing)
        "_desc": desc,
        "_level_raw": raw.get("level_raw"),
        "_function_raw": raw.get("function_raw"),
        "_country_code": raw.get("country_code"),
        "_location_raw": raw.get("location_raw"),
        "_is_open": raw.get("is_open", True),
        "_company_name_raw": raw.get("company_name_raw"),
        "_salary": raw.get("salary"),
    }
    return job
