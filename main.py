import asyncio
from playwright.async_api import async_playwright
from brain import KnowledgeBase
from actions import identify_state, apply_stealth
from logger import log_event
from states.handlers import STATE_ROUTER, handle_dynamic_page

async def main():
    kb = KnowledgeBase()
    async with async_playwright() as p:
        # Pass args to hide automation flags from Chrome natively
        browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        # 🥷 INJECT STEALTH HERE
        # This masks the bot's identity before it even connects to the website
        await apply_stealth(page)

        print("🚀 Starting Modular & Scalable State Machine...")
        await page.goto("https://order.gfs.com/")

        last_state = None

        while True:
            current_state = await identify_state(page)
            
            # If the state changed, log it and WAIT A SECOND for the page to settle
            if current_state != last_state:
                log_event("STATE_CHANGE", {"from": last_state, "to": current_state, "url": page.url})
                print(f"📍 State Changed -> {current_state}")
                last_state = current_state
                
                # Give the page time to actually draw popups or transition fully
                if current_state not in ["transitioning", "unknown_page"]:
                    await asyncio.sleep(2) 
                    # Re-check the state just in case a popup appeared during those 2 seconds!
                    current_state = await identify_state(page)
                    if current_state == "popup_active":
                        print("🚨 Caught a delayed popup!")
                        last_state = "popup_active"

            # Ignore middle-of-loading states
            if current_state in ["transitioning", "unknown_page"]:
                await asyncio.sleep(2)
                continue

            # Route to hardcoded states
            if current_state in STATE_ROUTER:
                status = await STATE_ROUTER[current_state](page, kb)
                if status == "stop": break
            
            # Route to dynamically discovered states
            elif current_state.startswith("page_"):
                await handle_dynamic_page(page, kb, current_state)
            
            else:
                await asyncio.sleep(2)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())