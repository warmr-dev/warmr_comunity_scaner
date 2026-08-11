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
    assert not any("discord" in u for u in urls)


def test_classify_invite_shapes():
    assert classify_invite_url("https://chat.whatsapp.com/AbCdEfGhIjK")
    assert classify_invite_url("https://t.me/+AbCdEfGhIjK")
    assert classify_invite_url("https://t.me/pythondevs")
    assert classify_invite_url("https://join.slack.com/t/foo/shared_invite/zt-1")
    assert classify_invite_url("https://joinhampton.slack.com")
    assert classify_invite_url("https://discord.gg/abcdef") is None
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
