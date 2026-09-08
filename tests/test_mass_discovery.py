from community_scanner.discovery.commoncrawl import _canonical_community_url
from community_scanner.likelihood import community_likelihood
from community_scanner.models import DiscoveryHit
from community_scanner.store import make_engine, make_session_factory, upsert_raw_candidates
from community_scanner.models import Base


def test_likelihood_skool_high():
    score = community_likelihood("https://www.skool.com/florida-cpa/about")
    assert score >= 0.85


def test_likelihood_homepage_low():
    score = community_likelihood("https://www.skool.com/")
    assert score < 0.4


def test_cc_canonical_skool():
    assert (
        _canonical_community_url(
            "https://www.skool.com/0-to-code-hero-1008/about?utm_source=x"
        )
        == "https://www.skool.com/0-to-code-hero-1008"
    )


def test_cc_canonical_slack():
    url = (
        "https://join.slack.com/t/18xxgames/shared_invite/"
        "zt-8ksy028m-CSZC~G5QtiFv60_jdqqulQ"
    )
    assert _canonical_community_url(url) == url


def test_raw_candidates_upsert(tmp_path):
    db = tmp_path / "t.db"
    url = f"sqlite:///{db}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    Session = make_session_factory(url)
    hits = [
        DiscoveryHit(
            url="https://www.skool.com/test-community-abc",
            title="Test",
            snippet="likelihood probe",
            provider="commoncrawl",
            query="*.skool.com/*",
        ),
        DiscoveryHit(
            url="https://www.skool.com/test-community-abc",
            title="Test",
            snippet="dup",
            provider="commoncrawl",
            query="*.skool.com/*",
        ),
    ]
    with Session() as session:
        stats = upsert_raw_candidates(session, hits, min_likelihood=0.4)
        session.commit()
    assert stats["inserted"] == 1
    assert stats["dup"] == 1
