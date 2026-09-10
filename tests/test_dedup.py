import pytest
from unittest.mock import MagicMock, patch
from utils.url_utils import normalize_url, sha256_bytes
from agents.data_parser import ContentHashRegistry, DataParser, DomainRateLimiter
from utils.stats import PipelineStats

def test_url_deduplication_set():
    urls = [
        "https://example.com/a.pdf?utm_source=twitter",
        "https://example.com/a.pdf?utm_source=facebook",
        "https://EXAMPLE.COM/a.pdf",
        "https://example.com/b.pdf"
    ]
    seen = set()
    unique = []
    duplicates = 0
    for u in urls:
        norm = normalize_url(u)
        if norm not in seen:
            seen.add(norm)
            unique.append(norm)
        else:
            duplicates += 1

    assert len(unique) == 2
    assert duplicates == 2
    assert "https://example.com/a.pdf" in seen
    assert "https://example.com/b.pdf" in seen

def test_content_hash_registry():
    registry = ContentHashRegistry()
    content_a = b"Common duplicate PDF report bytes"
    hash_a = sha256_bytes(content_a)

    is_dup1, orig1 = registry.check_and_register(hash_a, "https://domain-a.com/report.pdf")
    assert is_dup1 is False
    assert orig1 is None

    is_dup2, orig2 = registry.check_and_register(hash_a, "https://domain-b.com/copy.pdf")
    assert is_dup2 is True
    assert orig2 == "https://domain-a.com/report.pdf"

def test_domain_rate_limiter():
    limiter = DomainRateLimiter(max_per_domain=2)
    limiter.acquire("example.com")
    limiter.acquire("example.com")
    limiter.release("example.com")
    limiter.release("example.com")
    # Tidak boleh ada exception atau deadlock
    assert True

def test_data_parser_duplicate_content_flow():
    parser = DataParser()
    stats = PipelineStats()

    # Mock response returning duplicate bytes
    mock_resp = MagicMock()
    mock_resp.content = b"identical duplicate document content"
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.text = "identical duplicate document content"
    mock_resp.raise_for_status = MagicMock()

    with patch("agents.data_parser.get_thread_session") as mock_session_getter:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_getter.return_value = mock_session

        item1 = {"link": "https://site-a.com/doc.html", "title": "Doc A", "snippet": ""}
        item2 = {"link": "https://site-b.com/doc.html", "title": "Doc B", "snippet": ""}

        res1 = parser.parse_url(item1, "test topic", "dork 1", stats=stats)
        assert res1["status"] == "success"
        assert res1["duplicate_of"] is None
        assert res1["content_sha256"] != ""

        res2 = parser.parse_url(item2, "test topic", "dork 1", stats=stats)
        assert res2["status"] == "duplicate_content"
        assert res2["duplicate_of"] == "https://site-a.com/doc.html"
        assert stats.duplicate_content == 1
