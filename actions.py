import asyncio
import random
import re
import os
import datetime
import shutil
from urllib.parse import urlparse
from logger import log_event, capture_context
from PIL import Image, ImageChops

# --- 🧪 HUMAN PHYSICS ENGINE ---
async def bezier_move(page, end_x, end_y, steps=15):
    """Moves mouse in a curve to simulate human trackpad acceleration."""
    start_x, start_y = random.randint(0, 100), random.randint(0, 100)
    cp1_x = start_x + (end_x - start_x) * random.uniform(0.1, 0.4)
    cp1_y = start_y + (end_y - start_y) * random.uniform(0.1, 0.4)
    cp2_x = start_x + (end_x - start_x) * random.uniform(0.6, 0.9)
    cp2_y = start_y + (end_y - start_y) * random.uniform(0.6, 0.9)

    for i in range(steps + 1):
        t = i / steps
        x = (1-t)**3 * start_x + 3*(1-t)**2 * t * cp1_x + 3*(1-t) * t**2 * cp2_x + t**3 * end_x
        y = (1-t)**3 * start_y + 3*(1-t)**2 * t * cp1_y + 3*(1-t) * t**2 * cp2_y + t**3 * end_y
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.01, 0.02))

async def deep_human_scroll(page, kb, state):
    """Smart Scroll: Memorizes static page depths, but skips Product Pages for the Harvester."""
    print(f"📜 Initiating Smart Scan for state: {state}...")
    
    viewport = page.viewport_size
    if viewport:
        await page.mouse.move(viewport['width'] / 2, viewport['height'] / 2)
        
    # 🚨 THE FIX: Do not pre-scroll product pages!
    is_product_page = (state == "product_page")
    if is_product_page:
        print("🛒 Product page detected. Bypassing pre-scan so Harvester can scrape-and-scroll.")
        return

    # 1. 🧠 Memory Check for Static Pages
    saved_depth = kb.get_coords(state, "scroll_depth")
    if saved_depth and "scrolls" in saved_depth:
        known_scrolls = saved_depth["scrolls"]
        print(f"🧠 Memory active: Recalled this page needs {known_scrolls} scrolls.")
        for _ in range(known_scrolls):
            pixels = random.randint(800, 1200)
            await page.mouse.wheel(0, pixels)
            await asyncio.sleep(random.uniform(0.3, 0.8))
        print("✅ Smart Scan complete from memory.")
        return

    # 2. 🔍 Discovery Mode (First-time Static Pages)
    print("🔍 Discovering full DOM depth (Dynamic Verifier)...")
    last_height = await page.evaluate("document.body.scrollHeight")
    
    scrolls_taken = 0
    max_scrolls = 15 
    
    for _ in range(max_scrolls):
        scrolls_taken += 1
        pixels = random.randint(800, 1200)
        await page.mouse.wheel(0, pixels)
        
        await page.evaluate("""() => {
            const containers = document.querySelectorAll('.scroll-container, main');
            containers.forEach(c => c.scrollBy(0, 1000));
        }""")
        
        await asyncio.sleep(2.5) 
        
        new_height = await page.evaluate("document.body.scrollHeight")
        
        if new_height == last_height:
            print(f"✅ Verified: Reached absolute bottom after {scrolls_taken} scrolls.")
            break
        
        last_height = new_height
        print(f"📈 Page expanded... (New height: {new_height}px)")
        
    # 3. 💾 Save to Memory
    print(f"💾 Memorizing depth for {state}: {scrolls_taken} scrolls.")
    kb.learn(state, "scroll_depth", {"scrolls": scrolls_taken})

async def human_click(page, x, y):
    hx, hy = x + random.randint(-3, 3), y + random.randint(-3, 3)
    await page.mouse.move(hx, hy)
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.07, 0.18))
    await page.mouse.up()

# --- 🛡️ STEALTH & POPUPS ---
async def apply_stealth(page):
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
    """)

async def dismiss_all_popups(page):
    selectors = ["button:has-text('Close')", "button:has-text('Dismiss')", ".close", "[aria-label*='close' i]", "dialog button"]
    for _ in range(4):
        for selector in selectors:
            loc = page.locator(selector).filter(visible=True).first
            if await loc.count() > 0:
                print(f"🧹 Clearing popup: {selector}")
                box = await loc.bounding_box()
                await bezier_move(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
                await human_click(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
                await asyncio.sleep(1.2)
                return True
    return False

# --- 👁️ VISION & ENHANCED AWARENESS ---
def detect_visual_change(new_path, ref_path, threshold=5):
    if not os.path.exists(ref_path): return False
    try:
        img1, img2 = Image.open(new_path).convert('RGB'), Image.open(ref_path).convert('RGB')
        diff = ImageChops.difference(img1, img2)
        if diff.getbbox():
            diff_pixels = sum(abs(p) for p in diff.getdata())
            total_pixels = img1.size[0] * img1.size[1] * 255
            return (diff_pixels / total_pixels) * 100 > threshold
    except Exception: pass
    return False

async def identify_state(page):
    try:
        url = page.url.lower()
        
        # ⚓ Stripped down to robust URL anchors to prevent DOM-load timing errors
        is_product_page = "search" in url or "product" in url or "item" in url
        is_login = "sso.gfs.com" in url or "okta" in url
        is_home = "home" in url or "dashboard" in url

        if is_login: 
            state = "login_page"
        elif is_product_page:
            state = "product_page"
        elif is_home: 
            state = "dashboard"
        elif "order.gfs.com" in url: return "transitioning"
        else:
            path = urlparse(url).path
            clean = re.sub(r'[^a-zA-Z0-9]', '_', path).strip('_')
            state = f"page_{clean}" if clean else "unknown_page"

        if state not in ["transitioning", "unknown_page"]:
            os.makedirs("vision/last_seen", exist_ok=True)
            temp_shot, ref_shot = f"vision/{state}_temp.png", f"vision/last_seen/{state}_LATEST.png"
            await page.screenshot(path=temp_shot)
            if detect_visual_change(temp_shot, ref_shot):
                print(f"⚠️ [VISION] UI Shift detected in {state}!")
                shutil.copy(temp_shot, f"vision/{state}_DIFF_{datetime.datetime.now().strftime('%H%M%S')}.png")
            shutil.move(temp_shot, ref_shot)
        return state
    except: return "transitioning"

async def teach_and_click(page, kb, state, element, action="click", value=None):
    coords = kb.get_coords(state, element)
    if not coords:
        selectors = {
            "username_field": 'input[name*="user" i], input[type="email"]',
            "password_field": 'input[type="password"]',
            "search_bar": 'input[type="search"], input[placeholder*="search" i]'
        }
        if element in selectors:
            loc = page.locator(selectors[element]).first
            if await loc.is_visible():
                box = await loc.bounding_box()
                coords = {"x": int(box["x"] + box["width"]/2), "y": int(box["y"] + box["height"]/2)}
                kb.learn(state, element, coords)

    if coords:
        await bezier_move(page, coords['x'], coords['y'])
        await human_click(page, coords['x'], coords['y'])
        if action == "type" and value:
            await asyncio.sleep(0.5)
            await page.keyboard.type(value, delay=random.randint(50, 90))
            await page.keyboard.press("Enter")