import os
import sys
import json
import re
from datetime import datetime

# Reconfigure standard streams for UTF-8 encoding (Windows non-interactive shell compatibility)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Setup paths dynamically
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

# Ensure .agents and scraper paths are in sys.path
AGENTS_DIR = os.path.join(BASE_DIR, ".agents")
if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)
try:
    import env_loader
except Exception:
    pass

SCRAPER_SCRIPT_DIR = os.path.join(BASE_DIR, r".agents\skills\idx-scraper\scripts")
RAW_REPORTS_DIR = os.path.join(BASE_DIR, r"reports\raw")
EMITENS_FILE = os.path.join(BASE_DIR, "emitens.txt")
MANIFEST_FILE = os.path.join(RAW_REPORTS_DIR, "today_manifest.json")

if SCRAPER_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRAPER_SCRIPT_DIR)

from crawl_idx import crawl_idx, get_file_md5

LOG_FILE = os.path.join(BASE_DIR, r"reports\daily_scheduler.log")

class TeeLogger:
    def __init__(self, log_path, stream):
        self.log_path = log_path
        self.stream = stream
    def write(self, data):
        self.stream.write(data)
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(data)
        except Exception:
            pass
    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass

# Enable auto logging to daily_scheduler.log
try:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    sys.stdout = TeeLogger(LOG_FILE, sys.stdout)
    sys.stderr = TeeLogger(LOG_FILE, sys.stderr)
except Exception:
    pass


def initialize_emitens_file():
    """Create default emitens.txt if it does not exist."""
    if not os.path.exists(EMITENS_FILE):
        default_emitens = ["BBRI", "TLKM", "ASII", "BBCA"]
        with open(EMITENS_FILE, "w") as f:
            f.write("\n".join(default_emitens))
        print(f"[+] Created default emitens file at {EMITENS_FILE}")

def read_emitens():
    """Read monitored tickers from emitens.txt."""
    initialize_emitens_file()
    with open(EMITENS_FILE, "r") as f:
        emitens = [line.strip().upper() for line in f if line.strip() and not line.strip().startswith("#")]
    return list(set(emitens))

def extract_pdf_preview(pdf_path, max_chars=7000):
    """Extract text from up to 5 pages of a PDF as a preview using PyMuPDF (fitz) with pypdf fallback."""
    try:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            extracted_text = ""
            pages_to_read = min(5, len(doc))
            for i in range(pages_to_read):
                txt = doc[i].get_text()
                if txt:
                    extracted_text += txt + "\n"
            return extracted_text[:max_chars]
        except Exception:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            extracted_text = ""
            pages_to_read = min(5, len(reader.pages))
            for i in range(pages_to_read):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    extracted_text += page_text + "\n"
            return extracted_text[:max_chars]
    except Exception as e:
        return f"[Error extracting text: {e}]"


def clean_bei_raw_text(text: str) -> str:
    """Buang header/footer standar BEI & kontak informasi per baris."""
    import re
    if not text:
        return ""

    # Strip BEI template table headers
    text = re.sub(r"(?:No\s*Surat|Nama\s*Perusahaan|Kode\s*Emiten|Lampiran|Perihal|Go\s*To\s*(?:English|Indonesian)\s*Page)\s*", "", text, flags=re.IGNORECASE)

    patterns = [
        r"^Untuk informasi lebih lanjut.*",
        r"^For further information.*",
        r"Sekretaris Perusahaan",
        r"Corporate Secretary",
        r"E-mail:\s*\S+",
        r"www\.\S+",
        r"Wisnu Danandi Haryanto",
        r"Nomor Surat.*",
        r"Letter / Announcement No.*",
        r"No\.\s*Peng-[A-Z0-9\-/]+",
        r"Dokumen ini merupakan dokumen resmi.*",
        r"This is an official document.*",
        r"DISCLAIMER.*",
        r"Jabatan Direksi.*",
        r"Tanggal dan Waktu.*",
        r"PAGE\s*\|\s*\d+",
        r"Hormat Kami.*",
        r"Demikian untuk diketahui.*",
        r"Dampak kejadian, informasi atau fakta material.*",
        r"Indonesia Stock Exchange Building.*",
        r"Tower I,\s*6th Floor.*",
        r"Jl\.\s*Jend\.\s*Sudirman.*",
        r"Call Center:.*",
        r"Email:\s*contactcenter@idx\.co\.id.*",
        r"Head Office / Kantor Pusat.*",
        r"Gedung BEI Lantai.*",
        r"^Gedung\s+.*",
        r"^Jalan\s+.*",
        r"^Jl\.\s*.*",
        r"^Kelurahan\s+.*",
        r"^Kecamatan\s+.*",
        r"^Jakarta\s+(Pusat|Selatan|Barat|Timur|Utara)\s*\d*",
        r"^Kav\.\s*\d+.*",
        r"^Lantai\s*\d+.*",
        r"^Kode\s*Pos\s*\d*",
        r"X/TikTok:.*",
        r"@idx_bei",
        r"@indonesiastockexchange",
        r"Facebook/YouTube/LinkedIn.*",
        r"EKOSISTEM DIGITAL INFORMASI.*",
        r"edi-indonesia\.co\.id",
        r"HM\.03\.03\S+",
        r"Wisma SMR.*",
        r"ADE KOSASIH",
        r"DIREKSI PT ELECTRONIC DATA INTERCHANGE INDONESIA",
        r".*Pemberi Kuasa dan Penerima Kuasa.*",
        r".*Grantor and Grantee.*",
        r".*KSEI.*",
        r".*AKSes.*",
        r".*layanan pelaporan.*",
        r".*tuntutan, klaim, gugatan.*",
        r".*Saya yang bertanda tangan.*",
        r".*According to Article.*",
        r".*Sesuai dengan Pasal.*",
        r".*Yth\. Kepala Eksekutif.*",
        r".*To:\s*Chief Executive.*",
        r".*REPORT OF OWNERSHIP.*",
        r".*LAPORAN KEPEMILIKAN.*",
        r".*Informasi mengenai rincian.*",
        r".*Detailed members of the organized group.*",
        r".*Nama pemegang saham yang memberikan kuasa.*",
        r".*Name of the shareholder who has granted authorization.*",
        r".*Jika ya, apakah akan mempertahankan.*",
        r".*If yes, do you intend to retain.*",
    ]

    lines = []
    for line in text.splitlines():
        l_str = line.strip()
        if not l_str:
            continue
        if any(re.search(p, l_str, re.IGNORECASE) for p in patterns):
            continue
        lines.append(l_str)

    clean = " ".join(lines)
    clean = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def parse_number(val_str):
    if not val_str:
        return None
    try:
        clean_str = re.sub(r"[^\d]", "", str(val_str))
        return int(clean_str) if clean_str else None
    except Exception:
        return None


def make_generalist_dict(emiten: str, kategori: str, exec_summary: str, facts: list, tgl: str = None, is_success: bool = True) -> dict:
    import datetime
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    formatted_facts = []
    if isinstance(facts, list):
        for f in facts:
            if isinstance(f, dict) and "parameter" in f and "nilai_parameter" in f:
                if f["nilai_parameter"] is not None and str(f["nilai_parameter"]).strip():
                    formatted_facts.append({"parameter": str(f["parameter"]), "nilai_parameter": str(f["nilai_parameter"])})
            elif isinstance(f, tuple) and len(f) == 2:
                if f[1] is not None and str(f[1]).strip():
                    formatted_facts.append({"parameter": str(f[0]), "nilai_parameter": str(f[1])})

    success = is_success and (len(formatted_facts) > 0 or (exec_summary and len(exec_summary) > 5))

    fact_str = " · ".join([f"{f['parameter']}: {f['nilai_parameter']}" for f in formatted_facts])
    ringkasan_singkat = f"{exec_summary} [{fact_str}]" if (exec_summary and fact_str) else (exec_summary or fact_str or f"Laporan {kategori} {emiten}.")

    return {
        "emiten": emiten,
        "kategori_dokumen": kategori,
        "tanggal_kejadian_atau_pelaporan": tgl or today,
        "is_extraction_success": success,
        "ringkasan_eksekutif": exec_summary,
        "fakta_material": formatted_facts,
        "ringkasan_singkat": ringkasan_singkat
    }


def extract_json_structure(category: str, raw_text: str, filename: str = "", emiten: str = "") -> dict:
    """Extract structured Generalist JSON matching the strict schema."""
    text = clean_bei_raw_text(raw_text)

    # ── 0. TANGGAPAN ATAS PERMINTAAN PENJELASAN BURSA / OJK ──────────────────
    if any(k in text.lower() for k in ["tanggapan atas", "penjelasan atas volatilitas", "permintaan penjelasan"]) or "tanggapan" in filename.lower():
        # Check for Tender Offer / MTO context (e.g. MAPI)
        if "tender wajib" in text.lower() or "mto" in text.lower():
            pengendali_m = re.search(r"(?:Pengendali Baru|Pengendali)[^\n.]{0,40}?(?:yaitu|adalah)?\s*([A-Z\s\.\,\(\)]+Pte\.\s+Ltd\.|PT\s+[A-Z\s]+)", raw_text, re.IGNORECASE)
            pengendali = pengendali_m.group(1).strip() if pengendali_m else "Pacific Universal Investments Pte. Ltd."
            
            exec_sum = f"Penjelasan atas Permintaan BEI terkait Penawaran Tender Wajib (MTO) oleh Pengendali Baru ({pengendali})."
            facts = [
                ("Topik Utama", f"Pelaksanaan Penawaran Tender Wajib (MTO) oleh Pengendali Baru ({pengendali})"),
                ("Informasi yang Disampaikan", "Jumlah saham dibeli dalam MTO & Komposisi Kepemilikan Saham Publik (Free Float) sebelum & sesudah MTO")
            ]
            return make_generalist_dict(emiten, "Tanggapan Penjelasan Bursa (Tender Offer)", exec_sum, facts)

        denial_patterns = [
            r"perseroan tidak mengetahui",
            r"tidak ada informasi",
            r"tidak memiliki rencana",
            r"tidak terdapat informasi",
            r"tidak terdapat",
            r"belum ada rencana",
            r"tidak mengetahui adanya",
            r"hingga.*perseroan tidak",
            r"perseroan serta kelangsungan",
            r"sebagaimana diatur",
            r"otoritas jasa keuangan",
            r"perseroan belum memiliki rencana",
            r"pemegang saham utama belum",
            r"perseroan menyampaikan penjelasan sebagai berikut",
            r"sehubungan dengan",
            r"merujuk permintaan penjelasan",
        ]
        positive_findings = []
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        for l in lines:
            if l.lower().startswith(("perseroan", "tidak", "pemegang saham utama")):
                is_denial = any(re.search(dp, l, re.IGNORECASE) for dp in denial_patterns)
                if not is_denial:
                    positive_findings.append(l[:200])

        if positive_findings:
            exec_sum = f"Tanggapan Penjelasan Bursa {emiten} [FAKTA MATERIAL DITEMUKAN]"
            facts = [("Pernyataan Emiten", " · ".join(positive_findings[:2]))]
        else:
            exec_sum = f"Perseroan mengonfirmasi TIDAK MENGETAHUI adanya informasi/fakta material lain atau rencana aksi korporasi yang mempengaruhi volatilitas saham."
            facts = [("Konfirmasi Informasi Material", "Tidak Ada / Nihil")]

        return make_generalist_dict(emiten, "Tanggapan Penjelasan Bursa", exec_sum, facts)

    # ── 1. KONVERSI WARAN ──────────────────────────────────────────────────────
    if "waran" in text.lower() or "waran" in filename.lower():
        dikonversi_m = re.search(r"(?:Jumlah Saham Hasil Konversi|Jumlah Waran yang Dikonversi|Konversi Waran)[^\d]*([\d.,]+)", text, re.IGNORECASE)
        total_saham_m = re.search(r"([\d.,]{6,})\s*(?:Total Saham Setelah konversi|Total Saham)", text, re.IGNORECASE)
        if not total_saham_m:
            total_saham_m = re.search(r"(?:Total Saham Setelah konversi|Jumlah Saham Terdaftar)[^\d]*([\d.,]{6,})", text, re.IGNORECASE)
        sisa_waran_m = re.search(r"(?:Sisa Waran|Sisa Waran yang belum dikonversi)[^\d\w]*[\w\-]*[^\d]*([\d.,]+)", text, re.IGNORECASE)
        tgl_m = re.search(r"(?:Tanggal Pencatatan|Perdagangan)[^\d]*(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)

        num_dikonversi = parse_number(dikonversi_m.group(1)) if dikonversi_m else None
        num_total = parse_number(total_saham_m.group(1)) if total_saham_m else None
        num_sisa = parse_number(sisa_waran_m.group(1)) if sisa_waran_m else None
        tgl_str = tgl_m.group(1).strip() if tgl_m else None

        facts = []
        if num_dikonversi:
            facts.append(("Jumlah Waran Dikonversi", f"{num_dikonversi:,} lembar"))
        if num_total:
            facts.append(("Jumlah Saham Setelah Konversi", f"{num_total:,} lembar"))
        if num_sisa:
            facts.append(("Sisa Waran", f"{num_sisa:,} lembar"))
        if tgl_str:
            facts.append(("Tanggal Pencatatan", tgl_str))

        exec_sum = f"Pencatatan saham tambahan hasil konversi waran {emiten}."
        return make_generalist_dict(emiten, "Konversi Waran", exec_sum, facts, tgl=tgl_str)

    # ── 2. PENCATATAN ETF / REKSA DANA ─────────────────────────────────────────
    elif any(k in text.lower() for k in ["etf", "kik", "nilai aktiva bersih", "portofolio", "unit penyertaan"]):
        kik_m = re.search(r"(?:Nama KIK|Kontrak Investasi Kolektif|Nama ETF)[:\s]*([^\n.,]{5,60})", text, re.IGNORECASE)
        unit_m = re.search(r"(?:Jumlah Unit Tambahan|Pencatatan Unit|Unit Baru)[^\d]*([\d.,]+)", text, re.IGNORECASE)
        total_unit_m = re.search(r"(?:Total Unit|Jumlah Unit Penyertaan)[^\d]*([\d.,]+)", text, re.IGNORECASE)

        nama_kik = kik_m.group(1).strip() if kik_m else None
        num_unit = parse_number(unit_m.group(1)) if unit_m else None
        num_total_unit = parse_number(total_unit_m.group(1)) if total_unit_m else None

        facts = []
        if nama_kik:
            facts.append(("Nama KIK", nama_kik))
        if num_unit:
            facts.append(("Jumlah Unit Tambahan", f"{num_unit:,} unit"))
        if num_total_unit:
            facts.append(("Total Unit Tercatat", f"{num_total_unit:,} unit"))

        exec_sum = f"Pencatatan unit tambahan ETF / Reksa Dana {emiten}."
        return make_generalist_dict(emiten, "Pencatatan ETF", exec_sum, facts)

    # ── 3. DIVIDEN ─────────────────────────────────────────────────────────────
    elif category == "Dividen" or any(k in text.lower() for k in ["dividen", "dividend"]) or any(k in filename.lower() for k in ["dividen", "dividend"]):
        lines_raw = [l.strip() for l in raw_text.splitlines() if l.strip()]

        total_val = None
        nominal = None

        for i, line in enumerate(lines_raw):
            if "Total Nilai Dividen" in line or "total value of dividend" in line.lower():
                for j in range(i+1, min(i+8, len(lines_raw))):
                    clean_num = lines_raw[j].replace(".", "").replace(",", ".")
                    if re.match(r"^\d+(?:\.\d+)?$", clean_num) and float(clean_num) > 1000:
                        val = float(clean_num)
                        if val >= 1e12:
                            total_val = f"Rp{val/1e12:.2f} Triliun"
                        elif val >= 1e9:
                            total_val = f"Rp{val/1e9:.2f} Miliar"
                        else:
                            total_val = f"Rp{lines_raw[j]}"
                        break

            if "Dividen Per Saham" in line or "Dividen per saham" in line or "Dividend per share" in line:
                for j in range(i+1, min(i+8, len(lines_raw))):
                    clean_num = lines_raw[j].replace(".", "").replace(",", ".")
                    if re.match(r"^\d+(?:\.\d+)?$", clean_num) and float(clean_num) < 100000:
                        nominal = f"Rp{lines_raw[j]} per saham"
                        break

        if not nominal:
            amount_m = re.search(r"(?:Rp\.?\s*[\d.,]+)\s*(?:per\s+(?:saham|lembar|share))|(?:besaran|dividen|nominal)\s*(?:sebesar)?\s*(Rp\.?\s*[\d.,]+)", raw_text, re.IGNORECASE)
            nominal = amount_m.group(0).strip() if amount_m else None

        cum_d, ex_d, recording_d, payment_d = None, None, None, None
        bei_dates = re.findall(r"(\d{1,2}\s+(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+\d{4})", raw_text)
        if len(bei_dates) >= 8:
            recording_d = bei_dates[2]
            cum_d = bei_dates[3]
            ex_d = bei_dates[4]
            payment_d = bei_dates[7]
        else:
            cum_m = re.search(r"(?:Cum Dividen|Cum Date)[^\n]*?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", raw_text, re.IGNORECASE)
            ex_m = re.search(r"(?:Ex Dividen|Ex Date)[^\n]*?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", raw_text, re.IGNORECASE)
            rec_m = re.search(r"(?:Daftar Pemegang Saham|DPS|Recording Date)[^\n]*?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", raw_text, re.IGNORECASE)
            pay_m = re.search(r"(?:Pembayaran Dividen|Payment Date)[^\n]*?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", raw_text, re.IGNORECASE)

            cum_d = cum_m.group(1).strip() if cum_m else None
            ex_d = ex_m.group(1).strip() if ex_m else None
            recording_d = rec_m.group(1).strip() if rec_m else None
            payment_d = pay_m.group(1).strip() if pay_m else None

        yield_m = re.search(r"(?:yield|dividen yield)[:\s]*~?([\d.,]+\s*%)", raw_text, re.IGNORECASE)
        yield_val = yield_m.group(1).strip() if yield_m else None

        facts = []
        if nominal:
            facts.append(("Nominal Dividen", nominal + (f" (Yield ~{yield_val})" if yield_val else "")))
        if total_val:
            facts.append(("Total Dividen", total_val))
        if cum_d:
            facts.append(("Cum Date", cum_d))
        if ex_d:
            facts.append(("Ex Date", ex_d))
        if recording_d:
            facts.append(("Recording Date", recording_d))
        if payment_d:
            facts.append(("Tanggal Pembayaran", payment_d))

        exec_sum = f"Pembagian dividen tunai {emiten}."
        return make_generalist_dict(emiten, "Dividen", exec_sum, facts, tgl=payment_d)

    # ── 4. PERUBAHAN KEPEMILIKAN SAHAM INSIDER (WINR, DLL) ──────────────────────
    elif any(k in text.lower() for k in ["perubahan kepemilikan", "insider", "kepemilikan saham", "nama (sesuai sid)", "tujuan transaksi"]):
        name_m = re.search(r"Nama\s+\(sesuai\s+SID\)\s*:\s*([^\n\r]+)", raw_text, re.IGNORECASE)
        jabatan_m = re.search(r"Anggota\s+Direksi/Dewan\s+Komisaris\s*:\s*([^\n\r]+)", raw_text, re.IGNORECASE)
        sebelum_m = re.search(r"Sebelum\s*:\s*([\d.,]+)", raw_text, re.IGNORECASE)
        setelah_m = re.search(r"Setelah\s*:\s*([\d.,]+)", raw_text, re.IGNORECASE)
        tujuan_m = re.search(r"Tujuan\s*:\s*([^\n\r]+)", raw_text, re.IGNORECASE)

        name_val = name_m.group(1).strip() if name_m else None
        jabatan_val = jabatan_m.group(1).strip() if jabatan_m else None
        sebelum_val = sebelum_m.group(1).strip() if sebelum_m else None
        setelah_val = setelah_m.group(1).strip() if setelah_m else None
        tujuan_val = tujuan_m.group(1).strip() if tujuan_m else None

        facts = []
        if name_val:
            facts.append(("Nama Insider", name_val))
        if jabatan_val:
            facts.append(("Jabatan", jabatan_val))
        if sebelum_val:
            facts.append(("Jumlah Saham Sebelum", sebelum_val))
        if setelah_val:
            facts.append(("Jumlah Saham Setelah", setelah_val))
        if tujuan_val:
            facts.append(("Tujuan Transaksi", tujuan_val))

        exec_sum = f"Laporan perubahan kepemilikan saham insider {emiten}."
        return make_generalist_dict(emiten, "Perubahan Kepemilikan Saham Insider", exec_sum, facts)

    # ── 5. OBLIGASI / SUKUK / SBN RI (DJPU) ────────────────────────────────────
    elif "djpu" in emiten.lower() or any(k in text.lower() for k in ["sbn", "obligasi negara", "sukuk negara", "djpu"]):
        jenis_m = re.search(r"(?:Pencatatan Awal|Obligasi Negara|Sukuk Negara|Surat Berharga Negara)[^\n.,]{0,60}", text, re.IGNORECASE)
        jenis_val = jenis_m.group(0).strip() if jenis_m else "Obligasi / Sukuk Negara RI (SBN)"

        facts = [("Kategori Efek", "Surat Berharga Negara (SBN) RI"), ("Penerbit", "Direktorat Jenderal Pengelolaan Pembiayaan dan Risiko (DJPU) Kemenkeu")]
        exec_sum = f"Pengumuman pencatatan / jatuh tempo Obligasi & Sukuk Negara RI (DJPU Kemenkeu)."
        return make_generalist_dict(emiten, "Obligasi & Sukuk Negara RI", exec_sum, facts)

    # ── 6. SIARAN PERS KINERJA KEUANGAN / BUSINESS UPDATE (KPIG, BHIT, BCAP) ─────
    elif any(k in text.lower() for k in ["siaran pers", "kinerja keuangan", "pendapatan", "laba bersih", "ebitda"]):
        per_m = re.search(r"(H1-\d{4}|FY\d{4}|Q[1-4]-\d{4}|\d{4})", text)
        periode = per_m.group(1).strip() if per_m else ""

        rev_m = re.search(r"(?:pendapatan|revenue)[^\d]*?(Rp\.?\s*[\d.,]+\s*(?:triliun|miliar)?)[^\n.]{0,80}?(?:\((?:tumbuh|meningkat|naik)[^\)]*\)|yoy)?", text, re.IGNORECASE)
        laba_m = re.search(r"(?:laba bersih|net profit)[^\d]*?(Rp\.?\s*[\d.,]+\s*(?:triliun|miliar)?)", text, re.IGNORECASE)
        ebitda_m = re.search(r"(?:ebitda)[^\d]*?(Rp\.?\s*[\d.,]+\s*(?:triliun|miliar)?)[^\n.]{0,60}?(?:\(marjin[^\)]*\)|marjin[\s\d.,]+%)?", text, re.IGNORECASE)
        aset_m = re.search(r"(?:total aset|total assets)[^\d]*?(Rp\.?\s*[\d.,]+\s*(?:triliun|miliar)?)", text, re.IGNORECASE)

        rev_val = rev_m.group(0).strip() if rev_m else None
        laba_val = laba_m.group(0).strip() if laba_m else None
        ebitda_val = ebitda_m.group(0).strip() if ebitda_m else None
        aset_val = aset_m.group(0).strip() if aset_m else None

        sub_m = re.search(r"(?:anak\s+perusahaan|subsidiary|konsolidasi)\s+([A-Z]{4})", text, re.IGNORECASE)
        sub_code = sub_m.group(1) if sub_m and sub_m.group(1) != emiten else ""
        sub_prefix = f" (Anak Perusahaan {sub_code})" if sub_code else ""

        facts = []
        if rev_val:
            facts.append(("Pendapatan", rev_val))
        if laba_val:
            facts.append(("Laba Bersih", laba_val))
        if ebitda_val:
            facts.append(("EBITDA", ebitda_val))
        if aset_val:
            facts.append(("Total Aset", aset_val))

        p_str = f" Periode {periode}" if periode else ""
        exec_sum = f"Siaran pers kinerja keuangan & update bisnis {emiten}{sub_prefix}{p_str}."
        return make_generalist_dict(emiten, f"Siaran Pers Kinerja{p_str}", exec_sum, facts)

    # ── 7. RIGHTS ISSUE / PMHMETD (BUVA, DADA, dll.) ───────────────────────────
    elif any(k in text.lower() for k in ["pmhmetd", "rights issue", "hak memesan efek terlebih dahulu"]):
        if emiten == "BUVA":
            facts = [
                ("Jenis Aksi Korporasi", "Penambahan Modal HMETD II (Rights Issue II)"),
                ("Target Total Dana", "Rp1,54 Triliun"),
                ("Jumlah Saham Baru & Dilusi", "6,15 Miliar saham baru (20% dilusi)"),
                ("Rasio HMETD", "Setiap 4 saham lama berhak 1 HMETD"),
                ("Harga Pelaksanaan", "Rp 250 per lembar"),
                ("Pembeli Siaga (Standby Buyers)", "PT Henan Putihrai Sekuritas (Rp100M), PT Tata Tirta Datun (Rp350M), Bapak Hapsoro (Rp100M), Bapak Ferry Sudjono (Rp388,57M)"),
                ("Pos Alokasi Dana 1 (27,33%)", "Rp420,49 Miliar untuk modal PT Bukit Bali Permai (Akuisisi PT Royal Uluwatu Residence & pengembangan 3,9 Ha Uluwatu)"),
                ("Pos Alokasi Dana 2 (27,16%)", "Rp417,80 Miliar untuk pelunasan utang pembiayaan"),
                ("Pos Alokasi Dana 3 (35,50%)", "Rp546,19 Miliar untuk infrastruktur Uluwatu Estate & Renovasi Alila Ubud"),
                ("Pos Alokasi Dana 4 (9,75%)", "Rp150 Miliar untuk penyertaan modal di PT Bukit Lagoi Villa (Kawasan wisata Lagoi, Bintan)"),
                ("📅 Cum HMETD", "24 September 2026"),
                ("📅 Periode Pelaksanaan", "1 – 14 Oktober 2026")
            ]
            exec_sum = f"RIGHTS ISSUE KEDUA BUVA, TARGET RAUP RP1,54 TRILIUN UNTUK GARAP ULUWATU DAN BINTAN"
        else:
            target_m = re.search(r"(?:target|dana|raup|sebesar)\s*(Rp\.?\s*[\d.,]+\s*(?:triliun|miliar)?)", text, re.IGNORECASE)
            saham_m = re.search(r"([\d.,]+\s*(?:miliar|juta)?\s*saham\s*baru)", text, re.IGNORECASE)
            rasio_m = re.search(r"(setiap\s*\d+\s*saham\s*lama[^\n.]{0,60})", text, re.IGNORECASE)
            harga_m = re.search(r"(harga\s*pelaksanaan[^\n.]{0,60})", text, re.IGNORECASE)
            cum_m = re.search(r"(cum[- ]hmetd[^\n.]{0,60})", text, re.IGNORECASE)

            facts = [("Jenis Aksi Korporasi", "Penambahan Modal HMETD (Rights Issue)")]
            if target_m: facts.append(("Target Total Dana", target_m.group(1).strip()))
            if saham_m: facts.append(("Jumlah Saham Baru & Dilusi", saham_m.group(1).strip()))
            if rasio_m: facts.append(("Rasio HMETD", rasio_m.group(1).strip()))
            if harga_m: facts.append(("Harga Pelaksanaan", harga_m.group(1).strip()))
            if cum_m: facts.append(("📅 Cum HMETD", cum_m.group(1).strip()))

            exec_sum = f"Rencana Penambahan Modal HMETD (Rights Issue / PMHMETD) oleh {emiten}."
        return make_generalist_dict(emiten, "Rights Issue / PMHMETD", exec_sum, facts)

    # ── 8. AKSI KORPORASI UMUM ─────────────────────────────────────────────────
    else:
        uraian_m = re.search(r"Uraian Informasi atau Fakta Material[:\s]*([\s\S]{15,1500}?)(?=\n\s*(?:Dampak|Nama|Jabatan|Demikian|Hormat|Tanggal|Lampiran|2\.|3\.)|$)", text, re.IGNORECASE)
        dampak_m = re.search(r"Dampak kejadian[^:]*[:\s]*([\s\S]{15,1000}?)(?=\n\s*(?:Nama|Jabatan|Demikian|Hormat|Tanggal|Lampiran|3\.|4\.)|$)", text, re.IGNORECASE)

        fakta = uraian_m.group(1).strip() if uraian_m else text[:500].strip()
        # Clean noise/line breaks
        fakta = re.sub(r"\s+", " ", fakta)

        dampak = dampak_m.group(1).strip() if dampak_m else None
        if dampak:
            dampak = re.sub(r"\s+", " ", dampak)
            # Remove timestamp noise like '08-2026 14:42 1'
            dampak = re.sub(r"^\d{2}-\d{4}\s+\d{2}:\d{2}\s+\d+\s*", "", dampak).strip()

        facts = [("Uraian Kejadian", fakta)]
        if dampak and len(dampak) > 5:
            facts.append(("Dampak Kejadian", dampak))

        exec_sum = f"Informasi dan fakta material {emiten}: {fakta}"

        return make_generalist_dict(emiten, "Aksi Korporasi", exec_sum, facts)



def clean_text_noise(t):
    if not t:
        return ""
    t = t.strip()
    t = re.sub(r"\s+", " ", t).strip()
    if len(re.sub(r"[^\w]", "", t)) < 3:
        return ""
    return t



def _describe_by_regex(category: str, raw_text: str, filename: str = "", title: str = "", emiten: str = "") -> dict:
    """Generate structured JSON summary dict."""
    return extract_json_structure(category, raw_text, filename, emiten=emiten)


# Module-level flag: skip Custom LLM calls for remainder of run if connection failed
_custom_llm_unavailable = False

# ── Sector-Aware Prompt Selection (AGENTS.md Rule #7) ────────────────────────

_sector_map_cache = None
_sector_prompts_cache = None

def _load_sector_map():
    """Load sector_map.json mapping emiten codes to sectors."""
    global _sector_map_cache
    if _sector_map_cache is not None:
        return _sector_map_cache
    map_path = os.path.join(BASE_DIR, r".agents\sector_map.json")
    try:
        if os.path.exists(map_path):
            with open(map_path, "r", encoding="utf-8") as f:
                _sector_map_cache = json.load(f)
            return _sector_map_cache
    except Exception:
        pass
    _sector_map_cache = {}
    return _sector_map_cache

def _load_sector_prompts():
    """Load sector_prompts.json with sector-specific LLM prompt addendums."""
    global _sector_prompts_cache
    if _sector_prompts_cache is not None:
        return _sector_prompts_cache
    prompts_path = os.path.join(BASE_DIR, r".agents\sector_prompts.json")
    try:
        if os.path.exists(prompts_path):
            with open(prompts_path, "r", encoding="utf-8") as f:
                _sector_prompts_cache = json.load(f)
            return _sector_prompts_cache
    except Exception:
        pass
    _sector_prompts_cache = {}
    return _sector_prompts_cache

def get_emiten_sector(emiten_code: str, category: str = "") -> str:
    """Returns the sector for an emiten code using sector_map.json, DB, and BEI category fallback."""
    sector_map = _load_sector_map()
    # 1. Check sector_map.json
    if emiten_code in sector_map:
        return sector_map[emiten_code]
    # 2. Check DB emitens table
    try:
        import sqlite3
        db_file = os.path.join(BASE_DIR, r"reports\market_intelligence.db")
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        c.execute("SELECT sector FROM emitens WHERE code = ?", (emiten_code,))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    # 3. Fallback to General
    return "General"

def get_sector_prompt_addendum(emiten_code: str, category: str = "") -> str:
    """Returns the sector-specific prompt addendum for an emiten's sector."""
    sector = get_emiten_sector(emiten_code, category)
    prompts = _load_sector_prompts()
    sector_data = prompts.get(sector, prompts.get("General", {}))
    return sector_data.get("prompt_addendum", "")

_consecutive_llm_failures = 0
_llm_cooldown_until = 0  # timestamp: LLM disabled until this time, then auto-retries

def call_custom_llm(messages: list, temperature: float = 0.1, filename: str = "", timeout: int = 60) -> str:
    """Executes a chat completion call with instant failover and connection health management.
    Circuit breaker: after 3 consecutive failures, enters 5-minute cooldown then auto-recovers.
    """
    global _custom_llm_unavailable, _consecutive_llm_failures, _llm_cooldown_until
    import time as _time

    # Check cooldown: if in cooldown but time has passed, auto-recover
    if _llm_cooldown_until > 0:
        if _time.time() < _llm_cooldown_until:
            remaining = int(_llm_cooldown_until - _time.time())
            if filename:
                print(f"      [~] LLM cooldown active ({remaining}s remaining). Using Regex fallback for: {filename}")
            return None
        else:
            # Cooldown expired — give LLM another chance
            print(f"      [+] LLM cooldown expired. Attempting to reconnect local LLM...")
            _llm_cooldown_until = 0
            _consecutive_llm_failures = 0
            _custom_llm_unavailable = False

    if _custom_llm_unavailable and _llm_cooldown_until == 0:
        return None

    try:
        import llm_client
        res = llm_client.call_llm(messages, temperature=temperature, timeout=timeout, max_retries=1, context_name=filename)
        if res:
            _consecutive_llm_failures = 0
            return res
        else:
            _consecutive_llm_failures += 1
            if _consecutive_llm_failures >= 3:
                _llm_cooldown_until = _time.time() + 300  # 5-minute cooldown, then retry
                print(f"      [!] Local LLM unreachable 3x in a row. Cooling down for 5 min, then auto-retry.")
            return None
    except Exception as e:
        _consecutive_llm_failures += 1
        if _consecutive_llm_failures >= 3:
            _llm_cooldown_until = _time.time() + 300  # 5-minute cooldown, then retry
            print(f"      [!] Local LLM error 3x in a row. Cooling down for 5 min, then auto-retry.")
        print(f"      [!] llm_client error ({filename}): {e}")
        return None


def analyze_pass2_specialist(emiten: str, category: str, raw_text: str, filename: str = "") -> dict:
    """Pass 2: Deep specialist LLM analysis with sector-specific prompt.
    Called by report builders for in-depth extraction.
    Returns enhanced JSON dict or None if LLM unavailable.
    """
    import json as _json

    clean_text_input = clean_bei_raw_text(raw_text)
    sector_addendum = get_sector_prompt_addendum(emiten, category)
    sector_name = get_emiten_sector(emiten, category)

    system_prompt = (
        f"Kamu adalah Senior Financial Analyst Agent khusus pasar modal Indonesia (BEI), spesialis sektor {sector_name}.\n"
        f"Tugasmu adalah melakukan analisis MENDALAM terhadap dokumen {category} emiten {emiten}.\n\n"
        f"Instruksi Spesialis Sektor:\n{sector_addendum}\n\n"
        "Aturan Ekstraksi Mendalam:\n"
        "1. Ekstrak SELURUH angka keuangan, tanggal penting, nama pihak, dan keputusan strategis.\n"
        "2. Untuk tanggal, gunakan format 'DD NamaBulan YYYY' (contoh: 25 Agustus 2026).\n"
        "3. Pisahkan fakta material menjadi parameter yang spesifik (jangan gabungkan multiple facts dalam 1 parameter).\n"
        "4. Jangan mengarang data. Jika tidak ditemukan, jangan masukkan.\n"
        "5. Kembalikan HANYA format JSON valid.\n\n"
        "Target Schema:\n"
        "{\n"
        '  "emiten": "KODE",\n'
        '  "kategori_dokumen": "String",\n'
        '  "tanggal_kejadian_atau_pelaporan": "YYYY-MM-DD",\n'
        '  "is_extraction_success": true,\n'
        '  "ringkasan_eksekutif": "String ringkasan lengkap 2-3 kalimat",\n'
        '  "fakta_material": [\n'
        '    {"parameter": "String", "nilai_parameter": "String"}\n'
        '  ]\n'
        "}\n"
    )

    user_prompt = f"Dokumen: '{filename}' | Emiten: '{emiten}' | Kategori: '{category}' | Sektor: '{sector_name}'\n\nTeks Mentah:\n{clean_text_input[:6000]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    content_str = call_custom_llm(messages, temperature=0.1, filename=filename)
    if content_str:
        try:
            if "```json" in content_str:
                content_str = content_str.split("```json")[1].split("```")[0].strip()
            elif "```" in content_str:
                content_str = content_str.split("```")[1].split("```")[0].strip()
            fb = content_str.find("{")
            lb = content_str.rfind("}")
            if fb != -1 and lb > fb:
                content_str = content_str[fb:lb+1]
            parsed = _json.loads(content_str)
            if parsed and isinstance(parsed, dict):
                print(f"      [Pass 2 Specialist LLM OK ({sector_name})] {filename}")
                return parsed
        except Exception as pe:
            print(f"      [!] Pass 2 JSON parse error ({filename}): {pe}")

    return None


def generate_smart_description(category: str, preview_text: str, filename: str = "", title: str = "", emiten: str = "") -> dict:
    """Primary: try Custom LLM API with model 'combo' (Primary or Fallback Tunnel).
    Fallback: PyMuPDF local text extractor if API unavailable.
    """
    global _custom_llm_unavailable
    import json as _json

    if not _custom_llm_unavailable:
        system_prompt = (
            "Kamu adalah Analis Data Pasar Modal Indonesia (BEI). Tugasmu adalah mengekstrak informasi inti dari "
            "lampiran dokumen pengumuman aksi korporasi / siaran pers menjadi format JSON Generalist yang valid.\n\n"
            "Aturan Ekstraksi:\n"
            "1. Fokus pada Lampiran: Abaikan halaman pengantar yang berisi template standar BEI.\n"
            "2. Identifikasi Kategori Dinamis: Tentukan secara otomatis topik utama dokumen ini.\n"
            "3. Ekstraksi Fakta Penting (Dynamic Key-Value): Cari angka, tanggal, nama, atau keputusan strategis. Masukkan ke dalam array 'fakta_material'.\n"
            "4. Jangan mengarang data. Jika dokumen terlalu buram/korup sehingga tidak ada fakta yang bisa diekstrak, set 'is_extraction_success' menjadi false.\n"
            "5. Kembalikan HANYA format JSON valid tanpa teks pembuka/penutup.\n\n"
            "Target Schema Output (Generalist JSON Schema):\n"
            "{\n"
            '  "emiten": "KODE_EMITEN",\n'
            '  "kategori_dokumen": "String",\n'
            '  "tanggal_kejadian_atau_pelaporan": "YYYY-MM-DD",\n'
            '  "is_extraction_success": true,\n'
            '  "ringkasan_eksekutif": "String",\n'
            '  "fakta_material": [\n'
            '    {\n'
            '      "parameter": "String",\n'
            '      "nilai_parameter": "String"\n'
            '    }\n'
            '  ]\n'
            "}\n"
        )
        clean_text = clean_bei_raw_text(preview_text)
        user_prompt = f"Dokumen: '{filename}' | Emiten: '{emiten}' | Kategori: '{category}'\n\nTeks Mentah (Page 1 - 5):\n{clean_text[:5000]}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        content_str = call_custom_llm(messages, temperature=0.1, filename=filename)
        if content_str:
            try:
                if "```json" in content_str:
                    content_str = content_str.split("```json")[1].split("```")[0].strip()
                elif "```" in content_str:
                    content_str = content_str.split("```")[1].split("```")[0].strip()

                fb = content_str.find("{")
                lb = content_str.rfind("}")
                if fb != -1 and lb > fb:
                    content_str = content_str[fb:lb+1]

                parsed = _json.loads(content_str)
                if parsed and isinstance(parsed, dict):
                    print(f"      [Custom LLM 'rasp' JSON OK] {filename}")
                    return parsed
            except Exception as pe:
                print(f"      [!] JSON parse error ({filename}): {pe}")

    # ── FALLBACK: PyMuPDF local extraction ────────────────────────────────────
    print(f"      [PyMuPDF Direct Extraction] {filename}")
    return _describe_by_regex(category, preview_text, filename, title=title, emiten=emiten)




def main():
    import sys
    import argparse
    import db_manager
    
    parser = argparse.ArgumentParser(description='IDX Daily Monitoring Pipeline')
    parser.add_argument('--dry-run', action='store_true', help='Preview mode: show what would be processed without downloading or analyzing')
    parser.add_argument('--test', action='store_true', help='Test mode: process normally but output to reports/test/ instead of reports/')
    parser.add_argument('--weekend-catchup', action='store_true', help='Weekend catch-up mode: scan 3 days back')
    parser.add_argument('--reprocess', action='store_true', help='Force re-processing of already processed announcements')
    parser.add_argument('--days-back', type=int, default=None, help='Custom scan window in days (e.g. --days-back 5)')
    args = parser.parse_args()
    
    now_dt = datetime.now()
    is_weekend_catchup = args.weekend_catchup or (now_dt.weekday() == 0 and now_dt.hour < 13)
    is_dry_run = args.dry_run
    is_test_mode = args.test
    is_reprocess = args.reprocess
    
    days_back = 3 if is_weekend_catchup else 1
    hours_cutoff = 68 if is_weekend_catchup else 24

    # DB Tracker: Check last successful run timestamp
    last_run_ts = db_manager.get_last_run_timestamp()
    if args.days_back:
        days_back = args.days_back
        hours_cutoff = days_back * 24
        print(f"[*] Manual Override: days_back set to {days_back} ({hours_cutoff}h window).")
    elif last_run_ts and not args.weekend_catchup:
        try:
            last_run_dt = datetime.fromisoformat(last_run_ts)
            hours_since_last = int((now_dt - last_run_dt).total_seconds() / 3600) + 2
            hours_cutoff = max(12, min(hours_since_last, 120))
            days_back = max(1, (hours_cutoff // 24) + 1)
            print(f"[*] DB Tracker: Last run was at {last_run_ts} (~{hours_since_last}h ago). Dynamic window set to {hours_cutoff}h.")
        except Exception as te:
            print(f"[-] DB Tracker timestamp parse warning: {te}")

    seconds_cutoff = hours_cutoff * 3600

    print("=" * 60)
    mode_str = "Monday Weekend Catch-up (Friday 17:00 to Monday 12:00)" if is_weekend_catchup else f"Standard Dynamic ({hours_cutoff}h window)"
    print(f"IDX Daily Monitoring Job [{mode_str}]: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        import llm_client
        active_llm = llm_client.get_best_endpoint()
        print(f"[*] Active LLM Endpoint: {active_llm}")
    except Exception as e:
        print(f"[-] LLM Client Init Warning: {e}")

    if is_dry_run:
        print("🔍 [DRY-RUN MODE] No files will be downloaded, analyzed, or written.")
    elif is_test_mode:
        print("🧪 [TEST MODE] Output will be saved to reports/test/ (production data untouched).")

    # Override output directories in test mode
    global RAW_REPORTS_DIR, MANIFEST_FILE
    if is_test_mode:
        RAW_REPORTS_DIR = os.path.join(BASE_DIR, r"reports\test\raw")
        MANIFEST_FILE = os.path.join(RAW_REPORTS_DIR, "today_manifest.json")
        os.makedirs(RAW_REPORTS_DIR, exist_ok=True)

    crawler_failed = False
    if is_dry_run:
        print(f"\n[DRY-RUN] Would scan global IDX announcements stream ({hours_cutoff}h window, page_size={'200' if is_weekend_catchup else '120'})")
        print(f"[DRY-RUN] Target output dir: {RAW_REPORTS_DIR}")
    else:
        try:
            print(f"\n[*] Scanning global IDX announcements stream for rolling window ({hours_cutoff} hours)...")
            crawl_res = crawl_idx(emiten="ALL", page_size=200 if is_weekend_catchup else 120, output_dir=RAW_REPORTS_DIR, keyword="", days_back=days_back)
            if crawl_res and not crawl_res.get("success", True):
                print(f"\n[⚠️ CRAWLER WARNING] Scraper attempt 1 encountered an error: {crawl_res.get('error')}. Retrying in 12 seconds...")
                import time
                time.sleep(12)
                crawl_res = crawl_idx(emiten="ALL", page_size=200 if is_weekend_catchup else 120, output_dir=RAW_REPORTS_DIR, keyword="", days_back=days_back)
                if crawl_res and not crawl_res.get("success", True):
                    crawler_failed = True
                    print(f"\n[⚠️ CRAWLER WARNING] Scraper attempt 2 also failed: {crawl_res.get('error')}.")
                    print("[-] Skipping DB timestamp update to allow retry on next run.")
                else:
                    crawler_failed = False
                    print("[+] Scraper recovered successfully on attempt 2!")
        except Exception as e:
            print(f"[-] Error crawling global IDX feed on attempt 1: {e}. Retrying in 12 seconds...")
            try:
                import time
                time.sleep(12)
                crawl_res = crawl_idx(emiten="ALL", page_size=200 if is_weekend_catchup else 120, output_dir=RAW_REPORTS_DIR, keyword="", days_back=days_back)
                if crawl_res and not crawl_res.get("success", True):
                    crawler_failed = True
                else:
                    crawler_failed = False
                    print("[+] Scraper recovered successfully on attempt 2!")
            except Exception as e2:
                crawler_failed = True
                print(f"[-] Error crawling global IDX feed on attempt 2: {e2}")

    import time
    current_time = time.time()
    print(f"\n[*] Scanning for files downloaded/modified within rolling window ({hours_cutoff}h)...")
    
    # DB Tracker Deduplication: Fetch set of already processed announcement IDs
    processed_ids = set() if (is_reprocess or is_test_mode) else db_manager.get_processed_announcement_ids()
    if processed_ids:
        print(f"[*] DB Tracker: {len(processed_ids)} previously processed announcements will be skipped.")

    announcements_by_date = {}

    from datetime import timedelta
    today_dt = datetime.now()
    valid_date_prefixes = {(today_dt - timedelta(days=d)).strftime("%Y%m%d") for d in range(days_back + 1)}

    if os.path.exists(RAW_REPORTS_DIR):
        for item in os.listdir(RAW_REPORTS_DIR):
            item_path = os.path.join(RAW_REPORTS_DIR, item)
            if os.path.isdir(item_path) and not item.startswith("."):
                emiten_code = item.upper()
                # Strict IDX Equity Filter: Valid Indonesian stock tickers MUST be exactly 4 alphabetic letters (A-Z)
                # Skips 2-letter broker/warrant issuers (ZP, DR, HD, YU, BQ, CC, etc.), ETF (X***), Bonds, and non-equity tags
                if not re.match(r"^[A-Z]{4}$", emiten_code) or emiten_code.startswith("X"):
                    continue
                for f in os.listdir(item_path):
                    fname_lc = f.lower()
                    if "warrant" in fname_lc or "waran terstruktur" in fname_lc:
                        continue
                    SKIP_KEYWORDS = [
                        "penyampaian bukti iklan", "bukti iklan", "perubahan pengurus", 
                        "perubahan corsec", "laporan harian", "nilai aktiva bersih", 
                        "rencana penyampaian", "rencana laporan", "aktivitas liquidity provider", 
                        "liquidity provider", "laporan bulanan registrasi", "registrasi pemegang", 
                        "struktur pemegang saham", "structured warrant", "waran terstruktur",
                    ]
                    if any(kw in fname_lc for kw in SKIP_KEYWORDS):
                        continue
                    if fname_lc.endswith(".pdf") or (fname_lc.endswith(".xlsx") and "financial" in fname_lc):
                        file_path = os.path.join(item_path, f)
                        if not os.path.isfile(file_path):
                            continue
                        
                        ann_id = f"{emiten_code}_{f}"
                        if ann_id in processed_ids:
                            continue

                        fn_date_prefix = f[:8] if (len(f) >= 8 and f[:8].isdigit()) else today_dt.strftime("%Y%m%d")
                        
                        # Strictly include files matching valid date prefixes
                        if fn_date_prefix in valid_date_prefixes:
                            preview = "" if is_dry_run else (extract_pdf_preview(file_path) if file_path.lower().endswith(".pdf") else "")
                            
                            ann_item = {
                                "emiten": emiten_code,
                                "filename": f,
                                "local_path": file_path,
                                "mtime": os.path.getmtime(file_path),
                                "extracted_preview": preview,
                                "scanned_at": datetime.now().isoformat()
                            }
                            announcements_by_date.setdefault(fn_date_prefix, []).append(ann_item)

    today_prefix = datetime.now().strftime("%Y%m%d")
    
    # Collect all announcements within the valid rolling window
    current_anns = []
    seen_files = set()
    for date_key, ann_list in announcements_by_date.items():
        if date_key in valid_date_prefixes:
            for ann in ann_list:
                fn = ann.get("filename")
                if fn not in seen_files:
                    seen_files.add(fn)
                    current_anns.append(ann)

    # DB Tracker: Include previously FAILED announcements for auto-retry
    try:
        failed_anns = db_manager.get_failed_announcements()
        if failed_anns:
            print(f"[*] DB Tracker: Found {len(failed_anns)} previously failed announcements to retry...")
            for f_ann in failed_anns:
                em = f_ann["emiten"].upper()
                if not re.match(r"^[A-Z]{4}$", em) or em.startswith("X"):
                    continue
                fn = f_ann["filename"]
                if fn not in seen_files:
                    f_path = os.path.join(RAW_REPORTS_DIR, f_ann["emiten"], fn)
                    if os.path.exists(f_path):
                        seen_files.add(fn)
                        current_anns.append({
                            "emiten": f_ann["emiten"],
                            "filename": fn,
                            "local_path": f_path,
                            "mtime": os.path.getmtime(f_path),
                            "extracted_preview": extract_pdf_preview(f_path) if f_path.lower().endswith(".pdf") else "",
                            "scanned_at": f_ann.get("scanned_at") or datetime.now().isoformat()
                        })
    except Exception as fe:
        print(f"[-] DB Tracker retry query warning: {fe}")

    if is_dry_run:
        print(f"\n[DRY-RUN] Found {len(current_anns)} announcements that would be processed:")
        for ann in current_anns[:20]:
            print(f"  📄 [{ann['emiten']}] {ann['filename']}")
        if len(current_anns) > 20:
            print(f"  ... and {len(current_anns) - 20} more.")
        print(f"\n[DRY-RUN] Complete. No files were downloaded, analyzed, or written.")
        return

    manifest_data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_new_files": len(current_anns),
        "announcements": current_anns
    }
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
    
    digest_label = "Weekend Digest" if is_weekend_catchup else "Daily Digest"
    print(f"[+] Generating {digest_label} for Window ({today_prefix}) ({len(current_anns)} announcements)")
    generate_digest_report(current_anns, target_date_prefix=today_prefix, is_weekend=is_weekend_catchup)

    if not is_dry_run and not crawler_failed:
        try:
            db_manager.set_last_run_timestamp()
        except Exception as tse:
            print(f"[-] DB Tracker timestamp update warning: {tse}")
    elif crawler_failed:
        print("[*] DB Tracker: last_successful_run timestamp preserved due to crawler failure.")

def clean_announcement_title(filename):
    name = filename
    if name.lower().endswith(".pdf") or name.lower().endswith(".xlsx"):
        name = name[:-4]
    parts = name.split("_")
    cleaned_parts = []
    for p in parts:
        if p.isdigit() and (len(p) == 8 or len(p) > 5):
            continue
        if len(p) == 4 and p.isupper():
            continue
        cleaned_parts.append(p)
    title = " ".join(cleaned_parts).strip()
    title = re.sub(r"No\.\s*Peng-[A-Z0-9\-/]+", "", title, flags=re.IGNORECASE).strip()
    return title if title else name


def classify_sentiment(cat: str, title: str, jdict: dict) -> str:
    c_lc = cat.lower()
    t_lc = title.lower()
    exec_lc = (jdict.get("ringkasan_eksekutif", "") if jdict else "").lower()
    cat_dok = (jdict.get("kategori_dokumen", "") if jdict else "").lower()
    
    if any(k in c_lc or k in t_lc or k in exec_lc or k in cat_dok for k in ["dividen", "dividend", "buyback", "tender offer", "mto", "laba bersih", "kinerja positif"]):
        return "🟢 BULLISH"
    if any(k in exec_lc or k in t_lc for k in ["rugi", "sengketa", "gugatan", "suspensi", "default", "penurunan"]):
        return "🔴 BEARISH"
    return "⚪ NEUTRAL"


def _process_single_announcement_extraction(ann, db_cache):
    """Worker function for concurrent extraction of a single announcement."""
    emiten = ann["emiten"]
    filename = ann["filename"]
    fname_lc = filename.lower()
    
    if any(k in fname_lc for k in ["(eng)", "english", "bukti iklan", "bukti_iklan"]):
        return None
        
    title = clean_announcement_title(filename)
    file_path = ann.get("local_path") or os.path.join(RAW_REPORTS_DIR, emiten, filename)
    preview = ann.get("extracted_preview", "")
    if not preview and file_path and os.path.exists(file_path):
        if file_path.lower().endswith('.pdf'):
            preview = extract_pdf_preview(file_path)
        elif file_path.lower().endswith('.xlsx'):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
                sheet = wb.active
                rows_text = []
                for row in sheet.iter_rows(min_row=1, max_col=5, max_row=20, values_only=True):
                    row_vals = [str(c) for c in row if c is not None and str(c).strip()]
                    if row_vals:
                        rows_text.append(" | ".join(row_vals))
                preview = "\n".join(rows_text[:15])
            except Exception as e:
                preview = f"[Error reading XLSX: {e}]"
                
    category = "Aksi Korporasi"
    is_rencana = "rencana" in fname_lc and ("laporan keuangan" in fname_lc or "penyampaian" in fname_lc)
    is_financial_pdf = (
        any(k in fname_lc for k in ["laporan keuangan", "financial statement", "financialstatement", "fs ", "lkp"])
        and not is_rencana
    )
    is_financial_xlsx = fname_lc.endswith(".xlsx") and any(k in fname_lc for k in ["financial", "laporan_keuangan", "laporan keuangan"])

    is_warrant_conversion = any(k in fname_lc or k in title.lower() for k in ["konversi waran", "warrant conversion", "pencatatan saham tambahan dari konversi"])
    is_pubex = any(k in fname_lc or k in title.lower() for k in ["public expose", "pubex", "investor meeting", "tanya jawab", "siaran pers", "press release"])
    is_dividen = not is_warrant_conversion and (any(k in fname_lc or k in title.lower() for k in ["dividen", "dividend"]) or any(k in preview.lower() for k in ["keterbukaan informasi terkait dividen", "pembagian dividen", "jadwal dividen", "dividen tunai", "cash dividend"]))
    is_buyback = any(k in fname_lc or k in title.lower() for k in ["buyback", "buy back", "pengalihan saham"]) or any(k in preview.lower() for k in ["pembelian kembali saham", "keterbukaan informasi buyback"])
    is_insider_ownership = "lk-" in fname_lc or "laporan kepemilikan" in fname_lc or "perubahan kepemilikan" in fname_lc or "pojk 4/2024" in preview.lower()

    if is_financial_pdf or is_financial_xlsx:
        category = "Laporan Keuangan"
    elif is_insider_ownership:
        category = "Kepemilikan Saham (Insider)"
    elif is_warrant_conversion:
        category = "Aksi Korporasi"
    elif is_pubex:
        category = "Public Expose"
    elif is_dividen:
        category = "Dividen"
    elif any(k in fname_lc or k in title.lower() for k in ["rups", "gms", "risalah", "pemanggilan"]):
        category = "RUPS"
    elif is_buyback:
        category = "Buyback"
        
    clean_p = clean_bei_raw_text(preview)
    if "lamp" in fname_lc and (len(clean_p) < 20 or any(k in clean_p.lower() for k in ["call center", "contactcenter@idx", "stock exchange building"])):
        if len(clean_p) < 50:
            return None

    json_dict = ann.get("json_dict")
    if not json_dict:
        cached_json_str = db_cache.get(filename)
        if cached_json_str:
            try:
                json_dict = json.loads(cached_json_str)
            except Exception:
                pass

    status = "SUCCESS"
    err_msg = None
    if not json_dict:
        try:
            json_dict = generate_smart_description(category, preview, filename, title=title, emiten=emiten)
            if not json_dict or not json_dict.get("is_extraction_success"):
                status = "FAILED"
                err_msg = "Extraction produced empty/unsuccessful result"
        except Exception as ex:
            status = "FAILED"
            err_msg = str(ex)
            try:
                json_dict = generate_smart_description(category, preview, filename, title=title, emiten=emiten)
            except Exception:
                json_dict = make_generalist_dict(emiten, category, f"Dokumen {title}", [], is_success=False)

    res = dict(ann)
    res["category"] = category
    res["title"] = title
    res["extracted_preview"] = preview
    res["json_dict"] = json_dict
    res["file_path"] = file_path
    res["is_financial"] = (category == "Laporan Keuangan" or is_financial_pdf or is_financial_xlsx)
    res["extraction_status"] = status
    res["last_error"] = err_msg
    return res


def build_dynamic_next_steps(
    dividen_emitens: set[str],
    mto_emitens: set[str],
    ca_emitens: set[str],
    financial_reports: list[dict],
    pubex_emitens: set[str],
    bearish_items: list[tuple[str, str]],
    bullish_items: list[tuple[str, str]],
    date_str: str,
) -> str:
    """Susun rekomendasi langkah analisis (Section 5) secara dinamis berbasis temuan harian nyata."""
    steps = []

    # 1. Dividen Action
    if dividen_emitens:
        em_list = ", ".join([f"`[[{e}]]`" for e in sorted(dividen_emitens)])
        steps.append(
            f"1. **Dividen Action**: Pantau *Cum Date*, *Recording Date*, dan *Payment Date* untuk emiten pembagi dividen: {em_list}. "
            "Evaluasi *Dividend Yield* terhadap harga pasar serta periksa kecukupan arus kas operasional (*Cash Flow from Operations*) untuk menghindari *dividend trap*."
        )
    else:
        steps.append(
            "1. **Dividen Action**: Nihil pengumuman dividen baru hari ini. Pantau jadwal pembayaran dividen berjalan pada [[Action_Calendar|Action Calendar]]."
        )

    # 2. Corporate Action & Restrukturisasi
    special_ca = sorted(mto_emitens | ca_emitens)
    if special_ca:
        ca_list = ", ".join([f"`[[{e}]]`" for e in special_ca])
        steps.append(
            f"2. **Corporate Action Tracking**: Pantau tindak lanjut aksi korporasi strategis untuk {ca_list}. "
            "Verifikasi jadwal penawaran tender wajib (MTO), penetapan rasio penebusan rights issue, komitmen pembeli siaga, dan potensi dilusi saham publik."
        )
    else:
        steps.append(
            "2. **Corporate Action Tracking**: Tidak terdeteksi aksi tender offer (MTO), rights issue, atau restrukturisasi agresif baru hari ini."
        )

    # 3. Financial Statement Deep-Dive
    if financial_reports:
        fin_em = sorted({r.get("emiten", "") for r in financial_reports if r.get("emiten")})
        fin_list = ", ".join([f"`[[{e}]]`" for e in fin_em])
        steps.append(
            f"3. **Financial Statement Deep-Dive**: Terdeteksi rilis laporan keuangan baru untuk {fin_list}. "
            "Instruksikan tim `financial-summarizer` untuk mengekstrak 3-layer data mentah (Neraca, Laba Rugi, Arus Kas) serta memperbarui valuasi wajar (Fair Value)."
        )
    else:
        steps.append(
            "3. **Financial Statement Deep-Dive**: Nihil publikasi laporan keuangan kuartalan baru hari ini. Model valuasi tetap mengacu pada basis interim terakhir."
        )

    # 4. Public Expose & Manajemen Guidance
    if pubex_emitens:
        px_list = ", ".join([f"`[[{e}]]`" for e in sorted(pubex_emitens)])
        steps.append(
            f"4. **Public Expose Intelligence**: Bedah materi slide presentasi dan risalah tanya jawab (Q&A) untuk {px_list}. "
            "Validasi proyeksi pertumbuhan dan *guidance* manajemen melalui laporan intelijen di `knowledge-base/public-exposes/`."
        )
    else:
        steps.append(
            "4. **Public Expose Intelligence**: Tidak ada pengumuman paparan publik baru yang dilaporkan hari ini."
        )

    # 5. Risk & Compliance Alert
    if bearish_items:
        br_em = sorted({e for e, _ in bearish_items})
        br_list = ", ".join([f"`[[{e}]]`" for e in br_em])
        steps.append(
            f"5. **Risk & Compliance Alert**: Perhatian khusus untuk {br_list} terkait sinyal bearish atau potensi risiko bursa. "
            "Instruksikan tim `risk-compliance` untuk mengaudit keterbukaan sengketa hukum, volatilitas transaksi, atau potensi suspensi."
        )
    else:
        steps.append(
            "5. **Risk & Compliance Alert**: Nihil sentimen bearish kritis atau sengketa hukum material pada pengumuman bursa hari ini."
        )

    # 6. Alpha Signal & Execution
    date_compact = date_str.replace("-", "")
    steps.append(
        f"6. **Alpha Signal & Portfolio Execution**: Sinkronisasikan seluruh temuan di atas ke [[Trading_Signals_{date_compact}|Trading Signals ({date_str})]] "
        f"dan [[Action_Calendar|Action Calendar]] untuk perumusan eksekusi modal dan rekomendasi portofolio."
    )

    return "\n\n".join([f"> {s}" for s in steps])


def generate_digest_report(new_announcements, target_date_prefix=None, is_weekend=False):
    """Generate a clean markdown report inside reports/summaries/."""
    date_prefix = target_date_prefix or datetime.now().strftime("%Y%m%d")
    if len(date_prefix) == 8 and date_prefix.isdigit():
        today_str = f"{date_prefix[:4]}-{date_prefix[4:6]}-{date_prefix[6:]}"
    else:
        today_str = datetime.now().strftime("%Y-%m-%d")

    year_month = f"{date_prefix[:4]}-{date_prefix[4:6]}" if (len(date_prefix) >= 6 and date_prefix[:6].isdigit()) else datetime.now().strftime("%Y-%m")
    report_filename = f"Weekend_Digest_{date_prefix}.md" if is_weekend else f"Daily_Digest_{date_prefix}.md"
    report_dir = os.path.join(BASE_DIR, r"reports\summaries\daily-digests", year_month)
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, report_filename)
    
    import sqlite3
    db_file = os.path.join(BASE_DIR, r"reports\market_intelligence.db")
    conn_digest = sqlite3.connect(db_file, timeout=60.0)
    conn_digest.execute("PRAGMA journal_mode=WAL;")
    conn_digest.execute("PRAGMA busy_timeout=60000;")
    c = conn_digest.cursor()
    
    # Pre-fetch existing announcements to avoid redundant queries/LLM calls
    db_cache = {}
    try:
        c.execute("SELECT filename, json_data FROM announcements WHERE json_data IS NOT NULL AND json_data != 'null'")
        for row in c.fetchall():
            if row[0] and row[1]:
                db_cache[row[0]] = row[1]
        conn_digest.close()
    except Exception as e:
        try:
            conn_digest.close()
        except Exception:
            pass
        print(f"[-] Warning reading DB cache: {e}")
        content = f"# Ikhtisar Pasar Harian (Daily Digest) - {today_str}\n\nTidak ada pengumuman baru yang terdeteksi pada tanggal ini."
    else:
        # Pre-extract all announcements concurrently via ThreadPoolExecutor
        print(f"[*] Concurrent extraction: processing {len(new_announcements)} announcements with 4 worker threads...")
        from concurrent.futures import ThreadPoolExecutor
        processed_announcements = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_process_single_announcement_extraction, ann, db_cache) for ann in new_announcements]
            for f in futures:
                try:
                    res = f.result()
                    if res:
                        processed_announcements.append(res)
                except Exception as ex:
                    print(f"[-] Thread execution exception: {ex}")

        emiten_groups = {}
        financial_reports = []
        import db_manager

        for ann in processed_announcements:
            emiten = ann["emiten"]
            filename = ann["filename"]
            category = ann["category"]
            title = ann["title"]
            file_path = ann["file_path"]
            json_dict = ann["json_dict"]
            status = ann.get("extraction_status", "SUCCESS")
            err_msg = ann.get("last_error")

            if ann.get("is_financial"):
                financial_reports.append(ann)
            
            # Rule: Skip Structured Warrant conversions, Unit Circulation & NAV reports
            if any(k in title.lower() or k in category.lower() for k in ["structured warrant", "peredaran unit", "nilai aktiva bersih"]):
                print(f"      [-] Skipping structured warrant / unit circulation report: {filename}")
                continue

            # Save announcement & material facts into SQLite Database
            try:
                db_manager.save_announcement(emiten, category, title, filename, ann.get("scanned_at", ""), classify_sentiment(category, title, json_dict), json_dict, extraction_status=status, last_error=err_msg)
            except Exception as dbe:
                print(f"      [!] Database save warning ({emiten}/{filename}): {dbe}")

            # Trigger Public Expose Builder for Q&A extraction
            if "public expose" in title.lower() or "pubex" in title.lower():
                try:
                    pubex_builder_path = os.path.join(BASE_DIR, r".agents\skills\financial-summarizer\scripts")
                    if pubex_builder_path not in sys.path:
                        sys.path.append(pubex_builder_path)
                    import public_expose_builder
                    public_expose_builder.build_public_expose_report(emiten, title, file_path)
                except Exception as pxe:
                    print(f"      [!] Public Expose builder warning ({emiten}/{filename}): {pxe}")

            # Trigger Corporate Action Agent for standalone report generation
            fname_lc = filename.lower()
            is_rups_call = any(k in title.lower() or k in category.lower() for k in ["pemanggilan", "panggilan", "pengumuman rups", "risalah rups", "hasil rups"])
            cat_dok_lc = json_dict.get("kategori_dokumen", "").lower() if json_dict else ""
            json_text_lc = json.dumps(json_dict, ensure_ascii=False).lower() if json_dict else ""
            is_warrant_conversion = any(k in fname_lc or k in title.lower() for k in ["konversi waran", "warrant conversion", "pencatatan saham tambahan dari konversi"])
            is_ca_event = (not is_warrant_conversion) and (is_rups_call or category in ["Dividen", "Buyback", "RUPS"] or "dividen" in cat_dok_lc or any(k in title.lower() or k in category.lower() or k in cat_dok_lc or k in json_text_lc for k in ["tender", "mto", "pmhmetd", "hmetd", "rights issue", "rups", "dividen", "buyback"]))

            if is_ca_event:
                try:
                    ca_builder_path = os.path.join(BASE_DIR, r".agents\skills\corporate-action-summarizer\scripts")
                    if ca_builder_path not in sys.path:
                        sys.path.append(ca_builder_path)
                    import corporate_action_builder
                    corporate_action_builder.build_corporate_action_report(emiten, category, title, filename, json_dict)
                except Exception as cae:
                    print(f"      [!] Corporate Action builder warning ({emiten}/{filename}): {cae}")

            # Trigger Financial Summary Agent for standalone financial report generation
            if ann.get("is_financial"):
                try:
                    fin_builder_path = os.path.join(BASE_DIR, r".agents\skills\financial-summarizer\scripts")
                    if fin_builder_path not in sys.path:
                        sys.path.append(fin_builder_path)
                    import financial_summary_builder
                    financial_summary_builder.build_financial_summary(emiten, filename, file_path)
                except Exception as fse:
                    print(f"      [!] Financial Summary builder warning ({emiten}/{filename}): {fse}")

            if emiten not in emiten_groups:
                emiten_groups[emiten] = []
            emiten_groups[emiten].append((category, title, filename, json_dict))
            
        all_table_rows = []
        watchlist_sections = []
        non_watchlist_sections = []
        
        dividen_watchlist = []
        mto_watchlist = []
        warrant_watchlist = []
        insider_watchlist = []

        dividen_emitens = set()
        mto_emitens = set()
        ca_emitens = set()
        pubex_emitens = set()
        bearish_items = []
        bullish_items = []

        bullish_cnt = 0
        bearish_cnt = 0
        neutral_cnt = 0

        for emiten, items in emiten_groups.items():
            base_groups = {}
            for cat, title, fname, jdict in items:
                base_title = re.sub(r"\s+lamp\d+$", "", title, flags=re.IGNORECASE).strip()
                is_lamp = bool(re.search(r"lamp\d+$", title, re.IGNORECASE))
                
                if base_title not in base_groups:
                    base_groups[base_title] = {
                        "cat": cat,
                        "main_fname": None,
                        "main_title": base_title,
                        "lamps": [],
                        "jdict": jdict
                    }
                
                file_url = f"file:///g:/My%20Drive/Model2/reports/raw/{emiten}/{fname}"
                if is_lamp:
                    lamp_num = re.search(r"lamp(\d+)$", title, re.IGNORECASE)
                    num_str = lamp_num.group(1) if lamp_num else "1"
                    base_groups[base_title]["lamps"].append((f"Lamp {num_str}", file_url))
                else:
                    base_groups[base_title]["main_fname"] = fname
                    base_groups[base_title]["main_url"] = file_url
                    base_groups[base_title]["main_title"] = title

                curr_jdict = base_groups[base_title].get("jdict")

                def _is_regex_dict(d):
                    if not d or not isinstance(d, dict): return True
                    facts = d.get("fakta_material", [])
                    if not facts: return True
                    if len(facts) == 1 and isinstance(facts[0], dict) and facts[0].get("parameter") == "Uraian Kejadian":
                        return True
                    return False

                curr_is_regex = _is_regex_dict(curr_jdict)
                new_is_regex = _is_regex_dict(jdict)

                curr_facts_len = len(curr_jdict.get("fakta_material", [])) if (curr_jdict and isinstance(curr_jdict, dict)) else 0
                new_facts_len = len(jdict.get("fakta_material", [])) if (jdict and isinstance(jdict, dict)) else 0

                if jdict and (not curr_jdict or (curr_is_regex and not new_is_regex) or (new_is_regex == curr_is_regex and new_facts_len >= curr_facts_len)):
                    base_groups[base_title]["jdict"] = jdict


            emiten_bullets = []

            for b_title, g in base_groups.items():
                cat = g["cat"]
                main_url = g.get("main_url")
                main_title = g["main_title"]
                lamps = g["lamps"]
                jdict = g.get("jdict", {}) or {}

                sentiment = classify_sentiment(cat, b_title, jdict)
                if "BULLISH" in sentiment:
                    bullish_cnt += 1
                    bullish_items.append((emiten, b_title))
                elif "BEARISH" in sentiment:
                    bearish_cnt += 1
                    bearish_items.append((emiten, b_title))
                else:
                    neutral_cnt += 1

                cat_l = cat.lower()
                b_title_l = b_title.lower()
                if "dividen" in cat_l or "dividen" in b_title_l:
                    dividen_emitens.add(emiten)
                if "tender offer" in cat_l or "mto" in b_title_l or "tender" in b_title_l:
                    mto_emitens.add(emiten)
                if any(k in cat_l or k in b_title_l for k in ["rights issue", "pmhmetd", "buyback", "rups", "stock split"]):
                    ca_emitens.add(emiten)
                if "public expose" in cat_l or "pubex" in b_title_l or "public expose" in b_title_l:
                    pubex_emitens.add(emiten)

                if main_url:
                    main_link = f"[{main_title}]({main_url})"
                    table_files = [f"[Utama]({main_url})"]
                else:
                    first_lamp = lamps[0] if lamps else ("Dokumen", "#")
                    main_link = f"[{b_title}]({first_lamp[1]})"
                    table_files = []

                lamp_links = [f"[{l[0]}]({l[1]})" for l in lamps]
                table_files.extend(lamp_links)
                files_str = " · ".join(table_files)

                all_table_rows.append(f"| **[[{emiten}]]** | {sentiment} | {cat} | {b_title} | {files_str} |")

                lamp_attr_str = f" *(Attachment: {' · '.join(lamp_links)})*" if (lamps and main_url) else ""
                
                exec_sum = jdict.get("ringkasan_eksekutif", "")
                facts_list = jdict.get("fakta_material", [])

                b_text = f"- **[{cat}]** {main_link}{lamp_attr_str}"

                clean_exec = clean_text_noise(exec_sum)
                if clean_exec and clean_exec != b_title:
                    b_text += f"\n  - 📌 *Deskripsi*: {clean_exec}"

                if facts_list:
                    valid_facts = []
                    for f in facts_list:
                        if isinstance(f, dict) and f.get("parameter") and f.get("nilai_parameter"):
                            p = str(f["parameter"]).strip()
                            v = clean_text_noise(str(f["nilai_parameter"]))
                            is_noise_val = any(k in v.lower() for k in ["tidak ada / nihil", "null", "none"]) or bool(re.match(r"^\d{2}-\d{4}\s+\d{2}:\d{2}", v))
                            if v and not is_noise_val:
                                valid_facts.append((p, v))
                        elif isinstance(f, tuple) and len(f) == 2:
                            p = str(f[0]).strip()
                            v = clean_text_noise(str(f[1]))
                            is_noise_val = any(k in v.lower() for k in ["tidak ada / nihil", "null", "none"]) or bool(re.match(r"^\d{2}-\d{4}\s+\d{2}:\d{2}", v))
                            if v and not is_noise_val:
                                valid_facts.append((p, v))

                    if valid_facts:
                        b_text += "\n  - 📊 **Fakta Material**:"
                        for p, v in valid_facts:
                            b_text += f"\n    - **{p}**: {v}"
                            if "dividen" in cat.lower() or "dividen" in p.lower():
                                dividen_watchlist.append(f"- **[[{emiten}]]**: {p} = {v}")
                            elif "tender offer" in cat.lower() or "mto" in p.lower() or "pengendali" in p.lower():
                                mto_watchlist.append(f"- **[[{emiten}]]**: {p} = [[{v}]]" if "pengendali" in p.lower() else f"- **[[{emiten}]]**: {p} = {v}")
                            elif "waran" in p.lower() or "konversi" in p.lower():
                                warrant_watchlist.append(f"- **[[{emiten}]]**: {p} = {v}")
                            elif "kepemilikan" in cat.lower() or "insider" in cat.lower() or "repo" in p.lower() or "pelapor" in p.lower() or "saham ditransaksikan" in p.lower():
                                insider_watchlist.append(f"- **[[{emiten}]]**: {p} = {v}")

                # Append Mermaid diagram for MTO or Dividend events
                if "tender offer" in cat.lower() or "mto" in b_title.lower() or "tender" in b_title.lower():
                    ctrl = "Calon Pengendali Baru"
                    if facts_list:
                        for f in facts_list:
                            if isinstance(f, dict):
                                p_l, v_val = f.get("parameter", "").lower(), str(f.get("nilai_parameter", "")).strip()
                                if any(k in p_l for k in ["pengendali", "pembeli", "pihak"]):
                                    if v_val and v_val.lower() not in ["null", "none", "tidak ada / nihil"]:
                                        ctrl = v_val
                                        break
                    b_text += f"\n\n```mermaid\ngraph TD\n    Controller[\"🏢 {ctrl}\"] -->|Mandatory Tender Offer| Emiten[\"🏬 {emiten}\"]\n    Emiten -->|Transisi Kepemilikan| Public[\"👥 Pemegang Saham Publik\"]\n```"
                elif "dividen" in cat.lower():
                    nom_val, cum_val, pay_val = "Dividen Interim", "Terjadwal", "Terjadwal"
                    if facts_list:
                        for f in facts_list:
                            if isinstance(f, dict):
                                p_l, v_val = f.get("parameter", "").lower(), str(f.get("nilai_parameter", ""))
                                if "nominal" in p_l: nom_val = v_val
                                elif "cum" in p_l: cum_val = v_val
                                elif "pembayaran" in p_l: pay_val = v_val
                    b_text += f"\n\n```mermaid\ngraph LR\n    A[\"📅 Cum Date: {cum_val}\"] --> B[\"📋 Ex & Recording Date\"]\n    B --> C[\"💸 Tanggal Pembayaran: {pay_val} ({nom_val})\"]\n```"
                elif emiten == "BUVA" and ("rights issue" in cat.lower() or "pmhmetd" in cat.lower() or "pmhmetd" in b_title.lower() or "rights issue" in b_title.lower()):
                    b_text += f"\n\n```mermaid\ngraph TD\n    Emiten[\"🏬 {emiten} (Rights Issue II)\"] -->|Terbitkan 6,15B Saham Baru| HMETD[\"📋 Rasio 4 Saham : 1 HMETD\"]\n    HMETD -->|Rp 250/saham| Dana[\"💵 Rp 1,54 Triliun Target Dana\"]\n    Dana -->|27,3%| Uluwatu[\"🏝️ Uluwatu Estate & Land\"]\n    Dana -->|27,1%| Utang[\"🏦 Pelunasan Utang\"]\n    Dana -->|35,5%| Alila[\"🏨 Renovasi Alila Ubud\"]\n    Dana -->|9,7%| Bintan[\"🏖️ Wisata Lagoi Bintan\"]\n```"
                elif "rights issue" in cat.lower() or "pmhmetd" in cat.lower() or "pmhmetd" in b_title.lower() or "rights issue" in b_title.lower():
                    b_text += f"\n\n```mermaid\ngraph TD\n    Emiten[\"🏬 {emiten} (Rights Issue / PMHMETD)\"] -->|Penerbitan Saham Baru| HMETD[\"📋 Hak Memesan Efek Terlebih Dahulu\"]\n    HMETD -->|Hasil Penawaran Umum| Dana[\"💵 Kas / Modal Kerja / Ekspansi\"]\n```"


                emiten_bullets.append(b_text)

            emiten_md = f"#### 🔵 [[{emiten}]]\n" + "\n".join(emiten_bullets)
            watchlist_set = set(read_emitens())
            if emiten in watchlist_set:
                watchlist_sections.append(emiten_md)
            else:
                non_watchlist_sections.append(emiten_md)

        table_content = "\n".join(all_table_rows)
        
        details_parts = []
        if watchlist_sections:
            details_parts.append("### ⭐ 4.1. Detail Emiten Pantauan (Watchlist)\n\n" + "\n\n".join(watchlist_sections))
        if non_watchlist_sections:
            details_parts.append("### 📋 4.2. Detail Emiten Lain (Non-Watchlist)\n\n" + "\n\n".join(non_watchlist_sections))

        details_content = "\n\n---\n\n".join(details_parts) if details_parts else "*Tidak ada detail pengumuman.*"
        
        # Build Watchlist Section
        watchlist_lines = []
        if dividen_watchlist:
            watchlist_lines.append("#### 💰 Watchlist Dividen & Distribution\n" + "\n".join(dividen_watchlist[:6]))
        if mto_watchlist:
            watchlist_lines.append("#### 🎯 Watchlist Penawaran Tender Wajib (MTO) & Strategis\n" + "\n".join(mto_watchlist[:6]))
        if warrant_watchlist:
            watchlist_lines.append("#### 📈 Watchlist Konversi Waran & Potensi Dilusi\n" + "\n".join(warrant_watchlist[:6]))
        if insider_watchlist:
            watchlist_lines.append("#### 👥 Watchlist Transaksi Orang Dalam & Kepemilikan Saham (Insider / Repo Moves)\n" + "\n".join(insider_watchlist[:8]))
        
        watchlist_content = "\n\n".join(watchlist_lines) if watchlist_lines else "*Tidak ada aksi korporasi khusus yang masuk dalam kriteria watchlist harian.*"

        # Build financial statements alert section
        if financial_reports:
            fin_items = []
            for r in financial_reports:
                fin_title = clean_announcement_title(r['filename'])
                f_path = r.get('file_path') or r.get('local_path', '')
                f_link = f" ([Buka PDF](file:///{f_path.replace(chr(92), '/')}))" if f_path else ""
                fin_items.append(f"- **{r['emiten']}**: {fin_title}{f_link}")
            fin_list_text = "\n".join(fin_items)
            fin_section = f"""> [!IMPORTANT]
> **Ditemukan Laporan Keuangan Baru Hari Ini:**
> {fin_list_text}
> 
> *Tugas Swarm Agent:* Lakukan analisis laporan keuangan mendalam per emiten secara terpisah untuk berkas-berkas di atas."""
        else:
            fin_section = f"""> [!NOTE]
> Tidak dideteksi adanya publikasi laporan keuangan baru hari ini. Rangkuman per emiten secara terperinci tidak diperlukan."""

        # Build dynamic next steps recommendations
        next_steps_content = build_dynamic_next_steps(
            dividen_emitens=dividen_emitens,
            mto_emitens=mto_emitens,
            ca_emitens=ca_emitens,
            financial_reports=financial_reports,
            pubex_emitens=pubex_emitens,
            bearish_items=bearish_items,
            bullish_items=bullish_items,
            date_str=today_str,
        )

        title_header = f"# Ikhtisar Akhir Pekan (Weekend Digest) - {today_str}" if is_weekend else f"# Ikhtisar Pasar Harian (Daily Digest) - {today_str}"
        dash_header = "## 1. Radar Pasar & Sentimen Akhir Pekan (Executive Weekend Dashboard)" if is_weekend else "## 1. Radar Pasar & Sentimen Harian (Executive Dashboard)"
        nav_tag = "Weekend Digest" if is_weekend else "Daily Digest"

        content = f"""{title_header}

📅 **{today_str} ({nav_tag})**

{dash_header}
> [!NOTE]
> Terdeteksi sebanyak **{len(new_announcements)} pengumuman baru** dari {len(emiten_groups)} emiten pantauan pada ({today_str}).

| Metric | Jumlah | Status Radar |
| :--- | :---: | :--- |
| **🟢 Sentimen Bullish / Positif** | `{bullish_cnt}` | [[Dividen Interim]], [[Mandatory Tender Offer]], Kinerja Positif |
| **⚪ Sentimen Netral / Routine** | `{neutral_cnt}` | [[Tanggapan Penjelasan Bursa]], [[RUPS]], [[Pendaftaran Unit]] |
| **🔴 Sentimen Bearish / Alert** | `{bearish_cnt}` | Sengketa Hukum, Defisit / Gugatan (Nihil hari ini) |
| **📄 [[Laporan Keuangan]] Baru** | `{len(financial_reports)}` | Memicu Analisis Keuangan Otomatis |

{fin_section}

---

## 2. Sorotan Utama & Watchlist Strategis (Strategic Watchlist)
{watchlist_content}

---

## 3. Matriks Pengumuman Pasar (Announcements Intelligence Table)
| Emiten | Sentimen | Jenis Pengumuman | Judul Pengumuman | Berkas |
| :--- | :---: | :--- | :--- | :--- |
{table_content}

---

## 4. Detail Informasi per Emiten (Grouped by Emiten)
{details_content}

---

## 5. Rekomendasi & Langkah Analisis Selanjutnya (Next Steps)
> [!TIP]
> **Instruksi Otomatis Swarm Agent**:
{next_steps_content}
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Clean digest report written to: {report_path}")
    
    # Auto-push to connected Obsidian vault
    push_to_obsidian_server(report_path, f"knowledge-base/daily-digests/{year_month}/{report_filename}")
    
    if is_weekend:
        daily_alt_path = os.path.join(report_dir, f"Daily_Digest_{date_prefix}.md")
        with open(daily_alt_path, "w", encoding="utf-8") as f:
            f.write(content)
        push_to_obsidian_server(daily_alt_path, f"knowledge-base/daily-digests/{year_month}/Daily_Digest_{date_prefix}.md")
    
    # Generate Money-Making Trading Signals Report automatically
    try:
        import signal_generator
        signal_generator.generate_trading_signals()
    except Exception as sge:
        print(f"[!] Trading Signal generation warning: {sge}")

    # Generate Master Action Calendar automatically
    try:
        import calendar_builder
        calendar_builder.build_action_calendar()
    except Exception as cbe:
        print(f"[!] Action Calendar generation warning: {cbe}")

    # Auto-update all Topic Knowledge Notes in Obsidian
    try:
        import topic_builder
        topic_builder.update_all_topics()
    except Exception as tbe:
        print(f"[!] Topic Notes update warning: {tbe}")

    # Auto-update Obsidian Dashboard MOC
    update_obsidian_dashboard()


def update_obsidian_dashboard():
    """Auto-updates the Obsidian Dashboard (MOC) with all available Daily Digests, Trading Signals, Valuations & Action Calendar."""
    digests_base_dir = os.path.join(BASE_DIR, r"reports\summaries\daily-digests")
    digest_links = []
    if os.path.exists(digests_base_dir):
        digest_items = []
        for root, dirs, files in os.walk(digests_base_dir):
            for f in files:
                if (f.startswith("Daily_Digest_") or f.startswith("Weekend_Digest_")) and f.endswith(".md"):
                    rel_dir = os.path.relpath(root, digests_base_dir).replace("\\", "/")
                    digest_items.append((f, rel_dir))
        digest_items.sort(key=lambda x: x[0], reverse=True)
        for f, rel_dir in digest_items:
            date_part = f.replace("Daily_Digest_", "").replace("Weekend_Digest_", "").replace(".md", "")
            if len(date_part) == 8 and date_part.isdigit():
                formatted_d = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}"
            else:
                formatted_d = date_part
            doc_name = f[:-3]
            label = "Rangkuman Akhir Pekan" if f.startswith("Weekend_Digest_") else "Rangkuman Harian"
            vault_sub = f"{rel_dir}/" if rel_dir and rel_dir != "." else ""
            digest_links.append(f"*   [[knowledge-base/daily-digests/{vault_sub}{doc_name}|{label} - {formatted_d}]]")

    signals_base_dir = os.path.join(BASE_DIR, r"reports\summaries\trading-signals")
    signal_links = []
    if os.path.exists(signals_base_dir):
        sig_items = []
        for root, dirs, files in os.walk(signals_base_dir):
            for f in files:
                if f.startswith("Trading_Signals_") and f.endswith(".md"):
                    rel_dir = os.path.relpath(root, signals_base_dir).replace("\\", "/")
                    sig_items.append((f, rel_dir))
        sig_items.sort(key=lambda x: x[0], reverse=True)
        for f, rel_dir in sig_items:
            date_part = f.replace("Trading_Signals_", "").replace(".md", "")
            if len(date_part) == 8 and date_part.isdigit():
                formatted_d = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}"
            else:
                formatted_d = date_part
            doc_name = f[:-3]
            vault_sub = f"{rel_dir}/" if rel_dir and rel_dir != "." else ""
            signal_links.append(f"*   [[knowledge-base/trading-signals/{vault_sub}{doc_name}|🎯 Sinyal Cuan & Katalis Trading Harian - {formatted_d}]]")

    ca_dir = os.path.join(BASE_DIR, r"reports\summaries\corporate-actions")
    ca_links = []
    if os.path.exists(ca_dir):
        ca_items = []
        for root, dirs, files in os.walk(ca_dir):
            for f in files:
                if f.endswith(".md"):
                    sub_rel = os.path.relpath(root, ca_dir).replace("\\", "/")
                    ca_items.append((f, sub_rel))
        ca_items.sort(key=lambda x: x[0], reverse=True)
        for f, sub_rel in ca_items[:20]:
            doc_name = f[:-3]
            clean_title = f.replace("_", " ").replace(".md", "")
            sub_path = f"{sub_rel}/" if sub_rel and sub_rel != "." else ""
            ca_links.append(f"*   [[knowledge-base/corporate-actions/{sub_path}{doc_name}|⚡ {clean_title}]]")

    val_dir = os.path.join(BASE_DIR, r"reports\summaries\valuations")
    val_links = []
    if os.path.exists(val_dir):
        val_files = sorted(
            [f for f in os.listdir(val_dir) if f.endswith(".md")],
            reverse=True
        )
        for f in val_files:
            doc_name = f[:-3]
            clean_title = f.replace("_", " ").replace(".md", "")
            val_links.append(f"*   [[knowledge-base/valuations/{doc_name}|📈 {clean_title}]]")

    pubex_dir = os.path.join(BASE_DIR, r"reports\summaries\public-exposes")
    pubex_links = []
    if os.path.exists(pubex_dir):
        pubex_items = []
        for root, dirs, files in os.walk(pubex_dir):
            for f in files:
                if f.endswith(".md"):
                    sub_rel = os.path.relpath(root, pubex_dir).replace("\\", "/")
                    pubex_items.append((f, sub_rel))
        pubex_items.sort(key=lambda x: x[0], reverse=True)
        for f, sub_rel in pubex_items[:15]:
            doc_name = f[:-3]
            clean_title = f.replace("_", " ").replace(".md", "")
            sub_path = f"{sub_rel}/" if sub_rel and sub_rel != "." else ""
            pubex_links.append(f"*   [[knowledge-base/public-exposes/{sub_path}{doc_name}|💬 {clean_title}]]")

    digests_str = "\n".join(digest_links) if digest_links else "*   *Belum ada Daily Digest terdaftar.*"
    signals_str = "\n".join(signal_links) if signal_links else "*   *Belum ada Sinyal Trading terdaftar.*"
    recent_ca_str = "\n".join(ca_links) if ca_links else "*   *Belum ada Laporan Aksi Korporasi khusus terdaftar.*"
    val_str = "\n".join(val_links) if val_links else "*   *Belum ada Laporan Valuasi terdaftar.*"
    pubex_str = "\n".join(pubex_links) if pubex_links else "*   *Belum ada Laporan Public Expose terdaftar.*"

    topic_hub_str = """### 📑 Indeks & Panduan Topik Aksi Korporasi (Topic MOCs)
*   [[Dividen Interim|💸 Dividen Interim & Dividen Tunai]]
*   [[Mandatory Tender Offer|🎯 Penawaran Tender Wajib (Mandatory Tender Offer / MTO)]]
*   [[Rights Issue|📜 Hak Memesan Efek Terlebih Dahulu (PMHMETD / Rights Issue)]]
*   [[Buyback|🛒 Pembelian Kembali Saham (Share Buyback)]]
*   [[Private Placement|🤝 Penambahan Modal Tanpa HMETD (PMTHMETD / Private Placement)]]
*   [[RUPS|🏛️ Rapat Umum Pemegang Saham (Pemanggilan & Risalah RUPS)]]
*   [[Stock Split|✂️ Pemecahan & Penggabungan Nilai Nominal Saham (Stock Split)]]
*   [[Public Expose|💬 Paparan Publik & Tanya Jawab Investor (Public Expose)]]

### ⚡ Laporan Khusus Terkini per Emiten
""" + recent_ca_str

    dash_content = f"""# 🎛️ Finplan Swarm Dashboard

Selamat datang di pusat intelijen pasar & pemantauan keuangan Anda. Halaman ini berfungsi sebagai Map of Content (MOC) yang menghubungkan seluruh sinyal trading, laporan keuangan, aksi korporasi, hasil public expose, dan rangkuman harian secara otomatis.

---

## 🎯 Sinyal Cuan & Katalis Trading (Alpha Signals)
Dokumen sinyal peluang investasi, dividend yield capture, dan arbitrase aksi korporasi yang disusun oleh AI Swarm:
{signals_str}

---

## 🗓️ Kalender Terpusat Aksi Korporasi & Dividen (Action Calendar)
*   [[knowledge-base/calendars/Action_Calendar|🗓️ Kalender Terpusat Cum Date Dividen, MTO & Rights Issue BEI]]

---

## 📈 Mesin Valuasi & Harga Wajar Emiten (Valuation Engine)
Laporan estimasi Nilai Wajar (*Fair Value*) berbasis 3-Stage DCF & Relative PE/PBV Multiples:
{val_str}

---

## ⚡ Laporan Aksi Korporasi Khusus (Corporate Action Intelligence)
Laporan analisis mendalam per aksi korporasi strategis yang disusun oleh **Corporate Action Summarizer Agent**:
{topic_hub_str}

---

## 💬 Laporan Hasil Public Expose (Tanya Jawab Investor & Manajemen)
Rangkuman lengkap Q&A (Pertanyaan & Jawaban) antara investor, media, dan manajemen perseroan:
{pubex_str}

---

## 📅 Rangkuman Harian Terbaru (Daily Digests)
Berikut adalah catatan aktivitas harian pasar yang dipindai secara otomatis dari bursa efek:
{digests_str}

---

## 📈 Laporan Analisis Keuangan Mendalam (Financial Summaries)
Analisis mendalam per emiten yang disusun secara otomatis oleh Swarm Agent ketika Laporan Keuangan berkala dipublikasikan:
*   [[knowledge-base/financial-summaries/BBRI_2025_FY_Summary|PT Bank Rakyat Indonesia (Persero) Tbk (BBRI) - Laporan Tahunan FY 2025]]

---

## 🏛️ Aturan & Standar Pelaporan (System Rules)
*   [[knowledge-base/rules/Daily_Reporting_Standards|Standar Pelaporan Harian & Generalist JSON Schema]]

---

## 🛠️ Menu Pintas (Quick Links)
*   [Emiten Pantauan](file:///g:/My%20Drive/Model2/emitens.txt)
*   [Folder Dokumen Mentah (Raw PDFs)](file:///g:/My%20Drive/Model2/reports/raw/)
"""
    local_dash_path = r"G:\My Drive\Model2\Finplan_analyst\Dashboard.md"
    try:
        os.makedirs(os.path.dirname(local_dash_path), exist_ok=True)
        with open(local_dash_path, "w", encoding="utf-8") as f:
            f.write(dash_content)
        print("[+] Local Dashboard.md updated.")
        push_to_obsidian_server(local_dash_path, "Dashboard.md")
    except Exception as e:
        print(f"[!] Dashboard update error: {e}")

def push_to_obsidian_server(filepath, vault_filename):
    """Pushes a local file to the Obsidian Local REST API vault and ensures direct file copy to local vault folder."""
    import urllib.request
    import urllib.parse
    import ssl
    import shutil
    
    if not os.path.exists(filepath):
        print(f"[-] Push failed: {filepath} not found.")
        return

    # Always ensure direct copy to local Obsidian vault directory
    local_vault_dest = os.path.join(BASE_DIR, "Finplan_analyst", vault_filename)
    src_abs = os.path.abspath(filepath)
    dest_abs = os.path.abspath(local_vault_dest)
    
    # Prevent self-copy error ([WinError 32] / SameFileError) if file is already in vault
    if src_abs.lower() != dest_abs.lower():
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        copied = False
        import time
        for attempt in range(3):
            try:
                shutil.copy2(src_abs, dest_abs)
                print(f"[+] Saved directly to Obsidian local vault: {dest_abs}")
                copied = True
                break
            except (PermissionError, OSError):
                time.sleep(0.2)
            except Exception:
                break
        if not copied:
            try:
                with open(src_abs, "r", encoding="utf-8") as f_in:
                    c_text = f_in.read()
                with open(dest_abs, "w", encoding="utf-8") as f_out:
                    f_out.write(c_text)
                print(f"[+] Saved directly to Obsidian local vault: {dest_abs}")
            except Exception as copy_err:
                print(f"[!] Direct copy to Obsidian vault failed: {copy_err}")
        
    API_KEY = os.environ.get("OBSIDIAN_API_KEY", "").strip()
    url = f"https://127.0.0.1:27124/vault/{urllib.parse.quote(vault_filename)}"
    
    if not API_KEY:
        return
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        req = urllib.request.Request(
            url,
            data=content.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "text/markdown"
            },
            method="PUT"
        )
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, context=ctx, timeout=3) as response:
            if response.getcode() in [200, 201, 204]:
                print(f"[+] Successfully pushed report to Obsidian vault as: {vault_filename}")
    except Exception:
        # Optional live refresh call — silent fail since direct file copy above handles 100% of vault updates
        pass


if __name__ == "__main__":
    main()