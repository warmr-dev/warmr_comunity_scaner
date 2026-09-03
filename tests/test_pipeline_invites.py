from community_scanner.models import DiscoveryHit
from community_scanner.pipeline import _expand_discovery_invite_hits, _invites_from_hit


def test_invites_from_hit_keeps_active_platforms_only():
    hit = DiscoveryHit(
        url="https://example.com/list",
        title="Top community links",
        snippet=(
            "Join https://discord.gg/abc123 and https://t.me/+SecretHash "
            "plus https://join.slack.com/t/workspace/shared_invite/xyz "
            "and https://www.skool.com/makers"
        ),
        provider="searxng",
        query="slack invite",
    )
    invites = _invites_from_hit(hit)
    urls = {invite.url.lower().rstrip("/") for invite in invites}
    platforms = {invite.platform for invite in invites}
    assert "https://join.slack.com/t/workspace/shared_invite/xyz" in urls
    assert "https://www.skool.com/makers" in urls
    assert any("t.me" in url for url in urls)
    assert "discord" not in platforms
    assert {"slack", "skool", "telegram"} <= platforms


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
    assert len(expanded) == 3
    assert any(hit.url.startswith("https://www.reddit.com/r/devops") for hit in expanded)
    assert any(hit.url.startswith("https://join.slack.com/") for hit in expanded)
