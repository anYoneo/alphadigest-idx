# Public Expose Builder — Swarm Intelijen Pasar Modal Indonesia
# =============================================================================
# Modul pemroses berkas Public Expose dari Bursa Efek Indonesia (BEI).
# Bagian dari pipeline Swarm Intelijen Pasar Modal Indonesia.
#
# Author  : Financial Summarizer Agent
# Version : 2.0.0
# Updated : 2026-09-23
# =============================================================================

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Pastikan output konsol Windows mendukung UTF-8 (mencegah UnicodeEncodeError)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Graceful imports — PyMuPDF (fitz) preferred, pypdf as fallback
# ---------------------------------------------------------------------------
try:
    import fitz  # PyMuPDF

    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

try:
    from pypdf import PdfReader  # type: ignore

    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("public_expose_builder")

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
PRIMARY_BASE = Path(r"g:\My Drive\Model2\Finplan_analyst\knowledge-base\public-exposes")
BACKUP_BASE = Path(r"g:\My Drive\Model2\reports\summaries\public-exposes")

# ---------------------------------------------------------------------------
# BEI boilerplate noise patterns
# ---------------------------------------------------------------------------
_NOISE_PATTERNS: list[str] = [
    r"Go To English Page",
    r"Nomor Surat\s*:.*",
    r"Sender Name\s*:.*",
    r"Dokumen ini merupakan dokumen resmi[^\n]*",
    r"Hormat Kami[^\n]*",
    r"https?://\S+",
    r"www\.\S+",
    r"\(021\)[\s\d\-]+",          # Jakarta phone numbers
    r"\b021[\s\-]?\d{4,8}\b",
    r"Fax\s*[:\.]?\s*[\d\s\-\(\)]+",
    r"Faksimili\s*[:\.]?\s*[\d\s\-\(\)]+",
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",  # email
    r"\b\d{5}\b(?!\s*\w)",        # kode pos (5-digit standalone)
    r"PT Kustodian Sentral Efek Indonesia[^\n]*",
    r"Bursa Efek Indonesia[^\n]*(?:menyampaikan|meneruskan)[^\n]*",
    r"(?:Kepada|Perihal|Lampiran)\s*:[^\n]*",
    r"[-_=]{5,}",                 # garis pemisah berulang
]

_COMPILED_NOISE = [re.compile(p, re.IGNORECASE) for p in _NOISE_PATTERNS]


# =============================================================================
# 1. extract_text_from_pdf
# =============================================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    """Ekstrak teks dari berkas PDF menggunakan PyMuPDF, pypdf, atau plaintext.

    Urutan prioritas:
    1. PyMuPDF (fitz) — mempertahankan struktur blok halaman.
    2. pypdf         — fallback jika fitz tidak tersedia.
    3. Baca sebagai teks biasa — untuk berkas non-PDF.

    Parameters
    ----------
    pdf_path : str
        Path absolut atau relatif ke berkas PDF.

    Returns
    -------
    str
        Teks mentah yang diekstrak dari dokumen.

    Raises
    ------
    ValueError
        Jika berkas tidak dapat dibaca dengan metode apa pun.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise ValueError(f"Berkas tidak ditemukan: {pdf_path}")

    # ── PyMuPDF ──────────────────────────────────────────────────────────────
    if _FITZ_AVAILABLE:
        try:
            doc = fitz.open(str(path))  # type: ignore[attr-defined]
            pages: list[str] = []
            for page in doc:
                blocks = page.get_text("blocks")  # type: ignore[attr-defined]
                block_texts = [b[4] for b in blocks if len(b) > 4 and isinstance(b[4], str)]
                pages.append("\n".join(block_texts))
            doc.close()
            full_text = "\n\n".join(pages)
            if full_text.strip():
                logger.info("Ekstraksi berhasil via PyMuPDF: %s (%d halaman)", path.name, len(pages))
                return full_text
            logger.warning("PyMuPDF menghasilkan teks kosong, mencoba fallback.")
        except Exception as exc:
            logger.warning("PyMuPDF gagal (%s), mencoba fallback pypdf.", exc)

    # ── pypdf ─────────────────────────────────────────────────────────────────
    if _PYPDF_AVAILABLE:
        try:
            reader = PdfReader(str(path))
            pages_text: list[str] = []
            for pg in reader.pages:
                extracted = pg.extract_text() or ""
                pages_text.append(extracted)
            full_text = "\n\n".join(pages_text)
            if full_text.strip():
                logger.info("Ekstraksi berhasil via pypdf: %s (%d halaman)", path.name, len(pages_text))
                return full_text
            logger.warning("pypdf menghasilkan teks kosong, mencoba baca plaintext.")
        except Exception as exc:
            logger.warning("pypdf gagal (%s), mencoba baca plaintext.", exc)

    # ── Plaintext fallback ────────────────────────────────────────────────────
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            logger.info("Berkas dibaca sebagai plaintext: %s", path.name)
            return text
    except Exception as exc:
        logger.error("Gagal membaca berkas sebagai plaintext: %s", exc)

    raise ValueError(
        f"Tidak dapat mengekstrak teks dari berkas: {pdf_path}. "
        "Pastikan PyMuPDF atau pypdf terinstal untuk berkas PDF."
    )


# =============================================================================
# 2. detect_public_expose_type
# =============================================================================

def detect_public_expose_type(text: str) -> str:
    """Deteksi jenis dokumen Public Expose dari konten teks.

    Parameters
    ----------
    text : str
        Teks mentah dari dokumen.

    Returns
    -------
    str
        Salah satu dari: ``'hasil_qa'``, ``'materi_presentasi'``,
        ``'undangan'``, atau ``'unknown'``.
    """
    if not text or not text.strip():
        return "unknown"

    sample = text[:8000].lower()

    # ── Ciri dokumen hasil Q&A ────────────────────────────────────────────────
    qa_signals = [
        r"\bpenanya\b",
        r"\bpertanyaan\b.*\bjawaban\b",
        r"\bjawaban manajemen\b",
        r"\bsesi tanya jawab\b",
        r"\bhasil public expose\b",
        r"(?:^|\n)\s*[A-D]\.\s+",   # pola lettered A. B. C. D.
        r"(?:^|\n)\s*\d+\.\s+pertanyaan",
    ]
    qa_score = sum(1 for p in qa_signals if re.search(p, sample, re.IGNORECASE | re.MULTILINE))

    # ── Ciri materi presentasi ────────────────────────────────────────────────
    pres_signals = [
        r"\bprofil perusahaan\b",
        r"\bpresentasi\b",
        r"\bagenda\b",
        r"\bslide\b",
        r"\bhighlights?\b",
        r"\bkinerja\b.*\b(?:1h|semester|ytd)\b",
        r"\bstrategi bisnis\b",
        r"\bguidance\b",
        r"\boutlook\b",
    ]
    pres_score = sum(1 for p in pres_signals if re.search(p, sample, re.IGNORECASE))

    # ── Ciri undangan ─────────────────────────────────────────────────────────
    inv_signals = [
        r"\bundangan\b",
        r"\bdengan hormat\b",
        r"\bmengundang\b",
        r"\bpelaksanaan public expose\b",
        r"\bhari/tanggal\b",
        r"\bwaktu\s*:",
        r"\btempat\s*:",
    ]
    inv_score = sum(1 for p in inv_signals if re.search(p, sample, re.IGNORECASE))

    scores = {
        "hasil_qa": qa_score,
        "materi_presentasi": pres_score,
        "undangan": inv_score,
    }
    best_type = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    if best_score == 0:
        logger.warning("Tidak dapat mendeteksi tipe dokumen — dikembalikan 'unknown'.")
        return "unknown"

    logger.info("Tipe dokumen terdeteksi: '%s' (skor=%d)", best_type, best_score)
    return best_type


# =============================================================================
# 3. strip_bei_noise
# =============================================================================

def strip_bei_noise(text: str) -> str:
    """Buang teks boilerplate dan noise khas BEI dari konten dokumen.

    Parameters
    ----------
    text : str
        Teks mentah dari dokumen BEI.

    Returns
    -------
    str
        Teks yang sudah dibersihkan dari noise.
    """
    if not text:
        return ""

    cleaned = text
    for pattern in _COMPILED_NOISE:
        try:
            cleaned = pattern.sub(" ", cleaned)
        except Exception as exc:
            logger.debug("Pattern noise gagal diaplikasikan: %s", exc)

    # Bersihkan spasi berlebih dan baris kosong ganda
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    original_len = len(text)
    cleaned_len = len(cleaned)
    reduction_pct = (1 - cleaned_len / original_len) * 100 if original_len > 0 else 0
    logger.info(
        "Noise stripping selesai: %d → %d karakter (-%d%%)",
        original_len, cleaned_len, int(reduction_pct),
    )

    return cleaned


# =============================================================================
# 4. parse_qa_pairs
# =============================================================================

def parse_qa_pairs(text: str) -> list[dict[str, Any]]:
    """Ekstrak pasangan tanya-jawab dari teks hasil Public Expose.

    Mendukung tiga format:
    - **Numbered**: ``1. Pertanyaan: ... Jawaban: ...``
    - **Lettered**: ``A. [pertanyaan]  B. [nama]  C. [jabatan]  D. [jawaban]``
    - **Labeled**: ``Penanya: ... Pertanyaan: ... Jawaban Manajemen: ...``

    Parameters
    ----------
    text : str
        Teks yang sudah dibersihkan dari noise.

    Returns
    -------
    list[dict]
        Daftar dict dengan kunci ``nomor``, ``penanya``, ``pertanyaan``, ``jawaban``.
    """
    results: list[dict[str, Any]] = []

    if not text or not text.strip():
        return results

    # ── Format 1: Label Penanya / Pertanyaan / Jawaban ────────────────────────
    label_pattern = re.compile(
        r"(?:Penanya|Nama)\s*:\s*(?P<penanya>[^\n]+)\n"
        r"(?:Pertanyaan|Topik)\s*:\s*(?P<pertanyaan>.*?)\n"
        r"(?:Jawaban(?:\s+Manajemen)?|Tanggapan)\s*:\s*(?P<jawaban>.*?)"
        r"(?=(?:Penanya|Nama)\s*:|$)",
        re.DOTALL | re.IGNORECASE,
    )
    label_matches = list(label_pattern.finditer(text))
    if label_matches:
        for i, m in enumerate(label_matches, start=1):
            results.append({
                "nomor": i,
                "penanya": m.group("penanya").strip(),
                "pertanyaan": m.group("pertanyaan").strip(),
                "jawaban": m.group("jawaban").strip(),
            })
        logger.info("Format label: %d pasang Q&A diekstrak.", len(results))
        return results

    # ── Format 2: Lettered A/B/C/D ───────────────────────────────────────────
    lettered_pattern = re.compile(
        r"A\.\s*(?P<pertanyaan>.*?)"
        r"B\.\s*(?P<penanya>.*?)"
        r"(?:C\.\s*(?P<jabatan>.*?))?"
        r"D\.\s*(?P<jawaban>.*?)"
        r"(?=A\.|$)",
        re.DOTALL | re.IGNORECASE,
    )
    lettered_matches = list(lettered_pattern.finditer(text))
    if lettered_matches:
        for i, m in enumerate(lettered_matches, start=1):
            penanya = m.group("penanya") or ""
            jabatan = m.group("jabatan") or ""
            penanya_full = (
                f"{penanya.strip()} — {jabatan.strip()}" if jabatan.strip() else penanya.strip()
            )
            results.append({
                "nomor": i,
                "penanya": penanya_full,
                "pertanyaan": m.group("pertanyaan").strip(),
                "jawaban": m.group("jawaban").strip(),
            })
        logger.info("Format lettered A-D: %d pasang Q&A diekstrak.", len(results))
        return results

    # ── Format 3: Numbered 1. Pertanyaan: ... Jawaban: ... ───────────────────
    numbered_pattern = re.compile(
        r"(?:^|\n)\s*(\d+)\.\s+"
        r"(?:Pertanyaan\s*:)?\s*(?P<pertanyaan>.*?)"
        r"(?:Jawaban(?:\s+Manajemen)?\s*:|Tanggapan\s*:)\s*(?P<jawaban>.*?)"
        r"(?=(?:\n\s*\d+\.)|$)",
        re.DOTALL | re.IGNORECASE,
    )
    numbered_matches = list(numbered_pattern.finditer(text))
    if numbered_matches:
        for m in numbered_matches:
            nomor = int(m.group(1))
            results.append({
                "nomor": nomor,
                "penanya": "",
                "pertanyaan": m.group("pertanyaan").strip(),
                "jawaban": m.group("jawaban").strip(),
            })
        logger.info("Format numbered: %d pasang Q&A diekstrak.", len(results))
        return results

    logger.warning("Tidak ada format Q&A yang cocok ditemukan dalam teks.")
    return results


# =============================================================================
# 5. parse_presentation_material
# =============================================================================

def parse_presentation_material(text: str) -> dict[str, Any]:
    """Ekstrak komponen materi presentasi Public Expose.

    Parameters
    ----------
    text : str
        Teks yang sudah dibersihkan dari noise.

    Returns
    -------
    dict
        Kunci: ``jadwal``, ``lokasi``, ``agenda``, ``profil_perusahaan``,
        ``kinerja_1h``, ``target_tahun_depan``, ``strategi_bisnis``.
        Nilai kosong dikembalikan sebagai string kosong atau list kosong.
    """
    result: dict[str, Any] = {
        "jadwal": "",
        "lokasi": "",
        "agenda": [],
        "profil_perusahaan": "",
        "kinerja_1h": "",
        "target_tahun_depan": "",
        "strategi_bisnis": [],
    }

    if not text or not text.strip():
        return result

    # ── Jadwal ────────────────────────────────────────────────────────────────
    jadwal_match = re.search(
        r"(?:hari[/,]?\s*tanggal|tanggal pelaksanaan|waktu\s*&\s*tanggal)[^\n]*\n?([^\n]+)",
        text, re.IGNORECASE,
    )
    if jadwal_match:
        result["jadwal"] = jadwal_match.group(1).strip()
    else:
        date_match = re.search(
            r"\b(?:Senin|Selasa|Rabu|Kamis|Jumat|Sabtu|Minggu)[,\s]+\d{1,2}\s+"
            r"(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)"
            r"\s+\d{4}\b",
            text, re.IGNORECASE,
        )
        if date_match:
            result["jadwal"] = date_match.group(0).strip()

    # ── Lokasi ────────────────────────────────────────────────────────────────
    lokasi_match = re.search(
        r"(?:tempat|lokasi|venue|gedung)\s*[:\-]\s*([^\n]+)",
        text, re.IGNORECASE,
    )
    if lokasi_match:
        result["lokasi"] = lokasi_match.group(1).strip()

    # ── Agenda ────────────────────────────────────────────────────────────────
    agenda_block = re.search(
        r"(?:agenda|susunan acara)[^\n]*\n(.*?)(?:\n{2,}|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if agenda_block:
        raw_agenda = agenda_block.group(1)
        agenda_items = re.findall(r"(?:^\s*[\d\-\•\*]+\.?\s*)(.+)", raw_agenda, re.MULTILINE)
        result["agenda"] = [a.strip() for a in agenda_items if a.strip()]

    # ── Profil Perusahaan ─────────────────────────────────────────────────────
    profil_match = re.search(
        r"(?:profil perusahaan|company profile|tentang\s+kami|about us)[^\n]*\n(.*?)(?:\n{2,}|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if profil_match:
        result["profil_perusahaan"] = profil_match.group(1).strip()[:1000]

    # ── Kinerja 1H / YTD ─────────────────────────────────────────────────────
    kinerja_match = re.search(
        r"(?:kinerja|financial highlights?|laporan keuangan)\s*"
        r"(?:1h|semester\s*[i1]|ytd|semester\s*pertama)[^\n]*\n(.*?)(?:\n{2,}|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if kinerja_match:
        result["kinerja_1h"] = kinerja_match.group(1).strip()[:1500]

    # ── Target / Guidance ─────────────────────────────────────────────────────
    target_match = re.search(
        r"(?:target|guidance|outlook|proyeksi|rencana ke depan)[^\n]*\n(.*?)(?:\n{2,}|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if target_match:
        result["target_tahun_depan"] = target_match.group(1).strip()[:1000]

    # ── Strategi Bisnis ───────────────────────────────────────────────────────
    strategi_block = re.search(
        r"(?:strategi bisnis|strategic initiatives?|inisiatif strategis)[^\n]*\n(.*?)(?:\n{2,}|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if strategi_block:
        raw_strat = strategi_block.group(1)
        strat_items = re.findall(r"(?:^\s*[\d\-\•\*]+\.?\s*)(.+)", raw_strat, re.MULTILINE)
        result["strategi_bisnis"] = [s.strip() for s in strat_items if s.strip()]
        if not result["strategi_bisnis"]:
            result["strategi_bisnis"] = [raw_strat.strip()[:800]]

    logger.info(
        "Parsing materi presentasi selesai: jadwal='%s', lokasi='%s', agenda=%d item",
        result["jadwal"][:40] if result["jadwal"] else "(kosong)",
        result["lokasi"][:40] if result["lokasi"] else "(kosong)",
        len(result["agenda"]),
    )
    return result


# =============================================================================
# 6. build_qa_report
# =============================================================================

def build_qa_report(
    emiten: str,
    date_str: str,
    qa_pairs: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> str:
    """Buat laporan Markdown standar untuk sesi Q&A Public Expose.

    Parameters
    ----------
    emiten : str
        Kode emiten BEI (mis. ``'PGEO'``).
    date_str : str
        Tanggal pelaksanaan dalam format ``'YYYY-MM-DD'``.
    qa_pairs : list[dict]
        Output dari :func:`parse_qa_pairs`.
    metadata : dict, optional
        Info tambahan: ``lokasi``, ``moderator``, dsb.

    Returns
    -------
    str
        Dokumen Markdown lengkap.
    """
    meta = metadata or {}
    emiten_upper = emiten.upper()
    today_display = date_str or datetime.now().strftime("%Y-%m-%d")
    date_compact = today_display.replace("-", "")

    nav_left = f"knowledge-base/daily-digests/{emiten_upper}_{date_compact}"
    nav_right = f"Dashboard/{emiten_upper}"

    lines: list[str] = [
        f"# 🎤 Laporan Public Expose: [{emiten_upper}]",
        "",
        f"⬅️ [[{nav_left}]] | 📅 **{today_display}** | 🎛️ [[{nav_right}]]",
        "",
        "> [!IMPORTANT]",
        f"> Dokumen ini memuat seluruh sesi tanya jawab Public Expose {emiten_upper} "
        f"yang dilaksanakan pada **{today_display}**. "
        "Semua pertanyaan dan jawaban direproduksi secara verbatim untuk keperluan analisis investasi.",
        "",
    ]

    # Metadata opsional
    if meta:
        lines.append("## ℹ️ Informasi Acara")
        lines.append("")
        for key, val in meta.items():
            if val:
                lines.append(f"- **{key.capitalize()}**: {val}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"## ❓ Sesi Tanya Jawab ({len(qa_pairs)} Pertanyaan)")
    lines.append("")

    if not qa_pairs:
        lines.append("*Tidak ada pasangan Q&A yang berhasil diekstrak dari dokumen.*")
    else:
        for item in qa_pairs:
            nomor = item.get("nomor", "?")
            penanya = item.get("penanya", "") or "*Tidak tercatat*"
            pertanyaan = item.get("pertanyaan", "") or "*Teks pertanyaan tidak tersedia*"
            jawaban = item.get("jawaban", "") or "*Teks jawaban tidak tersedia*"

            lines.append(f"### ❓ Pertanyaan #{nomor}")
            lines.append("")
            lines.append(f"> **Pertanyaan**: {pertanyaan}")
            lines.append(f"> **Penanya**: {penanya}")
            lines.append("")
            lines.append("💡 **Jawaban Manajemen**:")
            lines.append("")
            lines.append(jawaban)
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"*Dokumen dihasilkan otomatis oleh **Swarm Intelijen Pasar Modal Indonesia** "
        f"pada {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB.*"
    )

    return "\n".join(lines)


# =============================================================================
# 7. build_presentation_report
# =============================================================================

def build_presentation_report(
    emiten: str,
    date_str: str,
    material: dict[str, Any],
) -> str:
    """Buat laporan Markdown untuk materi presentasi Public Expose.

    Parameters
    ----------
    emiten : str
        Kode emiten BEI.
    date_str : str
        Tanggal pelaksanaan dalam format ``'YYYY-MM-DD'``.
    material : dict
        Output dari :func:`parse_presentation_material`.

    Returns
    -------
    str
        Dokumen Markdown lengkap.
    """
    emiten_upper = emiten.upper()
    today_display = date_str or datetime.now().strftime("%Y-%m-%d")
    date_compact = today_display.replace("-", "")

    nav_left = f"knowledge-base/daily-digests/{emiten_upper}_{date_compact}"
    nav_right = f"Dashboard/{emiten_upper}"

    lines: list[str] = [
        f"# 📊 Materi Public Expose: [{emiten_upper}]",
        "",
        f"⬅️ [[{nav_left}]] | 📅 **{today_display}** | 🎛️ [[{nav_right}]]",
        "",
        "> [!NOTE]",
        f"> Ringkasan materi presentasi Public Expose {emiten_upper} tanggal **{today_display}**. "
        "Dokumen ini mengacu pada slide/materi resmi yang disampaikan manajemen kepada investor.",
        "",
        "---",
        "",
    ]

    # ── Jadwal & Lokasi ───────────────────────────────────────────────────────
    lines.append("## 📅 Jadwal & Lokasi")
    lines.append("")
    jadwal = material.get("jadwal", "") or "*Tidak tersedia*"
    lokasi = material.get("lokasi", "") or "*Tidak tersedia*"
    lines.append("| Item | Detail |")
    lines.append("|------|--------|")
    lines.append(f"| **Tanggal/Waktu** | {jadwal} |")
    lines.append(f"| **Lokasi/Venue** | {lokasi} |")
    lines.append("")

    # ── Agenda ────────────────────────────────────────────────────────────────
    lines.append("## 📋 Agenda")
    lines.append("")
    agenda_items: list[str] = material.get("agenda", [])
    if agenda_items:
        for i, item in enumerate(agenda_items, start=1):
            lines.append(f"{i}. {item}")
    else:
        lines.append("*Agenda tidak tersedia dalam dokumen.*")
    lines.append("")

    # ── Profil Perusahaan ─────────────────────────────────────────────────────
    lines.append("## 🏢 Profil Perusahaan")
    lines.append("")
    profil = material.get("profil_perusahaan", "") or "*Profil perusahaan tidak tersedia.*"
    lines.append(profil)
    lines.append("")

    # ── Kinerja 1H / YTD ─────────────────────────────────────────────────────
    lines.append("## 📈 Kinerja 1H / YTD")
    lines.append("")
    kinerja = material.get("kinerja_1h", "") or "*Data kinerja tidak tersedia.*"
    lines.append(kinerja)
    lines.append("")

    # ── Target & Guidance ─────────────────────────────────────────────────────
    lines.append("## 🎯 Target & Guidance Manajemen")
    lines.append("")
    target = material.get("target_tahun_depan", "") or "*Guidance tidak tersedia.*"
    lines.append(target)
    lines.append("")

    # ── Strategi Bisnis ───────────────────────────────────────────────────────
    lines.append("## 🧭 Strategi Bisnis")
    lines.append("")
    strategi: list[str] = material.get("strategi_bisnis", [])
    if strategi:
        for s in strategi:
            lines.append(f"- {s}")
    else:
        lines.append("*Poin strategi bisnis tidak tersedia.*")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"*Dokumen dihasilkan otomatis oleh **Swarm Intelijen Pasar Modal Indonesia** "
        f"pada {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB.*"
    )

    return "\n".join(lines)


# =============================================================================
# 8. save_report
# =============================================================================

def save_report(
    emiten: str,
    date_str: str,
    content: str,
    report_type: str = "public_expose",
) -> dict[str, str]:
    """Simpan laporan ke dua lokasi: primary (knowledge-base) dan backup (summaries).

    Parameters
    ----------
    emiten : str
        Kode emiten BEI.
    date_str : str
        Tanggal dalam format ``'YYYY-MM-DD'``.
    content : str
        Konten Markdown laporan.
    report_type : str, optional
        Tipe laporan untuk penamaan file (default ``'public_expose'``).

    Returns
    -------
    dict
        ``{'primary': str, 'backup': str}`` — path absolut kedua file.
    """
    emiten_upper = emiten.upper()
    date_compact = date_str.replace("-", "") if date_str else datetime.now().strftime("%Y%m%d")
    filename = f"{emiten_upper}_Public_Expose_{date_compact}.md"

    primary_path = PRIMARY_BASE / filename
    backup_path = BACKUP_BASE / filename

    saved: dict[str, str] = {"primary": "", "backup": ""}

    for label, target_path in [("PRIMARY", primary_path), ("BACKUP", backup_path)]:
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            logger.info("[%s] Laporan disimpan: %s", label, target_path)
            saved[label.lower()] = str(target_path)
        except Exception as exc:
            logger.error("[%s] Gagal menyimpan laporan ke %s: %s", label, target_path, exc)
            saved[label.lower()] = ""

    return saved


# =============================================================================
# 9. process_public_expose  (Orchestrator)
# =============================================================================

def process_public_expose(
    emiten: str,
    pdf_path: str,
    date_str: str | None = None,
) -> dict[str, Any]:
    """Pipeline utama pemrosesan Public Expose secara end-to-end.

    Urutan langkah:
    1. Ekstrak teks dari PDF
    2. Strip noise BEI
    3. Deteksi tipe dokumen
    4. Parse konten sesuai tipe
    5. Build laporan Markdown
    6. Simpan ke primary & backup

    Parameters
    ----------
    emiten : str
        Kode emiten BEI (mis. ``'PGEO'``).
    pdf_path : str
        Path ke berkas PDF Public Expose.
    date_str : str, optional
        Tanggal dalam format ``'YYYY-MM-DD'``. Default: tanggal hari ini.

    Returns
    -------
    dict
        ``{'type': str, 'qa_count': int, 'output_paths': dict, 'success': bool, 'error': str}``
    """
    result: dict[str, Any] = {
        "type": "unknown",
        "qa_count": 0,
        "output_paths": {"primary": "", "backup": ""},
        "success": False,
        "error": "",
    }

    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    logger.info("=== Memulai pipeline Public Expose: %s [%s] ===", emiten.upper(), date_str)

    # Step 1: Ekstrak teks
    try:
        raw_text = extract_text_from_pdf(pdf_path)
    except ValueError as exc:
        result["error"] = str(exc)
        logger.error("Pipeline berhenti: %s", exc)
        return result

    # Step 2: Strip noise
    clean_text = strip_bei_noise(raw_text)

    # Step 3: Deteksi tipe
    doc_type = detect_public_expose_type(clean_text)
    result["type"] = doc_type

    # Step 4 & 5: Parse + Build report
    report_content = ""
    try:
        if doc_type == "hasil_qa":
            qa_pairs = parse_qa_pairs(clean_text)
            result["qa_count"] = len(qa_pairs)
            report_content = build_qa_report(emiten, date_str, qa_pairs)
            logger.info("Q&A report dibuat: %d pasang pertanyaan-jawaban.", len(qa_pairs))

        elif doc_type == "materi_presentasi":
            material = parse_presentation_material(clean_text)
            report_content = build_presentation_report(emiten, date_str, material)
            logger.info("Presentation report dibuat.")

        elif doc_type == "undangan":
            material = parse_presentation_material(clean_text)
            material["profil_perusahaan"] = "(Dokumen ini adalah Undangan Public Expose)"
            report_content = build_presentation_report(emiten, date_str, material)
            logger.info("Invitation summary report dibuat.")

        else:
            report_content = (
                f"# ⚠️ Public Expose: [{emiten.upper()}] — Tipe Tidak Teridentifikasi\n\n"
                f"📅 **{date_str}**\n\n"
                "> [!WARNING]\n"
                "> Tipe dokumen tidak dapat diidentifikasi secara otomatis. "
                "Teks mentah disertakan di bawah untuk review manual.\n\n"
                "---\n\n"
                f"```\n{clean_text[:5000]}\n```\n"
            )
            logger.warning("Tipe unknown — menyimpan teks mentah sebagai fallback.")

    except Exception as exc:
        result["error"] = f"Parsing/building error: {exc}"
        logger.error("Gagal saat parsing/building report: %s", exc, exc_info=True)
        report_content = (
            f"# ⚠️ Public Expose: [{emiten.upper()}] — Error Pemrosesan\n\n"
            f"📅 **{date_str}**\n\nError: {exc}\n\n---\n\n"
            f"Teks mentah (5000 karakter pertama):\n```\n{clean_text[:5000]}\n```\n"
        )

    # Step 6: Simpan
    if report_content:
        output_paths = save_report(emiten, date_str, report_content)
        result["output_paths"] = output_paths
        result["success"] = bool(output_paths.get("primary") or output_paths.get("backup"))
    else:
        result["error"] = (result.get("error") or "") + " | Konten laporan kosong."

    logger.info(
        "=== Pipeline selesai: %s | tipe=%s | qa=%d | sukses=%s ===",
        emiten.upper(), result["type"], result["qa_count"], result["success"],
    )
    return result


# =============================================================================
# 10. CLI Interface
# =============================================================================

def _build_cli_parser() -> argparse.ArgumentParser:
    """Buat CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="public_expose_builder",
        description=(
            "Pemroses berkas Public Expose BEI — "
            "Swarm Intelijen Pasar Modal Indonesia"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python public_expose_builder.py --emiten PGEO --file reports/raw/PGEO/public_expose.pdf
  python public_expose_builder.py --emiten PGEO --file reports/raw/PGEO/public_expose.pdf --date 2026-09-23
  python public_expose_builder.py --emiten BBCA --file /path/to/hasil_qa.pdf --verbose
        """,
    )
    parser.add_argument(
        "--emiten", "-e",
        required=True,
        metavar="KODE",
        help="Kode emiten BEI (mis. PGEO, BBCA, ANTM)",
    )
    parser.add_argument(
        "--file", "-f",
        required=True,
        metavar="PATH",
        dest="pdf_path",
        help="Path ke berkas PDF Public Expose",
    )
    parser.add_argument(
        "--date", "-d",
        metavar="YYYY-MM-DD",
        default=None,
        help="Tanggal pelaksanaan (default: hari ini)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Tampilkan log DEBUG",
    )
    return parser


def main() -> None:
    """Entry point CLI."""
    parser = _build_cli_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Mode verbose aktif.")

    result = process_public_expose(
        emiten=args.emiten,
        pdf_path=args.pdf_path,
        date_str=args.date,
    )

    # Ringkasan output ke stdout
    print("\n" + "=" * 60)
    print("  Public Expose Builder — Hasil Pemrosesan")
    print("=" * 60)
    print(f"  Emiten      : {args.emiten.upper()}")
    print(f"  Tipe Dok.   : {result['type']}")
    print(f"  Jumlah Q&A  : {result['qa_count']}")
    print(f"  Status      : {'✅ Sukses' if result['success'] else '❌ Gagal'}")
    if result.get("error"):
        print(f"  Error       : {result['error']}")
    print()
    if result["output_paths"].get("primary"):
        print(f"  📁 Primary  : {result['output_paths']['primary']}")
    if result["output_paths"].get("backup"):
        print(f"  💾 Backup   : {result['output_paths']['backup']}")
    print("=" * 60 + "\n")

    sys.exit(0 if result["success"] else 1)


def build_public_expose_report(emiten: str, title: str, file_path: str):
    """Pipeline adapter function for daily_run."""
    return process_public_expose(pdf_path=file_path, emiten=emiten)


if __name__ == "__main__":
    main()
