from pipeline.dedupe import dedupe

BASE = " ".join(f"word{i}" for i in range(120))


def _j(i, title="Officer, Cash Management Operations", desc=BASE, source="custom"):
    return {"id": f"id{i}", "source_job_id": str(i), "company_id": "sc", "title": title, "city": "hanoi",
            "source": source, "url": f"https://x/{i}", "posted_at": None, "_desc": desc}


def test_same_source_near_identical_merged_with_openings():
    jobs = [_j(3), _j(1, desc=BASE.replace("word5 ", "word-5 ", 1)), _j(2)]
    out, merged = dedupe(jobs)
    assert merged == 2 and len(out) == 1
    assert out[0]["id"] == "id1" and out[0]["openings"] == 3
    assert sorted(out[0]["_merged_ids"]) == ["id2", "id3"]


def test_same_source_different_text_kept_apart():
    other = " ".join(f"other{i}" for i in range(120))
    out, merged = dedupe([_j(1), _j(2, desc=other)])
    assert merged == 0 and len(out) == 2 and not any(j.get("openings") for j in out)


def test_short_descriptions_not_merged():
    out, _ = dedupe([_j(1, desc="short text"), _j(2, desc="short text")])
    assert len(out) == 2
