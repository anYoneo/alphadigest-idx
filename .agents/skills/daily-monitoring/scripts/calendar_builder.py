import sqlite3
import os
import json
import re
import glob
from datetime import datetime, date

BASE_DIR = r"G:\My Drive\Model2"
DB_PATH = os.path.join(BASE_DIR, r"reports\market_intelligence.db")
OUTPUT_DIR = os.path.join(BASE_DIR, r"reports\summaries")
CA_DIR = os.path.join(OUTPUT_DIR, "corporate-actions")

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

def clean_text(val):
    if not val:
        return "-"
    val = re.sub(r"\s+", " ", str(val)).strip()
    return val

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

def parse_markdown_facts(file_path):
    """Parses key parameters from a corporate action markdown report."""
    facts = {}
    if not os.path.exists(file_path):
        return facts
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        table_matches = re.findall(r"\|\s*\*\*?([^\*\|]+)\*\*?\s*\|\s*`?([^`\|]+)`?\s*\|", content)
        for p, v in table_matches:
            p_clean = p.strip().lower()
            v_clean = v.strip()
            facts[p_clean] = v_clean
            facts[p.strip()] = v_clean
            
        bullet_matches = re.findall(r"-\s*\*\*([^\*:]+)\*\*:\s*`?([^`\n]+)`?", content)
        for p, v in bullet_matches:
            p_clean = p.strip().lower()
            v_clean = v.strip()
            if p_clean not in facts:
                facts[p_clean] = v_clean
                facts[p.strip()] = v_clean
    except Exception as e:
        print(f"[!] Error parsing {file_path}: {e}")
    return facts

def extract_dates_from_json_data(json_str):
    """Parses json_data from DB and extracts date and other parameters from fakta_material."""
    result = {}
    if not json_str:
        return result
    try:
        data = json.loads(json_str)
        if "fakta_material" in data and isinstance(data["fakta_material"], list):
            for item in data["fakta_material"]:
                if isinstance(item, dict) and "parameter" in item and "nilai_parameter" in item:
                    k = item["parameter"].strip().lower()
                    v = str(item["nilai_parameter"]).strip()
                    result[k] = v
                    result[k.replace(" ", "_")] = v
        for k, v in data.items():
            if isinstance(v, str):
                k_clean = k.strip().lower()
                result[k_clean] = v.strip()
                result[k_clean.replace(" ", "_")] = v.strip()
    except Exception:
        pass
    return result

def build_action_calendar():
    """Generates a Master Action & Dividend Calendar note for Obsidian with smart date expiration filtering."""
    today_dt = date.today()
    today_str = today_dt.strftime("%Y-%m-%d")
    today_fn = today_dt.strftime("%Y%m%d")

    lines = []
    lines.append(f"# 🗓️ Kalender Terpusat Aksi Korporasi & Dividen BEI (Action Calendar) - {today_str}\n")
    lines.append(f"⬅️ [[knowledge-base/daily-digests/Daily_Digest_{today_fn}|Kembali ke Daily Digest]] | 📅 **{today_str}** | 🎛️ [[Dashboard|Ke Dashboard Utama]]\n")
    lines.append("> [!TIP]\n> Kalender ini merangkum tanggal penting **Cum Date Dividen**, **Periode HMETD**, **Program Buyback**, **Penawaran MTO**, dan **Jadwal DPS/RUPSLB** secara aktif. Event yang telah melewati tanggal pelaksanaan otomatis dipindahkan ke bagian Arsip Selesai.\n")
    lines.append("---\n")

    db_conn = None
    if os.path.exists(DB_PATH):
        db_conn = sqlite3.connect(DB_PATH)

    # -------------------------------------------------------------------------
    # SECTION 1: DIVIDEND CALENDAR (Active vs Expired)
    # -------------------------------------------------------------------------
    lines.append("## 💸 1. Kalender Pembagian Dividen Tunai & Interim (Mendatang / Aktif)")
    lines.append("| Emiten | Nominal Dividen | Total Nilai | 📅 Cum Date (Batas Beli) | 💸 Tanggal Pembayaran | Rating Sinyal | Dokumen |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :---: | :---: |")

    div_emitens = {}
    div_expired = []
    
    if db_conn:
        cursor = db_conn.cursor()
        try:
            # Priority 1: dividends table
            cursor.execute("SELECT emiten, nominal, total, cum_date, payment_date FROM dividends ORDER BY id DESC")
            divs = cursor.fetchall()
            for emiten, nom, tot, cum, pay in divs:
                if emiten not in div_emitens:
                    nom_str = nom if nom and nom != "None" else "Terjadwal"
                    tot_str = tot if tot and tot != "None" else "Dalam Rincian LK"
                    div_emitens[emiten] = {
                        "nominal": nom_str,
                        "total": tot_str,
                        "cum": cum or "Terjadwal",
                        "payment": pay or "Terjadwal",
                        "link": f"[[{emiten}_Dividen_{today_fn}|📄 Dokumen]]"
                    }
            
            # Priority 2: announcements json_data
            cursor.execute("SELECT id, emiten, json_data FROM announcements WHERE category = 'Dividen' OR json_data LIKE '%dividen%'")
            for a_id, a_emiten, a_json in cursor.fetchall():
                if a_emiten and a_emiten not in div_emitens and a_json:
                    j_data = extract_dates_from_json_data(a_json)
                    if j_data:
                        nom = j_data.get("nominal dividen") or j_data.get("dividen per saham") or j_data.get("nominal") or "Dalam Rincian LK"
                        tot = j_data.get("total nilai dividen") or j_data.get("total nilai") or j_data.get("total dividen") or "Dalam Rincian LK"
                        cum = j_data.get("cum date") or j_data.get("cum date (batas beli)") or j_data.get("cum_date") or "Terjadwal 2026"
                        pay = j_data.get("tanggal pembayaran") or j_data.get("payment date") or j_data.get("payment_date") or "Terjadwal 2026"
                        if nom != "Dalam Rincian LK" or cum != "Terjadwal 2026":
                            div_emitens[a_emiten] = {
                                "nominal": nom,
                                "total": tot,
                                "cum": cum,
                                "payment": pay,
                                "link": f"[[{a_id}|📄 Dokumen]]"
                            }
        except Exception as e:
            print(f"[!] DB Announcements Dividen Error: {e}")

    div_dir = os.path.join(CA_DIR, "dividen")
    div_files = sorted(glob.glob(os.path.join(div_dir, "*.md")), reverse=True)
    for dfp in div_files:
        dfname = os.path.basename(dfp)
        emiten = dfname.split("_")[0]
        if emiten.startswith("X") or emiten == "PANI":
            continue
        if emiten in div_emitens:
            continue
        facts = parse_markdown_facts(dfp)
        nom = facts.get("nominal dividen") or facts.get("dividen per saham") or facts.get("nominal") or "Dalam Rincian LK"
        tot = facts.get("total nilai dividen") or facts.get("total nilai") or facts.get("total dividen") or "Dalam Rincian LK"
        cum = facts.get("cum date") or facts.get("cum date (batas beli)") or facts.get("cum_date") or "Terjadwal 2026"
        pay = facts.get("tanggal pembayaran") or facts.get("payment date") or facts.get("payment_date") or "Terjadwal 2026"
        slug = dfname.replace(".md", "")
        
        div_emitens[emiten] = {
            "nominal": nom,
            "total": tot,
            "cum": cum,
            "payment": pay,
            "link": f"[[{slug}|📄 Dokumen]]"
        }

    active_div_count = 0
    for em, data in sorted(div_emitens.items()):
        if is_past_date(data["cum"], today_dt):
            div_expired.append((em, data))
        else:
            lines.append(f"| **[[{em}]]** | `{data['nominal']}` | `{data['total']}` | **{data['cum']}** | `{data['payment']}` | 🔥 **HIGH YIELD** | {data['link']} |")
            active_div_count += 1

    if active_div_count == 0:
        lines.append("| - | - | - | *Tidak ada dividen mendatang* | - | - | - |")

    lines.append("\n---\n")

    # -------------------------------------------------------------------------
    # SECTION 2: RIGHTS ISSUE CALENDAR (Active vs Expired)
    # -------------------------------------------------------------------------
    lines.append("## 📜 2. Kalender Rights Issue (PMHMETD / HMETD - Aktif)")
    lines.append("| Emiten | Rasio & Harga HMETD | Target Dana | 📅 Cum HMETD | 📅 Periode Perdagangan HMETD | Status | Dokumen |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :---: | :---: |")

    ri_emitens = {}
    ri_expired = []
    
    if db_conn:
        cursor = db_conn.cursor()
        try:
            cursor.execute("SELECT id, emiten, json_data FROM announcements WHERE category LIKE '%Rights Issue%' OR category LIKE '%PMHMETD%' OR json_data LIKE '%hmetd%' OR json_data LIKE '%rights issue%'")
            for a_id, a_emiten, a_json in cursor.fetchall():
                if a_emiten and a_emiten not in ["PANI", "MDIY", "MPPA"] and a_emiten not in ri_emitens and a_json:
                    j_data = extract_dates_from_json_data(a_json)
                    if j_data:
                        harga = j_data.get("harga pelaksanaan hmetd") or j_data.get("harga pelaksanaan") or j_data.get("harga hmetd") or "Akan Ditentukan dalam Prospektus HMETD"
                        target = j_data.get("target total modal / dana") or j_data.get("target modal minimum") or j_data.get("target total dana") or "Dalam Proses RUPSLB"
                        cum = j_data.get("cum hmetd") or j_data.get("batas waktu pemenuhan") or j_data.get("cum date") or "Terjadwal (Pasca RUPSLB)"
                        periode = j_data.get("periode perdagangan hmetd") or j_data.get("periode perdagangan") or "Tanggapan Penjelasan BEI / RUPSLB"
                        if harga != "Akan Ditentukan dalam Prospektus HMETD" or cum != "Terjadwal (Pasca RUPSLB)":
                            ri_emitens[a_emiten] = {
                                "harga": harga,
                                "target": target,
                                "cum": cum,
                                "periode": periode,
                                "status": "🟡 **UPCOMING**",
                                "link": f"[[{a_id}|📄 Dokumen]]"
                            }
        except Exception as e:
            print(f"[!] DB Announcements Rights Issue Error: {e}")

    ri_dir = os.path.join(CA_DIR, "rights-issue")
    ri_files = sorted(glob.glob(os.path.join(ri_dir, "*.md")), reverse=True)
    for rfp in ri_files:
        rfname = os.path.basename(rfp)
        emiten = rfname.split("_")[0]
        if emiten in ["PANI", "MDIY", "MPPA"] or emiten in ri_emitens:
            continue
        facts = parse_markdown_facts(rfp)
        harga = facts.get("harga pelaksanaan hmetd") or facts.get("harga pelaksanaan") or facts.get("harga hmetd") or "Akan Ditentukan dalam Prospektus HMETD"
        target = facts.get("target total modal / dana") or facts.get("target modal minimum") or facts.get("target total dana") or "Dalam Proses RUPSLB"
        cum = facts.get("cum hmetd") or facts.get("batas waktu pemenuhan") or facts.get("cum date") or "Terjadwal (Pasca RUPSLB)"
        periode = facts.get("periode perdagangan hmetd") or "Tanggapan Penjelasan BEI / RUPSLB"
        slug = rfname.replace(".md", "")
        
        ri_emitens[emiten] = {
            "harga": harga,
            "target": target,
            "cum": cum,
            "periode": periode,
            "status": "🟡 **UPCOMING**",
            "link": f"[[{slug}|📄 Dokumen]]"
        }

    for em, data in sorted(ri_emitens.items()):
        if is_past_date(data["cum"], today_dt):
            ri_expired.append((em, data))
        else:
            lines.append(f"| **[[{em}]]** | `{data['harga']}` | `{data['target']}` | **{data['cum']}** | {data['periode']} | {data['status']} | {data['link']} |")

    lines.append("\n---\n")

    # -------------------------------------------------------------------------
    # SECTION 3: BUYBACK CALENDAR
    # -------------------------------------------------------------------------
    lines.append("## 🔄 3. Kalender Buyback (Pembelian Kembali Saham - Aktif)")
    lines.append("| Emiten | Alokasi Dana Buyback | Estimasi Harga / Jumlah Saham | 📅 Periode Pelaksanaan Buyback | Status | Dokumen |")
    lines.append("| :--- | :--- | :--- | :--- | :---: | :---: |")

    bb_emitens = {}
    
    if db_conn:
        cursor = db_conn.cursor()
        try:
            cursor.execute("SELECT id, emiten, json_data FROM announcements WHERE category LIKE '%Buyback%' OR json_data LIKE '%buyback%' OR json_data LIKE '%pembelian kembali%'")
            for a_id, a_emiten, a_json in cursor.fetchall():
                if a_emiten and a_emiten not in bb_emitens and a_json:
                    j_data = extract_dates_from_json_data(a_json)
                    if j_data:
                        dana = j_data.get("alokasi dana buyback") or j_data.get("alokasi dana") or j_data.get("maksimum dana buyback") or "Dalam Keterbukaan Informasi"
                        harga = j_data.get("harga maksimum buyback") or j_data.get("jumlah saham buyback") or j_data.get("estimasi harga") or "Harga Pasar Reguler"
                        periode = j_data.get("periode buyback") or j_data.get("periode pelaksanaan") or j_data.get("jangka waktu buyback") or "Terjadwal 2026"
                        if dana != "Dalam Keterbukaan Informasi" or periode != "Terjadwal 2026":
                            bb_emitens[a_emiten] = {
                                "dana": dana,
                                "harga": harga,
                                "periode": periode,
                                "status": "🟢 **AKSI AKTIF**",
                                "link": f"[[{a_id}|📄 Dokumen]]"
                            }
        except Exception as e:
            print(f"[!] DB Announcements Buyback Error: {e}")

    bb_dir = os.path.join(CA_DIR, "buyback")
    bb_files = sorted(glob.glob(os.path.join(bb_dir, "*.md")), reverse=True)
    for bfp in bb_files:
        bfname = os.path.basename(bfp)
        emiten = bfname.split("_")[0]
        if emiten in bb_emitens:
            continue
        facts = parse_markdown_facts(bfp)
        dana = facts.get("alokasi dana buyback") or facts.get("alokasi dana") or facts.get("maksimum dana buyback") or "Dalam Keterbukaan Informasi"
        harga = facts.get("harga maksimum buyback") or facts.get("jumlah saham buyback") or facts.get("estimasi harga") or "Harga Pasar Reguler"
        periode = facts.get("periode buyback") or facts.get("periode pelaksanaan") or facts.get("jangka waktu buyback") or "Terjadwal 2026"
        slug = bfname.replace(".md", "")

        bb_emitens[emiten] = {
            "dana": dana,
            "harga": harga,
            "periode": periode,
            "status": "🟢 **AKSI AKTIF**",
            "link": f"[[{slug}|📄 Dokumen]]"
        }

    for em, data in sorted(bb_emitens.items()):
        lines.append(f"| **[[{em}]]** | `{data['dana']}` | `{data['harga']}` | **{data['periode']}** | {data['status']} | {data['link']} |")

    lines.append("\n---\n")

    # -------------------------------------------------------------------------
    # SECTION 4: PRIVATE PLACEMENT (PMTHMETD) CALENDAR
    # -------------------------------------------------------------------------
    lines.append("## ⚡ 4. Kalender Private Placement (PMTHMETD / Debt-to-Equity Swap)")
    lines.append("| Emiten | Skema Aksi Korporasi | Target Konversi Utang / Modal | Status | Dokumen |")
    lines.append("| :--- | :--- | :--- | :---: | :---: |")

    pp_dir = os.path.join(CA_DIR, "private-placement")
    pp_files = sorted(glob.glob(os.path.join(pp_dir, "*.md")), reverse=True)
    pp_emitens = {}
    for pfp in pp_files:
        pfname = os.path.basename(pfp)
        emiten = pfname.split("_")[0]
        if emiten in pp_emitens:
            continue
        facts = parse_markdown_facts(pfp)
        skema = facts.get("skema aksi korporasi") or facts.get("jenis aksi korporasi") or "PMTHMETD / Private Placement"
        target = facts.get("target konversi utang / modal") or facts.get("target total modal / dana") or facts.get("target dana") or "Dalam Proses RUPSLB"
        slug = pfname.replace(".md", "")

        pp_emitens[emiten] = {
            "skema": skema,
            "target": target,
            "status": "🟡 **PROSES RUPSLB**",
            "link": f"[[{slug}|📄 Dokumen]]"
        }

    for em, data in sorted(pp_emitens.items()):
        lines.append(f"| **[[{em}]]** | `{data['skema']}` | `{data['target']}` | {data['status']} | {data['link']} |")

    lines.append("\n---\n")

    # -------------------------------------------------------------------------
    # SECTION 5: MANDATORY TENDER OFFER (MTO) CALENDAR
    # -------------------------------------------------------------------------
    lines.append("## 🎯 5. Kalender Mandatory Tender Offer (MTO)")
    lines.append("| Emiten | Pengendali Baru | Status MTO | Catatan Strategis | Dokumen |")
    lines.append("| :--- | :--- | :--- | :--- | :---: |")

    mto_emitens = {}
    
    if db_conn:
        cursor = db_conn.cursor()
        try:
            # Priority 1: mto_events table
            cursor.execute("SELECT id, emiten, new_controller, main_topic, details FROM mto_events ORDER BY id DESC")
            for m_id, m_emiten, m_new_controller, m_main_topic, m_details in cursor.fetchall():
                if m_emiten and m_emiten not in mto_emitens:
                    mto_emitens[m_emiten] = {
                        "pengendali": m_new_controller or "Pengendali Baru",
                        "status": "🟡 **PROSES PENAWARAN**",
                        "catatan": m_main_topic or "Pantau Rilis Harga MTO Resmi",
                        "link": f"[[{m_emiten}_MTO_{today_fn}|📄 Dokumen]]"
                    }
                    
            # Priority 2: announcements json_data
            cursor.execute("SELECT id, emiten, json_data FROM announcements WHERE category LIKE '%Tender Offer%' OR json_data LIKE '%tender offer%' OR json_data LIKE '%mto%'")
            for a_id, a_emiten, a_json in cursor.fetchall():
                if a_emiten and a_emiten not in mto_emitens and a_json:
                    j_data = extract_dates_from_json_data(a_json)
                    if j_data:
                        pengendali = j_data.get("pengendali baru") or j_data.get("pihak pembeli") or j_data.get("nama pihak penawar") or "Pengendali Baru"
                        status_mto = j_data.get("status mto") or j_data.get("status penawaran") or "PROSES PENAWARAN"
                        catatan = j_data.get("catatan strategis") or j_data.get("harga penawaran tender") or "Pantau Rilis Harga MTO Resmi"
                        if pengendali != "Pengendali Baru" or catatan != "Pantau Rilis Harga MTO Resmi":
                            mto_emitens[a_emiten] = {
                                "pengendali": pengendali,
                                "status": status_mto if "**" in status_mto else f"🟡 **{status_mto}**",
                                "catatan": catatan,
                                "link": f"[[{a_id}|📄 Dokumen]]"
                            }
        except Exception as e:
            print(f"[!] DB Announcements MTO Error: {e}")

    mto_dir = os.path.join(CA_DIR, "tender-offer")
    mto_files = sorted(glob.glob(os.path.join(mto_dir, "*.md")), reverse=True)
    for mfp in mto_files:
        mfname = os.path.basename(mfp)
        emiten = mfname.split("_")[0]
        if emiten in mto_emitens:
            continue
        facts = parse_markdown_facts(mfp)
        pengendali = facts.get("pengendali baru") or facts.get("pihak pembeli") or facts.get("nama pihak penawar") or "Pengendali Baru"
        status_mto = facts.get("status mto") or facts.get("status penawaran") or "🟡 **PROSES PENAWARAN**"
        catatan = facts.get("catatan strategis") or facts.get("harga penawaran tender") or "Pantau Rilis Harga MTO Resmi"
        slug = mfname.replace(".md", "")

        mto_emitens[emiten] = {
            "pengendali": pengendali,
            "status": status_mto if "**" in status_mto else f"🟡 **{status_mto}**",
            "catatan": catatan,
            "link": f"[[{slug}|📄 Dokumen]]"
        }

    for em, data in sorted(mto_emitens.items()):
        lines.append(f"| **[[{em}]]** | `{data['pengendali']}` | {data['status']} | {data['catatan']} | {data['link']} |")

    lines.append("\n---\n")

    # -------------------------------------------------------------------------
    # SECTION 6: RUPS & ELIGIBLE DATE (DPS) CALENDAR (Active vs Expired)
    # -------------------------------------------------------------------------
    lines.append("## 🏛️ 6. Kalender Agenda RUPS & Batas Hak Suara (Eligible Date / DPS - Aktif)")
    lines.append("| Emiten | Jenis Rapat | 📝 Batas Hak Suara (DPS) | 🏛️ Tanggal RUPS | Agenda Utama | Dokumen Resmi |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :---: |")

    seen_rups_emiten = set()
    rups_expired = []
    
    if db_conn:
        cursor = db_conn.cursor()
        try:
            cursor.execute("SELECT id, emiten, json_data FROM announcements WHERE category LIKE '%RUPS%' OR json_data LIKE '%rups%'")
            for a_id, a_emiten, a_json in cursor.fetchall():
                if a_emiten and a_emiten not in seen_rups_emiten and a_json:
                    j_data = extract_dates_from_json_data(a_json)
                    if j_data:
                        r_date = j_data.get("tanggal rups") or j_data.get("tanggal pelaksanaan") or j_data.get("hari & tanggal rupslb") or "Terjadwal"
                        r_dps = j_data.get("dps") or j_data.get("recording date") or j_data.get("eligible date") or "Terjadwal"
                        r_ag = j_data.get("agenda utama") or j_data.get("agenda") or "Persetujuan Aksi Korporasi & Tata Kelola Perseroan"
                        
                        if r_date != "Terjadwal" or r_dps != "Terjadwal":
                            seen_rups_emiten.add(a_emiten)
                            r_ag_clean = clean_text(r_ag)
                            if len(r_ag_clean) > 80:
                                r_ag_clean = r_ag_clean[:77] + "..."
                            r_link = f"[[{a_id}|📄 Dokumen]]"
                            
                            if is_past_date(r_date, today_dt):
                                rups_expired.append((a_emiten, r_dps, r_date, r_ag_clean, r_link))
                            else:
                                lines.append(f"| **[[{a_emiten}]]** | RUPSLB / RUPST | **{r_dps}** | **{r_date}** | {r_ag_clean} | {r_link} |")
        except Exception as e:
            print(f"[!] DB Announcements RUPS Error: {e}")

    rups_dir = os.path.join(CA_DIR, "rups")
    rups_files = sorted(glob.glob(os.path.join(rups_dir, "**", "*.md"), recursive=True))

    if rups_files:
        for rfp in reversed(rups_files):
            rfname = os.path.basename(rfp)
            with open(rfp, "r", encoding="utf-8") as _rf:
                rtext = _rf.read()
            em_m = re.search(r"\[\[([A-Z0-9]{4})\]\]", rtext)
            r_emiten = em_m.group(1) if em_m else rfname.split("_")[0]

            if r_emiten in seen_rups_emiten:
                continue
            seen_rups_emiten.add(r_emiten)

            rups_dt_m = re.search(r"(?:Tanggal RUPS|Tanggal Pelaksanaan|Hari & Tanggal RUPSLB)[^\n|]*?:\s*([^\n|]+)", rtext, re.IGNORECASE)
            r_date = rups_dt_m.group(1).strip("`* ") if rups_dt_m else "Terjadwal"

            dps_m = re.search(r"(?:DPS|Recording Date|Eligible Date)[^\n|]*?:\s*([^\n|]+)", rtext, re.IGNORECASE)
            r_dps = dps_m.group(1).strip("`* ") if dps_m else "Terjadwal"

            ag_m = re.search(r"(?:Agenda Utama|Agenda)[^\n|]*?:\s*([^\n|]+)", rtext, re.IGNORECASE)
            r_ag = ag_m.group(1).strip("`* ") if ag_m else "Persetujuan Aksi Korporasi & Tata Kelola Perseroan"
            r_ag_clean = clean_text(r_ag)
            if len(r_ag_clean) > 80:
                r_ag_clean = r_ag_clean[:77] + "..."

            r_slug = rfname.replace(".md", "")
            r_link = f"[[{r_slug}|📄 Dokumen]]"

            if is_past_date(r_date, today_dt):
                rups_expired.append((r_emiten, r_dps, r_date, r_ag_clean, r_link))
            else:
                lines.append(f"| **[[{r_emiten}]]** | RUPSLB / RUPST | **{r_dps}** | **{r_date}** | {r_ag_clean} | {r_link} |")

    if db_conn:
        db_conn.close()

    # -------------------------------------------------------------------------
    # SECTION 7: ARCHIVE / EXPIRED EVENTS (Completed / Past Dates)
    # -------------------------------------------------------------------------
    if div_expired or rups_expired or ri_expired:
        lines.append("\n---\n")
        lines.append("## 📦 7. Arsip Aksi Korporasi Selesai (Past Executed Events)")
        lines.append("> [!NOTE]\n> Bagian ini memuat daftar aksi korporasi yang Cum Date / Tanggal RUPS-nya telah terlewati dari tanggal hari ini.\n")
        lines.append("| Emiten | Kategori | Tanggal Pelaksanaan | Status | Dokumen |")
        lines.append("| :--- | :--- | :--- | :---: | :---: |")
        for em, d_data in div_expired:
            lines.append(f"| **[[{em}]]** | Dividen Tunai | `{d_data['cum']}` | ⚪ **SELESAI** | {d_data['link']} |")
        for r_em, r_dps, r_date, r_ag, r_link in rups_expired:
            lines.append(f"| **[[{r_em}]]** | RUPSLB / RUPST | `{r_date}` | ⚪ **SELESAI** | {r_link} |")
        for em, r_data in ri_expired:
            lines.append(f"| **[[{em}]]** | Rights Issue | `{r_data['cum']}` | ⚪ **SELESAI** | {r_data['link']} |")

    lines.append("\n---\n")
    lines.append("## 🔗 Hubungan Note Terkait (Knowledge Graph)")
    lines.append(f"- [[knowledge-base/trading-signals/Trading_Signals_{today_fn}|🎯 Sinyal Cuan {today_str}]]")
    lines.append(f"- [[knowledge-base/daily-digests/Daily_Digest_{today_fn}|📄 Daily Digest {today_str}]]")
    lines.append(f"- [[Dashboard|🎛️ Kembali ke Dashboard]]")

    content = "\n".join(lines)
    out_file = os.path.join(OUTPUT_DIR, "Action_Calendar.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[+] Action Calendar created at: {out_file}")

    vault_cal = os.path.join(BASE_DIR, r"Finplan_analyst\knowledge-base\calendars\Action_Calendar.md")
    try:
        os.makedirs(os.path.dirname(vault_cal), exist_ok=True)
        with open(vault_cal, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[+] Action Calendar copied to vault: {vault_cal}")
    except Exception as e:
        print(f"[!] Copy error: {e}")


if __name__ == "__main__":
    build_action_calendar()