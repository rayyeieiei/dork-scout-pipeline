import logging
import threading
from urllib.parse import urlparse
import urllib.robotparser
from typing import Dict

class RobotsChecker:
    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent
        self.parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def can_fetch(self, url: str) -> bool:
        """Memeriksa apakah robots.txt domain target mengizinkan scraping URL ini secara thread-safe."""
        if not url:
            return False
        try:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            robots_url = f"{base_url}/robots.txt"

            with self._lock:
                if base_url not in self.parsers:
                    rp = urllib.robotparser.RobotFileParser()
                    rp.set_url(robots_url)
                    try:
                        rp.read()
                        self.parsers[base_url] = rp
                    except Exception as e:
                        self.logger.debug(f"Gagal membaca robots.txt dari {base_url}: {e}. Default: ALLOW.")
                        return True

                rp = self.parsers[base_url]

            return rp.can_fetch(self.user_agent, url)
        except Exception as e:
            self.logger.debug(f"Error pada evaluasi robots.txt untuk {url}: {e}")
            return True
