import asyncio
import random
import re
import os
import datetime
import shutil
from urllib.parse import urlparse
from logger import log_event, capture_context
from PIL import Image, ImageChops
from paddleocr import PaddleOCR

# --- 🧠 VISION ENGINE INITIALIZATION ---
ocr_engine = None

def get_ocr():
    global ocr_engine
    if ocr_engine is None:
        print("🧠 Vision Engine: Booting AI Eye (PaddleOCR)...")
        ocr_engine = PaddleOCR(use_angle_cls=False, lang='en')
    return ocr_engine

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
    """Smart Scroll: Bypasses non-content pages like Login to prevent layout breaks."""
    if state in ["product_page", "login_page"]:
        print(f"⚡ {state} detected. Bypassing pre-scan to keep form stable.")
        return

    saved_depth = kb.get_coords(state, "scroll_depth")
    if saved_depth and "scrolls" in saved_depth:
        print(f"🧠 Memory active: Recalled this page needs {saved_depth['scrolls']} scrolls.")
        for _ in range(saved_depth["scrolls"]):
            await page.mouse.wheel(0, random.randint(800, 1200))
            await asyncio.sleep(random.uniform(0.3, 0.8))
        return

    last_height = await page.evaluate("document.body.scrollHeight")
    scrolls_taken = 0
    for _ in range(15):
        scrolls_taken += 1
        await page.mouse.wheel(0, random.randint(800, 1200))
        await page.evaluate("window.scrollBy(0, 1000)")
        await asyncio.sleep(2.5) 
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height: break
        last_height = new_height
        
    kb.learn(state, "scroll_depth", {"scrolls": scrolls_taken})

async def human_click(page, x, y):
    hx, hy = x + random.randint(-3, 3), y + random.randint(-3, 3)
    await page.mouse.move(hx, hy)
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.07, 0.18))
    await page.mouse.up()

# --- 🛡️ STEALTH & POPUPS ---
async def apply_stealth(page):
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

async def dismiss_all_popups(page):
    selectors = ["button:has-text('Close')", "button:has-text('Dismiss')", ".close", "[aria-label*='close' i]"]
    for selector in selectors:
        loc = page.locator(selector).filter(visible=True).first
        if await loc.count() > 0:
            print(f"🧹 Clearing popup: {selector}")
            box = await loc.bounding_box()
            await bezier_move(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
            await human_click(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
            return True
    return False

# --- 👁️ VISION & STATE AWARENESS ---
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
    url = page.url.lower()
    if any(x in url for x in ["sso.gfs.com", "okta"]): return "login_page"
    if any(x in url for x in ["search", "product", "item"]): return "product_page"
    if "home" in url or "dashboard" in url: return "dashboard"
    return "transitioning"

async def teach_and_click(page, kb, state, element, action="click", value=None):
    """Hybrid Click: Tries standard DOM, falls back to OCR, then falls back to Human."""
    coords = kb.get_coords(state, element)
    
    if not coords:
        selectors = {
            "username_field": 'input[name*="user" i], input[type="email"], #okta-signin-username',
            "password_field": 'input[type="password"], #okta-signin-password',
            "search_bar": 'input[type="search"], input[placeholder*="search" i]'
        }
        
        # PLAN A: Standard HTML Selectors
        if element in selectors:
            try:
                # First try the main page
                loc = page.locator(selectors[element]).first
                await loc.wait_for(state="visible", timeout=2000)
                box = await loc.bounding_box()
                if box:
                    coords = {"x": int(box["x"] + box["width"]/2), "y": int(box["y"] + box["height"]/2)}
            except:
                # If that fails, pierce through the iframes
                for frame in page.frames:
                    try:
                        loc = frame.locator(selectors[element]).first
                        if await loc.is_visible():
                            box = await loc.bounding_box()
                            if box:
                                coords = {"x": int(box["x"] + box["width"]/2), "y": int(box["y"] + box["height"]/2)}
                                break
                    except: pass
                
                # PLAN B: PaddleOCR Vision Fallback
                if not coords:
                    print(f"👁️ [VISION] HTML failed for {element}. Trying OCR...")
                    await asyncio.sleep(2.5) 
                    
                    shot_path = f"vision/ocr_attempt_{element}.png"
                    os.makedirs("vision", exist_ok=True)
                    await page.screenshot(path=shot_path)
                    
                    ocr = get_ocr()
                    result = ocr.ocr(shot_path)
                    
                    if result and result[0]:
                        look_for = ["Email", "Username", "Sign In", "User"] if "username" in element else ["Password"]
                        for line in result[0]:
                            text = line[1][0]
                            if any(word.lower() in text.lower() for word in look_for):
                                box = line[0]
                                offset = 40 if any(w in text.lower() for w in ["password", "email", "user"]) else 0
                                coords = {"x": int((box[0][0] + box[2][0]) / 2), "y": int((box[0][1] + box[2][1]) / 2) + offset}
                                print(f"🎯 [VISION] TARGET ACQUIRED: '{text}'! Mapping coordinates.")
                                break

                # 🚨 PLAN C: HUMAN IN THE LOOP (The Ultimate Override)
                if not coords:
                    print(f"\n🚨 [CRITICAL ALERT] Bot is blind! Cannot find {element}.")
                    print(f"👉 PLEASE CLICK THE {element.upper()} DIRECTLY ON THE BROWSER WINDOW NOW...")
                    
                    # Inject a full-screen invisible overlay to intercept the human's mouse click
                    coords = await page.evaluate("""() => {
                        return new Promise(resolve => {
                            const overlay = document.createElement('div');
                            overlay.style.position = 'fixed';
                            overlay.style.top = '0';
                            overlay.style.left = '0';
                            overlay.style.width = '100vw';
                            overlay.style.height = '100vh';
                            overlay.style.zIndex = '99999999';
                            overlay.style.backgroundColor = 'rgba(255, 0, 0, 0.15)'; // Light red tint
                            overlay.style.cursor = 'crosshair';
                            
                            overlay.addEventListener('click', (e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                document.body.removeChild(overlay);
                                resolve({x: e.clientX, y: e.clientY});
                            });
                            
                            document.body.appendChild(overlay);
                        });
                    }""")
                    
                    print(f"🤝 [HUMAN OVERRIDE] Learned coordinates at X:{coords['x']}, Y:{coords['y']}!")

    if coords:
        kb.learn(state, element, coords)
        print(f"🖱️ Moving to {element}...")
        await bezier_move(page, coords['x'], coords['y'])
        await human_click(page, coords['x'], coords['y'])
        if action.startswith("type") and value:
            await asyncio.sleep(0.5)
            await page.keyboard.type(value, delay=random.randint(50, 90))
            if action == "type": await page.keyboard.press("Enter")
        return True
        
    print(f"❌ [CRITICAL] Could not find {element} via HTML, Vision, or Human.")
    return False