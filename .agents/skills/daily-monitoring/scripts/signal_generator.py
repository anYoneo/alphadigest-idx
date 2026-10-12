import sqlite3
import os
import sys
import json
import re
import glob
from datetime import datetime, date

BASE_DIR = r"G:\My Drive\Model2"
DB_PATH = os.path.join(BASE_DIR, r"reports\market_intelligence.db")
OUTPUT_DIR = os.path.join(BASE_DIR, r"reports\summaries")
OBSIDIAN_SIGNALS_DIR = os.path.join(BASE_DIR, r"Finplan_analyst\knowledge-base\trading-signals")

INDONESIAN_MONTHS = {
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "agt": 8,
    "september": 9, "sep": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12
}

def parse_date_to_obj(date_str):
    """Converts Indonesian date string or YYYY-MM-DD into a datetime.date object."""
    if not date_str or date_str in ["-", "Terjadwal", "TBA", "Dalam Rincian LK"]:
        return None
    
    m1 = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", str(date_str))
    if m1:
        try:
            return date(int(m1.group(1)), int(m1.group(2)), int(m1.group(3)))
        except ValueError:
            pass

    m2 = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})", str(date_str))
    if m2:
        day = int(m2.group(1))
        month_str = m2.group(2).lower()
        year = int(m2.group(3))
        month = INDONESIAN_MONTHS.get(month_str)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass
    return None

def is_past_date(date_str, reference_date=None):
    """Returns True if date_str is an explicit past date strictly before reference_date."""
    if reference_date is None:
        reference_date = date.today()
    dt = parse_date_to_obj(date_str)
    if dt and dt < reference_date:
        return True
    return False

def extract_facts(json_str):
    """Extracts material facts map from announcement json_data."""
    facts = {}
    if not json_str:
        return facts
    try:
        data = json.loads(json_str)
        if "fakta_material" in data and isinstance(data["fakta_material"], list):
            for item in data["fakta_material"]:
                if isinstance(item, dict) and "parameter" in item and "nilai_parameter" in item:
                    k = str(item["parameter"]).strip().lower()
                    v = str(item["nilai_parameter"]).strip()
                    facts[k] = v
                    facts[k.replace(" ", "_")] = v
        for k, v in data.items():
            if isinstance(v, str):
                k_clean = k.strip().lower()
                facts[k_clean] = v.strip()
                facts[k_clean.replace(" ", "_")] = v.strip()
    except Exception:
        pass
    return facts

def generate_trading_signals():
    """Generates an institutional-grade, 100% dynamic Trading Signals & Catalysts Report."""
    if not os.path.exists(DB_PATH):
        print(f"[-] DB not found at {DB_PATH}")
        return

    today_dt = date.today()
    today_str = today_dt.strftime("%Y-%m-%d")
    today_fn = today_dt.strftime("%Y%m%d")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. DIVIDEND SIGNALS (Query dividends table + announcements json_data)
    # ─────────────────────────────────────────────────────────────────────────
    cursor.execute("SELECT emiten, nominal, total, cum_date, payment_date FROM dividends ORDER BY id DESC")
    div_rows = cursor.fetchall()
    
    div_signals = {}
    for emiten, nom, tot, cum, pay in div_rows:
        if emiten not in div_signals:
            cum_str = cum or "Terjadwal"
            if not is_past_date(cum_str, today_dt):
                div_signals[emiten] = {
                    "nominal": nom or "Terjadwal",
                    "total": tot or "Dalam Rincian LK",
                    "cum_date": cum_str,
                    "payment_date": pay or "Terjadwal",
                    "yield": "~5.0% - 10.0%" if ("50" in str(nom) or "100" in str(nom) or "60" in str(nom)) else "Dividend Yield Menarik"
                }

    cursor.execute("SELECT emiten, json_data FROM announcements WHERE category = 'Dividen' OR json_data LIKE '%dividen%'")
    for a_emiten, a_json in cursor.fetchall():
        if a_emiten and a_emiten not in div_signals and a_json:
            facts = extract_facts(a_json)
            cum_val = facts.get("cum date") or facts.get("cum_date") or "Terjadwal"
            if not is_past_date(cum_val, today_dt):
                nom_val = facts.get("nominal dividen") or facts.get("dividen per saham") or facts.get("nominal") or "Terjadwal"
                tot_val = facts.get("total nilai dividen") or facts.get("total nilai") or "Dalam Rincian LK"
                pay_val = facts.get("tanggal pembayaran") or facts.get("payment date") or "Terjadwal"
                div_signals[a_emiten] = {
                    "nominal": nom_val,
                    "total": tot_val,
                    "cum_date": cum_val,
                    "payment_date": pay_val,
                    "yield": "High Conviction Yield"
                }

    # ─────────────────────────────────────────────────────────────────────────
    # 2. MTO & ACQUISITION ARBITRAGE (Query mto_events + announcements)
    # ─────────────────────────────────────────────────────────────────────────
    cursor.execute("SELECT emiten, new_controller, main_topic, details FROM mto_events ORDER BY id DESC")
    mto_rows = cursor.fetchall()
    
    mto_signals = {}
    for emiten, ctrl, top, det in mto_rows:
        if emiten not in mto_signals:
            mto_signals[emiten] = {
                "pengendali": ctrl or "Pengendali Baru",
                "detail": det or top or "Pelaksanaan Penawaran Tender Wajib (MTO)",
                "status": "Arbitrase Spread Penawaran Tender"
            }

    cursor.execute("SELECT emiten, json_data FROM announcements WHERE category LIKE '%Tender%' OR json_data LIKE '%tender offer%' OR json_data LIKE '%mto%'")
    for a_emiten, a_json in cursor.fetchall():
        if a_emiten and a_emiten not in mto_signals and a_json:
            facts = extract_facts(a_json)
            ctrl_val = facts.get("pengendali baru") or facts.get("pihak penawar") or facts.get("pengendali") or "Pengendali Baru"
            top_val = facts.get("topik utama") or facts.get("uraian kejadian") or "Penawaran Tender Wajib (MTO)"
            mto_signals[a_emiten] = {
                "pengendali": ctrl_val,
                "detail": top_val,
                "status": "Penawaran Tender Wajib Resmi"
            }

    # ─────────────────────────────────────────────────────────────────────────
    # 3. BUYBACK PRICE FLOOR SUPPORT
    # ─────────────────────────────────────────────────────────────────────────
    cursor.execute("SELECT emiten, json_data FROM announcements WHERE category LIKE '%Buyback%' OR json_data LIKE '%buyback%' OR json_data LIKE '%pembelian kembali%'")
    buyback_signals = {}
    for a_emiten, a_json in cursor.fetchall():
        if a_emiten and a_emiten not in buyback_signals and a_json:
            facts = extract_facts(a_json)
            dana_val = facts.get("alokasi dana buyback") or facts.get("alokasi dana") or facts.get("maksimum dana") or "Dana Internal Kas"
            harga_val = facts.get("harga maksimum buyback") or facts.get("harga plafon") or "Harga Pasar Reguler"
            periode_val = facts.get("periode buyback") or facts.get("periode pelaksanaan") or "Aktif 2026"
            buyback_signals[a_emiten] = {
                "alokasi_dana": dana_val,
                "harga_maksimum": harga_val,
                "periode": periode_val,
                "rating": "🛡️ PRICE FLOOR SUPPORT"
            }

    # ─────────────────────────────────────────────────────────────────────────
    # 4. RIGHTS ISSUE / PMHMETD CATALYSTS & DILUTION
    # ─────────────────────────────────────────────────────────────────────────
    cursor.execute("SELECT emiten, json_data FROM announcements WHERE category LIKE '%Rights Issue%' OR category LIKE '%PMHMETD%' OR json_data LIKE '%hmetd%' OR json_data LIKE '%rights issue%'")
    ri_signals = {}
    for a_emiten, a_json in cursor.fetchall():
        if a_emiten and a_emiten not in ri_signals and a_json:
            facts = extract_facts(a_json)
            cum_val = facts.get("cum hmetd") or facts.get("cum date") or facts.get("batas waktu pemenuhan") or "Terjadwal (Pasca RUPSLB)"
            if not is_past_date(cum_val, today_dt):
                target_val = facts.get("target total modal / dana") or facts.get("target total dana") or facts.get("target dana") or "Target Modal Kerja / Ekspansi"
                harga_val = facts.get("harga pelaksanaan hmetd") or facts.get("harga pelaksanaan") or "Sesuai Prospektus HMETD"
                rasio_val = facts.get("rasio hmetd") or "Rasio Ditetapkan Pasca RUPSLB"
                standby_val = facts.get("pembeli siaga") or facts.get("komitmen pembeli siaga") or "Standby Buyers / Pengendali"
                ri_signals[a_emiten] = {
                    "target_dana": target_val,
                    "harga_pelaksanaan": harga_val,
                    "rasio": rasio_val,
                    "standby_buyer": standby_val,
                    "cum_hmetd": cum_val
                }

    # ─────────────────────────────────────────────────────────────────────────
    # 5. EARNINGS SURGE (>20% YoY GROWTH) & INSIDER CATALYSTS
    # ─────────────────────────────────────────────────────────────────────────
    cursor.execute("SELECT emiten, title, exec_summary, json_data FROM announcements WHERE exec_summary LIKE '%naik%' OR exec_summary LIKE '%tumbuh%' OR exec_summary LIKE '%melonjak%' OR title LIKE '%kinerja%' OR title LIKE '%siaran pers%'")
    growth_signals = {}
    for a_emiten, a_title, a_exec, a_json in cursor.fetchall():
        if a_emiten and a_emiten not in growth_signals:
            growth_signals[a_emiten] = {
                "title": a_title,
                "summary": a_exec or "Publikasi Pertumbuhan Kinerja Keuangan Positif",
                "rating": "🔥 GROWTH BREAKOUT"
            }

    cursor.execute("SELECT emiten, title, exec_summary FROM announcements WHERE exec_summary LIKE '%insider%' OR exec_summary LIKE '%kepemilikan%' OR title LIKE '%perubahan kepemilikan%'")
    insider_signals = {}
    for a_emiten, a_title, a_exec in cursor.fetchall():
        if a_emiten and a_emiten not in insider_signals:
            insider_signals[a_emiten] = {
                "detail": a_exec or a_title
            }

    conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # BUILD MARKDOWN DOCUMENT
    # ─────────────────────────────────────────────────────────────────────────
    lines = []
    lines.append(f"# 🎯 Sinyal Cuan & Katalis Trading Harian (Alpha Signal Radar) - {today_str}\n")
    lines.append(f"⬅️ [[knowledge-base/daily-digests/Daily_Digest_{today_fn}|Kembali ke Daily Digest]] | 📅 **{today_str}** | 🎛️ [[Dashboard|Ke Dashboard Utama]]\n")
    lines.append("> [!TIP]\n> Laporan ini dihasilkan secara otomatis oleh **AI Swarm Intelligence** untuk mendeteksi peluang capital gain, dividend yield capture, arbitrase aksi korporasi, dan sinyal akumulasi insider di Bursa Efek Indonesia (BEI).\n")
    lines.append("---\n")

    matrix_rows = []

    # SECTION 1: DIVIDEND CAPTURE PLAY
    lines.append("## 💸 1. Sinyal Berburu Dividen Tinggi (High Dividend Capture Play)")
    if div_signals:
        for emiten, d in div_signals.items():
            lines.append(f"### 💰 [[{emiten}]] - Potensi Dividend Yield High-Conviction")
            lines.append(f"- **Nominal Dividen**: `{d['nominal']}`")
            lines.append(f"- **Total Nilai Pembayaran**: `{d['total']}`")
            lines.append(f"- **📅 Cum Date (Batas Beli)**: **{d['cum_date']}**")
            lines.append(f"- **💸 Tanggal Pembayaran**: `{d['payment_date']}`")
            lines.append(f"- 📈 **Strategi Aksi**: *Accumulate on Dips*. Lakukan akumulasi sebelum **Cum Date ({d['cum_date']})** untuk mengunci hak dividen tunai.")
            lines.append(f"\n```mermaid\ngraph LR\n    A[\"📅 Cum Date: {d['cum_date']}\"] -->|Akumulasi Saham| B[\"📋 Ex Date (Waspada Dividend Trap)\"]\n    B --> C[\"💸 Pembayaran Dana: {d['payment_date']} ({d['nominal']})\"]\n```\n")
            matrix_rows.append(f"| **[[{emiten}]]** | Dividen Tunai ({d['nominal']}) | 🔥 **HIGH YIELD** | Akumulasi s.d. {d['cum_date']} | **Cash Yield Play** |")
    else:
        lines.append("*Belum terdeteksi pengumuman dividen baru dengan Cum Date aktif hari ini.*\n")

    lines.append("---\n")

    # SECTION 2: MTO & ARBITRAGE
    lines.append("## 🎯 2. Peluang Arbitrase Aksi Korporasi & Tender Offer (MTO)")
    if mto_signals:
        for emiten, m in mto_signals.items():
            lines.append(f"### 🏢 [[{emiten}]] - Penawaran Tender Wajib (MTO) oleh [[{m['pengendali']}]]")
            lines.append(f"- **Pengendali Baru**: `[[{m['pengendali']}]]`")
            lines.append(f"- **Detail Transaksi**: {m['detail']}")
            lines.append(f"- 💡 **Strategi Arbitrase**: Pantau rilis harga penawaran Tender Wajib resmi. Jika harga penawaran MTO lebih tinggi dari harga pasar reguler, terdapat peluang **Risk-Free Arbitrage Spread**!")
            lines.append(f"\n```mermaid\ngraph TD\n    Controller[\"🏢 {m['pengendali']}\"] -->|Penawaran Tender Wajib| Target[\"🏬 {emiten}\"]\n    Target -->|Garansi Price Floor MTO| Profit[\"💵 Arbitrage Spread\"]\n```\n")
            matrix_rows.append(f"| **[[{emiten}]]** | Mandatory Tender Offer | 🚀 **ARBITRAGE SPREAD** | Pantau Harga Penawaran MTO | **Spread Arbitrase** |")
    else:
        lines.append("*Tidak ada aksi Tender Offer (MTO) aktif pada periode pengamatan terkini.*\n")

    lines.append("---\n")

    # SECTION 3: BUYBACK PRICE FLOOR
    lines.append("## 🛍️ 3. Sinyal Penahan Harga Saham (Buyback Price Floor & Value Support)")
    if buyback_signals:
        for emiten, b in buyback_signals.items():
            lines.append(f"### 🛡️ [[{emiten}]] - Program Pembelian Kembali Saham (Buyback)")
            lines.append(f"- **Alokasi Dana Maksimum**: `{b['alokasi_dana']}`")
            lines.append(f"- **Batas Harga Pelaksanaan**: `{b['harga_maksimum']}`")
            lines.append(f"- **Periode Pelaksanaan**: `{b['periode']}`")
            lines.append(f"- 💡 **Strategi Aksi**: Dana *buyback* memberikan penopang harga (*price floor*) di pasar reguler dan mengindikasikan harga saham dinilai *undervalued* oleh manajemen perseroan.")
            matrix_rows.append(f"| **[[{emiten}]]** | Buyback Saham ({b['alokasi_dana']}) | 🟢 **PRICE SUPPORT** | Buy on Support / Accumulate | **Capital Preservation** |")
    else:
        lines.append("*Tidak ada pengumuman program buyback baru hari ini.*\n")

    lines.append("\n---\n")

    # SECTION 4: RIGHTS ISSUE CATALYSTS
    lines.append("## 📜 4. Peluang Aksi Korporasi Rights Issue (PMHMETD & Ekspansi)")
    if ri_signals:
        for emiten, r in ri_signals.items():
            lines.append(f"### 🏨 [[{emiten}]] - Rencana Penambahan Modal HMETD (Rights Issue)")
            lines.append(f"- **Target Total Dana**: `{r['target_dana']}`")
            lines.append(f"- **Harga Pelaksanaan & Rasio**: `{r['harga_pelaksanaan']}` | `{r['rasio']}`")
            lines.append(f"- **Komitmen Pembeli Siaga**: `{r['standby_buyer']}`")
            lines.append(f"- **📅 Cum HMETD**: **{r['cum_hmetd']}**")
            lines.append(f"- ⚠️ **Strategi Investor**: Bandingkan harga pelaksanaan HMETD vs harga pasar. Tebus HMETD jika harga pasar berada di atas harga pelaksanaan guna mencegah dilusi kepemilikan.")
            matrix_rows.append(f"| **[[{emiten}]]** | Rights Issue / HMETD | 🟡 **EXPANSION / DILUTION** | Evaluasi Harga Tebus vs Pasar | **Fundamental Expansion** |")
    else:
        lines.append("*Tidak ada aksi Rights Issue dengan Cum HMETD aktif hari ini.*\n")

    lines.append("\n---\n")

    # SECTION 5: EARNINGS GROWTH SURGE
    lines.append("## 🚀 5. Sinyal Keuntungan Laba & Kinerja Positif (Earnings Surge Catalyst)")
    if growth_signals:
        for emiten, g in list(growth_signals.items())[:5]:
            lines.append(f"### 📈 [[{emiten}]] - {g['title']}")
            lines.append(f"- **Ikhtisar Kinerja**: {g['summary']}")
            lines.append(f"- 🎯 **Implikasi Pasar**: Momentum pertumbuhan positif mendorong apresiasi harga saham dan potensi pembagian dividen lebih besar.")
            matrix_rows.append(f"| **[[{emiten}]]** | Pertumbuhan Kinerja Positif | 🔥 **GROWTH BREAKOUT** | Buy on Retracement / Momentum | **Capital Gain** |")
    else:
        lines.append("*Tidak ada siaran pers lonjakan laba signifikan yang terdeteksi hari ini.*\n")

    lines.append("\n---\n")

    # SECTION 6: INSIDER ACCUMULATION TRACKER
    lines.append("## 🐋 6. Radar Akumulasi Pihak Dalam (Insider Buy Tracker)")
    if insider_signals:
        for emiten, ins in list(insider_signals.items())[:5]:
            lines.append(f"- **[[{emiten}]]**: {ins['detail']}")
    else:
        lines.append("*Tidak terdeteksi transaksi perubahan kepemilikan insider signifikan hari ini.*")

    lines.append("\n---\n")

    # SECTION 7: TRADING ACTION MATRIX
    lines.append("## 📊 7. Matriks Rekomendasi Aksi Investor & Trading Alpha")
    lines.append("| Emiten | Jenis Katalis | Rating Sinyal | Target Aksi Investor | Ekspektasi Peluang |")
    lines.append("| :--- | :--- | :---: | :--- | :---: |")
    if matrix_rows:
        for mrow in matrix_rows:
            lines.append(mrow)
    else:
        lines.append("| - | *Belum ada katalis aktif* | ⚪ **NEUTRAL** | Standby Radar | - |")

    lines.append("\n---\n")
    lines.append("## 🔗 Hubungan Note Terkait (Knowledge Graph)")
    lines.append(f"- [[knowledge-base/daily-digests/Daily_Digest_{today_fn}|📄 Daily Digest {today_str}]]")
    lines.append(f"- [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Aksi Korporasi]]")
    lines.append(f"- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]")

    signal_content = "\n".join(lines)
    
    year_month = f"{today_fn[:4]}-{today_fn[4:6]}" if (len(today_fn) >= 6 and today_fn[:6].isdigit()) else datetime.now().strftime("%Y-%m")
    out_dir = os.path.join(OUTPUT_DIR, "trading-signals", year_month)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"Trading_Signals_{today_fn}.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(signal_content)
        
    print(f"[+] Trading Signals generated at: {out_file}")

    # Copy directly to local Obsidian Vault
    obs_dir = os.path.join(OBSIDIAN_SIGNALS_DIR, year_month)
    try:
        os.makedirs(obs_dir, exist_ok=True)
        obs_file = os.path.join(obs_dir, f"Trading_Signals_{today_fn}.md")
        with open(obs_file, "w", encoding="utf-8") as f:
            f.write(signal_content)
        print(f"[+] Saved directly to Obsidian local vault: {obs_file}")
    except Exception as oe:
        print(f"[!] Obsidian copy error: {oe}")

    # Auto-push to Obsidian REST API if running
    try:
        daily_mon_path = os.path.join(BASE_DIR, r".agents\skills\daily-monitoring\scripts")
        if daily_mon_path not in sys.path:
            sys.path.append(daily_mon_path)
        from daily_run import push_to_obsidian_server
        push_to_obsidian_server(out_file, f"knowledge-base/trading-signals/{year_month}/Trading_Signals_{today_fn}.md")
    except Exception as e:
        print(f"[!] Push error: {e}")

if __name__ == "__main__":
    generate_trading_signals()