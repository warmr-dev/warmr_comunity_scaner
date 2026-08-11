from community_scanner.discovery.base import DEFAULT_SCAN_GEO, QueryParams, generate_queries, resolve_geo


def test_default_geo_is_usa():
    queries = generate_queries(QueryParams(niche="accounting"), limit=8)
    assert queries
    assert any("USA" in q or "slack" in q.lower() or "whatsapp" in q.lower() for q in queries)


def test_invite_first_templates():
    queries = generate_queries(QueryParams(niche="accounting"), limit=20)
    blob = " ".join(queries).lower()
    assert "join.slack.com" in blob or "shared_invite" in blob
    assert "chat.whatsapp.com" in blob or "whatsapp" in blob
    assert "t.me" in blob or "telegram" in blob
    assert "discord" in blob
    assert "skool.com" not in blob


def test_no_paid_dictionary_trap():
    queries = generate_queries(QueryParams(niche="accounting"), limit=20)
    assert not any(q.lower().startswith("paid ") for q in queries)
    assert not any(q.lower().startswith("professional ") for q in queries)


def test_resolve_geo_fallback():
    assert resolve_geo(None) == DEFAULT_SCAN_GEO
    assert resolve_geo("") == DEFAULT_SCAN_GEO
    assert resolve_geo("  ") == DEFAULT_SCAN_GEO
