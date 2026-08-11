from community_scanner.discovery.base import DEFAULT_SCAN_GEO, QueryParams, generate_queries, resolve_geo


def test_default_geo_is_usa():
    queries = generate_queries(QueryParams(niche="it"), limit=8)
    assert queries
    assert any("telegram" in q.lower() or "t.me" in q.lower() or "whatsapp" in q.lower() for q in queries)


def test_tg_wa_slack_directory_templates():
    queries = generate_queries(QueryParams(niche="education"), limit=40)
    blob = " ".join(queries).lower()
    assert "tgstat" in blob or "t.me" in blob
    assert "whatsapp" in blob or "chat.whatsapp" in blob
    assert "slack" in blob or "join.slack" in blob
    assert "discord" not in blob
    assert "disboard" not in blob


def test_no_paid_dictionary_trap():
    queries = generate_queries(QueryParams(niche="accounting"), limit=20)
    assert not any(q.lower().startswith("paid ") for q in queries)
    assert not any(q.lower().startswith("professional ") for q in queries)


def test_resolve_geo_fallback():
    assert resolve_geo(None) == DEFAULT_SCAN_GEO
    assert resolve_geo("") == DEFAULT_SCAN_GEO
    assert resolve_geo("  ") == DEFAULT_SCAN_GEO
