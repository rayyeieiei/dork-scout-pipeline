# 🚀 Dork Scout Pipeline

**Automated OSINT Harvester & Multi-Category Dorking Pipeline**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: Pytest](https://img.shields.io/badge/tests-pytest%20(25%20passed)-brightgreen.svg)]()

`dork-scout-pipeline` adalah pipeline otomatisasi riset **Open Source Intelligence (OSINT)** berbasis Python yang dirancang untuk mencari, memvalidasi, menormalisasi, mengekstrak, dan mengunduh berkas publik dari internet (PDF laporan riset, dataset keuangan, video publik, shared AI chats, dan Google Drive/Docs).

---

## ✨ Fitur Utama

- 🔍 **Multi-Category OSINT Query Builder**:
  - `pdf`: Dokumen riset, whitepaper, kurikulum, laporan tahunan (`filetype:pdf`).
  - `gdrive`: Google Drive shared folders, direct files, Google Docs, Sheets, Slides.
  - `finance_data`: Laporan keuangan & dataset pasar (`xlsx`, `xls`, `csv`).
  - `video`: File video publik (`mp4`, `mkv`).
  - `ai_chats`: Transkrip percakapan publik dari Claude & ChatGPT.
- 🛡️ **Redirect-Aware Google Drive Link Resolver**:
  - Deteksi dan normalisasi ke Canonical URL stabil (`https://drive.google.com/file/d/<ID>/view`).
  - Penanganan HTTP 3xx redirect tanpa salah menganggap link sebagai error.
  - Preservasi parameter `resourcekey`.
  - Klasifikasi status aksesibilitas (`accessible`, `redirect_resolved`, `permission_required`, `not_found`, `deleted_or_unavailable`, `rate_limited`).
  - Proteksi otomatis melewati unduhan file privat/rusak.
- 📅 **Freshness & Year Filtering (`--year`)**:
  - Filter tahun publikasi otomatis (`"2025" OR "2024"`) untuk memastikan hasil riset relevan dan terkini.
- 🚫 **Anti-Paywall & Spam Exclusion (`--no-paywall`)**:
  - Menyaring platform paywall (Scribd, Studocu, Slideshare, Pinterest) untuk mengutamakan berkas direct download publik.
- ⚡ **Multi-Threading & Connection Pooling**:
  - Eksekusi paralel menggunakan `ThreadPoolExecutor`.
  - Thread-local `requests.Session` dengan connection pooling & bounded retry (exponential backoff).
- 🚦 **Per-Domain Concurrency Limit**:
  - Mencegah pembebanan berlebih pada satu server target menggunakan `BoundedSemaphore` per domain.
- 🔒 **Content Hash Deduplication (SHA-256)**:
  - Fingerprinting SHA-256 pada konten biner untuk mendeteksi berkas duplikat lintas domain.
- 🤖 **Kepatuhan Etika Web (`robots.txt`)**:
  - Pengecekan otomatis `robots.txt` sebelum crawling/scraping target.
- 📊 **Export & Interactive Terminal Menu**:
  - Ekspor otomatis ke `output_results.json` dan `output_results.csv`.
  - Batch parallel raw file downloader ke folder `downloads/`.
  - Ringkasan metrik eksekusi terminal yang bersih (*dependency-free*).

---

## 📁 Struktur Repositori

```text
dork-scout-pipeline/
├── agents/
│   ├── query_builder.py     # Module A: Dork generator multi-kategori & freshness
│   ├── search_fetcher.py    # Module B: Live search (DuckDuckGo, SerpApi, Google CSE)
│   └── data_parser.py       # Module C: Concurrent parser, rate limiter, hash registry
├── utils/
│   ├── config.py            # Konfigurasi terpusat & defensive parser
│   ├── drive_resolver.py    # Google Drive link resolver & accessibility validator
│   ├── export_data.py       # Ekspor JSON & CSV
│   ├── file_saver.py        # Parallel chunk streaming downloader & sanitasi nama file
│   ├── logger.py            # RotatingFileHandler & credential masking filter
│   ├── robots_checker.py    # Thread-safe robots.txt validator
│   ├── safety.py            # Query compliance & exploit rejection
│   ├── stats.py             # Dataclass pelacak metrik eksekusi
│   └── url_utils.py         # URL normalization, domain extractor, SHA-256
├── tests/                   # Pytest test suite (100% offline & mocked)
├── main.py                  # CLI & Interactive Menu entry point
├── requirements.txt         # Daftar dependensi Python
└── README.md
```

---

## 🛠️ Panduan Instalasi

1. **Clone repository:**
   ```bash
   git clone https://github.com/rayyeieiei/dork-scout-pipeline.git
   cd dork-scout-pipeline
   ```

2. **Buat virtual environment (opsional tapi disarankan):**
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependensi:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Konfigurasi Environment:**
   Salin `.env.example` menjadi `.env`:
   ```bash
   cp .env.example .env
   ```
   *Secara default, pipeline menggunakan `SEARCH_PROVIDER=duckduckgo` yang gratis dan langsung aktif tanpa API key.*

---

## 🚀 Cara Penggunaan

### 1. Mode Interaktif (Tanya-Jawab Terminal)
Cukup jalankan:
```bash
python main.py
```
Ikuti prompt di terminal:
1. Masukkan topik riset (contoh: `soal tka matematika sma`).
2. Pilih kategori (1-6).
3. Masukkan filter tahun (contoh: `2025` atau tekan Enter untuk semua tahun).
4. Gunakan action menu untuk download file, buka link di browser (`open <nomor>`), atau baca teks (`view <nomor>`).

### 2. Mode Cepat CLI (Non-Interaktif)
```bash
# Cari PDF modul matematika tahun 2025:
python main.py -t "soal tka matematika sma" -c pdf --year 2025 --limit 5

# Cari folder & dokumen Google Drive publik:
python main.py -t "kurikulum merdeka sma" -c gdrive --limit 5

# Cari dataset laporan keuangan:
python main.py -t "laporan keuangan pt telkom" -c finance_data --year 2024
```

---

## 🧪 Menjalankan Pengujian (Tests)

Jalankan seluruh test suite menggunakan `pytest`:
```bash
python -m pytest -v
```
Seluruh 25 test unit berjalan 100% secara offline menggunakan mocking tanpa ketergantungan internet.

---

## ⚖️ Batasan Etika & Legalitas

1. Proyek ini ditujukan **eksklusif untuk riset data publik yang terindeks dan legal (OSINT)**.
2. Tidak menyediakan fungsionalitas untuk credential harvesting, pembobolan autentikasi, bypass CAPTCHA, atau eksploitasi celah keamanan.
3. Kueri yang mengarah ke kebocoran kredensial (misal `.env password`, `sql dump`, `id_rsa`) akan otomatis ditolak oleh `utils/safety.py`.

---

## 📜 Lisensi

Didistribusikan di bawah lisensi MIT.
