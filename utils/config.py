import os
import logging
from dataclasses import dataclass
from typing import Any
from dotenv import load_dotenv

# Load .env file
load_dotenv()

def _get_env_int(key: str, default: int) -> int:
    """Mengambil environment variable integer secara defensif dengan fallback."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (ValueError, TypeError):
        return default

def _get_env_float(key: str, default: float) -> float:
    """Mengambil environment variable float secara defensif dengan fallback."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except (ValueError, TypeError):
        return default

def _get_env_str(key: str, default: str) -> str:
    """Mengambil environment variable string dengan fallback."""
    val = os.getenv(key)
    if val is None or not val.strip():
        return default
    return val.strip()

def _get_env_bool(key: str, default: bool) -> bool:
    """Mengambil environment variable boolean dengan fallback."""
    raw = os.getenv(key)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in ("true", "1", "yes", "y", "on"):
        return True
    if val in ("false", "0", "no", "n", "off"):
        return False
    return default

@dataclass(frozen=True)
class AppConfig:
    # Concurrency & Networking
    MAX_WORKERS: int
    MAX_REQUESTS_PER_DOMAIN: int
    HTTP_TIMEOUT: float
    HTTP_RETRIES: int
    HTTP_BACKOFF_FACTOR: float

    # File Size & Limit Guardrails
    MAX_HTML_MB: float
    MAX_PDF_MB: float
    MAX_DOWNLOAD_MB: float
    PDF_MAX_PAGES: int

    # Search & Identity
    USER_AGENT: str
    SEARCH_PROVIDER: str
    LOG_LEVEL: str
    LOG_FILE: str

    # API Keys
    SERPAPI_API_KEY: str
    GOOGLE_API_KEY: str
    GOOGLE_CSE_ID: str

def load_config() -> AppConfig:
    """Membuat instance AppConfig dari environment variables dengan fallback defensif."""
    return AppConfig(
        MAX_WORKERS=_get_env_int("MAX_WORKERS", 6),
        MAX_REQUESTS_PER_DOMAIN=_get_env_int("MAX_REQUESTS_PER_DOMAIN", 2),
        HTTP_TIMEOUT=_get_env_float("HTTP_TIMEOUT", 15.0),
        HTTP_RETRIES=_get_env_int("HTTP_RETRIES", 3),
        HTTP_BACKOFF_FACTOR=_get_env_float("HTTP_BACKOFF_FACTOR", 0.5),
        MAX_HTML_MB=_get_env_float("MAX_HTML_MB", 5.0),
        MAX_PDF_MB=_get_env_float("MAX_PDF_MB", 25.0),
        MAX_DOWNLOAD_MB=_get_env_float("MAX_DOWNLOAD_MB", 100.0),
        PDF_MAX_PAGES=_get_env_int("PDF_MAX_PAGES", 3),
        USER_AGENT=_get_env_str("USER_AGENT", "DorkScoutPipeline/1.0 (Public OSINT Research)"),
        SEARCH_PROVIDER=_get_env_str("SEARCH_PROVIDER", "duckduckgo").lower(),
        LOG_LEVEL=_get_env_str("LOG_LEVEL", "INFO").upper(),
        LOG_FILE=_get_env_str("LOG_FILE", "logs/dork_scout.log"),
        SERPAPI_API_KEY=_get_env_str("SERPAPI_API_KEY", ""),
        GOOGLE_API_KEY=_get_env_str("GOOGLE_API_KEY", ""),
        GOOGLE_CSE_ID=_get_env_str("GOOGLE_CSE_ID", ""),
    )

# Global singleton config instance
config = load_config()
