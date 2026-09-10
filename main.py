import sys
import argparse
import logging
from typing import List, Dict, Any

from utils.config import config
from utils.logger import setup_logging
from utils.url_utils import normalize_url, get_domain
from utils.safety import validate_query_safety
from utils.stats import PipelineStats
from agents.query_builder import QueryBuilder
from agents.search_fetcher import SearchFetcher
from agents.data_parser import DataParser
from utils.export_data import save_to_json, save_to_csv
from utils.file_saver import download_files_batch, open_url_in_browser

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Inisialisasi logging terstruktur
logger = setup_logging()

def safe_input(prompt: str) -> str:
    """Helper input aman yang menangani EOF dan KeyboardInterrupt tanpa crash."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""

def parse_arguments():
    parser = argparse.ArgumentParser(description="Dork Scout Pipeline - Advanced OSINT & Research Harvester")
    parser.add_argument("-t", "--topic", type=str, help="Topik riset (contoh: 'soal tka matematika sma')")
    parser.add_argument("-c", "--category", type=str, 
                        choices=["all", "pdf", "finance_data", "video", "ai_chats", "gdrive"],
                        default=None,
                        help="Kategori dorking OSINT (all, pdf, finance_data, video, ai_chats, gdrive)")
    parser.add_argument("-y", "--year", type=str, default=None, 
                        help="Filter tahun rilis/kurikulum (contoh: '2025', '2026')")
    parser.add_argument("--limit", type=int, default=config.MAX_WORKERS, 
                        help=f"Jumlah hasil per dork query (default: {config.MAX_WORKERS})")
    parser.add_argument("--workers", type=int, default=config.MAX_WORKERS, 
                        help=f"Jumlah thread worker paralel (default: {config.MAX_WORKERS})")
    parser.add_argument("--no-paywall", action="store_true", default=True,
                        help="Filter website paywall & spam (Scribd, Studocu, dll.) agar langsung dapat file raw")
    return parser.parse_args()

def prompt_category_selection() -> str:
    """Menampilkan menu pemilihan kategori riset kepada user."""
    categories = [
        ("all", "1. All Categories (PDF, Finance Data, Videos, Shared AI Chats, GDrive)"),
        ("pdf", "2. PDF Papers & Modul (Research papers, modul soal, whitepapers)"),
        ("gdrive", "3. Google Drive & Docs (Shared folders, direct files, Docs, Sheets)"),
        ("finance_data", "4. Finance & Datasets (XLSX, XLS, CSV laporan keuangan/data pasar)"),
        ("video", "5. Public Videos (MP4 / MKV video files)"),
        ("ai_chats", "6. Shared AI Chats (Claude & ChatGPT shared conversations)")
    ]

    print("\n" + "-" * 70, flush=True)
    print("🎯 PILIH KATEGORI RISET OSINT:", flush=True)
    print("-" * 70, flush=True)
    for _, desc in categories:
        print(f"  {desc}", flush=True)
    print("-" * 70, flush=True)

    choice_map = {
        "1": "all",
        "2": "pdf",
        "3": "gdrive",
        "4": "finance_data",
        "5": "video",
        "6": "ai_chats",
        "all": "all",
        "pdf": "pdf",
        "gdrive": "gdrive",
        "drive": "gdrive",
        "docs": "gdrive",
        "finance": "finance_data",
        "finance_data": "finance_data",
        "video": "video",
        "ai_chats": "ai_chats",
        "chat": "ai_chats"
    }

    user_choice = safe_input("[?] Masukkan nomor pilihan [1-6] (default 1): ").lower()
    return choice_map.get(user_choice, "all")

def display_results_table(collected_data: list):
    """Menampilkan tabel ringkasan hasil temuan OSINT di terminal."""
    if not collected_data:
        return

    print("\n" + "=" * 90, flush=True)
    print("📊 RINGKASAN HASIL TEMUAN OSINT TERVERIFIKASI (RESEARCH SUMMARY)", flush=True)
    print("=" * 90, flush=True)

    category_icons = {
        "pdf": "📄 [PDF]",
        "finance_data": "📊 [FINANCE/DATA]",
        "video": "🎬 [VIDEO]",
        "ai_chats": "🤖 [AI CHAT]",
        "gdrive_folder": "📁 [GDRIVE FOLDER]",
        "gdrive_file": "📄 [GDRIVE FILE]",
        "gdoc": "📝 [GDOC]",
        "gsheet": "📊 [GSHEET]",
        "gslide": "📑 [GSLIDE]",
        "gform": "📋 [GFORM]",
        "gdrive": "📁 [GDRIVE]",
        "csv": "📊 [CSV]",
        "excel": "📊 [EXCEL]",
        "html": "🌐 [HTML]",
        "duplicate": "🔁 [DUPLICATE]"
    }

    for idx, item in enumerate(collected_data, start=1):
        doc_type = item.get("type", "unknown").lower()
        badge = category_icons.get(doc_type, f"📁 [{doc_type.upper()}]")
        title = item.get("title") or "Tanpa Judul"
        source_domain = item.get("source_domain") or "unknown_domain"
        url = item.get("canonical_url") or item.get("url") or "-"
        status = item.get("status", "unknown")

        # Format status informatif untuk Google Drive
        status_str = status
        if item.get("is_google_drive"):
            d_status = item.get("drive_status") or status
            if d_status == "redirect_resolved":
                status_str = f"redirect_resolved (HTTP {item.get('initial_http_status')} -> {item.get('final_http_status')})"
            elif d_status == "permission_required":
                status_str = "permission_required (Login / Request Access Required)"
            elif d_status == "not_found":
                status_str = "not_found (File does not exist)"
            elif d_status == "deleted_or_unavailable":
                status_str = "deleted_or_unavailable (File in trash / deleted)"
            elif d_status == "accessible":
                status_str = "accessible (Public Resource)"
            else:
                status_str = d_status
        
        raw_text = (item.get("extracted_text") or item.get("snippet") or "").strip()
        preview = " ".join(raw_text.split()[:30])
        if len(preview) < len(raw_text):
            preview += "..."

        print(f"\n[{idx}] {badge} {title}", flush=True)
        print(f"    🏢 Domain         : {source_domain}", flush=True)
        if item.get("is_google_drive") and item.get("drive_resource_type"):
            print(f"    📦 Resource Type  : Google Drive ({item.get('drive_resource_type').upper()})", flush=True)
        print(f"    🔗 Canonical Link : {url}", flush=True)
        print(f"    ⚡ Status         : {status_str}", flush=True)
        print(f"    📝 Overview       : {preview if preview else '(Tidak ada teks terdeteksi)'}", flush=True)
        print("    " + "-" * 82, flush=True)

def handle_interactive_download(
    collected_data: list, 
    output_folder: str = "downloads", 
    max_workers: int = 5,
    stats: PipelineStats = None
):
    """Menangani interaksi unduhan file, pembukaan di browser, dan melihat detail teks."""
    if not collected_data:
        return

    while True:
        print("\n" + "=" * 90, flush=True)
        print("📥 PILIHAN TINDAKAN (ACTION MENU):", flush=True)
        print("  - Masukkan nomor untuk DOWNLOAD file fisik ke 'downloads/' (contoh: '1', '1,3', 'all')")
        print("  - Ketik 'open <nomor>' untuk BUKA DIRECT LINK DI BROWSER (contoh: 'open 1')")
        print("  - Ketik 'view <nomor>' untuk BACA TEKS EKSTRAKSI LENGKAP (contoh: 'view 1')")
        print("  - Tekan [Enter] atau ketik 'skip' / 'q' untuk SELESAI")
        print("=" * 90, flush=True)

        user_input = safe_input("[?] Pilihan Anda: ").lower()

        if not user_input or user_input in ['skip', 'q', 'exit']:
            print("\n[✓] Selesai. Seluruh metadata tersimpan di 'output_results.json' dan 'output_results.csv'.", flush=True)
            break

        # Aksi: Buka URL di browser
        if user_input.startswith("open "):
            try:
                target_idx = int(user_input.split()[1]) - 1
                if 0 <= target_idx < len(collected_data):
                    target_url = collected_data[target_idx].get("canonical_url") or collected_data[target_idx].get("url")
                    print(f"[*] Membuka di browser default: {target_url}", flush=True)
                    open_url_in_browser(target_url)
                else:
                    print(f"[!] Nomor tidak valid. Pilih antara 1 - {len(collected_data)}", flush=True)
            except Exception:
                print("[!] Format salah. Gunakan contoh: 'open 1'", flush=True)
            continue

        # Aksi: Lihat teks ekstraksi lengkap
        if user_input.startswith("view "):
            try:
                target_idx = int(user_input.split()[1]) - 1
                if 0 <= target_idx < len(collected_data):
                    item = collected_data[target_idx]
                    print("\n" + "=" * 70, flush=True)
                    print(f"📖 DETAIL KONTEN: {item.get('title')}", flush=True)
                    print("=" * 70, flush=True)
                    print(f"Canonical URL: {item.get('canonical_url') or item.get('url')}")
                    print(f"Domain: {item.get('source_domain')}")
                    if item.get("is_google_drive"):
                        print(f"Drive Status: {item.get('drive_status')}")
                        print(f"File ID: {item.get('google_file_id')}\n")
                    print(item.get("extracted_text") or "(Tidak ada teks ekstraksi)", flush=True)
                    print("=" * 70, flush=True)
                else:
                    print(f"[!] Nomor tidak valid. Pilih antara 1 - {len(collected_data)}", flush=True)
            except Exception:
                print("[!] Format salah. Gunakan contoh: 'view 1'", flush=True)
            continue

        # Aksi: Batch Download Paralel
        items_to_download = []
        if user_input == "all":
            items_to_download = collected_data
        else:
            try:
                parts = [p.strip() for p in user_input.split(",") if p.strip()]
                for p in parts:
                    idx = int(p) - 1
                    if 0 <= idx < len(collected_data):
                        items_to_download.append(collected_data[idx])
                    else:
                        print(f"[!] Nomor {p} di luar jangkauan (1-{len(collected_data)})", flush=True)
            except ValueError:
                print("[!] Input tidak dikenali. Masukkan angka (misal '1,2'), 'all', 'open <nomor>', atau 'skip'.", flush=True)
                continue

        if items_to_download:
            valid_download_items = []
            for it in items_to_download:
                if it.get("is_google_drive") and not it.get("is_downloadable", True):
                    d_status = it.get("drive_status", "inaccessible")
                    print(f"[!] '{it.get('title')}' tidak dapat diunduh (Status: {d_status}). Gunakan 'open' untuk membukanya di browser.", flush=True)
                else:
                    valid_download_items.append(it)

            if valid_download_items:
                print(f"\n[*] Memulai batch download paralel ({len(valid_download_items)} file) ke folder '{output_folder}/'...", flush=True)
                results = download_files_batch(valid_download_items, output_folder=output_folder, max_workers=max_workers, stats=stats)
                print("\n[+] Hasil Unduhan:", flush=True)
                for res in results:
                    if res.get("status") == "success":
                        print(f"    [✓] {res.get('title')} -> {res.get('saved_path')}", flush=True)
                    else:
                        print(f"    [✕] {res.get('title')} -> Gagal ({res.get('url')})", flush=True)

def main():
    args = parse_arguments()

    print("==================================================", flush=True)
    print("🚀 DORK SCOUT PIPELINE - OPTIMIZED OSINT HARVESTER 🚀", flush=True)
    print("==================================================", flush=True)

    stats = PipelineStats()
    stats.start_timer()

    # 1. Input Topik Riset
    topic = args.topic
    if not topic:
        topic = safe_input("\n[>] Masukkan topik riset (contoh: 'soal tka matematika sma'): ")

    if not topic:
        logger.warning("Topik kosong, program dihentikan.")
        return

    # Validasi Keamanan Query
    is_safe, reason = validate_query_safety(topic)
    if not is_safe:
        logger.error(f"Pencegahan Keamanan: {reason}")
        print(f"\n[!] ERROR: {reason}", flush=True)
        return

    # 2. Input Kategori Riset
    category = args.category
    if not category:
        category = prompt_category_selection()

    # 3. Input Filter Tahun (Freshness)
    year = args.year
    if year is None:
        year_input = safe_input("[?] Filter Tahun / Kurikulum (contoh: '2025' atau '2026', tekan Enter untuk semua): ")
        year = year_input if year_input else None

    logger.info(f"Memulai riset | Topik: '{topic}' | Kategori: '{category}' | Tahun: '{year or 'Semua'}' | Workers: {args.workers}")

    # 4. Query Builder (Module A)
    builder = QueryBuilder()
    dork_queries = builder.generate_dorks(topic, category=category, year=year, no_paywall=args.no_paywall)
    stats.inc_queries_generated(len(dork_queries))
    logger.info(f"Dihasilkan {len(dork_queries)} dork queries tingkat lanjut.")

    # 5. Search Fetcher & Parallel Data Parser (Modules B & C)
    fetcher = SearchFetcher()
    parser = DataParser(
        timeout=config.HTTP_TIMEOUT,
        max_pdf_pages=config.PDF_MAX_PAGES,
        max_workers=args.workers,
        max_per_domain=config.MAX_REQUESTS_PER_DOMAIN
    )
    all_collected_data: List[Dict[str, Any]] = []
    seen_normalized_urls = set()

    for dork in dork_queries:
        logger.info(f"Mengeksekusi dork: {dork}")
        raw_items = fetcher.fetch(dork, num_results=args.limit)
        stats.inc_search_results(len(raw_items))

        # Deduplikasi URL secara cerdas menggunakan Normalized URL
        unique_items = []
        for item in raw_items:
            link = item.get("link", "")
            norm_link = normalize_url(link) or link
            if norm_link and norm_link not in seen_normalized_urls:
                seen_normalized_urls.add(norm_link)
                stats.inc_unique_urls()
                unique_items.append(item)
            else:
                stats.inc_duplicate_urls()

        if unique_items:
            parsed_batch = parser.parse_urls_concurrently(
                unique_items, 
                topic, 
                dork, 
                category=category,
                stats=stats
            )
            all_collected_data.extend(parsed_batch)

    stats.stop_timer()

    # 6. Export Metadata
    if all_collected_data:
        save_to_json(all_collected_data, "output_results.json")
        save_to_csv(all_collected_data, "output_results.csv")
        print(f"\n[+] Sukses! Total {len(all_collected_data)} target terverifikasi berhasil diproses dan diekspor.")

        # 7. Tampilkan Ringkasan Hasil & Menu Interaktif
        display_results_table(all_collected_data)
        handle_interactive_download(
            all_collected_data, 
            output_folder="downloads", 
            max_workers=args.workers,
            stats=stats
        )
    else:
        logger.warning("Tidak ada data yang berhasil dikumpulkan. Coba longgarkan filter kata kunci atau tahun.")

    # 8. Tampilkan Ringkasan Final Metrik Eksekusi Pipeline
    print("\n" + stats.format_summary(topic), flush=True)

if __name__ == "__main__":
    main()
