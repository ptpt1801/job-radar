import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# test strings are assembled at runtime so this file itself passes the guard
PHONE = "09" + "12345678"
PHONE_INTL = "+84" + "912345678"
MAIL = "someone" + "@" + "gmail.com"
spec = importlib.util.spec_from_file_location("pg", ROOT / "scripts" / "privacy_guard.py")
pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)


def _scan(tmp_path, name, content):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content) if isinstance(content, bytes) else p.write_text(content, encoding="utf-8")
    pg.ROOT = tmp_path
    return pg.scan([p])


def test_detects_phone(tmp_path):
    assert _scan(tmp_path, "a.txt", "call " + PHONE)
    assert _scan(tmp_path, "b.txt", "call " + PHONE_INTL)


def test_ignores_long_ids(tmp_path):
    assert not _scan(tmp_path, "a.txt", "id 744000162262305 and 20912345678901")


def test_detects_personal_email_but_allows_noreply(tmp_path):
    assert _scan(tmp_path, "a.txt", "me: " + MAIL)
    assert not _scan(tmp_path, "b.txt", "Co-Authored-By: Claude <noreply@anthropic.com> 1+x@users.noreply.github.com")


def test_detects_docx_pdf_private(tmp_path):
    assert _scan(tmp_path, "cv.docx", b"PK")
    assert _scan(tmp_path, "cv.pdf", b"%PDF")
    assert _scan(tmp_path, "private/cv_profile.json", "{}")


def test_report_has_no_content(tmp_path, capsys):
    pg.ROOT = tmp_path
    (tmp_path / "x.txt").write_text(PHONE, encoding="utf-8")
    pg.files = lambda: [tmp_path / "x.txt"]
    assert pg.main() == 1
    assert PHONE not in capsys.readouterr().out
