from pipeline.robots import Robots

UA = "JobRadarBot/1.0 (+https://github.com/ptpt1801/job-radar)"


def test_longest_match_allow_beats_root_disallow():
    r = Robots("User-agent: *\nDisallow: /\nAllow: /$\nAllow: /careers\nAllow: /api/pcsx\n")
    assert r.can_fetch(UA, "https://x.com/api/pcsx/search?domain=a.com")
    assert r.can_fetch(UA, "https://x.com/careers/job/1")
    assert r.can_fetch(UA, "https://x.com/")
    assert not r.can_fetch(UA, "https://x.com/private")


def test_wildcards_and_specific_agent():
    txt = "User-agent: *\nDisallow: */apply\nDisallow: /search-jobs/\n\nUser-agent: JobRadarBot\nDisallow: /nope\nCrawl-delay: 3\n"
    r = Robots(txt)
    assert not r.can_fetch(UA, "https://x.com/nope/1")
    assert r.can_fetch(UA, "https://x.com/search-jobs/")   # specific group replaces '*'
    assert r.crawl_delay(UA) == 3
    g = Robots("User-agent: *\nDisallow: */apply\nDisallow: /search-jobs/\n")
    assert not g.can_fetch(UA, "https://x.com/global/en/apply?x=1")
    assert g.can_fetch(UA, "https://x.com/global/en/job/1")
    assert not g.can_fetch(UA, "https://x.com/search-jobs/hanoi")


def test_empty_and_disallow_all():
    assert Robots("").can_fetch(UA, "https://x.com/a")
    assert Robots("User-agent: *\nDisallow:\n").can_fetch(UA, "https://x.com/a")
    assert not Robots(disallow_all=True).can_fetch(UA, "https://x.com/a")
