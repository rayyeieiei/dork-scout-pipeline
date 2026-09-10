import time
import threading
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PipelineStats:
    queries_generated: int = 0
    search_results: int = 0
    unique_urls: int = 0
    duplicate_urls: int = 0
    robots_blocked: int = 0
    fetch_success: int = 0
    parse_success: int = 0
    duplicate_content: int = 0
    unsupported_content: int = 0
    request_errors: int = 0
    parse_errors: int = 0
    downloads_success: int = 0
    downloads_failed: int = 0

    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def start_timer(self):
        with self._lock:
            self.start_time = time.time()
            self.end_time = None

    def stop_timer(self):
        with self._lock:
            self.end_time = time.time()

    @property
    def elapsed_seconds(self) -> float:
        if self.end_time is not None:
            return max(0.0, self.end_time - self.start_time)
        return max(0.0, time.time() - self.start_time)

    def inc_queries_generated(self, count: int = 1):
        with self._lock:
            self.queries_generated += count

    def inc_search_results(self, count: int = 1):
        with self._lock:
            self.search_results += count

    def inc_unique_urls(self, count: int = 1):
        with self._lock:
            self.unique_urls += count

    def inc_duplicate_urls(self, count: int = 1):
        with self._lock:
            self.duplicate_urls += count

    def inc_robots_blocked(self, count: int = 1):
        with self._lock:
            self.robots_blocked += count

    def inc_fetch_success(self, count: int = 1):
        with self._lock:
            self.fetch_success += count

    def inc_parse_success(self, count: int = 1):
        with self._lock:
            self.parse_success += count

    def inc_duplicate_content(self, count: int = 1):
        with self._lock:
            self.duplicate_content += count

    def inc_unsupported_content(self, count: int = 1):
        with self._lock:
            self.unsupported_content += count

    def inc_request_errors(self, count: int = 1):
        with self._lock:
            self.request_errors += count

    def inc_parse_errors(self, count: int = 1):
        with self._lock:
            self.parse_errors += count

    def inc_downloads_success(self, count: int = 1):
        with self._lock:
            self.downloads_success += count

    def inc_downloads_failed(self, count: int = 1):
        with self._lock:
            self.downloads_failed += count

    def format_summary(self, topic: str) -> str:
        """Menghasilkan teks ringkasan metrik eksekusi terminal yang bersih dan dependency-free."""
        elapsed = self.elapsed_seconds
        lines = [
            "=" * 60,
            "DORK SCOUT PIPELINE SUMMARY",
            "=" * 60,
            f"Topic                : {topic}",
            f"Queries Generated    : {self.queries_generated}",
            f"Search Results       : {self.search_results}",
            f"Unique URLs          : {self.unique_urls}",
            f"Duplicate URLs       : {self.duplicate_urls}",
            f"Robots Blocked       : {self.robots_blocked}",
            f"Parsed Successfully  : {self.parse_success}",
            f"Duplicate Content    : {self.duplicate_content}",
            f"Unsupported Files    : {self.unsupported_content}",
            f"Request Errors       : {self.request_errors}",
            f"Downloaded Files     : {self.downloads_success}",
            f"Execution Time       : {elapsed:.2f} sec",
            "=" * 60
        ]
        return "\n".join(lines)
