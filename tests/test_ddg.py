from community_scanner.discovery.ddg import DuckDuckGoProvider, _unwrap_ddg_url


def test_unwrap_ddg_url():
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fdiscord.gg%2Fabc123&rut=x"
    assert _unwrap_ddg_url(href) == "https://discord.gg/abc123"


def test_ddg_search_smoke(monkeypatch):
    html = """
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ft.me%2F%2BSecretHash">
      Telegram invite
    </a>
    <a class="result__snippet">Join our group</a>
    """

    class FakeResp:
        status_code = 200
        text = html

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResp()

    monkeypatch.setattr("community_scanner.discovery.ddg.httpx.Client", FakeClient)
    provider = DuckDuckGoProvider(delay=0)
    hits = provider.search("inurl:t.me/+", count=5)
    assert len(hits) == 1
    assert hits[0].url.startswith("https://t.me/")
