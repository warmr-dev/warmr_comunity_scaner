from community_scanner.classify import classify
from community_scanner.language_filter import (
    contains_non_latin_script,
    is_non_english_community,
    is_official_junk_handle,
    is_regional_tgstat_url,
)
from community_scanner.models import AccessStatus, Platform, ValueTier


def test_cyrillic_is_non_english():
    assert contains_non_latin_script("Канал про Python")
    assert is_non_english_community(name="DevOps сообщество", platform_id="devops_ru")


def test_language_suffix_in_handle():
    assert is_non_english_community(platform_id="France24_es")
    assert is_non_english_community(platform_id="animeon_su")
    assert not is_non_english_community(platform_id="LearnPython3")


def test_official_junk_handles():
    assert is_official_junk_handle("telegram")
    assert is_official_junk_handle("desktop")
    assert is_official_junk_handle("CercoLavoroBot")
    assert not is_official_junk_handle("devops_sre_notes")


def test_regional_tgstat_urls():
    assert is_regional_tgstat_url("https://tgstat.ru/en/channel/@foo")
    assert is_regional_tgstat_url("https://uk.tgstat.com/en/channel/@foo")
    assert not is_regional_tgstat_url("https://tgstat.com/channel/@foo")


def test_classify_rejects_non_english():
    from community_scanner.models import ExtractedCommunity

    item = ExtractedCommunity(
        website="https://t.me/devops_ru",
        canonical_key="telegram:devops_ru",
        canonical_domain="t.me",
        platform=Platform.TELEGRAM,
        platform_id="devops_ru",
        name="DevOps на русском",
        join_url="https://t.me/devops_ru",
        size_members=5000,
        access_status=AccessStatus.JOIN,
    )
    out = classify(item)
    assert out.access_status == AccessStatus.REJECT
    assert out.raw_signals.get("reject_reason") == "non_english"


def test_classify_rejects_official_telegram():
    from community_scanner.models import ExtractedCommunity

    item = ExtractedCommunity(
        website="https://t.me/telegram",
        canonical_key="telegram:telegram",
        canonical_domain="t.me",
        platform=Platform.TELEGRAM,
        platform_id="telegram",
        name="Telegram",
        join_url="https://t.me/telegram",
        size_members=100000,
        access_status=AccessStatus.JOIN,
    )
    out = classify(item)
    assert out.access_status == AccessStatus.REJECT
    assert out.value_tier == ValueTier.JUNK
