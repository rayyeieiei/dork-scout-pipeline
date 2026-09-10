import logging
from typing import List, Dict, Optional
from datetime import datetime

class QueryBuilder:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def get_supported_categories() -> Dict[str, str]:
        """Mengembalikan daftar kategori dorking yang didukung beserta deskripsinya."""
        return {
            "all": "Semua Kategori (PDF, Finance Data, Video, AI Chats, Google Drive)",
            "pdf": "PDF Papers (Research papers, modul kurikulum, whitepapers)",
            "gdrive": "Google Drive & Docs (Shared folders, direct files, Docs & Sheets)",
            "finance_data": "Finance & Datasets (XLSX, XLS, CSV laporan keuangan/data pasar)",
            "video": "Public Videos (File video publik MP4 / MKV)",
            "ai_chats": "Shared AI Chats (Percakapan publik Claude & ChatGPT)"
        }

    def generate_dorks(
        self, 
        topic: str, 
        category: str = "all", 
        year: Optional[str] = None,
        no_paywall: bool = True
    ) -> List[str]:
        """
        Mengubah topik riset menjadi Google Dorks tingkat lanjut yang presisi.
        
        Fitur Tambahan (Inspired by six2dez & Modern OSINT):
        - Year/Freshness Filter: Memastikan hasil relevan dengan tahun terbaru (contoh: 2025/2026).
        - Paywall Exclusions: Memfilter domain spam berbayar (Scribd, Studocu, Slideshare, Pinterest).
        - Focused Repository Targeting: Mengarahkan langsung ke direct file, Google Drive, atau repositori resmi.
        """
        clean_topic = topic.strip()
        category = category.lower().strip()

        # Siapkan filter tahun / freshness
        year_str = ""
        if year:
            clean_year = year.strip()
            try:
                yr_int = int(clean_year)
                # Mendukung variasi tahun ini dan tahun sebelumnya/setelahnya
                year_str = f'("{yr_int}" OR "{yr_int-1}")'
            except ValueError:
                year_str = f'"{clean_year}"'

        # Filter anti-paywall & anti-spam untuk file mentah
        paywall_exclusions = '-site:scribd.com -site:studocu.com -site:slideshare.net -site:pinterest.*' if no_paywall else ''

        self.logger.info(f"Membangun dork untuk '{clean_topic}' | Kategori: '{category}' | Filter Tahun: '{year or 'Semua'}'...")

        # Helper untuk menggabungkan klausa dork secara rapi
        def build_clause(base: str, target_filter: str = "") -> str:
            parts = [base]
            if year_str:
                parts.append(year_str)
            if target_filter:
                parts.append(target_filter)
            return " ".join(p.strip() for p in parts if p.strip())

        dorks_by_category = {
            "pdf": [
                build_clause(f'"{clean_topic}" filetype:pdf', paywall_exclusions),
                build_clause(f'intitle:"{clean_topic}" filetype:pdf', paywall_exclusions),
                build_clause(f'"{clean_topic}" (site:edu OR site:ac.id OR site:go.id OR site:kemdikbud.go.id) filetype:pdf')
            ],
            "gdrive": [
                build_clause(f'"{clean_topic}" site:drive.google.com/file/d/'),
                build_clause(f'"{clean_topic}" site:drive.google.com/drive/folders/'),
                build_clause(f'"{clean_topic}" site:docs.google.com/document/d/'),
                build_clause(f'"{clean_topic}" site:docs.google.com/spreadsheets/d/')
            ],
            "finance_data": [
                build_clause(f'"{clean_topic}" (filetype:xlsx OR filetype:xls OR filetype:csv) intext:"laporan keuangan"'),
                build_clause(f'"{clean_topic}" (filetype:xlsx OR filetype:csv) ("financial report" OR "balance sheet" OR dataset)')
            ],
            "video": [
                build_clause(f'"{clean_topic}" (filetype:mp4 OR filetype:mkv)'),
                build_clause(f'intitle:"{clean_topic}" (filetype:mp4 OR inurl:mp4)')
            ],
            "ai_chats": [
                build_clause(f'"{clean_topic}" (site:claude.ai/share OR site:chatgpt.com/share)')
            ]
        }

        if category in dorks_by_category:
            return dorks_by_category[category]
        elif category == "all":
            all_dorks = []
            for dork_list in dorks_by_category.values():
                all_dorks.extend(dork_list)
            return all_dorks
        else:
            self.logger.warning(f"Kategori '{category}' tidak dikenal. Default ke 'all'.")
            all_dorks = []
            for dork_list in dorks_by_category.values():
                all_dorks.extend(dork_list)
            return all_dorks
