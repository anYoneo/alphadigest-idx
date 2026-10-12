# Rules: General Agent Guidelines

Dokumen ini berisi pedoman umum pengoperasian, standar komunikasi, serta aturan penulisan kode untuk semua agen di workspace `Model2`.

---

## 1. Standar Komunikasi & Bahasa
*   **Bahasa Utama**: Gunakan bahasa Indonesia yang profesional, formal, terstruktur, dan mudah dipahami oleh analis keuangan.
*   **Format Tabel**: Sajikan data keuangan (seperti Neraca, Laba Rugi, dan Rasio) dalam bentuk tabel Markdown yang rapi dengan format ribuan yang jelas (contoh: `12,345,678` atau `Rp 12.345.678`).
*   **Tautan File**: Selalu gunakan tautan markdown lokal yang dapat diklik untuk merujuk ke file laporan keuangan mentah ([reports/raw/](file:///g:/My%20Drive/Model2/reports/raw/)) dan laporan ringkasan ([reports/summaries/](file:///g:/My%20Drive/Model2/reports/summaries/)).

---

## 2. Kepatuhan & Akurasi Data (Zero Hallucination)
*   **Akurasi Angka**: Angka yang disajikan dalam laporan ringkasan harus 100% sama dengan angka yang tercantum di dalam berkas PDF laporan keuangan resmi dari IDX.
*   **Penanganan Data Kosong**: Jika suatu data keuangan (misal: nilai persediaan atau arus kas pendanaan) tidak ditemukan di laporan utama, **DILARANG KERAS** membuat asumsi atau tebakan angka. Tuliskan tanda `-` atau `"Data tidak tersedia"` secara eksplisit.
*   **Transparansi Sumber**: Selalu cantumkan nomor halaman laporan keuangan asli atau nama lampiran dari mana data tersebut diekstrak.

---

## 3. Pedoman Pengembangan Kode (Coding Standards)
Jika ada agen yang perlu membuat atau memodifikasi skrip pendukung (seperti Python atau Node.js):
*   **Kompatibilitas Runtime**: Pastikan skrip Python kompatibel dengan interpreter Python internal (`python 3.12`).
*   **Penanganan Error**: Semua fungsi pengambilan data eksternal wajib dilengkapi dengan penanganan error (`try-except`) dan logger yang informatif.
*   **Keamanan Jaringan**: Setiap pemanggilan API eksternal harus menyertakan headers browser standar (User-Agent, Referer) untuk menghindari pemblokiran. Pastikan menggunakan pustaka penembus bot yang andal (seperti `curl_cffi` di Python) jika berhadapan dengan WAF/Cloudflare.
