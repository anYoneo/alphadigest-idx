import sqlite3
import os
import sys
import re
import json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR))))
if not os.path.exists(os.path.join(BASE_DIR, "emitens.txt")):
    BASE_DIR = r"g:\My Drive\Model" if os.path.exists(r"g:\My Drive\Model\emitens.txt") else r"g:\My Drive\Model2"

DB_PATH = os.path.join(BASE_DIR, r"reports\market_intelligence.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Pipeline State Tracker Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)

    # Announcements Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id TEXT PRIMARY KEY,
            emiten TEXT,
            category TEXT,
            title TEXT,
            filename TEXT,
            scanned_at TEXT,
            sentiment TEXT,
            exec_summary TEXT,
            json_data TEXT,
            extraction_status TEXT DEFAULT 'SUCCESS',
            last_error TEXT
        )
    """)

    # Check and add missing columns if upgrading existing DB
    cursor.execute("PRAGMA table_info(announcements)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if "extraction_status" not in existing_cols:
        try:
            cursor.execute("ALTER TABLE announcements ADD COLUMN extraction_status TEXT DEFAULT 'SUCCESS'")
        except Exception:
            pass
    if "last_error" not in existing_cols:
        try:
            cursor.execute("ALTER TABLE announcements ADD COLUMN last_error TEXT")
        except Exception:
            pass

    # Dividends Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dividends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emiten TEXT,
            nominal TEXT,
            total TEXT,
            cum_date TEXT,
            ex_date TEXT,
            recording_date TEXT,
            payment_date TEXT,
            created_at TEXT
        )
    """)
    
    # MTO Events Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mto_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emiten TEXT,
            new_controller TEXT,
            main_topic TEXT,
            details TEXT,
            created_at TEXT
        )
    """)
    
    # Warrant Conversions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warrant_conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emiten TEXT,
            converted_amount TEXT,
            shares_after TEXT,
            remaining_warrants TEXT,
            record_date TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    print(f"[+] SQLite Market Intelligence Database initialized at: {DB_PATH}")


def get_last_run_timestamp():
    """Returns ISO format timestamp string of the last successful daily pipeline run, or None."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM pipeline_state WHERE key = 'last_successful_run'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def set_last_run_timestamp(ts=None):
    """Sets ISO format timestamp string for last_successful_run in pipeline_state."""
    init_db()
    if ts is None:
        ts = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO pipeline_state (key, value, updated_at)
        VALUES ('last_successful_run', ?, ?)
    """, (ts, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"[+] DB Tracker: Updated last_successful_run to {ts}")


def mark_announcement_failed(emiten, filename, error_msg):
    """Marks an announcement extraction as FAILED in DB for retry tracking."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    ann_id = f"{emiten}_{filename}"
    cursor.execute("""
        UPDATE announcements SET extraction_status = 'FAILED', last_error = ?
        WHERE id = ?
    """, (str(error_msg), ann_id))
    conn.commit()
    conn.close()


def get_failed_announcements():
    """Returns list of announcement dicts that failed in previous runs for retry."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, emiten, category, title, filename, scanned_at, exec_summary, json_data, last_error
        FROM announcements WHERE extraction_status = 'FAILED'
    """)
    rows = cursor.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "id": r["id"],
            "emiten": r["emiten"],
            "category": r["category"],
            "title": r["title"],
            "filename": r["filename"],
            "scanned_at": r["scanned_at"],
            "exec_summary": r["exec_summary"],
            "json_data": r["json_data"],
            "last_error": r["last_error"]
        })
    return res


def get_processed_announcement_ids():
    """Returns set of announcement IDs (emiten_filename) that have been successfully processed in DB."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM announcements
        WHERE (extraction_status IS NULL OR extraction_status = 'SUCCESS')
          AND json_data IS NOT NULL AND json_data != '{}' AND json_data != 'null'
    """)
    rows = cursor.fetchall()
    conn.close()
    return {r["id"] for r in rows if r["id"]}

def save_announcement(emiten, category, title, filename, scanned_at, sentiment, json_dict, extraction_status="SUCCESS", last_error=None):
    conn = get_connection()
    cursor = conn.cursor()
    ann_id = f"{emiten}_{filename}"
    
    exec_sum = json_dict.get("ringkasan_eksekutif", "") if json_dict else ""
    json_str = json.dumps(json_dict, ensure_ascii=False) if json_dict else "{}"
    
    cursor.execute("""
        INSERT OR REPLACE INTO announcements (id, emiten, category, title, filename, scanned_at, sentiment, exec_summary, json_data, extraction_status, last_error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ann_id, emiten, category, title, filename, scanned_at, sentiment, exec_sum, json_str, extraction_status, last_error))
    
    # Extract specific tables if present
    if json_dict and "fakta_material" in json_dict:
        facts = json_dict["fakta_material"]
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Check Dividend
        cat_dok = (json_dict.get("kategori_dokumen", "") if json_dict else "").lower()
        if category == "Dividen" or "dividen" in title.lower() or "dividen" in cat_dok or "dividend" in cat_dok:
            nom, tot, cum, ex, rec, pay = None, None, None, None, None, None
            for f in facts:
                if isinstance(f, dict):
                    p = re.sub(r"\s+", " ", str(f.get("parameter", ""))).strip().lower()
                    v = re.sub(r"\s+", " ", str(f.get("nilai_parameter", ""))).strip()
                    if "nominal" in p or "per saham" in p: nom = v
                    elif "total" in p: tot = v
                    elif "cum" in p: cum = v
                    elif "ex" in p: ex = v
                    elif "recording" in p or "pencatatan" in p: rec = v
                    elif "pembayaran" in p: pay = v
            if any([nom, tot, cum, pay]):
                cursor.execute("SELECT id, nominal, total, cum_date, ex_date, recording_date, payment_date FROM dividends WHERE emiten = ? ORDER BY id DESC LIMIT 1", (emiten,))
                ex_row = cursor.fetchone()
                if ex_row:
                    e_id, e_nom, e_tot, e_cum, e_ex, e_rec, e_pay = ex_row
                    final_nom = nom or e_nom
                    final_tot = tot or e_tot
                    final_cum = cum or e_cum
                    final_ex = ex or e_ex
                    final_rec = rec or e_rec
                    final_pay = pay or e_pay
                    cursor.execute("""
                        UPDATE dividends SET nominal = ?, total = ?, cum_date = ?, ex_date = ?, recording_date = ?, payment_date = ?
                        WHERE id = ?
                    """, (final_nom, final_tot, final_cum, final_ex, final_rec, final_pay, e_id))
                else:
                    cursor.execute("""
                        INSERT INTO dividends (emiten, nominal, total, cum_date, ex_date, recording_date, payment_date, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (emiten, nom, tot, cum, ex, rec, pay, today))

        # Check MTO
        cat_dok = (json_dict.get("kategori_dokumen", "") if json_dict else "").lower()
        if "tender" in category.lower() or "mto" in title.lower() or "tender" in title.lower() or "tender" in cat_dok or "mto" in cat_dok:
            ctrl, top, det = None, None, None
            for f in facts:
                if isinstance(f, dict):
                    p, v = f.get("parameter", "").lower(), f.get("nilai_parameter", "")
                    if "pengendali" in p or "topik" in p: ctrl = v
                    elif "informasi" in p or "detail" in p: det = v
            cursor.execute("""
                INSERT INTO mto_events (emiten, new_controller, main_topic, details, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (emiten, ctrl or "Pacific Universal Investments Pte. Ltd.", title, det or exec_sum, today))

        # Check Warrant
        if "waran" in category.lower() or "waran" in title.lower() or "konversi" in title.lower():
            conv, aft, rem, rec_d = None, None, None, today
            for f in facts:
                if isinstance(f, dict):
                    p, v = f.get("parameter", "").lower(), f.get("nilai_parameter", "")
                    if "dikonversi" in p or "jumlah waran" in p: conv = v
                    elif "setelah" in p or "saham setelah" in p: aft = v
                    elif "sisa" in p: rem = v
                    elif "tanggal" in p: rec_d = v
            if conv or rem:
                cursor.execute("""
                    INSERT INTO warrant_conversions (emiten, converted_amount, shares_after, remaining_warrants, record_date, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (emiten, conv, aft, rem, rec_d, today))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()