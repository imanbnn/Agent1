# FILE: harvester.py
import asyncio
import os
import re
import json
import datetime
import sqlite3
from logger import log_event
from scroll import force_scroll_down
from actions import teach_and_click, gemini_double_check_totals, get_supervisor_status, dismiss_all_popups

DB_FILE = "gfs_products.db"
CSV_FILE = "gfs_results.csv"
product_db = {}
target_total = 9999 
RAW_INFO_BUFFER = []
RAW_PRICE_BUFFER = []
NO_IMAGE_SVG = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNjAiIGhlaWdodD0iMTYwIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZWVlIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJzYW5zLXNlcmlmIiBmb250LXNpemU9IjE0IiBmb250LXdlaWdodD0iYm9sZCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkltYWdlIE5vdCBGb3VuZDwvdGV4dD48L3N2Zz4="

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            code TEXT PRIMARY KEY,
            name TEXT,
            details TEXT,
            price TEXT,
            stock TEXT,
            last_ordered TEXT,
            image_file TEXT,
            img_url TEXT,
            changes TEXT,
            last_seen TEXT
        )
    ''')
    conn.commit()
    conn.close()

def process_changes():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    for code, details in product_db.items():
        c.execute("SELECT price, details, img_url, changes FROM products WHERE code = ?", (code,))
        row = c.fetchone()
        change_msg = ""
        if row:
            old_price, old_details, old_img, old_changes = row
            if old_price != details["price"] and details["price"] != "Price Not Found":
                change_msg = f"New Price: {details['price']} ({current_time})"
            elif old_details != details["details"] and details["details"] != "No Details":
                change_msg = f"Desc Changed ({current_time})"
            elif old_img != details["img_url"] and details["img_url"]:
                change_msg = f"New Image ({current_time})"
            else:
                change_msg = old_changes or ""
            details["changes"] = change_msg
            c.execute("""
                UPDATE products 
                SET name=?, details=?, price=?, stock=?, last_ordered=?, image_file=?, img_url=?, changes=?, last_seen=?
                WHERE code=?
            """, (details["name"], details["details"], details["price"], details["stock"], 
                  details["last_ordered"], details["image_file"], details["img_url"], change_msg, current_time, code))
        else:
            change_msg = f"New Product ({current_time})"
            details["changes"] = change_msg
            c.execute("""
                INSERT INTO products (code, name, details, price, stock, last_ordered, image_file, img_url, changes, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (code, details["name"], details["details"], details["price"], details["stock"], 
                  details["last_ordered"], details["image_file"], details["img_url"], change_msg, current_time))
    conn.commit()
    conn.close()

def update_status(state, message, current=0, total=0):
    try:
        with open("status.json", "w", encoding="utf-8") as f:
            json.dump({"state": state, "message": message, "current": current, "total": total}, f)
    except: pass

def initialize_csv():
    with open(CSV_FILE, mode="w", encoding="utf-8") as f:
        f.write("Name;Code;Details;Pricing;Stock_Status;Last_Ordered;Image_File;Changes\n")

def sanitize_text(text):
    if not text: return ""
    return str(text).replace(';', ',').replace('\n', ' ').replace('\r', '').strip()

def write_csv_line(code, data):
    with open(CSV_FILE, mode="a", encoding="utf-8") as f:
        name = sanitize_text(data.get('name', 'Unknown'))
        details = sanitize_text(data.get('details', 'No Details'))
        price = sanitize_text(data.get('price', 'Price Not Found'))
        stock = sanitize_text(data.get('stock', 'In Stock'))
        last_ord = sanitize_text(data.get('last_ordered', 'N/A'))
        img_file = sanitize_text(data.get('image_file', 'No Image'))
        changes = sanitize_text(data.get('changes', ''))
        f.write(f"{name};{code};{details};{price};{stock};{last_ord};{img_file};{changes}\n")

def generate_html_dashboard():
    print("🌐 Generating HTML Visual Dashboard from Master Database...")
    sup_status = get_supervisor_status()
    cards_html = ""
    table_data = []
    try:
        if os.path.exists(DB_FILE):
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT name, code, details, price, stock, last_ordered, image_file, changes, last_seen FROM products ORDER BY last_seen DESC")
            rows = c.fetchall()
            for row in rows:
                name, code, details, price, stock, last_ord, img, changes, last_seen = row
                stock_class = "in-stock"
                if "OUT OF STOCK" in stock.upper(): stock_class = "out-of-stock"
                elif "CONTACT" in stock.upper(): stock_class = "contact-sales"
                img_path = img if img not in ["No Image", "Failed to Download", ""] else NO_IMAGE_SVG
                badge_html = f'<div class="badge">🆕 {changes}</div>' if changes else ""
                cards_html += f"""
                <div class="card">
                    {badge_html}
                    <img src="{img_path}" alt="Product Image">
                    <h3>{name}</h3>
                    <div class="details">#{code} | {details}</div>
                    <div class="price">{price}</div>
                    <div class="stock {stock_class}">{stock}</div>
                    <div class="ordered">Last Ordered: {last_ord} <br><small>Last Seen: {last_seen}</small></div>
                </div>
                """
                table_data.append([
                    f"<img src='{img_path}' style='width: 45px; height: 45px; object-fit: contain; border-radius: 4px;'>",
                    f"<b>#{code}</b>",
                    name,
                    details,
                    f"<span style='color: #27ae60; font-weight: bold;'>{price}</span>",
                    f"<span class='stock {stock_class}'>{stock}</span>",
                    last_ord,
                    changes,
                    last_seen
                ])
            conn.close()
    except Exception as e:
        print(f"⚠️ Failed to read DB for dashboard: {e}")
    html_content = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GFS Harvest Dashboard</title>
        <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
        <link rel="stylesheet" href="https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css">
        <script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f7f6; padding: 140px 20px 20px; color: #333; margin: 0; }}
            .control-panel {{ position: fixed; top: 0; left: 0; right: 0; background: white; padding: 15px 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); z-index: 1000; display: flex; flex-direction: column; gap: 15px; }}
            .panel-top {{ display: flex; align-items: center; gap: 20px; justify-content: space-between; width: 100%; }}
            .panel-left {{ display: flex; align-items: center; gap: 15px; flex-grow: 1; }}
            .btn-search, .btn-explore, .btn-view {{ color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 6px; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.15); }}
            .btn-search {{ background: #27ae60; }} .btn-search:hover {{ background: #219150; transform: translateY(-1px); }}
            .btn-explore {{ background: #8e44ad; }} .btn-explore:hover {{ background: #732d91; transform: translateY(-1px); }}
            .btn-view {{ background: #ecf0f1; color: #2c3e50; box-shadow: none; border: 1px solid #bdc3c7; }} 
            .btn-view:hover {{ background: #bdc3c7; }}
            .btn-search:disabled, .btn-explore:disabled {{ background: #95a5a6; cursor: not-allowed; box-shadow: none; transform: none; }}
            .view-toggle-container {{ display: flex; gap: 10px; border-left: 2px solid #eee; padding-left: 20px; margin-left: 10px; }}
            .active-view {{ background: #34495e !important; color: white !important; border-color: #34495e !important; box-shadow: 0 4px 6px rgba(52, 73, 94, 0.3) !important; }}
            .status-container {{ flex-grow: 1; max-width: 500px; margin-left: 20px; }}
            .progress-bg {{ background: #ecf0f1; height: 12px; border-radius: 6px; overflow: hidden; width: 100%; box-shadow: inset 0 1px 3px rgba(0,0,0,0.1); }}
            #progress-bar {{ background: #3498db; height: 100%; width: 0%; transition: width 0.3s ease; }}
            .supervisor-badge {{ background: #2c3e50; color: white; padding: 10px 20px; border-radius: 8px; font-weight: bold; font-size: 0.9em; white-space: nowrap; }}
            h1 {{ text-align: center; color: #2c3e50; margin-top: 0; }}
            /* Grid View */
            .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; margin-top: 20px; }}
            .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: flex; flex-direction: column; transition: transform 0.2s; position: relative; }}
            .card:hover {{ transform: translateY(-5px); box-shadow: 0 8px 15px rgba(0,0,0,0.15); }}
            .card img {{ max-width: 100%; height: 160px; object-fit: contain; align-self: center; margin-bottom: 15px; border-radius: 4px; }}
            .card h3 {{ margin: 0 0 10px 0; font-size: 1.1em; color: #2c3e50; }}
            .details {{ color: #7f8c8d; font-size: 0.9em; margin-bottom: 15px; flex-grow: 1; }}
            /* Shared Item Attributes */
            .price {{ color: #27ae60; font-weight: bold; font-size: 1.2em; margin-bottom: 5px; }}
            .stock {{ font-weight: bold; font-size: 0.9em; margin-bottom: 5px; }}
            .in-stock {{ color: #27ae60; }} .out-of-stock {{ color: #e74c3c; }} .contact-sales {{ color: #f39c12; }}
            .ordered {{ color: #34495e; font-size: 0.85em; margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; }}
            .badge {{ background: #e74c3c; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.8em; font-weight: bold; margin-bottom: 12px; display: inline-block; align-self: flex-start; }}
            /* Table View */
            table.dataTable thead th {{ background-color: #34495e; color: white; padding: 12px 10px; border-bottom: none; }}
            table.dataTable tbody tr:hover {{ background-color: #f8f9fa; }}
            table.dataTable tbody td {{ vertical-align: middle; }}
            .dataTables_wrapper .dataTables_filter input {{ border: 1px solid #bdc3c7; border-radius: 4px; padding: 6px 10px; margin-left: 10px; }}
        </style>
    </head>
    <body>
        <div class="control-panel">
            <div class="panel-top">
                <div class="panel-left">
                    <button id="searchBtn" class="btn-search" onclick="startBot('search')">🔍 Run Search Queue</button>
                    <button id="exploreBtn" class="btn-explore" onclick="startBot('explore')">🧭 Explore Catalog</button>
                    <div class="view-toggle-container">
                        <button id="btn-grid" class="btn-view active-view" onclick="toggleView('grid')">📱 Grid View</button>
                        <button id="btn-table" class="btn-view" onclick="toggleView('table')">🗄️ ERP Database View</button>
                    </div>
                    <div class="status-container">
                        <p id="status-text">Status: Loading...</p>
                        <div class="progress-bg"><div id="progress-bar"></div></div>
                    </div>
                </div>
                <div class="supervisor-badge">🧠 Supervisor: {sup_status}</div>
            </div>
        </div>
        <h1>📦 Master Local Database Dashboard</h1>
        <div id="grid-container" class="grid">
            {cards_html}
        </div>
        <div id="table-container" style="display: none; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-top: 20px;">
            <table id="erpTable" class="display" style="width:100%">
                <thead>
                    <tr>
                        <th>Image</th>
                        <th>Code</th>
                        <th>Name</th>
                        <th>Details</th>
                        <th>Price</th>
                        <th>Stock Status</th>
                        <th>Last Ordered</th>
                        <th>Recent Changes</th>
                        <th>Last Seen</th>
                    </tr>
                </thead>
                <tbody>
                </tbody>
            </table>
        </div>
        <script>
            const erpData = {json.dumps(table_data)};
            $(document).ready(function() {{
                $('#erpTable').DataTable({{
                    data: erpData,
                    pageLength: 25,
                    lengthMenu: [10, 25, 50, 100, 500],
                    order: [[8, 'desc']], 
                    columnDefs: [
                        {{ orderable: false, targets: 0 }},
                        {{ className: "dt-head-left", targets: "_all" }}
                    ],
                    language: {{
                        search: "Global Filter:",
                        lengthMenu: "Show _MENU_ products per page"
                    }}
                }});
            }});
            function toggleView(viewType) {{
                if (viewType === 'grid') {{
                    document.getElementById('grid-container').style.display = 'grid';
                    document.getElementById('table-container').style.display = 'none';
                    document.getElementById('btn-grid').classList.add('active-view');
                    document.getElementById('btn-table').classList.remove('active-view');
                }} else {{
                    document.getElementById('grid-container').style.display = 'none';
                    document.getElementById('table-container').style.display = 'block';
                    document.getElementById('btn-table').classList.add('active-view');
                    document.getElementById('btn-grid').classList.remove('active-view');
                    $('#erpTable').DataTable().columns.adjust().draw();
                }}
            }}
            function startBot(mode) {{
                document.getElementById('searchBtn').disabled = true;
                document.getElementById('exploreBtn').disabled = true;
                fetch('/api/start?mode=' + mode).then(() => {{
                    document.getElementById('status-text').innerText = "Status: Initializing " + mode.toUpperCase() + " mode...";
                }});
            }}
            setInterval(() => {{
                fetch('status.json?t=' + Date.now())
                    .then(r => r.json())
                    .then(data => {{
                        document.getElementById('status-text').innerText = "Status: " + data.message;
                        let pct = data.total > 0 ? (data.current / data.total) * 100 : 0;
                        if(data.state === "complete") pct = 100;
                        document.getElementById('progress-bar').style.width = pct + '%';
                        if(data.state === 'running' || data.state === 'processing') {{
                            document.getElementById('searchBtn').disabled = true;
                            document.getElementById('exploreBtn').disabled = true;
                        }} else {{
                            document.getElementById('searchBtn').disabled = false;
                            document.getElementById('exploreBtn').disabled = false;
                        }}
                        if(data.state === 'complete' && !window.hasRefreshed) {{
                            window.hasRefreshed = true;
                            setTimeout(() => window.location.reload(), 2500);
                        }}
                        if(data.state === 'idle') window.hasRefreshed = false;
                    }}).catch(e => {{}});
            }}, 1500);
        </script>
    </body></html>
    """
    try:
        with open("dashboard.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    except Exception as e:
        print(f"⚠️ Failed to generate HTML dashboard: {e}")

async def download_pending_images(page):
    os.makedirs("dashboard_images", exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    pending = [k for k, v in product_db.items() if v.get("img_url") and v.get("image_file") in ["No Image", "Failed to Download"]]
    if not pending: return
    completed = 0
    sem = asyncio.Semaphore(15) 
    async def fetch_img(code, details):
        nonlocal completed
        img_file = f"dashboard_images/{code}.jpg"
        if not os.path.exists(img_file):
            try:
                async with sem:
                    url = details["img_url"]
                    if url.startswith("//"): url = "https:" + url
                    response = await page.request.get(url, headers=headers, timeout=10000)
                    if response.ok:
                        with open(img_file, 'wb') as f: f.write(await response.body())
                        product_db[code]["image_file"] = img_file
            except: product_db[code]["image_file"] = "Failed to Download"
        else: product_db[code]["image_file"] = img_file
        completed += 1
        if completed % 10 == 0: update_status("running", f"Downloading Images... {completed}/{len(pending)}", completed, len(pending))
    print(f"📸 Downloading {len(pending)} queued images in parallel...")
    await asyncio.gather(*[fetch_img(code, product_db[code]) for code in pending])

async def get_total_results_via_dom(page):
    try:
        text = await page.evaluate("document.body.innerText")
        match = re.search(r'(\d+)\s+results', text.lower())
        return int(match.group(1)) if match else 9999
    except: return 9999

async def setup_wiretap(page):
    global RAW_INFO_BUFFER, RAW_PRICE_BUFFER
    RAW_INFO_BUFFER.clear()
    RAW_PRICE_BUFFER.clear()
    async def handle_response(response):
        global target_total, RAW_INFO_BUFFER, RAW_PRICE_BUFFER
        url = response.url.lower()
        if response.request.resource_type in ["fetch", "xhr"]:
            try:
                data = await response.json()
                if "totalResults" in data and ("materials/search" in url or "search" in url): 
                    new_total = int(data["totalResults"])
                    if target_total == 9999 or new_total > target_total:
                        target_total = new_total
                if "materialInfos" in data:
                    RAW_INFO_BUFFER.append(data)
                if "materialPrices" in data:
                    RAW_PRICE_BUFFER.append(data)
            except: pass
    page.on("response", handle_response)

def merge_buffers_to_db():
    global product_db, RAW_INFO_BUFFER, RAW_PRICE_BUFFER
    for payload in RAW_INFO_BUFFER:
        for item in payload.get("materialInfos", []):
            code = str(item.get("materialNumber", ""))
            if not code: continue
            if code not in product_db:
                product_db[code] = { "name": "Unknown", "details": "No Details", "price": "Price Not Found", "stock": "In Stock", "last_ordered": "N/A", "image_file": "No Image", "img_url": "", "changes": "" }
            desc = item.get("description") or {}
            name = desc.get("en") or desc.get("fr") or product_db[code].get("name")
            brand = (item.get("brand") or {}).get("en", "Unknown Brand")
            weight = item.get("baseUomWeight") or {}
            net_weight = weight.get("net", "")
            try:
                nw_float = float(net_weight)
                net_weight = f"{int(nw_float)}" if nw_float.is_integer() else f"{nw_float}"
            except Exception: pass
            uom = weight.get("uom", "").upper()
            if uom in ["KG", "KGM"]: uom = "Kilograms"
            elif uom in ["LB", "LBR"]: uom = "Pounds"
            elif uom in ["G", "GRM"]: uom = "Grams"
            elif uom in ["ML", "MLT"]: uom = "Milliliters"
            elif uom in ["L", "LTR"]: uom = "Liters"
            else: uom = uom.capitalize()
            base_uom = item.get("baseUom", "Case").capitalize()
            if base_uom in ["Cs", "Bg", "Ea"]: base_uom = {"Cs":"Case", "Bg":"Bag", "Ea":"Each"}.get(base_uom, base_uom)
            details_str = f"{brand} | {net_weight} {uom}/{base_uom}"
            img_url = ""
            if "image" in item and item["image"]:
                for lang in ["en", "fr", "es"]:
                    img_data = item["image"].get(lang) or {}
                    if img_data.get("url"):
                        img_url = img_data["url"]
                        break
            product_db[code].update({"name": name, "details": details_str})
            if img_url and not product_db[code].get("img_url"):
                product_db[code]["img_url"] = img_url
    for payload in RAW_PRICE_BUFFER:
        for item in payload.get("materialPrices", []):
            code = str(item.get("materialNumber", ""))
            if not code: continue
            if code not in product_db:
                product_db[code] = { "name": "Unknown", "details": "No Details", "price": "Price Not Found", "stock": "In Stock", "last_ordered": "N/A", "image_file": "No Image", "img_url": "", "changes": "" }
            units = item.get("unitPrices") or []
            price_strings = []
            for u in units:
                if u.get("price") is not None:
                    uom = u.get("salesUom") or u.get("uom") or "EA"
                    if uom in ["CS", "BG", "EA"]: uom = {"CS":"Case", "BG":"Bag", "EA":"Each"}.get(uom, uom)
                    else: uom = uom.capitalize()
                    price_strings.append(f"{uom}: ${float(u['price']):.2f}")
            if price_strings:
                product_db[code]["price"] = " | ".join(price_strings)

async def dump_json_buffers(suffix=""):
    global RAW_INFO_BUFFER, RAW_PRICE_BUFFER
    try:
        if RAW_INFO_BUFFER:
            filename = f"raw_info_dump_{suffix}.json" if suffix else "raw_info_dump.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(RAW_INFO_BUFFER, f, separators=(',', ':'))
        if RAW_PRICE_BUFFER:
            filename = f"raw_price_dump_{suffix}.json" if suffix else "raw_price_dump.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(RAW_PRICE_BUFFER, f, separators=(',', ':'))
    except Exception as e:
        print(f"⚠️ FATAL ERROR dumping JSON buffers: {e}")

async def run_harvest(page, kb=None, state="search_results"):
    global target_total, product_db, RAW_INFO_BUFFER, RAW_PRICE_BUFFER
    global_product_db = {}
    product_db.clear()
    RAW_INFO_BUFFER.clear()
    RAW_PRICE_BUFFER.clear()
    target_total = 9999 
    
    initialize_csv()
    update_status("running", "Initializing Harvester...", 5, 100)
    for _ in range(15):
        if target_total != 9999: break
        await asyncio.sleep(0.5)
        
    all_res_target = 9999
    order_guide_target = 0
    print("🔍 Scanning DOM for product totals...")
    try:
        text = await page.evaluate("document.body.innerText")
        text_lower = text.lower()
        all_match = re.search(r'(\d+)\s+results', text_lower)
        og_match = re.search(r'order guide only\s*\((\d+)\)', text_lower)
        if all_match: 
            all_res_target = int(all_match.group(1))
            print(f"📊 DOM found All Results: {all_res_target}")
        if og_match: 
            order_guide_target = int(og_match.group(1))
            print(f"📊 DOM found Order Guide: {order_guide_target}")
    except Exception as e:
        print(f"⚠️ DOM parsing error: {e}")
        
    if target_total != 9999:
        print(f"📡 Wiretap intercepted target: {target_total}")
        all_res_target = target_total
    if all_res_target == 9999 or order_guide_target == 0:
        print("🤖 Missing some totals. Tagging in Gemini Supervisor...")
        totals = await gemini_double_check_totals(page)
        if totals:
            if all_res_target == 9999: 
                all_res_target = int(totals.get("all_results_total", 9999))
            if order_guide_target == 0: 
                order_guide_target = int(totals.get("order_guide_total", 0))
    target_total = all_res_target
    print(f"🎯 Target Phase 1 Confirmed: {target_total} | Target Phase 2 Confirmed: {order_guide_target}")

    async def perform_scroll_loop(phase_name="Phase 1"):
        stagnant_strikes = 0
        max_strikes = 8 
        seen_in_dom = set() 
        while len(seen_in_dom) < target_total and stagnant_strikes < max_strikes:
            last_count = len(seen_in_dom)
            remaining_items = max(0, target_total - last_count)
            update_status("running", f"[{phase_name}] Scrolling... {last_count}/{target_total} (Need {remaining_items} more)", last_count, target_total)
            
            await dismiss_all_popups(page)
            await force_scroll_down(page, scrolls=1)
            merge_buffers_to_db()
            
            try:
                dom_data = await page.evaluate("""() => {
                    let items = {};
                    let regex = /#(\\d{5,9})/;
                    let container = document.querySelector('cdk-virtual-scroll-viewport, .scroll-container, main, .product-grid, .item-list') || document.body;
                    let elements = container.querySelectorAll('*');
                    for (let el of elements) {
                        if (el.children.length > 0) continue;
                        let tagName = el.tagName.toLowerCase();
                        if (tagName === 'script' || tagName === 'style' || tagName === 'noscript') continue;
                        if (el.closest('header') || el.closest('naoo-header') || el.closest('.header') || el.closest('nav') || el.closest('.docket-header')) continue;
                        let text = el.innerText || el.textContent || '';
                        if (text.includes('{') || text.includes('}')) continue;
                        let match = text.match(regex);
                        if (match) {
                            let code = match[1];
                            let parent = el.parentElement;
                            let maxDepth = 12; 
                            let foundCard = false;
                            let cardNode = null;
                            while (parent && maxDepth > 0) {
                                let pText = parent.innerText || '';
                                if (pText.includes(code) && (pText.includes('$') || pText.includes('Case') || pText.includes('Pack') || pText.includes('Compare') || pText.includes('Price') || pText.includes('Ordered'))) {
                                    cardNode = parent;
                                    foundCard = true;
                                    if (parent.querySelector('img')) {
                                        break;
                                    }
                                }
                                parent = parent.parentElement;
                                maxDepth--;
                            }
                            let lines = [];
                            let imgUrl = "";
                            if (foundCard && cardNode) {
                                lines = (cardNode.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
                                let imgs = cardNode.querySelectorAll('img');
                                for (let img of imgs) {
                                    let src = img.src || img.getAttribute('data-src') || '';
                                    if (src && !src.startsWith('data:image') && !src.includes('svg')) {
                                        imgUrl = src;
                                        break;
                                    }
                                }
                            } else if (parent && (parent.innerText || '').split('\\n').length >= 3) {
                                lines = (parent.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
                            }
                            items[code] = { lines: lines, img: imgUrl };
                        }
                    }
                    return items;
                }""")
                for code, data_dict in dom_data.items():
                    if code == "722349852": continue
                    seen_in_dom.add(code) 
                    lines = data_dict.get("lines", [])
                    scraped_img = data_dict.get("img", "")
                    if code not in product_db:
                        if code in global_product_db:
                            product_db[code] = dict(global_product_db[code])
                        else:
                            product_db[code] = { "name": "Unknown", "details": "No Details", "price": "Price Not Found", "stock": "In Stock", "last_ordered": "N/A", "image_file": "No Image", "img_url": "", "changes": "" }
                    if scraped_img and (not product_db[code].get("img_url") or "no_image" in product_db[code].get("img_url", "").lower()):
                        product_db[code]["img_url"] = scraped_img
                    if len(lines) > 0:
                        ignore_labels = ["compare", "view similar items", "long term out of stock", "new", "in stock", "contact sales", "add to cart", "out of stock", "special order", "hide unavailable items"]
                        clean_lines = [l for l in lines if l.lower() not in ignore_labels and "delivery" not in l.lower()]
                        ordered_lines = [l for l in clean_lines if "ordered:" in l.lower() or "ordered " in l.lower()]
                        for l in ordered_lines:
                            match = re.search(r'ordered:?\s*(.*)', l, re.IGNORECASE)
                            if match:
                                product_db[code]["last_ordered"] = match.group(1).strip()
                            clean_lines.remove(l) 
                        code_idx = -1
                        for i, l in enumerate(clean_lines):
                            if f"#{code}" in l:
                                code_idx = i
                                break
                        if code_idx != -1:
                            if code_idx > 0 and product_db[code]["name"] in ["Unknown", ""]:
                                product_db[code]["name"] = clean_lines[code_idx - 1]
                            if product_db[code]["details"] in ["No Details", "⭐ [ORDER GUIDE] No Details", ""]:
                                d_line = clean_lines[code_idx]
                                c_details = d_line.replace(f"#{code} |", "").replace(f"#{code}", "").strip()
                                if c_details:
                                    product_db[code]["details"] = c_details
                                elif code_idx + 1 < len(clean_lines):
                                    product_db[code]["details"] = clean_lines[code_idx + 1]
                        else:
                            if product_db[code]["name"] in ["Unknown", ""] and clean_lines:
                                product_db[code]["name"] = clean_lines[0]
                        if product_db[code]["price"] in ["Price Not Found", ""]:
                            for i, l in enumerate(clean_lines):
                                if "$" in l and any(c.isdigit() for c in l):
                                    if ":" in l:
                                        product_db[code]["price"] = l
                                    else:
                                        unit = clean_lines[i-1] if i > 0 and len(clean_lines[i-1]) <= 6 else "Case"
                                        product_db[code]["price"] = f"{unit}: {l}"
                                    break
            except Exception as e:
                print(f"⚠️ DOM extraction error: {e}")
            
            if len(seen_in_dom) == last_count:
                stagnant_strikes += 1
                print(f"⚠️ Memory Stagnant on {phase_name}. Strike {stagnant_strikes}/{max_strikes}")
                try:
                    await page.evaluate("""() => {
                        const containers = document.querySelectorAll('cdk-virtual-scroll-viewport, .scroll-container, [class*="scroll"], main, .product-grid, .item-list');
                        containers.forEach(c => {
                            if (c && c.scrollHeight > c.clientHeight) {
                                c.scrollTop += 1500;
                                c.dispatchEvent(new Event('scroll', { bubbles: true }));
                            }
                        });
                        window.scrollBy({ top: 1500, behavior: 'instant' });
                    }""")
                    
                    viewport = page.viewport_size
                    if viewport:
                        # CRITICAL FIX: Click far right edge to avoid product cards
                        safe_x = int(viewport['width'] - 10)
                        safe_y = int(viewport['height'] * 0.5)
                        await page.mouse.click(safe_x, safe_y)
                        
                    await page.keyboard.press("PageDown")
                    await asyncio.sleep(1.5)
                except: pass
            else: 
                stagnant_strikes = 0
                print(f"📦 [{phase_name}] Progress: {len(seen_in_dom)} / {target_total} products mapped. ({max(0, target_total - len(seen_in_dom))} left to go!)")
    try:
        print("🚀 Starting Phase 1: Scraping 'All Results' tab...")
        
        await perform_scroll_loop(phase_name="Phase 1")
        await dump_json_buffers("phase1")
        merge_buffers_to_db()
        global_product_db.update(product_db)
        if order_guide_target > 0 and kb is not None:
            print(f"\n🔄 Initiating Phase 2: Switching to 'Order Guide Only' tab to fetch {order_guide_target} items...")
            await page.evaluate("""() => {
                window.scrollTo({ top: 0, behavior: 'smooth' });
                document.documentElement.scrollTop = 0;
                document.body.scrollTop = 0;
                const elements = document.querySelectorAll('cdk-virtual-scroll-viewport, .scroll-container, main, .product-grid, .item-list');
                for (let el of elements) {
                    el.scrollTop = 0;
                    el.dispatchEvent(new Event('scroll'));
                }
            }""")
            await asyncio.sleep(2.0)
            for _ in range(5):
                await page.keyboard.press("PageUp")
                await asyncio.sleep(0.2)
            for _ in range(3):
                await page.keyboard.press("Home")
                await asyncio.sleep(0.5)
            tab_clicked = False
            try:
                selectors_to_try = [
                    "text=/Order Guide Only/i",
                    "[role='tab']:has-text('Order Guide')",
                    "div.tab-header:has-text('Order Guide')",
                    "//div[contains(translate(text(), 'ORDER', 'order'), 'order guide')]"
                ]
                for sel in selectors_to_try:
                    try:
                        tab_loc = page.locator(sel).first
                        await tab_loc.wait_for(state="attached", timeout=2000)
                        await tab_loc.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5)
                        await tab_loc.click(force=True)
                        tab_clicked = True
                        print(f"✅ Switched tabs via direct DOM Locator successfully using: {sel}")
                        break
                    except Exception:
                        continue
            except Exception as e:
                print(f"⚠️ Direct DOM clicker failed: {e}")
                pass
            if not tab_clicked:
                tab_clicked = await teach_and_click(page, kb, state, "order_guide_tab", action="click")
            if tab_clicked:
                print("✅ Wiping memory buffers for Phase 2 isolation...")
                product_db.clear()
                RAW_INFO_BUFFER.clear()
                RAW_PRICE_BUFFER.clear()
                target_total = order_guide_target
                await asyncio.sleep(5) 
                merge_buffers_to_db() 
                await perform_scroll_loop(phase_name="Phase 2")
                await dump_json_buffers("phase2")
                merge_buffers_to_db()
                for code, data in product_db.items():
                    if "[ORDER GUIDE]" not in data["details"]:
                        data["details"] = f"⭐ [ORDER GUIDE] {data['details']}"
                    global_product_db[code] = data
    except Exception as e:
        print(f"⚠️ HARVEST WARNING: Sequence interrupted ({e}). Saving retrieved data...")
    finally:
        update_status("processing", "Saving to SQLite DB & Generating Dashboard...", 90, 100)
        product_db.clear()
        product_db.update(global_product_db)
        await download_pending_images(page)
        process_changes()
        for code, data in product_db.items(): write_csv_line(code, data)
        generate_html_dashboard()