# Corporate Action Builder — Swarm Intelijen Pasar Modal Indonesia
# =============================================================================
# File    : corporate_action_builder.py
# Project : Swarm Intelijen Pasar Modal Indonesia (IDX)
# Skill   : corporate-action-summarizer
# Version : 2.0.0
# Updated : 2026-09-23
# Author  : Corporate Action Intelligence Agent (Swarm)
# =============================================================================
"""
Modul pemroses aksi korporasi untuk Swarm Intelijen Pasar Modal Indonesia.

Fitur utama:
  - Auto-deteksi tipe aksi korporasi dari teks dokumen (keyword matching)
  - Ekstraksi parameter per tipe menggunakan regex (Dividen, Rights Issue,
    MTO, Buyback, Stock Split, RUPS, Private Placement)
  - Pembuatan laporan Markdown 8-seksi institusional
  - Penyimpanan ke knowledge-base (PRIMARY) dan reports/summaries (BACKUP)
  - Integrasi opsional dengan LLM (jika CUSTOM_LLM_KEY tersedia)
  - CLI Interface untuk eksekusi mandiri

Penggunaan CLI:
    python corporate_action_builder.py --emiten BUVA --file reports/raw/BUVA/PMHMETD.pdf --date 2026-09-23
    python corporate_action_builder.py --emiten HUMI --text "Perseroan mengumumkan pembagian dividen..."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Pastikan output konsol Windows mendukung UTF-8 (mencegah UnicodeEncodeError)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Konstanta Path Direktori
# ---------------------------------------------------------------------------
BASE_DIR = Path(r"G:\My Drive\Model2")
PRIMARY_DIR   = BASE_DIR / "Finplan_analyst" / "knowledge-base" / "corporate-actions"
BACKUP_DIR    = BASE_DIR / "reports" / "summaries" / "corporate-actions"
RAW_DIR       = BASE_DIR / "reports" / "raw"

# ---------------------------------------------------------------------------
# Enum Tipe Aksi Korporasi
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    """Tipe aksi korporasi yang didukung oleh builder."""
    DIVIDEN           = "Dividen"
    RIGHTS_ISSUE      = "Rights_Issue"
    MTO               = "Tender_Offer"
    BUYBACK           = "Buyback"
    STOCK_SPLIT       = "Stock_Split"
    RUPS              = "Hasil_RUPS"
    RUPS_PEMANGGILAN  = "Pemanggilan_RUPS"
    PRIVATE_PLACEMENT = "Private_Placement"
    WARAN_KONVERSI    = "Konversi_Waran"   # akan di-skip
    UNKNOWN           = "General"


# ---------------------------------------------------------------------------
# Dataclass Parameter Hasil Ekstraksi
# ---------------------------------------------------------------------------

@dataclass
class DividenParams:
    nominal_per_saham: str = "TBA"
    total_nilai: str       = "TBA"
    cum_date: str          = "Terjadwal"
    ex_date: str           = "Terjadwal"
    recording_date: str    = "Terjadwal"
    payment_date: str      = "Terjadwal"
    jenis_dividen: str     = "Final"

@dataclass
class RightsIssueParams:
    jumlah_saham_baru: str    = "TBA"
    rasio_hmetd: str          = "TBA"          # format "X:Y"
    harga_pelaksanaan: str    = "TBA"
    target_dana: str          = "TBA"
    pembeli_siaga: str        = "TBA"
    komitmen_siaga: str       = "TBA"
    alokasi_dana: List[Tuple[str, str]] = field(default_factory=list)  # [(nama, persen%), ...]
    jadwal: List[Tuple[str, str]] = field(default_factory=list)        # [(event, tanggal), ...]
    dilusi_maksimum: str      = "TBA"
    pengendali: str           = "TBA"

@dataclass
class MtoParams:
    pengendali_baru: str     = "TBA"
    harga_penawaran: str     = "TBA"
    persen_akuisisi: str     = "TBA"
    batas_waktu: str         = "Terjadwal"
    pihak_pembeli: str       = "TBA"

@dataclass
class BuybackParams:
    nilai_program: str       = "TBA"
    jumlah_saham_maks: str   = "TBA"
    harga_maksimum: str      = "Harga Pasar Reguler"
    periode_mulai: str       = "Terjadwal"
    periode_selesai: str     = "Terjadwal"

@dataclass
class StockSplitParams:
    rasio_split: str         = "TBA"          # contoh: "1:5"
    harga_lama: str          = "TBA"
    harga_baru: str          = "TBA"
    tanggal_efektif: str     = "Terjadwal"

@dataclass
class RupsParams:
    tanggal_rups: str        = "Terjadwal"
    waktu_rups: str          = "09.00 WIB"
    lokasi_rups: str         = "Kantor Perseroan"
    recording_date: str      = "Terjadwal"
    agenda_list: List[Tuple[str, str]] = field(default_factory=list)
    kuorum: str              = "TBA"
    keputusan: str           = "TBA"
    is_pemanggilan: bool     = True

@dataclass
class GenericParams:
    fakta_material: List[Dict[str, str]] = field(default_factory=list)
    ringkasan: str = ""


# ---------------------------------------------------------------------------
# Helper: Baca PDF
# ---------------------------------------------------------------------------

def read_pdf_text(filepath: str) -> str:
    """
    Membaca teks dari file PDF.

    Mencoba secara berurutan:
    1. PyMuPDF (fitz) — preferensi utama, akurasi tinggi
    2. pypdf — fallback pertama
    3. Kembalikan string kosong jika keduanya tidak tersedia

    Args:
        filepath: Path absolut atau relatif ke file PDF.

    Returns:
        Teks penuh dari PDF sebagai string.
    """
    filepath = str(filepath)
    if not os.path.exists(filepath):
        print(f"[!] File tidak ditemukan: {filepath}")
        return ""

    # -- Coba PyMuPDF (fitz) --
    try:
        import fitz  # type: ignore
        doc = fitz.open(filepath)
        pages: List[str] = []
        for page in doc:
            pages.append(page.get_text("text"))  # type: ignore[attr-defined]
        doc.close()
        text = "\n".join(pages)
        if text.strip():
            print(f"[+] PDF dibaca dengan PyMuPDF: {len(text)} karakter ({len(pages)} halaman)")
            return text
    except ImportError:
        pass
    except Exception as e:
        print(f"[!] PyMuPDF error: {e}")

    # -- Fallback: pypdf --
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(filepath)
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        if text.strip():
            print(f"[+] PDF dibaca dengan pypdf: {len(text)} karakter ({len(pages)} halaman)")
            return text
    except ImportError:
        pass
    except Exception as e:
        print(f"[!] pypdf error: {e}")

    print("[!] Tidak ada library PDF yang tersedia (fitz/pypdf). Kembalikan string kosong.")
    return ""


# ---------------------------------------------------------------------------
# Auto-Deteksi Tipe Aksi Korporasi
# ---------------------------------------------------------------------------

# Keyword patterns untuk setiap tipe (case-insensitive)
_ACTION_KEYWORDS: Dict[ActionType, List[str]] = {
    ActionType.WARAN_KONVERSI: [
        r"konversi waran",
        r"warrant conversion",
        r"pencatatan saham tambahan dari konversi waran",
    ],
    ActionType.MTO: [
        r"mandatory tender offer",
        r"\bMTO\b",
        r"penawaran tender wajib",
        r"penawaran tender",
        r"tender offer",
    ],
    ActionType.PRIVATE_PLACEMENT: [
        r"PMTHMETD",
        r"penambahan modal tanpa hak memesan",
        r"penambahan modal tanpa hmetd",
        r"tanpa hmetd",
        r"private placement",
        r"PMHMETD tanpa HMETD",
        r"tanpa hak memesan efek terlebih dahulu",
        r"non-preemptive",
    ],
    ActionType.RIGHTS_ISSUE: [
        r"rights issue",
        r"\bPMHMETD\b",
        r"penambahan modal dengan memberikan hak",
        r"(?<!tanpa\s)(?<!tanpa\s-)\bHMETD\b",
        r"(?<!tanpa\s)hak memesan efek terlebih dahulu",
        r"penambahan modal melalui penawaran umum terbatas",
        r"\bPUT\b",
    ],
    ActionType.BUYBACK: [
        r"buyback",
        r"buy back",
        r"pembelian kembali saham",
        r"pembelian saham kembali",
    ],
    ActionType.STOCK_SPLIT: [
        r"stock split",
        r"pemecahan saham",
        r"pemecahan nilai nominal",
    ],
    ActionType.RUPS_PEMANGGILAN: [
        r"pemanggilan rups",
        r"panggilan rups",
        r"pengumuman rups",
        r"undangan rups",
    ],
    ActionType.RUPS: [
        r"\bRUPS\b",
        r"\bRUPSLB\b",
        r"rapat umum pemegang saham",
        r"hasil rups",
        r"risalah rups",
        r"keputusan rups",
    ],
    ActionType.DIVIDEN: [
        r"dividen tunai",
        r"dividen interim",
        r"dividen final",
        r"dividen spesial",
        r"pembagian dividen",
        r"\bdividen\b",
        r"\bdividend\b",
    ],
}


def detect_action_type(text: str) -> ActionType:
    """
    Auto-deteksi tipe aksi korporasi dari teks dokumen menggunakan keyword matching.

    Urutan prioritas deteksi:
    1. Waran Konversi (di-skip / return langsung)
    2. MTO (Mandatory Tender Offer)
    3. Private Placement (PMTHMETD)
    4. Rights Issue (PMHMETD)
    5. Buyback
    6. Stock Split
    7. RUPS Pemanggilan
    8. RUPS Hasil
    9. Dividen
    10. Unknown / General

    Args:
        text: Teks lengkap dokumen PDF atau string input.

    Returns:
        ActionType enum yang terdeteksi.
    """
    text_lower = text.lower()

    for action_type, patterns in _ACTION_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                print(f"[+] Auto-detected action type: {action_type.value} (matched: '{pattern}')")
                return action_type

    print("[!] Tidak ada tipe aksi korporasi yang terdeteksi — menggunakan ActionType.UNKNOWN")
    return ActionType.UNKNOWN


# ---------------------------------------------------------------------------
# Ekstraktor Parameter per Tipe Aksi
# ---------------------------------------------------------------------------

def _first_match(text: str, patterns: List[str]) -> Optional[str]:
    """Helper: kembalikan group(1) dari pattern pertama yang cocok."""
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            try:
                val = m.group(1).strip().replace("\n", " ")
                if val:
                    return val
            except IndexError:
                pass
    return None


def extract_dividen_params(text: str) -> DividenParams:
    """
    Ekstraksi parameter Dividen dari teks dokumen menggunakan regex.

    Mengekstrak: nominal per saham, total nilai, cum date, ex date,
    recording date, dan payment date.

    Args:
        text: Teks dokumen yang mengandung informasi dividen.

    Returns:
        DividenParams dataclass dengan nilai-nilai yang ditemukan.
    """
    p = DividenParams()

    # Jenis dividen
    if re.search(r"dividen interim", text, re.IGNORECASE):
        p.jenis_dividen = "Interim"
    elif re.search(r"dividen spesial|special dividend", text, re.IGNORECASE):
        p.jenis_dividen = "Spesial"
    elif re.search(r"dividen final|final dividend", text, re.IGNORECASE):
        p.jenis_dividen = "Final"

    # Nominal per saham
    nominal = _first_match(text, [
        r"(?:dividen|dividend)[^\n]*?(?:sebesar|senilai|Rp\.?)\s*(Rp\.?\s*[\d.,]+(?:\s*(?:per saham|per lembar))?)",
        r"(?:nominal|besaran)\s+dividen[^\n]*?(?:Rp\.?)\s*([\d.,]+)",
        r"Rp\.?\s*([\d.,]+)\s*(?:per saham|per lembar saham)",
        r"dividen\s+(?:tunai\s+)?(?:sebesar\s+)?Rp\.?\s*([\d.,]+)",
    ])
    if nominal:
        p.nominal_per_saham = f"Rp {nominal}" if not nominal.lower().startswith("rp") else nominal

    # Total nilai dividen
    total = _first_match(text, [
        r"total\s+(?:nilai\s+)?dividen[^\n]*?(?:Rp\.?|sebesar)\s*(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?)",
        r"(?:senilai|sebesar)\s*(Rp\.?\s*[\d.,]+\s*(?:miliar|juta|triliun))[^\n]*dividen",
        r"dividen[^\n]*?total\s*(Rp\.?\s*[\d.,]+\s*(?:miliar|juta|triliun)?)",
    ])
    if total:
        p.total_nilai = total

    # Pattern tanggal — beragam format IDX
    _date_pat = r"(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\d{1,2}-\d{4})"

    cum = _first_match(text, [
        rf"cum\s*(?:date\s*)?(?:dividen|dividend|pasar reguler)[^\n]*?(?:adalah|pada|tanggal)?\s*:?\s*{_date_pat}",
        rf"(?:tanggal\s+)?cum\s+(?:dividen|dividend)\s*[:\-]?\s*{_date_pat}",
        rf"cum\s+date\s*[:\-]?\s*{_date_pat}",
    ])
    if cum:
        p.cum_date = cum

    ex = _first_match(text, [
        rf"ex\s*(?:date\s*)?(?:dividen|dividend)[^\n]*?(?:adalah|pada|tanggal)?\s*:?\s*{_date_pat}",
        rf"(?:tanggal\s+)?ex\s+(?:dividen|dividend)\s*[:\-]?\s*{_date_pat}",
        rf"ex\s+date\s*[:\-]?\s*{_date_pat}",
    ])
    if ex:
        p.ex_date = ex

    rec = _first_match(text, [
        rf"(?:recording\s+date|daftar\s+pemegang\s+saham|DPS)[^\n]*?(?:adalah|pada|tanggal)?\s*:?\s*{_date_pat}",
        rf"recording\s+date\s*[:\-]?\s*{_date_pat}",
        rf"tanggal\s+dps\s*[:\-]?\s*{_date_pat}",
    ])
    if rec:
        p.recording_date = rec

    pay = _first_match(text, [
        rf"(?:tanggal\s+)?pembayaran\s+dividen\s*[:\-]?\s*{_date_pat}",
        rf"payment\s+date\s*[:\-]?\s*{_date_pat}",
        rf"dividen\s+(?:akan\s+)?dibayarkan[^\n]*?{_date_pat}",
    ])
    if pay:
        p.payment_date = pay

    return p


def extract_rights_issue_params(text: str) -> RightsIssueParams:
    """
    Ekstraksi parameter Rights Issue / PMHMETD dari teks dokumen.

    Mengekstrak: jumlah saham baru, rasio HMETD, harga pelaksanaan,
    target dana, pembeli siaga, komitmen, alokasi penggunaan dana, dan jadwal.

    Args:
        text: Teks dokumen yang mengandung informasi Rights Issue.

    Returns:
        RightsIssueParams dataclass dengan nilai-nilai yang ditemukan.
    """
    p = RightsIssueParams()

    # Jumlah saham baru
    jml = _first_match(text, [
        r"(?:menerbitkan|diterbitkan|sebanyak)\s+([\d.,]+(?:\s*(?:miliar|juta|ribu))?\s*(?:lembar|saham|saham baru))",
        r"(?:saham baru|new shares)[^\n]*?(?:sebanyak|berjumlah)\s*([\d.,]+(?:\s*(?:miliar|juta|ribu))?)",
        r"([\d.,]+(?:\s*(?:miliar|juta))?)\s+saham\s+(?:baru|HMETD)",
    ])
    if jml:
        p.jumlah_saham_baru = jml

    # Rasio HMETD (misal: "1 saham lama : 5 saham baru" → "1:5")
    rasio = _first_match(text, [
        r"(?:rasio|ratio|perbandingan)\s+(?:HMETD|rights?)[^\n]*?(\d+\s*[:/]\s*\d+)",
        r"(\d+)\s*(?:saham lama|lembar lama)\s*(?:mendapatkan|memperoleh|berhak atas)\s*(\d+)\s*(?:saham baru|HMETD|rights?)",
        r"setiap\s+(\d+)\s+(?:saham|lembar)[^\n]*?(\d+)\s+(?:saham baru|HMETD)",
    ])
    if rasio:
        # Normalisasi ke format "X:Y"
        parts = re.findall(r"\d+", rasio)
        if len(parts) >= 2:
            p.rasio_hmetd = f"{parts[0]}:{parts[1]}"
        else:
            p.rasio_hmetd = rasio

    # Harga pelaksanaan
    harga = _first_match(text, [
        r"(?:harga pelaksanaan|harga HMETD|exercise price|harga rights?)\s*[:\-]?\s*(Rp\.?\s*[\d.,]+)",
        r"(?:pelaksanaan|exercise)\s+(?:HMETD|rights?)\s+(?:sebesar|seharga)\s+(Rp\.?\s*[\d.,]+)",
        r"Rp\.?\s*([\d.,]+)\s*(?:per saham|\/saham)[^\n]*?(?:HMETD|rights|pelaksanaan)",
    ])
    if harga:
        p.harga_pelaksanaan = f"Rp {harga}" if not harga.lower().startswith("rp") else harga

    # Target dana
    target = _first_match(text, [
        r"(?:target|total|jumlah)\s+(?:dana|modal)[^\n]*?(?:sebesar|senilai|berjumlah)\s*(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?)",
        r"(?:mengumpulkan|menghimpun|menargetkan)\s+dana\s*(?:sebesar)?\s*(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?)",
        r"(?:hasil rights issue|dana hasil)\s+(?:sekitar|kurang lebih|sebesar)?\s*(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?)",
    ])
    if target:
        p.target_dana = target

    # Pembeli siaga
    siaga = _first_match(text, [
        r"(?:pembeli siaga|standby buyer|standby purchaser)[^\n]*?(?:adalah|yaitu|:)\s*([A-Z][^\n,;\.]{5,60}(?:Tbk\.?|Ltd\.?|Pte\.?|Corp\.?|Inc\.?|Co\.)?)",
        r"PT\.?\s+[A-Z][^\n,\.]{5,50}\s+(?:sebagai\s+)?(?:pembeli siaga|standby)",
    ])
    if siaga:
        p.pembeli_siaga = siaga.strip()

    # Komitmen pembeli siaga
    komitmen = _first_match(text, [
        r"(?:komitmen|berkomitmen|bersedia membeli)\s+(?:untuk membeli|menyerap)?\s*(?:saham)?\s*(?:sebanyak|sebesar|senilai)\s*(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?|[\d.,]+(?:\s*(?:miliar|juta|triliun))?\s*saham)",
        r"(?:standby buyer|pembeli siaga)[^\n]*?komitmen[^\n]*?(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?)",
    ])
    if komitmen:
        p.komitmen_siaga = komitmen

    # Dilusi maksimum
    dilusi = _first_match(text, [
        r"(?:dilusi|potensi dilusi|dilusi maksimum)[^\n]*?([\d.,]+\s*%)",
        r"(?:kepemilikan)[^\n]*?(?:terdilusi|mengalami dilusi)\s+(?:hingga|sebesar|maksimum)\s+([\d.,]+\s*%)",
    ])
    if dilusi:
        p.dilusi_maksimum = dilusi

    # Pengendali
    pengendali = _first_match(text, [
        r"(?:pemegang saham pengendali|pengendali utama|controlling shareholder)[^\n]*?(?:adalah|yaitu|:)\s*([A-Z][^\n,;\.]{5,60}(?:Tbk\.?|Ltd\.?|Pte\.?|Corp\.?|Inc\.?|Co\.)?)",
        r"PT\.?\s+[A-Z][^\n,\.]{5,50}\s+(?:selaku|sebagai)\s+pemegang saham pengendali",
    ])
    if pengendali:
        p.pengendali = pengendali.strip()

    # Alokasi penggunaan dana (cari pola persentase)
    alloc_pattern = re.finditer(
        r"(?P<nama>[A-Za-z\s&\/,'-]{10,80}?)\s+(?:sebesar|senilai|sekitar)?\s*(?P<pct>[\d.,]+\s*%)",
        text, re.IGNORECASE
    )
    seen_pct: List[str] = []
    for m in alloc_pattern:
        nama = m.group("nama").strip()
        pct  = m.group("pct").strip()
        if pct not in seen_pct and len(nama) > 5:
            p.alokasi_dana.append((nama, pct))
            seen_pct.append(pct)
            if len(p.alokasi_dana) >= 6:
                break

    return p


def extract_mto_params(text: str) -> MtoParams:
    """
    Ekstraksi parameter Mandatory Tender Offer (MTO) dari teks dokumen.

    Mengekstrak: pengendali baru, harga penawaran, persentase akuisisi,
    batas waktu tender, dan pihak pembeli.

    Args:
        text: Teks dokumen yang mengandung informasi MTO.

    Returns:
        MtoParams dataclass dengan nilai-nilai yang ditemukan.
    """
    p = MtoParams()

    _date_pat = r"(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"

    # Pengendali baru / pihak pembeli
    pengendali = _first_match(text, [
        r"(?:pengendali baru|pihak pengambil alih|acquirer|penawar)[^\n]*?(?:adalah|yaitu|:)\s*([A-Z][^\n,;\.]{5,70})",
        r"PT\.?\s+[A-Z][^\n,\.]{5,60}\s+(?:sebagai\s+)?(?:pengendali|acquirer|pihak penawar)",
        r"(?:[Pp]erusahaan pengambil alih|[Pp]ihak pembeli)\s*[:\-]?\s*([A-Z][^\n,;\.]{5,70})",
    ])
    if pengendali:
        p.pengendali_baru = pengendali.strip()
        p.pihak_pembeli   = pengendali.strip()

    # Harga penawaran MTO
    harga = _first_match(text, [
        r"(?:harga penawaran|offering price|harga tender)[^\n]*?(Rp\.?\s*[\d.,]+(?:\s*(?:per saham|\/saham))?)",
        r"(?:MTO|tender offer)[^\n]*?(?:harga|seharga|sebesar)\s*(Rp\.?\s*[\d.,]+)",
        r"(?:membeli|membeli saham)[^\n]*?(?:dengan harga|seharga)\s*(Rp\.?\s*[\d.,]+)",
    ])
    if harga:
        p.harga_penawaran = harga

    # Persentase saham yang diakuisisi
    pct = _first_match(text, [
        r"(?:mengakuisisi|membeli|mengambil alih)\s+(?:sebanyak|sekitar)?\s*([\d.,]+\s*%)\s+(?:saham|kepemilikan)",
        r"(?:persentase akuisisi|saham yang ditawarkan)[^\n]*?([\d.,]+\s*%)",
        r"([\d.,]+\s*%)\s+(?:saham|kepemilikan)[^\n]*?(?:tender|MTO|penawaran)",
    ])
    if pct:
        p.persen_akuisisi = pct

    # Batas waktu tender
    batas = _first_match(text, [
        rf"(?:batas waktu|deadline|periode tender|closing date)[^\n]*?{_date_pat}",
        rf"(?:penawaran berakhir|tender berakhir)[^\n]*?{_date_pat}",
        rf"(?:sampai dengan|s\.?d\.?|hingga)\s+{_date_pat}\s+(?:masa penawaran|periode)",
    ])
    if batas:
        p.batas_waktu = batas

    return p


def extract_buyback_params(text: str) -> BuybackParams:
    """
    Ekstraksi parameter program Buyback dari teks dokumen.

    Mengekstrak: nilai program, jumlah saham maksimum, harga maksimum,
    dan periode pelaksanaan.

    Args:
        text: Teks dokumen yang mengandung informasi Buyback.

    Returns:
        BuybackParams dataclass dengan nilai-nilai yang ditemukan.
    """
    p = BuybackParams()

    _date_pat = r"(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"

    # Nilai program
    nilai = _first_match(text, [
        r"(?:alokasi|anggaran|nilai program|dana buyback|nilai buyback)[^\n]*?(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?)",
        r"(?:buyback|buy back)[^\n]*?(?:senilai|sebesar|maksimal)\s*(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?)",
        r"(?:menyediakan|menggunakan)\s+dana\s+(?:sebesar)?\s*(Rp\.?\s*[\d.,]+(?:\s*(?:miliar|juta|triliun))?)\s+(?:untuk|guna)\s+(?:buyback|pembelian kembali)",
    ])
    if nilai:
        p.nilai_program = nilai

    # Jumlah saham maksimum
    jml = _first_match(text, [
        r"(?:maksimum|sebanyak-banyaknya|paling banyak)\s+([\d.,]+(?:\s*(?:miliar|juta|ribu))?\s*(?:saham|lembar))",
        r"(?:buyback|pembelian kembali)[^\n]*?(?:maksimum|maksimal)\s*([\d.,]+(?:\s*(?:miliar|juta|ribu))?\s*(?:saham|lembar))",
        r"([\d.,]+(?:\s*(?:miliar|juta|ribu))?\s*(?:saham|lembar saham))\s+(?:akan|yang akan)\s+(?:dibeli kembali|di-buyback)",
    ])
    if jml:
        p.jumlah_saham_maks = jml

    # Harga maksimum
    harga = _first_match(text, [
        r"(?:harga maksimum|harga tertinggi|harga plafon|maximum price)[^\n]*?(Rp\.?\s*[\d.,]+)",
        r"(?:tidak lebih dari|tidak melebihi)\s+(Rp\.?\s*[\d.,]+)\s+(?:per saham|\/saham)",
        r"(?:buyback|pembelian kembali)[^\n]*?(?:harga|price)\s+(?:maksimum)?\s*(Rp\.?\s*[\d.,]+)",
    ])
    if harga:
        p.harga_maksimum = harga

    # Periode pelaksanaan
    periode_mulai = _first_match(text, [
        rf"(?:dimulai|periode mulai|start date|mulai tanggal)[^\n]*?{_date_pat}",
        rf"(?:buyback|pembelian kembali)[^\n]*?(?:mulai\s+)?(?:dari\s+)?(?:tanggal\s+)?{_date_pat}",
    ])
    if periode_mulai:
        p.periode_mulai = periode_mulai

    periode_selesai = _first_match(text, [
        rf"(?:berakhir|selesai|sampai dengan|s\.?d\.?|hingga)[^\n]*?{_date_pat}\s*(?:\(|$|\n|\.|,|;)",
        rf"(?:buyback|pembelian kembali)[^\n]*?(?:s\.?d\.?|sampai|hingga)\s+{_date_pat}",
    ])
    if periode_selesai:
        p.periode_selesai = periode_selesai

    return p


def extract_stock_split_params(text: str) -> StockSplitParams:
    """
    Ekstraksi parameter Stock Split dari teks dokumen.

    Args:
        text: Teks dokumen yang mengandung informasi Stock Split.

    Returns:
        StockSplitParams dataclass dengan nilai-nilai yang ditemukan.
    """
    p = StockSplitParams()

    _date_pat = r"(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"

    # Rasio split
    rasio = _first_match(text, [
        r"(?:rasio|ratio)\s+(?:stock\s+split|pemecahan)[^\n]*?(\d+\s*[:/]\s*\d+)",
        r"(?:split|pemecahan)\s+(?:saham)?\s+(?:dengan rasio|rasio)?\s*(\d+\s*[:/]\s*\d+)",
        r"(?:setiap\s+)?(\d+)\s+(?:saham lama|lembar lama)\s+menjadi\s+(\d+)\s+(?:saham baru|lembar baru)",
        r"(\d+)\s*[:/]\s*(\d+)\s+(?:stock split|pemecahan saham)",
    ])
    if rasio:
        parts = re.findall(r"\d+", rasio)
        if len(parts) >= 2:
            p.rasio_split = f"{parts[0]}:{parts[1]}"
        else:
            p.rasio_split = rasio

    # Harga lama & baru (nominal saham)
    harga_lama = _first_match(text, [
        r"(?:nilai nominal lama|harga nominal sebelum|nominal lama)[^\n]*?(Rp\.?\s*[\d.,]+)",
        r"(?:dari|from)\s+(Rp\.?\s*[\d.,]+)\s+(?:per saham|\/saham|menjadi|to)",
    ])
    if harga_lama:
        p.harga_lama = harga_lama

    harga_baru = _first_match(text, [
        r"(?:nilai nominal baru|harga nominal sesudah|nominal baru)[^\n]*?(Rp\.?\s*[\d.,]+)",
        r"(?:menjadi|to)\s+(Rp\.?\s*[\d.,]+)\s+(?:per saham|\/saham)",
    ])
    if harga_baru:
        p.harga_baru = harga_baru

    # Tanggal efektif
    efektif = _first_match(text, [
        rf"(?:tanggal efektif|efektif berlaku|effective date)[^\n]*?{_date_pat}",
        rf"(?:stock split|pemecahan saham)\s+(?:efektif\s+)?{_date_pat}",
    ])
    if efektif:
        p.tanggal_efektif = efektif

    return p


def extract_rups_params(text: str, is_pemanggilan: bool = True) -> RupsParams:
    """
    Ekstraksi parameter RUPS / RUPSLB dari teks dokumen.

    Args:
        text: Teks dokumen yang mengandung informasi RUPS.
        is_pemanggilan: True jika ini adalah Pemanggilan RUPS, False jika Hasil RUPS.

    Returns:
        RupsParams dataclass dengan nilai-nilai yang ditemukan.
    """
    p = RupsParams(is_pemanggilan=is_pemanggilan)

    _date_pat = r"(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"

    # Tanggal RUPS
    tgl = _first_match(text, [
        rf"(?:rapat\s+(?:akan\s+)?diselenggarakan|pelaksanaan\s+rups?|tanggal\s+rups?)[^\n]*?{_date_pat}",
        rf"(?:hari,?\s+tanggal|akan\s+diadakan\s+pada)[^\n]*?{_date_pat}",
        rf"(?:Senin|Selasa|Rabu|Kamis|Jumat|Sabtu|Minggu),?\s+{_date_pat}",
    ])
    if tgl:
        p.tanggal_rups = tgl

    # Waktu RUPS
    waktu = _first_match(text, [
        r"(?:pukul|waktu|jam)[^\n]*?(\d{1,2}[:\.\s]\d{2}\s*(?:WIB|WITA|WIT)?(?:\s*s\.?d\.?\s*selesai)?)",
        r"(\d{1,2}[:\.\s]\d{2}\s*(?:WIB|WITA|WIT))[^\n]*?(?:rups|rapat)",
    ])
    if waktu:
        p.waktu_rups = waktu

    # Lokasi
    lokasi = _first_match(text, [
        r"(?:tempat|lokasi|bertempat\s+di|diadakan\s+di)[^\n]*?([A-Z][^\n,\.]{10,100})",
        r"(?:Gedung|Hotel|Kantor|Jl\.|Jalan)[^\n,\.]{5,80}",
    ])
    if lokasi:
        p.lokasi_rups = lokasi.strip()

    # Recording date / Eligible date
    rec = _first_match(text, [
        rf"(?:recording date|eligible date|daftar pemegang saham|DPS)[^\n]*?{_date_pat}",
        rf"(?:terdaftar dalam DPS|berhak hadir)[^\n]*?{_date_pat}",
    ])
    if rec:
        p.recording_date = rec

    # Kuorum (untuk hasil RUPS)
    if not is_pemanggilan:
        kuorum = _first_match(text, [
            r"(?:kuorum kehadiran|quorum)[^\n]*?([\d.,]+\s*%)",
            r"(?:dihadiri|hadir)\s+(?:oleh\s+)?(?:pemegang saham\s+)?(?:mewakili\s+)?([\d.,]+\s*%)",
        ])
        if kuorum:
            p.kuorum = kuorum

        keputusan = _first_match(text, [
            r"(?:keputusan|memutuskan|menyetujui)[^\n]*?([A-Z][^\n]{20,200})",
        ])
        if keputusan:
            p.keputusan = keputusan[:200]

    # Agenda (cari pola "Mata Acara" atau "Agenda")
    agenda_matches = re.finditer(
        r"(?:Mata Acara|Agenda)\s+(?:ke-?\s*)?(\d+|[IVX]+)\s*[:\.\-]\s*([^\n]{10,150})",
        text, re.IGNORECASE
    )
    for m in agenda_matches:
        nomor = m.group(1).strip()
        deskripsi = m.group(2).strip()
        p.agenda_list.append((f"Agenda {nomor}", deskripsi))

    return p


def extract_params(action_type: ActionType, text: str) -> Any:
    """
    Dispatcher: memanggil fungsi ekstraksi yang sesuai berdasarkan ActionType.

    Args:
        action_type: Tipe aksi korporasi yang telah terdeteksi.
        text: Teks dokumen sumber.

    Returns:
        Dataclass parameter yang sesuai (DividenParams, RightsIssueParams, dll.)
        atau GenericParams jika tidak ada matcher spesifik.
    """
    dispatcher = {
        ActionType.DIVIDEN:           lambda: extract_dividen_params(text),
        ActionType.RIGHTS_ISSUE:      lambda: extract_rights_issue_params(text),
        ActionType.PRIVATE_PLACEMENT: lambda: extract_rights_issue_params(text),
        ActionType.MTO:               lambda: extract_mto_params(text),
        ActionType.BUYBACK:           lambda: extract_buyback_params(text),
        ActionType.STOCK_SPLIT:       lambda: extract_stock_split_params(text),
        ActionType.RUPS_PEMANGGILAN:  lambda: extract_rups_params(text, is_pemanggilan=True),
        ActionType.RUPS:              lambda: extract_rups_params(text, is_pemanggilan=False),
    }
    fn = dispatcher.get(action_type)
    if fn:
        return fn()
    return GenericParams(ringkasan="[Tidak ada extractor spesifik untuk tipe ini]")


# ---------------------------------------------------------------------------
# Integrasi LLM Opsional
# ---------------------------------------------------------------------------

def _call_llm(prompt: str) -> Optional[str]:
    """
    Memanggil LLM melalui llm_client.py atau OpenAI-compatible API.

    Memeriksa CUSTOM_LLM_KEY di environment. Jika tidak tersedia,
    mengembalikan None sehingga placeholder akan digunakan.

    Args:
        prompt: Prompt teks untuk LLM.

    Returns:
        Respons teks dari LLM, atau None jika tidak tersedia.
    """
    api_key = os.environ.get("CUSTOM_LLM_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    # Coba import llm_client.py dari direktori yang sama atau sys.path
    try:
        llm_client_path = Path(__file__).parent / "llm_client.py"
        if llm_client_path.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("llm_client", str(llm_client_path))
            if spec and spec.loader:
                llm_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(llm_mod)  # type: ignore
                return llm_mod.complete(prompt)  # type: ignore
    except Exception as e:
        print(f"[!] llm_client.py load error: {e}")

    # Fallback: direct OpenAI-compatible call
    try:
        import urllib.request
        import urllib.parse

        base_url = os.environ.get("CUSTOM_LLM_BASE_URL", "https://api.openai.com/v1")
        model    = os.environ.get("CUSTOM_LLM_MODEL", "gpt-4o-mini")
        payload  = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[!] LLM API call error: {e}")
        return None


def _llm_or_placeholder(prompt: str) -> str:
    """
    Mencoba mendapatkan narasi dari LLM; jika gagal, kembalikan placeholder.

    Args:
        prompt: Prompt untuk LLM.

    Returns:
        Narasi dari LLM atau teks placeholder.
    """
    result = _call_llm(prompt)
    if result:
        return result
    return "[Analisis LLM tidak tersedia — isi manual]"


# ---------------------------------------------------------------------------
# Builder Laporan Markdown 8-Seksi
# ---------------------------------------------------------------------------

_ACTION_EMOJI: Dict[ActionType, str] = {
    ActionType.DIVIDEN:           "💰",
    ActionType.RIGHTS_ISSUE:      "📋",
    ActionType.PRIVATE_PLACEMENT: "🏢",
    ActionType.MTO:               "🎯",
    ActionType.BUYBACK:           "🛍️",
    ActionType.STOCK_SPLIT:       "✂️",
    ActionType.RUPS_PEMANGGILAN:  "📢",
    ActionType.RUPS:              "🏛️",
    ActionType.UNKNOWN:           "⚡",
    ActionType.WARAN_KONVERSI:    "🔄",
}

_ACTION_HEADLINE: Dict[ActionType, str] = {
    ActionType.DIVIDEN:           "Pengumuman Pembagian Dividen Tunai",
    ActionType.RIGHTS_ISSUE:      "Rencana Rights Issue / PMHMETD",
    ActionType.PRIVATE_PLACEMENT: "Penambahan Modal Tanpa HMETD (Private Placement)",
    ActionType.MTO:               "Mandatory Tender Offer (MTO)",
    ActionType.BUYBACK:           "Program Pembelian Kembali Saham (Buyback)",
    ActionType.STOCK_SPLIT:       "Pemecahan Nilai Nominal Saham (Stock Split)",
    ActionType.RUPS_PEMANGGILAN:  "Pemanggilan RUPS / RUPSLB",
    ActionType.RUPS:              "Hasil & Keputusan RUPS / RUPSLB",
    ActionType.UNKNOWN:           "Keterbukaan Informasi Aksi Korporasi",
    ActionType.WARAN_KONVERSI:    "Konversi Waran",
}


def build_markdown_report(
    emiten: str,
    action_type: ActionType,
    params: Any,
    source_path: str,
    raw_text: str = "",
) -> str:
    """
    Menghasilkan laporan Markdown institusional 8-seksi untuk satu aksi korporasi.

    Seksi laporan:
    1. Ringkasan Eksekutif & Tujuan Strategis
    2. Fakta Material & Parameter Keuangan
    3. Struktur Kepemilikan, Pengendali & Pembeli Siaga
    4. Alokasi & Rencana Penggunaan Dana
    5. Timeline & Jadwal Pelaksanaan
    6. Diagram Visual Flowchart (Mermaid)
    7. Rekomendasi Investor & Strategi Trading
    8. Hubungan Note Terkait (Knowledge Graph)

    Args:
        emiten: Kode saham emiten (contoh: "BUVA", "HUMI").
        action_type: ActionType enum tipe aksi korporasi.
        params: Dataclass parameter hasil ekstraksi (DividenParams, dll.).
        source_path: Path file sumber (PDF atau teks).
        raw_text: Teks mentah dokumen (opsional, untuk LLM context).

    Returns:
        String Markdown laporan lengkap 8-seksi.
    """
    today = datetime.now()
    today_str    = today.strftime("%Y-%m-%d")
    today_fn     = today.strftime("%Y%m%d")
    emoji        = _ACTION_EMOJI.get(action_type, "⚡")
    headline     = _ACTION_HEADLINE.get(action_type, "Aksi Korporasi")
    source_fname = Path(source_path).name if source_path else "N/A"

    lines: List[str] = []

    # ── HEADER ──────────────────────────────────────────────────────────────
    lines += [
        f"# {emoji} {headline} — [[{emiten}]]",
        "",
        f"⬅️ [[knowledge-base/daily-digests/Daily_Digest_{today_fn}|Kembali ke Daily Digest]] | 📅 **{today_str}** | 🎛️ [[Dashboard|Ke Dashboard Utama]]",
        "",
        "> [!IMPORTANT]",
        f"> Laporan ini disusun secara otomatis oleh **Corporate Action Intelligence Agent** pada **{today_str}**.",
        f"> Sumber dokumen: `{source_fname}`",
        "",
        "---",
        "",
    ]

    # ── SEKSI 1: RINGKASAN EKSEKUTIF ────────────────────────────────────────
    llm_prompt_exec = (
        f"Tulis ringkasan eksekutif singkat (3-4 kalimat) dalam Bahasa Indonesia "
        f"untuk aksi korporasi {action_type.value} oleh emiten {emiten} di BEI. "
        f"Jelaskan tujuan strategis dan dampak bagi investor."
        + (f"\n\nKonteks dokumen:\n{raw_text[:1500]}" if raw_text else "")
    )
    exec_summary = _llm_or_placeholder(llm_prompt_exec)

    lines += [
        "## 📌 1. Ringkasan Eksekutif & Tujuan Strategis",
        "",
        f"- **Kode & Nama Emiten**: `[[{emiten}]]`",
        f"- **Kategori Aksi Korporasi**: `{action_type.value}`",
        f"- **Dokumen Sumber**: `{source_fname}`",
        f"- **Tanggal Laporan**: `{today_str}`",
        "",
        exec_summary,
        "",
        "---",
        "",
    ]

    # ── SEKSI 2: FAKTA MATERIAL & PARAMETER KEUANGAN ────────────────────────
    lines += [
        "## 📊 2. Fakta Material & Parameter Keuangan",
        "",
        "| Parameter Utama | Nilai / Keterangan |",
        "| :--- | :--- |",
    ]

    if isinstance(params, DividenParams):
        lines += [
            f"| **Jenis Dividen** | `{params.jenis_dividen}` |",
            f"| **Nominal per Saham** | `{params.nominal_per_saham}` |",
            f"| **Total Nilai Dividen** | `{params.total_nilai}` |",
            f"| **Cum Date (Pasar Reguler)** | `{params.cum_date}` |",
            f"| **Ex Date** | `{params.ex_date}` |",
            f"| **Recording Date (DPS)** | `{params.recording_date}` |",
            f"| **Payment Date** | `{params.payment_date}` |",
        ]

    elif isinstance(params, RightsIssueParams):
        is_pp = (action_type == ActionType.PRIVATE_PLACEMENT)
        label = "PMTHMETD / Private Placement" if is_pp else "PMHMETD / Rights Issue"
        lines += [
            f"| **Jenis Aksi** | `{label}` |",
            f"| **Jumlah Saham Baru** | `{params.jumlah_saham_baru}` |",
            f"| **Rasio HMETD** | `{params.rasio_hmetd}` |",
            f"| **Harga Pelaksanaan** | `{params.harga_pelaksanaan}` |",
            f"| **Target Dana** | `{params.target_dana}` |",
            f"| **Pembeli Siaga** | `{params.pembeli_siaga}` |",
            f"| **Komitmen Pembeli Siaga** | `{params.komitmen_siaga}` |",
            f"| **Dilusi Maksimum** | `{params.dilusi_maksimum}` |",
            f"| **Pengendali Utama** | `{params.pengendali}` |",
        ]

    elif isinstance(params, MtoParams):
        lines += [
            f"| **Pengendali Baru** | `{params.pengendali_baru}` |",
            f"| **Pihak Pembeli** | `{params.pihak_pembeli}` |",
            f"| **Harga Penawaran MTO** | `{params.harga_penawaran}` |",
            f"| **Persentase Akuisisi** | `{params.persen_akuisisi}` |",
            f"| **Batas Waktu Tender** | `{params.batas_waktu}` |",
        ]

    elif isinstance(params, BuybackParams):
        lines += [
            f"| **Nilai Program Buyback** | `{params.nilai_program}` |",
            f"| **Jumlah Saham Maksimum** | `{params.jumlah_saham_maks}` |",
            f"| **Harga Maksimum** | `{params.harga_maksimum}` |",
            f"| **Periode Mulai** | `{params.periode_mulai}` |",
            f"| **Periode Selesai** | `{params.periode_selesai}` |",
        ]

    elif isinstance(params, StockSplitParams):
        lines += [
            f"| **Rasio Split** | `{params.rasio_split}` |",
            f"| **Harga Nominal Lama** | `{params.harga_lama}` |",
            f"| **Harga Nominal Baru** | `{params.harga_baru}` |",
            f"| **Tanggal Efektif** | `{params.tanggal_efektif}` |",
        ]

    elif isinstance(params, RupsParams):
        status = "Pemanggilan RUPS" if params.is_pemanggilan else "Hasil Keputusan RUPS"
        lines += [
            f"| **Status** | `{status}` |",
            f"| **Tanggal RUPS** | `{params.tanggal_rups}` |",
            f"| **Waktu** | `{params.waktu_rups}` |",
            f"| **Lokasi** | `{params.lokasi_rups}` |",
            f"| **Recording Date (DPS)** | `{params.recording_date}` |",
        ]
        if not params.is_pemanggilan and params.kuorum != "TBA":
            lines.append(f"| **Kuorum Kehadiran** | `{params.kuorum}` |")

    elif isinstance(params, GenericParams) and params.fakta_material:
        for item in params.fakta_material:
            p_name = item.get("parameter", "")
            p_val  = item.get("nilai_parameter", "")
            if p_name and p_val:
                lines.append(f"| **{p_name}** | `{p_val}` |")
    else:
        lines.append("| **Detail** | Lihat dokumen sumber. |")

    lines += ["", "---", ""]

    # ── SEKSI 3: STRUKTUR KEPEMILIKAN ────────────────────────────────────────
    lines += [
        "## 👥 3. Struktur Kepemilikan, Pengendali & Pembeli Siaga",
        "",
    ]

    if isinstance(params, RightsIssueParams):
        lines += [
            f"- **Pemegang Saham Pengendali**: `{params.pengendali}`",
            f"- **Pembeli Siaga (Standby Buyer)**: `{params.pembeli_siaga}`",
            f"- **Komitmen Pembeli Siaga**: `{params.komitmen_siaga}`",
            f"- **Dilusi Maksimum** (jika tidak exercise HMETD): `{params.dilusi_maksimum}`",
        ]
    elif isinstance(params, MtoParams):
        lines += [
            f"- **Pengendali Baru / Acquirer**: `{params.pengendali_baru}`",
            f"- **Persentase Saham Diakuisisi**: `{params.persen_akuisisi}`",
            f"- **Harga Penawaran**: `{params.harga_penawaran}`",
        ]
    else:
        lines.append(
            f"- **Emiten**: `{emiten}` | Informasi kepemilikan mengacu pada dokumen resmi sumber."
        )

    lines += ["", "---", ""]

    # ── SEKSI 4: ALOKASI & PENGGUNAAN DANA ──────────────────────────────────
    lines += [
        "## 🎯 4. Alokasi & Rencana Penggunaan Dana",
        "",
    ]

    if isinstance(params, RightsIssueParams) and params.alokasi_dana:
        lines += [
            "| Peruntukan Dana | Alokasi (%) |",
            "| :--- | :---: |",
        ]
        for nama, pct in params.alokasi_dana:
            lines.append(f"| {nama.strip()} | `{pct}` |")
        lines += [
            "",
            f"- **Total Target Dana**: `{params.target_dana}`",
        ]
    elif isinstance(params, BuybackParams):
        lines += [
            f"- **Nilai Program Buyback**: `{params.nilai_program}`",
            "- **Tujuan**: Meningkatkan EPS, menopang harga saham, dan mengoptimalkan struktur modal.",
        ]
    elif isinstance(params, MtoParams):
        lines += [
            f"- **Harga Penawaran MTO**: `{params.harga_penawaran}` per saham",
            "- **Tujuan**: Konsolidasi kepemilikan pasca perubahan pengendali.",
        ]
    else:
        lines.append(
            "- Informasi alokasi dana belum tersedia — lihat prospektus / dokumen resmi."
        )

    lines += ["", "---", ""]

    # ── SEKSI 5: TIMELINE & JADWAL ───────────────────────────────────────────
    lines += [
        "## 📅 5. Timeline & Jadwal Pelaksanaan",
        "",
        "| Tahapan / Event | Tanggal |",
        "| :--- | :---: |",
    ]

    if isinstance(params, DividenParams):
        lines += [
            f"| **Cum Date (Pasar Reguler & Negosiasi)** | `{params.cum_date}` |",
            f"| **Ex Date** | `{params.ex_date}` |",
            f"| **Recording Date (DPS)** | `{params.recording_date}` |",
            f"| **Payment Date (Pembayaran ke RDN)** | `{params.payment_date}` |",
        ]
    elif isinstance(params, RightsIssueParams):
        if params.jadwal:
            for event, tgl in params.jadwal:
                lines.append(f"| **{event}** | `{tgl}` |")
        else:
            lines += [
                f"| **Harga Pelaksanaan HMETD** | `{params.harga_pelaksanaan}` |",
                "| **Periode Pelaksanaan HMETD** | `Terjadwal — lihat prospektus` |",
            ]
    elif isinstance(params, MtoParams):
        lines += [
            f"| **Batas Waktu Tender** | `{params.batas_waktu}` |",
        ]
    elif isinstance(params, BuybackParams):
        lines += [
            f"| **Periode Mulai Buyback** | `{params.periode_mulai}` |",
            f"| **Periode Selesai Buyback** | `{params.periode_selesai}` |",
        ]
    elif isinstance(params, StockSplitParams):
        lines += [
            f"| **Tanggal Efektif Stock Split** | `{params.tanggal_efektif}` |",
        ]
    elif isinstance(params, RupsParams):
        lines += [
            f"| **Recording Date / DPS** | `{params.recording_date}` |",
            f"| **Pelaksanaan RUPS** | `{params.tanggal_rups}` |",
        ]
    else:
        lines.append("| **Jadwal** | Lihat dokumen sumber. |")

    lines += ["", "---", ""]

    # ── SEKSI 6: DIAGRAM MERMAID ─────────────────────────────────────────────
    lines += [
        "## 📈 6. Diagram Visual Flowchart (Mermaid)",
        "",
    ]
    lines.append(_build_mermaid(emiten, action_type, params))
    lines += ["", "---", ""]

    # ── SEKSI 7: REKOMENDASI INVESTOR ────────────────────────────────────────
    llm_prompt_rec = (
        f"Berikan 3-4 poin rekomendasi strategis singkat untuk investor saham Indonesia "
        f"terkait aksi korporasi {action_type.value} oleh emiten {emiten}. "
        f"Sertakan strategi entry/exit, manajemen risiko, dan peluang arbitrase jika ada. "
        f"Gunakan Bahasa Indonesia profesional. Format sebagai bullet points."
        + (f"\n\nKonteks:\n{raw_text[:1000]}" if raw_text else "")
    )
    rec_text = _llm_or_placeholder(llm_prompt_rec)

    lines += [
        "## 💡 7. Rekomendasi Investor & Strategi Trading",
        "",
        rec_text,
        "",
        "---",
        "",
    ]

    # ── SEKSI 8: KNOWLEDGE GRAPH ─────────────────────────────────────────────
    lines += [
        "## 🔗 8. Hubungan Note Terkait (Knowledge Graph)",
        "",
        f"- [[knowledge-base/daily-digests/Daily_Digest_{today_fn}|📄 Daily Digest {today_str}]]",
        f"- [[knowledge-base/trading-signals/Trading_Signals_{today_fn}|🎯 Sinyal Cuan {today_str}]]",
        f"- [[{emiten}|🏬 Halaman Emiten {emiten}]]",
        "- [[Dashboard|🎛️ Kembali ke Dashboard Utama]]",
        "",
        "---",
        "",
        f"*Laporan dibuat otomatis oleh Corporate Action Intelligence Agent · {today_str}*",
    ]

    return "\n".join(lines)


def _build_mermaid(emiten: str, action_type: ActionType, params: Any) -> str:
    """
    Membangun blok diagram Mermaid yang sesuai dengan tipe aksi korporasi.

    Args:
        emiten: Kode saham emiten.
        action_type: Tipe aksi korporasi.
        params: Dataclass parameter hasil ekstraksi.

    Returns:
        String blok kode Mermaid (```mermaid...```).
    """
    if isinstance(params, DividenParams):
        return (
            "```mermaid\n"
            "graph LR\n"
            f'    A["📅 Cum Date\\n{params.cum_date}"] --> B["📋 Ex Date\\n{params.ex_date}"]\n'
            f'    B --> C["📝 Recording Date\\n{params.recording_date}"]\n'
            f'    C --> D["💸 Payment Date\\n{params.payment_date}\\n{params.nominal_per_saham} / saham"]\n'
            "```"
        )

    elif isinstance(params, RightsIssueParams) and action_type == ActionType.RIGHTS_ISSUE:
        return (
            "```mermaid\n"
            "graph TD\n"
            f'    Emiten["🏬 {emiten}\\nPMHMETD Rights Issue"] --> HMETD["📋 Penerbitan HMETD\\nRasio: {params.rasio_hmetd}\\nHarga: {params.harga_pelaksanaan}"]\n'
            f'    HMETD --> Exercise["✅ Pemegang Saham\\nExercise HMETD"]\n'
            f'    HMETD --> Siaga["🏦 Pembeli Siaga\\n{params.pembeli_siaga}\\nKomitmen: {params.komitmen_siaga}"]\n'
            f'    Exercise --> Dana["💵 Target Dana\\n{params.target_dana}"]\n'
            f'    Siaga --> Dana\n'
            "```"
        )

    elif isinstance(params, RightsIssueParams) and action_type == ActionType.PRIVATE_PLACEMENT:
        return (
            "```mermaid\n"
            "graph TD\n"
            f'    Investor["🏦 Investor Independen\\n/ Kreditur"] -->|"Konversi Utang / Injeksi Modal"| Emiten["🏬 {emiten}\\nPMTHMETD"]\n'
            f'    Emiten -->|"Penerbitan Saham Baru Non-Preemptive"| Struktur["📈 Penyehatan Permodalan\\n{params.target_dana}"]\n'
            "```"
        )

    elif isinstance(params, MtoParams):
        return (
            "```mermaid\n"
            "graph TD\n"
            f'    Controller["🏢 {params.pengendali_baru}\\nAcquirer"] -->|"Mandatory Tender Offer\\n{params.persen_akuisisi}"| Emiten["🏬 {emiten}"]\n'
            f'    Emiten -->|"Harga Penawaran\\n{params.harga_penawaran}"| Public["👥 Pemegang Saham Publik\\nBatas: {params.batas_waktu}"]\n'
            "```"
        )

    elif isinstance(params, BuybackParams):
        return (
            "```mermaid\n"
            "graph TD\n"
            f'    Emiten["🏬 {emiten}\\nBuyback Program"] -->|"Dana: {params.nilai_program}"| Treasury["💰 Treasury Stock\\nMaks: {params.jumlah_saham_maks}"]\n'
            f'    Treasury -->|"Pembelian Pasar Reguler"| Market["📈 Support Harga\\n& EPS Accretion"]\n'
            "```"
        )

    elif isinstance(params, StockSplitParams):
        return (
            "```mermaid\n"
            "graph LR\n"
            f'    Old["📌 Nominal Lama\\n{params.harga_lama}"] -->|"Stock Split {params.rasio_split}\\nEfektif: {params.tanggal_efektif}"| New["📌 Nominal Baru\\n{params.harga_baru}"]\n'
            f'    New --> Likuid["📈 Peningkatan\\nLikuiditas Saham"]\n'
            "```"
        )

    elif isinstance(params, RupsParams):
        today_str = datetime.now().strftime("%Y-%m-%d")
        if params.is_pemanggilan:
            return (
                "```mermaid\n"
                "graph LR\n"
                f'    Notice["📢 Pemanggilan RUPS\\n{today_str}"] --> Rec["📝 Recording Date\\n{params.recording_date}"]\n'
                f'    Rec --> Meeting["🏛️ Pelaksanaan RUPS\\n{params.tanggal_rups}\\n{params.waktu_rups}"]\n'
                "```"
            )
        else:
            return (
                "```mermaid\n"
                "graph LR\n"
                f'    Meeting["🏛️ RUPS Dilaksanakan\\n{params.tanggal_rups}"] --> Vote["🗳️ Pemungutan Suara\\nKuorum: {params.kuorum}"]\n'
                f'    Vote --> Decision["✅ Keputusan Disetujui\\n{params.keputusan[:60]}..."]\n'
                "```"
            )

    # Generic fallback
    return (
        "```mermaid\n"
        "graph TD\n"
        f'    Emiten["🏬 {emiten}"] -->|"{action_type.value}"| Action["⚡ Aksi Korporasi\\nLihat dokumen sumber"]\n'
        "```"
    )


# ---------------------------------------------------------------------------
# Simpan Laporan ke File
# ---------------------------------------------------------------------------

def save_report(
    emiten: str,
    action_type: ActionType,
    date_str: str,
    content: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Menyimpan laporan Markdown ke dua lokasi:
    - PRIMARY : G:/My Drive/Model2/Finplan_analyst/knowledge-base/corporate-actions/
    - BACKUP  : G:/My Drive/Model2/reports/summaries/corporate-actions/

    Subfolder ditentukan otomatis berdasarkan ActionType.

    Args:
        emiten: Kode saham emiten (contoh: "BUVA").
        action_type: Tipe aksi korporasi sebagai ActionType enum.
        date_str: Tanggal laporan dalam format "YYYY-MM-DD" atau "YYYYMMDD".
        content: Konten Markdown laporan.

    Returns:
        Tuple (primary_path, backup_path) — None jika gagal menyimpan.
    """
    # Normalisasi date_str → YYYYMMDD untuk nama file
    date_fn = date_str.replace("-", "")
    if len(date_fn) != 8 or not date_fn.isdigit():
        date_fn = datetime.now().strftime("%Y%m%d")

    # Subfolder per tipe
    subfolder_map: Dict[ActionType, str] = {
        ActionType.DIVIDEN:           "dividen",
        ActionType.RIGHTS_ISSUE:      "rights-issue",
        ActionType.PRIVATE_PLACEMENT: "private-placement",
        ActionType.MTO:               "tender-offer",
        ActionType.BUYBACK:           "buyback",
        ActionType.STOCK_SPLIT:       "stock-split",
        ActionType.RUPS_PEMANGGILAN:  "rups/pemanggilan",
        ActionType.RUPS:              "rups/hasil-rups",
        ActionType.UNKNOWN:           "general-disclosures",
    }
    subfolder = subfolder_map.get(action_type, "general-disclosures")
    filename  = f"{emiten}_{action_type.value}_{date_fn}.md"

    # -- PRIMARY: knowledge-base --
    primary_dir  = PRIMARY_DIR / subfolder
    primary_path = primary_dir / filename
    saved_primary: Optional[str] = None
    try:
        primary_dir.mkdir(parents=True, exist_ok=True)
        primary_path.write_text(content, encoding="utf-8")
        saved_primary = str(primary_path)
        print(f"[+] PRIMARY saved: {primary_path}")
    except Exception as e:
        print(f"[!] ERROR menyimpan ke PRIMARY ({primary_path}): {e}")

    # -- BACKUP: reports/summaries --
    backup_dir   = BACKUP_DIR / subfolder
    backup_path  = backup_dir / filename
    saved_backup: Optional[str] = None
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(content, encoding="utf-8")
        saved_backup = str(backup_path)
        print(f"[+] BACKUP saved:  {backup_path}")
    except Exception as e:
        print(f"[!] ERROR menyimpan ke BACKUP ({backup_path}): {e}")

    return saved_primary, saved_backup


# ---------------------------------------------------------------------------
# Fungsi Pipeline Utama
# ---------------------------------------------------------------------------

def process_corporate_action(
    emiten: str,
    source_path: str = "",
    raw_text: str = "",
    date_str: str = "",
    forced_action_type: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Pipeline lengkap pemrosesan satu aksi korporasi:
    1. Baca PDF (jika source_path tersedia)
    2. Auto-deteksi tipe aksi
    3. Ekstraksi parameter
    4. Build laporan Markdown
    5. Simpan ke PRIMARY & BACKUP

    Args:
        emiten: Kode saham (contoh: "BUVA").
        source_path: Path ke file PDF sumber (opsional).
        raw_text: Teks alternatif jika tidak ada PDF (opsional).
        date_str: Tanggal laporan "YYYY-MM-DD" (default: hari ini).
        forced_action_type: Override tipe aksi (nama ActionType enum, opsional).

    Returns:
        Tuple (primary_path, backup_path) dari hasil save_report.
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Baca teks
    text = raw_text
    if source_path and not text:
        text = read_pdf_text(source_path)

    if not text:
        print(f"[!] Tidak ada teks untuk diproses. Emiten: {emiten}")
        return None, None

    # 2. Skip Konversi Waran
    if forced_action_type:
        try:
            action_type = ActionType(forced_action_type)
        except ValueError:
            # Coba match by name
            try:
                action_type = ActionType[forced_action_type.upper()]
            except KeyError:
                print(f"[!] ActionType '{forced_action_type}' tidak valid. Menggunakan auto-detect.")
                action_type = detect_action_type(text)
    else:
        action_type = detect_action_type(text)

    if action_type == ActionType.WARAN_KONVERSI:
        print(f"[~] Skipping Konversi Waran untuk {emiten} — tipe ini tidak diproses.")
        return None, None

    # 3. Ekstraksi parameter
    params = extract_params(action_type, text)
    print(f"[+] Parameter diekstrak untuk {action_type.value}: {type(params).__name__}")

    # 4. Build laporan
    content = build_markdown_report(
        emiten=emiten,
        action_type=action_type,
        params=params,
        source_path=source_path,
        raw_text=text,
    )
    print(f"[+] Laporan Markdown dihasilkan: {len(content)} karakter")

    # 5. Simpan
    return save_report(emiten, action_type, date_str, content)


# ---------------------------------------------------------------------------
# Fungsi Kompatibilitas Mundur (Backward Compatibility)
# ---------------------------------------------------------------------------

def _extract_fact_map(facts_list: List[Any]) -> Dict[str, str]:
    """Helper backward-compat: konversi list fakta material ke dict."""
    fact_map: Dict[str, str] = {}
    if not facts_list:
        return fact_map
    for item in facts_list:
        if isinstance(item, dict):
            p = str(item.get("parameter", "")).strip()
            v = str(item.get("nilai_parameter", "")).strip()
            if p and v:
                fact_map[p.lower()] = v
                fact_map[p] = v
        elif isinstance(item, tuple) and len(item) == 2:
            p = str(item[0]).strip()
            v = str(item[1]).strip()
            if p and v:
                fact_map[p.lower()] = v
                fact_map[p] = v
    return fact_map


def build_corporate_action_report(
    emiten: str,
    category: str,
    title: str,
    filename: str,
    json_dict: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Fungsi kompatibilitas mundur (backward-compatible) dengan versi lama.

    Menerima data yang sudah diekstrak dalam json_dict dan membangun laporan
    menggunakan infrastruktur baru. Cocok untuk digunakan oleh daily_run.py
    yang masih menggunakan signature lama.

    Args:
        emiten: Kode saham.
        category: Kategori aksi (string bebas).
        title: Judul dokumen resmi dari BEI.
        filename: Nama / path file sumber.
        json_dict: Dict berisi ringkasan_eksekutif dan fakta_material.

    Returns:
        Path file laporan yang disimpan (PRIMARY), atau None jika gagal.
    """
    jdict = json_dict or {}
    exec_sum    = jdict.get("ringkasan_eksekutif", f"Pengumuman {category} oleh {emiten}.")
    facts_list  = jdict.get("fakta_material", [])
    facts       = _extract_fact_map(facts_list)

    # Bangun pseudo-text agar auto-detect bisa bekerja
    pseudo_text = f"{category}\n{title}\n{exec_sum}\n"
    for k, v in facts.items():
        pseudo_text += f"{k}: {v}\n"

    # Deteksi action_type
    action_type = detect_action_type(pseudo_text)

    # Ekstraksi parameter dari dict langsung (jika ada)
    if action_type == ActionType.DIVIDEN:
        p = DividenParams(
            nominal_per_saham = facts.get("nominal dividen") or facts.get("dividen per saham") or "TBA",
            total_nilai       = facts.get("total dividen") or facts.get("total nilai dividen") or "TBA",
            cum_date          = facts.get("cum dividen") or facts.get("cum date") or "Terjadwal",
            ex_date           = facts.get("ex dividen") or facts.get("ex date") or "Terjadwal",
            recording_date    = facts.get("recording date") or facts.get("daftar pemegang") or "Terjadwal",
            payment_date      = facts.get("pembayaran dividen") or facts.get("tanggal pembayaran") or "Terjadwal",
        )
        params: Any = p

    elif action_type in (ActionType.RIGHTS_ISSUE, ActionType.PRIVATE_PLACEMENT):
        p2 = RightsIssueParams(
            harga_pelaksanaan = facts.get("harga pelaksanaan hmetd") or facts.get("harga pelaksanaan") or "TBA",
            target_dana       = facts.get("target modal minimum") or facts.get("target total dana") or "TBA",
            pembeli_siaga     = facts.get("pembeli siaga") or "TBA",
            pengendali        = facts.get("pemegang saham pengendali") or "TBA",
            dilusi_maksimum   = facts.get("dilusi maksimum") or "TBA",
        )
        params = p2

    elif action_type == ActionType.BUYBACK:
        p3 = BuybackParams(
            nilai_program      = facts.get("alokasi dana buyback") or facts.get("total budget") or "TBA",
            harga_maksimum     = facts.get("harga maksimum buyback") or "Harga Pasar Reguler",
            jumlah_saham_maks  = facts.get("jumlah saham buyback") or facts.get("persentase saham") or "TBA",
        )
        params = p3

    elif action_type == ActionType.MTO:
        p4 = MtoParams(
            pengendali_baru = jdict.get("pengendali_baru") or "TBA",
            harga_penawaran = facts.get("harga penawaran") or "TBA",
            persen_akuisisi = facts.get("persentase akuisisi") or "TBA",
        )
        params = p4

    else:
        gp = GenericParams(
            fakta_material = [f for f in facts_list if isinstance(f, dict)],
            ringkasan      = exec_sum,
        )
        params = gp

    # Tanggal dari filename
    m_date   = re.match(r"^(\d{8})_", os.path.basename(filename)) if filename else None
    date_fn  = m_date.group(1) if m_date else datetime.now().strftime("%Y%m%d")
    date_str = f"{date_fn[:4]}-{date_fn[4:6]}-{date_fn[6:]}"

    content = build_markdown_report(
        emiten=emiten,
        action_type=action_type,
        params=params,
        source_path=filename or "",
        raw_text=pseudo_text,
    )

    primary, _ = save_report(emiten, action_type, date_str, content)
    return primary


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="corporate_action_builder",
        description=(
            "Corporate Action Builder — Swarm Intelijen Pasar Modal Indonesia\n"
            "Memproses dokumen aksi korporasi IDX menjadi laporan Markdown institusional."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python corporate_action_builder.py --emiten BUVA --file reports/raw/BUVA/PMHMETD.pdf --date 2026-09-23
  python corporate_action_builder.py --emiten HUMI --file reports/raw/HUMI/Dividen.pdf
  python corporate_action_builder.py --emiten MAPI --text "Perseroan mengumumkan MTO..." --type MTO
  python corporate_action_builder.py --emiten BBCA --file laporan.pdf --date 2026-09-23 --type Dividen
        """,
    )
    parser.add_argument(
        "--emiten", "-e",
        required=True,
        help="Kode saham emiten (contoh: BUVA, HUMI, BBCA)",
    )
    parser.add_argument(
        "--file", "-f",
        default="",
        help="Path ke file PDF sumber (absolut atau relatif)",
    )
    parser.add_argument(
        "--text", "-t",
        default="",
        help="Teks dokumen langsung (alternatif --file)",
    )
    parser.add_argument(
        "--date", "-d",
        default="",
        help="Tanggal laporan format YYYY-MM-DD (default: hari ini)",
    )
    parser.add_argument(
        "--type",
        default="",
        dest="action_type",
        help=(
            "Override tipe aksi korporasi. Pilihan: "
            "Dividen, Rights_Issue, Tender_Offer, Buyback, Stock_Split, "
            "Hasil_RUPS, Pemanggilan_RUPS, Private_Placement"
        ),
    )
    parser.add_argument(
        "--output", "-o",
        default="",
        help="Cetak konten Markdown ke stdout sebelum menyimpan",
        action="store_true",
    )
    return parser.parse_args()


def main() -> None:
    """
    Entry point CLI untuk corporate_action_builder.

    Menjalankan pipeline lengkap: baca PDF → deteksi → ekstrak → laporan → simpan.
    """
    args = _parse_args()

    emiten      = args.emiten.upper().strip()
    source_path = args.file
    raw_text    = args.text
    date_str    = args.date or datetime.now().strftime("%Y-%m-%d")
    forced_type = args.action_type or ""

    print("=" * 65)
    print("  Corporate Action Builder — Swarm Intelijen Pasar Modal IDX")
    print("=" * 65)
    print(f"  Emiten  : {emiten}")
    print(f"  Sumber  : {source_path or '(teks langsung)'}")
    print(f"  Tanggal : {date_str}")
    if forced_type:
        print(f"  Tipe    : {forced_type} (dipaksa)")
    print("-" * 65)

    primary, backup = process_corporate_action(
        emiten=emiten,
        source_path=source_path,
        raw_text=raw_text,
        date_str=date_str,
        forced_action_type=forced_type if forced_type else None,
    )

    print("=" * 65)
    if primary:
        print(f"  ✅ PRIMARY : {primary}")
    if backup:
        print(f"  ✅ BACKUP  : {backup}")
    if not primary and not backup:
        print("  ❌ Laporan tidak berhasil disimpan.")
    print("=" * 65)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        # Demo mode: jalankan contoh tanpa argumen
        print("[DEMO MODE] Menjalankan contoh Dividen HUMI...")
        sample_text = """
        Keterbukaan Informasi Dividen Tunai HUMI
        Perseroan mengumumkan pembagian Dividen Tunai Final sebesar Rp 25 per saham
        kepada seluruh pemegang saham. Total nilai dividen adalah Rp 150 Miliar.
        Cum Date Dividen Pasar Reguler dan Negosiasi: 15 Oktober 2026
        Ex Date Dividen Pasar Reguler dan Negosiasi: 16 Oktober 2026
        Recording Date: 17 Oktober 2026
        Tanggal Pembayaran Dividen: 30 Oktober 2026
        """
        primary, backup = process_corporate_action(
            emiten="HUMI",
            raw_text=sample_text,
            date_str=datetime.now().strftime("%Y-%m-%d"),
        )
        if primary:
            print(f"\n[DEMO] Laporan tersimpan di:\n  PRIMARY: {primary}\n  BACKUP:  {backup}")
