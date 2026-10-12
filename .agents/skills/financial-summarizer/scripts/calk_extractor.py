"""
CALK Extractor Module (Catatan Atas Laporan Keuangan)
Extracts qualitative disclosures and footnotes from Indonesian Stock Exchange (IDX/BEI)
PDF financial reports using PyMuPDF (fitz) and LLM-powered structured extraction.

Key Capabilities:
1. Smart page scanning for CALK keywords (kontrak, subsequent events, related party, opini auditor, kontinjensi).
2. Token-budget optimized page filtering (max 25 pages).
3. 7-day disk caching to avoid redundant LLM invocations.
4. Robust XBRL sheet 1000000 fallback parser for auditor opinions.
5. Fail-safe design to prevent pipeline crashes.
"""

import os
import sys
import re
import time
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

import fitz  # PyMuPDF

# ==============================================================================
# PATHS AND ENVIRONMENT SETUP
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# BASE_DIR is root of Model2 repo: 4 levels up from scripts directory
BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
AGENTS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
CACHE_DIR = os.path.join(REPORTS_DIR, "cache", "calk")
RAW_DIR = os.path.join(REPORTS_DIR, "raw")

if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)

try:
    import env_loader
except Exception:
    pass

try:
    import llm_client
except Exception:
    llm_client = None

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

# ==============================================================================
# KEYWORD DICTIONARIES FOR SMART PAGE SELECTION
# ==============================================================================
CALK_KEYWORDS = {
    "perjanjian_kontrak": [
        "perjanjian",
        "kontrak",
        "agreement",
        "contract",
        "komitmen sewa",
        "perjanjian pinjaman",
        "fasilitas kredit",
        "perjanjian kerjasama",
    ],
    "subsequent_events": [
        "peristiwa setelah",
        "subsequent event",
        "setelah tanggal pelaporan",
        "setelah tanggal neraca",
        "peristiwa setelah periode pelaporan",
        "subsequent events",
    ],
    "related_party": [
        "pihak berelasi",
        "related party",
        "pihak-pihak berelasi",
        "transaksi pihak berelasi",
        "saldo dan transaksi dengan pihak berelasi",
    ],
    "opini_auditor": [
        "laporan auditor",
        "auditor report",
        "opini",
        "pendapat",
        "tanggung jawab auditor",
        "reviu",
        "laporan auditor independen",
        "independent auditors' report",
    ],
    "komitmen_kontinjensi": [
        "kontinjensi",
        "contingent",
        "komitmen",
        "commitment",
        "litigasi",
        "litigation",
        "perkara hukum",
        "tuntutan hukum",
        "garansi bank",
    ],
}


def get_default_calk_result(source_pages: Optional[List[int]] = None) -> Dict[str, Any]:
    """Returns a fresh empty CALK result structure."""
    return {
        "perjanjian_kontrak": [],
        "subsequent_events": [],
        "related_party": [],
        "opini_auditor": {
            "jenis": "",
            "kap": "",
            "tanggal": "",
            "penekanan": "",
        },
        "komitmen_kontinjensi": [],
        "source_pages": source_pages or [],
    }


def find_largest_pdf(emiten: str, raw_dir: Optional[str] = None) -> Optional[str]:
    """
    Finds the largest PDF file in reports/raw/{EMITEN}/.
    The largest PDF is typically the complete Financial Statement with full CALK.
    """
    if not emiten:
        return None
    raw_path = raw_dir or RAW_DIR
    emiten_folder = os.path.join(raw_path, emiten.upper().strip())
    if not os.path.exists(emiten_folder) or not os.path.isdir(emiten_folder):
        return None

    pdf_files = []
    try:
        for fname in os.listdir(emiten_folder):
            if fname.lower().endswith(".pdf"):
                full_path = os.path.join(emiten_folder, fname)
                try:
                    fsize = os.path.getsize(full_path)
                    pdf_files.append((fsize, full_path))
                except Exception:
                    continue
    except Exception as e:
        print(f"[CALK] Error searching PDFs in {emiten_folder}: {e}")
        return None

    if not pdf_files:
        return None

    pdf_files.sort(key=lambda x: x[0], reverse=True)
    return pdf_files[0][1]


def is_cache_valid(cache_path: str, max_age_days: int = 7) -> bool:
    """Checks if cache file exists and is less than max_age_days old."""
    if not cache_path or not os.path.exists(cache_path):
        return False
    try:
        mtime = os.path.getmtime(cache_path)
        age_seconds = time.time() - mtime
        return age_seconds < (max_age_days * 86400)
    except Exception:
        return False


def load_calk_cache(cache_path: str) -> Optional[Dict[str, Any]]:
    """Loads and validates cached CALK extraction result."""
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # Ensure all expected keys exist
                base = get_default_calk_result()
                for k, v in data.items():
                    if k in base:
                        base[k] = v
                return base
    except Exception as e:
        print(f"[CALK] Cache read warning for {cache_path}: {e}")
    return None


def save_calk_cache(cache_path: str, data: Dict[str, Any]) -> bool:
    """Saves CALK extraction result to cache file."""
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[CALK] Cache save warning for {cache_path}: {e}")
        return False


def clean_pdf_page_text(text: str) -> str:
    """Cleans junk artifacts, excessive hashes, and normalizes whitespace."""
    if not text:
        return ""
    # Remove common PDF stream artifacts and junk hashes
    text = re.sub(r"x[a-zA-Z0-9]{15,}\.\d*", "", text)
    # Remove long repeated dashes or underscores
    text = re.sub(r"[-_]{4,}", " ", text)
    # Normalize multiple whitespaces and newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def select_relevant_calk_pages(
    pdf_path: str,
    max_pages: int = 8,
) -> tuple[List[int], str]:
    """
    Scans all pages in the PDF for CALK keywords.
    Returns:
        (selected_page_numbers, concatenated_cleaned_text)
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return [], ""

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"[CALK] Error opening PDF {pdf_path}: {e}")
        return [], ""

    total_pages = len(doc)
    page_matches = []  # List of tuples: (page_num, score, matched_categories, text)

    try:
        for page_idx in range(total_pages):
            page_num = page_idx + 1
            try:
                raw_text = doc[page_idx].get_text()
            except Exception:
                continue

            if not raw_text or len(raw_text.strip()) < 30:
                continue

            text_lc = raw_text.lower()
            matched_cats = []
            score = 0

            for cat, keywords in CALK_KEYWORDS.items():
                cat_hits = 0
                for kw in keywords:
                    if kw in text_lc:
                        cat_hits += 1
                if cat_hits > 0:
                    matched_cats.append(cat)
                    score += cat_hits

            if score > 0:
                cleaned = clean_pdf_page_text(raw_text)
                page_matches.append((page_num, score, matched_cats, cleaned))

    finally:
        try:
            doc.close()
        except Exception:
            pass

    if not page_matches:
        return [], ""

    # Smart balancing: pick top 2 highest-scoring pages per category
    category_pages: Dict[str, List[tuple]] = {cat: [] for cat in CALK_KEYWORDS}
    for item in page_matches:
        for cat in item[2]:
            category_pages[cat].append(item)

    selected_set = set()
    for cat, items in category_pages.items():
        sorted_items = sorted(items, key=lambda x: x[1], reverse=True)
        for it in sorted_items[:2]:
            selected_set.add(it[0])
            if len(selected_set) >= max_pages:
                break
        if len(selected_set) >= max_pages:
            break

    if len(selected_set) < max_pages:
        sorted_all = sorted(page_matches, key=lambda x: x[1], reverse=True)
        for it in sorted_all:
            selected_set.add(it[0])
            if len(selected_set) >= max_pages:
                break

    sorted_page_nums = sorted(list(selected_set))

    page_dict = {it[0]: it[3] for it in page_matches}
    page_texts_list = []
    for pnum in sorted_page_nums:
        ptxt = page_dict.get(pnum, "")
        if ptxt:
            page_texts_list.append(f"--- [Halaman {pnum}] ---\n{ptxt[:1200]}")

    combined_text = "\n\n".join(page_texts_list)
    if len(combined_text) > 8000:
        combined_text = combined_text[:8000] + "\n\n... [Teks dipotong]"

    return sorted_page_nums, combined_text


def _normalize_string_list(val: Any) -> List[str]:
    """Helper to convert LLM output into a clean list of strings."""
    if not val:
        return []
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    if isinstance(val, list):
        res = []
        for item in val:
            if isinstance(item, str) and item.strip():
                res.append(item.strip())
            elif isinstance(item, dict):
                # Format dict into a clean descriptive summary string
                parts = []
                for k, v in item.items():
                    if v is not None and str(v).strip():
                        label = k.replace("_", " ").title()
                        parts.append(f"{label}: {v}")
                if parts:
                    res.append("; ".join(parts))
        return res
    return []


def _normalize_opini_auditor(val: Any) -> Dict[str, str]:
    """Helper to normalize auditor opinion object."""
    default_opini = {
        "jenis": "",
        "kap": "",
        "tanggal": "",
        "penekanan": "",
    }
    if not val:
        return default_opini

    if isinstance(val, str):
        default_opini["jenis"] = val.strip()
        return default_opini

    if isinstance(val, dict):
        for k in ["jenis", "kap", "tanggal", "penekanan"]:
            v = val.get(k, "")
            default_opini[k] = str(v).strip() if v is not None else ""
        return default_opini

    return default_opini


def get_auditor_opinion_from_xbrl(xbrl_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Fallback: extracts auditor info from XBRL sheet 1000000 data.
    xbrl_data may be a flat dictionary of general info rows or a full parsed workbook dict.
    
    Returns:
        {'jenis': str, 'kap': str, 'tanggal': str, 'penekanan': str}
    """
    res = {
        "jenis": "",
        "kap": "",
        "tanggal": "",
        "penekanan": "",
    }

    if not xbrl_data or not isinstance(xbrl_data, dict):
        return res

    # Flatten nested dictionaries if any (e.g., if sheet_1000000 is nested)
    flat_items = {}
    for k, v in xbrl_data.items():
        if isinstance(v, dict):
            for subk, subv in v.items():
                flat_items[str(subk).strip()] = subv
        else:
            flat_items[str(k).strip()] = v

    for raw_k, raw_v in flat_items.items():
        if raw_v is None:
            continue
        v_str = str(raw_v).strip()
        if not v_str or v_str == "-":
            continue

        k_lc = raw_k.lower()

        # 1. Jenis Opini / Hasil Penugasan
        if not res["jenis"] and any(
            p in k_lc
            for p in [
                "jenis opini",
                "hasil penugasan review",
                "opini auditor",
                "audit opinion",
                "penugasan audit",
                "tingkat asurans",
                "keterangan auditor",
            ]
        ):
            res["jenis"] = v_str

        # 2. Kantor Akuntan Publik (KAP)
        if not res["kap"] and any(
            p in k_lc
            for p in [
                "auditor tahun berjalan",
                "nama kantor akuntan",
                "kantor akuntan publik",
                "nama kap",
                "current year auditor",
                "nama akuntan publik",
                "auditor name",
            ]
        ):
            res["kap"] = v_str

        # 3. Tanggal Laporan Audit
        if not res["tanggal"] and any(
            p in k_lc
            for p in [
                "tanggal laporan audit",
                "tanggal laporan auditor",
                "tanggal opini",
                "audit report date",
                "tanggal audit",
            ]
        ):
            res["tanggal"] = v_str

        # 4. Penekanan Suatu Hal / Modifikasi
        if not res["penekanan"] and any(
            p in k_lc
            for p in [
                "penekanan suatu hal",
                "hal penekanan",
                "emphasis of matter",
                "key audit matters",
                "hal audit utama",
                "catatan penekanan",
            ]
        ):
            res["penekanan"] = v_str

    return res


def extract_calk_highlights(
    pdf_path: Optional[str] = None,
    emiten: str = "",
    period: str = "Q2",
    year: str = "2026",
    xbrl_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Main entry point to extract qualitative disclosures from PDF CALK.

    Args:
        pdf_path: Path to the financial statement PDF. If None, auto-locates largest PDF.
        emiten: Ticker symbol of the emiten (e.g., 'ADRO', 'BBCA').
        period: Reporting period (e.g., 'Q1', 'Q2', 'Q3', 'FY').
        year: Reporting year (e.g., '2026').
        xbrl_data: Optional parsed XBRL sheet 1000000 dict for fallback auditor opinion.

    Returns:
        Dict matching schema:
        {
            'perjanjian_kontrak': List[str],
            'subsequent_events': List[str],
            'related_party': List[str],
            'opini_auditor': {'jenis': str, 'kap': str, 'tanggal': str, 'penekanan': str},
            'komitmen_kontinjensi': List[str],
            'source_pages': List[int]
        }
    """
    emiten_code = emiten.upper().strip() if emiten else ""
    period_code = period.upper().strip() if period else "Q2"
    year_str = str(year).strip() if year else "2026"

    # Infer emiten / year / period from pdf_path if missing
    if pdf_path and os.path.exists(pdf_path):
        fname = os.path.basename(pdf_path)
        if not emiten_code:
            m_emiten = re.search(r"[_\-]([A-Z]{4})[_\-\.]", fname)
            if m_emiten:
                emiten_code = m_emiten.group(1).upper()
        if not year_str or year_str == "2026":
            m_year = re.search(r"202[4-9]", fname)
            if m_year:
                year_str = m_year.group(0)

    # Define cache path
    cache_key = f"{emiten_code or 'UNKNOWN'}_{period_code}_{year_str}"
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")

    # 1. Check cache first (freshness: < 7 days)
    if is_cache_valid(cache_file, max_age_days=7):
        cached_result = load_calk_cache(cache_file)
        if cached_result:
            print(f"[CALK] Loaded fresh cached CALK data for {cache_key}")
            return cached_result

    # 2. Locate PDF file if not provided
    target_pdf = pdf_path
    if not target_pdf or not os.path.exists(target_pdf):
        if emiten_code:
            target_pdf = find_largest_pdf(emiten_code)

    if not target_pdf or not os.path.exists(target_pdf):
        print(f"[CALK] Warning: No valid PDF file found for {emiten_code or 'CALK'}")
        fallback_res = get_default_calk_result()
        if xbrl_data:
            fallback_res["opini_auditor"] = get_auditor_opinion_from_xbrl(xbrl_data)
        return fallback_res

    # 3. Smart page scanning
    pdf_filename = os.path.basename(target_pdf)
    try:
        source_pages, combined_text = select_relevant_calk_pages(target_pdf, max_pages=8)
        print(f"[CALK] Scanning {pdf_filename}... found {len(source_pages)} relevant pages {source_pages} ({len(combined_text)} chars)")
    except Exception as e:
        print(f"[CALK] Error during PDF page selection ({pdf_filename}): {e}")
        fallback_res = get_default_calk_result()
        if xbrl_data:
            fallback_res["opini_auditor"] = get_auditor_opinion_from_xbrl(xbrl_data)
        return fallback_res

    if not source_pages or not combined_text.strip():
        print(f"[CALK] No relevant CALK pages identified in {pdf_filename}")
        res = get_default_calk_result(source_pages)
        if xbrl_data:
            res["opini_auditor"] = get_auditor_opinion_from_xbrl(xbrl_data)
        if emiten_code:
            save_calk_cache(cache_file, res)
        return res

    # 4. Construct LLM extraction prompt
    system_prompt = (
        "Anda adalah analis keuangan pasar modal Indonesia (IDX/BEI). "
        "Ekstrak fakta kunci dari teks CALK dan kembalikan HANYA JSON valid."
    )

    user_prompt = (
        "Ekstrak informasi penting berikut dalam format JSON murni:\n"
        "{\n"
        '  "perjanjian_kontrak": ["ringkasan kontrak/perjanjian material jika ada"],\n'
        '  "subsequent_events": ["peristiwa penting setelah tanggal pelaporan jika ada"],\n'
        '  "related_party": ["transaksi signifikan pihak berelasi jika ada"],\n'
        '  "komitmen_kontinjensi": ["komitmen/kontinjensi/litigasi jika ada"]\n'
        "}\n\n"
        "Aturan: Jika tidak ada data untuk kategori tersebut, isi dengan array kosong []. Balas HANYA JSON tanpa markdown atau teks pengantar.\n\n"
        f"Teks CALK:\n{combined_text}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 5. Call LLM
    parsed_json = None
    if llm_client:
        try:
            content_str = llm_client.call_llm(
                messages=messages,
                temperature=0.1,
                timeout=45,
                max_retries=1,
                context_name=f"CALK {emiten_code}",
            )
            if content_str:
                parsed_json = llm_client.parse_json_from_llm(content_str)
                if not parsed_json:
                    clean_str = content_str
                    if "```json" in clean_str:
                        clean_str = clean_str.split("```json")[1].split("```")[0].strip()
                    elif "```" in clean_str:
                        clean_str = clean_str.split("```")[1].split("```")[0].strip()
                    fb = clean_str.find("{")
                    lb = clean_str.rfind("}")
                    if fb != -1 and lb > fb:
                        parsed_json = json.loads(clean_str[fb : lb + 1])
                if parsed_json:
                    print(f"[CALK] Successfully extracted JSON for {emiten_code}")
                else:
                    print(f"[CALK] Could not parse JSON from LLM for {emiten_code}. Snippet: {content_str[:150]}")
        except Exception as e:
            print(f"[CALK] LLM extraction exception for {emiten_code}: {e}")

    # 6. Format and validate final result
    final_result = get_default_calk_result(source_pages)

    if parsed_json and isinstance(parsed_json, dict):
        final_result["perjanjian_kontrak"] = _normalize_string_list(
            parsed_json.get("perjanjian_kontrak")
        )
        final_result["subsequent_events"] = _normalize_string_list(
            parsed_json.get("subsequent_events")
        )
        final_result["related_party"] = _normalize_string_list(
            parsed_json.get("related_party")
        )
        final_result["komitmen_kontinjensi"] = _normalize_string_list(
            parsed_json.get("komitmen_kontinjensi")
        )
        final_result["opini_auditor"] = _normalize_opini_auditor(
            parsed_json.get("opini_auditor")
        )

    # 7. Fallback auditor opinion if missing and xbrl_data available
    if not final_result["opini_auditor"].get("jenis") and xbrl_data:
        xbrl_opini = get_auditor_opinion_from_xbrl(xbrl_data)
        if xbrl_opini.get("jenis"):
            final_result["opini_auditor"] = xbrl_opini

    # 8. Cache result
    if emiten_code:
        save_calk_cache(cache_file, final_result)

    return final_result


# ==============================================================================
# COMMAND LINE / STANDALONE TEST RUNNER
# ==============================================================================
if __name__ == "__main__":
    test_emiten = sys.argv[1] if len(sys.argv) > 1 else "ADRO"
    print(f"=== Testing CALK Extractor for {test_emiten} ===")
    res = extract_calk_highlights(emiten=test_emiten, period="Q2", year="2026")
    print(json.dumps(res, ensure_ascii=False, indent=2))
