---
name: financial-data-extractor
description: Helper agent khusus membaca berkas mentah (PDF/XLSX), mengekstraksi angka Neraca, Laba Rugi, Arus Kas, KPI operasional sektoral, dan informasi kualitatif material — memformatnya menjadi paket data 3-layer bersih untuk Financial Summarizer.
---

# Skill: Financial Data Extractor (Helper Agent)

## Pemicu (Trigger)
Gunakan skill ini sebagai langkah pertama sebelum melakukan analisis keuangan:
- Ekstraksi data mentah dari file PDF/XLSX laporan keuangan.
- Membantu `financial-summarizer` menyiapkan paket data finansial 3-layer terstruktur.

---

## ⚙️ Langkah 0: Deteksi Sektor Emiten

Sebelum melakukan ekstraksi apapun, **wajib** menentukan sektor emiten:

1. Ambil kode saham (ticker) emiten dari nama berkas atau instruksi pengguna.
2. Buka `sector_map.json` (di `.agents/sector_map.json`).
3. Lookup ticker di bagian `tickers`: `sector_map["tickers"][TICKER]` → nama sektor.
4. Buka skema ekstraksi sektor tersebut: `sector_map["sector_schemas"][nama_sektor]`.
5. Gunakan `layer_2_kpis` dan `layer_3_qualitative` dari skema itu sebagai panduan ekstraksi.

> **Jika ticker tidak ditemukan** di `sector_map.json`, gunakan skema `"General"` dan tandai hasilnya dengan `[SEKTOR: TIDAK DIKETAHUI — gunakan General schema]`.

---

## 📂 Langkah 1: Pemindaian Berkas (Scanning & Parsing)

1. Buka berkas target di `reports/raw/[EMITEN]/`.
2. Jika berkas berupa **XLSX**:
   - Gunakan `openpyxl` untuk membaca lembar kerja (*sheets*) Neraca, Laba Rugi, dan Arus Kas.
   - Ambil angka-angka penting untuk periode berjalan (*current period*) dan periode komparatif (*previous period*).
3. Jika berkas berupa **PDF**:
   - Gunakan `pypdf` / `PyMuPDF` untuk memindai tabel Laporan Keuangan Utama.
   - Bersihkan teks dari spasi berlebih dan karakter header/footer.

---

## 📊 Langkah 2: Ekstraksi Layer 1 — Core Financials (Semua Sektor)

Hasil ekstraksi wajib disajikan dalam format tabel terstruktur:

```markdown
### 📋 LAYER 1: Data Keuangan Inti (Core Financials)
**Emiten:** [TICKER] | **Sektor:** [NAMA SEKTOR] | **Periode:** [KUARTAL/TAHUN]
**Jenis Laporan:** [LKT-A / LKT-Q / LKS / LKB-Bulanan]

#### A. Neraca (Balance Sheet)
| Pos Keuangan                   | Periode Berjalan (Rp) | Periode Sebelumnya (Rp) |
|---|---|---|
| Kas & Setara Kas               | ...                   | ...                     |
| Aset Lancar                    | ...                   | ...                     |
| Aset Tidak Lancar              | ...                   | ...                     |
| **Total Aset**                 | ...                   | ...                     |
| Liabilitas Jangka Pendek       | ...                   | ...                     |
| Liabilitas Jangka Panjang      | ...                   | ...                     |
| **Total Liabilitas**           | ...                   | ...                     |
| **Total Ekuitas**              | ...                   | ...                     |
| Utang Berbunga (Interest-Bearing Debt) | ...          | ...                     |

#### B. Laporan Laba Rugi (Income Statement)
| Pos Keuangan                   | Kuartal Berjalan | QoQ (Kuartal Lalu) | YoY (Periode Sama Thn Lalu) |
|---|---|---|---|
| Pendapatan / Revenue           | ...              | ...                | ...                         |
| Beban Pokok Pendapatan / COGS  | ...              | ...                | ...                         |
| **Laba Kotor**                 | ...              | ...                | ...                         |
| Beban Usaha (Opex)             | ...              | ...                | ...                         |
| **Laba Usaha / EBIT**          | ...              | ...                | ...                         |
| Beban Bunga / Keuangan         | ...              | ...                | ...                         |
| **Laba Sebelum Pajak / EBT**   | ...              | ...                | ...                         |
| **Laba Bersih**                | ...              | ...                | ...                         |
| Laba per Saham / EPS (Rp)      | ...              | ...                | ...                         |
| Depresiasi & Amortisasi        | ...              | ...                | ...                         |

#### C. Laporan Arus Kas (Cash Flow Statement)
| Aktivitas                      | Periode Berjalan (Rp) | Periode Sebelumnya (Rp) |
|---|---|---|
| Arus Kas Operasi               | ...                   | ...                     |
| Arus Kas Investasi             | ...                   | ...                     |
| Arus Kas Pendanaan             | ...                   | ...                     |
| **Net Change in Cash**         | ...                   | ...                     |
| Free Cash Flow (Operasi - Capex) | ...                 | ...                     |
```

---

## 🏭 Langkah 3: Ekstraksi Layer 2 — KPI Operasional Sektoral

Gunakan daftar `layer_2_kpis` dari `sector_map.json` untuk sektor yang terdeteksi. Format output:

```markdown
### 🏭 LAYER 2: KPI Operasional Sektoral
**Sektor:** [NAMA SEKTOR] [ICON]

| KPI                            | Periode Berjalan | Periode Lalu (QoQ/YoY) | Satuan  |
|---|---|---|---|
| [KPI dari sector_map.json]     | ...              | ...                    | [unit]  |
| ...                            | ...              | ...                    | ...     |

> ⚠️ **Zero Hallucination**: Jika data KPI tidak tersedia dalam dokumen, tulis `-` — JANGAN menebak atau menginterpolasi.
```

**Catatan penting per jenis laporan:**
- **LKB-Bulanan (Bank/Multifinance)**: Prioritaskan NPL, CAR, LDR/LFR, CASA karena biasanya tersedia di form standar OJK.
- **Annual Report**: Biasanya memuat KPI operasional lebih lengkap di bagian MD&A atau segmen bisnis.
- **Laporan Triwulanan (LKT-Q)**: Cek apakah ada tabel kinerja operasional di catatan atas laporan keuangan.

---

## 📝 Langkah 4: Ekstraksi Layer 3 — Qualitative Intelligence

Baca dan rangkum poin-poin berikut dari dokumen, dipandu oleh `layer_3_qualitative` di `sector_map.json`. Format output:

```markdown
### 📝 LAYER 3: Qualitative Intelligence

#### 🔍 Opini Auditor
- **Jenis Opini:** [Wajar Tanpa Pengecualian / WDP / Disclaimer / Adverse]
- **KAP:** [Nama Kantor Akuntan Publik]
- **Catatan Penting Auditor:** [Ringkasan paragraf penekanan / emphasis of matter, jika ada]

#### 📣 Narasi Manajemen (MD&A — Management Discussion & Analysis)
- **Penjelasan Kinerja:** [Alasan utama kenaikan/penurunan revenue/laba]
- **Guidance Manajemen:** [Target angka yang disebutkan manajemen: revenue, margin, KPI sektor]
- **Strategi & Outlook:** [Rencana bisnis, ekspansi, efisiensi yang disebutkan]

#### ⚠️ Catatan Kaki Material (Footnote Red Flags)
- **Kewajiban Kontinjensi:** [Perkara hukum, gugatan, klaim asuransi yang belum selesai]
- **Covenant Utang:** [Persyaratan finansial dari pinjaman yang harus dipenuhi]
- **Transaksi Pihak Berelasi (RPT):** [Nilai & jenis transaksi dengan afiliasi yang material]
- **Perubahan Kebijakan Akuntansi:** [Perubahan standar PSAK yang berdampak pada laporan]

#### 🏗️ Pipeline & Aksi Korporasi
- **Proyek/Ekspansi dalam Progress:** [Deskripsi singkat & milestone]
- **Aksi Korporasi Diumumkan:** [Rights issue, merger, akuisisi, dividen, buyback — jika ada]

#### 🌐 Konteks Eksternal Material
- **Eksposur Kurs:** [Denominasi USD/mata uang asing yang material]
- **Risiko Regulasi:** [Perubahan regulasi yang disebut manajemen sebagai risiko]
- **Faktor Makro:** [Harga komoditas, suku bunga, kebijakan pemerintah yang relevan]
```

---

## ✅ Langkah 5: Validasi & Serah Terima

1. **Validasi Neraca Wajib:**
   - ✅ Total Aset = Total Liabilitas + Total Ekuitas (toleransi < 0,1%)
   - ✅ Pastikan 3 laporan inti tersedia (Neraca, L/R, Arus Kas)
   - ✅ Laba Bersih di L/R konsisten dengan Arus Kas (metode tidak langsung)

2. **Jika data tidak valid:**
   - Tandai dengan `[DATA TIDAK VALID — PERLU VERIFIKASI: halaman X]`
   - Minta pengulangan ekstraksi pada halaman terkait.

3. **Serahkan paket 3-layer** ke `financial-summarizer` dengan header ringkasan:

```markdown
---
### ✅ RINGKASAN SERAH TERIMA DATA
- **Emiten:** [TICKER] | **Sektor:** [NAMA SEKTOR]
- **Jenis Laporan:** [LKT-A / LKT-Q / LKS / LKB]
- **Periode:** [KUARTAL/TAHUN]
- **Layer 1 (Core Financials):** ✅ Lengkap / ⚠️ Tidak Lengkap
- **Layer 2 (Sector KPIs):** ✅ [N] dari [Total] KPI berhasil diekstrak / ⚠️ [N] KPI tidak tersedia
- **Layer 3 (Qualitative):** ✅ Lengkap / ⚠️ Parsial (MD&A tidak tersedia / Annual Report diperlukan)
- **Validasi Neraca:** ✅ SEIMBANG / ❌ TIDAK SEIMBANG
---
```
