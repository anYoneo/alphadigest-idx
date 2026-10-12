---
name: risk-compliance
description: Spesialis deteksi anomali keuangan, red flags catatan kaki laporan keuangan, dan evaluasi kesehatan jangka panjang emiten untuk mendukung laporan investasi Swarm.
---

# Skill: Risk & Compliance Agent

## Pemicu (Trigger)
Gunakan skill ini ketika:
- Diminta untuk menganalisis risiko dan potensi red flags pada laporan keuangan emiten.
- Orchestrator menugaskan analisis catatan kaki (footnote) setelah Financial Summarizer selesai (Tahap 4C pipeline).
- Pengguna meminta: `"analisis risiko [emiten]"`, `"cek catatan kaki laporan [emiten]"`, `"ada red flag di laporan [emiten]?"`.
- Diaktifkan oleh Daily Monitoring ketika mendeteksi pengumuman dengan dampak tinggi (opini auditor disclaimer/adverse, restatement, tuntutan hukum material).

---

## Kepemilikan Variabel Eksklusif (Data Ownership)

Agen ini adalah **satu-satunya** yang berwenang mengisi dan mempublikasikan variabel berikut:

| Variabel | Deskripsi | Nilai yang Mungkin |
|---|---|---|
| `Auditor_Opinion` | Opini auditor eksternal atas laporan keuangan | `Wajar Tanpa Pengecualian (WTP)` / `WTP Dengan Paragraf Penekanan` / `Wajar Dengan Pengecualian (WDP)` / `Tidak Wajar` / `Menolak Memberikan Pendapat` |
| `Footnote_Red_Flags` | Daftar anomali material yang ditemukan di catatan kaki | Array string (kosong `[]` jika tidak ada) |
| `Leverage_Risk_Level` | Tingkat risiko leverage/utang emiten | `🟢 RENDAH` / `🟡 SEDANG` / `🔴 TINGGI` / `🚨 KRITIS` |
| `Permodalan_Status` | Status kesehatan permodalan emiten | `Aman` / `Rentan` / `Kritis` |

**DILARANG KERAS**: Agen lain mengisi, menimpa, atau menduplikasi variabel di atas.

---

## Langkah-Langkah Eksekusi

### Langkah 1: Menerima Konteks dari Orchestrator
1. Terima kode emiten, periode laporan, dan path berkas PDF dari Orchestrator.
2. Konfirmasi lembar data terstruktur dari `financial-data-extractor` sudah tersedia (opsional, jika ada).

### Langkah 2: Analisis Opini Auditor
1. Cari seksi **"Laporan Auditor Independen"** di PDF laporan keuangan.
2. Ekstrak nama Kantor Akuntan Publik (KAP) dan nama auditor penandatangan.
3. Identifikasi jenis opini dan catat setiap paragraf penekanan (*emphasis of matter*) atau paragraf hal lain (*other matter*).
4. Isi variabel `Auditor_Opinion`.

> **⚠️ Red Flag Opini**: Opini WDP, Tidak Wajar, atau Menolak Memberikan Pendapat adalah red flag **KRITIS** yang wajib dilaporkan segera ke Orchestrator.

### Langkah 3: Analisis Catatan Kaki Material
Periksa catatan kaki berikut secara sistematis:

#### A. Transaksi Pihak Terafiliasi (Related Party Transactions)
- Cari catatan mengenai transaksi dengan pihak berelasi (anak perusahaan, induk, direksi/komisaris).
- **Tandai sebagai red flag** jika: nilai transaksi > 5% total aset, tidak ada penjelasan harga wajar (*arm's length*), atau ada transfer aset signifikan ke entitas afiliasi tanpa kompensasi setara.

#### B. Kewajiban Kontinjensi & Tuntutan Hukum (Contingent Liabilities)
- Cari catatan litigasi, gugatan hukum, atau klaim yang belum terselesaikan.
- **Tandai sebagai red flag** jika: nilai potensi kewajiban > 10% total ekuitas, atau ada putusan pengadilan yang sudah berkekuatan hukum tetap namun belum dibayar.

#### C. Utang Jatuh Tempo & Covenant
- Periksa jadwal jatuh tempo utang 12 bulan ke depan vs. posisi kas dan fasilitas kredit yang tersedia.
- Cari klausul pelanggaran covenant (*covenant breach*) atau waiver dari kreditur.
- **Tandai sebagai red flag** jika rasio utang jatuh tempo > 80% dari kas + setara kas yang tersedia.

#### D. Going Concern
- Cari paragraf keraguan atas kelangsungan usaha (*going concern doubt*) di laporan auditor atau catatan manajemen.
- **Going concern** adalah red flag **KRITIS** — wajib dilaporkan segera.

#### E. Restatement & Koreksi Periode Lalu
- Periksa apakah ada penyajian ulang (*restatement*) angka periode sebelumnya.
- **Tandai sebagai red flag** jika restatement menyebabkan perubahan laba bersih > 10%.

### Langkah 4: Evaluasi Risiko Leverage
Hitung dan evaluasi:
- **Interest Coverage Ratio (ICR)**: EBIT ÷ Beban Bunga
  - ICR < 1.5x → 🔴 TINGGI
  - ICR 1.5x – 3x → 🟡 SEDANG
  - ICR > 3x → 🟢 RENDAH
- **Net Debt to EBITDA**: (Total Utang Berbunga − Kas) ÷ EBITDA
  - > 4x → 🚨 KRITIS
  - 2x – 4x → 🔴 TINGGI
  - 1x – 2x → 🟡 SEDANG
  - < 1x → 🟢 RENDAH
- **Debt to Equity Ratio (DER)**: wajib dibandingkan dengan rata-rata sektor

### Langkah 5: Evaluasi Status Permodalan
- Bandingkan total ekuitas dengan modal disetor + saldo laba.
- Untuk emiten perbankan: bandingkan **CAR (Capital Adequacy Ratio)** dengan batas minimum OJK (saat ini 8% – 14% tergantung profil risiko).
- Isi variabel `Permodalan_Status`.

### Langkah 6: Kompilasi Laporan Risk & Compliance

Format output standar yang dikirim ke Orchestrator:

```markdown
## ⚠️ Laporan Risk & Compliance — [EMITEN] [Periode]

### 🔍 Opini Auditor
- **KAP**: [Nama KAP]
- **Auditor Penandatangan**: [Nama]
- **Jenis Opini**: [Jenis Opini]
- **Paragraf Penekanan**: [Ada / Tidak Ada — jika ada, kutip langsung]

### 🚩 Red Flags yang Ditemukan
- [Daftar red flags, atau "Tidak ada red flag material yang ditemukan" jika bersih]

### 📊 Metrik Risiko Leverage
- **Interest Coverage Ratio**: [Nilai]x → [🟢/🟡/🔴 Level]
- **Net Debt / EBITDA**: [Nilai]x → [🟢/🟡/🔴/🚨 Level]
- **DER**: [Nilai]x (Rata-rata sektor: [Nilai]x)
- **`Leverage_Risk_Level`**: [🟢 RENDAH / 🟡 SEDANG / 🔴 TINGGI / 🚨 KRITIS]

### 🏦 Status Permodalan
- **`Permodalan_Status`**: [Aman / Rentan / Kritis]
- **Catatan**: [Penjelasan singkat jika Rentan/Kritis]

### 📋 Ringkasan untuk Orchestrator
[2-3 kalimat ringkasan dampak temuan terhadap investment thesis]
```

---

## Checklist Red Flag Prioritas Tinggi

Segera eskalasi ke Orchestrator jika menemukan salah satu dari:
- [ ] Opini auditor WDP, Tidak Wajar, atau Menolak Memberikan Pendapat
- [ ] Paragraf going concern dalam laporan auditor
- [ ] Restatement laba bersih > 10%
- [ ] Tuntutan hukum aktif senilai > 10% total ekuitas
- [ ] Net Debt/EBITDA > 4x (KRITIS)
- [ ] ICR < 1x (tidak mampu bayar bunga dari operasional)
- [ ] Transaksi pihak terafiliasi tanpa penjelasan harga wajar, nilai > 5% total aset
- [ ] Covenant breach yang belum diselesaikan

---

## Catatan Penting
- Agen ini **TIDAK** menghitung atau menduplikasi rasio yang sudah dimiliki oleh Financial Summarizer (DER, DAR sudah ada di Summarizer — Risk Agent hanya menginterpretasikan implikasi risikonya).
- Semua kutipan dari catatan kaki wajib disertai **nomor halaman** dari PDF sumber (standar zero-hallucination sesuai `general-rules.md`).
- Output disimpan di: `Finplan_analyst/knowledge-base/financial-summaries/[EMITEN]_Risk_[PERIODE].md`
