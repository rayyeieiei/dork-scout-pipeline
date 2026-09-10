import re
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import requests

from utils.config import config

logger = logging.getLogger(__name__)

# Pola Regex terstruktur untuk mendeteksi variasi URL Google Drive & Google Docs
GDRIVE_PATTERNS = [
    # 1. Drive File: drive.google.com/file/d/<ID>
    (re.compile(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', re.IGNORECASE), "file"),
    # 2. Drive Folder: drive.google.com/drive/folders/<ID> atau /drive/u/0/folders/<ID>
    (re.compile(r'drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)', re.IGNORECASE), "folder"),
    # 3. Docs Document: docs.google.com/document/d/<ID>
    (re.compile(r'docs\.google\.com/document/d/([a-zA-Z0-9_-]+)', re.IGNORECASE), "doc"),
    # 4. Sheets Spreadsheet: docs.google.com/spreadsheets/d/<ID>
    (re.compile(r'docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)', re.IGNORECASE), "sheet"),
    # 5. Slides Presentation: docs.google.com/presentation/d/<ID>
    (re.compile(r'docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)', re.IGNORECASE), "slide"),
    # 6. Forms: docs.google.com/forms/d/<ID> atau /forms/d/e/<ID>
    (re.compile(r'docs\.google\.com/forms/d/(?:e/)?([a-zA-Z0-9_-]+)', re.IGNORECASE), "form"),
    # 7. Drive Open: drive.google.com/open?id=<ID>
    (re.compile(r'drive\.google\.com/open', re.IGNORECASE), "open"),
    # 8. Drive UC: drive.google.com/uc?id=<ID> atau /uc?export=download&id=<ID>
    (re.compile(r'drive\.google\.com/uc', re.IGNORECASE), "uc"),
]

# Frasa indikator status landing page Google Drive
PERMISSION_REQUIRED_PHRASES = [
    "you need permission",
    "perlu izin",
    "request access",
    "minta akses",
    "sign in with your google account",
    "sign in to access",
    "sign in to continue",
    "akses ditolak",
    "must be signed in",
    "servicelogin"
]

NOT_FOUND_PHRASES = [
    "sorry, the file you have requested does not exist",
    "maaf, file yang anda minta tidak ada",
    "file not found",
    "document does not exist",
    "dokumen tidak ada",
    "the requested url was not found on this server"
]

DELETED_UNAVAILABLE_PHRASES = [
    "file is in owner's trash",
    "file ada di tempat sampah pemilik",
    "file has been deleted",
    "file telah dihapus",
    "item is unavailable",
    "item tidak tersedia"
]

RATE_LIMITED_PHRASES = [
    "too many requests",
    "quota exceeded",
    "download quota exceeded",
    "kuota download terlampaui"
]

@dataclass
class DriveResolutionResult:
    is_google_drive: bool
    google_file_id: Optional[str]
    drive_resource_type: Optional[str]  # "file", "folder", "doc", "sheet", "slide", "form", "unknown"
    original_url: str
    canonical_url: str
    final_url: str
    initial_http_status: Optional[int]
    final_http_status: Optional[int]
    drive_status: str  # "accessible", "redirect_resolved", "permission_required", "not_found", "deleted_or_unavailable", "rate_limited", "request_error", "unsupported_drive_url"
    is_downloadable: bool
    download_url: Optional[str]
    resource_key: Optional[str] = None
    extracted_text: str = ""

def is_google_drive_url(url: str) -> bool:
    """Memeriksa apakah URL berasal dari ekosistem Google Drive / Docs yang valid."""
    if not url or not isinstance(url, str):
        return False
    url_lower = url.lower().strip()
    if "drive.google.com" not in url_lower and "docs.google.com" not in url_lower:
        return False
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain not in ("drive.google.com", "docs.google.com"):
            return False
        for pattern, _ in GDRIVE_PATTERNS:
            if pattern.search(url):
                return True
        return False
    except Exception:
        return False

def extract_google_file_id_and_type(url: str) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Mengekstrak (file_id, resource_type, resource_key) dari URL Google Drive / Docs.
    Mengembalikan (None, 'unknown', None) jika URL tidak dikenali.
    """
    if not is_google_drive_url(url):
        return None, "unknown", None

    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # 1. Ekstraksi resourcekey jika ada (case-insensitive)
    resource_key = None
    for k, v in query_params.items():
        if k.lower() == "resourcekey" and v:
            resource_key = v[0]
            break

    # 2. Cek query parameter 'id' (misal: /open?id=ABC atau /uc?id=ABC)
    if "id" in query_params and query_params["id"]:
        file_id = query_params["id"][0]
        url_lower = url.lower()
        if "spreadsheets" in url_lower:
            return file_id, "sheet", resource_key
        elif "document" in url_lower:
            return file_id, "doc", resource_key
        elif "presentation" in url_lower:
            return file_id, "slide", resource_key
        elif "folders" in url_lower:
            return file_id, "folder", resource_key
        return file_id, "file", resource_key

    # 3. Cek pola Regex path
    for pattern, r_type in GDRIVE_PATTERNS:
        match = pattern.search(url)
        if match and match.groups():
            return match.group(1), r_type, resource_key

    return None, "unknown", resource_key

def extract_google_file_id(url: str) -> Optional[str]:
    """Helper singkat untuk mendapatkan Google File ID saja."""
    file_id, _, _ = extract_google_file_id_and_type(url)
    return file_id

def get_canonical_drive_url(file_id: str, resource_type: str, resource_key: Optional[str] = None) -> str:
    """
    Menghasilkan URL canonical standar Google Drive berdasarkan resource_type dan file_id.
    Mempertahankan resourcekey jika tersedia.
    """
    if not file_id:
        return ""

    rk_suffix = f"?resourcekey={resource_key}" if resource_key else ""

    if resource_type == "folder":
        return f"https://drive.google.com/drive/folders/{file_id}{rk_suffix}"
    elif resource_type == "doc":
        return f"https://docs.google.com/document/d/{file_id}/edit{rk_suffix}"
    elif resource_type == "sheet":
        return f"https://docs.google.com/spreadsheets/d/{file_id}/edit{rk_suffix}"
    elif resource_type == "slide":
        return f"https://docs.google.com/presentation/d/{file_id}/edit{rk_suffix}"
    elif resource_type == "form":
        return f"https://docs.google.com/forms/d/{file_id}/viewform{rk_suffix}"
    else:
        # Default Google Drive File Viewer
        return f"https://drive.google.com/file/d/{file_id}/view{rk_suffix}"

def get_direct_download_url(file_id: str, resource_type: str, resource_key: Optional[str] = None) -> Tuple[Optional[str], bool]:
    """
    Menghasilkan URL direct download / export untuk file Google Drive.
    Mengembalikan (download_url, is_folder).
    """
    if not file_id:
        return None, False

    rk_param = f"&resourcekey={resource_key}" if resource_key else ""

    if resource_type == "folder":
        return None, True
    elif resource_type == "doc":
        return f"https://docs.google.com/document/d/{file_id}/export?format=pdf{rk_param}", False
    elif resource_type == "sheet":
        return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv{rk_param}", False
    elif resource_type == "slide":
        return f"https://docs.google.com/presentation/d/{file_id}/export?format=pdf{rk_param}", False
    elif resource_type == "form":
        return None, False
    else:
        # Google Drive File
        return f"https://drive.google.com/uc?export=download&id={file_id}{rk_param}", False

def classify_drive_response(
    initial_status: int, 
    final_status: int, 
    final_url: str, 
    body_sample: str
) -> str:
    """
    Mengklarifikasi status aksesibilitas Google Drive secara presisi berdasarkan HTTP status,
    URL tujuan redirect, dan sampel konten teks landing page.
    """
    # 1. Cek redirect ke Google Login / Auth
    final_url_lower = final_url.lower()
    if "accounts.google.com" in final_url_lower or "/servicelogin" in final_url_lower or "/signin" in final_url_lower:
        return "permission_required"

    # 2. Cek status kode HTTP eksplisit
    if final_status == 404:
        return "not_found"
    elif final_status in (401, 403):
        return "permission_required"
    elif final_status == 429:
        return "rate_limited"
    elif final_status >= 500:
        return "request_error"

    # 3. Cek sampel teks landing page (analisis konten)
    body_lower = body_sample.lower()
    
    for phrase in NOT_FOUND_PHRASES:
        if phrase in body_lower:
            return "not_found"

    for phrase in DELETED_UNAVAILABLE_PHRASES:
        if phrase in body_lower:
            return "deleted_or_unavailable"

    for phrase in PERMISSION_REQUIRED_PHRASES:
        if phrase in body_lower:
            return "permission_required"

    for phrase in RATE_LIMITED_PHRASES:
        if phrase in body_lower:
            return "rate_limited"

    # 4. Jika final_status 200 OK dan tidak ada indikasi error
    if final_status == 200:
        if initial_status in (301, 302, 303, 307, 308):
            return "redirect_resolved"
        return "accessible"

    return "request_error"

def resolve_and_validate_gdrive_url(
    url: str, 
    session: Optional[requests.Session] = None, 
    timeout: float = 15.0,
    snippet: str = ""
) -> DriveResolutionResult:
    """
    Memvalidasi dan menormalisasi URL Google Drive secara redirect-aware tanpa bypass:
    - Mengekstrak file ID & resource type
    - Menghasilkan canonical URL yang stabil
    - Melakukan HTTP request untuk validasi aksesibilitas
    - Menangani status 3xx tanpa salah menganggapnya sebagai broken link
    - Menghasilkan status klasifikasi yang akurat (accessible, permission_required, dll.)
    """
    if not is_google_drive_url(url):
        return DriveResolutionResult(
            is_google_drive=False,
            google_file_id=None,
            drive_resource_type=None,
            original_url=url,
            canonical_url=url,
            final_url=url,
            initial_http_status=None,
            final_http_status=None,
            drive_status="unsupported_drive_url",
            is_downloadable=False,
            download_url=None,
            extracted_text=snippet
        )

    file_id, resource_type, resource_key = extract_google_file_id_and_type(url)
    if not file_id:
        return DriveResolutionResult(
            is_google_drive=True,
            google_file_id=None,
            drive_resource_type="unknown",
            original_url=url,
            canonical_url=url,
            final_url=url,
            initial_http_status=None,
            final_http_status=None,
            drive_status="unsupported_drive_url",
            is_downloadable=False,
            download_url=None,
            resource_key=resource_key,
            extracted_text=snippet
        )

    canonical_url = get_canonical_drive_url(file_id, resource_type, resource_key)
    download_url, is_folder = get_direct_download_url(file_id, resource_type, resource_key)

    http_session = session or requests.Session()
    headers = {"User-Agent": config.USER_AGENT}

    initial_status: Optional[int] = None
    final_status: Optional[int] = None
    final_url = canonical_url
    drive_status = "request_error"
    body_sample = ""

    try:
        # Gunakan canonical URL untuk validasi live request dengan stream=True agar hemat bandwidth
        resp = http_session.get(canonical_url, headers=headers, timeout=timeout, allow_redirects=True, stream=True, verify=True)
        
        if resp.history:
            initial_status = resp.history[0].status_code
        else:
            initial_status = resp.status_code

        final_status = resp.status_code
        final_url = str(resp.url)

        # Baca hanya sebagian kecil respon (maks 8KB) untuk mengklarifikasi teks status
        raw_chunk = b""
        for chunk in resp.iter_content(chunk_size=4096):
            if chunk:
                raw_chunk += chunk
                if len(raw_chunk) >= 8192:
                    break
        body_sample = raw_chunk.decode("utf-8", errors="ignore")

        drive_status = classify_drive_response(initial_status, final_status, final_url, body_sample)

    except requests.exceptions.RequestException as e:
        logger.debug(f"Gagal melakukan validasi Google Drive link '{canonical_url}': {e}")
        drive_status = "request_error"
        body_sample = f"[Network Error: {e}]"

    is_downloadable = (drive_status in ("accessible", "redirect_resolved")) and not is_folder

    # Buat preview teks ringkas
    type_label = resource_type.upper()
    status_label = drive_status.replace("_", " ").upper()
    overview_text = f"[Google Drive {type_label} | Status: {status_label} | ID: {file_id}]"
    if snippet:
        overview_text += f" Snippet: {snippet}"

    return DriveResolutionResult(
        is_google_drive=True,
        google_file_id=file_id,
        drive_resource_type=resource_type,
        original_url=url,
        canonical_url=canonical_url,
        final_url=final_url,
        initial_http_status=initial_status,
        final_http_status=final_status,
        drive_status=drive_status,
        is_downloadable=is_downloadable,
        download_url=download_url if is_downloadable else None,
        resource_key=resource_key,
        extracted_text=overview_text
    )
