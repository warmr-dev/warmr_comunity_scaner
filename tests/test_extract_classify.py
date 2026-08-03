from community_scanner.classify import classify
from community_scanner.extract import heuristic_extract
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


def test_heuristic_and_classify():
    norm = normalize_url("https://floridacpa.example")
    item = heuristic_extract(HTML, norm, query="accounting Florida")
    assert item.name == "Florida CPA Network"
    assert item.access_status == AccessStatus.JOIN
    assert item.price_amount == 49
    assert item.size_members == 1250
    item = classify(item)
    assert item.value_score >= 45
    assert item.value_tier in {ValueTier.HIGH, ValueTier.MEDIUM}
