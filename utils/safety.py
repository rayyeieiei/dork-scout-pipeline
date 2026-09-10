import re
from typing import Tuple

# Pola-pola query yang mengarah pada pencarian kredensial terlarang, kebocoran database, atau eksploitasi
PROHIBITED_PATTERNS = [
    r'\.env\b.*?\b(password|secret|key|db_pass)\b',
    r'\b(database|sql)\s+dump\b',
    r'\b(password|credentials?|passwd|shadow)\s*(file|leak|dump)\b',
    r'\bid_rsa\b',
    r'wp-config(?:\.php)?\b',
    r'\b(admin|root)\s*:\s*(password|admin)\b',
    r'\b(vulnerability|exploit|sqli|rce)\s*scan\b',
    r'\b(cve-\d{4}-\d+)\s*(exploit|poc)\b'
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PROHIBITED_PATTERNS]

def validate_query_safety(query: str) -> Tuple[bool, str]:
    """
    Memvalidasi apakah query/topik mematuhi batasan etis OSINT & riset legal.
    Menolak kueri yang mengarah ke credential harvesting, exploit scanning, atau database dumps.
    """
    if not query or not query.strip():
        return False, "Topik pencarian kosong."

    clean_query = query.strip()

    for pat in _COMPILED_PATTERNS:
        if pat.search(clean_query):
            return False, f"Query ditolak: terdeteksi pola pencarian kredensial/eksploitasi yang dilarang ({pat.pattern})."

    return True, "Query aman."
