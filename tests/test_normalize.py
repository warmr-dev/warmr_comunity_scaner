from community_scanner.normalize import normalize_url
from community_scanner.models import Platform


def test_custom_site_key():
    n = normalize_url("https://www.accounting-club.com/join")
    assert n.platform == Platform.CUSTOM
    assert n.canonical_domain == "accounting-club.com"
    assert n.canonical_key == "site:accounting-club.com"
    assert not n.is_blocked


def test_discord_platform_id():
    n = normalize_url("https://discord.gg/AbCdEf")
    assert n.platform == Platform.DISCORD
    assert n.platform_id == "AbCdEf"
    assert n.canonical_key == "discord:abcdef"
    assert not n.is_blocked


def test_skool_platform_id():
    n = normalize_url("https://www.skool.com/florida-cpa/about")
    assert n.platform == Platform.SKOOL
    assert n.platform_id == "florida-cpa"
    assert n.canonical_key == "skool:florida-cpa"


def test_same_domain_different_communities():
    a = normalize_url("https://www.skool.com/alpha")
    b = normalize_url("https://www.skool.com/beta")
    assert a.canonical_domain == b.canonical_domain == "skool.com"
    assert a.canonical_key != b.canonical_key


def test_blocked_google():
    n = normalize_url("https://www.google.com/search?q=test")
    assert n.is_blocked
