"""
financial_summary_builder.py — 3-Tier Adaptive Financial Summary Generator
==========================================================================
Generates sector-adaptive financial analysis reports from IDX XBRL workbooks.
Supports 3 template tiers (Q1/Q3 Interim, Q2 Semester, FY Annual) and
4 P&L variants (General, Mining, Financial, Infra/Toll).

v2.0 — 2026-09-01 — Complete rewrite with:
  - YAML frontmatter for machine-readability
  - Cash Flow Statement from sheet 15xxxxx
  - Per Share Metrics (EPS, BVPS)
  - Annualized ROE/ROA
  - Financial sector P&L variant (NII, NIM, skip GPM/NPM)
  - Public Expose vault lookup for sector KPIs
  - CALK extraction via LLM (calk_extractor.py)
  - Bilingual labels (ID / EN)
  - Mermaid pie chart for asset/liability composition
"""

import os
import re
import sys
import json
import glob
import openpyxl
from datetime import datetime

# ─── Path Setup ───────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
REPORTS_DIR = os.path.join(BASE_DIR, "reports", "summaries", "financial-summaries")
OBSIDIAN_VAULT_DIR = os.path.join(BASE_DIR, "Finplan_analyst", "knowledge-base", "financial-summaries")
PUBEX_DIR = os.path.join(BASE_DIR, "reports", "summaries", "public-exposes", "hasil-pubex")

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(OBSIDIAN_VAULT_DIR, exist_ok=True)

AGENTS_DIR = os.path.join(BASE_DIR, ".agents")
if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    import env_loader
    import llm_client
except Exception:
    pass

try:
    from calk_extractor import extract_calk_highlights
except Exception:
    extract_calk_highlights = None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Sector Mapping & Classification
# ═══════════════════════════════════════════════════════════════════════════════

def load_sector_map():
    map_file = os.path.join(AGENTS_DIR, "sector_map.json")
    if os.path.exists(map_file):
        try:
            with open(map_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_emiten_sector(emiten_code: str, fallback_sector: str = "") -> str:
    sector_map = load_sector_map()
    mapped = sector_map.get(emiten_code.upper())
    if mapped:
        return mapped
    if fallback_sector:
        f_lc = fallback_sector.lower()
        if "health" in f_lc or "kesehatan" in f_lc:
            return "Kesehatan"
        if "energy" in f_lc or "energi" in f_lc:
            return "Energi & Utilitas"
        if "tech" in f_lc or "teknologi" in f_lc or "telco" in f_lc:
            return "Telekomunikasi & Teknologi"
        if "prop" in f_lc or "real" in f_lc or "konstruksi" in f_lc:
            return "Properti & Konstruksi"
        if "bank" in f_lc or "finance" in f_lc or "financial" in f_lc or "insurance" in f_lc:
            return "Multifinance & Perbankan"
        if "infra" in f_lc or "trans" in f_lc:
            return "Infrastruktur & Transportasi"
        if "min" in f_lc or "tambang" in f_lc or "coal" in f_lc or "metal" in f_lc:
            return "Pertambangan"
        if "agri" in f_lc or "plant" in f_lc:
            return "Agrikultur"
        if "consum" in f_lc or "retail" in f_lc:
            return "Konsumer & Ritel"
        if "manuf" in f_lc or "industr" in f_lc:
            return "Manufaktur"
    return "General"


def classify_pl_variant(sector: str, pl_data: dict) -> str:
    """Determine which P&L template variant to use."""
    if "Multifinance" in sector or "Perbankan" in sector or "Asuransi" in sector or "Financial" in sector:
        return "financial"

    pl_keys_lc = [k.lower() for k in pl_data.keys()]
    has_premium = any("pendapatan premi" in k or "beban klaim" in k for k in pl_keys_lc)
    has_nii = any("pendapatan bunga bersih" in k or "net interest income" in k for k in pl_keys_lc)
    if has_premium or has_nii:
        return "financial"

    if "Pertambangan" in sector or "Energi" in sector:
        return "mining"
    if "Infrastruktur" in sector and "Transportasi" in sector:
        return "infra"
    return "general"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Utility Functions
# ═══════════════════════════════════════════════════════════════════════════════

def push_to_obsidian(relative_vault_path, content):
    try:
        dest_path = os.path.join(BASE_DIR, "Finplan_analyst", "knowledge-base", relative_vault_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[+] Saved directly to Obsidian local vault: {dest_path}")
        return True
    except Exception as e:
        print(f"[!] Direct copy to Obsidian vault failed: {e}")
        return False


def format_money(val, currency="IDR", scale=1.0):
    if val is None or not isinstance(val, (int, float)):
        return "-"
    num = val * scale
    is_usd = ("USD" in str(currency).upper() or "DOLLAR" in str(currency).upper())
    if is_usd:
        if abs(num) >= 1e9:
            return f"USD {num/1e9:,.2f} Billion"
        elif abs(num) >= 1e6:
            return f"USD {num/1e6:,.2f} Million"
        elif abs(num) >= 1e3:
            return f"USD {num/1e3:,.2f} Thousand"
        else:
            return f"USD {num:,.2f}"
    else:
        if abs(num) >= 1e12:
            return f"Rp {num/1e12:,.2f} Triliun"
        elif abs(num) >= 1e9:
            return f"Rp {num/1e9:,.2f} Miliar"
        elif abs(num) >= 1e6:
            return f"Rp {num/1e6:,.2f} Juta"
        else:
            return f"Rp {num:,.2f}"


def fmt(val, scale=1.0):
    """Format a raw numeric value for table display (no currency prefix)."""
    if val is None or not isinstance(val, (int, float)):
        return "-"
    num = val * scale
    if abs(num) >= 1e12:
        return f"{num/1e12:,.2f}T"
    elif abs(num) >= 1e9:
        return f"{num/1e9:,.2f}B"
    elif abs(num) >= 1e6:
        return f"{num/1e6:,.2f}M"
    elif abs(num) >= 1e3:
        return f"{num/1e3:,.2f}K"
    else:
        return f"{num:,.2f}"


def pct(curr, prev):
    """Calculate and format percentage change YoY."""
    if curr is None or prev is None or prev == 0:
        return "-"
    change = ((curr - prev) / abs(prev)) * 100.0
    sign = "+" if change > 0 else ""
    icon = "🟢" if change > 0 else ("🔴" if change < 0 else "⚪")
    return f"{sign}{change:.2f}% {icon}"


def safe_div(a, b):
    """Safe division returning None on failure."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def ratio_fmt(val, suffix="x", decimals=2):
    """Format a ratio value."""
    if val is None:
        return "-"
    return f"{val:.{decimals}f}{suffix}"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Enhanced XBRL Parser
# ═══════════════════════════════════════════════════════════════════════════════


def _is_koreksi_file(filename: str) -> bool:
    """Return True if this file is a correction/restatement of a previous filing."""
    fn_lc = filename.lower()
    return any(kw in fn_lc for kw in [
        "koreksi", "revisi", "restatement", "perbaikan",
        "amend", "restate", "corrected", "restated"
    ])

def parse_financial_xlsx(xlsx_path):
    """Parse IDX XBRL workbook and extract all financial data."""
    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    except Exception as e:
        print(f"      [!] Error opening workbook {xlsx_path}: {e}")
        return None

    data = {
        "entity_name": "",
        "emiten_code": "",
        "period_desc": "",
        "period_type": "",    # Q1, Q2, Q3, FY
        "scale": 1.0,
        "currency": "IDR",
        "sector_raw": "",
        "sector_detail": {},  # sektor, subsektor, industri, subindustri
        "auditor_info": {},
        "shares_outstanding": None,
        "is_financial_sector": False,
        "bs": {},
        "pl": {},
        "cf": {},
    }

    try:
        # ── Sheet 1000000: General Info ───────────────────────────────────
        if "1000000" in wb.sheetnames:
            sheet = wb["1000000"]
            for row in sheet.iter_rows(values_only=True):
                if not row or not row[0]:
                    continue
                lbl = str(row[0]).strip().lower()
                val = str(row[1] or "").strip() if len(row) > 1 else ""

                if "nama entitas" in lbl:
                    data["entity_name"] = val
                elif "kode entitas" in lbl:
                    data["emiten_code"] = val
                elif ("mata uang pelaporan" in lbl or "presentation currency" in lbl) and val:
                    data["currency"] = val
                elif "pembulatan" in lbl or "rounding" in lbl:
                    val_lc = val.lower()
                    if "ribuan" in val_lc or "thousand" in val_lc:
                        data["scale"] = 1000.0
                    elif "jutaan" in val_lc or "million" in val_lc:
                        data["scale"] = 1000000.0
                    elif "miliar" in val_lc or "billion" in val_lc:
                        data["scale"] = 1000000000.0
                    elif "satuan" in val_lc or "full" in val_lc:
                        data["scale"] = 1.0
                elif "periode penyampaian" in lbl:
                    data["period_desc"] = val
                    val_lc = val.lower()
                    if "kuartal i " in val_lc or "first quarter" in val_lc or "kuartal i/" in val_lc:
                        data["period_type"] = "Q1"
                    elif "kuartal ii" in val_lc or "second quarter" in val_lc or "semester" in val_lc:
                        data["period_type"] = "Q2"
                    elif "kuartal iii" in val_lc or "third quarter" in val_lc:
                        data["period_type"] = "Q3"
                    elif "tahunan" in val_lc or "annual" in val_lc or "kuartal iv" in val_lc or "fourth" in val_lc:
                        data["period_type"] = "FY"
                elif "sektor" == lbl.strip() or lbl.strip() == "sektor":
                    data["sector_detail"]["sektor"] = val
                    if not data["sector_raw"]:
                        data["sector_raw"] = val
                elif "subsektor" in lbl:
                    data["sector_detail"]["subsektor"] = val
                elif "industri" == lbl.strip() or lbl.strip() == "industri":
                    data["sector_detail"]["industri"] = val
                elif "subindustri" in lbl:
                    data["sector_detail"]["subindustri"] = val
                elif "jenis opini" in lbl:
                    data["auditor_info"]["opini"] = val
                elif "auditor tahun berjalan" in lbl:
                    data["auditor_info"]["kap"] = val
                elif "tanggal laporan audit" in lbl or "tanggal laporan review" in lbl:
                    data["auditor_info"]["tanggal"] = val
                elif "hasil penugasan review" in lbl:
                    data["auditor_info"]["hasil_review"] = val
                elif "nama partner audit" in lbl and "berjalan" in lbl:
                    data["auditor_info"]["partner"] = val
                elif "industri utama" in lbl:
                    data["sector_detail"]["industri_utama"] = val

        # ── Best Balance Sheet ────────────────────────────────────────────
        best_bs = None
        max_bs_rows = 0
        for s in wb.sheetnames:
            if any(s.startswith(p) for p in ['12', '22', '32', '42', '52', '62', '72', '82']):
                try:
                    rows = [r for r in wb[s].iter_rows(values_only=True)
                            if r and len(r) >= 3 and (isinstance(r[1], (int, float)) or isinstance(r[2], (int, float)))]
                    if len(rows) > max_bs_rows:
                        max_bs_rows = len(rows)
                        best_bs = s
                except Exception:
                    pass

        if best_bs:
            sheet = wb[best_bs]
            for row in sheet.iter_rows(values_only=True):
                if not row or len(row) < 3 or not row[0]:
                    continue
                lbl = str(row[0]).strip()
                curr = row[1] if isinstance(row[1], (int, float)) else None
                prev = row[2] if isinstance(row[2], (int, float)) else None
                if curr is not None or prev is not None:
                    data["bs"][lbl] = (curr, prev)
                # Extract shares outstanding
                lbl_lc = lbl.lower()
                if ("saham biasa" in lbl_lc or "common stock" in lbl_lc) and curr is not None:
                    data["shares_outstanding"] = curr

        # ── Best Income Statement ────────────────────────────────────────
        best_pl = None
        max_pl_rows = 0
        for s in wb.sheetnames:
            if any(s.startswith(p) for p in ['13', '23', '33', '43', '53', '63', '73', '83']):
                try:
                    rows = [r for r in wb[s].iter_rows(values_only=True)
                            if r and len(r) >= 3 and (isinstance(r[1], (int, float)) or isinstance(r[2], (int, float)))]
                    if len(rows) > max_pl_rows:
                        max_pl_rows = len(rows)
                        best_pl = s
                except Exception:
                    pass

        if best_pl:
            sheet = wb[best_pl]
            for row in sheet.iter_rows(values_only=True):
                if not row or len(row) < 3 or not row[0]:
                    continue
                lbl = str(row[0]).strip()
                curr = row[1] if isinstance(row[1], (int, float)) else None
                prev = row[2] if isinstance(row[2], (int, float)) else None
                if curr is not None or prev is not None:
                    data["pl"][lbl] = (curr, prev)

        # Detect financial sector from P&L data
        pl_keys_lc = [k.lower() for k in data["pl"].keys()]
        if any("pendapatan bunga bersih" in k or "net interest income" in k for k in pl_keys_lc):
            data["is_financial_sector"] = True
        if any("premi" in k and ("pendapatan" in k or "premium" in k) for k in pl_keys_lc):
            data["is_financial_sector"] = True
        if any("beban klaim" in k or "claims expense" in k for k in pl_keys_lc):
            data["is_financial_sector"] = True

        # ── Best Cash Flow Statement (sheet 15xxxxx) ─────────────────────
        best_cf = None
        max_cf_rows = 0
        for s in wb.sheetnames:
            if any(s.startswith(p) for p in ['15', '25', '35', '45', '55', '65', '75', '85']):
                try:
                    rows = [r for r in wb[s].iter_rows(values_only=True)
                            if r and len(r) >= 3 and (isinstance(r[1], (int, float)) or isinstance(r[2], (int, float)))]
                    if len(rows) > max_cf_rows:
                        max_cf_rows = len(rows)
                        best_cf = s
                except Exception:
                    pass

        # Fallback: try 14xxxxx if 15xxxxx has no data (some older formats)
        if not best_cf or max_cf_rows < 5:
            for s in wb.sheetnames:
                if any(s.startswith(p) for p in ['14', '24', '34', '44', '84']):
                    try:
                        rows = [r for r in wb[s].iter_rows(values_only=True)
                                if r and len(r) >= 3 and (isinstance(r[1], (int, float)) or isinstance(r[2], (int, float)))]
                        if len(rows) > max_cf_rows:
                            max_cf_rows = len(rows)
                            best_cf = s
                    except Exception:
                        pass

        if best_cf:
            sheet = wb[best_cf]
            for row in sheet.iter_rows(values_only=True):
                if not row or len(row) < 3 or not row[0]:
                    continue
                lbl = str(row[0]).strip()
                curr = row[1] if isinstance(row[1], (int, float)) else None
                prev = row[2] if isinstance(row[2], (int, float)) else None
                if curr is not None or prev is not None:
                    data["cf"][lbl] = (curr, prev)

    finally:
        wb.close()

    return data


def parse_financial_pdf(pdf_path: str, emiten: str = "") -> dict:
    """
    Fallback parser for when no IDX XBRL XLSX is available.
    Uses PyMuPDF + pure regex to extract financial figures from the PDF.
    Works with the standard IDX XBRL PDF format where labels and numbers
    appear on alternating lines (e.g. 'Jumlah aset lancar\\n16,530,448\\n14,241,193').
    No LLM required — 100% offline and deterministic.
    Returns the same dict schema as parse_financial_xlsx().
    """
    data = {
        "entity_name": emiten,
        "emiten_code": emiten,
        "period_desc": "",
        "period_type": "",
        "scale": 1000000.0,
        "currency": "IDR",
        "sector_raw": "",
        "sector_detail": {},
        "auditor_info": {},
        "shares_outstanding": None,
        "is_financial_sector": False,
        "bs": {},
        "pl": {},
        "cf": {},
        "_source": "pdf_regex",
    }

    try:
        import fitz  # PyMuPDF
    except ImportError:
        print(f"      [!] PyMuPDF not installed -- cannot parse PDF for {emiten}")
        return None

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"      [!] Cannot open PDF {pdf_path}: {e}")
        return None

    def _parse_num(s: str):
        """Parse IDX number format: '16,530,448' or '16.530.448' -> 16530448.0"""
        s = s.strip().replace(" ", "")
        if not s or s in ("-", "--", "–"):
            return None
        # Detect if dots are thousands separators (e.g. 16.530.448) vs decimal
        # IDX standard: dots as thousands, comma as decimal (or vice versa for some)
        # Heuristic: if >1 dot and last segment is 3 digits → dot is thousands sep
        s = re.sub(r"[^\d.,\-]", "", s)
        if not s:
            return None
        # Handle negative
        neg = s.startswith("-")
        s = s.lstrip("-")
        # If commas: 16,530,448 → standard English format
        if "," in s and "." not in s:
            s = s.replace(",", "")
        elif "." in s and "," not in s:
            # 16.530.448 → dot as thousands
            parts = s.split(".")
            if all(len(p) == 3 for p in parts[1:]):
                s = s.replace(".", "")
            else:
                s = s.replace(".", "")  # treat as integer
        elif "," in s and "." in s:
            # 16,530,448.00 or 16.530,00
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        try:
            val = float(s)
            return -val if neg else val
        except Exception:
            return None

    # ── Collect all text from relevant pages ──────────────────────────────────
    BS_PAGES, PL_PAGES, CF_PAGES, META_PAGES = [], [], [], []
    BS_KW  = ["aset", "liabilitas", "ekuitas", "piutang", "persediaan", "utang modal"]
    PL_KW  = ["pendapatan", "penjualan", "beban", "laba", "rugi", "premi", "klaim"]
    CF_KW  = ["arus kas", "cash flow", "aktivitas operasi", "aktivitas investasi", "aktivitas pendanaan"]
    META_KW = ["nama emiten", "kode emiten", "mata uang", "pembulatan", "periode", "satuan", "jutaan", "ribuan"]

    for i, page in enumerate(doc):
        txt_raw = page.get_text()
        tl = txt_raw.lower()
        if i < 5:
            META_PAGES.append(txt_raw)
        if any(k in tl for k in BS_KW):
            BS_PAGES.append(txt_raw)
        if any(k in tl for k in PL_KW):
            PL_PAGES.append(txt_raw)
        if any(k in tl for k in CF_KW):
            CF_PAGES.append(txt_raw)

    doc.close()

    if not BS_PAGES and not PL_PAGES:
        print(f"      [!] No financial content found in PDF {pdf_path}")
        return None

    # ── Extract metadata from first pages ─────────────────────────────────────
    meta_text = "\n".join(META_PAGES)
    # Entity name
    m = re.search(r"(?:Nama Emiten|nama perusahaan|PT\s+[A-Z][\w\s,\.]+(?:Tbk|TBK))", meta_text, re.IGNORECASE)
    if m:
        data["entity_name"] = m.group(0).strip()
    # Period
    meta_lc = meta_text.lower()
    if "kuartal ii" in meta_lc or "semester" in meta_lc or "6 bulan" in meta_lc or "june" in meta_lc or "juni" in meta_lc:
        data["period_type"] = "Q2"
    elif "kuartal i " in meta_lc or "maret" in meta_lc or "march" in meta_lc or "3 bulan" in meta_lc:
        data["period_type"] = "Q1"
    elif "kuartal iii" in meta_lc or "september" in meta_lc:
        data["period_type"] = "Q3"
    elif "tahunan" in meta_lc or "desember" in meta_lc or "december" in meta_lc or "annual" in meta_lc:
        data["period_type"] = "FY"
    # Scale
    if "jutaan" in meta_lc or "million" in meta_lc:
        data["scale"] = 1000000.0
    elif "ribuan" in meta_lc or "thousand" in meta_lc:
        data["scale"] = 1000.0
    elif "miliar" in meta_lc or "billion" in meta_lc:
        data["scale"] = 1000000000.0
    # Currency
    if "usd" in meta_lc:
        data["currency"] = "USD"

    # ── Generic label→number extractor ───────────────────────────────────────
    # In IDX XBRL PDFs the layout is: label line, then number line(s)
    # We build a flat token list from each page and pair labels with numbers
    NUM_PAT = re.compile(r"^-?[\d][,.\d]*\d$")  # pure numeric token

    def _extract_pairs(pages: list) -> dict:
        """
        Extract label→(current, prev) pairs from IDX XBRL PDF pages.
        Strategy: iterate lines, when we see a label line followed by 1-2 number lines → pair them.
        """
        result = {}
        for page_txt in pages:
            lines = [l.strip() for l in page_txt.splitlines() if l.strip()]
            i = 0
            while i < len(lines):
                line = lines[i]
                # Skip lines that are pure numbers
                if NUM_PAT.match(line.replace(",", "").replace(".", "").replace("-", "", 1)):
                    i += 1
                    continue
                # Skip very short or obviously non-label lines
                if len(line) < 4 or re.match(r"^\d", line):
                    i += 1
                    continue
                # Collect up to 2 numbers following this label
                nums = []
                j = i + 1
                while j < len(lines) and len(nums) < 2:
                    candidate = lines[j]
                    # Try to parse as number
                    n = _parse_num(candidate)
                    if n is not None:
                        nums.append(n)
                        j += 1
                    elif len(candidate) < 4 or re.match(r"^[A-Z][A-Z\s]+$", candidate):
                        # short filler or all-caps header -> skip
                        j += 1
                    else:
                        break
                if nums:
                    curr = nums[0]
                    prev = nums[1] if len(nums) > 1 else None
                    lbl = line[:80]  # cap label length
                    if lbl not in result:   # first occurrence wins (summary line)
                        result[lbl] = (curr, prev)
                    i = j
                else:
                    i += 1
        return result

    bs_raw = _extract_pairs(BS_PAGES)
    pl_raw = _extract_pairs(PL_PAGES)
    cf_raw = _extract_pairs(CF_PAGES)

    # ── Map raw labels to canonical internal keys ─────────────────────────────
    def _find(raw: dict, patterns: list):
        """Match first label containing any of the patterns (case-insensitive)."""
        for pat in patterns:
            pat_lc = pat.lower()
            for k, v in raw.items():
                if pat_lc in k.lower():
                    return v
        return (None, None)

    data["bs"] = {
        "Jumlah Aset":               _find(bs_raw, ["jumlah aset", "total assets", "total aset"]),
        "Jumlah Liabilitas":         _find(bs_raw, ["jumlah liabilitas", "total liabilit"]),
        "Jumlah Ekuitas":            _find(bs_raw, ["jumlah ekuitas", "total ekuitas", "total equity"]),
        "Kas dan Setara Kas":        _find(bs_raw, ["kas dan setara", "cash and cash equiv"]),
        "Aset Lancar":               _find(bs_raw, ["jumlah aset lancar", "total aset lancar", "total current assets"]),
        "Aset Tidak Lancar":         _find(bs_raw, ["jumlah aset tidak lancar", "total non-current assets", "total aset tidak lancar"]),
        "Liabilitas Jangka Pendek":  _find(bs_raw, ["jumlah liabilitas jangka pendek", "total current liabilit"]),
        "Liabilitas Jangka Panjang": _find(bs_raw, ["jumlah liabilitas jangka panjang", "total non-current liabilit"]),
        "Piutang Usaha":             _find(bs_raw, ["piutang usaha", "trade receivable"]),
        "Persediaan":                _find(bs_raw, ["persediaan", "inventori"]),
        "Utang Usaha":               _find(bs_raw, ["utang usaha", "trade payable"]),
    }
    # Remove None-value entries
    data["bs"] = {k: v for k, v in data["bs"].items() if v != (None, None)}

    data["pl"] = {
        "Pendapatan":             _find(pl_raw, ["penjualan dan pendapatan", "jumlah pendapatan", "pendapatan usaha", "revenue"]),
        "Beban Pokok Penjualan":  _find(pl_raw, ["beban pokok penjualan", "beban pokok pendapatan", "cost of goods"]),
        "Laba Bruto":             _find(pl_raw, ["laba bruto", "laba kotor", "gross profit"]),
        "Beban Usaha":            _find(pl_raw, ["beban usaha", "beban umum dan administrasi", "operating expense"]),
        "Laba Usaha":             _find(pl_raw, ["laba usaha", "laba operasi", "operating profit", "laba (rugi) usaha"]),
        "Laba Sebelum Pajak":     _find(pl_raw, ["laba sebelum pajak", "laba (rugi) sebelum pajak", "profit before tax"]),
        "Laba Bersih":            _find(pl_raw, ["laba (rugi) yang dapat diatribusikan ke entitas induk",
                                                  "laba (rugi) periode berjalan", "laba bersih", "net income", "profit for"]),
        # Financial sector extras
        "Pendapatan Bunga Bersih": _find(pl_raw, ["pendapatan bunga bersih", "net interest income", "pendapatan bunga dan"]),
        "Pendapatan Premi":        _find(pl_raw, ["pendapatan premi", "premi neto"]),
    }
    data["pl"] = {k: v for k, v in data["pl"].items() if v != (None, None)}

    data["cf"] = {
        "Arus Kas Operasi":    _find(cf_raw, ["arus kas dari aktivitas operasi", "kas dari operasi", "operating activities"]),
        "Arus Kas Investasi":  _find(cf_raw, ["arus kas dari aktivitas investasi", "investing activities"]),
        "Arus Kas Pendanaan":  _find(cf_raw, ["arus kas dari aktivitas pendanaan", "financing activities"]),
    }
    data["cf"] = {k: v for k, v in data["cf"].items() if v != (None, None)}

    # Detect financial sector from PL labels
    pl_keys_lc = " ".join(data["pl"].keys()).lower()
    if "bunga bersih" in pl_keys_lc or "premi" in pl_keys_lc:
        data["is_financial_sector"] = True

    total_items = len(data["bs"]) + len(data["pl"]) + len(data["cf"])
    print(f"      [PDF-Regex] {emiten}: extracted BS={len(data['bs'])} PL={len(data['pl'])} CF={len(data['cf'])} items")

    if total_items < 3:
        print(f"      [!] PDF-Regex extracted too few items ({total_items}) for {emiten} -- result unreliable")
        return None

    return data

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Metric Extraction Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def extract_metric(items_dict, patterns):
    """Extract (current, prev) tuple from a dict by matching label patterns."""
    for pattern in patterns:
        pat_lc = pattern.lower()
        for k, v in items_dict.items():
            k_lc = k.lower()
            if pat_lc == k_lc or pat_lc in k_lc:
                return v
    return (None, None)


def extract_general_pl(pl):
    """Extract P&L metrics for General/Manufacturing/Healthcare/Tech sectors."""
    rev = extract_metric(pl, [
        "penjualan dan pendapatan usaha", "pendapatan usaha", "jumlah pendapatan usaha",
        "jumlah pendapatan", "pendapatan", "revenue", "sales and revenue", "net revenues"
    ])
    cogs = extract_metric(pl, [
        "beban pokok penjualan dan pendapatan", "beban pokok penjualan", "beban pokok pendapatan",
        "jumlah beban pokok penjualan", "beban pokok", "cost of goods sold", "cost of revenues"
    ])
    gp = extract_metric(pl, ["jumlah laba bruto", "laba bruto", "laba kotor", "gross profit"])
    opex = extract_metric(pl, [
        "beban umum dan administrasi", "beban usaha", "jumlah beban usaha", "operating expenses"
    ])
    ebit = extract_metric(pl, [
        "jumlah laba (rugi) sebelum pajak penghasilan", "laba (rugi) sebelum pajak",
        "laba usaha", "laba operasi", "operating profit", "profit before tax"
    ])
    ni = extract_metric(pl, [
        "jumlah laba (rugi) yang dapat diatribusikan ke entitas induk",
        "laba (rugi) yang dapat diatribusikan ke entitas induk",
        "jumlah laba (rugi)", "laba (rugi) periode berjalan",
        "laba bersih", "profit for the period", "net income"
    ])
    return {"rev": rev, "cogs": cogs, "gp": gp, "opex": opex, "ebit": ebit, "ni": ni}


def extract_financial_pl(pl):
    """Extract P&L metrics for Financial/Insurance/Banking sectors."""
    int_inc = extract_metric(pl, [
        "pendapatan bunga dan syariah", "pendapatan bunga", "interest income",
        "jumlah pendapatan bunga"
    ])
    int_exp = extract_metric(pl, [
        "beban bunga dan syariah", "beban bunga", "interest expense",
        "jumlah beban bunga"
    ])
    nii = extract_metric(pl, [
        "pendapatan bunga bersih", "pendapatan bunga - bersih",
        "net interest income", "jumlah pendapatan bunga bersih"
    ])
    prem_inc = extract_metric(pl, [
        "pendapatan premi", "pendapatan premi neto", "pendapatan premi bruto",
        "premium income", "net premium income"
    ])
    claim_exp = extract_metric(pl, [
        "beban klaim", "beban klaim dan manfaat", "beban klaim neto",
        "claims expense", "claims and benefits expense"
    ])
    ppap = extract_metric(pl, [
        "penyisihan kerugian penurunan nilai", "cadangan kerugian penurunan nilai",
        "beban provisi atas kerugian", "provision for impairment losses",
        "pembentukan cadangan", "penyisihan"
    ])
    opex = extract_metric(pl, [
        "beban umum dan administrasi", "beban usaha", "jumlah beban usaha",
        "beban operasional lainnya", "operating expenses"
    ])
    op_inc = extract_metric(pl, [
        "pendapatan operasional lainnya", "pendapatan usaha lainnya",
        "other operating income"
    ])
    ebit = extract_metric(pl, [
        "jumlah laba (rugi) sebelum pajak penghasilan", "laba (rugi) sebelum pajak",
        "laba usaha", "operating profit", "profit before tax"
    ])
    ni = extract_metric(pl, [
        "jumlah laba (rugi) yang dapat diatribusikan ke entitas induk",
        "laba (rugi) yang dapat diatribusikan ke entitas induk",
        "jumlah laba (rugi)", "laba (rugi) periode berjalan",
        "laba bersih", "profit for the period", "net income"
    ])
    # Total revenue for financial sector
    rev = extract_metric(pl, [
        "jumlah pendapatan usaha", "jumlah pendapatan", "pendapatan usaha",
        "total pendapatan", "total revenue"
    ])
    return {
        "int_inc": int_inc, "int_exp": int_exp, "nii": nii,
        "prem_inc": prem_inc, "claim_exp": claim_exp, "ppap": ppap,
        "opex": opex, "op_inc": op_inc, "ebit": ebit, "ni": ni, "rev": rev
    }


def extract_bs(bs):
    """Extract Balance Sheet metrics."""
    ca = extract_metric(bs, ["jumlah aset lancar", "aset lancar", "current assets", "total current assets"])
    nca = extract_metric(bs, ["jumlah aset tidak lancar", "aset tidak lancar", "non-current assets", "total non-current assets"])
    ta = extract_metric(bs, ["jumlah aset", "total aset", "total assets"])
    cl = extract_metric(bs, ["jumlah liabilitas jangka pendek", "liabilitas jangka pendek", "current liabilities", "total current liabilities"])
    ncl = extract_metric(bs, ["jumlah liabilitas jangka panjang", "liabilitas jangka panjang", "non-current liabilities", "total non-current liabilities"])
    tl = extract_metric(bs, ["jumlah liabilitas", "total liabilitas", "total liabilities"])
    eq = extract_metric(bs, [
        "jumlah ekuitas", "total ekuitas",
        "jumlah ekuitas yang diatribusikan kepada pemilik entitas induk",
        "total equity", "equity attributable to owners"
    ])
    cash = extract_metric(bs, [
        "kas dan setara kas", "kas dan bank", "cash and cash equivalents", "cash and banks"
    ])
    inv = extract_metric(bs, ["persediaan", "inventories", "inventory"])
    recv = extract_metric(bs, [
        "piutang usaha", "piutang usaha pihak ketiga", "trade receivables",
        "piutang usaha - neto", "piutang usaha - bersih"
    ])
    return {"ca": ca, "nca": nca, "ta": ta, "cl": cl, "ncl": ncl, "tl": tl,
            "eq": eq, "cash": cash, "inv": inv, "recv": recv}


def extract_cf(cf):
    """Extract Cash Flow statement metrics."""
    cfo = extract_metric(cf, [
        "jumlah arus kas bersih yang diperoleh dari (digunakan untuk) aktivitas operasi",
        "kas bersih diperoleh dari aktivitas operasi",
        "arus kas bersih dari aktivitas operasi",
        "kas diperoleh dari (digunakan untuk) operasi",
        "net cash from operating activities"
    ])
    cfi = extract_metric(cf, [
        "jumlah arus kas bersih yang diperoleh dari (digunakan untuk) aktivitas investasi",
        "kas bersih digunakan untuk aktivitas investasi",
        "arus kas bersih dari aktivitas investasi",
        "net cash from investing activities"
    ])
    cff = extract_metric(cf, [
        "jumlah arus kas bersih yang diperoleh dari (digunakan untuk) aktivitas pendanaan",
        "kas bersih diperoleh dari aktivitas pendanaan",
        "arus kas bersih dari aktivitas pendanaan",
        "net cash from financing activities"
    ])
    net = extract_metric(cf, [
        "jumlah kenaikan (penurunan) bersih kas dan setara kas",
        "kenaikan (penurunan) bersih kas",
        "net increase in cash"
    ])
    capex = extract_metric(cf, [
        "pembayaran untuk perolehan aset tetap",
        "purchase of fixed assets", "capital expenditure"
    ])
    div_paid = extract_metric(cf, [
        "pembayaran dividen dari aktivitas pendanaan",
        "pembayaran dividen",
        "dividends paid"
    ])
    return {"cfo": cfo, "cfi": cfi, "cff": cff, "net": net, "capex": capex, "div_paid": div_paid}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Ratio Computation
# ═══════════════════════════════════════════════════════════════════════════════

def get_annualize_factor(period_type: str) -> float:
    factors = {"Q1": 4.0, "Q2": 2.0, "Q3": 4.0/3.0, "FY": 1.0}
    return factors.get(period_type, 2.0)


def compute_ratios(bs_m, pl_m, period_type, is_financial=False):
    """Compute all financial ratios."""
    ca_c = bs_m["ca"][0]
    cl_c = bs_m["cl"][0]
    ta_c = bs_m["ta"][0]
    tl_c = bs_m["tl"][0]
    eq_c = bs_m["eq"][0]
    inv_c = bs_m["inv"][0]
    cash_c = bs_m["cash"][0]

    ann = get_annualize_factor(period_type)

    # Get net income
    if is_financial:
        ni_c = pl_m.get("ni", (None, None))[0]
    else:
        ni_c = pl_m.get("ni", (None, None))[0]

    # Get revenue for GPM/NPM
    if is_financial:
        rev_c = pl_m.get("rev", (None, None))[0]
        gp_c = None  # GPM not meaningful for financial sector
    else:
        rev_c = pl_m.get("rev", (None, None))[0]
        gp_c = pl_m.get("gp", (None, None))[0]

    ratios = {}

    # Liquidity
    ratios["cr"] = safe_div(ca_c, cl_c) if ca_c is not None and cl_c is not None else None
    quick_assets = None
    if ca_c is not None:
        quick_assets = ca_c - (inv_c or 0)
    ratios["qr"] = safe_div(quick_assets, cl_c) if quick_assets is not None and cl_c is not None else None

    # Profitability (skip GPM/NPM for financial sector)
    if not is_financial:
        ratios["gpm"] = safe_div(gp_c, rev_c) * 100 if safe_div(gp_c, rev_c) is not None else None
        ratios["npm"] = safe_div(ni_c, rev_c) * 100 if safe_div(ni_c, rev_c) is not None else None
        # Operating Profit Margin
        ebit_c = pl_m.get("ebit", (None, None))[0]
        ratios["opm"] = safe_div(ebit_c, rev_c) * 100 if safe_div(ebit_c, rev_c) is not None else None
    else:
        ratios["gpm"] = None
        ratios["npm"] = None
        ratios["opm"] = None
        # NIM for banking
        int_inc_c = pl_m.get("int_inc", (None, None))[0]
        int_exp_c = pl_m.get("int_exp", (None, None))[0]
        if int_inc_c is not None and int_exp_c is not None and ta_c is not None and ta_c != 0:
            nii_val = int_inc_c - abs(int_exp_c)
            ratios["nim"] = (nii_val * ann / ta_c) * 100
        else:
            ratios["nim"] = None
        # BOPO (CIR) = OpEx / Operating Income
        opex_c = pl_m.get("opex", (None, None))[0]
        op_rev = pl_m.get("rev", (None, None))[0]
        if opex_c and op_rev and op_rev != 0:
            ratios["bopo"] = (abs(opex_c) / abs(op_rev)) * 100
        else:
            ratios["bopo"] = None

    # Return on Equity / Assets (annualized)
    ta_p = bs_m["ta"][1]
    eq_p = bs_m["eq"][1]
    avg_ta = (ta_c + ta_p) / 2 if ta_c is not None and ta_p is not None else ta_c
    avg_eq = (eq_c + eq_p) / 2 if eq_c is not None and eq_p is not None else eq_c

    if ni_c is not None and avg_eq and avg_eq != 0:
        ratios["roe"] = (ni_c * ann / avg_eq) * 100
    else:
        ratios["roe"] = None

    if ni_c is not None and avg_ta and avg_ta != 0:
        ratios["roa"] = (ni_c * ann / avg_ta) * 100
    else:
        ratios["roa"] = None

    # Solvency
    ratios["der"] = safe_div(tl_c, eq_c) if tl_c is not None and eq_c is not None else None
    ratios["dar"] = safe_div(tl_c, ta_c) if tl_c is not None and ta_c is not None else None

    return ratios


def compute_per_share(ni_c, eq_c, shares, scale, period_type):
    """Compute EPS and BVPS."""
    if shares is None or shares == 0:
        return None, None

    # shares value from XBRL is already in the same scale unit as other data
    # so shares * scale = actual share count
    actual_shares = shares * scale

    ann = get_annualize_factor(period_type)

    eps = None
    if ni_c is not None:
        eps = (ni_c * scale * ann) / actual_shares

    bvps = None
    if eq_c is not None:
        bvps = (eq_c * scale) / actual_shares

    return eps, bvps


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Public Expose Vault Lookup
# ═══════════════════════════════════════════════════════════════════════════════

def lookup_pubex_kpis(emiten):
    """Look up the most recent Public Expose file in the vault for sector KPIs."""
    try:
        pattern = os.path.join(PUBEX_DIR, f"{emiten}_Public_Expose_*.md")
        files = sorted(glob.glob(pattern), reverse=True)
        if not files:
            return None

        latest = files[0]
        with open(latest, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract structured KPI data from the pubex content
        kpis = []
        lines = content.split("\n")
        in_table = False
        for line in lines:
            # Look for table rows with KPI data
            if "|" in line and ("Parameter" in line or "Indikator" in line or "Kinerja" in line):
                in_table = True
                continue
            if in_table and "|" in line and "---" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    kpis.append(f"- **{parts[0]}**: {parts[1]}")
            elif in_table and "|" not in line:
                in_table = False

            # Also extract bullet point KPIs
            if line.strip().startswith("- **") and any(kw in line.lower() for kw in [
                "produksi", "volume", "kapasitas", "target", "guidance",
                "pendapatan", "revenue", "lhr", "arpu", "npm", "npf",
                "car", "rbc", "nim", "asp", "rendemen"
            ]):
                kpis.append(line.strip())

        return {
            "source_file": os.path.basename(latest),
            "kpis": kpis[:10]  # Cap at 10 KPIs
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: YAML Frontmatter Builder
# ═══════════════════════════════════════════════════════════════════════════════

def build_yaml_frontmatter(emiten, entity_name, sector, period, year, currency, scale,
                           pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
                           is_financial, pl_variant):
    """Build YAML frontmatter for machine-readability."""
    # Get key values
    if is_financial:
        rev_c = pl_m.get("rev", (None, None))[0]
        ni_c = pl_m.get("ni", (None, None))[0]
    else:
        rev_c = pl_m.get("rev", (None, None))[0]
        ni_c = pl_m.get("ni", (None, None))[0]

    ta_c = bs_m["ta"][0]
    tl_c = bs_m["tl"][0]
    eq_c = bs_m["eq"][0]
    cash_c = bs_m["cash"][0]

    cfo_c = cf_m["cfo"][0]
    cfi_c = cf_m["cfi"][0]
    cff_c = cf_m["cff"][0]

    def scaled(v):
        if v is None:
            return "null"
        return f"{v * scale:.0f}"

    def ratio_val(key):
        v = ratios.get(key)
        return f"{v:.4f}" if v is not None else "null"

    lines = [
        "---",
        f"ticker: {emiten}",
        f"entity_name: \"{entity_name}\"",
        f"sektor: \"{sector}\"",
    ]
    sd = {}  # Will be populated from sector_detail if available
    lines += [
        f"periode: {period}",
        f"tahun: {year}",
        f"currency: \"{currency}\"",
        f"scale: {scale}",
        f"pl_variant: {pl_variant}",
        f"revenue: {scaled(rev_c)}",
        f"net_income: {scaled(ni_c)}",
        f"total_assets: {scaled(ta_c)}",
        f"total_liabilities: {scaled(tl_c)}",
        f"total_equity: {scaled(eq_c)}",
        f"cash: {scaled(cash_c)}",
        f"cfo: {scaled(cfo_c)}",
        f"cfi: {scaled(cfi_c)}",
        f"cff: {scaled(cff_c)}",
        f"shares_outstanding: {scaled(shares) if shares else 'null'}",
        f"eps: {f'{eps:.4f}' if eps is not None else 'null'}",
        f"bvps: {f'{bvps:.4f}' if bvps is not None else 'null'}",
        f"gpm: {ratio_val('gpm')}",
        f"opm: {ratio_val('opm')}",
        f"npm: {ratio_val('npm')}",
        f"roe_annualized: {ratio_val('roe')}",
        f"roa_annualized: {ratio_val('roa')}",
        f"der: {ratio_val('der')}",
        f"dar: {ratio_val('dar')}",
        f"current_ratio: {ratio_val('cr')}",
        f"quick_ratio: {ratio_val('qr')}",
        f"generated_at: \"{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\"",
        "---",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: Template Sub-Renderers
# ═══════════════════════════════════════════════════════════════════════════════

def render_executive_summary(emiten, entity_name, sector, period, year, currency, scale,
                             pl_m, bs_m, ratios, eps, bvps, is_financial, today_str):
    """Render the Executive Summary section (all tiers)."""
    if is_financial:
        ni = pl_m.get("ni", (None, None))
        rev = pl_m.get("rev", (None, None))
        int_inc = pl_m.get("int_inc", (None, None))
        rev_label = "Pendapatan Usaha / Total Revenue"
        rev_val = format_money(rev[0], currency, scale)
        rev_yoy = pct(rev[0], rev[1])
        rev_prev = format_money(rev[1], currency, scale)
        extra_line = f"- **Pendapatan Bunga / Interest Income**: `{format_money(int_inc[0], currency, scale)}`" if int_inc[0] else ""
    else:
        ni = pl_m.get("ni", (None, None))
        rev = pl_m.get("rev", (None, None))
        gp = pl_m.get("gp", (None, None))
        rev_label = "Pendapatan Neto / Net Revenue"
        rev_val = format_money(rev[0], currency, scale)
        rev_yoy = pct(rev[0], rev[1])
        rev_prev = format_money(rev[1], currency, scale)
        extra_line = f"- **Laba Bruto / Gross Profit**: `{format_money(gp[0], currency, scale)}` (**{pct(gp[0], gp[1])} YoY**)" if gp[0] else ""

    ta = bs_m["ta"]
    eq = bs_m["eq"]
    cash = bs_m["cash"]

    eps_str = f"{eps:,.2f}" if eps is not None else "-"
    bvps_str = f"{bvps:,.2f}" if bvps is not None else "-"

    # Mermaid flow diagram
    der_str = ratio_fmt(ratios.get("der"), "x") if ratios.get("der") is not None else "-"
    cr_str = ratio_fmt(ratios.get("cr"), "x") if ratios.get("cr") is not None else "-"
    qr_str = ratio_fmt(ratios.get("qr"), "x") if ratios.get("qr") is not None else "-"
    roe_str = ratio_fmt(ratios.get("roe"), "%") if ratios.get("roe") is not None else "-"
    roa_str = ratio_fmt(ratios.get("roa"), "%") if ratios.get("roa") is not None else "-"

    if is_financial:
        nim_str = ratio_fmt(ratios.get("nim"), "%") if ratios.get("nim") is not None else "-"
        profit_node = f"NIM: {nim_str}"
    else:
        gpm_str = ratio_fmt(ratios.get("gpm"), "%") if ratios.get("gpm") is not None else "-"
        npm_str = ratio_fmt(ratios.get("npm"), "%") if ratios.get("npm") is not None else "-"
        profit_node = f"GPM: {gpm_str} | NPM: {npm_str}"

    md = f"""## 📌 1. Ikhtisar Kinerja Utama / Executive Performance Highlight
- **Emiten**: `[[{emiten}]]` ({entity_name})
- **Sektor Usaha / Industry Sector**: `{sector}`
- **Periode Laporan / Reporting Period**: `{period} {year}`
- **{rev_label}**: `{rev_val}` (**{rev_yoy} YoY** dari {rev_prev})
{extra_line}
- **Laba (Rugi) Bersih / Net Income**: `{format_money(ni[0], currency, scale)}` (**{pct(ni[0], ni[1])} YoY**)
- **Total Aset / Total Assets**: `{format_money(ta[0], currency, scale)}` | **Total Ekuitas / Total Equity**: `{format_money(eq[0], currency, scale)}`
- **EPS (Annualized)**: `{eps_str}` | **BVPS**: `{bvps_str}`

```mermaid
graph TD
    A[\"🏬 {emiten} ({period} {year})<br>Revenue: {format_money(rev[0], currency, scale)}\"] --> B[\"📊 Neraca & Solvabilitas<br>DER: {der_str} | Kas: {format_money(cash[0], currency, scale)}\"]
    A --> C[\"💰 Profitabilitas<br>{profit_node}\"]
    B --> D[\"📈 Likuiditas<br>CR: {cr_str} | QR: {qr_str}\"]
    C --> E[\"🎯 Imbal Hasil (Ann.)<br>ROE: {roe_str} | ROA: {roa_str}\"]
```"""
    return md


def render_income_statement_general(pl_m, currency, scale, period, year):
    """Render Income Statement table — General/Manufacturing variant."""
    rev = pl_m["rev"]
    cogs = pl_m["cogs"]
    gp = pl_m["gp"]
    opex = pl_m["opex"]
    ebit = pl_m["ebit"]
    ni = pl_m["ni"]

    is_usd = "USD" in str(currency).upper() or "DOLLAR" in str(currency).upper()
    unit = "Ribu USD" if is_usd else "Juta Rp"

    return f"""## 📊 2. Laba Rugi Komparatif / Comparative Income Statement

| Pos Laba Rugi / Income Statement Item | {period} {year} | Prior Period | YoY (%) |
| :--- | ---: | ---: | :---: |
| **Pendapatan Neto / Net Revenue** | `{fmt(rev[0], scale)}` | `{fmt(rev[1], scale)}` | **{pct(rev[0], rev[1])}** |
| **Beban Pokok / COGS** | `({fmt(cogs[0], scale)})` | `({fmt(cogs[1], scale)})` | {pct(cogs[0], cogs[1])} |
| **Laba Bruto / Gross Profit** | `{fmt(gp[0], scale)}` | `{fmt(gp[1], scale)}` | **{pct(gp[0], gp[1])}** |
| **Beban Usaha / Operating Expenses** | `({fmt(opex[0], scale)})` | `({fmt(opex[1], scale)})` | {pct(opex[0], opex[1])} |
| **Laba Operasional / EBIT** | `{fmt(ebit[0], scale)}` | `{fmt(ebit[1], scale)}` | {pct(ebit[0], ebit[1])} |
| **Laba (Rugi) Bersih / Net Income** | **{fmt(ni[0], scale)}** | **{fmt(ni[1], scale)}** | **{pct(ni[0], ni[1])}** |"""


def render_income_statement_financial(pl_m, currency, scale, period, year):
    """Render Income Statement table — Financial/Insurance variant."""
    int_inc = pl_m.get("int_inc", (None, None))
    int_exp = pl_m.get("int_exp", (None, None))
    nii = pl_m.get("nii", (None, None))
    prem_inc = pl_m.get("prem_inc", (None, None))
    claim_exp = pl_m.get("claim_exp", (None, None))
    ppap = pl_m.get("ppap", (None, None))
    opex = pl_m.get("opex", (None, None))
    ebit = pl_m.get("ebit", (None, None))
    ni = pl_m.get("ni", (None, None))
    rev = pl_m.get("rev", (None, None))

    rows = []
    if int_inc[0] is not None:
        rows.append(f"| **Pendapatan Bunga / Interest Income** | `{fmt(int_inc[0], scale)}` | `{fmt(int_inc[1], scale)}` | {pct(int_inc[0], int_inc[1])} |")
    if int_exp[0] is not None:
        rows.append(f"| **Beban Bunga / Interest Expense** | `({fmt(int_exp[0], scale)})` | `({fmt(int_exp[1], scale)})` | {pct(int_exp[0], int_exp[1])} |")
    if nii[0] is not None:
        rows.append(f"| **Pendapatan Bunga Bersih / NII** | `{fmt(nii[0], scale)}` | `{fmt(nii[1], scale)}` | **{pct(nii[0], nii[1])}** |")
    if prem_inc[0] is not None:
        rows.append(f"| **Pendapatan Premi / Premium Income** | `{fmt(prem_inc[0], scale)}` | `{fmt(prem_inc[1], scale)}` | {pct(prem_inc[0], prem_inc[1])} |")
    if claim_exp[0] is not None:
        rows.append(f"| **Beban Klaim / Claims Expense** | `({fmt(claim_exp[0], scale)})` | `({fmt(claim_exp[1], scale)})` | {pct(claim_exp[0], claim_exp[1])} |")
    if rev[0] is not None:
        rows.append(f"| **Jumlah Pendapatan Usaha / Total Revenue** | `{fmt(rev[0], scale)}` | `{fmt(rev[1], scale)}` | {pct(rev[0], rev[1])} |")
    if ppap[0] is not None:
        rows.append(f"| **Pencadangan / Provision (PPAP)** | `({fmt(ppap[0], scale)})` | `({fmt(ppap[1], scale)})` | {pct(ppap[0], ppap[1])} |")
    if opex[0] is not None:
        rows.append(f"| **Beban Operasional / Operating Expenses** | `({fmt(opex[0], scale)})` | `({fmt(opex[1], scale)})` | {pct(opex[0], opex[1])} |")
    if ebit[0] is not None:
        rows.append(f"| **Laba Sebelum Pajak / Profit Before Tax** | `{fmt(ebit[0], scale)}` | `{fmt(ebit[1], scale)}` | {pct(ebit[0], ebit[1])} |")
    rows.append(f"| **Laba (Rugi) Bersih / Net Income** | **{fmt(ni[0], scale)}** | **{fmt(ni[1], scale)}** | **{pct(ni[0], ni[1])}** |")

    rows_str = "\n".join(rows)
    return f"""## 📊 2. Laba Rugi Komparatif / Comparative Income Statement (Financial Sector)

| Pos Laba Rugi / Income Statement Item | {period} {year} | Prior Period | YoY (%) |
| :--- | ---: | ---: | :---: |
{rows_str}"""


def render_balance_sheet(bs_m, currency, scale, period, year, with_pie=True):
    """Render Balance Sheet section."""
    ca = bs_m["ca"]
    nca = bs_m["nca"]
    ta = bs_m["ta"]
    cl = bs_m["cl"]
    ncl = bs_m["ncl"]
    tl = bs_m["tl"]
    eq = bs_m["eq"]
    cash = bs_m["cash"]

    md = f"""## 🏦 3. Neraca & Struktur Permodalan / Balance Sheet & Capital Structure

| Pos Neraca / Balance Sheet Item | {period} {year} | Prior Year End | Δ YoY/YtD (%) | Catatan / Notes |
| :--- | ---: | ---: | :---: | :--- |
| **Aset Lancar / Current Assets** | `{fmt(ca[0], scale)}` | `{fmt(ca[1], scale)}` | {pct(ca[0], ca[1])} | Kas: {format_money(cash[0], currency, scale)} |
| **Aset Tidak Lancar / Non-Current Assets** | `{fmt(nca[0], scale)}` | `{fmt(nca[1], scale)}` | {pct(nca[0], nca[1])} | Aset Tetap & Operasional |
| **TOTAL ASET / TOTAL ASSETS** | **{fmt(ta[0], scale)}** | **{fmt(ta[1], scale)}** | **{pct(ta[0], ta[1])}** | |
| **Liabilitas Jk. Pendek / Current Liabilities** | `{fmt(cl[0], scale)}` | `{fmt(cl[1], scale)}` | {pct(cl[0], cl[1])} | |
| **Liabilitas Jk. Panjang / Non-Current Liabilities** | `{fmt(ncl[0], scale)}` | `{fmt(ncl[1], scale)}` | {pct(ncl[0], ncl[1])} | |
| **TOTAL LIABILITAS / TOTAL LIABILITIES** | **{fmt(tl[0], scale)}** | **{fmt(tl[1], scale)}** | **{pct(tl[0], tl[1])}** | |
| **TOTAL EKUITAS / TOTAL EQUITY** | **{fmt(eq[0], scale)}** | **{fmt(eq[1], scale)}** | **{pct(eq[0], eq[1])}** | |"""

    if with_pie and ta[0] and tl[0] and eq[0]:
        # Compute percentages for pie chart
        tl_pct = abs(tl[0]) / abs(ta[0]) * 100 if ta[0] else 0
        eq_pct = abs(eq[0]) / abs(ta[0]) * 100 if ta[0] else 0
        ca_pct = abs(ca[0]) / abs(ta[0]) * 100 if ta[0] and ca[0] else 0
        nca_pct = abs(nca[0]) / abs(ta[0]) * 100 if ta[0] and nca[0] else 0

        md += f"""

```mermaid
pie title Komposisi Aset / Asset Composition
    "Aset Lancar / CA" : {ca_pct:.1f}
    "Aset Tidak Lancar / NCA" : {nca_pct:.1f}
```

```mermaid
pie title Sumber Pendanaan / Funding Structure
    "Liabilitas / Liabilities" : {tl_pct:.1f}
    "Ekuitas / Equity" : {eq_pct:.1f}
```"""

    return md


def render_cash_flow(cf_m, currency, scale, period, year):
    """Render Cash Flow Statement section (Q2 + FY only)."""
    cfo = cf_m["cfo"]
    cfi = cf_m["cfi"]
    cff = cf_m["cff"]
    net = cf_m["net"]
    capex = cf_m["capex"]
    div_paid = cf_m["div_paid"]

    # Free Cash Flow = CFO - Capex
    fcf_c = None
    if cfo[0] is not None and capex[0] is not None:
        fcf_c = cfo[0] - abs(capex[0])
    fcf_p = None
    if cfo[1] is not None and capex[1] is not None:
        fcf_p = cfo[1] - abs(capex[1])

    return f"""## 💸 4. Laporan Arus Kas / Cash Flow Statement

| Komponen Arus Kas / Cash Flow Component | {period} {year} | Prior Period | Δ YoY (%) |
| :--- | ---: | ---: | :---: |
| **Arus Kas Operasi / CFO** | `{fmt(cfo[0], scale)}` | `{fmt(cfo[1], scale)}` | {pct(cfo[0], cfo[1])} |
| **Arus Kas Investasi / CFI** | `{fmt(cfi[0], scale)}` | `{fmt(cfi[1], scale)}` | {pct(cfi[0], cfi[1])} |
| **Arus Kas Pendanaan / CFF** | `{fmt(cff[0], scale)}` | `{fmt(cff[1], scale)}` | {pct(cff[0], cff[1])} |
| **Kenaikan (Penurunan) Kas Bersih** | `{fmt(net[0], scale)}` | `{fmt(net[1], scale)}` | {pct(net[0], net[1])} |
| Belanja Modal / Capex | `({fmt(capex[0], scale)})` | `({fmt(capex[1], scale)})` | {pct(capex[0], capex[1])} |
| Pembayaran Dividen / Dividends Paid | `({fmt(div_paid[0], scale)})` | `({fmt(div_paid[1], scale)})` | {pct(div_paid[0], div_paid[1])} |
| **Free Cash Flow (CFO - Capex)** | **{fmt(fcf_c, scale)}** | **{fmt(fcf_p, scale)}** | **{pct(fcf_c, fcf_p)}** |"""


def render_ratios_table(ratios, is_financial):
    """Render Financial Ratios table (all tiers)."""
    rows = []

    # Liquidity
    rows.append(f"| **🛡️ Likuiditas** | **Current Ratio** | `{ratio_fmt(ratios.get('cr'), 'x')}` | `> 1.0x` | Kemampuan bayar kewajiban jk. pendek |")
    rows.append(f"| | **Quick Ratio** | `{ratio_fmt(ratios.get('qr'), 'x')}` | `> 0.8x` | Likuiditas tanpa persediaan |")

    # Profitability
    if not is_financial:
        rows.append(f"| **📊 Profitabilitas** | **Gross Profit Margin (GPM)** | `{ratio_fmt(ratios.get('gpm'), '%')}` | - | Margin kotor operasional inti |")
        rows.append(f"| | **Operating Profit Margin (OPM)** | `{ratio_fmt(ratios.get('opm'), '%')}` | - | Efisiensi operasional |")
        rows.append(f"| | **Net Profit Margin (NPM)** | `{ratio_fmt(ratios.get('npm'), '%')}` | - | Konversi revenue ke laba bersih |")
    else:
        if ratios.get("nim") is not None:
            rows.append(f"| **📊 Profitabilitas** | **Net Interest Margin (NIM)** | `{ratio_fmt(ratios.get('nim'), '%')}` | `> 3.0%` | Spread pendapatan bunga bersih |")
        if ratios.get("bopo") is not None:
            rows.append(f"| | **BOPO / Cost-to-Income Ratio** | `{ratio_fmt(ratios.get('bopo'), '%')}` | `< 80%` | Efisiensi biaya operasional |")

    # Return metrics (annualized)
    rows.append(f"| **🎯 Imbal Hasil (Ann.)** | **Return on Equity (ROE)** | `{ratio_fmt(ratios.get('roe'), '%')}` | - | Imbal hasil terhadap ekuitas |")
    rows.append(f"| | **Return on Assets (ROA)** | `{ratio_fmt(ratios.get('roa'), '%')}` | - | Produktivitas aset |")

    # Solvency
    rows.append(f"| **⚖️ Solvabilitas** | **Debt to Equity (DER)** | `{ratio_fmt(ratios.get('der'), 'x')}` | `< 2.0x` | Leverage utang vs modal |")
    rows.append(f"| | **Debt to Asset (DAR)** | `{ratio_fmt(ratios.get('dar'), 'x')}` | `< 0.7x` | Porsi aset didanai utang |")

    rows_str = "\n".join(rows)

    section_num = "5" if not is_financial else "5"  # Numbering depends on tier, but we handle in orchestrator
    return f"""## 📈 Analisis Rasio Keuangan / Financial Ratio Analysis

| Kategori / Category | Metrik / Metric | Nilai / Value | Benchmark | Interpretasi / Interpretation |
| :--- | :--- | :---: | :---: | :--- |
{rows_str}"""


def render_per_share_metrics(eps, bvps, currency, period, year):
    """Render Per Share Metrics section (Q2 + FY only)."""
    is_usd = "USD" in str(currency).upper() or "DOLLAR" in str(currency).upper()
    curr_sym = "USD" if is_usd else "Rp"
    eps_str = f"{curr_sym} {eps:,.2f}" if eps is not None else "-"
    bvps_str = f"{curr_sym} {bvps:,.2f}" if bvps is not None else "-"

    return f"""## 📐 Per Share Metrics

| Metrik / Metric | Nilai / Value | Keterangan / Notes |
| :--- | ---: | :--- |
| **EPS (Annualized)** | `{eps_str}` | Laba per saham (dianualisasi) |
| **BVPS** | `{bvps_str}` | Nilai buku per saham |"""


def render_sector_analysis(emiten, entity_name, sector, currency, scale, period, year,
                           pl_m, bs_m, ratios, is_financial, pl_variant):
    """Render Sector-Adaptive Analysis section (Q2 + FY only)."""
    # Look up Public Expose KPIs
    pubex = lookup_pubex_kpis(emiten)

    # Generate narrative
    if is_financial:
        ni = pl_m.get("ni", (None, None))
        rev = pl_m.get("rev", (None, None))
    else:
        ni = pl_m.get("ni", (None, None))
        rev = pl_m.get("rev", (None, None))
        gp = pl_m.get("gp", (None, None))

    ta = bs_m["ta"]
    eq = bs_m["eq"]

    narrative = (
        f"Pada periode {period} {year}, **{entity_name} ([[{emiten}]])** membukukan "
        f"total pendapatan sebesar **{format_money(rev[0], currency, scale)}** "
        f"({pct(rev[0], rev[1])} YoY). "
    )

    if not is_financial and pl_m.get("gp"):
        gp = pl_m["gp"]
        narrative += (
            f"Laba kotor tercatat **{format_money(gp[0], currency, scale)}** "
            f"dengan GPM **{ratio_fmt(ratios.get('gpm'), '%')}**. "
        )

    narrative += (
        f"Laba bersih sebesar **{format_money(ni[0], currency, scale)}** "
        f"({pct(ni[0], ni[1])} YoY). "
        f"Total aset **{format_money(ta[0], currency, scale)}**, "
        f"ekuitas **{format_money(eq[0], currency, scale)}**, "
        f"DER **{ratio_fmt(ratios.get('der'), 'x')}**."
    )

    # Sector-specific KPI section
    sector_kpis = _get_sector_kpi_text(sector, ratios, pl_variant)

    # Public Expose integration
    pubex_section = ""
    if pubex and pubex.get("kpis"):
        kpi_lines = "\n".join(pubex["kpis"])
        pubex_section = f"""
### 📋 Data Operasional dari Public Expose / Operational Data from Public Expose
> Sumber: `{pubex['source_file']}`

{kpi_lines}"""
    else:
        pubex_section = """
> [!NOTE]
> _Data Public Expose / Investor Presentation belum tersedia untuk emiten ini._"""

    return f"""## 🚀 Analisis Strategis & Karakteristik Sektor / Strategic Analysis: {sector}

{narrative}

### 🔍 Indikator Kunci Sektor / Sector Key Indicators ({sector})
{sector_kpis}
{pubex_section}"""


def _get_sector_kpi_text(sector, ratios, pl_variant):
    """Get sector-specific KPI text."""
    if pl_variant == "financial":
        return (
            "- **Karakteristik Industri Finansial / Financial Industry**: Kinerja ditopang oleh spread pendapatan bunga (NIM), "
            "hasil investasi, dan pengelolaan Cost of Funds.\n"
            "- **Kualitas Aset / Asset Quality**: Pengawasan rasio NPL/NPF dan kecukupan pencadangan (PPAP) "
            "untuk menjaga stabilitas margin usaha.\n"
            "- **Solvabilitas / Solvency**: Rasio kecukupan modal (CAR/RBC) ketat sesuai regulasi OJK."
        )
    elif pl_variant == "mining":
        return (
            "- **Karakteristik Industri Tambang & Komoditas / Mining & Commodity**: Kinerja dipengaruhi oleh "
            "Average Selling Price (ASP), volume produksi/pengapalan, dan efisiensi Cash Cost per ton.\n"
            "- **Profil Arus Kas / Cash Flow Profile**: Arus kas operasional yang solid menopang dividen berkala "
            "dan ekspansi hilirisasi / transisi energi.\n"
            "- **Regulasi & ESG**: Kewajiban reklamasi, royalti pemerintah, dan komitmen keberlanjutan."
        )
    elif pl_variant == "infra":
        return (
            "- **Karakteristik Infrastruktur & Transportasi**: Kinerja didorong oleh pertumbuhan volume "
            "Lalu Lintas Harian Rata-rata (LHR) dan penyesuaian tarif berkala.\n"
            "- **Struktur Leverage / Leverage Structure**: Pengelolaan liabilitas jangka panjang yang terukur "
            "seiring masa konsesi.\n"
            "- **Recurring Revenue**: Pendapatan tol/sewa/transport bersifat recurring dan predictable."
        )
    elif "Agrikultur" in sector:
        return (
            "- **Karakteristik Perkebunan & Agribisnis**: Dipengaruhi harga CPO/komoditas global, "
            "Oil Extraction Rate (OER), dan umur tanaman.\n"
            "- **Efisiensi Produksi**: Pengendalian biaya pupuk, logistik, dan pemeliharaan PKS.\n"
            "- **Siklus Musiman**: Produksi TBS mengikuti pola musiman curah hujan."
        )
    elif "Kesehatan" in sector:
        return (
            "- **Karakteristik Layanan Kesehatan**: Margin kotor tebal dari layanan medis spesialis "
            f"(GPM: **{ratio_fmt(ratios.get('gpm'), '%')}**).\n"
            "- **Penggerak Pertumbuhan**: Volume kunjungan pasien, ekspansi cabang baru, "
            "dan akuisisi teknologi diagnostik.\n"
            "- **Capex Intensif**: Investasi berkelanjutan pada peralatan medis dan fasilitas."
        )
    elif "Teknologi" in sector or "Telekomunikasi" in sector:
        return (
            "- **Karakteristik Industri IT & Cybersecurity**: Stabilitas margin kotor tinggi "
            f"(GPM: **{ratio_fmt(ratios.get('gpm'), '%')}**), beban terbesar pada remunerasi tenaga ahli.\n"
            "- **Model Pendapatan**: Managed Security Services (MSSP), lisensi software, "
            "dan integrasi enterprise (project-based).\n"
            "- **Working Capital**: DSO dan pengelolaan piutang B2B kritis untuk likuiditas."
        )
    elif "Properti" in sector or "Konstruksi" in sector:
        return (
            "- **Karakteristik Konstruksi & Properti**: Pertumbuhan bertumpu pada perolehan "
            "kontrak baru (Order Book) dan percepatan progres fisik proyek.\n"
            "- **Modal Kerja**: Restrukturisasi liabilitas dan pengelolaan arus kas proyek.\n"
            "- **Katalis**: Presales/marketing sales, groundbreaking proyek baru, dan penyerahan unit."
        )
    else:
        return (
            f"- **Karakteristik Industri ({sector})**: Kinerja mencerminkan dinamika penyerapan pasar, "
            "utilisasi kapasitas produksi, dan efisiensi biaya pokok.\n"
            "- **Faktor Penggerak**: Pertumbuhan organik, efisiensi operasional, dan ekspansi pasar."
        )


def render_calk_highlights(emiten, pdf_path, period, year, auditor_info):
    """Render CALK highlights section (Q2 + FY only)."""
    calk_data = None
    if extract_calk_highlights and pdf_path:
        try:
            calk_data = extract_calk_highlights(pdf_path, emiten, period, year)
        except Exception as e:
            print(f"      [!] CALK extraction failed: {e}")

    md = "## 📋 Catatan Kunci Laporan Keuangan / Key Notes to Financial Statements\n\n"

    # Auditor opinion (from XBRL fallback)
    opini = auditor_info.get("opini", "")
    kap = auditor_info.get("kap", "")
    tgl = auditor_info.get("tanggal", "")
    hasil = auditor_info.get("hasil_review", "")
    partner = auditor_info.get("partner", "")

    md += "### 🔍 Opini Auditor / Auditor Opinion\n"
    if opini or hasil or kap:
        md += f"- **Jenis Opini / Opinion Type**: `{opini or 'Reviu Terbatas / Limited Review'}`\n"
        md += f"- **KAP / Audit Firm**: `{kap}`\n"
        if partner:
            md += f"- **Partner Audit**: `{partner}`\n"
        if tgl:
            md += f"- **Tanggal Laporan / Report Date**: `{tgl}`\n"
        if hasil:
            md += f"- **Kesimpulan**: _{hasil[:300]}{'...' if len(hasil) > 300 else ''}_\n"
    else:
        md += "- _Informasi opini auditor tidak tersedia._\n"

    if calk_data:
        # Contracts & Agreements
        contracts = calk_data.get("perjanjian_kontrak", [])
        if contracts:
            md += "\n### 📝 Perjanjian & Kontrak Signifikan / Key Contracts & Agreements\n"
            for c in contracts[:5]:
                md += f"- {c}\n"

        # Subsequent Events
        events = calk_data.get("subsequent_events", [])
        if events:
            md += "\n### ⏩ Peristiwa Setelah Tanggal Pelaporan / Subsequent Events\n"
            for e in events[:5]:
                md += f"- {e}\n"

        # Related Party
        rp = calk_data.get("related_party", [])
        if rp:
            md += "\n### 🤝 Transaksi Pihak Berelasi / Related Party Transactions\n"
            for r in rp[:5]:
                md += f"- {r}\n"

        # Contingencies
        cont = calk_data.get("komitmen_kontinjensi", [])
        if cont:
            md += "\n### ⚠️ Komitmen & Kontinjensi / Commitments & Contingencies\n"
            for c in cont[:5]:
                md += f"- {c}\n"
    else:
        md += "\n> [!NOTE]\n> _Ekstraksi CALK otomatis belum tersedia. Data kualitatif akan ditambahkan pada pembaruan berikutnya._\n"

    return md


def render_investor_notes(ratios, is_financial, sector):
    """Render strategic notes for investors."""
    der = ratios.get("der")
    cr = ratios.get("cr")

    health = "sehat dan aman" if (der and der < 1.5 and cr and cr > 1.2) else "perlu dipantau secara disiplin"

    md = f"""## 💡 Catatan Strategis & Panduan Investor / Strategic Notes & Investor Guide

1. **Kesehatan Permodalan / Capital Health**: DER **{ratio_fmt(der, 'x')}**, CR **{ratio_fmt(cr, 'x')}** — _{health}_.
2. **Katalis Pertumbuhan / Growth Catalysts**: Pantau realisasi pendapatan dan efisiensi operasional periode berikutnya."""

    if is_financial:
        nim = ratios.get("nim")
        md += f"\n3. **Kualitas Aset Finansial**: Pantau tren NIM (**{ratio_fmt(nim, '%')}**) dan kualitas portofolio kredit/pembiayaan."

    return md


def render_knowledge_graph(emiten, today_str):
    """Render Knowledge Graph links section (all tiers)."""
    date_fmt = datetime.now().strftime('%Y%m%d')
    return f"""## 🔗 Hubungan Note Terkait / Knowledge Graph Links
- [[knowledge-base/daily-digests/Daily_Digest_{date_fmt}|📄 Daily Digest {today_str}]]
- [[knowledge-base/trading-signals/Trading_Signals_{date_fmt}|🎯 Trading Signals]]
- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]"""


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9: Template Tier Orchestrators
# ═══════════════════════════════════════════════════════════════════════════════

def render_template_interim(emiten, entity_name, sector, period, year, currency, scale,
                            pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
                            is_financial, pl_variant, today_str, frontmatter):
    """Render Q1/Q3 Interim template (compact)."""
    sections = []
    sections.append(frontmatter)
    sections.append(f"# 📈 Laporan Keuangan Interim: [[{emiten}]] — {period} {year}\n")
    sections.append(f"📅 **{today_str}** | 🎛️ [[Dashboard|Ke Dashboard Utama]]\n")
    sections.append("> [!NOTE]")
    sections.append(f"> Laporan interim ringkas **{entity_name} ([[{emiten}]])** — Sektor: {sector}.\n")
    sections.append("---\n")

    sections.append(render_executive_summary(
        emiten, entity_name, sector, period, year, currency, scale,
        pl_m, bs_m, ratios, eps, bvps, is_financial, today_str))
    sections.append("\n---\n")

    # Income Statement
    if is_financial:
        sections.append(render_income_statement_financial(pl_m, currency, scale, period, year))
    else:
        sections.append(render_income_statement_general(pl_m, currency, scale, period, year))
    sections.append("\n---\n")

    sections.append(render_balance_sheet(bs_m, currency, scale, period, year, with_pie=False))
    sections.append("\n---\n")
    sections.append(render_ratios_table(ratios, is_financial))
    sections.append("\n---\n")
    sections.append(render_knowledge_graph(emiten, today_str))

    return "\n".join(sections)


def render_template_semester(emiten, entity_name, sector, period, year, currency, scale,
                             pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
                             is_financial, pl_variant, today_str, frontmatter,
                             pdf_path, auditor_info):
    """Render Q2 Semester template (full)."""
    sections = []
    sections.append(frontmatter)
    sections.append(f"# 📈 Laporan Analisis Keuangan Mendalam: [[{emiten}]] — {period} {year}\n")
    date_fmt = datetime.now().strftime('%Y%m%d')
    sections.append(f"⬅️ [[knowledge-base/daily-digests/Daily_Digest_{date_fmt}|Kembali ke Daily Digest]] | 📅 **{today_str}** | 🎛️ [[Dashboard|Ke Dashboard Utama]]\n")
    sections.append("> [!IMPORTANT]")
    sections.append(f"> Dokumen ini disusun oleh **Financial Summarizer Agent** untuk menganalisis kinerja keuangan, kesehatan neraca, profitabilitas, dan katalis sektor ({sector}) **{entity_name} ([[{emiten}]])** berdasarkan LK {period} {year}.\n")
    sections.append("---\n")

    sections.append(render_executive_summary(
        emiten, entity_name, sector, period, year, currency, scale,
        pl_m, bs_m, ratios, eps, bvps, is_financial, today_str))
    sections.append("\n---\n")

    if is_financial:
        sections.append(render_income_statement_financial(pl_m, currency, scale, period, year))
    else:
        sections.append(render_income_statement_general(pl_m, currency, scale, period, year))
    sections.append("\n---\n")

    sections.append(render_balance_sheet(bs_m, currency, scale, period, year, with_pie=True))
    sections.append("\n---\n")

    sections.append(render_cash_flow(cf_m, currency, scale, period, year))
    sections.append("\n---\n")

    sections.append(render_ratios_table(ratios, is_financial))
    sections.append("\n---\n")

    sections.append(render_per_share_metrics(eps, bvps, currency, period, year))
    sections.append("\n---\n")

    sections.append(render_sector_analysis(
        emiten, entity_name, sector, currency, scale, period, year,
        pl_m, bs_m, ratios, is_financial, pl_variant))
    sections.append("\n---\n")

    sections.append(render_calk_highlights(emiten, pdf_path, period, year, auditor_info))
    sections.append("\n---\n")

    sections.append(render_investor_notes(ratios, is_financial, sector))
    sections.append("\n---\n")

    sections.append(render_knowledge_graph(emiten, today_str))

    return "\n".join(sections)


def render_template_annual(emiten, entity_name, sector, period, year, currency, scale,
                           pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
                           is_financial, pl_variant, today_str, frontmatter,
                           pdf_path, auditor_info):
    """Render FY Annual template (most comprehensive)."""
    # Start with semester template as base
    md = render_template_semester(
        emiten, entity_name, sector, period, year, currency, scale,
        pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
        is_financial, pl_variant, today_str, frontmatter,
        pdf_path, auditor_info)

    # Add FY-specific sections before Knowledge Graph
    kg_marker = "## 🔗 Hubungan Note Terkait"
    if kg_marker in md:
        # Insert additional FY sections before Knowledge Graph
        fy_extras = []

        # Dividend info from CF
        div_paid = cf_m["div_paid"]
        ni_c = pl_m.get("ni", (None, None))[0]
        if div_paid[0] is not None and ni_c is not None and ni_c != 0:
            payout = abs(div_paid[0]) / abs(ni_c) * 100
            fy_extras.append(f"""## 💰 Informasi Dividen / Dividend Information

| Metrik / Metric | Nilai / Value |
| :--- | ---: |
| **Total Dividen Dibayarkan / Dividends Paid** | `{format_money(div_paid[0], currency, scale)}` |
| **Dividend Payout Ratio** | `{payout:.1f}%` |
| **Laba Bersih (Basis)** | `{format_money(ni_c, currency, scale)}` |

---
""")

        # Note about multi-year trend
        fy_extras.append("""## 📊 Trend Multi-Tahun / Multi-Year Trend

> [!NOTE]
> _Tabel trend multi-tahun (3 tahun) akan tersedia setelah data historis FY sebelumnya diproses._

---
""")

        extra_str = "\n".join(fy_extras)
        md = md.replace(kg_marker, extra_str + kg_marker)

    # Update title
    md = md.replace("Laporan Analisis Keuangan Mendalam", "Laporan Analisis Keuangan Tahunan Komprehensif")

    return md


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10: Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def build_financial_summary(emiten, filename, file_path):
    """Main entry point: build a financial summary from an XBRL workbook or PDF fallback."""
    emiten = emiten.upper().strip()
    emiten_dir = os.path.dirname(file_path)

    # ── Guard: skip cover letters and pure administrative PDFs ────────────────
    fn_lc = filename.lower()
    SKIP_KW = ["surat pengantar", "penyampaian laporan", "checklist", "cover letter",
               "bukti penyampaian", "lampiran surat", "pengantar penyampaian"]
    if any(kw in fn_lc for kw in SKIP_KW):
        print(f"      [~] Skipping administrative file: {filename}")
        return None

    # ── Handle KOREKSI / RESTATEMENT files ───────────────────────────────────
    if _is_koreksi_file(filename):
        print(f"      [KOREKSI] Detected correction file: {filename}")
        # Find if the corrected XLSX sibling is available
        sibling_xlsx = None
        for f in os.listdir(emiten_dir):
            if f.lower().endswith(".xlsx") and "financialstatement" in f.lower():
                sibling_xlsx = os.path.join(emiten_dir, f)
                break
        if sibling_xlsx:
            print(f"      [KOREKSI] Rebuilding summary using corrected XLSX: {os.path.basename(sibling_xlsx)}")
            return build_financial_summary(emiten, os.path.basename(sibling_xlsx), sibling_xlsx)
        else:
            # No XLSX sibling — try to rebuild from the largest PDF (which may be the corrected FS)
            pdfs = [(f, os.path.getsize(os.path.join(emiten_dir, f)))
                    for f in os.listdir(emiten_dir)
                    if f.lower().endswith(".pdf") and not _is_koreksi_file(f)]
            if pdfs:
                pdfs.sort(key=lambda x: x[1], reverse=True)
                best_pdf = os.path.join(emiten_dir, pdfs[0][0])
                print(f"      [KOREKSI] No XLSX found, rebuilding from largest PDF: {pdfs[0][0]}")
                return build_financial_summary(emiten, pdfs[0][0], best_pdf)
            print(f"      [KOREKSI] No XLSX or FS PDF found for {emiten} — skip")
            return None

    # ── Locate XLSX (XBRL workbook) ───────────────────────────────────────────
    xlsx_path = None
    if file_path.lower().endswith(".xlsx"):
        xlsx_path = file_path
    else:
        # Try to find an XLSX sibling in the same folder
        for f in sorted(os.listdir(emiten_dir), reverse=True):  # newest first
            if f.lower().endswith(".xlsx") and "financialstatement" in f.lower():
                xlsx_path = os.path.join(emiten_dir, f)
                break

    # ── Parse financial data ──────────────────────────────────────────────────
    fin_data = None
    used_pdf_fallback = False

    if xlsx_path and os.path.exists(xlsx_path):
        fin_data = parse_financial_xlsx(xlsx_path)
        if not fin_data:
            print(f"      [!] XLSX parse failed for {emiten} -- trying PDF fallback")

    if not fin_data:
        # PDF fallback: smart 3-tier selection to avoid picking wrong files
        # Non-FS files that often co-exist in the same folder:
        NON_FS_KW = [
            "public expose", "pubex", "investor meeting",
            "laporan informasi", "fakta material", "pengumuman",
            "surat pengantar", "penyampaian", "checklist",
            "cover letter", "bukti penyampaian", "lampiran surat",
            "pengantar penyampaian", "rups", "rencana transaksi",
            "tanggapan", "permintaan penjelasan", "siaran pers",
            "press release", "keterbukaan informasi",
        ]

        all_pdfs = os.listdir(emiten_dir) if os.path.isdir(emiten_dir) else []

        def _is_non_fs(fname):
            fl = fname.lower()
            if _is_koreksi_file(fl):
                return True
            return any(kw in fl for kw in NON_FS_KW)

        # Tier 1: IDX XBRL-standard FinancialStatement-*.pdf
        tier1 = [(f, os.path.getsize(os.path.join(emiten_dir, f)))
                 for f in all_pdfs
                 if f.lower().endswith(".pdf") and "financialstatement" in f.lower()
                 and not _is_non_fs(f)]

        # Tier 2: PDF with FS-like name patterns (contains "fs " or "laporan keuangan" or emiten name)
        tier2 = [(f, os.path.getsize(os.path.join(emiten_dir, f)))
                 for f in all_pdfs
                 if f.lower().endswith(".pdf")
                 and f not in [t[0] for t in tier1]
                 and not _is_non_fs(f)
                 and any(kw in f.lower() for kw in [
                     "fs ", "fs-", " fs ", "laporan keuangan",
                     "financial statement", "audit report", "limited review",
                     "penjelasan perubahan"
                 ])]

        # Tier 3: largest remaining PDF that isn't a known non-FS file
        tier3 = [(f, os.path.getsize(os.path.join(emiten_dir, f)))
                 for f in all_pdfs
                 if f.lower().endswith(".pdf")
                 and f not in [t[0] for t in tier1 + tier2]
                 and not _is_non_fs(f)]

        candidate_pdfs = tier1 or tier2 or tier3

        if candidate_pdfs:
            candidate_pdfs.sort(key=lambda x: x[1], reverse=True)
            best_pdf_name, best_pdf_size = candidate_pdfs[0]
            best_pdf_path = os.path.join(emiten_dir, best_pdf_name)
            tier_used = "Tier1" if tier1 else ("Tier2" if tier2 else "Tier3")
            print(f"      [PDF-Fallback] {emiten}: No XLSX available. "
                  f"Using {tier_used} PDF: {best_pdf_name} ({best_pdf_size//1024} KB)")
            fin_data = parse_financial_pdf(best_pdf_path, emiten)
            used_pdf_fallback = True

    if not fin_data:
        print(f"      [!] No parseable financial data found for {emiten} (no XLSX or readable PDF)")
        return None

    # Determine period
    period = fin_data.get("period_type", "")
    if not period:
        # Fallback: detect from filename
        fn_upper = filename.upper()
        if "-I-" in fn_upper or "Q1" in fn_upper:
            period = "Q1"
        elif "-II-" in fn_upper or "Q2" in fn_upper:
            period = "Q2"
        elif "-III-" in fn_upper or "Q3" in fn_upper:
            period = "Q3"
        elif "TAHUNAN" in fn_upper or "FY" in fn_upper or "-IV-" in fn_upper:
            period = "FY"
        else:
            period = "Q2"  # Default

    # Determine year
    year_match = re.search(r"202[4-9]", filename)
    year = year_match.group(0) if year_match else str(datetime.now().year)

    # Core data
    entity_name = fin_data.get("entity_name", emiten)
    currency = fin_data.get("currency", "IDR")
    scale = fin_data.get("scale", 1.0)
    sector_raw = fin_data.get("sector_raw", "")
    sector = get_emiten_sector(emiten, sector_raw)
    is_financial = fin_data.get("is_financial_sector", False)
    auditor_info = fin_data.get("auditor_info", {})
    shares = fin_data.get("shares_outstanding")

    # Extract metrics
    pl_data = fin_data.get("pl", {})
    bs_data = fin_data.get("bs", {})
    cf_data = fin_data.get("cf", {})

    pl_variant = classify_pl_variant(sector, pl_data)

    if pl_variant == "financial":
        pl_m = extract_financial_pl(pl_data)
        is_financial = True
    else:
        pl_m = extract_general_pl(pl_data)

    bs_m = extract_bs(bs_data)
    cf_m = extract_cf(cf_data)

    # Compute ratios
    ratios = compute_ratios(bs_m, pl_m, period, is_financial)

    # Compute per share metrics
    ni_c = pl_m.get("ni", (None, None))[0]
    eq_c = bs_m["eq"][0]
    eps, bvps = compute_per_share(ni_c, eq_c, shares, scale, period)

    # Find PDF for CALK extraction
    pdf_path = None
    if os.path.exists(emiten_dir):
        pdfs = [(f, os.path.getsize(os.path.join(emiten_dir, f)))
                for f in os.listdir(emiten_dir) if f.lower().endswith(".pdf")]
        if pdfs:
            pdfs.sort(key=lambda x: x[1], reverse=True)
            pdf_path = os.path.join(emiten_dir, pdfs[0][0])

    # Build YAML frontmatter
    today_str = datetime.now().strftime("%Y-%m-%d")
    frontmatter = build_yaml_frontmatter(
        emiten, entity_name, sector, period, year, currency, scale,
        pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
        is_financial, pl_variant)

    # Select template tier and render
    if period in ("Q1", "Q3"):
        md = render_template_interim(
            emiten, entity_name, sector, period, year, currency, scale,
            pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
            is_financial, pl_variant, today_str, frontmatter)
    elif period == "FY":
        md = render_template_annual(
            emiten, entity_name, sector, period, year, currency, scale,
            pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
            is_financial, pl_variant, today_str, frontmatter,
            pdf_path, auditor_info)
    else:  # Q2 (default semester)
        md = render_template_semester(
            emiten, entity_name, sector, period, year, currency, scale,
            pl_m, bs_m, cf_m, ratios, eps, bvps, shares,
            is_financial, pl_variant, today_str, frontmatter,
            pdf_path, auditor_info)

    # Save
    report_filename = f"{emiten}_{year}_{period}_Summary.md"
    out_path = os.path.join(REPORTS_DIR, report_filename)

    # Append PDF-fallback caveat if data came from LLM-parsed PDF
    if used_pdf_fallback:
        pdf_caveat = (
            "\n\n---\n"
            "> [!WARNING] **Data Sumber: PDF (LLM-Extracted)**\n"
            "> Laporan ini dibuat dari ekstraksi PDF via LLM karena tidak tersedia XBRL workbook (.xlsx) dari IDX.\n"
            "> Angka-angka yang ditampilkan mungkin kurang presisi dibanding laporan berbasis XBRL.\n"
            "> Verifikasi manual disarankan sebelum digunakan sebagai dasar keputusan investasi.\n"
        )
        md = md + pdf_caveat

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    source_tag = " [PDF-Regex]" if used_pdf_fallback else ""
    print(f"[+] Financial Summary created{source_tag}: {out_path}")
    push_to_obsidian(f"financial-summaries/{report_filename}", md)
    return out_path
