from community_scanner.discovery.base import QueryParams
from community_scanner.discovery.directory_crawler import (
    DirectoryCrawlerProvider,
    extract_tgstat_channel_urls,
    niche_to_tag,
    parse_tgstat_subscribers,
    primary_telegram_invite,
)

TAG_HTML = """
<a href="https://tgstat.com/channel/@LearnPython3/stat">Learn Python</a>
<a href="https://tgstat.ru/en/channel/@python2day/stat">Python Today</a>
"""

CHANNEL_HTML = """
<div class="font-24 bold">Learn Python 3</div>
<h2 class="text-center">124 804</h2>
<div class="text-uppercase font-12">subscribers</div>
<a href="https://t.me/LearnPython3">Telegram</a>
<a href="https://t.me/TGStat">TGStat</a>
"""


def test_niche_to_tag_aliases():
    assert niche_to_tag("software-engineering") == "programming"
    assert niche_to_tag("devops") == "devops"


def test_extract_tgstat_channel_urls():
    urls = extract_tgstat_channel_urls(TAG_HTML)
    assert "https://tgstat.com/channel/@LearnPython3" in urls
    assert "https://tgstat.com/channel/@python2day" in urls


def test_parse_tgstat_subscribers():
    size, text = parse_tgstat_subscribers(CHANNEL_HTML)
    assert size == 124804
    assert text is not None


def test_primary_telegram_invite_prefers_channel_handle():
    url = primary_telegram_invite(CHANNEL_HTML, "@LearnPython3")
    assert url == "https://t.me/LearnPython3"


def test_directory_provider_crawl_with_mocked_tgstat(monkeypatch):
    provider = DirectoryCrawlerProvider(
        delay=0,
        max_channels_per_site=2,
        sites=("tgstat",),
        min_members=100,
    )

    def fake_get(url, *, timeout, delay):
        if "/tag/" in url or "search=" in url:
            return TAG_HTML
        if "@LearnPython3" in url:
            return CHANNEL_HTML
        if "@python2day" in url:
            return """
            <h2 class="text-center">50</h2><div>subscribers</div>
            <a href="https://t.me/python2day">Telegram</a>
            """
        return None

    monkeypatch.setattr(
        "community_scanner.discovery.directory_crawler._http_get",
        fake_get,
    )

    hits = provider.crawl(QueryParams(niche="python"), count=10)
    assert len(hits) == 1
    assert hits[0].url == "https://t.me/LearnPython3"
    assert hits[0].provider == "directory"
    assert "124" in (hits[0].snippet or "")
