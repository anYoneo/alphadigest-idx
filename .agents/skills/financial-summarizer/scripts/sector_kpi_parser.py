#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
sector_kpi_parser.py
================================================================================
Regex & Text Parser KPI Spesifik Per Sektor — Swarm Intelijen Pasar Modal IDX
--------------------------------------------------------------------------------
Modul ini mengekstrak Key Performance Indicators (KPI) spesifik sektor dari
teks yang telah diekstrak dari PDF laporan keuangan / keterbukaan informasi.

Sektor yang didukung:
  • Perbankan / Multifinance  (NIM, NPL, CAR, CASA, LDR, NPF, CoF)
  • Telekomunikasi             (ARPU, Pelanggan, Tenancy Ratio, Fiber)
  • Pertambangan               (Produksi, Penjualan, ASP, Cash Cost, Strip Ratio)
  • Energi & Utilitas          (Kapasitas MW, Capacity Factor, Tarif, PPA)
  • Multifinance               (NPF, Cost of Funds, Pembiayaan)
  • Agrikultur                 (Lahan, TBS, CPO, Yield, ASP CPO)

Source of Truth sektor: g:/My Drive/Model2/.agents/sector_map.json

Standar : Python 3.12, type hints, docstrings, try-except
Penulis  : Swarm Intelijen Pasar Modal — Financial Data Extractor Agent
Versi    : 1.0.0
Tanggal  : 2026-09-23
================================================================================
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Pastikan output konsol Windows mendukung UTF-8 (mencegah UnicodeEncodeError)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# KONSTANTA PATH
# ─────────────────────────────────────────────────────────────────────────────
_SECTOR_MAP_PATH = Path(r"g:/My Drive/Model2/.agents/sector_map.json")

# Mapping sektor ke parser name (lowercase key)
_SECTOR_PARSER_MAP: dict[str, str] = {
    # Format persis sector_map.json
    "multifinance & perbankan":    "banking",
    "energi & utilitas":           "energy",
    "telekomunikasi & teknologi":  "telecom",
    "pertambangan":                "mining",
    "agrikultur":                  "agriculture",
    # Alias / substring
    "perbankan":                   "banking",
    "bank":                        "banking",
    "banking":                     "banking",
    "multifinance":                "multifinance",
    "pembiayaan":                  "multifinance",
    "telekomunikasi":              "telecom",
    "telecom":                     "telecom",
    "teknologi":                   "telecom",
    "mining":                      "mining",
    "batubara":                    "mining",
    "energi":                      "energy",
    "energy":                      "energy",
    "utilitas":                    "energy",
    "agriculture":                 "agriculture",
    "perkebunan":                  "agriculture",
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(raw: str) -> Optional[float]:
    """
    Konversi string angka ke float.
    Toleran terhadap:
      - Titik ribuan vs koma desimal (format Indonesia vs internasional)
      - Spasi di antara digit
      - Tanda persen yang menyertai angka

    Parameters
    ----------
    raw : str
        String angka yang akan dikonversi.

    Returns
    -------
    float or None
        Nilai float jika berhasil, None jika gagal.
    """
    if raw is None:
        return None
    cleaned = raw.strip().replace("%", "").replace(" ", "")
    # Deteksi format Indonesia: 1.234,56 → 1234.56
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # Format internasional atau mixed: ganti koma desimal dengan titik
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _find_value(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[float]:
    """
    Cari pola regex dalam teks dan kembalikan nilai float dari grup pertama.

    Parameters
    ----------
    pattern : str
        Pola regex. Grup pertama harus menangkap nilai numerik.
    text : str
        Teks sumber hasil ekstraksi PDF.
    flags : int
        Flag regex. Default: re.IGNORECASE.

    Returns
    -------
    float or None
    """
    match = re.search(pattern, text, flags)
    if match:
        return _to_float(match.group(1))
    return None


def _find_all_values(pattern: str, text: str) -> list[float]:
    """
    Temukan semua kemunculan pola dalam teks, kembalikan sebagai list float.
    """
    matches = re.findall(pattern, text, re.IGNORECASE)
    result = []
    for m in matches:
        val = _to_float(m) if isinstance(m, str) else _to_float(m[0])
        if val is not None:
            result.append(val)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET SECTOR
# ─────────────────────────────────────────────────────────────────────────────

def get_sector(emiten: str) -> str:
    """
    Dapatkan nama sektor emiten dari sector_map.json.

    File sector_map.json diharapkan berstruktur:
      {
        "BBRI": "Perbankan",
        "TLKM": "Telekomunikasi",
        ...
      }
    atau nested:
      {
        "sectors": {
          "Perbankan": ["BBRI", "BBCA", ...],
          ...
        }
      }

    Parameters
    ----------
    emiten : str
        Kode emiten (contoh: 'BBRI').

    Returns
    -------
    str
        Nama sektor (lowercase) emiten, atau 'general' jika tidak ditemukan.
    """
    emiten_upper = emiten.upper().strip()
    try:
        with open(_SECTOR_MAP_PATH, "r", encoding="utf-8") as f:
            sector_map: dict = json.load(f)

        # Format 1: flat dict {emiten: sektor}
        if emiten_upper in sector_map:
            return str(sector_map[emiten_upper]).lower()

        # Format 2: nested {sectors: {sektor: [emiten, ...]}}
        nested: dict = sector_map.get("sectors", {})
        for sector_name, emiten_list in nested.items():
            if emiten_upper in [e.upper() for e in emiten_list]:
                return sector_name.lower()

        # Format 3: list of objects [{emiten: "BBRI", sector: "Perbankan"}, ...]
        emiten_list_obj: list = sector_map.get("emitens", [])
        for item in emiten_list_obj:
            if isinstance(item, dict) and item.get("emiten", "").upper() == emiten_upper:
                return str(item.get("sector", "General")).lower()

    except FileNotFoundError:
        # sector_map.json belum ada — log warning, lanjutkan dengan General
        print(
            f"⚠️  sector_map.json tidak ditemukan di: {_SECTOR_MAP_PATH}. "
            f"Gunakan sektor 'General'.",
            file=sys.stderr,
        )
    except json.JSONDecodeError as exc:
        print(f"⚠️  Gagal parse sector_map.json: {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"⚠️  Error membaca sektor untuk {emiten}: {exc}", file=sys.stderr)

    return "general"


# ─────────────────────────────────────────────────────────────────────────────
# 2. BANKING KPIs
# ─────────────────────────────────────────────────────────────────────────────

def parse_banking_kpis(text: str) -> dict:
    """
    Ekstrak KPI utama sektor Perbankan dari teks laporan keuangan.

    KPI yang diekstrak:
      - NIM      : Net Interest Margin (%)
      - NPL Gross: Non-Performing Loan Gross (%)
      - NPL Net  : Non-Performing Loan Net (%)
      - CAR      : Capital Adequacy Ratio (%)
      - CASA     : Current Account Savings Account Ratio (%)
      - LDR/LFR  : Loan-to-Deposit / Loan-to-Funding Ratio (%)

    Parameters
    ----------
    text : str
        Teks hasil ekstraksi PDF.

    Returns
    -------
    dict
        KPI banking dengan nilai float (atau None jika tidak ditemukan).
        Contoh: {'nim': 5.23, 'npl_gross': 2.10, 'npl_net': 0.85, ...}
    """
    kpis: dict[str, Optional[float]] = {
        "nim": None,
        "npl_gross": None,
        "npl_net": None,
        "car": None,
        "casa_ratio": None,
        "ldr_lfr": None,
    }

    try:
        # NIM — Net Interest Margin
        kpis["nim"] = _find_value(
            r"NIM\s*(?:[:\-=]|tercatat|mencapai|sebesar)?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"Net\s+Interest\s+Margin\s*(?:[:\-=]|tercatat|mencapai|sebesar)?\s*([\d.,]+)\s*%?",
            text,
        )

        # NPL Gross
        kpis["npl_gross"] = _find_value(
            r"NPL\s+[Gg]ross\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"[Gg]ross\s+NPL\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

        # NPL Net
        kpis["npl_net"] = _find_value(
            r"NPL\s+[Nn]et\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"[Nn]et\s+NPL\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

        # CAR — Capital Adequacy Ratio
        kpis["car"] = _find_value(
            r"CAR\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"Capital\s+Adequacy\s+Ratio\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"Rasio\s+Kecukupan\s+Modal\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

        # CASA Ratio
        kpis["casa_ratio"] = _find_value(
            r"CASA\s*(?:Ratio|Rasio)?\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"(?:Current\s+Account|Tabungan)\s+(?:&|dan|and)\s+(?:Savings|Giro).*?[:\-=]\s*([\d.,]+)\s*%?",
            text,
        )

        # LDR / LFR
        kpis["ldr_lfr"] = _find_value(
            r"L[DF]R\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"Loan[- ]to[- ](?:Deposit|Funding)\s+Ratio\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

    except Exception as exc:
        kpis["_error"] = str(exc)  # type: ignore[assignment]

    return kpis


# ─────────────────────────────────────────────────────────────────────────────
# 3. TELECOM KPIs
# ─────────────────────────────────────────────────────────────────────────────

def parse_telecom_kpis(text: str) -> dict:
    """
    Ekstrak KPI utama sektor Telekomunikasi & Teknologi dari teks laporan.

    KPI yang diekstrak:
      - ARPU            : Average Revenue Per User (Rp/bulan atau ribu Rp)
      - pelanggan_juta  : Jumlah pelanggan (juta)
      - tenancy_ratio   : Tenancy ratio tower (x)
      - coverage_fiber_km: Coverage jaringan fiber optik (km)

    Parameters
    ----------
    text : str
        Teks hasil ekstraksi PDF.

    Returns
    -------
    dict
    """
    kpis: dict[str, Optional[float]] = {
        "arpu_rp": None,
        "pelanggan_juta": None,
        "tenancy_ratio": None,
        "coverage_fiber_km": None,
    }

    try:
        # ARPU (Average Revenue Per User)
        kpis["arpu_rp"] = _find_value(
            r"ARPU\s*[:\-=]?\s*(?:Rp\.?\s*)?([\d.,]+)",
            text,
        ) or _find_value(
            r"Average\s+Revenue\s+Per\s+User\s*[:\-=]?\s*(?:Rp\.?\s*)?([\d.,]+)",
            text,
        )

        # Pelanggan (dalam juta)
        kpis["pelanggan_juta"] = _find_value(
            r"(?:Jumlah\s+)?[Pp]elanggan\s*[:\-=]?\s*([\d.,]+)\s*[Jj]uta",
            text,
        ) or _find_value(
            r"(?:Total\s+)?[Ss]ubscribers?\s*[:\-=]?\s*([\d.,]+)\s*(?:million|juta)",
            text,
        )

        # Tenancy Ratio
        kpis["tenancy_ratio"] = _find_value(
            r"[Tt]enancy\s+[Rr]atio\s*[:\-=]?\s*([\d.,]+)\s*x?",
            text,
        ) or _find_value(
            r"[Rr]asio\s+[Pp]enyewaan\s*[:\-=]?\s*([\d.,]+)",
            text,
        )

        # Coverage Fiber (km)
        kpis["coverage_fiber_km"] = _find_value(
            r"(?:Fiber\s+)?[Cc]overage\s*[:\-=]?\s*([\d.,]+)\s*[Kk][Mm]",
            text,
        ) or _find_value(
            r"(?:Jaringan\s+)?[Ff]iber\s+[Oo]ptik?\s*[:\-=]?\s*([\d.,]+)\s*[Kk][Mm]",
            text,
        ) or _find_value(
            r"(?:Panjang\s+)?[Jj]aringan.*?[:\-=]\s*([\d.,]+)\s*[Kk][Mm]",
            text,
        )

    except Exception as exc:
        kpis["_error"] = str(exc)  # type: ignore[assignment]

    return kpis


# ─────────────────────────────────────────────────────────────────────────────
# 4. MINING KPIs
# ─────────────────────────────────────────────────────────────────────────────

def parse_mining_kpis(text: str) -> dict:
    """
    Ekstrak KPI utama sektor Pertambangan dari teks laporan.

    KPI yang diekstrak:
      - volume_produksi_mt : Volume produksi (juta ton / metric ton)
      - volume_penjualan_mt: Volume penjualan (juta ton / metric ton)
      - asp_usd_ton        : Average Selling Price (USD/ton)
      - cash_cost_usd_ton  : Cash cost produksi (USD/ton)
      - strip_ratio        : Stripping ratio (bcm/ton)

    Parameters
    ----------
    text : str
        Teks hasil ekstraksi PDF.

    Returns
    -------
    dict
    """
    kpis: dict[str, Optional[float]] = {
        "volume_produksi_mt": None,
        "volume_penjualan_mt": None,
        "asp_usd_ton": None,
        "cash_cost_usd_ton": None,
        "strip_ratio": None,
    }

    try:
        # Volume Produksi (juta ton / MT)
        kpis["volume_produksi_mt"] = _find_value(
            r"(?:Volume\s+)?[Pp]roduksi\s*[:\-=]?\s*([\d.,]+)\s*(?:[Jj]uta\s+)?(?:[Tt]on|[Mm][Tt])",
            text,
        ) or _find_value(
            r"[Pp]roduction\s+[Vv]olume\s*[:\-=]?\s*([\d.,]+)\s*(?:million\s+)?(?:tonnes?|MT)",
            text,
        )

        # Volume Penjualan (juta ton / MT)
        kpis["volume_penjualan_mt"] = _find_value(
            r"(?:Volume\s+)?[Pp]enjualan\s*[:\-=]?\s*([\d.,]+)\s*(?:[Jj]uta\s+)?(?:[Tt]on|[Mm][Tt])",
            text,
        ) or _find_value(
            r"[Ss]ales\s+[Vv]olume\s*[:\-=]?\s*([\d.,]+)\s*(?:million\s+)?(?:tonnes?|MT)",
            text,
        )

        # ASP — Average Selling Price (USD/ton)
        kpis["asp_usd_ton"] = _find_value(
            r"ASP\s*[:\-=]?\s*(?:USD\s*)?([\d.,]+)\s*(?:/\s*[Tt]on)?",
            text,
        ) or _find_value(
            r"Average\s+Selling\s+Price\s*[:\-=]?\s*(?:USD\s*)?([\d.,]+)",
            text,
        ) or _find_value(
            r"Harga\s+Jual\s+Rata[- ][Rr]ata\s*[:\-=]?\s*(?:USD\s*)?([\d.,]+)",
            text,
        )

        # Cash Cost (USD/ton)
        kpis["cash_cost_usd_ton"] = _find_value(
            r"[Cc]ash\s+[Cc]ost\s*[:\-=]?\s*(?:USD\s*)?([\d.,]+)\s*(?:/\s*[Tt]on)?",
            text,
        ) or _find_value(
            r"[Bb]iaya\s+[Tt]unai\s*(?:per\s+[Tt]on)?\s*[:\-=]?\s*(?:USD\s*)?([\d.,]+)",
            text,
        )

        # Strip Ratio (bcm / ton)
        kpis["strip_ratio"] = _find_value(
            r"[Ss]trip\s+[Rr]atio\s*[:\-=]?\s*([\d.,]+)\s*(?:x|bcm)?",
            text,
        ) or _find_value(
            r"[Ss]tripping\s+[Rr]atio\s*[:\-=]?\s*([\d.,]+)",
            text,
        ) or _find_value(
            r"[Rr]asio\s+[Pp]engupasan\s*[:\-=]?\s*([\d.,]+)",
            text,
        )

    except Exception as exc:
        kpis["_error"] = str(exc)  # type: ignore[assignment]

    return kpis


# ─────────────────────────────────────────────────────────────────────────────
# 5. ENERGY KPIs
# ─────────────────────────────────────────────────────────────────────────────

def parse_energy_kpis(text: str) -> dict:
    """
    Ekstrak KPI utama sektor Energi & Utilitas dari teks laporan.

    KPI yang diekstrak:
      - kapasitas_mw       : Kapasitas terpasang (MW)
      - capacity_factor_pct: Capacity factor / availability factor (%)
      - tarif_usd_kwh      : Tarif listrik/uap (USD/kWh)
      - jumlah_ppa         : Jumlah kontrak PPA aktif

    Parameters
    ----------
    text : str
        Teks hasil ekstraksi PDF.

    Returns
    -------
    dict
    """
    kpis: dict[str, Optional[float]] = {
        "kapasitas_mw": None,
        "capacity_factor_pct": None,
        "tarif_usd_kwh": None,
        "jumlah_ppa": None,
    }

    try:
        # Kapasitas Terpasang (MW atau MWh)
        kpis["kapasitas_mw"] = _find_value(
            r"[Kk]apasitas\s+[Tt]erpasang\s*[:\-=]?\s*([\d.,]+)\s*M[Ww]h?",
            text,
        ) or _find_value(
            r"[Ii]nstalled\s+[Cc]apacity\s*[:\-=]?\s*([\d.,]+)\s*M[Ww]h?",
            text,
        ) or _find_value(
            r"(?:Total\s+)?[Cc]apacity\s*[:\-=]?\s*([\d.,]+)\s*M[Ww]h?",
            text,
        )

        # Capacity Factor / Availability Factor (%)
        kpis["capacity_factor_pct"] = _find_value(
            r"[Cc]apacity\s+[Ff]actor\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"[Aa]vailability\s+[Ff]actor\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"[Ff]aktor\s+[Kk]apasitas\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

        # Tarif (USD/kWh)
        kpis["tarif_usd_kwh"] = _find_value(
            r"[Tt]arif\s*(?:[Ll]istrik|[Uu]ap)?\s*[:\-=]?\s*(?:USD\s*)?([\d.,]+)\s*(?:/\s*kWh)?",
            text,
        ) or _find_value(
            r"[Ee]nergy\s+[Tt]ariff?\s*[:\-=]?\s*(?:USD\s*)?([\d.,]+)\s*(?:/\s*kWh)?",
            text,
        ) or _find_value(
            r"[Ss]team\s+[Tt]ariff?\s*[:\-=]?\s*(?:USD\s*)?([\d.,]+)",
            text,
        )

        # Jumlah PPA (Power Purchase Agreement) aktif
        kpis["jumlah_ppa"] = _find_value(
            r"(\d+)\s+(?:[Kk]ontrak\s+)?PPA\s+[Aa]ktif",
            text,
        ) or _find_value(
            r"PPA\s*[:\-=]?\s*(\d+)\s+(?:[Kk]ontrak)?",
            text,
        ) or _find_value(
            r"(\d+)\s+Power\s+Purchase\s+Agreements?",
            text,
        )

    except Exception as exc:
        kpis["_error"] = str(exc)  # type: ignore[assignment]

    return kpis


# ─────────────────────────────────────────────────────────────────────────────
# 6. MULTIFINANCE KPIs
# ─────────────────────────────────────────────────────────────────────────────

def parse_multifinance_kpis(text: str) -> dict:
    """
    Ekstrak KPI utama sektor Multifinance / Pembiayaan dari teks laporan.

    KPI yang diekstrak:
      - npf_gross_pct           : NPF Gross (%)
      - npf_net_pct             : NPF Net (%)
      - cost_of_funds_pct       : Cost of Funds (%)
      - pertumbuhan_pembiayaan_pct: Pertumbuhan pembiayaan YoY (%)
      - total_pembiayaan_triliun : Total portofolio pembiayaan (Rp triliun)

    Parameters
    ----------
    text : str
        Teks hasil ekstraksi PDF.

    Returns
    -------
    dict
    """
    kpis: dict[str, Optional[float]] = {
        "npf_gross_pct": None,
        "npf_net_pct": None,
        "cost_of_funds_pct": None,
        "pertumbuhan_pembiayaan_pct": None,
        "total_pembiayaan_triliun": None,
    }

    try:
        # NPF Gross
        kpis["npf_gross_pct"] = _find_value(
            r"NPF\s+[Gg]ross\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"[Gg]ross\s+NPF\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

        # NPF Net
        kpis["npf_net_pct"] = _find_value(
            r"NPF\s+[Nn]et\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"[Nn]et\s+NPF\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

        # Cost of Funds
        kpis["cost_of_funds_pct"] = _find_value(
            r"[Cc]ost\s+of\s+[Ff]unds?\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"CoF\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"[Bb]iaya\s+[Dd]ana\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

        # Pertumbuhan Pembiayaan (%)
        kpis["pertumbuhan_pembiayaan_pct"] = _find_value(
            r"[Pp]ertumbuhan\s+[Pp]embiayaan\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        ) or _find_value(
            r"[Ff]inancing\s+[Gg]rowth\s*[:\-=]?\s*([\d.,]+)\s*%?",
            text,
        )

        # Total Pembiayaan (Rp Triliun)
        kpis["total_pembiayaan_triliun"] = _find_value(
            r"[Tt]otal\s+[Pp]embiayaan\s*[:\-=]?\s*(?:Rp\.?\s*)?([\d.,]+)\s*[Tt]riliun",
            text,
        ) or _find_value(
            r"[Tt]otal\s+[Ff]inancing\s*[:\-=]?\s*(?:IDR|Rp\.?\s*)?([\d.,]+)\s*(?:[Tt]riliun|[Tt]rillion)?",
            text,
        )

    except Exception as exc:
        kpis["_error"] = str(exc)  # type: ignore[assignment]

    return kpis


# ─────────────────────────────────────────────────────────────────────────────
# 7. AGRICULTURE KPIs
# ─────────────────────────────────────────────────────────────────────────────

def parse_agriculture_kpis(text: str) -> dict:
    """
    Ekstrak KPI utama sektor Agrikultur / Perkebunan dari teks laporan.

    KPI yang diekstrak:
      - luas_lahan_ha        : Luas lahan tertanam/produktif (Ha)
      - produksi_tbs_ton     : Produksi Tandan Buah Segar/TBS (ton)
      - produksi_cpo_ton     : Produksi Crude Palm Oil/CPO (ton)
      - yield_per_ha         : Yield TBS per hektar (ton/ha)
      - asp_cpo_rp_kg        : Average Selling Price CPO (Rp/kg atau USD/MT)

    Parameters
    ----------
    text : str
        Teks hasil ekstraksi PDF.

    Returns
    -------
    dict
    """
    kpis: dict[str, Optional[float]] = {
        "luas_lahan_ha": None,
        "produksi_tbs_ton": None,
        "produksi_cpo_ton": None,
        "yield_per_ha": None,
        "asp_cpo_rp_kg": None,
    }

    try:
        # Luas Lahan (Ha)
        kpis["luas_lahan_ha"] = _find_value(
            r"[Ll]uas\s+[Ll]ahan\s*[:\-=]?\s*([\d.,]+)\s*[Hh][Aa]",
            text,
        ) or _find_value(
            r"[Pp]lantation\s+[Aa]rea\s*[:\-=]?\s*([\d.,]+)\s*[Hh][Aa]",
            text,
        ) or _find_value(
            r"[Aa]rea\s+(?:[Tt]ertanam|[Pp]roduktif|[Mm]ature)\s*[:\-=]?\s*([\d.,]+)\s*[Hh][Aa]",
            text,
        )

        # Produksi TBS (Tandan Buah Segar, ton)
        kpis["produksi_tbs_ton"] = _find_value(
            r"(?:Produksi\s+)?TBS\s*[:\-=]?\s*([\d.,]+)\s*[Tt]on",
            text,
        ) or _find_value(
            r"FFB\s+(?:Production|Output)\s*[:\-=]?\s*([\d.,]+)\s*(?:[Tt]on|MT)",
            text,
        ) or _find_value(
            r"[Tt]andan\s+[Bb]uah\s+[Ss]egar\s*[:\-=]?\s*([\d.,]+)\s*[Tt]on",
            text,
        )

        # Produksi CPO (Crude Palm Oil, ton)
        kpis["produksi_cpo_ton"] = _find_value(
            r"(?:Produksi\s+)?CPO\s*[:\-=]?\s*([\d.,]+)\s*[Tt]on",
            text,
        ) or _find_value(
            r"CPO\s+(?:Production|Output)\s*[:\-=]?\s*([\d.,]+)\s*(?:[Tt]on|MT)",
            text,
        ) or _find_value(
            r"Crude\s+Palm\s+Oil\s*[:\-=]?\s*([\d.,]+)\s*(?:[Tt]on|MT)",
            text,
        )

        # Yield per Ha (ton TBS / Ha)
        kpis["yield_per_ha"] = _find_value(
            r"[Yy]ield\s*(?:per\s+[Hh][Aa])?\s*[:\-=]?\s*([\d.,]+)\s*(?:[Tt]on/[Hh][Aa])?",
            text,
        ) or _find_value(
            r"[Pp]roduktivitas\s+(?:Lahan|TBS)\s*[:\-=]?\s*([\d.,]+)\s*(?:[Tt]on/[Hh][Aa])?",
            text,
        )

        # ASP CPO (Rp/kg atau USD/MT)
        kpis["asp_cpo_rp_kg"] = _find_value(
            r"ASP\s+CPO\s*[:\-=]?\s*(?:Rp\.?\s*)?([\d.,]+)\s*(?:/\s*[Kk][Gg])?",
            text,
        ) or _find_value(
            r"[Hh]arga\s+(?:Jual\s+)?CPO\s*[:\-=]?\s*(?:Rp\.?\s*)?([\d.,]+)",
            text,
        ) or _find_value(
            r"CPO\s+[Pp]rice\s*[:\-=]?\s*(?:USD|Rp\.?\s*)?([\d.,]+)",
            text,
        )

    except Exception as exc:
        kpis["_error"] = str(exc)  # type: ignore[assignment]

    return kpis


# ─────────────────────────────────────────────────────────────────────────────
# 8. DISPATCHER UTAMA
# ─────────────────────────────────────────────────────────────────────────────

def parse_kpis(emiten: str, text: str) -> dict:
    """
    Dispatcher otomatis: deteksi sektor emiten via ``get_sector()``, lalu
    panggil parser KPI yang sesuai.

    Parameters
    ----------
    emiten : str
        Kode emiten (contoh: 'BBRI', 'TLKM', 'ANTM').
    text : str
        Teks laporan keuangan/keterbukaan informasi hasil ekstraksi PDF.

    Returns
    -------
    dict
        Dictionary KPI sesuai sektor, atau ``{}`` untuk sektor 'General'.
        Selalu menyertakan field ``_sector`` dan ``_emiten`` untuk konteks.

    Examples
    --------
    >>> kpis = parse_kpis("BBRI", raw_text)
    >>> print(kpis.get('nim'))
    """
    sector_raw = get_sector(emiten)
    parser_key = _SECTOR_PARSER_MAP.get(sector_raw, "general")

    parser_dispatch: dict = {
        "banking":      parse_banking_kpis,
        "multifinance": parse_multifinance_kpis,
        "telecom":      parse_telecom_kpis,
        "mining":       parse_mining_kpis,
        "energy":       parse_energy_kpis,
        "agriculture":  parse_agriculture_kpis,
    }

    result: dict = {"_emiten": emiten.upper(), "_sector": sector_raw, "_parser": parser_key}

    parser_fn = parser_dispatch.get(parser_key)
    if parser_fn is not None:
        try:
            kpi_data = parser_fn(text)
            result.update(kpi_data)
        except Exception as exc:
            result["_error"] = f"Error saat parsing sektor '{sector_raw}': {exc}"
    else:
        # Sektor General: kembalikan dict kosong (hanya metadata)
        pass

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 9. FORMAT KPI MARKDOWN
# ─────────────────────────────────────────────────────────────────────────────

# Label human-readable per field KPI
_KPI_LABELS: dict[str, str] = {
    # Banking
    "nim":                          "NIM (%)",
    "npl_gross":                    "NPL Gross (%)",
    "npl_net":                      "NPL Net (%)",
    "car":                          "CAR (%)",
    "casa_ratio":                   "CASA Ratio (%)",
    "ldr_lfr":                      "LDR / LFR (%)",
    # Telecom
    "arpu_rp":                      "ARPU (Rp)",
    "pelanggan_juta":               "Pelanggan (Juta)",
    "tenancy_ratio":                "Tenancy Ratio (x)",
    "coverage_fiber_km":            "Coverage Fiber (km)",
    # Mining
    "volume_produksi_mt":           "Volume Produksi (Ton)",
    "volume_penjualan_mt":          "Volume Penjualan (Ton)",
    "asp_usd_ton":                  "ASP (USD/Ton)",
    "cash_cost_usd_ton":            "Cash Cost (USD/Ton)",
    "strip_ratio":                  "Strip Ratio (bcm/ton)",
    # Energy
    "kapasitas_mw":                 "Kapasitas Terpasang (MW)",
    "capacity_factor_pct":          "Capacity Factor (%)",
    "tarif_usd_kwh":                "Tarif (USD/kWh)",
    "jumlah_ppa":                   "Jumlah PPA Aktif",
    # Multifinance
    "npf_gross_pct":                "NPF Gross (%)",
    "npf_net_pct":                  "NPF Net (%)",
    "cost_of_funds_pct":            "Cost of Funds (%)",
    "pertumbuhan_pembiayaan_pct":   "Pertumbuhan Pembiayaan (%)",
    "total_pembiayaan_triliun":     "Total Pembiayaan (Rp Triliun)",
    # Agriculture
    "luas_lahan_ha":                "Luas Lahan (Ha)",
    "produksi_tbs_ton":             "Produksi TBS (Ton)",
    "produksi_cpo_ton":             "Produksi CPO (Ton)",
    "yield_per_ha":                 "Yield/Ha (Ton)",
    "asp_cpo_rp_kg":                "ASP CPO (Rp/Kg)",
}

_SECTOR_EMOJI: dict[str, str] = {
    "banking":      "💳",
    "multifinance": "💳",
    "telecom":      "📡",
    "mining":       "⛏️",
    "energy":       "⚡",
    "agriculture":  "🌿",
    "general":      "📊",
}


def format_kpi_markdown(emiten: str, sector: str, kpis: dict) -> str:
    """
    Format dictionary KPI menjadi tabel Markdown siap masuk ke laporan
    Financial Summarizer.

    Parameters
    ----------
    emiten : str
        Kode emiten.
    sector : str
        Nama sektor (misalnya 'perbankan', 'pertambangan').
    kpis : dict
        Hasil dari ``parse_kpis()`` atau parser spesifik.

    Returns
    -------
    str
        String Markdown berisi tabel KPI siap pakai dalam laporan.

    Examples
    --------
    >>> md = format_kpi_markdown("BBRI", "perbankan", kpis)
    >>> print(md)
    """
    parser_key = _SECTOR_PARSER_MAP.get(sector.lower(), "general")
    emoji = _SECTOR_EMOJI.get(parser_key, "📊")
    sector_display = sector.title()

    rows: list[str] = []
    for key, value in kpis.items():
        if key.startswith("_"):  # skip metadata fields
            continue
        label = _KPI_LABELS.get(key, key.replace("_", " ").title())
        if value is None:
            display_val = "_Tidak ditemukan_"
        elif isinstance(value, float):
            display_val = f"{value:,.4g}"
        else:
            display_val = str(value)
        rows.append(f"| {label} | {display_val} |")

    if not rows:
        table_content = "_Tidak ada KPI yang berhasil diekstrak._"
    else:
        table_header = "| KPI | Nilai |\n|-----|-------|"
        table_content = table_header + "\n" + "\n".join(rows)

    not_found = [
        _KPI_LABELS.get(k, k)
        for k, v in kpis.items()
        if not k.startswith("_") and v is None
    ]
    not_found_note = ""
    if not_found:
        not_found_str = ", ".join(f"`{n}`" for n in not_found)
        not_found_note = (
            f"\n> ⚠️ **KPI tidak ditemukan dalam teks**: {not_found_str}. "
            "Verifikasi manual diperlukan.\n"
        )

    md = f"""\
### {emoji} KPI Sektor: {sector_display} — {emiten.upper()}

{table_content}
{not_found_note}
"""
    return md


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def _build_cli_parser() -> argparse.ArgumentParser:
    """Buat dan kembalikan CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="sector_kpi_parser",
        description="Ekstrak KPI sektoral dari teks laporan keuangan IDX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python sector_kpi_parser.py --emiten BBRI --file reports/raw/BBRI/laporan.txt
  python sector_kpi_parser.py --emiten TLKM --file reports/raw/TLKM/laporan.txt --output-md
  python sector_kpi_parser.py --emiten ANTM --text "Strip Ratio: 5.2, ASP USD 90/ton"
        """,
    )
    parser.add_argument("--emiten",    required=True,  help="Kode emiten (contoh: BBRI)")
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path ke file teks hasil ekstraksi PDF",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Teks langsung (string) untuk diparse, alternatif dari --file",
    )
    parser.add_argument(
        "--output-md",
        action="store_true",
        dest="output_md",
        help="Cetak output dalam format Markdown",
    )
    parser.add_argument(
        "--sector-override",
        type=str,
        default=None,
        dest="sector_override",
        help="Override sektor manual (contoh: 'perbankan', 'pertambangan')",
    )
    return parser


def main() -> None:
    """Entry point untuk eksekusi CLI."""
    parser = _build_cli_parser()
    args   = parser.parse_args()

    # ── Baca teks input ───────────────────────────────────────────────────────
    text: str = ""
    if args.file:
        try:
            text = Path(args.file).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            print(f"❌ File tidak ditemukan: {args.file}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"❌ Gagal membaca file: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.text:
        text = args.text
    else:
        print("❌ Harus menyediakan --file atau --text.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    # ── Deteksi atau override sektor ──────────────────────────────────────────
    emiten = args.emiten.upper()
    if args.sector_override:
        sector = args.sector_override.lower()
        parser_key = _SECTOR_PARSER_MAP.get(sector, "general")
        parser_dispatch = {
            "banking":      parse_banking_kpis,
            "multifinance": parse_multifinance_kpis,
            "telecom":      parse_telecom_kpis,
            "mining":       parse_mining_kpis,
            "energy":       parse_energy_kpis,
            "agriculture":  parse_agriculture_kpis,
        }
        fn = parser_dispatch.get(parser_key)
        kpis: dict = {"_emiten": emiten, "_sector": sector, "_parser": parser_key}
        if fn:
            kpis.update(fn(text))
    else:
        kpis = parse_kpis(emiten, text)
        sector = kpis.get("_sector", "general")

    # ── Output ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  SECTOR KPI PARSER — {emiten}")
    print(f"  Sektor   : {sector.title()}")
    print(f"  Parser   : {kpis.get('_parser', 'general')}")
    print(f"{'='*60}\n")

    if args.output_md:
        md_output = format_kpi_markdown(emiten, sector, kpis)
        print(md_output)
    else:
        # JSON-like output
        print("{")
        for k, v in kpis.items():
            print(f'  "{k}": {json.dumps(v)},')
        print("}")

    # Hitung coverage
    data_keys = [k for k in kpis if not k.startswith("_")]
    found     = [k for k in data_keys if kpis[k] is not None]
    if data_keys:
        pct = len(found) / len(data_keys) * 100
        print(f"\n📊 Coverage: {len(found)}/{len(data_keys)} KPI ditemukan ({pct:.0f}%)")


if __name__ == "__main__":
    main()