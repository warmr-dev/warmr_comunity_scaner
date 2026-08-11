from community_scanner.classify import classify
from community_scanner.language_filter import (
    contains_cyrillic,
    is_official_junk_handle,
    is_russian_community,
    is_russian_tgstat_url,
)
from community_scanner.models import AccessStatus, Platform, ValueTier


def test_cyrillic_is_russian():
    assert contains_cyrillic("Канал про Python")
    assert is_russian_community(name="DevOps сообщество", platform_id="devops_ru")


def test_non_russian_languages_allowed():
    assert not is_russian_community(platform_id="France24_es")
    assert not is_russian_community(platform_id="gate_zh")
    assert not is_russian_community(name="Canal de programación en español", platform_id="dev_es")
    assert not is_russian_community(name="Canale Python Italia", platform_id="python_it")


def test_russian_handle_suffixes():
    assert is_russian_community(platform_id="devops_ru")
    assert is_russian_community(platform_id="animeon_su")
    assert not is_russian_community(platform_id="LearnPython3")


def test_official_junk_handles():
    assert is_official_junk_handle("telegram")
    assert is_official_junk_handle("desktop")
    assert not is_official_junk_handle("devops_sre_notes")


def test_russian_tgstat_urls():
    assert is_russian_tgstat_url("https://tgstat.ru/en/channel/@foo")
    assert not is_russian_tgstat_url("https://uk.tgstat.com/en/channel/@foo")
    assert not is_russian_tgstat_url("https://tgstat.com/channel/@foo")


def test_classify_rejects_russian():
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
    assert out.raw_signals.get("reject_reason") == "russian_content"


def test_classify_allows_spanish():
    from community_scanner.models import ExtractedCommunity

    item = ExtractedCommunity(
        website="https://t.me/France24_es",
        canonical_key="telegram:france24_es",
        canonical_domain="t.me",
        platform=Platform.TELEGRAM,
        platform_id="France24_es",
        name="France 24 Español",
        join_url="https://t.me/France24_es",
        size_members=5000,
        access_status=AccessStatus.JOIN,
    )
    out = classify(item)
    assert out.access_status != AccessStatus.REJECT


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
