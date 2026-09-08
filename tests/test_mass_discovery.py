from community_scanner.discovery.commoncrawl import _canonical_community_url
from community_scanner.likelihood import community_likelihood


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
