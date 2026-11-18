"""Text helpers: HTML -> text, accent folding, keyword matching."""
from __future__ import annotations

import html as htmllib
import re
import unicodedata

from bs4 import BeautifulSoup


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    if "<" not in s and "&" not in s:
        return s.strip()
    if "&lt;" in s and "<" not in s:
        s = htmllib.unescape(s)
    soup = BeautifulSoup(s, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "h5", "tr"]):
        if tag.name == "li":
            tag.insert(0, "\n• ")
        tag.append("\n")
    text = soup.get_text()
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def fold(s: str | None) -> str:
    """lowercase, strip Vietnamese accents, đ->d."""
    if not s:
        return ""
    s = s.lower().replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def kw_pattern(keywords: list[str]) -> re.Pattern | None:
    kws = [fold(k).strip() for k in keywords if k and fold(k).strip()]
    if not kws:
        return None
    parts = sorted({re.escape(k) for k in kws}, key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])")


def norm_title(s: str) -> str:
    s = fold(s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


PHONE_RE = re.compile(r"(?<!\d)(?:\+84|0)[\s.-]?[35789](?:[\s.-]?\d){8}(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def scrub(s: str | None) -> str | None:
    """Remove phone numbers and e-mail addresses (recruiters' contact details) from published text."""
    if not s:
        return s
    s = PHONE_RE.sub("[…]", s)
    return EMAIL_RE.sub("[email]", s)


VN_WORDS = ("vietnam", "viet nam", "ho chi minh", "hanoi", "ha noi", "da nang", "hai phong",
            "binh duong", "dong nai", "bac ninh", "vnm", "thu duc", "saigon", "can tho", "long an")


def looks_vn(*parts) -> bool:
    s = fold(" ".join(p for p in parts if p))
    return any(w in s for w in VN_WORDS)
