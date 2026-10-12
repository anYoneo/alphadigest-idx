---
name: idx-scraper
description: Spesialis pengumpulan data laporan keuangan (PDF) dan keterbukaan informasi emiten secara langsung dari Bursa Efek Indonesia (IDX) dengan bypassing Cloudflare.
---

# Skill: IDX Scraper

## Pemicu (Trigger)
Gunakan skill ini ketika diminta untuk:
- "ambil laporan keuangan [kode emiten] dari idx" (contoh: "ambil laporan keuangan BBRI dari idx")
- "download keterbukaan informasi [kode emiten]"
- "cari dokumen keuangan terbaru dari idx untuk [kode emiten]"
- "jalankan crawl idx untuk [kode emiten]"

---

## Langkah-Langkah Eksekusi

### Langkah 1: Jalankan Script Crawler
Untuk mengunduh laporan keuangan emiten berformat PDF, jalankan skrip `crawl_idx.py` menggunakan interpreter Python internal:
```powershell
& "C:\Users\bowol\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "g:\My Drive\Model2\.agents\skills\idx-scraper\scripts\crawl_idx.py" --emiten <KODE_EMITEN> --pagesize 5
```
*Catatan:* Ganti `<KODE_EMITEN>` dengan kode emiten berukuran 4 huruf (misal: `BBRI`, `TLKM`, `ASII`).

### Langkah 2: Verifikasi Unduhan
1. Pastikan skrip berjalan tanpa error dan mencetak ringkasan file PDF yang berhasil diunduh.
2. File PDF laporan keuangan asli akan otomatis disimpan ke dalam direktori: `g:\My Drive\Model2\reports\raw/`.
3. Informasikan kepada pengguna daftar dokumen PDF yang berhasil diunduh beserta tanggal publikasinya.

---

## Parameter Command Line `crawl_idx.py`
Skrip Python mendukung parameter berikut:
- `--emiten <KODE>`: (Wajib) Kode saham emiten sebanyak 4 huruf (kapital).
- `--pagesize <NUM>`: (Opsional) Jumlah halaman/entri pengumuman terbaru yang ingin dipindai (default: `10`).
- `--output-dir <PATH>`: (Opsional) Folder tujuan penyimpanan file PDF (default: `g:\My Drive\Model2\reports\raw`).
- `--keyword <TXT>`: (Opsional) Kata kunci filter judul pengumuman (misal: `Laporan Keuangan`).
