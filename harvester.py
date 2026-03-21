import asyncio
import json
import re
import os
import csv
from logger import log_event

CSV_FILE = "gfs_results.csv"

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

async def run_harvest(page):
    print("📡 DEPLOYING FINAL TECHNOLOGY: API JSON Compiler...")
    log_event("HARVEST_START", {"mode": "API_COMPILER"})
    
    initialize_csv()
    
    # In-memory database to merge /info and /prices payloads
    product_db = {}
    written_codes = set()
    target_total = 9999 

    # ⏳ Wait for page to stabilize
    print("⏳ Waiting 4 seconds for initial network requests...")
    await asyncio.sleep(4)

    # --- 🎧 THE API WIRETAP ---
    async def handle_response(response):
        nonlocal target_total
        
        if response.request.resource_type in ["fetch", "xhr"]:
            url = response.url.lower()
            
            try:
                # 1. Catch Total Results
                if "/materials/search" in url:
                    data = await response.json()
                    if "totalResults" in data:
                        target_total = int(data["totalResults"])
                        print(f"🎯 Target Acquired from API: {target_total} total products expected.")

                # 2. Catch Product Info (Name, Measurements)
                elif "/materials/info" in url:
                    data = await response.json()
                    for item in data.get("materialInfos", []):
                        code = item.get("materialNumber")
                        if not code: continue
                        
                        desc = item.get("description", {})
                        name = desc.get("en") or desc.get("fr") or "Unknown"
                        
                        # Parse Measurements (Safely defaulting to "Not Found")
                        weight = item.get("baseUomWeight", {})
                        m1 = f"{weight.get('net', '')} {weight.get('uom', '')}".strip()
                        if not m1:
                            m1 = "Not Found"
                        
                        m2 = "Not Found"
                        for u in item.get("units", []):
                            if u.get("qtyInParent") and u.get("uom") != "CS":
                                m2 = f"{u['qtyInParent']} {u['uom']} / {u.get('parentUom', 'CS')}"
                                break
                        
                        if code not in product_db:
                            product_db[code] = {"name": "", "price": "Price Not Found", "m1": "Not Found", "m2": "Not Found"}
                            
                        product_db[code]["name"] = name
                        product_db[code]["m1"] = m1
                        product_db[code]["m2"] = m2

                # 3. Catch Prices
                elif "/prices" in url:
                    data = await response.json()
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

                # 4. Check for completed products and write to CSV
                for code, details in list(product_db.items()):
                    # Instantly write if we have a name (missing prices and measurements are okay)
                    if code not in written_codes and details["name"]:
                        write_csv_line(code, details)
                        written_codes.add(code)
                        if len(written_codes) % 10 == 0 or len(written_codes) == target_total:
                            print(f"📦 Progress: {len(written_codes)} / {target_total} products saved.")
                            
            except Exception:
                pass # Ignore non-JSON or malformed responses

    # Attach listener
    page.on("response", handle_response)
    print("🎧 API Wiretap active. Scrolling to pull database records...")

    # --- 🔄 SCROLL ENGINE (Reverted to the exact 1500px jump that worked) ---
    scroll_attempts_without_new = 0
    max_empty_scrolls = 8
    last_count = 0

    while len(written_codes) < target_total and scroll_attempts_without_new < max_empty_scrolls:
        # Force the scroll
        await page.evaluate("""() => {
            const container = document.querySelector('cdk-virtual-scroll-viewport, .scroll-container') || window;
            container.scrollBy(0, 1500);
        }""")
        await page.mouse.wheel(0, 1500)

        # Wait for API to respond
        await asyncio.sleep(3.5)
        
        current_count = len(written_codes)
        if current_count > last_count:
            scroll_attempts_without_new = 0 # Reset timeout if we found new items
            last_count = current_count
        else:
            scroll_attempts_without_new += 1
            print(f"🔄 Scrolling... waiting for API (Attempt {scroll_attempts_without_new}/{max_empty_scrolls})")

    # Cleanup
    page.remove_listener("response", handle_response)
    final_count = len(written_codes)
    
    if final_count >= target_total:
        print(f"🎉 Mission Accomplished! 100% of products ({final_count}) saved to {CSV_FILE}.")
    else:
        print(f"🏁 Harvest complete. Saved {final_count} out of {target_total} products to {CSV_FILE}.")
        
    log_event("HARVEST_END", {"total_items": final_count, "target_total": target_total})