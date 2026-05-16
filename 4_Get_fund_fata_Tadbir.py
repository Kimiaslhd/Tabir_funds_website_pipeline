import requests
import pyodbc
import time
import sys
import urllib3
import re
import traceback
import html
from urllib.parse import quote

try:
    import jdatetime
except ImportError:
    print("=" * 100)
    print("ERROR: jdatetime package is not installed!")
    print("Install it with: pip install jdatetime")
    print("=" * 100)
    input("Press Enter to exit...")
    sys.exit(1)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONNECT_TIMEOUT = 8
READ_TIMEOUT = 15
PAGE_DELAY = 0.2
MAX_PAGES_NORMAL = 40
MAX_PAGES_SPECIAL = 80
MAX_CONSECUTIVE_FAILS = 5

# =========================================================
# MAIN
# =========================================================
def main():
    try:
        print("=" * 100)
        print("FUNDS NAV TADBIR IMPORT SCRIPT - ENHANCED VERSION")
        print("=" * 100)

        server = "........."
        database = "......."
        username = "......."
        password = "........"

        print("\nPlease enter dates in Jalali format (YYYY/MM/DD):")
        start_date_jalali_str = get_valid_jalali_date("Enter start date (e.g., 1404/10/01): ")
        end_date_jalali_str = get_valid_jalali_date("Enter end date (e.g., 1405/02/11): ")

        if start_date_jalali_str > end_date_jalali_str:
            print("Error: Start date cannot be after end date.")
            input("Press Enter to exit...")
            return

        print("\nConnecting to database...")
        conn = connect_to_database(server, database, username, password)
        if not conn:
            print("Failed to connect to database.")
            input("Press Enter to exit...")
            return

        print("Connected to database successfully!")

        funds = get_tadbir_funds(conn)
        total_funds = len(funds)
        print(f"\nFound {total_funds} Tadbir funds to process.")

        total_inserted = 0
        total_updated = 0
        success_count = 0
        failed_funds = []
        bad_domains = set()

        for i, fund in enumerate(funds, 1):
            dscode = str(fund[0]).strip() if fund[0] is not None else ""
            fund_name = str(fund[1]).strip() if fund[1] is not None else ""
            fund_type = safe_convert_to_int(fund[2])
            nav_url = str(fund[3]).strip() if fund[3] is not None else ""

            print("\n" + "=" * 100)
            print(f"FUND {i}/{total_funds}")
            print(f"Dscode    : {dscode}")
            print(f"FundName  : {fund_name}")
            print(f"FundType  : {fund_type}")
            print(f"NAV_URL   : {nav_url}")

            if not dscode or not nav_url:
                failed_funds.append({
                    "Dscode": dscode,
                    "FundName": fund_name,
                    "FundType": fund_type,
                    "NAV_URL": nav_url,
                    "Reason": "Missing Dscode or NAV_URL"
                })
                continue

            site_root = build_site_root(nav_url)
            domain_key = extract_domain_key(site_root)

            if domain_key in bad_domains:
                print(f"Skipping bad domain already failed before: {domain_key}")
                continue

            basket_ids_to_try = get_tadbir_basket_ids_by_fund_type(fund_type)

            print(f"SiteRoot       : {site_root}")
            print(f"BasketIdsToTry : {basket_ids_to_try}")

            data, debug_info = fetch_data_tadbir_light(
                site_root=site_root,
                fund_type=fund_type,
                basket_ids_to_try=basket_ids_to_try,
                start_date_jalali_str=start_date_jalali_str,
                end_date_jalali_str=end_date_jalali_str
            )

            print("\nDEBUG SUMMARY")
            print(f"Detected basket ids  : {debug_info.get('detected_basket_ids')}")
            print(f"Requested basket ids : {debug_info.get('requested_basket_ids')}")
            print(f"Working basket ids   : {debug_info.get('working_basket_ids')}")
            print(f"Initial status       : {debug_info.get('first_page_status')}")
            print(f"Failure reason       : {debug_info.get('failure_reason')}")

            if debug_info.get("domain_failed"):
                bad_domains.add(domain_key)

            if not data:
                print("No data found for this fund in requested range.")
                failed_funds.append({
                    "Dscode": dscode,
                    "FundName": fund_name,
                    "FundType": fund_type,
                    "NAV_URL": nav_url,
                    "SiteRoot": site_root,
                    "Reason": debug_info.get("failure_reason", "Unknown")
                })
                continue

            inserted_count, updated_count, gathered_dates = insert_data_into_database(
                conn=conn,
                dscode=dscode,
                fund_name=fund_name,
                data=data,
                start_date_jalali_str=start_date_jalali_str,
                end_date_jalali_str=end_date_jalali_str
            )

            total_inserted += inserted_count
            total_updated += updated_count
            success_count += 1

            print("\nFUND RESULT")
            print(f"Dscode        : {dscode}")
            print(f"Rows gathered : {len(data)}")
            print(f"Unique dates  : {len(gathered_dates)}")
            if gathered_dates:
                print(f"Min date      : {min(gathered_dates)}")
                print(f"Max date      : {max(gathered_dates)}")
            print(f"Inserted      : {inserted_count}")
            print(f"Updated       : {updated_count}")

            if i < total_funds:
                time.sleep(0.3)

        conn.close()

        print("\n" + "=" * 100)
        print("FINAL SUMMARY")
        print(f"Total funds processed : {total_funds}")
        print(f"Successful funds      : {success_count}")
        print(f"Failed funds          : {len(failed_funds)}")
        print(f"Total inserted rows   : {total_inserted}")
        print(f"Total updated rows    : {total_updated}")
        print("=" * 100)

    except Exception as e:
        print("\n" + "=" * 100)
        print(f"UNEXPECTED ERROR: {str(e)}")
        print("=" * 100)
        traceback.print_exc()

    print("\nPress Enter to exit...")
    input()

# =========================================================
# INPUT / DB
# =========================================================
def get_valid_jalali_date(prompt):
    while True:
        date_str = input(prompt).strip()
        if not re.match(r'^\d{4}/\d{2}/\d{2}$', date_str):
            print("Error: Date must be in YYYY/MM/DD format.")
            continue
        try:
            year, month, day = map(int, date_str.split('/'))
            jdatetime.date(year, month, day)
            return date_str
        except ValueError as e:
            print(f"Invalid Jalali date: {e}")

def safe_convert_to_int(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except:
        return None

def parse_number(value):
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    value = value.replace(",", "").replace("−", "-").replace("–", "-")
    try:
        if "." in value:
            return float(value)
        return int(value)
    except:
        return None

def connect_to_database(server, database, username, password):
    try:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};DATABASE={database};UID={username};PWD={password}"
        )
        return pyodbc.connect(conn_str)
    except pyodbc.Error as e:
        print(f"Database connection error: {e}")
        return None

def get_tadbir_funds(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT Dscode, fundName, FundType, NAV_URL
            FROM [dbo].[FundsNav_NavUrls]
            WHERE website_Type LIKE '%Tadbir%'
              AND NAV_URL IS NOT NULL
              AND LTRIM(RTRIM(NAV_URL)) <> ''
            ORDER BY fundName
        """)
        rows = cursor.fetchall()
        cursor.close()
        return rows
    except pyodbc.Error as e:
        print(f"Error fetching Tadbir funds: {e}")
        return []

def get_tadbir_basket_ids_by_fund_type(fund_type):
    if fund_type in (111, 211):
        return [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    return [0]

# =========================================================
# URL / SESSION
# =========================================================
def build_site_root(nav_url):
    url = str(nav_url).strip()

    url = url.replace("https://http://", "https://")
    url = url.replace("https://https://", "https://")
    url = url.replace("http://http://", "http://")

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    url = re.sub(r"^http://", "https://", url)
    url = url.rstrip("/")

    if "/Reports/" in url:
        url = url.split("/Reports/")[0]

    return url

def extract_domain_key(site_root):
    x = site_root.lower().strip()
    x = x.replace("https://", "").replace("http://", "")
    x = x.split("/")[0]
    return x

def create_session():
    session = requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
        "Connection": "keep-alive"
    })
    return session

def build_fundnavlist_url(site_root, from_date, to_date, basket_id, page):
    return (
        f"{site_root}/Reports/FundNAVList"
        f"?FromDate={quote(from_date, safe='')}"
        f"&ToDate={quote(to_date, safe='')}"
        f"&BasketId={basket_id}"
        f"&page={page}"
    )

# =========================================================
# HTML HELPERS
# =========================================================
def clean_text(text):
    text = html.unescape(str(text))
    text = re.sub(r"<script.*?>.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?>.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<.*?>", "", text, flags=re.S)
    text = text.replace("\u200c", " ")
    text = text.replace("\xa0", " ")
    text = text.replace("&nbsp;", " ")
    return text.strip()

def extract_tables(html_text):
    return re.findall(r"<table[^>]*>.*?</table>", html_text, flags=re.S | re.I)

def extract_headers_from_table(table_html):
    thead_match = re.search(r"<thead[^>]*>(.*?)</thead>", table_html, flags=re.S | re.I)
    source = thead_match.group(1) if thead_match else table_html

    ths = re.findall(r"<th[^>]*>(.*?)</th>", source, flags=re.S | re.I)
    if ths:
        return [clean_text(x) for x in ths if clean_text(x)]

    first_tr_match = re.search(r"<tr[^>]*>(.*?)</tr>", source, flags=re.S | re.I)
    if first_tr_match:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", first_tr_match.group(1), flags=re.S | re.I)
        return [clean_text(x) for x in cells if clean_text(x)]

    return []

def extract_rows_from_table(table_html):
    body_match = re.search(r"<tbody[^>]*>(.*?)</tbody>", table_html, flags=re.S | re.I)
    body_html = body_match.group(1) if body_match else table_html

    tr_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", body_html, flags=re.S | re.I)
    rows = []

    for tr in tr_matches:
        td_matches = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)
        if not td_matches:
            continue
        row = [clean_text(td) for td in td_matches]
        if any(x != "" for x in row):
            rows.append(row)

    return rows

def normalize_header_name(h):
    x = clean_text(h)
    x = x.replace("ي", "ی").replace("ك", "ک")
    x = x.replace("‌", " ")
    x = re.sub(r"\s+", " ", x).strip()
    return x

def score_nav_table(headers, rows):
    if not headers:
        return 0

    headers_norm = [normalize_header_name(h) for h in headers]
    joined = " | ".join(headers_norm)

    score = 0
    for t in ["تاریخ", "صدور", "ابطال", "واحد", "خالص ارزش", "اسمی"]:
        if t in joined:
            score += 1

    if len(headers_norm) >= 8:
        score += 1
    if len(rows) >= 1:
        score += 1

    return score

def find_best_nav_table(html_text):
    tables = extract_tables(html_text)
    best_headers = []
    best_rows = []
    best_score = -1

    for table_html in tables:
        headers = extract_headers_from_table(table_html)
        rows = extract_rows_from_table(table_html)
        score = score_nav_table(headers, rows)

        if score > best_score:
            best_score = score
            best_headers = headers
            best_rows = rows

    return best_headers, best_rows, best_score

def extract_basket_ids(html_text):
    basket_ids = []

    select_match = re.search(
        r'<select[^>]*id=["\']basketId["\'][^>]*>(.*?)</select>',
        html_text,
        flags=re.S | re.I
    )

    if select_match:
        select_html = select_match.group(1)
        options = re.findall(r'<option[^>]*value=["\']([^"\']+)["\']', select_html, flags=re.S | re.I)
        for opt in options:
            opt = clean_text(opt)
            if re.match(r"^\d+$", opt):
                basket_ids.append(int(opt))

    if 0 not in basket_ids:
        basket_ids.insert(0, 0)

    result = []
    seen = set()
    for x in basket_ids:
        if x not in seen:
            seen.add(x)
            result.append(x)

    return result

def extract_hidden_inputs(html_text):
    hidden_data = {}
    inputs = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', html_text, flags=re.S | re.I)

    for inp in inputs:
        name_match = re.search(r'name=["\']([^"\']+)["\']', inp, flags=re.I)
        value_match = re.search(r'value=["\']([^"\']*)["\']', inp, flags=re.I)

        if name_match:
            name = name_match.group(1)
            value = value_match.group(1) if value_match else ""
            hidden_data[name] = value

    return hidden_data

# =========================================================
# ROW MAPPING
# =========================================================
def row_to_item_flexible(row, headers, basket_id):
    item = {
        "BasketId": basket_id,
        "GroupName": None,
        "JalaliDate": None,
        "SubscriptionNAV": None,
        "CancelNAV": None,
        "EsmiNAV": None,
        "NavDiff": None,
        "TotalSubscriptionUnit": None,
        "TotalSubscription": None,
        "TotalCancelUnit": None,
        "TotalCancel": None,
        "TotalUnit": None,
        "StockValueReserve": None,
        "TotalNetAssetValue": None,
        "Date": None
    }

    headers_norm = [normalize_header_name(h) for h in headers]

    for i, cell in enumerate(row):
        if i >= len(headers_norm):
            continue

        header = headers_norm[i]
        value = cell

        if "گروه" in header or "نام" in header:
            item["GroupName"] = value
        elif "تاریخ" in header:
            item["JalaliDate"] = value
        elif "صدور" in header and ("قیمت" in header or "nav" in header.lower()):
            item["SubscriptionNAV"] = parse_number(value)
        elif "ابطال" in header and ("قیمت" in header or "nav" in header.lower()):
            item["CancelNAV"] = parse_number(value)
        elif "اسمی" in header:
            item["EsmiNAV"] = parse_number(value)
        elif "اختلاف" in header or "تغییر" in header:
            item["NavDiff"] = parse_number(value)
        elif "صدور" in header and "تعداد" in header:
            item["TotalSubscriptionUnit"] = parse_number(value)
        elif "صدور" in header and ("مبلغ" in header or "ارزش" in header or "ریال" in header or "کل" in header):
            item["TotalSubscription"] = parse_number(value)
        elif "ابطال" in header and "تعداد" in header:
            item["TotalCancelUnit"] = parse_number(value)
        elif "ابطال" in header and ("مبلغ" in header or "ارزش" in header or "ریال" in header or "کل" in header):
            item["TotalCancel"] = parse_number(value)
        elif "کل" in header and "واحد" in header:
            item["TotalUnit"] = parse_number(value)
        elif ("ذخیره" in header or "سهام" in header or "آماری" in header) and ("ارزش" in header or "ریال" in header or "آماری" in header):
            item["StockValueReserve"] = parse_number(value)
        elif "خالص" in header and "ارزش" in header:
            item["TotalNetAssetValue"] = parse_number(value)

    if not item["JalaliDate"]:
        for cell in row:
            x = str(cell).strip()
            if re.match(r"^14\d{2}/\d{2}/\d{2}$", x):
                item["JalaliDate"] = x
                break

    if len(row) >= 14:
        if item["GroupName"] is None:
            item["GroupName"] = row[1]
        if item["JalaliDate"] is None:
            item["JalaliDate"] = row[2]
        if item["SubscriptionNAV"] is None:
            item["SubscriptionNAV"] = parse_number(row[3])
        if item["CancelNAV"] is None:
            item["CancelNAV"] = parse_number(row[4])
        if item["EsmiNAV"] is None:
            item["EsmiNAV"] = parse_number(row[5])
        if item["NavDiff"] is None:
            item["NavDiff"] = parse_number(row[6])
        if item["TotalSubscriptionUnit"] is None:
            item["TotalSubscriptionUnit"] = parse_number(row[7])
        if item["TotalSubscription"] is None:
            item["TotalSubscription"] = parse_number(row[8])
        if item["TotalCancelUnit"] is None:
            item["TotalCancelUnit"] = parse_number(row[9])
        if item["TotalCancel"] is None:
            item["TotalCancel"] = parse_number(row[10])
        if item["TotalUnit"] is None:
            item["TotalUnit"] = parse_number(row[11])
        if item["StockValueReserve"] is None:
            item["StockValueReserve"] = parse_number(row[12])
        if item["TotalNetAssetValue"] is None:
            item["TotalNetAssetValue"] = parse_number(row[13])

    return item

# =========================================================
# FETCHER
# =========================================================
def fetch_data_tadbir_light(site_root, fund_type, basket_ids_to_try, start_date_jalali_str, end_date_jalali_str):
    debug_info = {
        "detected_basket_ids": [],
        "requested_basket_ids": basket_ids_to_try,
        "working_basket_ids": [],
        "first_page_status": None,
        "failure_reason": None,
        "domain_failed": False
    }

    try:
        session = create_session()

        start_key = start_date_jalali_str.replace("/", "")
        end_key = end_date_jalali_str.replace("/", "")
        list_url = site_root + "/Reports/FundNAVList"

        try:
            init_resp = session.get(list_url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except Exception as e:
            debug_info["failure_reason"] = f"Initial GET failed: {str(e)}"
            debug_info["domain_failed"] = True
            return [], debug_info

        debug_info["first_page_status"] = init_resp.status_code

        if init_resp.status_code != 200:
            debug_info["failure_reason"] = f"Initial FundNAVList returned status {init_resp.status_code}"
            if init_resp.status_code >= 500:
                debug_info["domain_failed"] = True
            return [], debug_info

        debug_info["detected_basket_ids"] = extract_basket_ids(init_resp.text)
        hidden_inputs = extract_hidden_inputs(init_resp.text)

        combined_data = []
        combined_seen = set()
        working_basket_ids = []
        max_pages = MAX_PAGES_SPECIAL if fund_type in (111, 211) else MAX_PAGES_NORMAL

        for basket_id in basket_ids_to_try:
            print(f"\nTrying basket id: {basket_id}")

            post_data = dict(hidden_inputs)
            post_data["FromDate"] = start_date_jalali_str
            post_data["ToDate"] = end_date_jalali_str
            post_data["BasketId"] = str(basket_id)
            post_data["page"] = "1"

            try:
                post_resp = session.post(
                    list_url,
                    data=post_data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Origin": site_root,
                        "Referer": site_root + "/Reports/FundNAV",
                    },
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
                )
            except Exception as e:
                print(f"POST failed for basket {basket_id}: {e}")
                continue

            if post_resp.status_code != 200:
                print(f"POST status {post_resp.status_code} for basket {basket_id}")
                continue

            basket_data = []
            basket_seen = set()
            previous_html = None
            page = 1
            any_in_range_found = False
            consecutive_failures = 0

            while page <= max_pages:
                full_url = build_fundnavlist_url(site_root, start_date_jalali_str, end_date_jalali_str, basket_id, page)

                try:
                    response = session.get(full_url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
                except Exception as e:
                    consecutive_failures += 1
                    print(f"GET failed for basket {basket_id}, page {page}: {e}")
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILS:
                        print(f"Stopping basket {basket_id} after {MAX_CONSECUTIVE_FAILS} consecutive failures.")
                        break
                    page += 1
                    continue

                if response.status_code != 200:
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILS:
                        print(f"Stopping basket {basket_id} after {MAX_CONSECUTIVE_FAILS} consecutive failures.")
                        break
                    page += 1
                    continue

                html_text = response.text

                if previous_html is not None and html_text == previous_html:
                    break

                previous_html = html_text

                headers_found, rows, score = find_best_nav_table(html_text)

                if not rows:
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILS:
                        print(f"Stopping basket {basket_id} after {MAX_CONSECUTIVE_FAILS} consecutive failures.")
                        break
                    page += 1
                    continue

                consecutive_failures = 0
                page_kept = 0
                page_dates = []
                all_rows_older_than_start = True

                for row in rows:
                    item = row_to_item_flexible(row, headers_found, basket_id)
                    jalali_date = item.get("JalaliDate")

                    if not jalali_date:
                        continue

                    jdatekey = str(jalali_date).replace("/", "").strip()
                    if not re.match(r"^\d{8}$", jdatekey):
                        continue

                    page_dates.append(jdatekey)

                    if jdatekey >= start_key:
                        all_rows_older_than_start = False

                    if start_key <= jdatekey <= end_key:
                        any_in_range_found = True
                        row_key = (
                            str(basket_id) + "|" +
                            jdatekey + "|" +
                            str(item.get("SubscriptionNAV")) + "|" +
                            str(item.get("CancelNAV")) + "|" +
                            str(item.get("EsmiNAV")) + "|" +
                            str(item.get("TotalUnit")) + "|" +
                            str(item.get("TotalNetAssetValue"))
                        )

                        if row_key not in basket_seen:
                            basket_seen.add(row_key)
                            basket_data.append(item)
                            page_kept += 1

                if page_dates:
                    print(f"Basket {basket_id} | Page {page} | Min={min(page_dates)} Max={max(page_dates)} Kept={page_kept}")

                if all_rows_older_than_start:
                    break

                if page_kept == 0 and page_dates and max(page_dates) < start_key:
                    break

                page += 1
                time.sleep(PAGE_DELAY)

            if basket_data and any_in_range_found:
                working_basket_ids.append(basket_id)
                for item in basket_data:
                    combined_key = (
                        str(item.get("BasketId")) + "|" +
                        str(item.get("JalaliDate")) + "|" +
                        str(item.get("SubscriptionNAV")) + "|" +
                        str(item.get("CancelNAV")) + "|" +
                        str(item.get("EsmiNAV")) + "|" +
                        str(item.get("TotalUnit")) + "|" +
                        str(item.get("TotalNetAssetValue"))
                    )
                    if combined_key not in combined_seen:
                        combined_seen.add(combined_key)
                        combined_data.append(item)

        debug_info["working_basket_ids"] = working_basket_ids

        if combined_data:
            return combined_data, debug_info

        debug_info["failure_reason"] = "No requested basket returned rows in requested date range"
        return [], debug_info

    except Exception as e:
        debug_info["failure_reason"] = f"Exception: {str(e)}"
        traceback.print_exc()
        return [], debug_info

# =========================================================
# DB SAVE
# =========================================================
def insert_data_into_database(conn, dscode, fund_name, data, start_date_jalali_str, end_date_jalali_str):
    try:
        cursor = conn.cursor()

        start_key = start_date_jalali_str.replace("/", "")
        end_key = end_date_jalali_str.replace("/", "")

        cursor.execute("""
            SELECT funddate_key, BasketId
            FROM [dbo].[FundsNAV_Tadibr]
            WHERE DScode = ?
              AND jdatekey >= ?
              AND jdatekey <= ?
        """, (dscode, int(start_key), int(end_key)))

        existing_keys = set()
        for row in cursor.fetchall():
            existing_keys.add(f"{row[0]}|{row[1]}")

        latest_rows = {}

        for item in data:
            jalali_date = item.get("JalaliDate")
            basket_id = item.get("BasketId", 0)

            if not jalali_date:
                continue

            jdatekey = str(jalali_date).replace("/", "").strip()
            if not re.match(r"^\d{8}$", jdatekey):
                continue
            if jdatekey < start_key or jdatekey > end_key:
                continue

            funddate_key = str(dscode) + str(basket_id) + jdatekey
            unique_db_key = str(dscode) + "|" + str(basket_id) + "|" + jdatekey

            row_data = {
                "funddate_key": funddate_key,
                "BasketId": int(basket_id) if str(basket_id).isdigit() else 0,
                "DScode": str(dscode),
                "jdatekey": int(jdatekey),
                "JalaliDate": str(jalali_date),
                "FundName": item.get("GroupName") if item.get("GroupName") else fund_name,
                "SubscriptionNAV": parse_number(item.get("SubscriptionNAV")),
                "TotalNetAssetValue": parse_number(item.get("TotalNetAssetValue")),
                "CancelNAV": parse_number(item.get("CancelNAV")),
                "EsmiNAV": parse_number(item.get("EsmiNAV")),
                "NavDiff": parse_number(item.get("NavDiff")),
                "TotalSubscriptionUnit": parse_number(item.get("TotalSubscriptionUnit")),
                "TotalSubscription": parse_number(item.get("TotalSubscription")),
                "TotalCancel": parse_number(item.get("TotalCancel")),
                "TotalCancelUnit": parse_number(item.get("TotalCancelUnit")),
                "TotalUnit": parse_number(item.get("TotalUnit")),
                "Date": item.get("Date"),
                "StockValueReserve": parse_number(item.get("StockValueReserve"))
            }

            if unique_db_key not in latest_rows:
                latest_rows[unique_db_key] = row_data
            else:
                old_nav = latest_rows[unique_db_key]["TotalNetAssetValue"]
                new_nav = row_data["TotalNetAssetValue"]

                old_nav = old_nav if old_nav is not None else -1
                new_nav = new_nav if new_nav is not None else -1

                if new_nav > old_nav:
                    latest_rows[unique_db_key] = row_data

        insert_sql = """
        INSERT INTO [dbo].[FundsNAV_Tadibr] (
            [funddate_key], [DScode], [jdatekey], [JalaliDate], [FundName], [BasketId],
            [SubscriptionNAV], [TotalNetAssetValue], [CancelNAV], [EsmiNAV], [NavDiff],
            [TotalSubscriptionUnit], [TotalSubscription], [TotalCancel], [TotalCancelUnit],
            [TotalUnit], [Date], [StockValueReserve]
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        update_sql = """
        UPDATE [dbo].[FundsNAV_Tadibr]
        SET [DScode] = ?, [jdatekey] = ?, [JalaliDate] = ?, [FundName] = ?, [BasketId] = ?,
            [SubscriptionNAV] = ?, [TotalNetAssetValue] = ?, [CancelNAV] = ?, [EsmiNAV] = ?, [NavDiff] = ?,
            [TotalSubscriptionUnit] = ?, [TotalSubscription] = ?, [TotalCancel] = ?, [TotalCancelUnit] = ?,
            [TotalUnit] = ?, [Date] = ?, [StockValueReserve] = ?
        WHERE [funddate_key] = ? AND [BasketId] = ?
        """

        inserted_count = 0
        updated_count = 0
        gathered_dates = []

        for unique_db_key, row_data in latest_rows.items():
            gathered_dates.append(str(row_data["jdatekey"]))

            existing_db_key = row_data["funddate_key"] + "|" + str(row_data["BasketId"])

            if existing_db_key in existing_keys:
                cursor.execute(update_sql, (
                    row_data["DScode"],
                    row_data["jdatekey"],
                    row_data["JalaliDate"],
                    row_data["FundName"],
                    row_data["BasketId"],
                    row_data["SubscriptionNAV"],
                    row_data["TotalNetAssetValue"],
                    row_data["CancelNAV"],
                    row_data["EsmiNAV"],
                    row_data["NavDiff"],
                    row_data["TotalSubscriptionUnit"],
                    row_data["TotalSubscription"],
                    row_data["TotalCancel"],
                    row_data["TotalCancelUnit"],
                    row_data["TotalUnit"],
                    row_data["Date"],
                    row_data["StockValueReserve"],
                    row_data["funddate_key"],
                    row_data["BasketId"]
                ))
                updated_count += 1
            else:
                cursor.execute(insert_sql, (
                    row_data["funddate_key"],
                    row_data["DScode"],
                    row_data["jdatekey"],
                    row_data["JalaliDate"],
                    row_data["FundName"],
                    row_data["BasketId"],
                    row_data["SubscriptionNAV"],
                    row_data["TotalNetAssetValue"],
                    row_data["CancelNAV"],
                    row_data["EsmiNAV"],
                    row_data["NavDiff"],
                    row_data["TotalSubscriptionUnit"],
                    row_data["TotalSubscription"],
                    row_data["TotalCancel"],
                    row_data["TotalCancelUnit"],
                    row_data["TotalUnit"],
                    row_data["Date"],
                    row_data["StockValueReserve"]
                ))
                inserted_count += 1

        conn.commit()
        cursor.close()

        return inserted_count, updated_count, gathered_dates

    except pyodbc.Error as e:
        print(f"Database error during insert/update: {e}")
        traceback.print_exc()
        return 0, 0, []

if __name__ == "__main__":
    try:
        print("Starting script...")
        main()
    except Exception as e:
        print(f"Critical error in main execution: {e}")
        traceback.print_exc()
        print("\nPress Enter to exit...")
        input()