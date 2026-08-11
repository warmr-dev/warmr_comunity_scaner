from community_scanner.classify import classify
from community_scanner.extract import heuristic_extract
from community_scanner.invites import classify_invite_url, find_all_invites_in_text, find_invite_in_text
from community_scanner.models import AccessStatus, ValueTier
from community_scanner.normalize import normalize_url


HTML = """
<html><head><title>Florida CPA Network</title></head>
<body>
<h1>Florida CPA Network</h1>
<p>Join 1,250 members of professional accountants in Florida.</p>
<p>Membership $49/mo</p>
<a href="/join">Join now</a>
<a href="mailto:hello@floridacpa.example">Contact</a>
</body></html>
"""

HTML_WITH_INVITES = """
<html><head><title>IT Channel List</title></head>
<body>
<h1>Best IT chats</h1>
<a href="https://t.me/pythondevs">Python</a>
<a href="https://chat.whatsapp.com/AbCdEfGhIjK">WhatsApp</a>
<a href="https://join.slack.com/t/devguild/shared_invite/zt-abc123">Slack</a>
<p>Also t.me/datascienceusa and discord.gg/ignoreme</p>
</body></html>
"""


def test_heuristic_and_classify():
    norm = normalize_url("https://floridacpa.example")
    item = heuristic_extract(HTML, norm, query="accounting Florida")
    assert item.name == "Florida CPA Network"
    assert item.access_status == AccessStatus.JOIN
    assert item.price_amount == 49
    assert item.size_members == 1250
    assert item.join_url is None
    item = classify(item)
    assert item.value_score >= 45
    assert item.value_tier in {ValueTier.HIGH, ValueTier.MEDIUM}


def test_extract_multiple_invites():
    norm = normalize_url("https://list.example/it")
    item = heuristic_extract(HTML_WITH_INVITES, norm, query="it telegram")
    assert item.join_url is not None
    invites = item.raw_signals.get("all_invites") or []
    urls = {i["url"] for i in invites}
    assert "https://t.me/pythondevs" in urls
    assert "https://chat.whatsapp.com/AbCdEfGhIjK" in urls
    assert any("join.slack.com" in u for u in urls)
    assert "https://t.me/datascienceusa" in urls
    assert "https://discord.gg/ignoreme" in urls


def test_classify_invite_shapes():
    assert classify_invite_url("https://chat.whatsapp.com/AbCdEfGhIjK")
    assert classify_invite_url("https://t.me/+AbCdEfGhIjK")
    assert classify_invite_url("https://t.me/pythondevs")
    assert classify_invite_url("https://join.slack.com/t/foo/shared_invite/zt-1")
    assert classify_invite_url("https://joinhampton.slack.com")
    assert classify_invite_url("https://discord.gg/abcdef")
    assert classify_invite_url("https://wa.me/15551234567") is None
    assert classify_invite_url("https://t.me/share") is None


def test_find_all_invites():
    matches = find_all_invites_in_text(
        "Join t.me/pythonusa and chat.whatsapp.com/Bcode123 and https://t.me/pythonusa again"
    )
    assert len(matches) == 2


def test_whatsapp_canonical_key_unique():
    a = normalize_url("https://chat.whatsapp.com/AAAA")
    b = normalize_url("https://chat.whatsapp.com/BBBB")
    assert a.platform.value == "whatsapp"
    assert a.canonical_key != b.canonical_key


def test_parse_member_count_telegram():
    from community_scanner.invites import MIN_MEMBERS_FOR_UPSERT, parse_member_count

    n, text = parse_member_count("Python Devs — 12 450 subscribers")
    assert n == 12450
    assert text is not None
    assert MIN_MEMBERS_FOR_UPSERT == 100
    tiny, _ = parse_member_count("3 members")
    assert tiny == 3


def test_classify_rejects_small_invite():
    from community_scanner.models import ExtractedCommunity, Platform

    item = ExtractedCommunity(
        website="https://t.me/tiny",
        canonical_key="telegram:tiny",
        canonical_domain="t.me",
        platform=Platform.TELEGRAM,
        platform_id="tiny",
        name="Tiny",
        join_url="https://t.me/tiny",
        size_members=12,
        access_status=AccessStatus.JOIN,
    )
    out = classify(item)
    assert out.access_status == AccessStatus.REJECT
    assert out.value_tier == ValueTier.JUNK


def test_classify_rejects_unknown_size_invite():
    from community_scanner.models import ExtractedCommunity, Platform

    item = ExtractedCommunity(
        website="https://t.me/mystery",
        canonical_key="telegram:mystery",
        canonical_domain="t.me",
        platform=Platform.TELEGRAM,
        platform_id="mystery",
        name="Mystery",
        join_url="https://t.me/mystery",
        size_members=None,
        access_status=AccessStatus.JOIN,
    )
    out = classify(item)
    assert out.access_status == AccessStatus.REJECT
    assert out.raw_signals.get("reject_reason") == "unknown_size"


def test_classify_keeps_whatsapp_without_size():
    from community_scanner.models import ExtractedCommunity, Platform

    item = ExtractedCommunity(
        website="https://chat.whatsapp.com/AbCdEfGhIjK",
        canonical_key="whatsapp:abcdefghijk",
        canonical_domain="chat.whatsapp.com",
        platform=Platform.WHATSAPP,
        platform_id="AbCdEfGhIjK",
        name="IT Devs WA",
        join_url="https://chat.whatsapp.com/AbCdEfGhIjK",
        size_members=None,
        access_status=AccessStatus.JOIN,
    )
    out = classify(item)
    assert out.access_status != AccessStatus.REJECT
    assert out.value_tier != ValueTier.JUNK


def test_classify_keeps_slack_without_size():
    from community_scanner.models import ExtractedCommunity, Platform

    item = ExtractedCommunity(
        website="https://join.slack.com/t/devguild/shared_invite/zt-abc",
        canonical_key="slack:devguild",
        canonical_domain="join.slack.com",
        platform=Platform.SLACK,
        platform_id="devguild",
        name="Dev Guild Slack",
        join_url="https://join.slack.com/t/devguild/shared_invite/zt-abc",
        size_members=None,
        access_status=AccessStatus.JOIN,
    )
    out = classify(item)
    assert out.access_status != AccessStatus.REJECT
    assert out.value_tier != ValueTier.JUNK
