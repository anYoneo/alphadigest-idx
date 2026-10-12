import os
import sys
import sqlite3
import re
import glob
from datetime import datetime

BASE_DIR = r"G:\My Drive\Model2"
DB_PATH = os.path.join(BASE_DIR, r"reports\market_intelligence.db")
VAULT_DIR = os.path.join(BASE_DIR, r"Finplan_analyst")
TOPICS_DIR = os.path.join(VAULT_DIR, r"knowledge-base\topics")


def extract_report_info(fpath, default_cat="Aksi Korporasi"):
    """Extracts metadata from a standalone corporate action or public expose markdown report."""
    fname = os.path.basename(fpath)
    slug = fname.replace(".md", "")
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None

    em_m = re.search(r"\[\[([A-Z0-9]{4})\]\]", text)
    emiten = em_m.group(1) if em_m else fname.split("_")[0]

    date_m = re.search(r"\*\*(\d{4}-\d{2}-\d{2})\*\*", text)
    if not date_m:
        date_m = re.search(r"(\d{8})", fname)
        if date_m and date_m.group(1).isdigit():
            d_raw = date_m.group(1)
            rep_date = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:]}"
        else:
            rep_date = ""
    else:
        rep_date = date_m.group(1)

    ringkasan_m = re.search(r"Ringkasan Inti Aksi\*\*:\s*([^\n]+)", text)
    if not ringkasan_m:
        ringkasan_m = re.search(r"Ringkasan Eksekutif[^\n]*\n+([^\n]+)", text)
    summary = ringkasan_m.group(1).strip() if ringkasan_m else "Laporan Keterbukaan Informasi"
    summary = re.sub(r"\[\[.*?\]\]", "", summary).replace("`", "")
    if len(summary) > 130:
        summary = summary[:127] + "..."

    # Extract material parameters if available
    params = {}
    for pm in re.finditer(r"\|\s*\*\*([^*]+)\*\*\s*\|\s*`([^`]+)`\s*\|", text):
        k = pm.group(1).strip()
        v = pm.group(2).strip()
        params[k.lower()] = v

    return {
        "emiten": emiten,
        "filename": fname,
        "slug": slug,
        "date": rep_date,
        "summary": summary,
        "params": params,
        "text": text
    }


def update_all_topics():
    """Auto-updates all Topic Knowledge Notes in Obsidian:
    1. Dividen Interim & Tunai
    2. Mandatory Tender Offer (MTO)
    3. Rights Issue (PMHMETD)
    4. RUPS (Pemanggilan & Risalah)
    5. Buyback (Pembelian Kembali Saham)
    6. Private Placement (PMTHMETD)
    7. Stock Split & Reverse Split
    8. Public Expose (Paparan Publik & Risalah Q&A)
    """
    os.makedirs(TOPICS_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_fn = datetime.now().strftime("%Y%m%d")

    ca_base = os.path.join(BASE_DIR, r"reports\summaries\corporate-actions")

    # =========================================================================
    # 1. DIVIDEN INTERIM / TUNAI
    # =========================================================================
    div_dir = os.path.join(ca_base, "dividen")
    div_rows = []
    seen_div = set()
    if os.path.exists(div_dir):
        files = sorted(glob.glob(os.path.join(div_dir, "*.md")), reverse=True)
        for fp in files:
            info = extract_report_info(fp)
            if not info or info["emiten"] in seen_div:
                continue
            seen_div.add(info["emiten"])
            p = info["params"]
            nominal = p.get("nominal dividen", p.get("dividen per saham", p.get("nominal", "Dalam Rincian")))
            cum_date = p.get("cum date", p.get("tanggal cum", p.get("tanggal cum dividen", info["date"] or "Terjadwal")))
            pay_date = p.get("tanggal pembayaran", p.get("payment date", p.get("pembayaran dividen", "Terjadwal")))
            link = f"[[knowledge-base/corporate-actions/dividen/{info['slug']}|⚡ Laporan Khusus {info['emiten']}]]"
            div_rows.append(f"| **[[{info['emiten']}]]** | `{nominal}` | **{cum_date}** | **{pay_date}** | {link} |")

    div_table_str = "\n".join(div_rows[:15]) if div_rows else "| **[[TAPG]]** | `Rp 60 / saham` | **11 Agustus 2026** | **25 Agustus 2026** | [[knowledge-base/corporate-actions/dividen/TAPG_Dividen_Interim_20260804|⚡ Laporan TAPG]] |"

    div_content = f"""# 💸 Panduan & Intelijen Topik: [[Dividen Interim]] & Dividen Tunai

⬅️ [[Dashboard|Ke Dashboard Utama]] | 📅 **Terakhir Diperbarui: {today_str}**

> [!NOTE]
> Topik ini merangkum seluruh pengumuman **Dividen Interim** dan **Dividen Tunai** yang dipindai dari Bursa Efek Indonesia (BEI) oleh AI Swarm.

---

## 📊 Daftar Pengumuman Dividen Terkini

| Emiten | Nominal Dividen | 📅 Cum Date (Batas Beli) | 💸 Tanggal Pembayaran | Dokumen Laporan |
| :--- | :--- | :--- | :--- | :--- |
{div_table_str}

---

## 💡 Panduan Strategi Investor (Dividend Yield Capture)
1. **Cum Date (Batas Hak Dividen)**: Pembeli saham hingga batas waktu penutupan pasar di tanggal Cum Date berhak menerima pembayaran dividen tunai.
2. **Ex Date**: Harga saham biasanya mengalami penyesuaian (*dividend trap*) sebesar nominal dividen. Disarankan melakukan akumulasi sebelum Cum Date.

---

## 🔗 Hubungan Note Terkait (Knowledge Graph)
- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Dividen & Aksi Korporasi]]
- [[knowledge-base/trading-signals/Trading_Signals_{today_fn}|🎯 Sinyal Cuan {today_str}]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]
"""

    # =========================================================================
    # 2. MANDATORY TENDER OFFER (MTO)
    # =========================================================================
    mto_dir = os.path.join(ca_base, "tender-offer")
    mto_rows = []
    seen_mto = set()
    if os.path.exists(mto_dir):
        files = sorted(glob.glob(os.path.join(mto_dir, "*.md")), reverse=True)
        for fp in files:
            info = extract_report_info(fp)
            if not info or info["emiten"] in seen_mto:
                continue
            seen_mto.add(info["emiten"])
            link = f"[[knowledge-base/corporate-actions/tender-offer/{info['slug']}|⚡ Laporan Khusus {info['emiten']}]]"
            mto_rows.append(f"| **[[{info['emiten']}]]** | {info['date']} | {info['summary']} | {link} |")

    mto_table_str = "\n".join(mto_rows[:15]) if mto_rows else "| **[[MAPI]]** | 2026-08-04 | Rencana Penawaran Tender Wajib oleh Pacific Universal Investments Pte. Ltd. | [[knowledge-base/corporate-actions/tender-offer/MAPI_Mandatory_Tender_Offer_20260804|⚡ Laporan MAPI]] |"

    mto_content = f"""# 🎯 Panduan & Intelijen Topik: [[Mandatory Tender Offer]] (MTO)

⬅️ [[Dashboard|Ke Dashboard Utama]] | 📅 **Terakhir Diperbarui: {today_str}**

> [!NOTE]
> Topik ini merangkum seluruh peristiwa **Penawaran Tender Wajib (Mandatory Tender Offer / MTO)** akibat pergantian pengendali perseroan sesuai regulasi POJK No. 9/POJK.04/2018.

---

## 📊 Peristiwa Tender Offer Terkini di Bursa

| Emiten | Tanggal Laporan | Ringkasan Katalis Akuisisi / MTO | Dokumen Laporan |
| :--- | :--- | :--- | :--- |
{mto_table_str}

---

## 💡 Panduan Arbitrase MTO (MTO Arbitrage Strategy)
1. **Harga Penawaran MTO**: Pengendali baru wajib menawar sisa saham publik pada harga tertinggi antara harga akuisisi pengendali vs rata-rata harga pasar 90 hari sebelum akuisisi.
2. **Peluang Arbitrase**: Jika harga pasar di bursa berada di bawah perkiraan harga MTO, terdapat selisih (*spread*) arbitrase berisiko rendah.

---

## 🔗 Hubungan Note Terkait (Knowledge Graph)
- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Aksi Korporasi]]
- [[knowledge-base/trading-signals/Trading_Signals_{today_fn}|🎯 Sinyal Cuan {today_str}]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]
"""

    # =========================================================================
    # 3. RIGHTS ISSUE (PMHMETD)
    # =========================================================================
    ri_dir = os.path.join(ca_base, "rights-issue")
    ri_rows = []
    seen_ri = set()
    if os.path.exists(ri_dir):
        files = sorted(glob.glob(os.path.join(ri_dir, "*.md")), reverse=True)
        for fp in files:
            info = extract_report_info(fp)
            if not info or info["emiten"] in seen_ri:
                continue
            seen_ri.add(info["emiten"])
            link = f"[[knowledge-base/corporate-actions/rights-issue/{info['slug']}|⚡ Laporan Khusus {info['emiten']}]]"
            ri_rows.append(f"| **[[{info['emiten']}]]** | {info['date']} | {info['summary']} | {link} |")

    ri_table_str = "\n".join(ri_rows[:15]) if ri_rows else "| **[[BUVA]]** | 2026-08-04 | Penambahan modal dengan HMETD II target dana Rp 1,54 Triliun | [[knowledge-base/corporate-actions/rights-issue/BUVA_Rights_Issue_20260804|⚡ Laporan BUVA]] |"

    rights_content = f"""# 📜 Panduan & Intelijen Topik: [[Rights Issue]] (PMHMETD)

⬅️ [[Dashboard|Ke Dashboard Utama]] | 📅 **Terakhir Diperbarui: {today_str}**

> [!NOTE]
> Topik ini merangkum seluruh pengumuman **Penambahan Modal dengan Hak Memesan Efek Terlebih Dahulu (PMHMETD / Rights Issue)** di BEI.

---

## 📊 Peristiwa Rights Issue Terkini di Bursa

| Emiten | Tanggal Laporan | Rencana & Target HMETD | Dokumen Laporan |
| :--- | :--- | :--- | :--- |
{ri_table_str}

---

## 💡 Panduan 5 Komponen Analisis Rights Issue
1. **Target Dana & Alokasi Penggunaan**: Pastikan alokasi dana ditujukan untuk ekspansi produktif atau akuisisi aset bernilai tinggi (bukan sekadar restrukturisasi utang).
2. **Komitmen Pengendali & Standby Buyers**: Adanya pembeli siaga ternama menjamin keberhasilan penyerapan dana rights issue.
3. **Efek Dilusi (%)**: Hitung penurunan persentase kepemilikan jika pemegang saham lama tidak mengeksekusi HMETD.

---

## 🔗 Hubungan Note Terkait (Knowledge Graph)
- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Aksi Korporasi]]
- [[knowledge-base/trading-signals/Trading_Signals_{today_fn}|🎯 Sinyal Cuan {today_str}]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]
"""

    # =========================================================================
    # 4. BUYBACK (PEMBELIAN KEMBALI SAHAM)
    # =========================================================================
    bb_dir = os.path.join(ca_base, "buyback")
    bb_rows = []
    seen_bb = set()
    if os.path.exists(bb_dir):
        files = sorted(glob.glob(os.path.join(bb_dir, "*.md")), reverse=True)
        for fp in files:
            info = extract_report_info(fp)
            if not info or info["emiten"] in seen_bb:
                continue
            seen_bb.add(info["emiten"])
            link = f"[[knowledge-base/corporate-actions/buyback/{info['slug']}|⚡ Laporan Khusus {info['emiten']}]]"
            bb_rows.append(f"| **[[{info['emiten']}]]** | {info['date']} | {info['summary']} | {link} |")

    bb_table_str = "\n".join(bb_rows[:15]) if bb_rows else "| **[[BTPS]]** | 2026-09-04 | Rencana Pembelian Kembali Saham (Share Buyback Plan) | [[knowledge-base/corporate-actions/buyback/BTPS_Buyback_20260904|⚡ Laporan BTPS]] |"

    buyback_content = f"""# 🛒 Panduan & Intelijen Topik: [[Buyback]] (Pembelian Kembali Saham)

⬅️ [[Dashboard|Ke Dashboard Utama]] | 📅 **Terakhir Diperbarui: {today_str}**

> [!NOTE]
> Topik ini merangkum seluruh pengumuman **Pembelian Kembali Saham (Share Buyback)** perseroan di BEI sesuai regulasi OJK (POJK No. 30/POJK.04/2017 & POJK No. 29/POJK.04/2023).

---

## 📊 Peristiwa Buyback Terkini di Bursa

| Emiten | Tanggal Pengumuman | Rencana Alokasi & Ringkasan Buyback | Dokumen Laporan |
| :--- | :--- | :--- | :--- |
{bb_table_str}

---

## 💡 Implikasi Finansial Buyback untuk Investor
1. **Sinyal Undervalued**: Manajemen yang mengeksekusi buyback dengan dana kas internal biasanya meyakini harga saham perseroan di pasar sedang *undervalued* (di bawah nilai wajar fundamentalnya).
2. **Peningkatan Earning Per Share (EPS)**: Pengurangan jumlah lembar saham beredar (*shares outstanding*) secara otomatis meningkatkan laba per saham (EPS) dan Return on Equity (ROE).
3. **Saham Treasuri (*Treasury Shares*)**: Saham hasil buyback dapat disimpan sebagai saham treasuri untuk dialihkan di masa depan (dijual kembali saat harga tinggi, atau dibagikan sebagai insentif program MESOP/MSOP).

---

## 🔗 Hubungan Note Terkait (Knowledge Graph)
- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Aksi Korporasi]]
- [[knowledge-base/trading-signals/Trading_Signals_{today_fn}|🎯 Sinyal Cuan {today_str}]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]
"""

    # =========================================================================
    # 5. PRIVATE PLACEMENT (PMTHMETD)
    # =========================================================================
    pp_dir = os.path.join(ca_base, "private-placement")
    pp_rows = []
    seen_pp = set()
    if os.path.exists(pp_dir):
        files = sorted(glob.glob(os.path.join(pp_dir, "*.md")), reverse=True)
        for fp in files:
            info = extract_report_info(fp)
            if not info or info["emiten"] in seen_pp:
                continue
            seen_pp.add(info["emiten"])
            link = f"[[knowledge-base/corporate-actions/private-placement/{info['slug']}|⚡ Laporan Khusus {info['emiten']}]]"
            pp_rows.append(f"| **[[{info['emiten']}]]** | {info['date']} | {info['summary']} | {link} |")

    pp_table_str = "\n".join(pp_rows[:15]) if pp_rows else "| **[[RATU]]** | 2026-09-04 | Rencana PMTHMETD Konversi Utang & Penguatan Struktur Permodalan | [[knowledge-base/corporate-actions/private-placement/RATU_Private_Placement_20260904|⚡ Laporan RATU]] |"

    pp_content = f"""# 🤝 Panduan & Intelijen Topik: [[Private Placement]] (PMTHMETD)

⬅️ [[Dashboard|Ke Dashboard Utama]] | 📅 **Terakhir Diperbarui: {today_str}**

> [!NOTE]
> Topik ini merangkum seluruh aksi korporasi **Penambahan Modal Tanpa Hak Memesan Efek Terlebih Dahulu (PMTHMETD / Private Placement)** sesuai regulasi POJK No. 14/POJK.04/2019.

---

## 📊 Peristiwa Private Placement Terkini di Bursa

| Emiten | Tanggal Laporan | Rencana Alokasi / Konversi Saham Baru | Dokumen Laporan |
| :--- | :--- | :--- | :--- |
{pp_table_str}

---

## 💡 Panduan Investor & Analisis Dampak PMTHMETD
1. **Tujuan Injeksi Modal**: PMTHMETD umumnya dilakukan untuk:
   - Masuknya investor strategis (*strategic partner*) baru.
   - Konversi utang menjadi saham (*Debt-to-Equity Swap*) untuk menyehatkan rasio solvabilitas (DER).
   - Penambahan modal kerja cepat hingga maksimal 10% dari modal disetor tanpa proses HMETD yang panjang.
2. **Risiko Dilusi Pemegang Saham Publik**: Karena pemegang saham publik tidak berhak membeli saham baru dalam aksi ini, persentase kepemilikan publik akan terdilusi secara proporsional.

---

## 🔗 Hubungan Note Terkait (Knowledge Graph)
- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Aksi Korporasi]]
- [[knowledge-base/trading-signals/Trading_Signals_{today_fn}|🎯 Sinyal Cuan {today_str}]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]
"""

    # =========================================================================
    # 6. RUPS (RAPAT UMUM PEMEGANG SAHAM)
    # =========================================================================
    rups_files = sorted(glob.glob(os.path.join(BASE_DIR, r"reports\summaries\rups-notices", "*.md")))
    rups_rows = []
    if rups_files:
        for rfp in rups_files:
            rfname = os.path.basename(rfp)
            with open(rfp, "r", encoding="utf-8") as _rf:
                rtext = _rf.read()
            em_m = re.search(r"\[\[([A-Z0-9]{4})\]\]", rtext)
            r_emiten = em_m.group(1) if em_m else rfname.split("_")[0]

            rups_dt_m = re.search(r"(?:Tanggal RUPS|Tanggal Pelaksanaan|Hari & Tanggal RUPSLB)[^\n|]*?:\s*([^\n|]+)", rtext, re.IGNORECASE)
            r_date = rups_dt_m.group(1).strip("`* ") if rups_dt_m else "Terjadwal"

            dps_m = re.search(r"(?:DPS|Recording Date|Eligible Date)[^\n|]*?:\s*([^\n|]+)", rtext, re.IGNORECASE)
            r_dps = dps_m.group(1).strip("`* ") if dps_m else "Terjadwal"

            ag_m = re.search(r"(?:Agenda Utama|Agenda)[^\n|]*?:\s*([^\n|]+)", rtext, re.IGNORECASE)
            r_ag = ag_m.group(1).strip("`* ") if ag_m else "Persetujuan Aksi Korporasi & Tata Kelola Perseroan"

            r_slug = rfname.replace(".md", "")
            r_link = f"[[knowledge-base/rups-notices/{r_slug}|⚡ Laporan Khusus {r_emiten}]]"
            rups_rows.append(f"| **[[{r_emiten}]]** | RUPSLB / RUPST | **{r_dps}** | **{r_date}** | {r_ag} | {r_link} |")

    rups_table_str = "\n".join(rups_rows) if rups_rows else "| **[[DSSA]]** | RUPSLB | **18 Agustus 2026** | **10 September 2026** | Persetujuan Aksi Korporasi & Tata Kelola | [[knowledge-base/rups-notices/DSSA_Pemanggilan_RUPS_20260812|⚡ Laporan Khusus DSSA]] |"

    rups_content = f"""# 🏛️ Panduan & Intelijen Topik: [[RUPS]] (Rapat Umum Pemegang Saham)

⬅️ [[Dashboard|Ke Dashboard Utama]] | 📅 **Terakhir Diperbarui: {today_str}**

> [!NOTE]
> Topik ini merangkum seluruh Pemanggilan RUPS, Agenda RUPSLB Mendatang, serta Hasil Risalah RUPS Tahunan (RUPST) & RUPS Luar Biasa (RUPSLB) emiten bursa.

---

## 📌 Pemanggilan & Agenda RUPSLB Mendatang

| Emiten | Jenis Rapat | 📝 Batas Hak Suara (DPS) | 🏛️ Tanggal RUPSLB | Agenda Utama | Dokumen Laporan |
| :--- | :--- | :--- | :--- | :--- | :---: |
{rups_table_str}

---

## 📊 Keputusan & Risalah RUPS Terkini

| Emiten | Tanggal RUPS | Keputusan Utama | Status Dividen RUPST | Dokumen Laporan |
| :--- | :--- | :--- | :--- | :--- |
| **[[IKBI]]** | 31 Juli 2026 | Persetujuan Laporan Tahunan FY2025 & Dividen | 💸 **Dividen Rp 44,31 / saham** | [[knowledge-base/corporate-actions/dividen/IKBI_Dividen_Tunai_20260804|⚡ Laporan Khusus IKBI]] |
| **[[ICON]]** | 31 Juli 2026 | Persetujuan Laporan Tahunan FY2025 | ❌ **Tidak Membagikan Dividen** | [[knowledge-base/corporate-actions/rups/ICON_RUPS_20260804|⚡ Laporan Khusus ICON]] |

---

## 🔗 Hubungan Note Terkait (Knowledge Graph)
- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Aksi Korporasi]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]
"""

    # =========================================================================
    # 7. STOCK SPLIT & REVERSE SPLIT
    # =========================================================================
    ss_content = f"""# ✂️ Panduan & Intelijen Topik: [[Stock Split]] & Reverse Stock Split

⬅️ [[Dashboard|Ke Dashboard Utama]] | 📅 **Terakhir Diperbarui: {today_str}**

> [!NOTE]
> Topik ini merangkum seluruh pengumuman **Pemecahan Nilai Nominal Saham (Stock Split)** dan **Penggabungan Nilai Nominal Saham (Reverse Stock Split)** di Bursa Efek Indonesia.

---

## 📊 Panduan Mekanisme Stock Split
- **Tujuan**: Meningkatkan likuiditas perdagangan saham di bursa dengan memperbanyak jumlah lembar saham yang beredar dan membuat harga nominal saham menjadi lebih terjangkau bagi investor ritel.
- **Rasio Umum**: 1:2, 1:5, atau 1:10 (misal harga Rp 10.000 dengan rasio 1:5 menjadi Rp 2.000 per saham).
- **Nilai Fundamental**: Nilai kapitalisasi pasar (*market cap*) perseroan dan persentase kepemilikan investor **tidak berubah sama sekali**.

---

## 💡 Dampak bagi Investor & Pasar
1. **Likuiditas Meningkat**: Jumlah lot yang beredar di pasar menjadi lebih banyak sehingga frekuensi dan volume transaksi harian cenderung meningkat signifikan.
2. **Katalis Jangka Pendek**: Secara psikologis, harga nominal yang lebih rendah sering kali menarik minat beli investor baru (*retail friendly*).

---

## 🔗 Hubungan Note Terkait (Knowledge Graph)
- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Aksi Korporasi]]
- [[knowledge-base/trading-signals/Trading_Signals_{today_fn}|🎯 Sinyal Cuan {today_str}]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]
"""

    # =========================================================================
    # 8. PUBLIC EXPOSE (PAPARAN PUBLIK)
    # =========================================================================
    pubex_base = os.path.join(BASE_DIR, r"reports\summaries\public-exposes")
    pubex_rows = []
    seen_px = set()
    if os.path.exists(pubex_base):
        for root, dirs, files in os.walk(pubex_base):
            for fp in files:
                if fp.endswith(".md"):
                    full_p = os.path.join(root, fp)
                    info = extract_report_info(full_p)
                    if not info or info["emiten"] in seen_px:
                        continue
                    seen_px.add(info["emiten"])
                    rel_f = os.path.relpath(full_p, BASE_DIR).replace("\\", "/")
                    link = f"[[{rel_f[:-3]}|💬 Laporan {info['emiten']}]]"
                    pubex_rows.append(f"| **[[{info['emiten']}]]** | {info['date']} | {info['summary']} | {link} |")

    pubex_table_str = "\n".join(pubex_rows[:15]) if pubex_rows else "*Belum ada berkas Paparan Publik terdaftar.*"

    pubex_content = f"""# 💬 Panduan & Intelijen Topik: [[Public Expose]] (Paparan Publik & Risalah Q&A)

⬅️ [[Dashboard|Ke Dashboard Utama]] | 📅 **Terakhir Diperbarui: {today_str}**

> [!NOTE]
> Topik ini merangkum seluruh hasil **Paparan Publik Tahunan / Insidentil (Public Expose)**, materi presentasi manajemen, dan risalah sesi Tanya Jawab (Q&A) dengan analis serta investor.

---

## 📊 Berkas Public Expose & Q&A Terkini

| Emiten | Tanggal Pelaksanaan | Materi Utama / Agenda Paparan Publik | Dokumen Laporan |
| :--- | :--- | :--- | :--- |
{pubex_table_str}

---

## 💡 Poin Kunci Analisis Risalah Public Expose
1. **Target Kinerja & Capex Manajemen**: Proyeksi pertumbuhan pendapatan, alokasi belanja modal (*capex*), dan *guidance* laba untuk tahun berjalan.
2. **Jawaban Manajemen atas Isu Krusial**: Klarifikasi langsung atas pertanyaan kritis investor mengenai proyek berjalan, struktur utang, atau regulasi pemerintah.

---

## 🔗 Hubungan Note Terkait (Knowledge Graph)
- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Aksi Korporasi]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]
"""

    # =========================================================================
    # Write files to both vault root (for short WikiLinks) & knowledge-base/topics/
    # =========================================================================
    topic_files = [
        ("Dividen Interim.md", "Dividen_Interim.md", div_content),
        ("Mandatory Tender Offer.md", "Mandatory_Tender_Offer.md", mto_content),
        ("Rights Issue.md", "Rights_Issue.md", rights_content),
        ("RUPS.md", "RUPS.md", rups_content),
        ("Buyback.md", "Buyback.md", buyback_content),
        ("Private Placement.md", "Private_Placement.md", pp_content),
        ("Stock Split.md", "Stock_Split.md", ss_content),
        ("Public Expose.md", "Public_Expose.md", pubex_content),
    ]

    for root_fn, sub_fn, content in topic_files:
        root_path = os.path.join(VAULT_DIR, root_fn)
        with open(root_path, "w", encoding="utf-8") as f:
            f.write(content)

        sub_path = os.path.join(TOPICS_DIR, sub_fn)
        with open(sub_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"[+] Updated topic note: {root_fn} and {sub_fn}")

        try:
            from daily_run import push_to_obsidian_server
            push_to_obsidian_server(root_path, root_fn)
            push_to_obsidian_server(sub_path, f"knowledge-base/topics/{sub_fn}")
        except Exception:
            pass


if __name__ == "__main__":
    update_all_topics()
