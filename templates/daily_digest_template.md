# Ikhtisar Pasar Harian (Daily Digest) — {{TANGGAL}}

⬅️ [[Dashboard|🎛️ Dashboard Utama]] | 📅 **{{TANGGAL}}** | 📁 [[knowledge-base/daily-digests/|Semua Digest]]

> [!NOTE]
> **Ringkasan Eksekutif**: {{RINGKASAN_EKSEKUTIF — 2-3 kalimat: highlight utama hari ini, jumlah pengumuman material, tren sektor, dan outlook besok.}}

---

## 📋 Daftar Pengumuman Hari Ini

> Hanya tampilkan pengumuman dengan dampak **MEDIUM** dan **HIGH**. Lewati: LBRE, konversi waran, perubahan kepemilikan rutin.

### 🔴 HIGH IMPACT

<!-- Format sub-bullet wajib: DILARANG format tabel. Gunakan pola berikut: -->

- **[Kategori]** [Judul Utama](link_pdf) *(Lampiran: [Lamp1](link) · [Lamp2](link))*
  - 📌 *Ringkasan*: {{ringkasan_eksekutif_3_kalimat}}
  - 📊 **Fakta Material**:
    - **Parameter A**: Nilai A
    - **Parameter B**: Nilai B
  - 💡 **Implikasi Investor**: {{analisis_singkat_dampak_ke_pemegang_saham}}

### 🟡 MEDIUM IMPACT

- **[Kategori]** [Judul Utama](link_pdf)
  - 📌 *Ringkasan*: {{ringkasan_eksekutif}}
  - 📊 **Fakta Material**:
    - **Parameter**: Nilai

---

## 💰 Format Khusus: Dividen

- **[Dividen]** [Judul Pengumuman Dividen](link_pdf)
  - 📌 *{{EMITEN}} mengumumkan pembagian dividen {{interim/final/spesial}} sebesar Rp X per saham.*
  - 📊 **Fakta Material**:
    - **Nominal Dividen**: Rp {{X}} per saham
    - **Total Nilai Dividen**: Rp {{Y}} Triliun
    - **Cum Date**: {{YYYY-MM-DD}} (Reguler & Negosiasi)
    - **Ex Date**: {{YYYY-MM-DD}}
    - **Recording Date**: {{YYYY-MM-DD}}
    - **Tanggal Pembayaran**: {{YYYY-MM-DD}}
  - 💡 **Implikasi Investor**: Dividend yield estimasi ~{{Z}}% pada harga {{Rp_harga}} per saham.

---

## 📣 Format Khusus: Rights Issue / PMHMETD

- **[Aksi Korporasi]** [Rights Issue / PMHMETD](link_pdf)
  - 📌 **{{HEADLINE_SINGKAT_KAPITAL}}**
  - 📊 **Struktur & Rasio HMETD**:
    - **Jumlah Saham Baru**: {{X}} saham baru ({{%}} dilusi)
    - **Rasio HMETD**: Setiap {{A}} saham lama berhak atas {{B}} HMETD
    - **Harga Pelaksanaan**: Rp {{X}} per lembar
    - **Target Total Dana**: Rp {{Y}} Triliun
  - 👥 **Pengendali & Pembeli Siaga**:
    - **Pengendali ({{Nama}} — {{%}})**: Exercise {{maks/penuh}} hak
    - 🟡 **{{Nama Pembeli Siaga}}**: Komitmen Rp {{X}} Miliar
  - 🎯 **Alokasi Dana**:
    - 1️⃣ **Rp {{X}} ({{%}})**: {{Peruntukan 1}}
    - 2️⃣ **Rp {{X}} ({{%}})**: {{Peruntukan 2}}
  - 📅 **Jadwal HMETD**:
    - 🟡 **Cum HMETD**: {{YYYY-MM-DD}}
    - 🟡 **Periode Pelaksanaan**: {{YYYY-MM-DD}} – {{YYYY-MM-DD}}
  - 💡 **Analisis Investor**: Laporan khusus → [[knowledge-base/corporate-actions/{{EMITEN}}_PMHMETD_{{TANGGAL}}]]

---

## 📊 Format Khusus: Laporan Keuangan

- **[Laporan Keuangan]** [Laporan Keuangan {{Q}} {{YYYY}}](link_pdf)
  - 📌 *{{EMITEN}} merilis laporan keuangan {{Kuartal/Semester/Tahunan}} {{YYYY}}.*
  - 📊 **Fakta Material**:
    - **Pendapatan**: Rp {{X}} Triliun (YoY: {{+/-}}{{%}})
    - **Laba Bersih**: Rp {{X}} Triliun (YoY: {{+/-}}{{%}})
    - **Net Profit Margin**: {{%}} (vs {{%}} periode lalu)
    - **Total Aset**: Rp {{X}} Triliun
  - 💡 **Tindak Lanjut**: ➡️ Minta `financial-summarizer-agent` lakukan analisis mendalam → [[knowledge-base/financial-summaries/{{EMITEN}}_{{PERIODE}}_Summary]]

---

## 🚨 Format Khusus: Tanggapan Volatilitas / Penjelasan Bursa

- **[Penjelasan Bursa]** [Tanggapan Volatilitas](link_pdf)
  - 📌 *Perseroan mengonfirmasi TIDAK MENGETAHUI adanya informasi/fakta material lain atau rencana aksi korporasi yang mempengaruhi volatilitas saham.*

---

## 🏛️ Format Khusus: Public Expose

- **[Public Expose]** [Hasil Public Expose {{YYYY}}](link_pdf) *(Lampiran: [Materi](link))*
  - 📌 *{{EMITEN}} menyelenggarakan Public Expose pada {{Tanggal}}.*
  - 📊 **Fakta Material**:
    - **Jumlah Pertanyaan Q&A**: {{N}} pertanyaan
    - **Topik Utama**: {{topik1}}, {{topik2}}, {{topik3}}
  - 💡 **Laporan Lengkap**: → [[knowledge-base/public-exposes/{{EMITEN}}_Public_Expose_{{TANGGAL}}]]

---

## 🗓️ Action Items & Langkah Selanjutnya

> [!TIP]
> Tentukan emiten mana yang perlu analisis mendalam lanjutan dan aksi korporasi mana yang perlu dibuatkan berkas intelijen terpisah.

- [ ] 📊 **Analisis Keuangan Mendalam**: {{emiten}} (rilis laporan keuangan Q{{X}} {{YYYY}})
- [ ] 📋 **Berkas Aksi Korporasi**: {{emiten}} ({{jenis aksi}}) → `corporate-action-summarizer`
- [ ] 📄 **Berkas Public Expose**: {{emiten}} → `public_expose_builder.py`
- [ ] ⚠️ **Review Risiko**: {{emiten}} (opini auditor / red flag) → `risk-compliance`

---

*Laporan ini dibuat otomatis oleh Financial Summarizer Agent | Disetujui oleh: Financial Analyst Agent (Orchestrator)*
*Sumber data: `today_manifest.json` per {{TANGGAL}}*
