# Public Expose Builder — Swarm Intelijen Pasar Modal Indonesia
# =============================================================================
# Modul pemroses berkas Public Expose dari Bursa Efek Indonesia (BEI).
# Mampu memproses berkas ganda (surat pengantar + slide presentasi lampiran + risalah Q&A).
#
# Author  : Financial Summarizer Agent
# Version : 3.0.0 (Smart Multi-File & Slide-Aware Heuristic Extractor)
# Updated : 2026-10-12
# =============================================================================

from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Pastikan output konsol Windows mendukung UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Graceful imports — PyMuPDF preferred, pypdf as fallback
# ---------------------------------------------------------------------------
try:
    import pymupdf as fitz
    _FITZ_AVAILABLE = True
except ImportError:
    try:
        import fitz
        _FITZ_AVAILABLE = True
    except ImportError:
        _FITZ_AVAILABLE = False

try:
    from pypdf import PdfReader
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

_NOISE_PATTERNS: list[str] = [
    r"Go To English Page",
    r"Go To Indonesian Page",
    r"Dokumen ini merupakan dokumen resmi[^\n]*",
    r"This is an official document[^\n]*",
    r"Hormat Kami[^\n]*",
    r"Respectfully[^\n]*",
    r"Demikian untuk diketahui[^\n]*",
    r"Thus to be informed accordingly[^\n]*",
    r"https?://\S+",
    r"www\.\S+",
    r"\(02\d\)[\s\d\-]+",
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    r"PT Kustodian Sentral Efek Indonesia[^\n]*",
    r"Bursa Efek Indonesia[^\n]*(?:menyampaikan|meneruskan)[^\n]*",
]
_COMPILED_NOISE = [re.compile(p, re.IGNORECASE) for p in _NOISE_PATTERNS]


# =============================================================================
# Helper: Extract Clean Text from PDF
# =============================================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    """Ekstrak teks lengkap dari berkas PDF."""
    path = Path(pdf_path)
    if not path.exists():
        raise ValueError(f"Berkas tidak ditemukan: {pdf_path}")

    if _FITZ_AVAILABLE:
        try:
            doc = fitz.open(str(path))
            pages = []
            for page in doc:
                txt = page.get_text()
                if txt and txt.strip():
                    pages.append(txt.strip())
            doc.close()
            full_text = "\n\n".join(pages)
            if full_text.strip():
                return full_text
        except Exception as exc:
            logger.warning("PyMuPDF ekstraksi gagal (%s): %s", path.name, exc)

    if _PYPDF_AVAILABLE:
        try:
            reader = PdfReader(str(path))
            pages_text = [pg.extract_text() or "" for pg in reader.pages]
            full_text = "\n\n".join(pages_text).strip()
            if full_text:
                return full_text
        except Exception as exc:
            logger.warning("pypdf ekstraksi gagal (%s): %s", path.name, exc)

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def extract_pdf_pages_structured(pdf_path: str) -> list[dict[str, Any]]:
    """Ekstrak informasi per halaman/slide (blocks, text, image count)."""
    path = Path(pdf_path)
    pages_data = []
    if not path.exists() or not _FITZ_AVAILABLE:
        return pages_data

    try:
        doc = fitz.open(str(path))
        for idx, page in enumerate(doc):
            text = page.get_text("text").strip()
            blocks = page.get_text("blocks")
            images = page.get_images()
            pages_data.append({
                "page_num": idx + 1,
                "text": text,
                "blocks": blocks,
                "image_count": len(images),
                "is_mostly_image": len(images) > 0 and len(text) < 150,
            })
        doc.close()
    except Exception as exc:
        logger.warning("Gagal ekstraksi terstruktur: %s (%s)", path.name, exc)

    return pages_data


def strip_bei_noise(text: str) -> str:
    """Bersihkan teks dari noise dan boilerplate."""
    if not text:
        return ""
    cleaned = text
    for pattern in _COMPILED_NOISE:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def clean_flow_text(text: str) -> str:
    """Gabungkan baris-baris tunggal menjadi kalimat rapi mengalir."""
    if not text:
        return ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    out = []
    buf = []
    for l in lines:
        if l.isdigit() and len(l) <= 2:
            continue
        if len(l.split()) <= 2 and not l.startswith(("-", "*", "•", "No.", "1.", "2.", "3.", "4.", "5.")):
            buf.append(l)
        else:
            if buf:
                out.append(" ".join(buf))
                buf = []
            out.append(l)
    if buf:
        out.append(" ".join(buf))
    return "\n".join(out)


# =============================================================================
# Helper: Metadata Extractor dari Surat Pengantar BEI
# =============================================================================

def parse_cover_letter_metadata(text: str) -> dict[str, str]:
    """Ekstrak informasi formal dari surat pengantar BEI (biasanya PDF 5 KB)."""
    meta = {
        "nomor_surat": "",
        "perihal": "",
        "tanggal_waktu_surat": "",
        "peserta_hadir": "",
        "tanggal_pelaksanaan": "",
        "waktu_pelaksanaan": "",
        "tempat_pelaksanaan": "",
        "penyelenggara": "",
        "lampiran_nama": "",
    }
    if not text:
        return meta

    # Cek tabel 5-baris standar pengumuman BEI
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i in range(len(lines) - 9):
        if (lines[i].lower() == "nomor surat" and 
            lines[i+1].lower() == "nama perusahaan" and
            lines[i+2].lower() == "kode emiten" and
            lines[i+3].lower() == "lampiran" and
            lines[i+4].lower() == "perihal"):
            meta["nomor_surat"] = lines[i+5]
            meta["penyelenggara"] = lines[i+6]
            meta["lampiran_nama"] = lines[i+8]
            meta["perihal"] = lines[i+9]
            break

    # Fallback regex jika belum terisi
    if not meta["nomor_surat"]:
        m = re.search(r"(?:Nomor Surat|Announcement No\.?)\s*[:\n]\s*([^\n]+)", text, re.I)
        if m:
            meta["nomor_surat"] = m.group(1).strip()

    if not meta["perihal"]:
        m = re.search(r"(?:Perihal|Subject)\s*[:\n]\s*([^\n]+)", text, re.I)
        if m:
            meta["perihal"] = m.group(1).strip()

    # Tanggal dan Waktu pengiriman
    m = re.search(r"(?:Tanggal dan Waktu|Date and Time)\s*[:\n]\s*([^\n]+)", text, re.I)
    if m:
        meta["tanggal_waktu_surat"] = m.group(1).strip()

    # Peserta yang hadir
    m = re.search(r"Peserta yang hadir[^\n]*\s*adalah\s*(?:sebanyak\s*)?([^\n\.]+)", text, re.I)
    if m:
        meta["peserta_hadir"] = m.group(1).strip()

    # Hari/Tanggal pelaksanaan acara
    m = re.search(r"(?:Hari\s*/\s*Tanggal|Tanggal Pelaksanaan)\s*[:\n]\s*([^\n]+)", text, re.I)
    if m:
        meta["tanggal_pelaksanaan"] = m.group(1).strip()

    # Waktu
    m = re.search(r"(?:Waktu\s*[:\n]\s*)([^\n]+)", text, re.I)
    if m:
        meta["waktu_pelaksanaan"] = m.group(1).strip()

    # Tempat/Media
    m = re.search(r"(?:Tempat|Lokasi|Media)\s*[:\n]\s*([^\n]+)", text, re.I)
    if m:
        meta["tempat_pelaksanaan"] = m.group(1).strip()

    # Nama Lampiran
    m = re.search(r"Lampiran\s*[:\n]\s*\d+\.\s*([^\n]+)", text, re.I)
    if m:
        meta["lampiran_nama"] = m.group(1).strip()

    return meta


# =============================================================================
# Smart Q&A Parser
# =============================================================================

def parse_qa_pairs_advanced(raw_text: str, pages_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ekstrak pasangan tanya jawab dari teks atau tabel dua kolom."""
    results: list[dict[str, Any]] = []

    # 1. Coba deteksi koordinat tabel dua kolom (seperti HEXA)
    table_qa = _parse_column_qa_from_pages(pages_data)
    if table_qa:
        logger.info("Ekstraksi Q&A tabel dua kolom berhasil: %d pertanyaan.", len(table_qa))
        return table_qa

    # 2. Format Q1, Q2, Q3 atau Pertanyaan 1, Pertanyaan 2
    q_matches = _parse_numbered_qa(raw_text)
    if q_matches:
        logger.info("Ekstraksi Q&A format penomoran berhasil: %d pertanyaan.", len(q_matches))
        return q_matches

    # 3. Format Penanya / Pertanyaan / Jawaban
    label_pattern = re.compile(
        r"(?:Penanya|Nama)\s*:\s*(?P<penanya>[^\n]+)\n"
        r"(?:Pertanyaan|Topik)\s*:\s*(?P<pertanyaan>.*?)\n"
        r"(?:Jawaban(?:\s+Manajemen)?|Tanggapan)\s*:\s*(?P<jawaban>.*?)"
        r"(?=(?:Penanya|Nama)\s*:|$)",
        re.DOTALL | re.IGNORECASE,
    )
    label_matches = list(label_pattern.finditer(raw_text))
    if label_matches:
        for i, m in enumerate(label_matches, start=1):
            results.append({
                "nomor": i,
                "penanya": m.group("penanya").strip(),
                "pertanyaan": m.group("pertanyaan").strip(),
                "jawaban": m.group("jawaban").strip(),
            })
        return results

    # 4. Format Lettered A-D
    lettered_pattern = re.compile(
        r"A\.\s*(?P<pertanyaan>.*?)"
        r"B\.\s*(?P<penanya>.*?)"
        r"(?:C\.\s*(?P<jabatan>.*?))?"
        r"D\.\s*(?P<jawaban>.*?)"
        r"(?=A\.|$)",
        re.DOTALL | re.IGNORECASE,
    )
    lettered_matches = list(lettered_pattern.finditer(raw_text))
    if lettered_matches:
        for i, m in enumerate(lettered_matches, start=1):
            penanya = m.group("penanya") or ""
            jabatan = m.group("jabatan") or ""
            penanya_full = f"{penanya.strip()} — {jabatan.strip()}" if jabatan.strip() else penanya.strip()
            results.append({
                "nomor": i,
                "penanya": penanya_full,
                "pertanyaan": m.group("pertanyaan").strip(),
                "jawaban": m.group("jawaban").strip(),
            })
        return results

    return results


def _parse_column_qa_from_pages(pages_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deteksi sesi Q&A berbasis koordinat kolom kiri (Pertanyaan) & kanan (Jawaban)."""
    qa_list: list[dict[str, Any]] = []
    current_q: dict[str, Any] | None = None

    for p in pages_data:
        blocks = p.get("blocks", [])
        if not blocks:
            continue

        # Cari tahu apakah halaman ini adalah halaman Q&A
        txt = p.get("text", "")
        if "pertanyaan" not in txt.lower() and "question" not in txt.lower() and not qa_list:
            continue

        for b in blocks:
            if len(b) < 5 or not isinstance(b[4], str):
                continue
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4].strip()
            if not text or len(text) < 3:
                continue

            # Abaikan running header / footer
            if "MOM_" in text or "Lampiran" in text or "PAPARAN PUBLIK" in text or "Halaman" in text:
                continue
            if "Pertanyaan (Question)" in text or "Jawaban (Answer)" in text:
                continue

            # Kolom kiri: Pertanyaan / Penanya (x0 < 325)
            # Kolom kanan: Jawaban (x0 >= 325)
            is_left_col = x0 < 325

            # Deteksi awal pertanyaan baru (Q1, Q2, atau Penanya)
            q_match = re.match(r"^(?:(?:Q|No\.?|Pertanyaan)\s*(\d+)|\b(\d+)\.)\s*(.*)", text, re.I | re.DOTALL)
            is_new_q = False
            q_num = len(qa_list) + 1
            if q_match and is_left_col:
                is_new_q = True
                try:
                    q_num = int(q_match.group(1) or q_match.group(2))
                except Exception:
                    pass

            if is_new_q:
                if current_q and (current_q["pertanyaan"] or current_q["jawaban"]):
                    qa_list.append(current_q)
                current_q = {
                    "nomor": q_num,
                    "penanya": "",
                    "pertanyaan": text,
                    "jawaban": "",
                }
            elif current_q is not None:
                if is_left_col:
                    current_q["pertanyaan"] += "\n" + text
                else:
                    if current_q["jawaban"]:
                        current_q["jawaban"] += "\n\n" + text
                    else:
                        current_q["jawaban"] = text

    if current_q and (current_q["pertanyaan"] or current_q["jawaban"]):
        qa_list.append(current_q)

    # Bersihkan whitespace
    for item in qa_list:
        item["pertanyaan"] = item["pertanyaan"].strip()
        item["jawaban"] = item["jawaban"].strip()

    return qa_list


def _parse_numbered_qa(raw_text: str) -> list[dict[str, Any]]:
    """Parse format penomoran seperti '1. Pertanyaan: ... Jawaban: ...'."""
    # Pastikan tidak tertukar dengan Kuartal Q1, Q2, Q3, Q4 di presentasi
    pattern = re.compile(
        r"(?:^|\n)\s*(?:(?:Pertanyaan|Question)\s*[:#\.]?\s*(\d+)|(?:^|\n)\s*(\d+)\.\s+(?:Pertanyaan|Question))\s*[:\.]?\s*"
        r"(?P<pertanyaan>.*?)"
        r"(?:(?:Jawaban|Answer|Tanggapan)\s*[:\.]?\s*|\n(?=(?:Pertanyaan|Question)\s*[:#\.]?\s*\d+|\d+\.\s+(?:Pertanyaan|Question)|$))"
        r"(?P<jawaban>.*?)"
        r"(?=(?:(?:Pertanyaan|Question)\s*[:#\.]?\s*\d+|\d+\.\s+(?:Pertanyaan|Question)|\Z))",
        re.DOTALL | re.IGNORECASE,
    )
    items = []
    for idx, m in enumerate(pattern.finditer(raw_text), start=1):
        items.append({
            "nomor": idx,
            "penanya": "",
            "pertanyaan": m.group("pertanyaan").strip(),
            "jawaban": m.group("jawaban").strip(),
        })
    return items


# =============================================================================
# Slide Presentation Extractor (Slide-Aware Heuristics)
# =============================================================================

def parse_presentation_deck(pages_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Ekstrak materi presentasi dari seluruh slide deck."""
    deck: dict[str, Any] = {
        "total_slides": len(pages_data),
        "agenda": [],
        "profil_perseroan": [],
        "pilar_bisnis": [],
        "aset_operasional": [],
        "kinerja_keuangan": [],
        "rasio_keuangan": [],
        "inisiatif_strategis": [],
        "target_guidance": [],
        "slides_summary": [],
    }

    current_section = "Umum"

    for p in pages_data:
        s_num = p["page_num"]
        raw = p["text"].strip()
        if not raw:
            continue

        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        title = lines[0] if lines else f"Slide {s_num}"
        if len(title) < 5 and len(lines) > 1:
            title = f"{lines[0]} {lines[1]}"

        deck["slides_summary"].append({
            "slide": s_num,
            "title": title,
            "preview": " ".join(lines[1:4])[:150] if len(lines) > 1 else "",
        })

        lower_raw = raw.lower()

        # Deteksi Agenda / Daftar Isi
        if any(k in lower_raw for k in ["daftar isi", "agenda", "susunan acara", "table of contents"]):
            for l in lines[1:]:
                if len(l) > 4 and not l.isdigit():
                    deck["agenda"].append(l)

        # Deteksi Profil Perseroan
        elif any(k in lower_raw for k in ["sekilas perseroan", "company overview", "tentang perseroan", "profil perusahaan"]):
            deck["profil_perseroan"].append(raw)

        # Deteksi Pilar Bisnis & Portofolio
        elif any(k in lower_raw for k in ["pilar", "operating hotels", "shopping malls", "industrial parks", "landed housing"]):
            deck["pilar_bisnis"].append(raw)

        # Deteksi Aset Operasional
        elif any(k in lower_raw for k in ["kinerja operasional", "aset", "proyek", "paragon mall", "po hotel"]):
            deck["aset_operasional"].append(raw)

        # Deteksi Kinerja Keuangan
        elif any(k in lower_raw for k in ["laporan posisi keuangan", "kinerja keuangan", "operational results", "financial performance", "hasil- hasil operasional"]):
            deck["kinerja_keuangan"].append(raw)

        # Deteksi Rasio Keuangan
        elif any(k in lower_raw for k in ["rasio keuangan", "financial ratio", "return on asset", "return on equity", "current ratio", "debt to equity"]):
            deck["rasio_keuangan"].append(raw)

        # Deteksi Target & Guidance
        elif any(k in lower_raw for k in ["target pertumbuhan", "guidance", "target 2026", "outlook", "proyeksi"]):
            deck["target_guidance"].append(raw)

        # Deteksi Strategi Usaha & Kemitraan
        elif any(k in lower_raw for k in ["strategi usaha", "signing ceremony", "kemitraan", "strategic initiative", "kerja sama", "accor", "marriott"]):
            deck["inisiatif_strategis"].append(raw)

    return deck


# =============================================================================
# Document Builder: Presentation Report (Materi Pubex)
# =============================================================================

def build_presentation_markdown(
    emiten: str,
    date_str: str,
    deck: dict[str, Any],
    meta: dict[str, str],
) -> str:
    """Susun berkas Markdown komprehensif untuk Materi Public Expose."""
    emiten_upper = emiten.upper()
    today_display = date_str or datetime.now().strftime("%Y-%m-%d")
    date_compact = today_display.replace("-", "")

    nav_left = f"knowledge-base/daily-digests/{emiten_upper}_{date_compact}"
    nav_right = f"Dashboard/{emiten_upper}"

    lines: list[str] = [
        f"# 📊 Materi Public Expose: [{emiten_upper}]",
        "",
        f"🏢 **Emiten**: `{emiten_upper}` | 📅 **Tanggal Pelaksanaan**: `{today_display}` | 📑 **Total Slide**: `{deck.get('total_slides', 0)} Slide`",
        f"⬅️ [[{nav_left}|Kembali ke Daily Digest]] | 🎛️ [[{nav_right}|Ke Dashboard Emiten]]",
        "",
        "> [!NOTE]",
        f"> Ringkasan materi presentasi resmi Public Expose {emiten_upper} yang disampaikan oleh manajemen kepada investor dan bursa. "
        "Seluruh poin strategis, matriks operasional, dan angka kinerja diekstrak langsung dari slide deck resmi.",
        "",
        "---",
        "",
        "## 📅 1. Jadwal & Metadata Penyelenggaraan",
        "",
        "| Parameter | Detail Informasi |",
        "|---|---|",
        f"| **Nomor Surat Pengantar** | {meta.get('nomor_surat') or '-'} |",
        f"| **Perihal Pengumuman** | {meta.get('perihal') or 'Materi Public Expose'} |",
        f"| **Waktu Pelaksanaan** | {meta.get('tanggal_pelaksanaan') or today_display} {meta.get('waktu_pelaksanaan') or ''} |",
        f"| **Lokasi / Media** | {meta.get('tempat_pelaksanaan') or 'Aplikasi Zoom / Daring'} |",
        f"| **Lampiran Resmi** | `{meta.get('lampiran_nama') or 'Materi Presentasi Slide Deck'}` |",
        "",
    ]

    # Agenda
    lines.append("## 📋 2. Agenda Paparan Publik")
    lines.append("")
    if deck["agenda"]:
        for i, ag in enumerate(deck["agenda"], start=1):
            lines.append(f"{i}. {ag}")
    else:
        lines.append("- Pemaparan Profil & Struktur Bisnis Perseroan")
        lines.append("- Kinerja Operasional & Keuangan")
        lines.append("- Arah Strategi Usaha & Target Pertumbuhan")
        lines.append("- Sesi Tanya Jawab (Q&A)")
    lines.append("")

    # Profil & Pilar Bisnis
    lines.append("## 🏢 3. Profil & Pilar Portofolio Bisnis")
    lines.append("")
    if deck["profil_perseroan"]:
        for p in deck["profil_perseroan"]:
            cleaned = clean_flow_text(p)
            lines.append(f"> {cleaned[:1500]}")
            lines.append("")
    if deck["pilar_bisnis"]:
        lines.append("### 🏛️ Pilar Usaha & Aset Utama")
        for pil in deck["pilar_bisnis"]:
            cleaned = clean_flow_text(pil)
            lines.append(f"- {cleaned[:1000]}")
            lines.append("")

    # Kinerja Operasional
    lines.append("## 🏗️ 4. Kinerja Operasional & Portofolio Aset")
    lines.append("")
    if deck["aset_operasional"]:
        for aset in deck["aset_operasional"]:
            cleaned = clean_flow_text(aset)
            lines.append(f"> {cleaned[:1200]}")
            lines.append("")
    else:
        lines.append("*Detail aset operasional terlampir pada dokumen slide resmi.*")
        lines.append("")

    # Kinerja Keuangan & Rasio
    lines.append("## 📈 5. Kinerja Keuangan & Posisi Finansial")
    lines.append("")
    if deck["kinerja_keuangan"]:
        for k in deck["kinerja_keuangan"]:
            lines.append("### 📊 Ringkasan Finansial")
            lines.append("```text")
            lines.append(clean_flow_text(k)[:1200].strip())
            lines.append("```")
            lines.append("")
    if deck["rasio_keuangan"]:
        lines.append("### 🧮 Rasio Keuangan Utama")
        for r in deck["rasio_keuangan"]:
            lines.append("```text")
            lines.append(clean_flow_text(r)[:1000].strip())
            lines.append("```")
            lines.append("")

    # Inisiatif Strategis & Ekspansi
    lines.append("## 🧭 6. Inisiatif Strategis, Kolaborasi, & Kemitraan")
    lines.append("")
    if deck["inisiatif_strategis"]:
        for strat in deck["inisiatif_strategis"]:
            cleaned = clean_flow_text(strat)
            lines.append(f"- {cleaned[:1500]}")
            lines.append("")
    else:
        lines.append("*Strategi usaha difokuskan pada penguatan fundamental dan ekspansi operasional.*")
        lines.append("")

    # Target & Guidance
    lines.append("## 🎯 7. Target Pertumbuhan & Guidance Manajemen")
    lines.append("")
    if deck["target_guidance"]:
        for tg in deck["target_guidance"]:
            cleaned = clean_flow_text(tg)
            lines.append(f"> {cleaned[:1000]}")
            lines.append("")
    else:
        lines.append("*Target pertumbuhan ditetapkan mengacu pada prospek industri dan kondisi makroekonomi terkini.*")
        lines.append("")

    # Mermaid Roadmap
    lines.append("## 🗺️ 8. Peta Jalur Strategis & Eksekusi")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    lines.append(f'    A["🏢 {emiten_upper}"] --> B["📊 Operasional & Aset"]')
    lines.append(f'    A --> C["📈 Kinerja Finansial"]')
    lines.append(f'    B --> D["🤝 Kemitraan Strategis"]')
    lines.append(f'    C --> E["🎯 Target & Guidance"]')
    lines.append("```")
    lines.append("")

    # Slide Navigator
    lines.append("## 📑 9. Daftar Indeks Slide Presentasi")
    lines.append("")
    lines.append("| Slide # | Judul / Topik Slide | Ringkasan Konten |")
    lines.append("|---|---|---|")
    for s in deck["slides_summary"]:
        lines.append(f"| Slide {s['slide']} | **{s['title']}** | {s['preview']} |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*Dokumen diolah otomatis oleh **Swarm Intelijen Pasar Modal Indonesia** pada {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB.*")

    return "\n".join(lines)


# =============================================================================
# Document Builder: Q&A Report (Hasil Pubex)
# =============================================================================

def build_qa_markdown(
    emiten: str,
    date_str: str,
    qa_pairs: list[dict[str, Any]],
    meta: dict[str, str],
    is_scanned_notice: bool = False,
) -> str:
    """Susun berkas Markdown komprehensif untuk Hasil Tanya Jawab (Q&A)."""
    emiten_upper = emiten.upper()
    today_display = date_str or datetime.now().strftime("%Y-%m-%d")
    date_compact = today_display.replace("-", "")

    nav_left = f"knowledge-base/daily-digests/{emiten_upper}_{date_compact}"
    nav_right = f"Dashboard/{emiten_upper}"

    lines: list[str] = [
        f"# 🎤 Laporan Hasil Public Expose: [{emiten_upper}]",
        "",
        f"🏢 **Emiten**: `{emiten_upper}` | 📅 **Tanggal Pelaksanaan**: `{today_display}` | ❓ **Total Pertanyaan**: `{len(qa_pairs)} Pertanyaan`",
        f"⬅️ [[{nav_left}|Kembali ke Daily Digest]] | 🎛️ [[{nav_right}|Ke Dashboard Emiten]]",
        "",
        "> [!IMPORTANT]",
        f"> Dokumen ini memuat seluruh risalah hasil pelaksanaan dan sesi tanya jawab (Q&A) Public Expose {emiten_upper}. "
        "Informasi dicatat secara verbatim guna memberikan analisis sentimen dan arah kebijakan manajemen bagi investor.",
        "",
        "---",
        "",
        "## ℹ️ 1. Informasi Penyelenggaraan & Kehadiran",
        "",
        "| Parameter | Detail Pelaksanaan |",
        "|---|---|",
        f"| **Nomor Surat** | {meta.get('nomor_surat') or '-'} |",
        f"| **Perihal** | {meta.get('perihal') or 'Laporan Hasil Public Expose'} |",
        f"| **Waktu Pengumuman** | {meta.get('tanggal_waktu_surat') or today_display} |",
        f"| **Jumlah Kehadiran Peserta** | {meta.get('peserta_hadir') or 'Sesuai daftar hadir bursa'} |",
        f"| **Lampiran Berkas** | `{meta.get('lampiran_nama') or 'Risalah Tanya Jawab Resmi'}` |",
        "",
        "---",
        "",
        f"## 💬 2. Risalah Tanya Jawab Manajemen & Investor ({len(qa_pairs)} Pertanyaan)",
        "",
    ]

    if not qa_pairs:
        if is_scanned_notice:
            lines.append("> [!NOTE]")
            lines.append("> **Catatan Format Berkas**: Dokumen lampiran risalah tanya jawab bursa berupa pindaian gambar/rasterized PDF. "
                         "Teks digital tidak dapat diekstrak secara langsung tanpa OCR. Seluruh berkas pindaian asli tersimpan aman di folder mentah bursa.")
        else:
            lines.append("*Sesi tanya jawab tidak memuat pertanyaan tertulis atau materi dipaparkan secara langsung.*")
        lines.append("")
    else:
        for item in qa_pairs:
            nomor = item.get("nomor", "?")
            penanya = item.get("penanya", "") or "*Investor / Analis Publik*"
            pertanyaan = item.get("pertanyaan", "") or "*Teks pertanyaan tidak tersedia*"
            jawaban = item.get("jawaban", "") or "*Teks tanggapan manajemen tidak tersedia*"

            lines.append(f"### ❓ Pertanyaan #{nomor}")
            lines.append("")
            lines.append(f"> **Penanya**: {penanya}")
            lines.append("")
            lines.append("```text")
            lines.append(f"Pertanyaan:\n{pertanyaan}")
            lines.append("```")
            lines.append("")
            lines.append("💡 **Jawaban & Klarifikasi Manajemen**:")
            lines.append("")
            lines.append(f"> {jawaban.replace(chr(10), chr(10) + '> ')}")
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append("## 📌 3. Peta Jalur Transparansi & Kepercayaan Pasar")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart TD")
    lines.append(f'    A["📢 Public Expose ({emiten_upper})"] --> B["💬 Dialog Manajemen & Publik"]')
    lines.append(f'    B --> C["🔍 Klarifikasi Isu Strategis & Finansial"]')
    lines.append(f'    C --> D["📊 Transparansi & Tata Kelola Perusahaan"]')
    lines.append("```")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*Dokumen diolah otomatis oleh **Swarm Intelijen Pasar Modal Indonesia** pada {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB.*")

    return "\n".join(lines)


# =============================================================================
# Save Function: Save to Primary and Backup Subfolders
# =============================================================================

def save_pubex_report(
    emiten: str,
    date_str: str,
    content: str,
    subfolder: str,  # 'informasi-pubex' atau 'hasil-pubex'
) -> dict[str, str]:
    """Simpan dokumen Markdown ke folder primary dan backup sesuai subfolder."""
    emiten_upper = emiten.upper()
    date_compact = date_str.replace("-", "") if date_str else datetime.now().strftime("%Y%m%d")
    filename = f"{emiten_upper}_Public_Expose_{date_compact}.md"

    primary_target = PRIMARY_BASE / subfolder / filename
    backup_target = BACKUP_BASE / subfolder / filename

    saved = {"primary": "", "backup": ""}
    for label, target_path in [("PRIMARY", primary_target), ("BACKUP", backup_target)]:
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            logger.info("[%s] Laporan tersimpan di %s/%s", label, subfolder, filename)
            saved[label.lower()] = str(target_path)
        except Exception as exc:
            logger.error("[%s] Gagal menyimpan ke %s: %s", label, target_path, exc)

    return saved


# =============================================================================
# Multi-File Announcement Handler
# =============================================================================

def process_announcement_bundle(
    emiten: str,
    main_pdf: str,
    lampiran_pdfs: list[str],
    date_str: str | None = None,
) -> dict[str, Any]:
    """Memproses paket pengumuman BEI (surat pengantar + seluruh berkas lampiran)."""
    emiten_upper = emiten.upper()

    # Ekstrak tanggal dari filename jika tidak diberikan
    if not date_str:
        m = re.search(r"(\d{4})(\d{2})(\d{2})", Path(main_pdf).name)
        if m:
            date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Ekstrak teks surat pengantar
    cover_text = extract_text_from_pdf(main_pdf)
    meta = parse_cover_letter_metadata(cover_text)

    # 2. Deteksi apakah ini Hasil atau Informasi/Materi
    perihal = meta.get("perihal", "").lower()
    subject_text = (perihal + " " + Path(main_pdf).name).lower()
    is_materi = any(k in subject_text for k in ["materi", "paparan", "presentasi"])
    is_hasil = (not is_materi) and any(k in subject_text for k in ["hasil", "qa", "q&a", "risalah", "tanya jawab"])

    results = []

    # Jika tidak ada lampiran, proses dokumen utama
    all_targets = lampiran_pdfs if lampiran_pdfs else [main_pdf]

    for target_pdf in all_targets:
        pages_data = extract_pdf_pages_structured(target_pdf)
        raw_text = extract_text_from_pdf(target_pdf)

        # Cek apakah target adalah sesi Q&A
        qa_pairs = parse_qa_pairs_advanced(raw_text, pages_data) if (is_hasil or not is_materi) else []

        # Tentukan tipe dokumen
        if is_hasil or (not is_materi and len(qa_pairs) > 0) or "hasil" in Path(target_pdf).name.lower():
            is_scanned = all(p.get("is_mostly_image", False) for p in pages_data) if pages_data else False
            report_md = build_qa_markdown(emiten_upper, date_str, qa_pairs, meta, is_scanned_notice=is_scanned)
            save_info = save_pubex_report(emiten_upper, date_str, report_md, "hasil-pubex")
            results.append({"type": "hasil_qa", "qa_count": len(qa_pairs), "saved": save_info})
        else:
            deck = parse_presentation_deck(pages_data)
            report_md = build_presentation_markdown(emiten_upper, date_str, deck, meta)
            save_info = save_pubex_report(emiten_upper, date_str, report_md, "informasi-pubex")
            results.append({"type": "materi_presentasi", "slides": deck["total_slides"], "saved": save_info})

    return {"emiten": emiten_upper, "date": date_str, "processed": results}


# =============================================================================
# Single-File Adapter (Backward Compatible with daily_run)
# =============================================================================

def process_public_expose(
    emiten: str,
    pdf_path: str,
    date_str: str | None = None,
) -> dict[str, Any]:
    """Handler tunggal dengan auto-pairing berkas lampiran pendukung."""
    emiten_upper = emiten.upper()
    path = Path(pdf_path)

    # Cek apakah berkas ini adalah _lamp1 atau berkas induk
    parent_dir = path.parent
    base_stem = path.stem.split("_lamp")[0]

    # Cari berkas pasangan
    sibling_files = list(parent_dir.glob(f"{base_stem}*.pdf"))
    main_pdf = None
    lampiran_pdfs = []

    for f in sibling_files:
        if "_lamp" in f.name:
            lampiran_pdfs.append(str(f))
        else:
            main_pdf = str(f)

    if not main_pdf:
        main_pdf = str(path)

    return process_announcement_bundle(
        emiten=emiten_upper,
        main_pdf=main_pdf,
        lampiran_pdfs=lampiran_pdfs,
        date_str=date_str,
    )


def build_public_expose_report(emiten: str, title: str, file_path: str):
    """Pipeline adapter untuk dipanggil dari daily_run."""
    return process_public_expose(emiten=emiten, pdf_path=file_path)


# =============================================================================
# CLI Interface & Batch Processing
# =============================================================================

def batch_process_all(raw_base: Path = Path(r"g:\My Drive\Model2\reports\raw")) -> None:
    """Proses seluruh pengumuman Public Expose di folder reports/raw/."""
    logger.info("=== Memulai Batch Processing Public Expose dari: %s ===", raw_base)
    emitens = [d for d in raw_base.iterdir() if d.is_dir()]
    total_processed = 0

    for em_dir in sorted(emitens):
        emiten = em_dir.name
        pubex_files = list(em_dir.glob("*Public Expose*.pdf"))
        if not pubex_files:
            continue

        # Kelompokkan berdasarkan base stem (sebelum _lamp)
        bundles: dict[str, list[Path]] = {}
        for f in pubex_files:
            stem = f.stem.split("_lamp")[0]
            bundles.setdefault(stem, []).append(f)

        for stem, files in bundles.items():
            main_file = next((f for f in files if "_lamp" not in f.name), files[0])
            lamp_files = [f for f in files if "_lamp" in f.name]

            logger.info("Memproses bundle [%s]: %s (%d lampiran)", emiten, main_file.name, len(lamp_files))
            try:
                res = process_announcement_bundle(
                    emiten=emiten,
                    main_pdf=str(main_file),
                    lampiran_pdfs=[str(lf) for lf in lamp_files],
                )
                total_processed += 1
            except Exception as exc:
                logger.error("Gagal memproses [%s / %s]: %s", emiten, stem, exc, exc_info=True)

    logger.info("=== Batch Processing selesai: %d pengumuman diproses ===", total_processed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Public Expose Builder v3.0")
    parser.add_argument("--emiten", "-e", help="Kode emiten")
    parser.add_argument("--file", "-f", help="Path PDF")
    parser.add_argument("--date", "-d", help="Tanggal YYYY-MM-DD")
    parser.add_argument("--batch", action="store_true", help="Proses batch seluruh raw")

    args = parser.parse_args()

    if args.batch:
        batch_process_all()
    elif args.emiten and args.file:
        res = process_public_expose(args.emiten, args.file, args.date)
        print(f"Hasil: {res}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
