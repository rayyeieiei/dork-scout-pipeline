import os
import re
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional
from utils.config import config

# Pattern untuk mendeteksi key atau token sensitif yang tidak boleh masuk ke log
SENSITIVE_PATTERNS = [
    re.compile(r'(api_key|apikey|secret|token|password|auth|authorization)=([^&\s]+)', re.IGNORECASE),
    re.compile(r'(Bearer\s+)[a-zA-Z0-9_\-\.]+', re.IGNORECASE),
]

class SensitiveFilter(logging.Filter):
    """Filter untuk menyensor data sensitif (API key, token, credential) dari log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.sanitize(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.sanitize(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self.sanitize(str(a)) for a in record.args)
        return True

    @staticmethod
    def sanitize(text: str) -> str:
        for pat in SENSITIVE_PATTERNS:
            text = pat.sub(r'\1=***REDACTED***', text)
        return text

def setup_logging(log_file: Optional[str] = None, log_level: Optional[str] = None) -> logging.Logger:
    """
    Mengonfigurasi logging terstruktur untuk Dork Scout Pipeline:
    - File handler menggunakan RotatingFileHandler (maks 5MB, 3 file cadangan).
    - Console handler untuk terminal dengan format bersih.
    - Dilengkapi SensitiveFilter agar tidak membocorkan kredensial ke log.
    """
    target_log_file = log_file or config.LOG_FILE
    target_level_name = log_level or config.LOG_LEVEL
    level = getattr(logging, target_level_name.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Bersihkan handler sebelumnya jika ada
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    sensitive_filter = SensitiveFilter()

    # 1. Console Handler (Output terminal rapi)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    console_handler.addFilter(sensitive_filter)
    root_logger.addHandler(console_handler)

    # 2. File Handler (Rotating log terstruktur)
    try:
        log_dir = os.path.dirname(target_log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            target_log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)  # File mencatat lebih detail hingga level DEBUG
        file_format = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s'
        )
        file_handler.setFormatter(file_format)
        file_handler.addFilter(sensitive_filter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        root_logger.warning(f"Tidak dapat membuat RotatingFileHandler untuk '{target_log_file}': {e}")

    return logging.getLogger("dork_scout")
