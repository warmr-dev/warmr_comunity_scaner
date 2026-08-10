from community_scanner.normalize import looks_like_community, normalize_url
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


def test_discord_home_kept_for_volume():
    n = normalize_url("https://discordapp.com/")
    assert not n.is_blocked
    assert n.canonical_key == "site:discordapp.com"


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


def test_dictionary_kept_for_volume():
    n = normalize_url("https://www.merriam-webster.com/dictionary/professional")
    assert not n.is_blocked


def test_looks_like_community_positive():
    assert looks_like_community(
        "https://accountantforums.com/",
        "Accountant Forums",
        "Join the accounting community",
    )


def test_looks_like_community_rejects_dictionary():
    assert not looks_like_community(
        "https://dictionary.com/browse/professional",
        "professional definition",
        "Meaning of professional",
    )


def test_looks_like_community_rejects_payed_vs_paid():
    assert not looks_like_community(
        "https://grammarly.com/blog/paid-payed",
        "Payed vs Paid",
        "What's the correct spelling?",
    )
