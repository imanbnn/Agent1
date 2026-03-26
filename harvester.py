import asyncio
import os
import re
import json  # <--- Imported for dumping JSON payloads
from logger import log_event
from scroll import force_scroll_down
from actions import get_ocr

CSV_FILE = "gfs_results.csv"

# 🌍 GLOBAL MEMORY FOR THE WIRETAP
product_db = {}
written_codes = set()
target_total = 9999 

# Flags so we only dump the FIRST payload and don't spam your hard drive
dumped_info = False
dumped_price = False

def initialize_csv():
    """Clears the CSV and writes the headers."""
    with open(CSV_FILE, mode="w", encoding="utf-8") as f:
        f.write("Name;Code;Price;First_Measurement;Second_Measurement\n")
    print("🧹 CSV initialized and cleared for new harvest.")

def write_csv_line(code, data):
    """Appends a completed product to the CSV."""
    with open(CSV_FILE, mode="a", encoding="utf-8") as f:
        name = str(data.get('name', 'Unknown')).replace(';', ',').replace('\n', ' ')
        price = str(data.get('price', 'Price Not Found')).replace(';', '')
        m1 = str(data.get('m1', 'Not Found')).replace(';', ',')
        m2 = str(data.get('m2', 'Not Found')).replace(';', ',')
        f.write(f"{name};{code};{price};{m1};{m2}\n")

async def setup_wiretap(page):
    """Starts listening to all network traffic the moment the browser opens."""
    print("🎧 Booting Global API Wiretap...")
    
    async def handle_response(response):
        global target_total, dumped_info, dumped_price
        
        if response.request.resource_type in ["fetch", "xhr"]:
            url = response.url.lower()
            try:
                # 1. Catch Total Results
                if "materials/search" in url:
                    data = await response.json()
                    if "totalResults" in data:
                        target_total = int(data["totalResults"])
                        print(f"🎯 [API] Target Acquired: {target_total} total products expected.")

                # 2. Catch Product Info
                elif "materials/info" in url or "material-info" in url:
                    data = await response.json()
                    
                    # 🚨 THE DATA DUMP 🚨
                    if not dumped_info:
                        with open("raw_info_dump.json", "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4)
                        print("💾 [DEBUG] Saved raw Product Info JSON to raw_info_dump.json")
                        dumped_info = True

                    for item in data.get("materialInfos", []):
                        code = item.get("materialNumber")
                        if not code: continue
                        
                        desc = item.get("description", {})
                        name = desc.get("en") or desc.get("fr") or "Unknown"
                        
                        weight = item.get("baseUomWeight", {})
                        m1 = f"{weight.get('net', '')} {weight.get('uom', '')}".strip() or "Not Found"
                        
                        m2 = "Not Found"
                        for u in item.get("units", []):
                            if u.get("qtyInParent") and u.get("uom") != "CS":
                                m2 = f"{u['qtyInParent']} {u['uom']} / {u.get('parentUom', 'CS')}"
                                break
                        
                        if code not in product_db:
                            product_db[code] = {"name": "", "price": "Price Not Found", "m1": "Not Found", "m2": "Not Found"}
                        product_db[code].update({"name": name, "m1": m1, "m2": m2})

                # 3. Catch Prices
                elif "prices" in url:
                    data = await response.json()
                    
                    # 🚨 THE DATA DUMP 🚨
                    if not dumped_price:
                        with open("raw_price_dump.json", "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4)
                        print("💰 [DEBUG] Saved raw Price JSON to raw_price_dump.json")
                        dumped_price = True

                    for item in data.get("materialPrices", []):
                        code = item.get("materialNumber")
                        if not code: continue
                        
                        units = item.get("unitPrices", [])
                        price_val = "Price Not Found"
                        if units and units[0].get("price") is not None:
                            price_val = f"${units[0]['price']}"
                            
                        if code not in product_db:
                            product_db[code] = {"name": "", "price": "Price Not Found", "m1": "Not Found", "m2": "Not Found"}
                        product_db[code]["price"] = price_val
            except Exception as e: 
                pass

    page.on("response", handle_response)
    print("✅ Global Wiretap Attached. Listening to all background traffic...")

async def get_total_results_via_ocr(page):
    """Uses AI Vision to read the total result count from the screen."""
    print("👁️ [VISION] Reading total results count from the screen...")
    shot_path = "vision/harvest_start_count.png"
    os.makedirs("vision", exist_ok=True)
    
    try:
        await page.wait_for_selector(".result-text-title", timeout=5000)
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
                print(f"🎯 [VISION] Target Acquired via OCR: {total} products expected.")
                return total
    
    print("⚠️ [VISION] Could not find results count on screen. Defaulting to 9999.")
    return 9999

async def run_harvest(page):
    global target_total
    print("📡 DEPLOYING HARVESTER: Saving intercepted data...")
    log_event("HARVEST_START", {"mode": "GLOBAL_WIRETAP"})
    
    initialize_csv()
    
    # If the API didn't catch the total, use OCR as a backup
    if target_total == 9999:
        target_total = await get_total_results_via_ocr(page)

    # Flush immediately what we've already caught in memory
    for code, details in list(product_db.items()):
        if code not in written_codes and details["name"]:
            write_csv_line(code, details)
            written_codes.add(code)
    
    print(f"📦 Initial batch saved: {len(written_codes)} products.")

    # --- 🔄 SCROLL ENGINE ---
    scroll_attempts_without_new = 0
    max_empty_scrolls = 10
    last_count = len(written_codes)

    while len(written_codes) < target_total and scroll_attempts_without_new < max_empty_scrolls:
        await page.mouse.move(640, 400) # Hover center
        await force_scroll_down(page, scrolls=1)
        await asyncio.sleep(2.5) # Give API time to process and trigger our global wiretap
        
        # Check for new items in the global DB
        for code, details in list(product_db.items()):
            if code not in written_codes and details["name"]:
                write_csv_line(code, details)
                written_codes.add(code)
                if len(written_codes) % 10 == 0 or len(written_codes) == target_total:
                    print(f"📦 Progress: {len(written_codes)} / {target_total} products saved.")

        current_count = len(written_codes)
        if current_count > last_count:
            scroll_attempts_without_new = 0 
            last_count = current_count
        else:
            scroll_attempts_without_new += 1
            print(f"🔄 Waiting for more items... (Attempt {scroll_attempts_without_new}/{max_empty_scrolls})")

    final_count = len(written_codes)
    print(f"🎉 Harvest complete. Saved {final_count} out of {target_total} products to {CSV_FILE}.")
    log_event("HARVEST_END", {"total_items": final_count, "target_total": target_total})