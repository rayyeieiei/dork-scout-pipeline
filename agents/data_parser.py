import io
import re
import logging
import threading
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import pypdf

from utils.config import config
from utils.url_utils import normalize_url, get_domain, sha256_bytes
from utils.robots_checker import RobotsChecker
from utils.stats import PipelineStats
from utils.drive_resolver import (
    is_google_drive_url, 
    resolve_and_validate_gdrive_url, 
    DriveResolutionResult
)

# Thread-local storage untuk HTTP Session per-worker thread
_thread_local = threading.local()

def get_thread_session() -> requests.Session:
    """Mengembalikan atau membuat requests.Session thread-local dengan connection pooling & retry."""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        retries = Retry(
            total=config.HTTP_RETRIES,
            backoff_factor=config.HTTP_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
            allowed_methods=["GET", "HEAD", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            "User-Agent": config.USER_AGENT
        })
        _thread_local.session = session
    return _thread_local.session

class DomainRateLimiter:
    """Membatasi jumlah concurrent request maksimum per domain target (BoundedSemaphore)."""
    def __init__(self, max_per_domain: int = 2):
        self.max_per_domain = max_per_domain
        self._lock = threading.Lock()
        self._semaphores: Dict[str, threading.BoundedSemaphore] = {}

    def acquire(self, domain: str):
        with self._lock:
            if domain not in self._semaphores:
                self._semaphores[domain] = threading.BoundedSemaphore(self.max_per_domain)
            sem = self._semaphores[domain]
        sem.acquire()

    def release(self, domain: str):
        with self._lock:
            sem = self._semaphores.get(domain)
        if sem:
            try:
                sem.release()
            except ValueError:
                pass

class ContentHashRegistry:
    """Registry thread-safe untuk mendeteksi duplicate content berdasarkan hash SHA-256."""
    def __init__(self):
        self._lock = threading.Lock()
        self._seen_hashes: Dict[str, str] = {}  # hash -> original_url

    def check_and_register(self, content_hash: str, url: str) -> Tuple[bool, Optional[str]]:
        if not content_hash:
            return False, None
        with self._lock:
            if content_hash in self._seen_hashes:
                return True, self._seen_hashes[content_hash]
            self._seen_hashes[content_hash] = url
            return False, None

class DataParser:
    def __init__(
        self, 
        timeout: Optional[float] = None, 
        max_pdf_pages: Optional[int] = None, 
        max_workers: Optional[int] = None,
        max_per_domain: Optional[int] = None
    ):
        self.timeout = timeout if timeout is not None else config.HTTP_TIMEOUT
        self.max_pdf_pages = max_pdf_pages if max_pdf_pages is not None else config.PDF_MAX_PAGES
        self.max_workers = max_workers if max_workers is not None else config.MAX_WORKERS
        self.max_per_domain = max_per_domain if max_per_domain is not None else config.MAX_REQUESTS_PER_DOMAIN

        self.logger = logging.getLogger(__name__)
        self.robots_checker = RobotsChecker(user_agent=config.USER_AGENT)
        self.domain_limiter = DomainRateLimiter(max_per_domain=self.max_per_domain)
        self.hash_registry = ContentHashRegistry()

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """Mengekstrak teks metadata & halaman awal PDF menggunakan pypdf tanpa menyimpan ke disk."""
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            total_pages = len(reader.pages)
            pages_to_read = min(total_pages, self.max_pdf_pages)
            
            self.logger.debug(f"Mengekstrak {pages_to_read} dari total {total_pages} halaman PDF...")
            extracted_pages = []
            
            # Metadata jika ada
            if reader.metadata and reader.metadata.title:
                extracted_pages.append(f"[Metadata Title: {reader.metadata.title}]")

            for i in range(pages_to_read):
                text = reader.pages[i].extract_text() or ""
                if text.strip():
                    extracted_pages.append(f"--- [Halaman {i+1}] ---\n{text.strip()}")
            
            if extracted_pages:
                return "\n\n".join(extracted_pages)[:2000]
            return "[PDF tidak memiliki lapisan teks yang dapat diekstrak / dokumen hasil scan]"

        except Exception as e:
            self.logger.debug(f"Gagal mengekstrak teks PDF: {e}")
            return f"[Error parsing PDF: {e}]"

    def _extract_media_header_info(self, url: str) -> Dict[str, Any]:
        """
        Mengekstrak metadata ringan untuk file media (MP4/MKV) via HTTP HEAD/Stream 
        tanpa mengunduh seluruh file video besar ke memory.
        """
        session = get_thread_session()
        try:
            head_resp = session.head(url, timeout=self.timeout, allow_redirects=True, verify=True)
            content_type = head_resp.headers.get("Content-Type", "video/mp4")
            content_length = head_resp.headers.get("Content-Length")
            
            size_str = "Ukuran tidak diketahui"
            if content_length and content_length.isdigit():
                size_mb = int(content_length) / (1024 * 1024)
                size_str = f"{size_mb:.2f} MB"

            return {
                "status": "success",
                "type": "video",
                "content_sha256": "",
                "extracted_text": f"[Media File: {content_type} | Ukuran: {size_str} | Direct Stream Link]"
            }
        except Exception as e:
            return {
                "status": "success",
                "type": "video",
                "content_sha256": "",
                "extracted_text": f"[Media File Video - URL: {url} | Error reading header: {e}]"
            }

    def parse_url(
        self, 
        item: Dict[str, Any], 
        topic: str, 
        dork_used: str, 
        category: str = "general",
        stats: Optional[PipelineStats] = None
    ) -> Dict[str, Any]:
        """
        Memproses satu URL target dengan:
        - URL normalization
        - Redirect-aware Google Drive link resolution & access validation
        - Per-domain concurrency limit (Semaphore)
        - Robots.txt enforcement
        - Connection pooling via Session
        - SHA-256 fingerprinting & duplicate content detection
        - Error resilience
        """
        raw_url = item.get("link", "")
        normalized_url = normalize_url(raw_url) or raw_url
        source_domain = get_domain(normalized_url or raw_url)

        base_result: Dict[str, Any] = {
            "topic": topic,
            "category": category,
            "dork_used": dork_used,
            "title": item.get("title", ""),
            "source_domain": source_domain,
            "url": raw_url,
            "normalized_url": normalized_url,
            "snippet": item.get("snippet", ""),
            "status": "pending",
            "type": "unknown",
            "content_sha256": "",
            "duplicate_of": None,
            "extracted_text": "",
            # Google Drive Specific Metadata
            "is_google_drive": False,
            "google_file_id": None,
            "drive_resource_type": None,
            "original_url": raw_url,
            "canonical_url": raw_url,
            "final_url": raw_url,
            "initial_http_status": None,
            "final_http_status": None,
            "drive_status": None,
            "is_downloadable": True,
            "download_url": None
        }

        if not raw_url:
            base_result["status"] = "invalid_url"
            if stats:
                stats.inc_request_errors()
            return base_result

        # Deteksi dan validasi resource Google Drive secara redirect-aware
        if is_google_drive_url(raw_url) or "drive.google.com" in source_domain or "docs.google.com" in source_domain or category == "gdrive":
            session = get_thread_session()
            self.domain_limiter.acquire(source_domain)
            try:
                drive_res = resolve_and_validate_gdrive_url(
                    raw_url, 
                    session=session, 
                    timeout=self.timeout, 
                    snippet=item.get("snippet", "")
                )
            finally:
                self.domain_limiter.release(source_domain)

            base_result["is_google_drive"] = drive_res.is_google_drive
            base_result["google_file_id"] = drive_res.google_file_id
            base_result["drive_resource_type"] = drive_res.drive_resource_type
            base_result["original_url"] = drive_res.original_url
            base_result["canonical_url"] = drive_res.canonical_url
            base_result["url"] = drive_res.canonical_url  # Tampilkan canonical URL stabil di tabel & CSV
            base_result["final_url"] = drive_res.final_url
            base_result["initial_http_status"] = drive_res.initial_http_status
            base_result["final_http_status"] = drive_res.final_http_status
            base_result["drive_status"] = drive_res.drive_status
            base_result["is_downloadable"] = drive_res.is_downloadable
            base_result["download_url"] = drive_res.download_url
            base_result["extracted_text"] = drive_res.extracted_text

            # Map tipe badge visual
            type_map = {
                "file": "gdrive_file",
                "folder": "gdrive_folder",
                "doc": "gdoc",
                "sheet": "gsheet",
                "slide": "gslide",
                "form": "gform"
            }
            base_result["type"] = type_map.get(drive_res.drive_resource_type, "gdrive")

            if drive_res.drive_status in ("accessible", "redirect_resolved"):
                base_result["status"] = "success"
                if stats:
                    stats.inc_fetch_success()
                    stats.inc_parse_success()
            elif drive_res.drive_status == "permission_required":
                base_result["status"] = "permission_required"
                if stats:
                    stats.inc_fetch_success()
            elif drive_res.drive_status == "not_found":
                base_result["status"] = "not_found"
                if stats:
                    stats.inc_request_errors()
            elif drive_res.drive_status == "deleted_or_unavailable":
                base_result["status"] = "deleted_or_unavailable"
                if stats:
                    stats.inc_request_errors()
            elif drive_res.drive_status == "rate_limited":
                base_result["status"] = "rate_limited"
                if stats:
                    stats.inc_request_errors()
            else:
                base_result["status"] = drive_res.drive_status
                if stats:
                    stats.inc_request_errors()

            return base_result

        # Deteksi file video
        url_lower = raw_url.lower()
        if url_lower.endswith(".mp4") or url_lower.endswith(".mkv") or "video" in category:
            media_info = self._extract_media_header_info(raw_url)
            base_result["status"] = media_info["status"]
            base_result["type"] = media_info["type"]
            base_result["content_sha256"] = media_info.get("content_sha256", "")
            base_result["extracted_text"] = media_info["extracted_text"]
            if stats:
                stats.inc_fetch_success()
                stats.inc_parse_success()
            return base_result

        # Pengecekan Robots.txt
        if not self.robots_checker.can_fetch(raw_url):
            self.logger.warning(f"Dilewati (dilarang robots.txt): {raw_url}")
            base_result["status"] = "blocked_by_robots"
            if stats:
                stats.inc_robots_blocked()
            return base_result

        # Eksekusi HTTP Request dengan pembatasan per-domain concurrency
        session = get_thread_session()
        self.domain_limiter.acquire(source_domain)
        try:
            self.logger.info(f"Mengunduh & menganalisis metadata: {raw_url}")
            resp = session.get(raw_url, timeout=self.timeout, stream=True, verify=True)
            resp.raise_for_status()

            # Baca konten biner dengan limit ukuran wajar
            content_bytes = resp.content
            content_length_mb = len(content_bytes) / (1024 * 1024)

            # Hitung SHA-256 fingerprint
            content_hash = sha256_bytes(content_bytes)
            base_result["content_sha256"] = content_hash

            # Cek duplikasi konten berdasarkan hash SHA-256
            is_dup, original_url = self.hash_registry.check_and_register(content_hash, raw_url)
            if is_dup:
                self.logger.info(f"Duplicate content terdeteksi: {raw_url} (sama dengan {original_url})")
                base_result["status"] = "duplicate_content"
                base_result["duplicate_of"] = original_url
                base_result["type"] = "duplicate"
                base_result["extracted_text"] = f"[Duplicate Content - SHA256: {content_hash[:12]}... sama dengan {original_url}]"
                if stats:
                    stats.inc_fetch_success()
                    stats.inc_duplicate_content()
                return base_result

            if stats:
                stats.inc_fetch_success()

            content_type = resp.headers.get("Content-Type", "").lower()

            # 1. Dokumen PDF
            if "application/pdf" in content_type or url_lower.endswith(".pdf"):
                base_result["status"] = "success"
                base_result["type"] = "pdf"
                base_result["extracted_text"] = self._extract_pdf_text(content_bytes)
                if stats:
                    stats.inc_parse_success()
                return base_result

            # 2. File Data Tabular (CSV / Spreadsheet)
            if "text/csv" in content_type or url_lower.endswith(".csv"):
                base_result["status"] = "success"
                base_result["type"] = "finance_data" if "finance" in category else "csv"
                base_result["extracted_text"] = resp.text[:1200]
                if stats:
                    stats.inc_parse_success()
                return base_result

            if "excel" in content_type or url_lower.endswith(".xlsx") or url_lower.endswith(".xls"):
                base_result["status"] = "success"
                base_result["type"] = "finance_data" if "finance" in category else "excel"
                file_size_kb = len(content_bytes) / 1024
                base_result["extracted_text"] = f"[Excel Spreadsheet File: {url_lower.split('/')[-1]} | Size: {file_size_kb:.1f} KB]"
                if stats:
                    stats.inc_parse_success()
                return base_result

            # 3. Shared AI Chats (Claude / ChatGPT)
            if "claude.ai" in source_domain or "chatgpt.com" in source_domain or "openai.com" in source_domain:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.extract()
                chat_text = " ".join(soup.stripped_strings)
                base_result["status"] = "success"
                base_result["type"] = "ai_chats"
                base_result["extracted_text"] = chat_text[:1500]
                if stats:
                    stats.inc_parse_success()
                return base_result

            # 4. Halaman Web / HTML Umum
            if "text/html" in content_type or "text/plain" in content_type or not content_type:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                    tag.extract()

                clean_text = " ".join(soup.stripped_strings)
                base_result["status"] = "success"
                base_result["type"] = "html"
                base_result["extracted_text"] = clean_text[:1000]
                if stats:
                    stats.inc_parse_success()
                return base_result

            # Format konten tidak didukung secara spesifik
            base_result["status"] = "unsupported_content"
            base_result["type"] = "other"
            base_result["extracted_text"] = f"[Unsupported Content-Type: {content_type} | Size: {content_length_mb:.2f} MB]"
            if stats:
                stats.inc_unsupported_content()
            return base_result

        except Exception as e:
            self.logger.error(f"Gagal memproses {raw_url}: {e}")
            base_result["status"] = "error"
            base_result["extracted_text"] = f"[Error: {e}]"
            if stats:
                stats.inc_request_errors()
            return base_result
        finally:
            self.domain_limiter.release(source_domain)

    def parse_urls_concurrently(
        self, 
        items: List[Dict[str, Any]], 
        topic: str, 
        dork_used: str, 
        category: str = "general",
        stats: Optional[PipelineStats] = None
    ) -> List[Dict[str, Any]]:
        """
        Mengekstrak daftar URL secara paralel menggunakan ThreadPoolExecutor.
        Mempertahankan urutan deterministik sesuai urutan input asli.
        """
        if not items:
            return []

        self.logger.info(f"Memulai concurrent worker ({self.max_workers} threads) untuk {len(items)} target...")
        indexed_results: List[Tuple[int, Dict[str, Any]]] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Petakan future ke indeks asli untuk menjaga urutan deterministik
            future_to_idx = {
                executor.submit(self.parse_url, item, topic, dork_used, category, stats): idx
                for idx, item in enumerate(items)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    res = future.result()
                    indexed_results.append((idx, res))
                except Exception as e:
                    self.logger.error(f"Thread worker error pada item #{idx}: {e}")
                    if stats:
                        stats.inc_parse_errors()
                    indexed_results.append((idx, {
                        "topic": topic,
                        "category": category,
                        "dork_used": dork_used,
                        "title": items[idx].get("title", ""),
                        "source_domain": get_domain(items[idx].get("link", "")),
                        "url": items[idx].get("link", ""),
                        "normalized_url": normalize_url(items[idx].get("link", "")),
                        "snippet": items[idx].get("snippet", ""),
                        "status": "error",
                        "type": "unknown",
                        "content_sha256": "",
                        "duplicate_of": None,
                        "extracted_text": f"[Worker Error: {e}]",
                        "is_google_drive": False,
                        "google_file_id": None,
                        "drive_resource_type": None,
                        "original_url": items[idx].get("link", ""),
                        "canonical_url": items[idx].get("link", ""),
                        "final_url": items[idx].get("link", ""),
                        "initial_http_status": None,
                        "final_http_status": None,
                        "drive_status": None,
                        "is_downloadable": True,
                        "download_url": None
                    }))

        # Urutkan kembali berdasarkan indeks asli agar output deterministik
        indexed_results.sort(key=lambda x: x[0])
        return [res for _, res in indexed_results]
