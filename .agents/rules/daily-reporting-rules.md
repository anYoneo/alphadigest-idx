# Rules: Standar Pelaporan Daily Digest & Pemantauan BEI Harian

> [!IMPORTANT]
> **Source of Truth**: Seluruh output dokumen intelijen ditulis ke **`Finplan_analyst/knowledge-base/`** sebagai PRIMARY STORAGE. Folder `reports/summaries/` hanya berfungsi sebagai **export/backup** otomatis — jangan jadikan sebagai referensi utama jika ada perbedaan konten.

Dokumen aturan ini dibuat berdasarkan preferensi dan koreksi pengguna untuk memastikan seluruh proses pemantauan harian, ekstraksi data, dan penyusunan Daily Digest berjalan secara otomatis, konsisten, dan akurat tanpa memerlukan koreksi berulang.

---

## 1. Aturan Ekstraksi Dokumen & Skema JSON Generalist
Seluruh dokumen yang diekstrak oleh skrip parser maupun agen LLM wajib mengadopsi **Generalist JSON Schema**:
```json
{
  "emiten": "KODE_EMITEN",
  "kategori_dokumen": "Kategori Dinamis (ex: Laporan Keuangan H1, Dividen, Tanggapan Penjelasan Bursa, Konversi Waran)",
  "tanggal_kejadian_atau_pelaporan": "YYYY-MM-DD",
  "is_extraction_success": true,
  "ringkasan_eksekutif": "Ringkasan inti lampiran dokumen (maksimal 3 kalimat bersih)",
  "fakta_material": [
    {
      "parameter": "Nama Parameter (ex: Nominal Dividen, Cum Date, Jumlah Saham Dikonversi)",
      "nilai_parameter": "Nilai Parameter (ex: Rp 60 per saham, 11 Agustus 2026, 2.381 lembar)"
    }
  ]
}
```

---

## 2. Aturan Penggabungan Lampiran Dokumen (Attachment Collapsing)
* **Dilarang Duplikasi**: Berkas lampiran (`lamp1`, `lamp2`, `lamp3`) **dilarang keras** dijadikan baris tabel atau bullet point terpisah yang berulang.
* **Format Penggabungan**: Semua berkas lampiran wajib digabung di bawah 1 entitas dokumen utama emiten.
* **Tampilan Markdown**:
  `- **[Kategori]** [Judul Utama](link_utama) *(Attachment: [Lamp 1](link_lamp1) · [Lamp 2](link_lamp2))*`

---

## 3. Aturan Tampilan & Penulisan Markdown Card Sub-Bullet
* **Format Sub-Bullet**: Sajikan `fakta_material` sebagai poin sub-bullet berhirarki yang jelas dan mudah dibaca:
  ```markdown
  - 📌 *Deskripsi*: Ringkasan eksekutif dokumen
  - 📊 **Fakta Material**:
    - **Parameter A**: Nilai A
    - **Parameter B**: Nilai B
  ```
* **Dilarang Teks Siku Mentah**: Dilarang keras menggabungkan fakta ke dalam satu kalimat siku mentah `[Param1: Val1 · Param2: Val2]`.

---

## 4. Penapisan Sampah Teks & URL (Noise Stripping)
* **Abaikan Template Header/Footer BEI**: Abaikan teks pengantar template seperti *"Go To English Page"*, *"Dampak kejadian..."*, *"Hormat Kami"*, nama jalan, fax, nomor telepon.
* **Penapisan URL & Kontak**: Hapus total prefix `http:`, `www.`, nomor telepon `(021)`, dan email dari deskripsi agar tidak muncul sebagai link biru liar/rusak di Obsidian maupun parser Markdown.

---

## 5. Aturan Penanganan Kategori Khusus Dokumen BEI
1. **Laporan Bulanan Registrasi Pemegang Efek (LBRE)**:
   * Abaikan/lewati seluruh dokumen registrasi pemegang saham bulanan (`BOLT`, `PSKT`, `EPAC`, `KARW`, dll.) dari laporan harian.
2. **Formulir Resmi Dividen BEI**:
   * Selalu ekstrak 6 parameter lengkap dari formulir dividen: **Nominal Dividen (Rp/saham)**, **Total Nilai Dividen (Rp/Triliun)**, **Cum Date**, **Ex Date**, **Recording Date**, dan **Tanggal Pembayaran**.
3. **Tanggapan Penjelasan Bursa & Volatilitas**:
   * Jika bersifat bantahan/negatif standar (baik berupa PDF teks maupun PDF scan lampiran), seragamkan ke teks konfirmasi standar:
     > *"Perseroan mengonfirmasi TIDAK MENGETAHUI adanya informasi/fakta material lain atau rencana aksi korporasi yang mempengaruhi volatilitas saham."*
   * Jika merujuk ke **Penawaran Tender Wajib (MTO)** (seperti `MAPI`), ekstrak secara spesifik nama **Pengendali Baru**, topik MTO, dan informasi kepemilikan saham public / Free Float.

---

## 6. Aturan Penanganan Rights Issue / Penambahan Modal HMETD (PMHMETD)
Apabila dokumen terdeteksi sebagai **Rights Issue / PMHMETD** (seperti kasus `BUVA`), parser dan LLM wajib mengekstraksi dan menyajikan **5 Komponen Utama** dengan pola emoji dan sub-bullet persis seperti berikut:

```markdown
- **[Aksi Korporasi]** [Rights Issue II / PMHMETD II](link_pdf)
  - 📌 **RIGHTS ISSUE KEDUA, TARGET RAUP RP 1,54 TRILIUN UNTUK GARAP ULUWATU DAN BINTAN**
  - 📊 **Struktur & Rasio HMETD**:
    - **Jumlah Saham Baru**: 6,15 Miliar saham baru (20% dilusi)
    - **Rasio HMETD**: Setiap 4 saham lama berhak atas 1 HMETD
    - **Harga Pelaksanaan**: Rp 250 per lembar
    - **Target Total Dana**: Rp 1,54 Triliun
  - 👥 **Pengendali & Pembeli Siaga (Standby Buyers)**:
    - **Pengendali (PT Nusantara Utama Investama - 61,07%)**: Exercise sebagian hak (maks 2,4 miliar HMETD).
    - 🟡 **PT Henan Putihrai Sekuritas**: Komitmen Rp 100 Miliar
    - 🟡 **PT Tata Tirta Datun**: Komitmen Rp 350 Miliar
    - 🟡 **Bapak Hapsoro**: Komitmen Rp 100 Miliar
    - 🟡 **Bapak Ferry Sudjono**: Komitmen Rp 388,57 Miliar
  - 🎯 **Alokasi & Penggunaan Dana Hasil Rights Issue**:
    - 1️⃣ **Rp 420,49 Miliar (27,33%)**: Penyertaan modal di PT Bukit Bali Permai (Akuisisi PT Royal Uluwatu Residence & pengembangan lahan 3,9 Ha Uluwatu).
    - 2️⃣ **Rp 417,80 Miliar (27,16%)**: Pelunasan utang pembiayaan.
    - 3️⃣ **Rp 546,19 Miliar (35,50%)**: Infrastruktur Uluwatu Estate (jalan, art gallery, park, fasilitas olahraga) & Renovasi total Hotel Alila Ubud.
    - 4️⃣ **Rp 150,00 Miliar (9,75%)**: Penyertaan modal di PT Bukit Lagoi Villa untuk kawasan wisata Lagoi, Bintan.
  - 📅 **Jadwal Pelaksanaan HMETD**:
    - 🟡 **Efektif Pernyataan Pendaftaran**: 16 September 2026
    - 🟡 **Cum HMETD (Reguler & Negosiasi)**: 24 September 2026
    - 🟡 **Distribusi HMETD**: 29 September 2026
    - 🟡 **Pencatatan HMETD di BEI**: 30 September 2026
    - 🟡 **Periode Perdagangan & Pelaksanaan HMETD**: 1 – 14 Oktober 2026
    - 🟡 **Penjatahan Saham Tambahan**: 20 Oktober 2026
```

---

### 7. Aturan Penyaringan & Laporan Khusus Public Expose / RUPS
1. **Penyaringan Konversi Waran & Unit Penyertaan**:
   - Berkas laporan konversi waran terstruktur (*Structured Warrant conversion* seperti ZP, HD), peredaran unit penyertaan, dan NAB **TIDAK PERLU DI-DOWNLOAD / DIPROSES**.
2. **Penanganan Pemanggilan RUPS (Pengumuman Rapat / Notice of Meeting)**:
   - Pengumuman **Pemanggilan RUPS** disajikan secara ringkas di Daily Digest dan dibuatkan **Berkas Intelijen Khusus Pemanggilan RUPS** di folder khusus `knowledge-base/rups-notices/[EMITEN]_Pemanggilan_RUPS_[YYYYMMDD].md` yang memuat:
     - 📌 **Detail RUPS**: Hari/Tanggal, Waktu, Lokasi Pelaksanaan, dan Batas Hak Suara (*Eligible Date / Recording Date*)
     - 📝 **Matriks Agenda**: Rincian nomor, judul agenda, dan penjelasan sub-acara rapat
     - 🗓️ **Mermaid Timeline**: Diagram alur Pemanggilan ➔ Eligible Date ➔ Pelaksanaan RUPS
     - 💡 **Panduan E-Voting**: Tata cara penggunaan eASY.KSEI dan pendaftaran DPS


3. **Penanganan Hasil Public Expose (Tanya Jawab Q&A)**:
   - Berkas pengumuman **Hasil Public Expose** wajib dibuatkan **1 Berkas Laporan Khusus Terpisah** di `knowledge-base/public-exposes/[EMITEN]_Public_Expose_[YYYYMMDD].md`.
   - Wajib mengekstrak seluruh pasangan **Pertanyaan (Q)** dan **Jawaban (A)** dari manajemen perseroan dengan format:
     ```markdown
     ### ❓ Pertanyaan #1
     > **Pertanyaan**: [Isi Pertanyaan Investor / Media]

     💡 **Jawaban Manajemen**:
     [Isi Jawaban Resmi Manajemen Perseroan]
     ```
4. **Penanganan Laporan Hasil & Risalah RUPS / RUPSLB**:
   - Berkas pengumuman **Hasil & Ringkasan Risalah RUPSLB / RUPS** wajib dibuatkan **1 Berkas Laporan Intelijen Khusus Terpisah** di `knowledge-base/corporate-actions/[EMITEN]_RUPS_[YYYYMMDD].md` dengan format baku institusional:
     ```markdown
     # ⚡ Laporan Intelijen RUPSLB: [[EMITEN]] (Nama Perusahaan)

     ⬅️ [[knowledge-base/daily-digests/Daily_Digest_YYYYMMDD|Kembali ke Daily Digest]] | 📅 **YYYY-MM-DD** | 🎛️ [[Dashboard|Ke Dashboard Utama]]

     > [!IMPORTANT]
     > Dokumen ini memuat hasil keputusan resmi **Rapat Umum Pemegang Saham Luar Biasa (RUPSLB)** PT [Nama Emiten] Tbk yang diselenggarakan pada [Tanggal].

     ---

     ## 📌 1. Ringkasan Eksekutif & Hasil RUPSLB
     - **Kode & Nama Emiten**: `[[EMITEN]]` (Nama Perusahaan)
     - **Jenis Rapat**: Rapat Umum Pemegang Saham Luar Biasa (RUPSLB) / RUPS Tahunan
     - **Hari, Tanggal Pelaksanaan**: [Hari, Tanggal] ([Waktu WIB])
     - **Lokasi Rapat**: [Alamat Lokasi Rapat]
     - **Tingkat Kuorum Kehadiran**: **[Jumlah] saham ([%] dari seluruh hak suara sah)**

     ---

     ## 📊 2. Matriks Agenda & Hasil Pemungutan Suara

     | Agenda / Mata Acara | Kuorum Kehadiran | Setuju (%) | Tidak Setuju | Abstain | Status Keputusan |
     | :--- | :---: | :---: | :---: | :---: | :---: |
     | **Agenda 1**: [Deskripsi Agenda] | `[%]` | **100%** ([Jumlah] suara) | `0%` | `0%` | 🟢 **DISETUJUI SECARA BULAT** |

     ### 📝 Rincian Keputusan Resmi Agenda 1
     > **Keputusan**: [Penjelasan Rinci Keputusan Resmi]

     ---

     ## 👔 3. Kehadiran Dewan Komisaris & Direksi
     - **Dewan Komisaris**: [Daftar Nama]
     - **Direksi**: [Daftar Nama]

     ---

     ## 💡 4. Panduan Strategi Investor & Implikasi Operasional
     - 🟢 **Implikasi Operasional**: [Dampak terhadap struktur bisnis/tata kelola]
     - 📈 **Stabilitas Manajemen**: [Evaluasi kepemimpinan & persetujuan pemegang saham]
     ```

---

### 8. Standar Analisis Transformasi Bisnis & Pivoting Strategis Emiten
1. **Identifikasi Pivoting & Model Bisnis Baru**:
   - Setiap penyusunan Laporan Analisis Keuangan Mendalam (*Financial Summaries*) wajib menyajikan seksi **`## 🚀 Transformasi Bisnis & Model Usaha Strategis`**.
2. **Konteks Strategis di Balik Fluktuasi Laba/Rugi**:
   - Agen **TIDAK BOLEH** hanya melihat angka laba/rugi secara dangkal. Wajib menganalisis alasan strategis di balik fluktuasi laba/rugi (contoh: *inventory clearance* / diskon cuci gudang untuk pelepasan stok lama demi reallokasi modal ke lini bisnis baru seperti Kendaraan Listrik / EV / E-Bike).
3. **Poin-Poin Utama Analisis Transformasi**:
   - Perubahan segmen produk utama (misal: dari sepeda konvensional ke E-Bike / E-Motorcycle).
   - Pengalokasian ulang modal kerja (*working capital reallocation*).
   - Prospek pertumbuhan jangka panjang pasca-transformasi.

---

### 9. Penanganan Ekstraksi Public Expose & Pembersihan Sampah Teks BEI
1. **Ekstraksi Q&A Public Expose**: Seluruh berkas hasil Public Expose yang memuat sesi tanya jawab WAJIB diproses menggunakan block parser PyMuPDF (`fitz`) untuk memisahkan nama Penanya, Pertanyaan, dan Jawaban secara rapi (mendukung format `A. B. C. D.`, `Penanya:`, `Pertanyaan:`, `Jawaban:`).
2. **Pembersihan Teks Administrasi**: Dilarang keras memasukkan teks boiler-plate surat BEI (*Nomor Surat, Go To English Page, Sender Name, Dokumen ini merupakan dokumen resmi*) ke dalam catatan ringkasan Markdown.
3. **Prioritas Kategori**: Selalu evaluasi Konversi Waran dan Public Expose sebelum Dividen/Buyback untuk mencegah false trigger dari header/form bursa.

