import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import Set

# Tracking parameters yang biasa digunakan untuk analytics dan aman dihapus
TRACKING_PARAMS: Set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "igshid",
    "mc_eid",
    "yclid",
    "_ga",
    "_gl",
    "msclkid",
    "ref",
    "ref_src",
    "ref_url",
}

def normalize_url(url: str) -> str:
    """
    Menormalisasi URL secara konsisten untuk deduplication:
    - Hanya menerima scheme http:// dan https://
    - Lowercase scheme dan netloc (hostname)
    - Menghapus fragment (#section, #page=2)
    - Menghapus query parameter tracking analytics (utm_*, gclid, fbclid, dll.)
    - Mengurutkan query parameter yang tersisa secara kanonikal
    - Mempertahankan path dan parameter fungsional yang esensial
    """
    if not url or not isinstance(url, str):
        return ""

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    # Hanya proses http dan https
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return ""

    netloc = parsed.netloc.lower()
    # Hapus port default jika ada (e.g. :80 untuk http, :443 untuk https)
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parsed.path
    if not path:
        path = "/"

    # Filter query parameters
    query_tuples = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_query = [
        (k, v) for k, v in query_tuples
        if k.lower() not in TRACKING_PARAMS
    ]
    # Urutkan secara deterministik
    filtered_query.sort(key=lambda x: (x[0], x[1]))
    clean_query = urlencode(filtered_query)

    # Fragment selalu diabaikan
    clean_fragment = ""

    normalized = urlunparse((
        scheme,
        netloc,
        path,
        parsed.params,
        clean_query,
        clean_fragment
    ))
    return normalized

def get_domain(url: str) -> str:
    """Mendapatkan domain/hostname huruf kecil dari URL."""
    if not url:
        return "unknown"
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Hapus port jika ada
        if ":" in domain:
            domain = domain.split(":")[0]
        return domain or "unknown"
    except Exception:
        return "unknown"

def sha256_bytes(content: bytes) -> str:
    """Menghasilkan fingerprint hash SHA-256 (hex string) dari bytes konten."""
    if not content:
        return ""
    if isinstance(content, str):
        content = content.encode("utf-8", errors="replace")
    return hashlib.sha256(content).hexdigest()
