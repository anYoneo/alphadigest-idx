---
name: daily-monitoring
description: Mengotomatiskan penarikan data harian dari IDX untuk daftar emiten pantauan, mengekstrak informasi awal, dan memicu penyusunan ringkasan harian (Daily Digest).
---

# Skill: Daily Monitoring

## Pemicu (Trigger)
Gunakan skill ini ketika:
- Sistem penjadwalan harian (cron) memicu jalannya sinkronisasi sore hari.
- Pengguna meminta: "jalankan pemantauan harian" / "buat rangkuman kejadian hari ini".

---

## Aturan Utama & Standar Kualitas (Standard Rules)
Seluruh proses pemantauan harian dan pembuatan berkas laporan wajib mematuhi aturan baku di [`daily-reporting-rules.md`](file:///g:/My%20Drive/Model2/.agents/rules/daily-reporting-rules.md):
1. **Generalist JSON Schema**: Seluruh ekstraksi menggunakan bidang dinamis (`emiten`, `kategori_dokumen`, `ringkasan_eksekutif`, `fakta_material: [{"parameter": "...", "nilai_parameter": "..."}]`).
2. **Penggabungan Lampiran (Attachment Collapsing)**: Seluruh lampiran (`lamp1`, `lamp2`, dst.) digabung di bawah 1 entitas dokumen utama.
3. **Format Markdown Card Sub-Bullet**: `fakta_material` disajikan dalam bentuk poin sub-bullet berhirarki (`- **Parameter**: Nilai`).
4. **Penapisan Teks Sampah & URL**: Nomor telepon, fax, email, dan prefix `http:` dibersihkan total agar tidak merusak tampilan Markdown/Obsidian.
5. **Penanganan Kategori Khusus**:
   - Filter dokumen registrasi pemegang saham bulanan (`LBRE`).
   - Penanganan dividen 6 parameter (Nominal, Total, Cum, Ex, Recording, Payment Date).
   - Penyeragaman Tanggapan Penjelasan Bursa (konfirmasi negatif vs Penawaran Tender Wajib MTO).

---

## Langkah-Langkah Eksekusi

### Langkah 1: Sinkronisasi Laporan IDX Sore Hari
Jalankan skrip koordinasi pemantauan harian `daily_run.py` menggunakan Python:
```powershell
& "C:\Users\bowol\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "g:\My Drive\Model2\.agents\skills\daily-monitoring\scripts\daily_run.py"
```

### Langkah 2: Pendelegasian & Penyusunan Laporan Harian (Daily Digest)
1. **Pemicu PM (Orkestrator):** Setelah skrip berjalan, Orkestrator (Financial Analyst Agent) bertindak sebagai PM. Ia memverifikasi terbentuknya berkas manifest di `g:\My Drive\Model2\reports\raw\today_manifest.json`.
2. **Pendelegasian Ke Spesialis Dokumen (Financial Summarizer):** Orkestrator menugaskan `financial-summarizer-agent` untuk membaca manifest harian dan menyusun draf Daily Digest harian sesuai template.
3. **Analisis Isi & Pembuatan Draf (Financial Summarizer):**
   - `financial-summarizer-agent` mengekstrak data dari `today_manifest.json`.
   - Jika terdapat kejadian bernilai tinggi (misal: RUPS, dividen interim, atau laporan keuangan baru), `financial-summarizer-agent` meminta ulasan kilat ke spesialis terkait (`risk-compliance-agent` untuk risiko, `valuation-forecasting-agent` untuk valuasi).
   - `financial-summarizer-agent` menulis berkas laporan akhir yang rapi, bersih, dan bebas dari duplikasi ke folder summaries: `g:\My Drive\Model2\reports\summaries\Daily_Digest_YYYYMMDD.md`.
4. **Persetujuan Akhir & Sign-Off (Orkestrator):** Orkestrator meninjau draf laporan yang telah dibuat oleh `financial-summarizer-agent` tersebut, menyetujui, dan menyajikannya secara formal kepada pengguna sebagai Project Manager (PM).
