import os
import time
import logging
from typing import List, Dict, Any

from utils.config import config

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False

class SearchFetcher:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.provider = config.SEARCH_PROVIDER
        self.serpapi_key = config.SERPAPI_API_KEY
        self.google_api_key = config.GOOGLE_API_KEY
        self.google_cse_id = config.GOOGLE_CSE_ID

    def fetch(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Mengirim query Dork ke search provider dan mengembalikan list of dict (title, link, snippet).
        Prioritas:
        1. SerpApi (jika key valid diset)
        2. Google Custom Search (jika key valid diset)
        3. Explicit Mock Mode (jika SEARCH_PROVIDER=mock)
        4. DuckDuckGo Live Search (Free live search default)
        """
        self.logger.info(f"Mengeksekusi fetch untuk dork: '{query}'")

        # 1. SerpApi Provider
        if self.provider == "serpapi" and self.serpapi_key and self.serpapi_key != "your_serpapi_key_here":
            return self._fetch_serpapi(query, num_results)

        # 2. Google CSE Provider
        elif self.provider == "google_custom_search" and self.google_api_key and self.google_api_key != "your_google_api_key_here":
            return self._fetch_google_cse(query, num_results)

        # 3. Explicit Mock Mode
        elif self.provider == "mock":
            self.logger.warning("Berjalan dalam MOCK MODE eksplisit.")
            return self._mock_fetch(query, num_results)

        # 4. DuckDuckGo Live Search (Default / Free Live Search)
        else:
            if DDGS_AVAILABLE:
                live_results = self._fetch_duckduckgo(query, num_results)
                if live_results:
                    return live_results
                self.logger.info(f"Tidak ada hasil live ditemukan untuk query: '{query}'")
                return []
            else:
                self.logger.warning("Paket ddgs tidak terpasang. Menggunakan mock fallback.")
                return self._mock_fetch(query, num_results)

    def _fetch_duckduckgo(self, query: str, num_results: int, max_retries: int = 2) -> List[Dict[str, Any]]:
        """Mengambil data pencarian live langsung via DuckDuckGo dengan retry handling."""
        for attempt in range(1, max_retries + 1):
            try:
                results = []
                with DDGS() as ddgs:
                    ddgs_results = list(ddgs.text(query, max_results=num_results))
                    for item in ddgs_results:
                        title = item.get("title") or item.get("heading") or "No Title"
                        link = item.get("href") or item.get("link") or ""
                        snippet = item.get("body") or item.get("snippet") or ""
                        if link:
                            results.append({
                                "title": title,
                                "link": link,
                                "snippet": snippet
                            })
                if results:
                    self.logger.info(f"DuckDuckGo menemukan {len(results)} hasil live.")
                    return results
            except Exception as e:
                self.logger.debug(f"Percobaan {attempt}/{max_retries} DuckDuckGo search gagal: {e}")
                if attempt < max_retries:
                    time.sleep(1.0)
        return []

    def _fetch_serpapi(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        import requests
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": self.serpapi_key,
            "num": num_results,
            "engine": "google"
        }
        try:
            resp = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT, verify=True)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("organic_results", [])[:num_results]:
                results.append({
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet", "")
                })
            return results
        except Exception as e:
            self.logger.error(f"Error pada SerpApi fetch: {e}")
            return []

    def _fetch_google_cse(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        import requests
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": query,
            "key": self.google_api_key,
            "cx": self.google_cse_id,
            "num": min(num_results, 10)
        }
        try:
            resp = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT, verify=True)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("items", []):
                results.append({
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet", "")
                })
            return results
        except Exception as e:
            self.logger.error(f"Error pada Google CSE fetch: {e}")
            return []

    def _mock_fetch(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Mock data fallback murni hanya jika mode offline/mock dipilih."""
        q_lower = query.lower()
        results = []

        if "mp4" in q_lower or "mkv" in q_lower:
            results.append({
                "title": f"Video Dokumenter Publik: {query[:35]}",
                "link": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
                "snippet": "Video dokumenter dan arsip rekaman publik berformat MP4..."
            })
        elif "claude.ai" in q_lower or "chatgpt.com" in q_lower:
            results.append({
                "title": f"Shared AI Research Conversation: {query[:35]}",
                "link": "https://chatgpt.com/share/67890-example-ai-research",
                "snippet": "Transkrip diskusi publik mengenai riset metodologi dan analisis prompt..."
            })
        elif "drive.google.com" in q_lower or "docs.google.com" in q_lower:
            results.append({
                "title": f"Google Drive Shared Resource: {query[:35]}",
                "link": "https://drive.google.com/file/d/mock-sample-doc-id/view",
                "snippet": "Modul riset dan dokumen kurikulum publik..."
            })
        else:
            results.append({
                "title": f"Dataset Keuangan Publik: {query[:35]}",
                "link": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
                "snippet": "Tabel data laporan keuangan historis dan metrik ekonomi..."
            })

        return results[:num_results]
