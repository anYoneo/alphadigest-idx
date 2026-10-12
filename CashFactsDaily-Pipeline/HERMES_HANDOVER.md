# 🚀 HANDOVER DOCUMENT: CashFactsDaily & FaktaCuan AI Video Automation Pipeline
**Target Agent:** Hermes  
**Project Location:** `g:\My Drive\Model2\CashFactsDaily-Pipeline\`  
**Project Goal:** Automated AI-generated video content business pipeline for Facebook Pages (CMP Ads) & YouTube Shorts (YPP) across two language brands.

---

## 📌 1. EXECUTIVE SUMMARY & BUSINESS STRATEGY

### A. Dual-Brand Architecture
1. **🇺🇸 @CashFactsDaily (English)**
   * **Target:** US / UK / Global Audience (Tier 1 CPM: $10 - $23+)
   * **Tone:** Punchy, authoritative, mind-blowing, high-energy
   * **CTA:** *"Follow @CashFactsDaily for daily mind-blowing facts"*
2. **🇮🇩 @FaktaCuan (Bahasa Indonesia)**
   * **Target:** Indonesia & Southeast Asia (High viral volume)
   * **Tone:** Santai, gaul, relatable, bikin kaget, sentuhan humor
   * **CTA:** *"Follow @FaktaCuan buat fakta mencengangkan setiap hari!"*

### B. Content Pillars (4-Pillar Hub & Spoke)
* **🔥 Newsjacking & Trends (30%):** Breaking AI/Tech updates, viral shifts.
* **📚 Education & How-To (30%):** Step-by-step AI workflows, tips, listicles (Save-worthy).
* **🎭 Deep Storytelling (25%):** Mind-blowing facts, historical tech heists, mystery narratives (DM-Share driver).
* **🎯 Authority & Review (15%):** Tool comparisons, tier lists, ManyChat keyword prompts.

### C. Target Output & Budget Tier
* **Tier 1 Budget:** ~$45/month (HeyGen $29 + ElevenLabs $5 + Ideogram $8 + DeepSeek API ~$3).
* **Capacity:** ~15–20 video per bulan (1 video per 2 hari per brand, cross-post ke FB & YouTube Shorts = 4 upload actions).

---

## 🛠️ 2. WHAT HAS BEEN COMPLETED (PHASE 1)

All files for **Phase 1 (Topic Scanning & Automated Script Generation)** are completely written and ready inside `CashFactsDaily-Pipeline/`:

```
CashFactsDaily-Pipeline/
├── .env.example              # Template API keys
├── .gitignore                # Git rules ignoring media outputs & env
├── requirements.txt          # Python dependencies (pytrends, openai, rich, feedparser, etc.)
├── run_pipeline.py           # 🚀 Master CLI orchestrator (scan, generate, full, status)
├── config/
│   └── settings.yaml         # Complete config (Brands, pillars, sources, paths, LLM settings)
├── src/
│   ├── utils.py              # Shared tools: load_config, load_env, ensure_dirs, JSON/log helpers
│   ├── topic_scanner.py      # Multi-source scraper (Google Trends, Reddit, Hacker News)
│   └── script_generator.py   # DeepSeek AI scriptwriter with 4 pillar prompts (EN + ID)
└── HERMES_HANDOVER.md        # This handover document
```

### Detail File yang Sudah Dibuat:
1. **`config/settings.yaml`**: Menyimpan seluruh konfigurasi non-rahasia (LLM endpoints, 4 content pillars with weights, subreddits, Google Trends regions, folder paths).
2. **`src/utils.py`**: Helper untuk auto-create directories, path resolution, format ISO timestamp, rich console logging, dan environment loading.
3. **`src/topic_scanner.py`**:
   * Scrape **Google Trends** (US & ID) via `pytrends`.
   * Scrape **Reddit** hot posts (6 subreddits: `technology`, `artificial`, `todayilearned`, `science`, `Futurology`, `MachineLearning`) via public JSON endpoints (tanpa OAuth ribet).
   * Scrape **Hacker News** top stories via Firebase API.
   * Keyword-based auto classification (`technology_ai`, `science_nature`, `business_finance`, `storytelling_facts`, `trending_viral`).
   * Deduplikasi & sorting score descending.
   * Output file: `data/topics/topics_YYYY-MM-DD.json`.
4. **`src/script_generator.py`**:
   * Membaca file `topics_YYYY-MM-DD.json`.
   * Memilih top N topik dengan diversitas kategori.
   * Menentukan pillar secara otomatis dari konteks & keyword.
   * Mengirim prompt ke **DeepSeek API** (OpenAI compatible client).
   * Menghasilkan script terstruktur (**Hook 0-3s**, **Setup/Loop 3-12s**, **Value 12-45s**, **Climax 45-55s**, **CTA 55-60s**) dengan visual cue `[B-Roll]` dan penekanan `*words*`.
   * Menghasilkan **2 file Markdown per topik**: 1 English (`..._en_...md`) dan 1 Indonesian (`..._id_...md`).
   * Output directory: `scripts/pending/`.
5. **`run_pipeline.py`**: CLI master dengan perintah:
   * `python run_pipeline.py scan` (Scrape topik saja)
   * `python run_pipeline.py generate [-n 4]` (Generate naskah saja)
   * `python run_pipeline.py full` (Scan + Generate sekaligus)
   * `python run_pipeline.py status` (Cek status pending/approved/published)

---

## ⚡ 3. IMMEDIATE PREREQUISITES / ACTION REQUIRED ON HOST

Sebelum menjalankan script Phase 1:
1. **Install Python 3.11+** di OS (pastikan centang *"Add Python to PATH"*).
2. **Install requirements:**
   ```powershell
   cd "g:\My Drive\Model2\CashFactsDaily-Pipeline"
   python -m pip install -r requirements.txt
   ```
3. **Setup `.env`:**
   ```powershell
   copy .env.example .env
   # Masukkan DEEPSEEK_API_KEY=sk-xxxx di dalam .env
   ```
4. **Test Run Phase 1:**
   ```powershell
   python run_pipeline.py full
   ```

---

## 🎯 4. NEXT PHASES TO BUILD (ROADMAP FOR HERMES)

Hermes diharapkan melanjutkan implementasi **Phase 2, Phase 3, dan Phase 4** dengan rincian arsitektur teknis berikut:

```
┌─────────────────────────────────────────────────────────────┐
│                      PIPELINE ROADMAP                       │
├─────────────────────────────────────────────────────────────┤
│ [PHASE 1] DONE: topic_scanner.py -> script_generator.py     │
│       │                                                     │
│       ▼                                                     │
│ [PHASE 2] NEXT: media_generator.py (ElevenLabs + HeyGen)    │
│       │         assembler.py (FFmpeg + Whisper Subtitles)   │
│       ▼                                                     │
│ [PHASE 3] NEXT: uploader.py (FB Graph API + YouTube API v3) │
│       │                                                     │
│       ▼                                                     │
│ [PHASE 4] NEXT: Master Daily Cron Scheduler + Analytics     │
└─────────────────────────────────────────────────────────────┘
```

---

### 🚧 PHASE 2: Media Asset Generation & Auto-Assembly (PRIORITAS UTAMA HERMES)

#### Task 2.1: Buat `src/media_generator.py`
Script ini mengambil script yang sudah dipindahkan user ke folder `scripts/approved/`:
1. **ElevenLabs Audio Generator:**
   * Endpoint: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
   * Gunakan multilingual model (`eleven_multilingual_v2` / `flash_v2_5`).
   * Konfigurasi voice ID terpisah di `settings.yaml` untuk English (US natural) dan Indonesian (natural, non-bule).
   * Simpan file audio di `media/audio/{script_name}.mp3`.
2. **HeyGen Avatar Video Generator:**
   * Upload / gunakan audio yang sudah digenerate ke HeyGen API (`https://api.heygen.com/v2/video/generate`).
   * Gunakan stock avatar ID yang konsisten (AI-generated look).
   * Polling status render hingga selesai -> download MP4 ke `media/avatar/{script_name}_avatar.mp4`.
3. **Ideogram / FLUX Thumbnail Generator:**
   * Extract title & hook dari script markdown.
   * Buat prompt thumbnail dengan typography teks kontras tinggi.
   * Simpan thumbnail di `media/thumbnails/{script_name}.png`.
4. **Music Selector:**
   * Pilih background music royalty-free secara acak dari `media/music_library/` (volume ducking 15-20%).

#### Task 2.2: Buat `src/assembler.py` (FFmpeg + Whisper)
Script untuk merakit video mentah menjadi draft video siap review:
1. **Auto Subtitles:** Ekstrak timing kata/kalimat menggunakan `openai-whisper` atau generate format `.srt` / `.ass` dengan gaya kinetic / box highlight.
2. **Video Composition (FFmpeg):**
   * Overlay Avatar Video (posisi talking head atau full screen).
   * Insert B-roll image cuts di sela-sela video sesuai marker `[B-Roll: ...]`.
   * Burn-in animated subtitles di tengah/bawah (9:16 vertical 1080x1920).
   * Mix voiceover audio (100% volume) + Background music (15% volume with auto ducking).
3. **Output:** Simpan ke `output/drafts/{script_name}_draft.mp4`.

---

### ⏳ PHASE 3: Auto-Uploader & Platform Distribution

#### Task 3.1: Buat `src/uploader.py`
Script untuk mendistribusikan video yang sudah dipoles/disetujui di `output/final/`:
1. **Facebook Graph API (`facebook-sdk` / direct `requests`):**
   * Upload video ke Facebook Page via `POST /{page_id}/video_reels` atau `POST /{page_id}/videos`.
   * Auto-generate SEO caption: narrative 150–300 kata + 3–5 targeted hashtags + discussion prompt.
   * Pinned comment untuk link / CTA.
2. **YouTube Data API v3 (`google-api-python-client`):**
   * Upload video sebagai YouTube Short (kategori Science & Technology).
   * Keyword-rich title + 100+ kata description + 5–8 tags.
   * Set thumbnail custom.
3. Setelah berhasil upload -> pindahkan file markdown dari `scripts/approved/` ke `scripts/published/`.

---

### ⏳ PHASE 4: Master Scheduler & Operations

1. **Automation Cron / Task Scheduler:**
   * Script runner otomatis setiap jam 07:00 pagi (Scan & Generate).
   * Notifikasi atau review window bagi user (~10–20 menit) untuk CapCut polish & approve.
   * Scheduled upload otomatis sesuai jam peak engagement:
     * **EN:** 09:00–11:30 AM EST & 05:00–07:30 PM EST
     * **ID:** 09:00–11:30 AM WIB & 05:00–07:30 PM WIB

---

## 📋 5. PETUNJUK KERJA UNTUK HERMES (HANDOVER INSTRUCTIONS)

1. **Baca Dokumen Ini & Codebase:**
   * Cek `config/settings.yaml` untuk memahami struktur konfigurasi.
   * Cek `src/utils.py`, `src/topic_scanner.py`, dan `src/script_generator.py` untuk memahami pipeline yang sudah aktif.
2. **Lanjutkan Pembangunan Phase 2:**
   * Buat file `src/media_generator.py` untuk mengintegrasikan ElevenLabs, HeyGen, dan Thumbnail generator.
   * Buat file `src/assembler.py` menggunakan `ffmpeg-python` atau sub-process FFmpeg untuk video composition.
   * Update `run_pipeline.py` agar mendukung sub-command baru: `assemble`, `media`, dan `upload`.
3. **Pertahankan Filosofi Proyek:**
   * Tetap pertahankan isolasi multi-bahasa (@CashFactsDaily vs @FaktaCuan).
   * Hindari "AI Slop" dengan menjaga fleksibilitas editing manusia di tahap intermediate (`scripts/approved/` dan `output/drafts/`).
   * Jangan hardcode API keys; selalu gunakan `load_env()` dan file `.env`.
