import pytest
from utils.url_utils import normalize_url, get_domain, sha256_bytes

def test_normalize_url_basic():
    raw = "https://Example.com/report.pdf?utm_source=google#page=2"
    expected = "https://example.com/report.pdf"
    assert normalize_url(raw) == expected

def test_normalize_url_tracking_params():
    raw = "https://example.com/data?utm_medium=email&id=42&utm_campaign=winter&page=1&fbclid=123"
    # Parameter non-tracking (id, page) harus dipertahankan dan diurutkan
    expected = "https://example.com/data?id=42&page=1"
    assert normalize_url(raw) == expected

def test_normalize_url_schemes():
    # Hanya http dan https yang diterima
    assert normalize_url("ftp://example.com/file.txt") == ""
    assert normalize_url("javascript:alert(1)") == ""
    assert normalize_url("") == ""
    assert normalize_url(None) == ""
    assert normalize_url("http://EXAMPLE.COM:80/path") == "http://example.com/path"
    assert normalize_url("https://EXAMPLE.COM:443/path") == "https://example.com/path"

def test_get_domain():
    assert get_domain("https://drive.google.com/file/d/123/view") == "drive.google.com"
    assert get_domain("http://Example.COM:8080/index.html") == "example.com"
    assert get_domain("invalid-url") == "unknown"
    assert get_domain("") == "unknown"

def test_sha256_bytes():
    b1 = b"hello osint world"
    b2 = b"hello osint world"
    b3 = b"different content"

    hash1 = sha256_bytes(b1)
    hash2 = sha256_bytes(b2)
    hash3 = sha256_bytes(b3)

    assert hash1 == hash2
    assert hash1 != hash3
    assert len(hash1) == 64
    assert sha256_bytes(b"") == ""
