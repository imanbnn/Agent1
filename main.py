import asyncio
import random
from playwright.async_api import async_playwright
from brain import KnowledgeBase
from actions import identify_state, apply_stealth, dismiss_all_popups, deep_human_scroll
from states.handlers import STATE_ROUTER
from logger import log_event, generate_evolution_manifest, log_evolution_snapshot

async def main():
    # 📝 Self-Updating Evolution Log
    log_evolution_snapshot("Fix: Smart Scroll Arguments", "Passed kb and current_state to deep_human_scroll to fix TypeError.")
    generate_evolution_manifest()
    
    kb = KnowledgeBase()
    
    async with async_playwright() as p:
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 800}, user_agent=ua)
        page = await context.new_page()

        await apply_stealth(page)
        print("🚀 Launching Beefed-up Autonomous Scraper...")
        await page.goto("https://order.gfs.com/")

        last_state = None
        while True:
            await dismiss_all_popups(page)
            current_state = await identify_state(page)
            
            if current_state != last_state:
                log_event("STATE_CHANGE", {"from": last_state, "to": current_state})
                print(f"📍 State Changed -> {current_state}")
                
                if current_state not in ["transitioning", "unknown_page"]:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except: 
                        pass # Network idle timeout is common, proceed anyway
                    
                    # 📜 Pass the KB and State so the bot can use its memory
                    await deep_human_scroll(page, kb, current_state)
                    current_state = await identify_state(page)
                
                last_state = current_state

            if current_state in ["transitioning", "unknown_page"]:
                await asyncio.sleep(2)
                continue

            if current_state in STATE_ROUTER:
                status = await STATE_ROUTER[current_state](page, kb)
                if status == "stop": break
            
            await asyncio.sleep(random.uniform(1.5, 3.5))

if __name__ == "__main__":
    asyncio.run(main())