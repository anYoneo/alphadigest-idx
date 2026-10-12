---
name: financial-summarizer
description: Spesialis ekstraksi laporan keuangan, perhitungan rasio keuangan (likuiditas, profitabilitas, solvabilitas), dan pembuatan rangkuman kinerja bisnis yang komprehensif.
---

# Skill: Financial Summarizer

## Pemicu (Trigger)
Gunakan skill ini ketika diminta untuk:
- "rangkum laporan keuangan [nama file]"
- "analisis kinerja keuangan [perusahaan]"
- "ekstrak balance sheet / income statement dari [file]"
- "hitung rasio keuangan untuk [perusahaan]"

---

## Panduan Perhitungan & Metrik Keuangan
Agen wajib memastikan akurasi perhitungan rasio keuangan menggunakan rumus standar berikut:

### 1. Rasio Likuiditas (Liquidity Ratios)
* **Current Ratio:**
  $$\text{Current Ratio} = \frac{\text{Total Aset Lancar}}{\text{Total Liabilitas Jangka Pendek}}$$
* **Quick Ratio:**
  $$\text{Quick Ratio} = \frac{\text{Total Aset Lancar} - \text{Persediaan}}{\text{Total Liabilitas Jangka Pendek}}$$

### 2. Rasio Profitabilitas (Profitability Ratios)
* **Gross Profit Margin (GPM):**
  $$\text{GPM} = \frac{\text{Laba Kotor}}{\text{Pendapatan}} \times 100\%$$
* **Net Profit Margin (NPM):**
  $$\text{NPM} = \frac{\text{Laba Bersih}}{\text{Pendapatan}} \times 100\%$$
* **Return on Assets (ROA):**
  $$\text{ROA} = \frac{\text{Laba Bersih}}{\text{Total Aset}} \times 100\%$$
* **Return on Equity (ROE):**
  $$\text{ROE} = \frac{\text{Laba Bersih}}{\text{Total Ekuitas}} \times 100\%$$

### 3. Rasio Solvabilitas / Leverage (Solvency Ratios)
* **Debt to Equity Ratio (DER):**
  $$\text{DER} = \frac{\text{Total Liabilitas}}{\text{Total Ekuitas}}$$
* **Debt to Asset Ratio (DAR):**
  $$\text{DAR} = \frac{\text{Total Liabilitas}}{\text{Total Aset}}$$

### 4. Perhitungan Pertumbuhan Tren (Growth Trend Metrics: YoY & QoQ)
* **Pertumbuhan YoY (Year-over-Year Growth):**
  $$\text{YoY Growth} = \frac{\text{Nilai Periode Berjalan} - \text{Nilai Periode Sama Tahun Lalu}}{\text{Nilai Periode Sama Tahun Lalu}} \times 100\%$$
* **Pertumbuhan QoQ (Quarter-on-Quarter Growth):**
  $$\text{QoQ Growth} = \frac{\text{Nilai Kuartal Berjalan} - \text{Nilai Kuartal Sebelumnya}}{\text{Nilai Kuartal Sebelumnya}} \times 100\%$$
* **Perubahan Margin & Rasio ($\Delta$ Margin Points):**
  $$\Delta \text{Margin (pts)} = \text{Margin Periode Berjalan (\%)} - \text{Margin Periode Lalu (\%)}$$

---

## Langkah-Langkah Eksekusi (Multi-Agent Relay)

### Langkah 1: Pemicuan Helper Agent (`financial-data-extractor`)
1. Cari berkas laporan keuangan target di folder `reports/raw/[EMITEN]/`.
2. Panggil/libatkan `financial-data-extractor` untuk memindai berkas mentah (PDF/XLSX).
3. Agen ekstraktor akan mengembalikan **Paket Data 3-Layer**:
   - **Layer 1** — Core Financials (Neraca, Laba Rugi, Arus Kas)
   - **Layer 2** — KPI Operasional Sektoral (sesuai `sector_map.json`)
   - **Layer 3** — Qualitative Intelligence (MD&A, catatan kaki, opini auditor)
4. Periksa **Ringkasan Serah Terima Data** dari extractor untuk mengetahui kelengkapan tiap layer.

### Langkah 2: Memvalidasi Data dari Extractor Agent
* **EBITDA:**
  $$\text{EBITDA} = \text{Laba Operasi (EBIT)} + \text{Depresiasi} + \text{Amortisasi}$$
* **Net Debt to EBITDA:**
  $$\text{Net Debt/EBITDA} = \frac{\text{Total Utang Berbunga} - \text{Kas \& Setara Kas}}{\text{EBITDA}}$$

1. Terima paket 3-layer dari `financial-data-extractor`.
2. Jalankan validasi neraca wajib dari Layer 1:
   - ✅ **Cek Keseimbangan**: Total Aset = Total Liabilitas + Total Ekuitas (toleransi selisih pembulatan < 0,1%)
   - ✅ **Cek Kelengkapan**: Pastikan 3 laporan utama tersedia (Neraca, Laba Rugi, Arus Kas)
   - ✅ **Cek Konsistensi**: Laba Bersih di Laba Rugi = Laba Bersih di Arus Kas (metode tidak langsung)
3. Jika neraca tidak seimbang atau data tidak lengkap:
   - Tandai kolom data yang bermasalah dengan `[DATA TIDAK VALID — PERLU VERIFIKASI]`
   - Minta `financial-data-extractor` mengulang ekstraksi pada halaman terkait (sertakan nomor halaman PDF)
4. Jika data sudah valid, lanjut ke Langkah 3.

### Langkah 3: Perhitungan Rasio Keuangan

Hitung seluruh rasio menggunakan rumus standar di seksi "Panduan Perhitungan" di atas:

1. **Rasio Likuiditas**: Current Ratio, Quick Ratio
2. **Rasio Profitabilitas**: GPM, NPM, ROA, ROE, EBITDA, EBITDA Margin
3. **Rasio Solvabilitas**: DER, DAR, Net Debt/EBITDA, Interest Coverage Ratio (EBIT ÷ Beban Bunga)
4. **Pertumbuhan Tren**: YoY & QoQ untuk Pendapatan, Laba Kotor, Laba Bersih, dan Total Aset

> ⚠️ **Aturan Zero Hallucination**: Jika data tidak tersedia untuk menghitung suatu rasio, tulis `-` (tanda hubung) — JANGAN menebak atau menginterpolasi angka.

**Tools pendukung:**

1. **`sector_kpi_parser.py`**: Helper regex parser untuk mengekstrak KPI spesifik sektor dari Layer 2.
2. **`valuation_engine.py`**: Mesin kalkulator valuasi yang menghitung 3-Stage DCF, PE/PBV Multiples, Blended Fair Value & Margin of Safety (MOS %), serta sinyal rating (`🟢 UNDERVALUED`, `⚪ FAIRLY VALUED`, `🔴 OVERVALUED`).
3. **`public_expose_builder.py`**: Pemroses berkas Public Expose (Q&A Pairs & Materi), membersihkan noise header bursa sebelum diterbitkan ke Obsidian Vault.

---

## 🚀 Standardisasi Analisis Transformasi Bisnis (Rule #8)
Setiap penyusunan Laporan Analisis Keuangan Mendalam wajib menyajikan seksi **`## 🚀 Transformasi Bisnis & Model Usaha Strategis`**:
- Menganalisis *pivoting* model bisnis (misal: pengalihan dari distributor konvensional ke ekosistem EV / Kendaraan Listrik).
- Menjelaskan konteks strategis di balik fluktuasi laba/rugi (misal: *inventory clearance* / diskon promosi cuci gudang persediaan stok lama demi pencairan kas/reallokasi modal kerja).
- Memetakan basis daya saing & jaringan distribusi untuk pertumbuhan jangka panjang.

### Langkah 4: Menulis Rangkuman Terstruktur

Output laporan analisis keuangan wajib mencakup **5 seksi utama** berikut:

#### Seksi 1: Scorecard Kinerja Finansial (Layer 1)
- Tabel rasio likuiditas, profitabilitas, solvabilitas, dan pertumbuhan YoY/QoQ.
- Analisis kualitatif singkat per tren (misal: "NPM naik 2% karena efisiensi biaya operasional").

#### Seksi 2: KPI Operasional Sektoral (Layer 2)
- Tabel KPI sektor dari paket Layer 2 (NPL/NIM untuk bank, volume produksi untuk tambang, dst.).
- Bandingkan dengan periode sebelumnya & berikan konteks (naik/turun karena apa).

#### Seksi 3: Qualitative Intelligence Digest (Layer 3)
- Ringkasan opini auditor & catatan penting.
- Poin-poin material dari MD&A: penjelasan kinerja, guidance, strategi.
- Red flags dari catatan kaki: kewajiban kontinjensi, RPT material, covenant utang.
- Pipeline proyek & aksi korporasi yang diumumkan.

#### Seksi 4: Transformasi Bisnis & Strategi (Rule #8)
- Analisis pivoting model bisnis & konteks strategis di balik angka-angka.

#### Seksi 5: Kesimpulan & Poin Perhatian
- Ringkasan 3-5 poin terpenting untuk investor.
- Pertanyaan kritis yang perlu dijawab di Public Expose atau laporan berikutnya.

**Format penyimpanan**: `[Perusahaan]_[Tahun]_[Kuartal]_Summary.md` di folder `reports/summaries/`.

