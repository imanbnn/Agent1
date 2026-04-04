import asyncio
import os
import re
import json
from dotenv import load_dotenv
from actions import teach_and_click, build_sitemap
from harvester import run_harvest, setup_wiretap

load_dotenv()

USERNAME = os.getenv("GFS_USERNAME")
PASSWORD = os.getenv("GFS_PASSWORD")
PRODUCT = os.getenv("GFS_DEFAULT_PRODUCT", "Butter") 

# Global flags for Auto-Pilot state management
WIRETAP_ATTACHED = False
AUTO_PILOT = False
URL_QUEUE = []

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
    global WIRETAP_ATTACHED, AUTO_PILOT, URL_QUEUE
    
    if not WIRETAP_ATTACHED:
        print("📡 Deploying Global Wiretap for upcoming search...")
        await setup_wiretap(page)
        WIRETAP_ATTACHED = True

    print("🧹 Clearing workspace...")
    await page.keyboard.press("Escape")
    await asyncio.sleep(1) 
    
    print("\n📍 [STATE] Dashboard Confirmed.")
    print("👆 Awaiting manual action... Choose [SEARCH ITEM] or [AUTO-CRAWL SITEMAP]")

    await page.evaluate("""() => {
        const container = document.createElement('div');
        container.id = 'dashboard-trigger-container';
        container.style.cssText = `
            position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
            z-index: 9999999; display: flex; gap: 20px;
        `;

        const createBtn = (id, text, color) => {
            const btn = document.createElement('button');
            btn.id = id;
            btn.innerHTML = text;
            btn.style.cssText = `
                padding: 15px 30px; background: ${color}; color: white;
                font-size: 16px; font-weight: bold; border: 3px solid rgba(0,0,0,0.2);
                border-radius: 10px; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.3);
                transition: transform 0.1s;
            `;
            btn.onmousedown = () => btn.style.transform = 'scale(0.95)';
            btn.onmouseup = () => btn.style.transform = 'scale(1)';
            return btn;
        };

        const searchBtn = createBtn('btn-search', '🔍 SEARCH SINGLE ITEM', '#8e44ad');
        const crawlBtn = createBtn('btn-crawl', '🗺️ AUTO-CRAWL SITEMAP', '#c0392b'); 

        searchBtn.onclick = () => { window.dashAction = 'search'; searchBtn.innerHTML = '⏳ TYPING...'; searchBtn.style.background = '#f39c12'; };
        crawlBtn.onclick = () => { window.dashAction = 'crawl'; crawlBtn.innerHTML = '⏳ MAPPING ROUTE...'; crawlBtn.style.background = '#f39c12'; };

        container.appendChild(searchBtn);
        container.appendChild(crawlBtn);
        document.body.appendChild(container);
    }""")

    action = None
    while not action:
        action = await page.evaluate("window.dashAction || null")
        await asyncio.sleep(0.5)

    await page.evaluate("""() => {
        const container = document.getElementById('dashboard-trigger-container');
        if (container) container.remove();
        delete window.dashAction;
    }""")

    if action == "search":
        print("🔍 Proceeding with single-item search...")
        await teach_and_click(page, kb, "dashboard", "search_bar", "type", PRODUCT)
        await asyncio.sleep(8)
        return "continue"

    elif action == "crawl":
        print("🗺️ Engaging Auto-Pilot: Expanding category menus...")

        try:
            await page.locator("text=Categories").first.click(timeout=3000)
            await asyncio.sleep(2) 
        except Exception:
            print("⚠️ Could not click 'Categories', attempting standard DOM scrape...")

        print("🕸️ Spidering DOM for active category links...")
        links = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href]');
            return [...new Set(Array.from(anchors).map(a => a.href))];
        }""")

        valid_urls = []
        for link in links:
            if "gfs.com" in link and any(k in link.lower() for k in ["/category", "/shop", "/products"]):
                clean_link = link.split('?')[0].split('#')[0] 
                if clean_link not in valid_urls:
                    valid_urls.append(clean_link)

        if os.path.exists("navigation_dump.json"):
            try:
                with open("navigation_dump.json", "r", encoding="utf-8") as f:
                    nav_links = re.findall(r'"(/[a-zA-Z0-9\-\/]*category[a-zA-Z0-9\-\/]*)"', f.read())
                    for nl in nav_links:
                        full_url = "https://order.gfs.com" + nl
                        if full_url not in valid_urls:
                            valid_urls.append(full_url)
            except Exception:
                pass

        if not valid_urls:
            print("⚠️ [WARNING] No valid category URLs found. Defaulting to Search.")
            await teach_and_click(page, kb, "dashboard", "search_bar", "type", PRODUCT)
            return "continue"

        URL_QUEUE = valid_urls
        AUTO_PILOT = True
        print(f"🚀 [AUTO-PILOT] Found {len(URL_QUEUE)} targeted categories to scrape!")

        next_url = URL_QUEUE.pop(0)
        print(f"🌐 Navigating to first URL: {next_url}")
        await page.goto(next_url)
        await asyncio.sleep(5) 
        return "continue" 

async def handle_product_page(page, kb):
    global AUTO_PILOT, URL_QUEUE

    if AUTO_PILOT:
        print(f"\n🤖 [AUTO-PILOT] Auto-Scraping Category... ({len(URL_QUEUE)} pages remaining in queue)")
        
        await run_harvest(page, mode="scan")

        if URL_QUEUE:
            next_url = URL_QUEUE.pop(0)
            print(f"🤖 [AUTO-PILOT] Moving to next category in sitemap: {next_url}")
            await page.goto(next_url)
            await asyncio.sleep(5)
            return "continue"
        else:
            print("🎉 [AUTO-PILOT] Sitemap queue empty! Full site crawl is complete.")
            return "stop"

    print("\n📍 [STATE] Product Page Confirmed.")
    print("👆 Awaiting manual action... Please select a mode.")

    await page.evaluate("""() => {
        const container = document.createElement('div');
        container.id = 'manual-trigger-container';
        container.style.cssText = `
            position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
            z-index: 9999999; display: flex; gap: 15px;
        `;

        const createBtn = (id, text, color) => {
            const btn = document.createElement('button');
            btn.id = id;
            btn.innerHTML = text;
            btn.style.cssText = `
                padding: 15px 20px; background: ${color}; color: white;
                font-size: 15px; font-weight: bold; border: 3px solid rgba(0,0,0,0.2);
                border-radius: 10px; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.3);
                transition: transform 0.1s;
            `;
            btn.onmousedown = () => btn.style.transform = 'scale(0.95)';
            btn.onmouseup = () => btn.style.transform = 'scale(1)';
            return btn;
        };

        const quickDumpBtn = createBtn('btn-quick-dump', '⚡ QUICK JSON DUMP', '#2980b9'); 
        const scrollDumpBtn = createBtn('btn-scroll-dump', '🗄️ SCROLL & DUMP', '#8e44ad'); 
        const scanBtn = createBtn('btn-api-scan', '📡 FULL SCAN', '#27ae60'); 

        quickDumpBtn.onclick = () => { window.manualAction = 'quick_dump'; quickDumpBtn.innerHTML = '⏳ DUMPING...'; quickDumpBtn.style.background = '#f39c12'; };
        scrollDumpBtn.onclick = () => { window.manualAction = 'agg_dump'; scrollDumpBtn.innerHTML = '⏳ MAPPING...'; scrollDumpBtn.style.background = '#f39c12'; };
        scanBtn.onclick = () => { window.manualAction = 'scan'; scanBtn.innerHTML = '⏳ SCANNING...'; scanBtn.style.background = '#f39c12'; };

        container.appendChild(quickDumpBtn);
        container.appendChild(scrollDumpBtn);
        container.appendChild(scanBtn);
        document.body.appendChild(container);
    }""")

    action = None
    while not action:
        action = await page.evaluate("window.manualAction || null")
        await asyncio.sleep(0.5)

    print(f"📡 [COMMAND RECEIVED] Executing: {action.upper()}")
    await run_harvest(page, mode=action) 

    await page.evaluate("""() => {
        const container = document.getElementById('manual-trigger-container');
        if (container) container.remove();
        delete window.manualAction;
    }""")
    
    print(f"🎉 {action.upper()} Complete. Stopping agent.")
    return "stop"

STATE_ROUTER = {
    "login_page": handle_login_page,
    "location_selection": handle_location_selection,
    "dashboard": handle_dashboard,
    "product_page": handle_product_page,
    "popup_active": handle_popup_active,
}