---
name: corporate-action-summarizer
description: Spesialis ekstraksi dan penyusunan laporan aksi korporasi mandiri (Dividen, Tender Offer/MTO, Rights Issue/PMHMETD, Stock Split, Buyback, RUPS) menjadi dokumen intelijen aksi korporasi terpisah.
---

# Skill: Corporate Action Summarizer

## Pemicu (Trigger)
Gunakan skill ini ketika:
- Memproses pengumuman aksi korporasi signifikan (Dividen, MTO, Rights Issue, Stock Split, Buyback, RUPSLB).
- Pengguna meminta: "rangkum aksi korporasi [emiten]", "buat laporan khusus MTO [emiten]", "analisis rights issue [emiten]".
- Diaktifkan secara otomatis oleh skrip `daily_run.py` ketika mendeteksi aksi korporasi bernilai strategis tinggi.

---

## Standar Output Laporan Aksi Korporasi Standalone

Setiap pengumuman aksi korporasi strategis akan dibuatkan **1 file khusus terpisah** di folder `reports/summaries/corporate-actions/` dan diunggah ke Obsidian di `knowledge-base/corporate-actions/[EMITEN]_[KATEGORI]_[TANGGAL].md`.

### Skema Struktur Berkas Khusus Aksi Korporasi:
1. **Judul Utama & Status Sentimen (Headline & Sentiment Rating)**
2. **📌 Ringkasan Eksekutif & Tujuan Strategis (Executive Summary & Strategic Purpose)**
3. **📊 Fakta Material & Parameter Keuangan (Key Material Facts & Parameters)**
4. **👥 Struktur Kepemilikan, Pengendali & Pembeli Siaga (Shareholders & Standby Buyers)**
5. **🎯 Alokasi & Rencana Penggunaan Dana (Use of Proceeds - Khusus Rights Issue / Private Placement)**
6. **📅 Timeline & Jadwal Pelaksanaan (Important Dates Calendar)**
7. **📈 Diagram Visual Flowchart (Mermaid Diagram)**
8. **💡 Rekomendasi Investor & Strategi Trading (Actionable Investor Strategy / Arbitrage Play)**

---

## Modul Pembentuk Berkas (`corporate_action_builder.py`)
Skrip eksekusi berada di: `g:\My Drive\Model2\.agents\skills\corporate-action-summarizer\scripts\corporate_action_builder.py`
