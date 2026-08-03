from community_scanner.classify import classify
from community_scanner.models import AccessStatus, ExtractedCommunity, Platform, ValueTier


def test_hampton_etalon_forces_high():
    item = ExtractedCommunity(
        website="https://joinhampton.slack.com",
        canonical_key="slack:joinhampton",
        canonical_domain="joinhampton.slack.com",
        platform=Platform.SLACK,
        platform_id="joinhampton",
        name="Hampton Slack",
        access_status=AccessStatus.WATCH,
    )
    out = classify(item)
    assert out.value_tier == ValueTier.HIGH
    assert out.value_score >= 85
    assert out.raw_signals.get("warmr_gold_etalon") == "Hampton"
    assert out.price_amount == 8000


def test_chief_etalon():
    item = ExtractedCommunity(
        website="https://members.chief.com",
        canonical_key="site:members.chief.com",
        canonical_domain="members.chief.com",
        platform=Platform.CUSTOM,
        name="Chief",
        access_status=AccessStatus.WATCH,
    )
    out = classify(item)
    assert out.value_tier == ValueTier.HIGH
    assert out.raw_signals.get("warmr_gold_etalon") == "Chief"
