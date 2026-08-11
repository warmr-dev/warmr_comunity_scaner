from community_scanner.classify import classify
from community_scanner.extract import heuristic_extract
from community_scanner.invites import classify_invite_url
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
<h1>Dev Guild Slack</h1>
<p>Join our community of 2,400 members.</p>
<a href="https://join.slack.com/t/devguild/shared_invite/zt-abc123">Join Slack</a>
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


def test_extract_slack_invite():
    norm = normalize_url("https://devguild.example")
    item = heuristic_extract(HTML_WITH_INVITE, norm, query="it slack")
    assert item.join_url == "https://join.slack.com/t/devguild/shared_invite/zt-abc123"
    assert item.raw_signals["join_url_source"]["platform"] == "slack"


def test_classify_invite_shapes():
    assert classify_invite_url("https://join.slack.com/t/foo/shared_invite/zt-1")
    assert classify_invite_url("https://chat.whatsapp.com/AbCdEfGhIjK")
    assert classify_invite_url("https://t.me/+AbCdEfGhIjK")
    assert classify_invite_url("https://discord.gg/abcdef")
    assert classify_invite_url("https://joinhampton.slack.com")
    assert classify_invite_url("https://slack.com") is None
    assert classify_invite_url("https://wa.me/15551234567") is None
    assert classify_invite_url("https://t.me/share") is None
