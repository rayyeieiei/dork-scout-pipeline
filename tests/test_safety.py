import pytest
from utils.safety import validate_query_safety

def test_safe_queries():
    safe_topics = [
        "renewable energy indonesia",
        "soal tka matematika sma",
        "laporan keuangan pt telkom 2025",
        "ai startup landscape",
        "agritech indonesia dataset"
    ]
    for topic in safe_topics:
        is_safe, reason = validate_query_safety(topic)
        assert is_safe is True, f"Topic '{topic}' should be safe, got: {reason}"

def test_prohibited_queries():
    unsafe_topics = [
        ".env password database",
        "mysql database dump credentials",
        "id_rsa private key",
        "wp-config.php leak",
        "shadow file leak",
        "admin:password list",
        "cve-2024-1234 exploit"
    ]
    for topic in unsafe_topics:
        is_safe, reason = validate_query_safety(topic)
        assert is_safe is False, f"Topic '{topic}' should be prohibited!"
