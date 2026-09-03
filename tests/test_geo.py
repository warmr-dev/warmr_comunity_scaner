from community_scanner.discovery.base import DEFAULT_SCAN_GEO, QueryParams, generate_queries, resolve_geo


def test_default_geo_is_usa():
    queries = generate_queries(QueryParams(niche="it"), limit=8)
    assert queries
    assert any("slack" in q.lower() or "skool" in q.lower() or "paid" in q.lower() for q in queries)


def test_all_platform_directory_templates():
    queries = generate_queries(QueryParams(niche="education"), limit=50)
    blob = " ".join(queries).lower()
    assert "slack" in blob or "join.slack" in blob
    assert "skool" in blob or "circle" in blob
    assert "paid" in blob or "mastermind" in blob or "membership" in blob


def test_no_paid_dictionary_trap():
    queries = generate_queries(QueryParams(niche="accounting"), limit=20)
    assert not any(q.lower().startswith("paid ") for q in queries)
    assert not any(q.lower().startswith("professional ") for q in queries)


def test_harvest_queries_are_invite_first():
    queries = generate_queries(QueryParams(niche="harvest"), limit=25, harvest=True)
    blob = " ".join(queries).lower()
    assert "join.slack" in blob or "shared_invite" in blob
    assert "skool" in blob or "circle" in blob
    assert "paid" in blob or "mastermind" in blob or "founder" in blob


def test_harvest_with_niche_appends_soft_variants():
    queries = generate_queries(QueryParams(niche="devops"), limit=40, harvest=True)
    assert any("devops" in q.lower() for q in queries)
    assert any(("inurl:" in q.lower() or "site:" in q.lower()) and "devops" not in q.lower() for q in queries)


def test_resolve_geo_fallback():
    assert resolve_geo(None) == DEFAULT_SCAN_GEO
    assert resolve_geo("") == DEFAULT_SCAN_GEO
    assert resolve_geo("  ") == DEFAULT_SCAN_GEO
