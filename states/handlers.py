import asyncio
import os
import json
import urllib.parse
from dotenv import load_dotenv
from actions import teach_and_click, smart_sitemap_extraction, understand_page_context, dismiss_all_popups

load_dotenv()
USERNAME = os.getenv("GFS_USERNAME")
PASSWORD = os.getenv("GFS_PASSWORD")

def get_fresh_queue():
    try:
        if os.path.exists("active_search_queue.json"):
            with open("active_search_queue.json", "r") as f:
                data = json.load(f)
                if "terms" in data and len(data["terms"]) > 0:
                    return [t.strip() for t in data["terms"] if t.strip()]
    except Exception as e:
        print(f"⚠️ Failed to read dynamic queue: {e}")
    return []

SEARCH_QUEUE = get_fresh_queue()
WIRETAP_ATTACHED = False
BOT_MODE = "idle"  

async def handle_popup_active(page, kb):
    print("🚨 Popup detected blocking the screen!")
    await teach_and_click(page, kb, "popup_active", "close_popup_btn", "click")
    await asyncio.sleep(3) 
    return "continue"

async def handle_login_page(page, kb):
    print("\n🔑 Login page detected. Assessing Okta 2-Step Form...")
    if not USERNAME or not PASSWORD:
        print("⚠️ ERROR: Missing credentials in .env file!")
        return "stop"
        
    try:
        user_loc = page.locator('input[name*="identifier" i], input[name*="user" i], input[type="email"], #okta-signin-username').first
        if await user_loc.is_visible(timeout=3000):
            print("👤 Typing Username...")
            await user_loc.fill(USERNAME)
            await page.keyboard.press("Enter")
            await asyncio.sleep(3) 
            
        pass_loc = page.locator('input[name*="credentials.passcode" i], input[type="password"], #okta-signin-password').first
        if await pass_loc.is_visible(timeout=3000):
            print("🔒 Typing Password...")
            await pass_loc.fill(PASSWORD)
            await page.keyboard.press("Enter")
            print("⏳ Waiting for GFS Dashboard redirect...")
            await asyncio.sleep(6)
        else:
            print("⏳ No active fields. We might be logged in already or auto-redirecting...")
            await asyncio.sleep(4)
            
    except Exception as e:
        print("⏳ No login inputs found. Waiting for redirect...")
        await asyncio.sleep(4)
        
    return "continue"

async def handle_location_selection(page, kb):
    await teach_and_click(page, kb, "location_selection", "brera_row")
    await asyncio.sleep(5)
    return "continue"

async def handle_dashboard(page, kb):
    global WIRETAP_ATTACHED, SEARCH_QUEUE, BOT_MODE
    if not WIRETAP_ATTACHED:
        print("📡 Deploying Global Wiretap...")
        from harvester import setup_wiretap
        await setup_wiretap(page)
        WIRETAP_ATTACHED = True
        
    print("🧹 Clearing workspace...")
    await dismiss_all_popups(page)
    await page.keyboard.press("Escape")
    await asyncio.sleep(3) 
    
    SEARCH_QUEUE = get_fresh_queue()
    
    if BOT_MODE == "explore":
        print("\n🧭 [STATE] Dashboard -> EXPLORE MODE. Mapping Catalog...")
        await smart_sitemap_extraction(page, kb)
        next_url = kb.get_next_url()
        
        if next_url:
            print(f"🚀 [AUTONOMOUS ROUTING] Navigating to next queued category: {next_url}")
            try:
                await page.goto(next_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"⚠️ Playwright failed to load {next_url}: {e}")
                if "Connection closed" in str(e) or page.is_closed():
                    return "stop"
            await asyncio.sleep(4)
        else:
            print("⚠️ Queue empty. Ensure smart sitemap extraction found valid links.")
            await asyncio.sleep(5)
            
    else:
        # 🛡️ FIX: Direct URL Navigation logic based on the nested JSON UI
        if not SEARCH_QUEUE:
            print("🎉 Target Queue is empty! All requested categories have been harvested.")
            return "stop"
            
        current_target_url = SEARCH_QUEUE[0] 
        print(f"\n🔍 [STATE] Dashboard -> URL NAVIGATION MODE. Target: {current_target_url}...")
        
        try:
            await page.goto(current_target_url, wait_until="domcontentloaded", timeout=60000)
            print(f"✅ Route forced for target: {current_target_url}")
        except Exception as e:
            print(f"⚠️ Force route failed: {e}")
            if "Connection closed" in str(e) or page.is_closed():
                print("🛑 [FATAL] Browser connection severed (OOM).")
                return "stop"
        await asyncio.sleep(4)
        
    return "continue"

async def handle_single_product(page, kb):
    print("\n⚠️ [NAVIGATION ALERT] I am inside a Single Product details page! Reversing back to the search list...")
    try:
        await page.go_back(wait_until="domcontentloaded", timeout=30000)
    except: pass
    await asyncio.sleep(3)
    return "continue"

async def handle_search_results(page, kb):
    global SEARCH_QUEUE
    print("\n📍 [STATE] Catalog Page Confirmed.")
    
    category_name = await understand_page_context(page, kb)
    print(f"🚜 Engaging Auto-Harvester for category: {category_name}...")
    
    from harvester import run_harvest 
    success = await run_harvest(page, kb=kb, state="search_results")
    
    if BOT_MODE == "explore":
        await smart_sitemap_extraction(page, kb)
        next_url = kb.get_next_url()
        
        if next_url:
            print(f"🧭 Page Harvest Complete. Remaining items in queue: {len(kb.data.get('queue', []))}")
            print(f"🚀 [AUTONOMOUS ROUTING] Proceeding to next category: {next_url}")
            try:
                await page.goto(next_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"⚠️ Playwright failed to load {next_url}: {e}")
                if "Connection closed" in str(e) or page.is_closed():
                    return "stop"
            await asyncio.sleep(5)
            return "continue" 
        else:
            print("🎉 Exploration Queue Empty. Entire catalog mapped. Stopping agent.")
            return "stop"
    else:
        if success:
            completed_url = SEARCH_QUEUE.pop(0)
            with open("active_search_queue.json", "w") as f:
                json.dump({"terms": SEARCH_QUEUE}, f)
            kb.data["retry_count"] = 0
            print(f"\n✅ SUCCESS! Target fully harvested. {len(SEARCH_QUEUE)} targets left in queue.")
        else:
            retry_count = kb.data.get("retry_count", 0) + 1
            kb.data["retry_count"] = retry_count
            if retry_count >= 3:
                failed_term = SEARCH_QUEUE.pop(0)
                with open("active_search_queue.json", "w") as f:
                    json.dump({"terms": SEARCH_QUEUE}, f)
                print(f"\n❌ MAX RETRIES (3) reached. Skipping to next item to prevent getting stuck.")
                kb.data["retry_count"] = 0
            else:
                print(f"\n🔄 REDO TRIGGERED: Retrying Target (Attempt {retry_count} of 3)...")
                
        print(f"🧭 Returning to dashboard for next sequence...")
        try:
            await page.goto("https://order.gfs.com/", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            if "Connection closed" in str(e) or page.is_closed():
                return "stop"
        await asyncio.sleep(5)
        return "continue"

STATE_ROUTER = {
    "login_page": handle_login_page,
    "location_selection": handle_location_selection,
    "dashboard": handle_dashboard,
    "search_results": handle_search_results,
    "single_product": handle_single_product,
    "popup_active": handle_popup_active,
}