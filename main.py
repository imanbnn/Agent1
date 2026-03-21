import asyncio
from playwright.async_api import async_playwright
from brain import KnowledgeBase
from actions import identify_state, apply_stealth, dismiss_all_popups
from logger import log_event, log_evolution_snapshot
from states.handlers import STATE_ROUTER, handle_dynamic_page

async def main():
    kb = KnowledgeBase()
    # Log the update to the agent context file
    log_evolution_snapshot(
        "Multi-Popup Recursive Dismissal", 
        "Added dismiss_all_popups loop to handle chained overlays and automated evolution logging."
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        await apply_stealth(page)
        print("🚀 Starting Scraper with Advanced Popup Handling...")
        await page.goto("https://order.gfs.com/")

        last_state = None

        while True:
            # 1. Proactively clear any popups before identifying state
            cleared = await dismiss_all_popups(page)
            if cleared:
                print("✨ Screen cleared of popups.")

            current_state = await identify_state(page)
            
            if current_state != last_state:
                log_event("STATE_CHANGE", {"from": last_state, "to": current_state, "url": page.url})
                print(f"📍 State Changed -> {current_state}")
                last_state = current_state
                
                if current_state not in ["transitioning", "unknown_page"]:
                    await asyncio.sleep(1.5) 
                    current_state = await identify_state(page)

            if current_state in ["transitioning", "unknown_page"]:
                await asyncio.sleep(2)
                continue

            if current_state in STATE_ROUTER:
                status = await STATE_ROUTER[current_state](page, kb)
                if status == "stop": break
            elif current_state.startswith("page_"):
                await handle_dynamic_page(page, kb, current_state)
            else:
                await asyncio.sleep(2)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())