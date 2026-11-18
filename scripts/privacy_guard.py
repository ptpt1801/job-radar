"""Fail if the repo contains personal data: VN phone numbers, personal e-mails,
*.docx / *.pdf files or a private/ directory. Prints file names only, never the match."""
from __future__ import annotations

import gzip
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHONE = re.compile(r"(?<![0-9A-Za-z])(\+84|0)[35789]\d{8}(?![0-9A-Za-z])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(r"^(\d+\+)?[A-Za-z0-9._-]+@users\.noreply\.github\.com$|^noreply@(github|anthropic)\.com$", re.I)
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf"}


def files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.splitlines()
        return [ROOT / f for f in out if f]
    except Exception:
        return [p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)]


def scan(paths: list[Path]) -> list[tuple[str, str]]:
    problems = []
    for p in paths:
        rel = p.relative_to(ROOT).as_posix()
        if rel.split("/")[0] == "private":
            problems.append((rel, "private/ directory is tracked"))
            continue
        if p.suffix.lower() in (".docx", ".pdf", ".doc"):
            problems.append((rel, f"{p.suffix} file"))
            continue
        if p.suffix.lower() in BINARY_EXT or not p.is_file():
            continue
        try:
            if p.suffix.lower() == ".gz":
                with gzip.open(p, "rt", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            else:
                text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if PHONE.search(text):
            problems.append((rel, "Vietnamese phone number"))
        bad = [e for e in EMAIL.findall(text) if not ALLOWED_EMAIL.match(e)]
        if bad:
            problems.append((rel, f"{len(bad)} e-mail address(es)"))
    return problems


def main() -> int:
    problems = scan(files())
    if problems:
        print("privacy-guard: FAILED")
        for rel, why in problems:
            print(f"  {rel}: {why}")
        return 1
    print("privacy-guard: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
