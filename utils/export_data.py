import json
import csv
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

def save_to_json(data: List[Dict], filepath: str = "output_results.json"):
    """Menyimpan data hasil parsing ke format JSON."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"Data berhasil diekspor ke {filepath}")
    except Exception as e:
        logger.error(f"Gagal mengekspor data ke JSON: {e}")

def save_to_csv(data: List[Dict], filepath: str = "output_results.csv"):
    """Menyimpan data hasil parsing ke format CSV."""
    if not data:
        logger.warning("Tidak ada data untuk diekspor ke CSV.")
        return
    try:
        keys = data[0].keys()
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"Data berhasil diekspor ke {filepath}")
    except Exception as e:
        logger.error(f"Gagal mengekspor data ke CSV: {e}")
