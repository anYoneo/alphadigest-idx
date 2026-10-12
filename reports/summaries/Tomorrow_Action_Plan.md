# 🗓️ Rencana Eksekusi Besok (Tomorrow's Strategic Action Plan)

## 📌 Ringkasan Capaian Hari Ini (Today's Accomplishments)
1. **🗄️ SQLite Database Engine (`market_intelligence.db`)**: 108 pengumuman, dividen, MTO, dan konversi waran tersimpan di database relasional.
2. **🕸️ Obsidian Knowledge Graph (`[[WikiLinks]]`)**: Note emiten, pengendali, dan topik terhubung secara otomatis di Graph View.
3. **📊 Visual Diagram (Mermaid)**: Grafik alur MTO `MAPI`, timeline dividen `TAPG` / `AMAR`, dan alur Rights Issue `BUVA`.
4. **💰 Alpha Signal Radar (`Trading_Signals_20260803.md`)**: Pendeteksi peluang cuan dividen (~8.5% yield), arbitrase MTO, dan pertumbuhan laba +194%.
5. **📜 Rules Rights Issue (PMHMETD)**: Ekstraksi 5 komponen lengkap Rights Issue (studi kasus `BUVA`).

---

## 🚀 Agendakan Pengembangan Besok (Tomorrow's Feature Backlog)

### 1. 📈 Mesin Valuasi Otomatis (Automated Valuation Engine: 3-Stage DCF & Multiples)
- **Fungsi**: Begitu Laporan Keuangan (LK) kuartalan/tahunan dipublikasikan, sistem akan langsung mengekstraksi Neraca & Laba Rugi untuk menghitung **Nilai Wajar (*Fair Value*)** emiten secara otomatis:
  - **3-Stage Discounted Cash Flow (DCF)**
  - **Relative Valuation**: P/E Ratio, P/BV Ratio, ROE vs Rata-Rata Historis 5 Tahun & Industri.
- **Output Note**: `knowledge-base/valuations/Valuation_[EMITEN].md`

---

### 2. 🏛️ Parser KPI Khusus Sektor (Sector-Specific KPI Taxonomy)
- **Perbankan (`BBRI`, `BBCA`, `AMAR`)**: Ekstraksi NPL Ratio, NIM (Net Interest Margin), CAR, LDR, & CASA.
- **Telko (`TLKM`, `TOWR`, `ISAT`)**: Ekstraksi ARPU & Tenancy Ratio.
- **Tambang & Energi (`ANTM`, `BUMI`, `PGAS`)**: Ekstraksi Volume Produksi, Cash Cost/Ton, & Average Selling Price (ASP).

---

### 3. 👤 Auto-Profile Entity Generator (Pusat Data Emiten)
- Pembuatan otomatis berkas profil emiten baru di `knowledge-base/entities/[EMITEN].md` begitu emiten baru muncul di radar BEI, mencakup sektor usaha, profil manajemen, dan histori aksi korporasi.

---

### 4. 🌐 Dashboard Web HTML Interaktif (Interactive Web Dashboard)
- Ekspor otomatis laporan harian menjadi halaman web HTML modern interaktif dengan fitur filter cepat (*Bullish*, *Bearish*, *Dividen*, *MTO*, *Rights Issue*) langsung dari browser.
