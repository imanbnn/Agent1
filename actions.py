import asyncio
import re
import os
import datetime
import shutil
from urllib.parse import urlparse
from logger import log_event, capture_context

async def apply_stealth(page):
    print("🥷 Applying Stealth Evasion techniques...")
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    await page.add_init_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    await page.add_init_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    await page.add_init_script("window.chrome = { runtime: {} };")

async def scroll_and_verify(page):
    print("📜 Verifying page depth (scrolling)...")
    last_height = await page.evaluate("document.body.scrollHeight")
    while True:
        await page.mouse.wheel(0, 800)
        await asyncio.sleep(1) 
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)

async def dismiss_all_popups(page):
    """Iteratively finds and clicks 'Close' buttons until the screen is clear."""
    popup_selectors = [
        "button:has-text('Close')", "button:has-text('Dismiss')", 
        "button:has-text('Accept')", "button:has-text('No Thanks')",
        "button:has-text('Maybe Later')", "[aria-label*='close' i]",
        ".close-button", "svg[class*='close']", "dialog button"
    ]
    
    found_any = False
    for _ in range(5): # Max 5 chained popups
        current_popup = None
        for selector in popup_selectors:
            locator = page.locator(selector).filter(has_text=re.compile(r".*", re.I)).first
            if await locator.is_visible():
                current_popup = locator
                break
        
        if current_popup:
            print(f"🧹 [CLEANUP] Dismissing visible popup...")
            await current_popup.click()
            await asyncio.sleep(1.5) # Wait for animation
            found_any = True
        else:
            break 
    return found_any

async def identify_state(page):
    try:
        url = page.url.lower()
        content = (await page.content()).lower()

        if "sso.gfs.com" in url or "okta" in url or "password" in content or "sign in" in content: 
            state = "login_page"
        elif "customer-unit-selection" in url or "select a customer" in content: 
            state = "location_selection"
        elif "search" in url: 
            state = "search_results"
        elif "order.gfs.com" in url and ("dashboard" in url or "home" in url): 
            state = "dashboard"
        elif url == "https://order.gfs.com/" or url == "https://order.gfs.com":
            return "transitioning"
        else:
            path = urlparse(url).path
            clean_path = re.sub(r'[^a-zA-Z0-9]', '_', path).strip('_')
            state = f"page_{clean_path}" if clean_path else "unknown_page"

        if state not in ["transitioning", "unknown_page"]:
            await save_state_reference(page, state)
        return state
    except Exception:
        return "transitioning"

async def save_state_reference(page, state):
    os.makedirs("vision/last_seen", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = f"vision/{state}_{timestamp}.png"
    reference_path = f"vision/last_seen/{state}_LATEST.png"
    await page.screenshot(path=history_path)
    shutil.copy(history_path, reference_path)

async def teach_and_click(page, kb, state, element, action="click", value=None):
    if state.startswith("page_"):
        await scroll_and_verify(page)

    coords = kb.get_coords(state, element)
    if not coords:
        print(f"👀 [VISION] Scanning for '{element}'...")
        auto_locator = None
        if element == "search_bar":
            auto_locator = page.locator('input[type="search"], input[placeholder*="search" i], [aria-label*="search" i]').first
        elif element == "username_field":
            auto_locator = page.locator('input[name*="user" i], input[type="email"]').first
        elif element == "password_field":
            auto_locator = page.locator('input[type="password"]').first

        if auto_locator:
            try:
                await auto_locator.wait_for(state="visible", timeout=3000)
                box = await auto_locator.bounding_box()
                if box:
                    coords = {"x": int(box["x"] + box["width"] / 2), "y": int(box["y"] + box["height"] / 2)}
                    kb.learn(state, element, coords)
                    log_event("AUTO_VISION_SUCCESS", {"element": element, "coords": coords})
            except Exception: pass

    if not coords:
        # Manual Teaching Logic remains the same [cite: 2]
        log_event("LEARNING_REQUIRED", {"state": state, "element": element})
        print(f"🎯 [TEACHING] Click the: **{element.upper()}**")
        click_res = {"x": None, "y": None}
        async def _on_click(source, x, y):
            nonlocal click_res
            click_res["x"], click_res["y"] = x, y
        try: await page.expose_binding("reportClick", _on_click)
        except: pass
        await page.add_init_script("window.addEventListener('mousedown', (e) => { if(window.reportClick) window.reportClick(e.clientX, e.clientY); }, true);")
        await page.evaluate(f"() => {{ /* UI Overlay Code */ }}") 
        while click_res["x"] is None: await asyncio.sleep(0.1)
        coords = click_res
        kb.learn(state, element, coords)

    print(f"🖱️ Action: {action} on {element} at {coords}")
    await page.mouse.click(coords['x'], coords['y'])
    if action == "type" and value:
        await asyncio.sleep(0.8)
        await page.keyboard.type(value, delay=60)
        await page.keyboard.press("Enter")