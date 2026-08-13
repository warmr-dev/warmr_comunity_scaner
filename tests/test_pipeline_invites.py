from community_scanner.models import DiscoveryHit
from community_scanner.pipeline import _expand_discovery_invite_hits, _invites_from_hit


def test_invites_from_hit_reads_snippet_invites():
    hit = DiscoveryHit(
        url="https://example.com/list",
        title="Top Telegram groups",
        snippet="Join https://discord.gg/abc123 and https://t.me/+SecretHash today",
        provider="searxng",
        query="inurl:t.me/+",
    )
    invites = _invites_from_hit(hit)
    urls = {invite.url.lower().rstrip("/") for invite in invites}
    assert "https://discord.gg/abc123" in urls
    assert any("t.me" in url for url in urls)


def test_expand_discovery_invite_hits_promotes_snippet_urls():
    hits = [
        DiscoveryHit(
            url="https://reddit.com/r/devops/comments/abc",
            title="DevOps chats",
            snippet="Our Slack: https://join.slack.com/t/workspace/shared_invite/xyz",
            provider="searxng",
            query="devops slack invite",
        )
    ]
    expanded = _expand_discovery_invite_hits(hits)
    assert len(expanded) == 2
    assert any(hit.url.startswith("https://join.slack.com/") for hit in expanded)
