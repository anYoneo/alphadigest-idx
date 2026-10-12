import os
import re
import sys
import argparse
from datetime import datetime
from curl_cffi import requests

# Base URL for IDX API
BASE_URL = "https://www.idx.co.id/primary/ListedCompany/GetAnnouncement"

# Request headers for bypassing bot detection
# Note: Do not hardcode a conflicting User-Agent; let curl_cffi send the UA matching the impersonated TLS profile.
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.idx.co.id/id/berita/pengumuman/",
    "Origin": "https://www.idx.co.id"
}

def clean_filename(filename):
    """Remove invalid characters from filename to make it safe for OS."""
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()

# Define whitelisted categories of announcements (Case-Insensitive)
WHITELIST_REGEX = re.compile(
    r"laporan keuangan|financial statement|financial report|lkp|"
    r"laporan\s?tahunan|annual\s(.*\s)?report|"
    r"dividen|dividend|"
    r"pmhmetd|pmthmetd|right issue|private placement|"
    r"buyback|buy\s?back|pembelian kembali|"
    r"rups|gms|rapat umum pemegang saham|rapat umum pemegang obligasi|general meeting|"
    r"merger|penggabungan|akuisisi|acquisition|"
    r"transaksi material|material transaction|transaksi afiliasi|affiliated transaction|"
    r"fakta material|keterbukaan informasi|information disclosure|benturan kepentingan|conflict of interest|"
    r"stock split|reverse split|pecahan saham|"
    r"aksi korporasi|corporate action",
    re.IGNORECASE
)

# Define blacklisted categories (Case-Insensitive)
BLACKLIST_REGEX = re.compile(
    r"laporan bulanan registrasi|registrasi pemegang|securities holders registration|"
    r"shareholders registration|perubahan struktur pemegang saham|peredaran unit|"
    r"nilai aktiva bersih|net asset value|portfolio composition|liquidity provider|"
    r"bukti iklan|advertisement submission|structured warrant|waran terstruktur|"
    r"penyesuaian waran|pelaksanaan waran terstruktur|jumlah waran terstruktur",
    re.IGNORECASE
)


def get_file_md5(file_path):
    """Calculate MD5 hash of a file to check for duplicate content."""
    import hashlib
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None

def download_file(url, output_path, existing_hashes, max_retries=3):
    """Download a file, check for MD5 duplicate, and save if unique."""
    import time
    pdf_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.idx.co.id/id/berita/pengumuman/",
    }
    for attempt in range(1, max_retries + 1):
        try:
            r = None
            for imp in ["chrome124", "chrome119", "chrome"]:
                try:
                    r = requests.get(url, headers=pdf_headers, impersonate=imp, timeout=25)
                    if r.status_code == 200:
                        break
                except Exception:
                    continue

            if r is not None and r.status_code == 200:
                import hashlib
                content_hash = hashlib.md5(r.content).hexdigest()
                if content_hash in existing_hashes:
                    print(f"        [~] Skipped duplicate PDF content (same as: {existing_hashes[content_hash]})")
                    return "DUPLICATE"
                
                with open(output_path, 'wb') as f:
                    f.write(r.content)
                # Add to local cache map so we don't download it again in this run
                existing_hashes[content_hash] = os.path.basename(output_path)
                return True
            else:
                status_code = r.status_code if r is not None else "No response"
                if attempt < max_retries:
                    time.sleep(2 * attempt)
                    continue
                print(f"  [-] Failed to download PDF. Status code: {status_code}")
                return False
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2 * attempt)
                continue
    return False


def crawl_idx_playwright(emiten, page_size, output_dir, keyword, days_back=1):
    """
    Playwright Stealth fallback scraper.
    Activated when Cloudflare WAF returns 403 on curl_cffi requests.
    Uses Chromium/Edge in headless stealth mode to bypass Cloudflare Managed Challenges.
    """
    import time
    import base64
    import hashlib
    from datetime import timedelta

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[-] Playwright is not installed. Cannot execute stealth fallback.")
        return {
            "success": False,
            "total_on_idx": 0,
            "retrieved": 0,
            "downloaded": 0,
            "error": "Playwright not installed"
        }

    print("\n" + "=" * 60)
    print("[*] Starting IDX Scraper via Playwright Stealth Fallback")
    print(f"Emiten: {emiten} | Keyword: {keyword or 'None'} | Days Back: {days_back}")

    print(f"Output Directory: {output_dir}")
    print("=" * 60)

    os.makedirs(output_dir, exist_ok=True)

    now_dt = datetime.now()
    date_from_str = (now_dt - timedelta(days=days_back)).strftime("%Y%m%d")
    today_str = now_dt.strftime("%Y%m%d")
    max_seconds = (days_back * 86400) + 14400

    all_replies = []
    total_count = 0
    download_count = 0
    crawl_success = True
    crawl_error = None

    try:
        with sync_playwright() as p:
            browser = None
            for ch in ['msedge', 'chrome', None]:
                try:
                    browser = p.chromium.launch(
                        headless=True,
                        channel=ch,
                        args=['--disable-blink-features=AutomationControlled']
                    )
                    break
                except Exception:
                    continue

            if not browser:
                print("[-] Failed to launch Playwright browser.")
                return {
                    "success": False,
                    "total_on_idx": 0,
                    "retrieved": 0,
                    "downloaded": 0,
                    "error": "Failed to launch browser"
                }

            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                locale='id-ID'
            )
            page = context.new_page()

            # Navigate to base page to establish session/cookies and solve CF challenges
            print("[*] Navigating to IDX announcements page...")
            for nav_att in range(3):
                try:
                    page.goto('https://www.idx.co.id/id/berita/pengumuman/', timeout=45000)
                    page.wait_for_timeout(2000)
                    break
                except Exception as ne:
                    if nav_att == 2:
                        raise ne
                    time.sleep(2)

            page_no = 1
            batch_size = 100

            while True:
                api_url = (
                    f"https://www.idx.co.id/primary/ListedCompany/GetAnnouncement?"
                    f"indexFrom={page_no}&pageSize={batch_size}&dateFrom={date_from_str}&dateTo={today_str}"
                    f"&lang=id&emitenType=*&kodeEmiten={'' if emiten.upper() in ['', 'ALL', '*'] else emiten.upper()}"
                )

                res = page.evaluate('''async (url) => {
                    try {
                        const r = await fetch(url);
                        if (r.status !== 200) return { error: `HTTP ${r.status}` };
                        return await r.json();
                    } catch (e) {
                        return { error: String(e) };
                    }
                }''', api_url)

                if not res or "error" in res:
                    err_msg = res.get("error") if res else "No response"
                    print(f"[-] Error fetching page {page_no} via Playwright: {err_msg}")
                    if page_no == 1:
                        crawl_success = False
                        crawl_error = err_msg
                    break

                replies = res.get("Replies", [])
                total_count = res.get("ResultCount", 0)

                if not replies:
                    break

                all_replies.extend(replies)
                print(f"[+] Fetched {len(all_replies)} / {total_count} announcements...")

                if len(all_replies) >= total_count or len(replies) < batch_size:
                    break

                page_no += 1

            print(f"[+] Total announcements retrieved via Playwright: {len(all_replies)} (Total on IDX: {total_count})")

            # Attachment downloading
            emiten_hashes = {}
            for idx, entry in enumerate(all_replies):
                p_data = entry.get("pengumuman", {})
                title = p_data.get("JudulPengumuman", "").strip()
                date_str = p_data.get("TglPengumuman", "")
                code = p_data.get("Kode_Emiten", "").strip().upper()
                attachments = entry.get("attachments", [])

                if not code or not re.match(r"^[A-Z]{4}$", code) or code.startswith("X"):
                    continue

                try:
                    date_parsed = datetime.fromisoformat(date_str.replace("Z", ""))
                    if (now_dt - date_parsed).total_seconds() > max_seconds:
                        continue
                    date_prefix = date_parsed.strftime("%Y%m%d")
                except Exception:
                    date_prefix = "unknown_date"

                if BLACKLIST_REGEX.search(title):
                    continue

                if keyword and not WHITELIST_REGEX.search(title):
                    continue

                if not attachments:
                    continue

                for att in attachments:
                    pdf_url = att.get("FullSavePath", "").strip()
                    orig_name = att.get("OriginalFilename", "").strip()
                    pdf_filename = att.get("PDFFilename", "").strip()

                    if not pdf_url:
                        continue

                    is_valid_att = (
                        pdf_url.lower().endswith(".pdf") or orig_name.lower().endswith(".pdf") or pdf_filename.lower().endswith(".pdf") or
                        pdf_url.lower().endswith(".xlsx") or orig_name.lower().endswith(".xlsx") or pdf_filename.lower().endswith(".xlsx")
                    )
                    if not is_valid_att:
                        continue

                    if not orig_name:
                        orig_name = pdf_filename or ("document.xlsx" if pdf_url.lower().endswith(".xlsx") else "document.pdf")

                    safe_orig_name = clean_filename(orig_name)
                    final_filename = f"{date_prefix}_{code}_{safe_orig_name}"

                    if orig_name.lower().endswith(".xlsx") and not final_filename.lower().endswith(".xlsx"):
                        final_filename += ".xlsx"
                    elif not (final_filename.lower().endswith(".pdf") or final_filename.lower().endswith(".xlsx")):
                        final_filename += ".pdf"

                    emiten_code = code.upper() if code else (emiten.upper() if emiten else "GENERAL")
                    emiten_dir = os.path.join(output_dir, emiten_code)
                    os.makedirs(emiten_dir, exist_ok=True)

                    if emiten_code not in emiten_hashes:
                        emiten_hashes[emiten_code] = {}
                        if os.path.exists(emiten_dir):
                            for existing_file in os.listdir(emiten_dir):
                                if existing_file.lower().endswith(".pdf") or existing_file.lower().endswith(".xlsx"):
                                    fp = os.path.join(emiten_dir, existing_file)
                                    file_hash = get_file_md5(fp)
                                    if file_hash:
                                        emiten_hashes[emiten_code][file_hash] = existing_file

                    dest_path = os.path.join(emiten_dir, final_filename)

                    if os.path.exists(dest_path):
                        continue

                    print(f"    [+] Downloading via Playwright: {emiten_code}/{final_filename}")
                    b64 = page.evaluate('''async (url) => {
                        try {
                            const r = await fetch(url);
                            if (r.status !== 200) return null;
                            const blob = await r.blob();
                            return new Promise((resolve) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                                reader.readAsDataURL(blob);
                            });
                        } catch(e) {
                            return null;
                        }
                    }''', pdf_url)

                    if b64:
                        content = base64.b64decode(b64)
                        content_hash = hashlib.md5(content).hexdigest()
                        if content_hash in emiten_hashes[emiten_code]:
                            print(f"        [~] Skipped duplicate PDF content (same as: {emiten_hashes[emiten_code][content_hash]})")
                            continue

                        with open(dest_path, 'wb') as f:
                            f.write(content)
                        emiten_hashes[emiten_code][content_hash] = os.path.basename(dest_path)
                        download_count += 1
                        print(f"        Saved to: {dest_path}")
                    else:
                        print(f"  [-] Failed to download file via Playwright: {pdf_url}")

            browser.close()

    except Exception as pe:
        print(f"[-] Playwright crawling error: {pe}")
        crawl_success = False
        crawl_error = str(pe)

    print(f"\n[OK] Playwright crawl finished. Successfully downloaded {download_count} new files.")
    return {
        "success": crawl_success,
        "total_on_idx": total_count,
        "retrieved": len(all_replies),
        "downloaded": download_count,
        "error": crawl_error
    }


def crawl_idx(emiten, page_size, output_dir, keyword, days_back=1):
    import time

    print("=" * 60)
    print(f"Starting IDX Scraper for Emiten: {emiten}")
    print(f"Page Size: {page_size} | Keyword: {keyword or 'None'} | Days Back: {days_back}")
    print(f"Output Directory: {output_dir}")
    print("=" * 60)

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Setup API params for specified rolling window
    from datetime import timedelta
    now_dt = datetime.now()
    date_from_str = (now_dt - timedelta(days=days_back)).strftime("%Y%m%d")
    today_str = now_dt.strftime("%Y%m%d")
    max_seconds = (days_back * 86400) + 14400  # Add 4h buffer

    all_replies = []
    page_no = 1
    batch_size = 100
    total_count = 0

    crawl_success = True
    crawl_error = None

    while True:
        params = {
            "indexFrom": page_no,
            "pageSize": batch_size,
            "dateFrom": date_from_str,
            "dateTo": today_str,
            "lang": "id",
            "keyword": keyword or "",
            "emitenType": "*",
            "kodeEmiten": "" if emiten.upper() in ["", "ALL", "*"] else emiten.upper()
        }

        r = None
        max_page_retries = 4
        for attempt in range(1, max_page_retries + 1):
            for imp in ["chrome124", "chrome119", "chrome"]:
                try:
                    r = requests.get(BASE_URL, params=params, headers=HEADERS, impersonate=imp, timeout=25)
                    if r.status_code == 200:
                        break
                except Exception:
                    continue

            if r is not None and r.status_code == 200:
                break
            
            status_str = r.status_code if r is not None else "No response"
            if attempt < max_page_retries:
                print(f"  [!] Fetch attempt {attempt} for page {page_no} returned {status_str}. Retrying in {3 * attempt}s...")
                time.sleep(3 * attempt)

        if r is None or r.status_code != 200:
            status_str = r.status_code if r is not None else "No response"
            print(f"[-] Failed to fetch from IDX at page {page_no} after {max_page_retries} attempts. Status code: {status_str}")
            if page_no == 1:
                crawl_success = False
                crawl_error = f"HTTP {status_str}"
                if r is not None and r.status_code == 403:
                    print("  [!] Cloudflare WAF 403 detected on curl_cffi. Switching to Playwright Stealth fallback...")
                    return crawl_idx_playwright(emiten, page_size, output_dir, keyword, days_back=days_back)
            break

        data = r.json()
        replies = data.get("Replies", [])
        total_count = data.get("ResultCount", 0)

        if not replies:
            break

        all_replies.extend(replies)
        print(f"[+] Fetched {len(all_replies)} / {total_count} announcements...")

        if len(all_replies) >= total_count or len(replies) < batch_size:
            break

        page_no += 1

    print(f"[+] Total announcements retrieved: {len(all_replies)} (Total on IDX: {total_count})")
    
    download_count = 0
    emiten_hashes = {}

    now_dt = datetime.now()
    for idx, entry in enumerate(all_replies):
        p = entry.get("pengumuman", {})
        title = p.get("JudulPengumuman", "").strip()
        date_str = p.get("TglPengumuman", "")
        code = p.get("Kode_Emiten", "").strip().upper()
        attachments = entry.get("attachments", [])

        # Skip ETF / Mutual Fund tickers starting with 'X' or non-stock codes
        # Strict IDX Equity Filter: Valid Indonesian stock tickers MUST be exactly 4 alphabetic letters (A-Z)
        # Filters out 2-letter broker/warrant issuer codes (ZP, DR, HD, YU, BQ, CC, PD, dll.),
        # Structured warrants, ETFs, Bonds/Sukuk (BJLB01, MGIA01), and non-equity tags (ALL, MARGIN, INDEKS)
        if not code or not re.match(r"^[A-Z]{4}$", code) or code.startswith("X"):
            continue

        # Check publication date timestamp (window cutoff)
        try:
            date_parsed = datetime.fromisoformat(date_str.replace("Z", ""))
            if (now_dt - date_parsed).total_seconds() > max_seconds:
                continue
            date_prefix = date_parsed.strftime("%Y%m%d")
        except Exception:
            date_prefix = "unknown_date"

        # Blacklist check: Skip junk/spam/structured warrants
        if BLACKLIST_REGEX.search(title):
            continue

        # Whitelist check: If a specific keyword is provided
        if keyword and not WHITELIST_REGEX.search(title):
            continue


        print(f"\n[{idx + 1}] Date: {date_str} | Ticker: {code}")
        print(f"    Title: {title}")

        if not attachments:
            print("    [-] No attachments found.")
            continue

        for att in attachments:
            pdf_url = att.get("FullSavePath", "").strip()
            orig_name = att.get("OriginalFilename", "").strip()
            pdf_filename = att.get("PDFFilename", "").strip()

            if not pdf_url:
                continue

            # Ensure it is a PDF or XLSX file
            is_valid_att = (
                pdf_url.lower().endswith(".pdf") or orig_name.lower().endswith(".pdf") or pdf_filename.lower().endswith(".pdf") or
                pdf_url.lower().endswith(".xlsx") or orig_name.lower().endswith(".xlsx") or pdf_filename.lower().endswith(".xlsx")
            )
            if not is_valid_att:
                print(f"    [-] Skipped unsupported attachment: {orig_name or pdf_filename}")
                continue

            # Fallback filename if original name is empty
            if not orig_name:
                orig_name = pdf_filename or ("document.xlsx" if pdf_url.lower().endswith(".xlsx") else "document.pdf")

            # Standardize name: YYYYMMDD_[Emiten]_[OriginalFilename]
            safe_orig_name = clean_filename(orig_name)
            final_filename = f"{date_prefix}_{code}_{safe_orig_name}"
            
            # Ensure correct extension
            if orig_name.lower().endswith(".xlsx") and not final_filename.lower().endswith(".xlsx"):
                final_filename += ".xlsx"
            elif not (final_filename.lower().endswith(".pdf") or final_filename.lower().endswith(".xlsx")):
                final_filename += ".pdf"

            # Define emiten subfolder to keep files organized
            emiten_code = code.upper() if code else (emiten.upper() if emiten else "GENERAL")
            emiten_dir = os.path.join(output_dir, emiten_code)
            os.makedirs(emiten_dir, exist_ok=True)

            # Initialize existing hashes for this emiten if not already done
            if emiten_code not in emiten_hashes:
                emiten_hashes[emiten_code] = {}
                if os.path.exists(emiten_dir):
                    for existing_file in os.listdir(emiten_dir):
                        if existing_file.lower().endswith(".pdf") or existing_file.lower().endswith(".xlsx"):
                            fp = os.path.join(emiten_dir, existing_file)
                            file_hash = get_file_md5(fp)
                            if file_hash:
                                emiten_hashes[emiten_code][file_hash] = existing_file

            dest_path = os.path.join(emiten_dir, final_filename)

            if os.path.exists(dest_path):
                print(f"    [~] Already exists: {emiten_code}/{final_filename}")
                continue

            print(f"    [+] Downloading: {orig_name}")
            print(f"        URL: {pdf_url}")
            
            success = download_file(pdf_url, dest_path, emiten_hashes[emiten_code])
            if success is True:
                print(f"        Saved to: {dest_path}")
                download_count += 1
    
    print(f"\n[OK] Crawl finished. Successfully downloaded {download_count} new files.")
    return {
        "success": crawl_success,
        "total_on_idx": total_count,
        "retrieved": len(all_replies),
        "downloaded": download_count,
        "error": crawl_error
    }

def headers_to_dict(headers):
    # Standard utility to make headers format clean
    return headers

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IDX Keterbukaan Informasi PDF Downloader")
    parser.add_argument("--emiten", type=str, required=True, help="Emiten ticker code (e.g. BBRI, TLKM)")
    parser.add_argument("--pagesize", type=int, default=10, help="Number of announcements to scan (default: 10)")
    parser.add_argument("--output-dir", type=str, default="g:\\My Drive\\Model2\\reports\\raw", help="Output folder")
    parser.add_argument("--keyword", type=str, default="", help="Keyword filter for titles")
    parser.add_argument("--days-back", type=int, default=1, help="Number of days to scan back (default: 1)")

    args = parser.parse_args()
    crawl_idx(args.emiten, args.pagesize, args.output_dir, args.keyword, days_back=args.days_back)