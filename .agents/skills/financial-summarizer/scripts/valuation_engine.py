#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
valuation_engine.py
================================================================================
Mesin Kalkulator Valuasi Saham — Swarm Intelijen Pasar Modal Indonesia (IDX)
--------------------------------------------------------------------------------
Modul ini menyediakan fungsi lengkap untuk menghitung nilai wajar saham
menggunakan metode:
  • 3-Stage Discounted Cash Flow (DCF)
  • Price-to-Earnings (PE) Multiple
  • Price-to-Book Value (PBV) Multiple
  • Blended Fair Value (weighted average)
  • Margin of Safety (MOS) & rating sinyal investasi

Output: Laporan valuasi dalam format Markdown, disimpan ke:
  PRIMARY : g:/My Drive/Model2/Finplan_analyst/knowledge-base/valuations/
  BACKUP  : g:/My Drive/Model2/reports/summaries/valuations/

Standar : Python 3.12, type hints, docstrings, try-except
Penulis  : Swarm Intelijen Pasar Modal — Valuation & Forecasting Agent
Versi    : 1.0.0
Tanggal  : 2026-09-23
================================================================================
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

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
_BASE = Path(r"g:/My Drive/Model2")
_PRIMARY_DIR = _BASE / "Finplan_analyst" / "knowledge-base" / "valuations"
_BACKUP_DIR  = _BASE / "reports" / "summaries" / "valuations"


# ─────────────────────────────────────────────────────────────────────────────
# 1. DISCOUNTED CASH FLOW (3-STAGE DCF)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_dcf(
    fcf_history: list[float],
    growth_rates: dict[str, float],
    wacc: float,
    terminal_growth: float,
    shares_outstanding: int,
) -> dict:
    """
    Hitung nilai intrinsik saham menggunakan metode 3-Stage DCF.

    Parameters
    ----------
    fcf_history : list[float]
        Riwayat Free Cash Flow (FCF) historis dalam miliar Rupiah (minimal 1 nilai).
        Nilai terakhir digunakan sebagai basis FCF awal.
    growth_rates : dict[str, float]
        Tingkat pertumbuhan per stage:
          - 'stage1': pertumbuhan tinggi (contoh: 0.15 = 15%)
          - 'stage2': pertumbuhan transisi (contoh: 0.08 = 8%)
    wacc : float
        Weighted Average Cost of Capital sebagai desimal (contoh: 0.10 = 10%).
    terminal_growth : float
        Tingkat pertumbuhan terminal jangka panjang (contoh: 0.04 = 4%).
    shares_outstanding : int
        Jumlah saham beredar (dalam lembar).

    Returns
    -------
    dict
        {
          'dcf_per_share'   : float  — nilai DCF per saham (Rp),
          'terminal_value'  : float  — nilai terminal (miliar Rp),
          'pv_fcf'          : float  — present value FCF stage 1+2 (miliar Rp),
          'pv_terminal'     : float  — present value terminal value (miliar Rp),
          'total_value'     : float  — total nilai perusahaan (miliar Rp),
          'fcf_projections' : dict   — proyeksi FCF per tahun,
          'error'           : str    — pesan error jika ada, else None,
        }

    Raises
    ------
    ValueError
        Jika WACC <= terminal_growth (tidak dapat menghitung terminal value).

    Examples
    --------
    >>> result = calculate_dcf([10_000, 11_500, 13_000], {'stage1': 0.15, 'stage2': 0.08},
    ...                        wacc=0.10, terminal_growth=0.04, shares_outstanding=15_000_000_000)
    >>> print(result['dcf_per_share'])
    """
    result: dict = {
        "dcf_per_share": 0.0,
        "terminal_value": 0.0,
        "pv_fcf": 0.0,
        "pv_terminal": 0.0,
        "total_value": 0.0,
        "fcf_projections": {},
        "error": None,
    }

    try:
        if not fcf_history:
            raise ValueError("fcf_history tidak boleh kosong.")
        if wacc <= terminal_growth:
            raise ValueError(
                f"WACC ({wacc:.2%}) harus lebih besar dari terminal_growth ({terminal_growth:.2%})."
            )
        if shares_outstanding <= 0:
            raise ValueError("shares_outstanding harus positif.")

        base_fcf: float = float(fcf_history[-1])
        g1: float = growth_rates.get("stage1", 0.12)
        g2: float = growth_rates.get("stage2", 0.07)

        # ── Stage 1: 3 tahun pertumbuhan tinggi ──────────────────────────────
        pv_stage1 = 0.0
        fcf = base_fcf
        projections: dict[str, float] = {}

        for yr in range(1, 4):
            fcf *= (1 + g1)
            pv = fcf / ((1 + wacc) ** yr)
            pv_stage1 += pv
            projections[f"Y{yr}"] = round(fcf, 2)

        # ── Stage 2: 3 tahun transisi ─────────────────────────────────────────
        pv_stage2 = 0.0
        for yr_offset in range(1, 4):
            yr = 3 + yr_offset
            fcf *= (1 + g2)
            pv = fcf / ((1 + wacc) ** yr)
            pv_stage2 += pv
            projections[f"Y{yr}"] = round(fcf, 2)

        # ── Stage 3: Terminal Value (Gordon Growth Model) ─────────────────────
        terminal_value: float = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
        pv_terminal: float = terminal_value / ((1 + wacc) ** 6)

        pv_fcf = pv_stage1 + pv_stage2
        total_value = pv_fcf + pv_terminal

        # ── Per Share ─────────────────────────────────────────────────────────
        # Asumsi: FCF dalam miliar Rp, shares_outstanding dalam lembar
        dcf_per_share = (total_value * 1_000_000_000) / shares_outstanding

        result.update(
            {
                "dcf_per_share": round(dcf_per_share, 2),
                "terminal_value": round(terminal_value, 2),
                "pv_fcf": round(pv_fcf, 2),
                "pv_terminal": round(pv_terminal, 2),
                "total_value": round(total_value, 2),
                "fcf_projections": projections,
            }
        )

    except Exception as exc:
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. PE MULTIPLE VALUATION
# ─────────────────────────────────────────────────────────────────────────────

def calculate_pe_valuation(
    eps: float,
    sector_avg_pe: float,
    historical_pe: Optional[float] = None,
) -> dict:
    """
    Hitung fair value saham berdasarkan Price-to-Earnings (PE) multiple.

    Jika ``historical_pe`` diberikan, fair value dihitung sebagai rata-rata
    dari PE sektor dan PE historis 3 tahun. Jika tidak, hanya PE sektor yang digunakan.

    Parameters
    ----------
    eps : float
        Earnings Per Share (EPS) terkini dalam Rupiah.
    sector_avg_pe : float
        Rata-rata PE sektor (misalnya 12.5).
    historical_pe : float, optional
        PE historis rata-rata 3 tahun emiten.

    Returns
    -------
    dict
        {
          'fair_value_pe'        : float — estimasi harga wajar berdasarkan PE (Rp),
          'benchmark_pe_used'    : float — PE benchmark yang dipakai,
          'premium_discount_pct' : float — premi/diskon vs current EPS (belum harga),
          'sector_avg_pe'        : float,
          'historical_pe'        : float or None,
          'error'                : str or None,
        }
    """
    result: dict = {
        "fair_value_pe": 0.0,
        "benchmark_pe_used": 0.0,
        "premium_discount_pct": 0.0,
        "sector_avg_pe": sector_avg_pe,
        "historical_pe": historical_pe,
        "error": None,
    }

    try:
        if eps <= 0:
            raise ValueError(f"EPS harus positif, diterima: {eps}")
        if sector_avg_pe <= 0:
            raise ValueError(f"sector_avg_pe harus positif, diterima: {sector_avg_pe}")

        if historical_pe is not None and historical_pe > 0:
            benchmark_pe = (sector_avg_pe + historical_pe) / 2
        else:
            benchmark_pe = sector_avg_pe

        fair_value = eps * benchmark_pe

        # premium_discount_pct: seberapa jauh fair_value vs nilai berbasis EPS murni
        # (placeholder relatif — akan bermakna penuh saat dibandingkan harga pasar)
        premium_discount_pct = ((fair_value / eps) - 1) * 100  # ekuivalen PE

        result.update(
            {
                "fair_value_pe": round(fair_value, 2),
                "benchmark_pe_used": round(benchmark_pe, 4),
                "premium_discount_pct": round(premium_discount_pct, 2),
            }
        )

    except Exception as exc:
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 3. PBV MULTIPLE VALUATION
# ─────────────────────────────────────────────────────────────────────────────

def calculate_pbv_valuation(
    book_value_per_share: float,
    sector_avg_pbv: float,
) -> dict:
    """
    Hitung fair value saham berdasarkan Price-to-Book Value (PBV) multiple.

    Parameters
    ----------
    book_value_per_share : float
        Book Value Per Share (BVPS) dalam Rupiah.
    sector_avg_pbv : float
        Rata-rata PBV sektor (misalnya 1.8).

    Returns
    -------
    dict
        {
          'fair_value_pbv'       : float — estimasi harga wajar berdasarkan PBV (Rp),
          'sector_avg_pbv'       : float,
          'premium_discount_pct' : float — premi/diskon implicit,
          'error'                : str or None,
        }
    """
    result: dict = {
        "fair_value_pbv": 0.0,
        "sector_avg_pbv": sector_avg_pbv,
        "premium_discount_pct": 0.0,
        "error": None,
    }

    try:
        if book_value_per_share <= 0:
            raise ValueError(f"book_value_per_share harus positif, diterima: {book_value_per_share}")
        if sector_avg_pbv <= 0:
            raise ValueError(f"sector_avg_pbv harus positif, diterima: {sector_avg_pbv}")

        fair_value = book_value_per_share * sector_avg_pbv
        premium_discount_pct = (sector_avg_pbv - 1) * 100  # berapa % di atas book value

        result.update(
            {
                "fair_value_pbv": round(fair_value, 2),
                "premium_discount_pct": round(premium_discount_pct, 2),
            }
        )

    except Exception as exc:
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. BLENDED FAIR VALUE
# ─────────────────────────────────────────────────────────────────────────────

def calculate_blended_fair_value(
    dcf_value: float,
    pe_value: float,
    pbv_value: float,
    weights: Optional[dict[str, float]] = None,
) -> dict:
    """
    Hitung harga wajar campuran (blended) dari tiga metode valuasi.

    Parameters
    ----------
    dcf_value : float
        Hasil DCF per share (Rp).
    pe_value : float
        Hasil PE fair value (Rp).
    pbv_value : float
        Hasil PBV fair value (Rp).
    weights : dict, optional
        Bobot per metode. Default: {'dcf': 0.50, 'pe': 0.30, 'pbv': 0.20}.
        Total bobot HARUS = 1.0.

    Returns
    -------
    dict
        {
          'blended_fair_value' : float — harga wajar campuran (Rp),
          'weights_used'       : dict  — bobot yang digunakan,
          'components'         : dict  — kontribusi masing-masing metode,
          'error'              : str or None,
        }
    """
    DEFAULT_WEIGHTS: dict[str, float] = {"dcf": 0.50, "pe": 0.30, "pbv": 0.20}
    result: dict = {
        "blended_fair_value": 0.0,
        "weights_used": {},
        "components": {},
        "error": None,
    }

    try:
        w = weights if weights is not None else DEFAULT_WEIGHTS
        total_w = sum(w.values())
        if not math.isclose(total_w, 1.0, rel_tol=1e-6):
            raise ValueError(
                f"Total bobot harus 1.0, diterima: {total_w:.4f}. "
                "Sesuaikan nilai 'weights'."
            )

        w_dcf = w.get("dcf", 0.0)
        w_pe  = w.get("pe",  0.0)
        w_pbv = w.get("pbv", 0.0)

        contrib_dcf = dcf_value * w_dcf
        contrib_pe  = pe_value  * w_pe
        contrib_pbv = pbv_value * w_pbv
        blended     = contrib_dcf + contrib_pe + contrib_pbv

        result.update(
            {
                "blended_fair_value": round(blended, 2),
                "weights_used": w,
                "components": {
                    "dcf": {"value": round(dcf_value, 2), "weight": w_dcf, "contribution": round(contrib_dcf, 2)},
                    "pe":  {"value": round(pe_value,  2), "weight": w_pe,  "contribution": round(contrib_pe,  2)},
                    "pbv": {"value": round(pbv_value, 2), "weight": w_pbv, "contribution": round(contrib_pbv, 2)},
                },
            }
        )

    except Exception as exc:
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 5. MARGIN OF SAFETY & SIGNAL
# ─────────────────────────────────────────────────────────────────────────────

def calculate_margin_of_safety(
    current_price: float,
    fair_value: float,
) -> dict:
    """
    Hitung Margin of Safety (MOS) dan sinyal rekomendasi investasi.

    Rumus MOS = (Fair Value - Current Price) / Fair Value × 100

    Sinyal:
      🟢 UNDERVALUED   → MOS > 20%
      ⚪ FAIRLY VALUED  → MOS antara -10% s.d. +20%
      🔴 OVERVALUED    → MOS < -10%

    Parameters
    ----------
    current_price : float
        Harga pasar saham saat ini (Rp).
    fair_value : float
        Harga wajar (fair value) hasil valuasi (Rp).

    Returns
    -------
    dict
        {
          'mos_pct'        : float — persentase Margin of Safety,
          'upside_pct'     : float — potensi kenaikan/penurunan dari harga saat ini,
          'signal'         : str   — '🟢 UNDERVALUED' | '⚪ FAIRLY VALUED' | '🔴 OVERVALUED',
          'current_price'  : float,
          'fair_value'     : float,
          'error'          : str or None,
        }
    """
    result: dict = {
        "mos_pct": 0.0,
        "upside_pct": 0.0,
        "signal": "⚪ FAIRLY VALUED",
        "current_price": current_price,
        "fair_value": fair_value,
        "error": None,
    }

    try:
        if current_price <= 0:
            raise ValueError(f"current_price harus positif, diterima: {current_price}")
        if fair_value <= 0:
            raise ValueError(f"fair_value harus positif, diterima: {fair_value}")

        mos_pct    = (fair_value - current_price) / fair_value * 100
        upside_pct = (fair_value - current_price) / current_price * 100

        if mos_pct > 20:
            signal = "🟢 UNDERVALUED"
        elif mos_pct < -10:
            signal = "🔴 OVERVALUED"
        else:
            signal = "⚪ FAIRLY VALUED"

        result.update(
            {
                "mos_pct": round(mos_pct, 2),
                "upside_pct": round(upside_pct, 2),
                "signal": signal,
            }
        )

    except Exception as exc:
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 6. GENERATE VALUATION REPORT
# ─────────────────────────────────────────────────────────────────────────────

def generate_valuation_report(
    emiten: str,
    current_price: float,
    eps: float,
    book_value_per_share: float,
    sector_avg_pe: float,
    sector_avg_pbv: float,
    fcf_history: Optional[list[float]] = None,
    growth_rates: Optional[dict[str, float]] = None,
    wacc: float = 0.10,
    terminal_growth: float = 0.04,
    shares_outstanding: int = 10_000_000_000,
    historical_pe: Optional[float] = None,
    weights: Optional[dict[str, float]] = None,
    analyst_notes: str = "",
) -> str:
    """
    Jalankan pipeline valuasi lengkap dan generate laporan Markdown.

    Laporan disimpan ke dua lokasi:
      PRIMARY : g:/My Drive/Model2/Finplan_analyst/knowledge-base/valuations/
      BACKUP  : g:/My Drive/Model2/reports/summaries/valuations/

    Parameters
    ----------
    emiten : str
        Kode emiten (contoh: 'BBRI').
    current_price : float
        Harga pasar saat ini (Rp).
    eps : float
        Earnings Per Share terkini (Rp).
    book_value_per_share : float
        Book Value Per Share (Rp).
    sector_avg_pe : float
        Rata-rata PE sektor.
    sector_avg_pbv : float
        Rata-rata PBV sektor.
    fcf_history : list[float], optional
        Riwayat FCF (miliar Rp). Jika None, DCF dilewati.
    growth_rates : dict, optional
        {'stage1': float, 'stage2': float}. Default: {'stage1': 0.12, 'stage2': 0.07}.
    wacc : float
        WACC. Default 0.10.
    terminal_growth : float
        Terminal growth rate. Default 0.04.
    shares_outstanding : int
        Jumlah saham beredar. Default 10 miliar.
    historical_pe : float, optional
        PE historis 3 tahun emiten.
    weights : dict, optional
        Bobot blended valuation.
    analyst_notes : str
        Catatan analis tambahan untuk dimasukkan ke laporan.

    Returns
    -------
    str
        Path file laporan yang berhasil disimpan (primary path), atau
        string error jika gagal.
    """
    tanggal_str = datetime.now().strftime("%Y%m%d")
    emiten_upper = emiten.upper()
    filename = f"{emiten_upper}_Valuation_{tanggal_str}.md"

    # ── Jalankan kalkulasi ────────────────────────────────────────────────────
    _growth = growth_rates or {"stage1": 0.12, "stage2": 0.07}

    dcf_result: dict = {}
    dcf_value: float = 0.0
    dcf_section = "_DCF tidak dihitung (fcf_history tidak tersedia)._"

    if fcf_history:
        dcf_result = calculate_dcf(
            fcf_history, _growth, wacc, terminal_growth, shares_outstanding
        )
        if dcf_result.get("error"):
            dcf_section = f"⚠️ Error DCF: {dcf_result['error']}"
        else:
            dcf_value = dcf_result["dcf_per_share"]
            proj_rows = "\n".join(
                f"| {yr} | {val:,.2f} |"
                for yr, val in dcf_result["fcf_projections"].items()
            )
            dcf_section = f"""\
| Parameter | Nilai |
|-----------|-------|
| WACC | {wacc:.2%} |
| Terminal Growth | {terminal_growth:.2%} |
| Stage 1 Growth | {_growth.get('stage1', 0):.2%} |
| Stage 2 Growth | {_growth.get('stage2', 0):.2%} |
| PV FCF (Stage 1+2) | Rp {dcf_result['pv_fcf']:,.2f} M |
| PV Terminal Value | Rp {dcf_result['pv_terminal']:,.2f} M |
| **DCF per Share** | **Rp {dcf_value:,.2f}** |

**Proyeksi FCF (Miliar Rp):**

| Tahun | FCF Proyeksi |
|-------|-------------|
{proj_rows}"""

    pe_result  = calculate_pe_valuation(eps, sector_avg_pe, historical_pe)
    pbv_result = calculate_pbv_valuation(book_value_per_share, sector_avg_pbv)

    pe_value  = pe_result.get("fair_value_pe", 0.0)
    pbv_value = pbv_result.get("fair_value_pbv", 0.0)

    # Jika DCF gagal atau tidak ada, gunakan rata-rata PE & PBV untuk blended
    if dcf_value == 0.0:
        _weights = weights or {"dcf": 0.0, "pe": 0.60, "pbv": 0.40}
    else:
        _weights = weights or {"dcf": 0.50, "pe": 0.30, "pbv": 0.20}

    blended_result = calculate_blended_fair_value(
        dcf_value or pe_value,  # fallback agar tidak nol
        pe_value,
        pbv_value,
        _weights,
    )
    fair_value = blended_result.get("blended_fair_value", pe_value)

    mos_result = calculate_margin_of_safety(current_price, fair_value)

    # ── Bangun Markdown ───────────────────────────────────────────────────────
    now_fmt = datetime.now().strftime("%d %B %Y %H:%M WIB")
    signal  = mos_result.get("signal", "⚪ FAIRLY VALUED")

    pe_err  = f"\n> ⚠️ Error PE: {pe_result['error']}"  if pe_result.get("error")  else ""
    pbv_err = f"\n> ⚠️ Error PBV: {pbv_result['error']}" if pbv_result.get("error") else ""

    components = blended_result.get("components", {})
    comp_rows = "\n".join(
        f"| {m.upper()} | {v['weight']:.0%} | Rp {v['value']:,.2f} | Rp {v['contribution']:,.2f} |"
        for m, v in components.items()
    )

    report_md = f"""# 📊 Laporan Valuasi: {emiten_upper}

> **Tanggal Analisis**: {now_fmt}
> **Analis**: Valuation & Forecasting Agent — Swarm Intelijen Pasar Modal IDX
> **Status**: {signal}

---

## 1. Ringkasan Valuasi

| Metrik | Nilai |
|--------|-------|
| **Harga Pasar (Current Price)** | Rp {current_price:,.0f} |
| **Fair Value (Blended)** | **Rp {fair_value:,.2f}** |
| **Margin of Safety (MOS)** | **{mos_result.get('mos_pct', 0):.2f}%** |
| **Potensi Upside/Downside** | {mos_result.get('upside_pct', 0):+.2f}% |
| **Signal Investasi** | {signal} |

---

## 2. Data Input Fundamental

| Parameter | Nilai |
|-----------|-------|
| EPS (Earnings Per Share) | Rp {eps:,.2f} |
| Book Value Per Share (BVPS) | Rp {book_value_per_share:,.2f} |
| Sektor Avg PE | {sector_avg_pe:.2f}x |
| Sektor Avg PBV | {sector_avg_pbv:.2f}x |
| Historical PE (3 Tahun) | {f"{historical_pe:.2f}x" if historical_pe else "N/A"} |

---

## 3. DCF Valuation (3-Stage)

{dcf_section}

---

## 4. PE Multiple Valuation{pe_err}

| Parameter | Nilai |
|-----------|-------|
| EPS | Rp {eps:,.2f} |
| Benchmark PE | {pe_result.get('benchmark_pe_used', sector_avg_pe):.2f}x |
| **Fair Value (PE)** | **Rp {pe_value:,.2f}** |

---

## 5. PBV Multiple Valuation{pbv_err}

| Parameter | Nilai |
|-----------|-------|
| Book Value Per Share | Rp {book_value_per_share:,.2f} |
| Sektor PBV | {sector_avg_pbv:.2f}x |
| **Fair Value (PBV)** | **Rp {pbv_value:,.2f}** |

---

## 6. Blended Fair Value

| Metode | Bobot | Fair Value | Kontribusi |
|--------|-------|-----------|-----------|
{comp_rows}
| **TOTAL** | **100%** | — | **Rp {fair_value:,.2f}** |

---

## 7. Margin of Safety & Rating

| Parameter | Nilai |
|-----------|-------|
| Harga Pasar | Rp {current_price:,.0f} |
| Fair Value (Blended) | Rp {fair_value:,.2f} |
| MOS | {mos_result.get('mos_pct', 0):.2f}% |
| **Rating** | **{signal}** |

> **Keterangan Sinyal:**
> - 🟢 UNDERVALUED  : MOS > 20% (saham diperdagangkan jauh di bawah nilai wajar)
> - ⚪ FAIRLY VALUED : MOS -10% s.d. +20% (harga mendekati nilai wajar)
> - 🔴 OVERVALUED   : MOS < -10% (saham diperdagangkan di atas nilai wajar)

---

## 8. Catatan Analis

{analyst_notes if analyst_notes else "_Tidak ada catatan tambahan._"}

---

*Laporan ini dibuat secara otomatis oleh Valuation & Forecasting Agent.*
*Bukan merupakan rekomendasi investasi. Selalu lakukan riset mandiri (DYOR).*
"""

    # ── Simpan ke file ────────────────────────────────────────────────────────
    saved_paths: list[str] = []
    errors: list[str] = []

    for target_dir in [_PRIMARY_DIR, _BACKUP_DIR]:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            filepath = target_dir / filename
            filepath.write_text(report_md, encoding="utf-8")
            saved_paths.append(str(filepath))
        except Exception as exc:
            errors.append(f"Gagal simpan ke '{target_dir}': {exc}")

    if saved_paths:
        print(f"✅ Laporan disimpan ke:")
        for p in saved_paths:
            print(f"   • {p}")
        return saved_paths[0]  # return primary path
    else:
        err_msg = "❌ Gagal menyimpan laporan:\n" + "\n".join(errors)
        print(err_msg, file=sys.stderr)
        return err_msg


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def _build_cli_parser() -> argparse.ArgumentParser:
    """Buat dan kembalikan CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="valuation_engine",
        description="Mesin Valuasi Saham IDX — 3-Stage DCF + PE + PBV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python valuation_engine.py --emiten BBRI --price 4500 --eps 450 --bvps 2200 \\
      --sector-pe 10.5 --sector-pbv 1.8

  python valuation_engine.py --emiten TLKM --price 3200 --eps 280 --bvps 1500 \\
      --sector-pe 14.0 --sector-pbv 2.2 --historical-pe 13.5 --wacc 0.09 \\
      --fcf 8000 10000 12000 --shares 100000000000
        """,
    )
    parser.add_argument("--emiten",       required=True,  help="Kode emiten (contoh: BBRI)")
    parser.add_argument("--price",        required=True,  type=float, help="Harga pasar saat ini (Rp)")
    parser.add_argument("--eps",          required=True,  type=float, help="Earnings Per Share (Rp)")
    parser.add_argument("--bvps",         required=True,  type=float, help="Book Value Per Share (Rp)")
    parser.add_argument("--sector-pe",    required=True,  type=float, dest="sector_pe",  help="Rata-rata PE sektor")
    parser.add_argument("--sector-pbv",   required=True,  type=float, dest="sector_pbv", help="Rata-rata PBV sektor")
    parser.add_argument("--historical-pe",type=float, default=None, dest="historical_pe", help="PE historis 3 tahun (opsional)")
    parser.add_argument("--wacc",         type=float, default=0.10,  help="WACC (desimal, default: 0.10)")
    parser.add_argument("--terminal-growth", type=float, default=0.04, dest="terminal_growth", help="Terminal growth rate (default: 0.04)")
    parser.add_argument("--shares",       type=int,   default=10_000_000_000, help="Jumlah saham beredar (default: 10 miliar)")
    parser.add_argument("--fcf",          type=float, nargs="+", default=None, help="Riwayat FCF (miliar Rp), contoh: --fcf 8000 10000 12000")
    parser.add_argument("--stage1-growth",type=float, default=0.12, dest="stage1", help="Stage 1 growth rate (default: 0.12)")
    parser.add_argument("--stage2-growth",type=float, default=0.07, dest="stage2", help="Stage 2 growth rate (default: 0.07)")
    parser.add_argument("--notes",        type=str,   default="", help="Catatan analis tambahan")
    return parser


def main() -> None:
    """Entry point untuk eksekusi CLI."""
    parser = _build_cli_parser()
    args   = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  VALUATION ENGINE — {args.emiten.upper()}")
    print(f"{'='*60}\n")

    output_path = generate_valuation_report(
        emiten=args.emiten,
        current_price=args.price,
        eps=args.eps,
        book_value_per_share=args.bvps,
        sector_avg_pe=args.sector_pe,
        sector_avg_pbv=args.sector_pbv,
        fcf_history=args.fcf,
        growth_rates={"stage1": args.stage1, "stage2": args.stage2},
        wacc=args.wacc,
        terminal_growth=args.terminal_growth,
        shares_outstanding=args.shares,
        historical_pe=args.historical_pe,
        analyst_notes=args.notes,
    )

    print(f"\n📄 Output: {output_path}\n")


if __name__ == "__main__":
    main()
