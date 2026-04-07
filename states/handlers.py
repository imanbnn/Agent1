# FILE: states/handlers.py
import asyncio
import os
import json
import urllib.parse
from dotenv import load_dotenv
from actions import teach_and_click, smart_sitemap_extraction, understand_page_context, dismiss_all_popups

load_dotenv()
USERNAME = os.getenv("GFS_USERNAME")
PASSWORD = os.getenv("GFS_PASSWORD")
SEARCH_TERMS_STR = os.getenv("GFS_SEARCH_TERMS", "Rice, Avocado, Chicken")

def get_fresh_queue():
    """Generates a fresh list of search terms from the environment variable."""
    return [term.strip() for term in SEARCH_TERMS_STR.split(",") if term.strip()]

SEARCH_QUEUE = get_fresh_queue()
WIRETAP_ATTACHED = False
BOT_MODE = "search"  # Modified dynamically by main.py based on Dashboard UI

async def handle_popup_active(page, kb):
    print("🚨 Popup detected blocking the screen!")
    await teach_and_click(page, kb, "popup_active", "close_popup_btn", "click")
    await asyncio.sleep(3) 
    return "continue"

async def handle_login_page(page, kb):
    print("\n🔑 Login page detected. Assessing form...")
    if not USERNAME or not PASSWORD:
        print("⚠️ ERROR: Missing credentials in .env file!")
        return "stop"
    await teach_and_click(page, kb, "login_page", "username_field", "type", USERNAME)
    await asyncio.sleep(2)
    await teach_and_click(page, kb, "login_page", "password_field", "type", PASSWORD)
    await asyncio.sleep(5)
    return "continue"

async def handle_location_selection(page, kb):
    await teach_and_click(page, kb, "location_selection", "brera_row")
    await asyncio.sleep(5)
    return "continue"

async def handle_dashboard(page, kb):
    global WIRETAP_ATTACHED, SEARCH_QUEUE
  
    if not WIRETAP_ATTACHED:
        print("📡 Deploying Global Wiretap...")
        from harvester import setup_wiretap
        await setup_wiretap(page)
        WIRETAP_ATTACHED = True
        
    print("🧹 Clearing workspace...")
    # 🧹 CRITICAL FIX: Explicitly clear the workspace of popups before interacting with the search bar
    await dismiss_all_popups(page)
    await page.keyboard.press("Escape")
    await asyncio.sleep(3) 
    
    if BOT_MODE == "explore":
        print("\n🧭 [STATE] Dashboard -> EXPLORE MODE. Mapping Catalog...")
        if "categories" not in page.url and "guides" not in page.url:
            print("🚀 Redirecting to the Categories / Guides Hub...")
            await page.goto("https://order.gfs.com/categories")
            await asyncio.sleep(5)
            
        await smart_sitemap_extraction(page, kb)
        next_url = kb.get_next_url()
        
        if next_url:
            print(f"🚀 [AUTONOMOUS ROUTING] Navigating to next queued category: {next_url}")
            await page.goto(next_url)
            await asyncio.sleep(4)
        else:
            print("⚠️ Queue empty. Ensure smart sitemap extraction found valid links.")
            await asyncio.sleep(5)
    else:
        # 🔄 CRITICAL FIX: Reload the queue continuously to monitor for changes instead of stopping
        if not SEARCH_QUEUE:
            print("🔄 Search Queue is empty! Resetting queue for continuous change monitoring...")
            SEARCH_QUEUE = get_fresh_queue()
            await asyncio.sleep(3)
            
        current_product = SEARCH_QUEUE[0] # PEEK, don't pop yet!
        print(f"\n🔍 [STATE] Dashboard -> SEARCH MODE. Target: {current_product}...")
        
        await teach_and_click(page, kb, "dashboard", "search_bar", "type", current_product)
        
        try:
            print("⏳ Waiting for page to route to search results...")
            await page.wait_for_url("**/search**", timeout=12000)
            SEARCH_QUEUE.pop(0) # Only pop if successful!
            print(f"✅ Route confirmed! Remaining in queue: {len(SEARCH_QUEUE)} items.")
        except Exception:
            print(f"⚠️ Search UI failed or timed out. Forcing direct URL navigation...")
            encoded_product = urllib.parse.quote(current_product)
            await page.goto(f"https://order.gfs.com/search?searchText={encoded_product}")
            SEARCH_QUEUE.pop(0)
            print(f"✅ Route forced! Remaining in queue: {len(SEARCH_QUEUE)} items.")
        await asyncio.sleep(4)
        
    return "continue"

async def handle_single_product(page, kb):
    print("\n⚠️ [NAVIGATION ALERT] I am inside a Single Product details page! Reversing back to the search list...")
    await page.go_back()
    await asyncio.sleep(3)
    return "continue"

async def handle_search_results(page, kb):
    global SEARCH_QUEUE
    print("\n📍 [STATE] Catalog Page Confirmed.")
    
    category_name = await understand_page_context(page, kb)
    print(f"🚜 Engaging Auto-Harvester for category: {category_name}...")
    
    from harvester import run_harvest 
    await run_harvest(page, kb=kb, state="search_results")
    
    if BOT_MODE == "explore":
        await smart_sitemap_extraction(page, kb)
        next_url = kb.get_next_url()
        
        if next_url:
            print(f"🧭 Page Harvest Complete. Remaining items in queue: {len(kb.data['queue'])}")
            print(f"🚀 [AUTONOMOUS ROUTING] Proceeding to next category: {next_url}")
            await page.goto(next_url)
            await asyncio.sleep(5)
            return "continue" 
        else:
            print("🎉 Exploration Queue Empty. Entire catalog mapped. Stopping agent.")
            return "stop"
    else:
        # Loop back to dashboard to process the next item (or reload the queue if empty)
        print(f"🧭 Search Harvest Complete. Returning to dashboard for next target...")
        await page.goto("https://order.gfs.com/")
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