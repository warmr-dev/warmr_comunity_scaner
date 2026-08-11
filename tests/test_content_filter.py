from community_scanner.classify import classify
from community_scanner.content_filter import is_adult_community, is_adult_content, is_adult_platform_id
from community_scanner.discovery.base import QueryParams
from community_scanner.discovery.directory_crawler import DirectoryCrawlerProvider
from community_scanner.extract import heuristic_extract
from community_scanner.models import AccessStatus, Platform, ValueTier
from community_scanner.normalize import looks_like_community, normalize_url


def test_is_adult_content_keywords():
    assert is_adult_content("Best NSFW telegram channels")
    assert is_adult_content("18+ adult community invite")
    assert is_adult_content("Join our OnlyFans creators group")
    assert not is_adult_content("Python programming community for developers")


def test_is_adult_platform_id():
    assert is_adult_platform_id("python_porn_hub")
    assert is_adult_platform_id("@onlyfans_promo")
    assert not is_adult_platform_id("LearnPython3")


def test_is_adult_community_unified():
    assert is_adult_community(name="Adult Chat 18+", url="https://t.me/adult_chat")
    assert not is_adult_community(name="DevOps SRE Notes", url="https://t.me/devops_sre_notes")


def test_looks_like_community_rejects_adult():
    assert not looks_like_community(
        "https://t.me/nsfw_channel",
        "NSFW Telegram Group 18+",
        "adult content invite",
    )


def test_classify_rejects_adult_invite():
    from community_scanner.models import ExtractedCommunity

    item = ExtractedCommunity(
        website="https://t.me/adultgroup",
        canonical_key="telegram:adultgroup",
        canonical_domain="t.me",
        platform=Platform.TELEGRAM,
        platform_id="adultgroup",
        name="18+ Adult Group",
        join_url="https://t.me/adultgroup",
        size_members=5000,
        access_status=AccessStatus.JOIN,
    )
    out = classify(item)
    assert out.access_status == AccessStatus.REJECT
    assert out.raw_signals.get("reject_reason") == "adult_content"


def test_extract_rejects_adult_html():
    html = """
    <html><head><title>NSFW 18+ Group</title></head>
    <body><h1>Adult only porn sharing community</h1>
    <a href="https://t.me/adultgroup">Join</a></body></html>
    """
    norm = normalize_url("https://example.com/list")
    item = heuristic_extract(html, norm)
    assert item.access_status == AccessStatus.REJECT


def test_directory_crawler_skips_adult_channel(monkeypatch):
    provider = DirectoryCrawlerProvider(
        delay=0,
        max_channels_per_site=2,
        sites=("tgstat",),
        min_members=100,
    )

    tag_html = '<a href="https://tgstat.com/channel/@adult_porn/stat">Bad</a>'
    adult_html = """
    <h2>5000</h2><div>subscribers</div>
    <div>Adult 18+ NSFW content</div>
    <a href="https://t.me/adult_porn">Telegram</a>
    """

    def fake_get(url, *, timeout, delay):
        if "/tag/" in url:
            return tag_html
        if "@adult_porn" in url:
            return adult_html
        return None

    monkeypatch.setattr(
        "community_scanner.discovery.directory_crawler._http_get",
        fake_get,
    )

    hits = provider.crawl(QueryParams(niche="python"), count=10)
    assert hits == []
