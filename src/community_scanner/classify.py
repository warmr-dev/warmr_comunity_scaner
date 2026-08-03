from __future__ import annotations

from community_scanner.models import AccessStatus, ExtractedCommunity, Platform, ValueTier


def classify(item: ExtractedCommunity) -> ExtractedCommunity:
    """Assign access_status refinements + value_score/tier."""
    score = 0
    signals: dict = dict(item.raw_signals)

    if item.access_status == AccessStatus.REJECT:
        item.value_score = 0
        item.value_tier = ValueTier.JUNK
        return item

    # Weak pages / missing identity
    if not item.name and item.platform == Platform.CUSTOM:
        item.access_status = AccessStatus.REJECT
        item.value_tier = ValueTier.JUNK
        item.value_score = 0
        signals["reject_reason"] = "no_name"
        item.raw_signals = signals
        return item

    if item.price_amount and item.price_amount > 0:
        score += 25
        signals["paid"] = True
    if item.size_members:
        if item.size_members >= 1000:
            score += 25
        elif item.size_members >= 200:
            score += 15
        elif item.size_members >= 50:
            score += 8
        else:
            score -= 10
            signals["too_small"] = True
    if item.is_professional:
        score += 20
    if item.platform in {Platform.SKOOL, Platform.CIRCLE, Platform.DISCORD, Platform.SLACK}:
        score += 10
    if item.access_status in {AccessStatus.JOIN, AccessStatus.APPLY}:
        score += 10
    if item.join_url:
        score += 5

    score = max(0, min(100, score))

    if score >= 70:
        tier = ValueTier.HIGH
    elif score >= 45:
        tier = ValueTier.MEDIUM
    elif score >= 20:
        tier = ValueTier.LOW
    else:
        tier = ValueTier.JUNK

    # Keep Watch when we lack join/apply clarity
    if item.access_status not in {AccessStatus.JOIN, AccessStatus.APPLY, AccessStatus.REJECT}:
        if tier in {ValueTier.HIGH, ValueTier.MEDIUM} and not item.join_url:
            item.access_status = AccessStatus.WATCH

    item.value_score = score
    item.value_tier = tier
    item.raw_signals = signals
    return item
