from __future__ import annotations

from community_scanner.content_filter import is_adult_community
from community_scanner.language_filter import is_non_english_community
from community_scanner.etalons import match_etalon
from community_scanner.models import AccessStatus, ExtractedCommunity, Platform, ValueTier


def classify(item: ExtractedCommunity) -> ExtractedCommunity:
    """Assign access_status refinements + value_score/tier.

    Warmr gold etalons (Hampton, Ramen Club, Chief, ...) force high tier.
    """
    from community_scanner.normalize import JUNK_HINTS, looks_like_community

    score = 0
    signals: dict = dict(item.raw_signals)

    if item.access_status == AccessStatus.REJECT:
        item.value_score = 0
        item.value_tier = ValueTier.JUNK
        return item

    if is_adult_community(
        name=item.name,
        url=item.website,
        platform_id=item.platform_id,
        snippet=str(item.raw_signals),
        html=item.join_url,
    ):
        item.access_status = AccessStatus.REJECT
        item.value_tier = ValueTier.JUNK
        item.value_score = 0
        item.raw_signals = {**signals, "reject_reason": "adult_content"}
        return item

    if is_non_english_community(
        name=item.name,
        url=item.website,
        platform_id=item.platform_id,
        snippet=str(item.raw_signals),
        html=item.join_url,
    ):
        item.access_status = AccessStatus.REJECT
        item.value_tier = ValueTier.JUNK
        item.value_score = 0
        item.raw_signals = {**signals, "reject_reason": "non_english"}
        return item

    # Require meaningful audience for invite links.
    # WhatsApp/Slack rarely expose public counts — allow unknown size for them.
    from community_scanner.invites import SIZE_OPTIONAL_PLATFORMS

    platform_lc = getattr(item.platform, "value", str(item.platform or "")).lower()
    size_optional = platform_lc in SIZE_OPTIONAL_PLATFORMS

    if item.size_members is not None and item.size_members < 100:
        item.access_status = AccessStatus.REJECT
        item.value_tier = ValueTier.JUNK
        item.value_score = 0
        item.raw_signals = {**signals, "reject_reason": "too_small"}
        return item

    if item.join_url and item.size_members is None and not size_optional:
        item.access_status = AccessStatus.REJECT
        item.value_tier = ValueTier.JUNK
        item.value_score = 0
        item.raw_signals = {**signals, "reject_reason": "unknown_size"}
        return item

    # Reject dictionary / tax-software / explainer SERP noise after fetch
    blob = " ".join(filter(None, [item.name, item.website, item.join_url]))
    if JUNK_HINTS.search(blob) and not looks_like_community(item.website, item.name, None):
        item.access_status = AccessStatus.REJECT
        item.value_tier = ValueTier.JUNK
        item.value_score = 0
        signals["reject_reason"] = "junk_serp"
        item.raw_signals = signals
        return item

    etalon = match_etalon(item.name, item.website, item.platform_id)
    if etalon:
        signals["warmr_gold_etalon"] = etalon.get("name")
        signals["warmr_tier"] = etalon.get("tier")
        if etalon.get("entry_cost"):
            item.price_amount = float(etalon["entry_cost"])
            item.currency = "USD"
            item.price_text = f"etalon entry_cost={etalon['entry_cost']}"
        if etalon.get("is_paid_membership"):
            item.is_professional = True
        # Known valuable inventory — keep as high regardless of thin public page
        item.value_score = max(85, int(min(100, 70 + (etalon.get("lead_price_base") or 0) / 20)))
        item.value_tier = ValueTier.HIGH
        if item.access_status == AccessStatus.WATCH and (etalon.get("join_link") or item.join_url):
            item.access_status = AccessStatus.APPLY if etalon.get("visibility") == "private" else AccessStatus.JOIN
        item.raw_signals = signals
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
        # Warmr-like: higher entry cost ≈ higher lead value potential
        if item.price_amount >= 1000:
            score += 20
            signals["high_ticket"] = True
        elif item.price_amount >= 100:
            score += 10
    if item.size_members:
        if item.size_members >= 1000:
            score += 20
        elif item.size_members >= 200:
            score += 12
        elif item.size_members >= 50:
            score += 6
        else:
            score -= 10
            signals["too_small"] = True
    if item.is_professional:
        score += 15
    if item.platform in {
        Platform.SKOOL,
        Platform.CIRCLE,
        Platform.DISCORD,
        Platform.SLACK,
        Platform.TELEGRAM,
        Platform.WHATSAPP,
    }:
        score += 12
        if item.platform == Platform.SLACK:
            score += 8
            signals["slack_bonus"] = True
        if item.platform == Platform.TELEGRAM and item.size_members and item.size_members >= 1000:
            score += 8
            signals["telegram_size_bonus"] = True
        if item.platform == Platform.WHATSAPP:
            score += 4
            signals["whatsapp_bonus"] = True
    if item.access_status in {AccessStatus.JOIN, AccessStatus.APPLY}:
        score += 10
    if item.join_url:
        score += 5

    # Founder / agency / paid-community language
    blob = " ".join(
        filter(
            None,
            [
                item.name,
                item.website,
                item.niche,
                item.audience,
                str(item.raw_signals),
            ],
        )
    ).lower()
    for token in ("founder", "agency", "saas", "ceo", "operator", "membership", "paid community"):
        if token in blob:
            score += 4
            signals.setdefault("keywords", []).append(token)

    score = max(0, min(100, score))

    if score >= 70:
        tier = ValueTier.HIGH
    elif score >= 45:
        tier = ValueTier.MEDIUM
    elif score >= 20:
        tier = ValueTier.LOW
    else:
        tier = ValueTier.JUNK

    if item.access_status not in {AccessStatus.JOIN, AccessStatus.APPLY, AccessStatus.REJECT}:
        if tier in {ValueTier.HIGH, ValueTier.MEDIUM} and not item.join_url:
            item.access_status = AccessStatus.WATCH

    item.value_score = score
    item.value_tier = tier
    item.raw_signals = signals
    return item
