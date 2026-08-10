from community_scanner.models import DiscoveryHit
from community_scanner.models import Platform
from community_scanner.normalize import normalize_url
from community_scanner.pipeline import job_to_models
from community_scanner.queue import fetch_job_from_candidate


def test_fetch_job_roundtrip():
    hit = DiscoveryHit(url="https://www.skool.com/example", title="Example", provider="seeds", query="q")
    norm = normalize_url(hit.url)
    job = fetch_job_from_candidate(hit, norm)
    hit2, norm2, geo = job_to_models(job)
    assert hit2.url == hit.url
    assert norm2.canonical_key == norm.canonical_key
    assert norm2.platform == Platform.SKOOL
    assert geo == "USA"
