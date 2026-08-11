from community_scanner.classify import classify
from community_scanner.extract import heuristic_extract
from community_scanner.invites import classify_invite_url, find_invite_in_text
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

HTML_WITH_INVITE = """
<html><head><title>Dev Guild</title></head>
<body>
<h1>Dev Guild Telegram</h1>
<p>Join our community of 2,400 members.</p>
<a href="https://t.me/devguild_it">Join Telegram</a>
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


def test_extract_telegram_invite():
    norm = normalize_url("https://devguild.example")
    item = heuristic_extract(HTML_WITH_INVITE, norm, query="it telegram")
    assert item.join_url == "https://t.me/devguild_it"
    assert item.raw_signals["join_url_source"]["platform"] == "telegram"


def test_classify_invite_shapes():
    assert classify_invite_url("https://chat.whatsapp.com/AbCdEfGhIjK")
    assert classify_invite_url("https://t.me/+AbCdEfGhIjK")
    assert classify_invite_url("https://t.me/pythondevs")
    assert classify_invite_url("https://whatsapp.com/channel/AbCdEf")
    # Discord / Slack disabled
    assert classify_invite_url("https://discord.gg/abcdef") is None
    assert classify_invite_url("https://join.slack.com/t/foo/shared_invite/zt-1") is None
    assert classify_invite_url("https://wa.me/15551234567") is None
    assert classify_invite_url("https://t.me/share") is None


def test_find_invite_bare_telegram():
    match = find_invite_in_text("Join us at t.me/accountingpros today")
    assert match is not None
    assert match.url == "https://t.me/accountingpros"
