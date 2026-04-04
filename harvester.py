import asyncio
import os
import re
import json
from logger import log_event
from scroll import force_scroll_down
from actions import get_ocr

CSV_FILE = "gfs_results.csv"

# 🌍 GLOBAL MEMORY FOR THE WIRETAP
product_db = {}
written_codes = set()
target_total = 9999 

# 🧠 BUFFERS: Aggregates JSON payloads across multiple scrolls
RAW_INFO_BUFFER = None
RAW_PRICE_BUFFER = None

def initialize_csv():
    """Clears the CSV and writes the headers."""
    with open(CSV_FILE, mode="w", encoding="utf-8") as f:
        f.write("Name;Code;Price;First_Measurement;Second_Measurement\n")
    print("🧹 CSV initialized for new harvest.")

def write_csv_line(code, data):
    """Appends a completed product to the CSV."""
    if code in written_codes: return
    with open(CSV_FILE, mode="a", encoding="utf-8") as f:
        name = str(data.get('name', 'Unknown')).replace(';', ',').replace('\n', ' ')
        price = str(data.get('price', 'Price Not Found')).replace(';', ',')
        m1 = str(data.get('m1', 'Not Found')).replace(';', ',')
        m2 = str(data.get('m2', 'Not Found')).replace(';', ',')
        f.write(f"{name};{code};{price};{m1};{m2}\n")
    written_codes.add(code)

async def scrape_current_html(page):
    """
    Direct DOM Scrape: Extracts visible products from HTML.
    FIXED: Escaped forward slashes in Regex to prevent JavaScript SyntaxError.
    """
    products = await page.evaluate("""() => {
        const items = [];
        const cards = document.querySelectorAll('.product-card, .list-item, .product-row, tr, [role="row"], article, .product-info, .item-row');

        cards.forEach(card => {
            const cardText = card.innerText;
            if (!cardText) return;

            // 1. Find Item Number
            const codeMatch = cardText.match(/#\\s*(\\d{6,8})/);
            let cleanCode = '';

            if (codeMatch) {
                cleanCode = codeMatch[1];
            } else {
                const codeEl = card.querySelector('.item-number, .product-code, [class*="material-number"], [class*="sku"]');
                if (codeEl) cleanCode = codeEl.innerText.replace(/[^0-9]/g, '');
            }

            if (cleanCode.length > 3) {
                const upperText = cardText.toUpperCase();
                const isOOS = upperText.includes('OUT OF STOCK');
                const isContact = upperText.includes('CONTACT YOUR SALES REPRESENTATIVE');

                // 2. Find Price & Handle Dual Pricing (Case | Unit)
                let finalPrice = 'Price Not Found';
                if (isOOS) {
                    finalPrice = 'OUT OF STOCK';
                } else if (isContact) {
                    finalPrice = 'Contact Sales Rep';
                } else {
                    const priceEl = card.querySelector('.price, .amount, [class*="unit-price"], .price-container, [class*="pricing"], [class*="price-val"], td:nth-child(4)');
                    if (priceEl && priceEl.innerText.includes('$')) {
                        finalPrice = priceEl.innerText.trim().replace(/\\n+/g, ' | ').replace(/\\s{2,}/g, ' ');
                    } else {
                        // FIXED: Escaped forward slashes (\\/) for JS context
                        const priceMatches = cardText.match(/\\$\\d+\\.\\d{2}(?:\\s*(?:Case|Each|\\/CS|\\/EA|\\/LB|\\/KG))?/gi);
                        if (priceMatches) finalPrice = priceMatches.join(' | ');
                    }
                }

                let cleanName = 'Unknown';
                const nameEl = card.querySelector('.product-name, h3, [class*="title"], [class*="desc"]');
                if (nameEl) cleanName = nameEl.innerText.trim();

                items.push({
                    name: cleanName,
                    code: cleanCode,
                    price: finalPrice
                });
            }
        });
        return items;
    }""")

    for p in products:
        if p['code'] not in product_db:
            product_db[p['code']] = {"name": p['name'], "price": p['price'], "m1": "HTML_SCAN", "m2": "HTML_SCAN"}
        else:
            if p['price'] != "Price Not Found":
                product_db[p['code']]["price"] = p['price']
        write_csv_line(p['code'], product_db[p['code']])

async def get_total_results_via_ocr(page):
    """Uses Vision to read the total result count from the screen."""
    shot_path = "vision/harvest_start_count.png"
    os.makedirs("vision", exist_ok=True)
    try: await page.wait_for_selector(".result-text-title", timeout=5000)
    except: pass
    await page.screenshot(path=shot_path)
    ocr = get_ocr()
    result = ocr.ocr(shot_path)
    if result and result[0]:
        for line in result[0]:
            text = line[1][0]
            match = re.search(r'(\d+)\s+results', text.lower())
            if match:
                total = int(match.group(1))
                return total
    return 9999

async def setup_wiretap(page):
    """Intercepts and aggregates all background API traffic."""
    async def handle_response(response):
        global target_total, RAW_INFO_BUFFER, RAW_PRICE_BUFFER
        if response.request.resource_type in ["fetch", "xhr"]:
            url = response.url.lower()
            try:
                if any(x in url for x in ["categories", "nav", "menu", "taxonomy"]):
                    data = await response.json()
                    with open("navigation_dump.json", "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
                elif "materials/search" in url:
                    data = await response.json()
                    if "totalResults" in data: target_total = int(data["totalResults"])
                elif "materials/info" in url or "material-info" in url:
                    data = await response.json()
                    if RAW_INFO_BUFFER is None: RAW_INFO_BUFFER = data
                    elif "materialInfos" in data: RAW_INFO_BUFFER.setdefault("materialInfos", []).extend(data["materialInfos"])
                    for item in data.get("materialInfos", []):
                        code = item.get("materialNumber")
                        if not code: continue
                        desc = item.get("description", {})
                        name = desc.get("en") or desc.get("fr") or "Unknown"
                        weight = item.get("baseUomWeight", {})
                        m1 = f"{weight.get('net', '')} {weight.get('uom', '')}".strip() or "Not Found"
                        if code not in product_db:
                            product_db[code] = {"name": name, "price": "Price Not Found", "m1": m1, "m2": "Not Found"}
                        else: product_db[code].update({"name": name, "m1": m1})
                elif "prices" in url:
                    data = await response.json()
                    if RAW_PRICE_BUFFER is None: RAW_PRICE_BUFFER = data
                    elif "materialPrices" in data: RAW_PRICE_BUFFER.setdefault("materialPrices", []).extend(data["materialPrices"])
                    for item in data.get("materialPrices", []):
                        code = item.get("materialNumber")
                        if not code: continue
                        units = item.get("unitPrices") or []
                        price_strings = [f"${u['price']}/{u.get('uom', 'EA')}" for u in units if u.get("price") is not None]
                        price_val = " | ".join(price_strings) if price_strings else "Price Not Found"
                        if code not in product_db:
                            product_db[code] = {"name": "", "price": price_val, "m1": "Not Found", "m2": "Not Found"}
                        elif product_db[code]["price"] == "Price Not Found":
                            product_db[code]["price"] = price_val
            except: pass
    page.on("response", handle_response)

async def run_harvest(page, mode="scan"):
    global target_total, RAW_INFO_BUFFER, RAW_PRICE_BUFFER
    initialize_csv()
    print(f"📡 DEPLOYING HARVESTER (Mode: {mode.upper()})...")

    if mode == "quick_dump":
        print("🚨 INITIATING QUICK JSON DUMP...")
        if RAW_INFO_BUFFER:
            with open("raw_info_dump.json", "w", encoding="utf-8") as f: json.dump(RAW_INFO_BUFFER, f, indent=4)
        if RAW_PRICE_BUFFER:
            with open("raw_price_dump.json", "w", encoding="utf-8") as f: json.dump(RAW_PRICE_BUFFER, f, indent=4)
        await scrape_current_html(page) 
        for code, details in list(product_db.items()):
            if details["name"]: write_csv_line(code, details)
        return 

    if target_total == 9999: target_total = await get_total_results_via_ocr(page)

    await scrape_current_html(page)
    max_empty_scrolls, scroll_attempts, last_screen_text, stagnant_strikes = 20, 0, "", 0
    
    while len(written_codes) < target_total and scroll_attempts < max_empty_scrolls:
        last_count = len(written_codes)
        await force_scroll_down(page, scrolls=1)
        await asyncio.sleep(4.0) 
        await scrape_current_html(page)
        
        for code, details in list(product_db.items()):
            if details["name"] and details["price"] != "Price Not Found":
                write_csv_line(code, details)

        if len(written_codes) > last_count:
            scroll_attempts, last_screen_text, stagnant_strikes = 0, "", 0
            print(f"📦 Progress: {len(written_codes)} / {target_total} products saved.")
        else:
            scroll_attempts += 1
            if scroll_attempts % 2 == 0: 
                shot_path = "vision/bottom_check.png"
                await page.screenshot(path=shot_path)
                ocr = get_ocr()
                result = ocr.ocr(shot_path)
                current_screen_text = " ".join([line[1][0].strip() for line in result[0]]) if result and result[0] else ""
                if current_screen_text and current_screen_text == last_screen_text:
                    stagnant_strikes += 1
                    if stagnant_strikes >= 2: break 
                else:
                    stagnant_strikes = 0
                    last_screen_text = current_screen_text

    for code, details in list(product_db.items()):
        if details["name"]: write_csv_line(code, details)

    if mode == "agg_dump":
        print("🚨 SAVING AGGREGATED JSON DUMPS...")
        if RAW_INFO_BUFFER:
            with open("raw_info_dump.json", "w", encoding="utf-8") as f: json.dump(RAW_INFO_BUFFER, f, indent=4)
        if RAW_PRICE_BUFFER:
            with open("raw_price_dump.json", "w", encoding="utf-8") as f: json.dump(RAW_PRICE_BUFFER, f, indent=4)

    print(f"🎉 Harvest complete. Total Saved: {len(written_codes)}")