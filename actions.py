import asyncio
import re
import os
import datetime
import shutil
from urllib.parse import urlparse
from logger import log_event, capture_context

# ---------------------------------------------------------
# 🥷 ANTI-BOT STEALTH FUNCTION
# ---------------------------------------------------------
async def apply_stealth(page):
    print("🥷 Applying Stealth Evasion techniques...")
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    await page.add_init_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    await page.add_init_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    await page.add_init_script("window.chrome = { runtime: {} };")

# ---------------------------------------------------------
# 📜 NEW: SCROLLING VERIFICATION LOGIC
# ---------------------------------------------------------
async def scroll_and_verify(page):
    """Scrolls to the bottom of the page to ensure all dynamic content is loaded."""
    print("📜 Verifying page depth (scrolling)...")
    last_height = await page.evaluate("document.body.scrollHeight")
    
    while True:
        # Scroll down 800 pixels
        await page.mouse.wheel(0, 800)
        await asyncio.sleep(1) # Wait for lazy-loading elements
        
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            print("✅ Reached the end of the page.")
            break
        last_height = new_height
    
    # Scroll back to top so coordinates aren't offset
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)

# ---------------------------------------------------------
# 👁️ STATE DETECTION & SNAPSHOT MANAGEMENT
# ---------------------------------------------------------
async def identify_state(page):
    try:
        popup_selectors = "dialog, [role='dialog'], [class*='modal'], [class*='popup'], .cdk-overlay-pane, .mat-dialog-container"
        popup_locator = page.locator(popup_selectors).first
        
        state = "unknown_page"
        if await popup_locator.is_visible(timeout=500):
            state = "popup_active"
        else:
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

        # 📸 REFERENCE SNAPSHOT LOGIC
        if state not in ["transitioning", "unknown_page"]:
            await save_state_reference(page, state)
            
        return state
    except Exception:
        return "transitioning"

async def save_state_reference(page, state):
    """Saves a timestamped log and updates the 'last_seen' reference for the state."""
    os.makedirs("vision/last_seen", exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = f"vision/{state}_{timestamp}.png"
    reference_path = f"vision/last_seen/{state}_LATEST.png"
    
    # Capture the screenshot
    await page.screenshot(path=history_path)
    
    # Update the "Last Seen" reference (overwrite previous)
    shutil.copy(history_path, reference_path)

async def teach_and_click(page, kb, state, element, action="click", value=None):
    # If we are discovering a new page, scroll it first to see everything
    if state.startswith("page_"):
        await scroll_and_verify(page)

    coords = kb.get_coords(state, element)
    
    if not coords:
        print(f"👀 [VISION] Scanning for '{element}'...")
        auto_locator = None
        if element == "search_bar":
            auto_locator = page.locator('input[type="search"], input[placeholder*="search" i], input[placeholder*="Search" i], [aria-label*="search" i]').first
        elif element == "username_field":
            auto_locator = page.locator('input[name*="user" i], input[type="email"], input[name*="email" i]').first
        elif element == "password_field":
            auto_locator = page.locator('input[type="password"]').first
        elif element == "close_popup_btn":
            auto_locator = page.locator('button:has-text("Close"), button:has-text("Dismiss"), button:has-text("Accept"), button:has-text("No Thanks"), [aria-label*="close" i], .close-button, svg[class*="close"]').first

        if auto_locator:
            try:
                await auto_locator.wait_for(state="visible", timeout=3000)
                box = await auto_locator.bounding_box()
                if box:
                    coords = {"x": int(box["x"] + box["width"] / 2), "y": int(box["y"] + box["height"] / 2)}
                    if element != "close_popup_btn": kb.learn(state, element, coords)
                    log_event("AUTO_VISION_SUCCESS", {"element": element, "coords": coords})
            except Exception: pass

    if not coords:
        log_event("LEARNING_REQUIRED", {"state": state, "element": element})
        print(f"🎯 [TEACHING] Click the: **{element.upper()}**")
        
        click_res = {"x": None, "y": None}
        async def _on_click(source, x, y):
            nonlocal click_res
            click_res["x"], click_res["y"] = x, y
        try: await page.expose_binding("reportClick", _on_click)
        except: pass

        await page.add_init_script("window.addEventListener('mousedown', (e) => { if(window.reportClick) window.reportClick(e.clientX, e.clientY); }, true);")
        await page.evaluate(f"""() => {{
            const targetElement = document.body || document.documentElement;
            const d = document.createElement('div');
            d.id = 'teaching-overlay';
            d.style = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:999999;background:rgba(255,0,0,0.2);border:10px solid red;cursor:crosshair;';
            d.innerHTML = '<div style="background:white;color:red;padding:20px;font-size:20px;font-weight:bold;border:2px solid red;box-shadow:0 0 10px black;">CLICK TO TEACH: {element.upper()}</div>';
            targetElement.appendChild(d);
            d.addEventListener('mousedown', (e) => {{ window.reportClick(e.clientX, e.clientY); d.remove(); }}, {{once:true, capture:true}});
        }}""")

        wait_cycles = 0
        while click_res["x"] is None and wait_cycles < 150:
            await asyncio.sleep(0.1)
            wait_cycles += 1
        if click_res["x"] is None: return
        coords = click_res
        if element != "close_popup_btn": kb.learn(state, element, coords)

    print(f"🖱️ Action: {action} on {element} at {coords}")
    await page.mouse.move(coords['x'], coords['y'])
    await page.mouse.click(coords['x'], coords['y'])
    if action == "type" and value:
        await asyncio.sleep(0.8)
        await page.keyboard.type(value, delay=60)
        await page.keyboard.press("Enter")