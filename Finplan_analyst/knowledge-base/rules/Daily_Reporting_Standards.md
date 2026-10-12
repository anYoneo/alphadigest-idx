# Rules: Standar Pelaporan Daily Digest & Pemantauan BEI Harian

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
