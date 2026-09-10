import os
import re
import logging
import webbrowser
import threading
from urllib.parse import urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.config import config
from utils.url_utils import normalize_url, get_domain
from utils.stats import PipelineStats
from utils.drive_resolver import (
    is_google_drive_url, 
    extract_google_file_id_and_type, 
    get_direct_download_url
)

logger = logging.getLogger(__name__)

# Thread-local storage untuk HTTP Session per-worker downloader
_thread_local = threading.local()

def get_downloader_session() -> requests.Session:
    """Mengembalikan atau membuat requests.Session thread-local untuk downloader."""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        retries = Retry(
            total=config.HTTP_RETRIES,
            backoff_factor=config.HTTP_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
            allowed_methods=["GET", "HEAD"]
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            "User-Agent": config.USER_AGENT
        })
        _thread_local.session = session
    return _thread_local.session

def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """Membersihkan nama file dari karakter terlarang sistem operasi."""
    if not filename or not isinstance(filename, str):
        return "downloaded_file"
    clean = re.sub(r'[\\/*?:"<>|]', "", filename)
    clean = clean.strip().replace(" ", "_")
    if not clean:
        clean = "downloaded_file"
    return clean[:max_length]

def convert_gdrive_url_to_download_link(url: str) -> Tuple[str, str, bool]:
    """
    Mengidentifikasi dan mengonversi link Google Drive / Docs / Sheets menjadi Direct Download / Export URL.
    Mengembalikan (download_url, resource_type, is_folder).
    """
    if not url:
        return url, "standard", False

    if is_google_drive_url(url):
        file_id, resource_type, resource_key = extract_google_file_id_and_type(url)
        if file_id:
            download_url, is_folder = get_direct_download_url(file_id, resource_type, resource_key)
            type_map = {
                "file": "gdrive_file",
                "folder": "gdrive_folder",
                "doc": "gdoc",
                "sheet": "gsheet",
                "slide": "gslide",
                "form": "gform"
            }
            mapped_type = type_map.get(resource_type, resource_type)
            if download_url:
                return download_url, mapped_type, is_folder
            return url, mapped_type, is_folder

    return url, "standard", False

def get_filename_from_url_and_headers(
    url: str, 
    content_type: str = "", 
    content_disposition: str = "", 
    custom_ext: str = ""
) -> str:
    """Mendapatkan nama file yang paling tepat berdasarkan Content-Disposition, URL path, atau Content-Type."""
    # 1. Cek Content-Disposition header
    if content_disposition:
        match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', content_disposition, re.IGNORECASE)
        if match:
            extracted_name = unquote(match.group(1).strip())
            if extracted_name:
                return sanitize_filename(extracted_name)

    # 2. Cek URL path
    parsed = urlparse(url)
    path = unquote(parsed.path)
    base_name = os.path.basename(path)

    if base_name and "." in base_name and "export" not in base_name and "uc" not in base_name:
        return sanitize_filename(base_name)

    # 3. Fallback berdasarkan Content-Type / Domain
    domain_slug = sanitize_filename(parsed.netloc) or "document"
    ext_map = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
        "text/csv": ".csv",
        "video/mp4": ".mp4",
        "video/x-matroska": ".mkv",
        "text/html": ".html"
    }

    detected_ext = custom_ext or ".bin"
    for mime_key, ext_val in ext_map.items():
        if mime_key in content_type:
            detected_ext = ext_val
            break

    if detected_ext == ".bin":
        url_lower = url.lower()
        if "pdf" in url_lower or "format=pdf" in url_lower:
            detected_ext = ".pdf"
        elif "csv" in url_lower or "format=csv" in url_lower:
            detected_ext = ".csv"

    return f"{domain_slug}_{os.urandom(3).hex()}{detected_ext}"

def download_file(url: str, output_folder: str = "downloads", timeout: Optional[float] = None) -> Optional[str]:
    """
    Mendownload file fisik biner (PDF/XLSX/CSV/MP4/GDrive) secara aman via chunk streaming 
    menggunakan session pool & verifikasi SSL yang terjaga.
    """
    if not url or not url.startswith("http"):
        logger.warning(f"URL tidak valid untuk di-download: {url}")
        return None

    # Handle Google Drive Links
    download_target_url, resource_type, is_folder = convert_gdrive_url_to_download_link(url)
    if is_folder:
        logger.warning(f"URL '{url}' adalah Google Drive Shared Folder. Gunakan 'open <nomor>' untuk membukanya di browser.")
        return None

    req_timeout = timeout if timeout is not None else config.HTTP_TIMEOUT
    os.makedirs(output_folder, exist_ok=True)
    session = get_downloader_session()

    try:
        logger.info(f"Memulai streaming download dari: {download_target_url}")
        resp = session.get(download_target_url, stream=True, timeout=req_timeout, allow_redirects=True, verify=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        content_disposition = resp.headers.get("Content-Disposition", "")
        total_length = resp.headers.get("Content-Length")

        # Cek jika dialihkan ke halaman login/permission
        final_url_lower = str(resp.url).lower()
        if "accounts.google.com" in final_url_lower or "/servicelogin" in final_url_lower:
            logger.warning(f"Download dibatalkan: File '{url}' memerlukan autentikasi / izin akses (permission_required).")
            return None

        custom_ext = ".pdf" if resource_type in ("doc", "slide") else (".csv" if resource_type == "sheet" else "")
        filename = get_filename_from_url_and_headers(url, content_type, content_disposition, custom_ext=custom_ext)
        filepath = os.path.join(output_folder, filename)

        # Hindari menimpa file lokal jika nama sama
        counter = 1
        name_part, ext_part = os.path.splitext(filename)
        while os.path.exists(filepath):
            filepath = os.path.join(output_folder, f"{name_part}_{counter}{ext_part}")
            counter += 1

        downloaded_bytes = 0
        chunk_size = 64 * 1024  # 64 KB chunks

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded_bytes += len(chunk)

        total_mb = downloaded_bytes / (1024 * 1024)
        if total_length:
            try:
                expected_mb = int(total_length) / (1024 * 1024)
                logger.info(f"Download selesai: {filepath} ({total_mb:.2f} MB / {expected_mb:.2f} MB)")
            except (ValueError, TypeError):
                logger.info(f"Download selesai: {filepath} ({total_mb:.2f} MB)")
        else:
            logger.info(f"Download selesai: {filepath} ({total_mb:.2f} MB)")

        return filepath

    except Exception as e:
        logger.error(f"Gagal mendownload {url}: {e}")
        return None

def _download_worker(item: Dict[str, Any], output_folder: str, stats: Optional[PipelineStats] = None) -> Dict[str, Any]:
    """Helper worker untuk eksekusi download tunggal dalam thread pool."""
    url = item.get("url") or item.get("link", "")
    title = item.get("title", url)

    # Validasi kesiapan download Google Drive
    if item.get("is_google_drive"):
        drive_status = item.get("drive_status")
        if drive_status in ("permission_required", "not_found", "deleted_or_unavailable", "unsupported_drive_url") or not item.get("is_downloadable", True):
            logger.warning(f"File Google Drive '{title}' tidak dapat diunduh (Status: {drive_status}). Melewati unduhan.")
            if stats:
                stats.inc_downloads_failed()
            return {
                "title": title,
                "url": item.get("canonical_url") or url,
                "saved_path": None,
                "status": "failed",
                "reason": drive_status
            }

    # Gunakan direct download_url jika tersedia dari resolver, atau fallback ke url
    target_download_url = item.get("download_url") or url
    saved_path = download_file(target_download_url, output_folder=output_folder)
    
    if saved_path:
        if stats:
            stats.inc_downloads_success()
        return {
            "title": title,
            "url": item.get("canonical_url") or url,
            "saved_path": saved_path,
            "status": "success"
        }
    else:
        if stats:
            stats.inc_downloads_failed()
        return {
            "title": title,
            "url": item.get("canonical_url") or url,
            "saved_path": None,
            "status": "failed"
        }

def download_files_batch(
    items: List[Dict[str, Any]], 
    output_folder: str = "downloads", 
    max_workers: Optional[int] = None,
    stats: Optional[PipelineStats] = None
) -> List[Dict[str, Any]]:
    """
    Mendownload banyak file secara paralel menggunakan concurrent.futures.ThreadPoolExecutor.
    Mempertahankan urutan input asli secara deterministik.
    """
    if not items:
        return []

    workers = max_workers if max_workers is not None else config.MAX_WORKERS
    logger.info(f"Menjalankan batch download paralel ({len(items)} file, {workers} workers)...")
    indexed_results: List[Tuple[int, Dict[str, Any]]] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(_download_worker, item, output_folder, stats): idx
            for idx, item in enumerate(items)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                res = future.result()
                indexed_results.append((idx, res))
            except Exception as e:
                logger.error(f"Thread worker download error pada item #{idx}: {e}")
                if stats:
                    stats.inc_downloads_failed()
                indexed_results.append((idx, {
                    "title": items[idx].get("title", "Unknown"),
                    "url": items[idx].get("canonical_url") or items[idx].get("url") or items[idx].get("link", ""),
                    "saved_path": None,
                    "status": "failed",
                    "error": str(e)
                }))

    indexed_results.sort(key=lambda x: x[0])
    return [res for _, res in indexed_results]

def open_url_in_browser(url: str):
    """Membuka link URL langsung di web browser bawaan pengguna."""
    try:
        webbrowser.open(url)
        logger.info(f"Membuka URL di browser: {url}")
    except Exception as e:
        logger.error(f"Gagal membuka URL di browser: {e}")
