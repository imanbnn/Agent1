# FILE: actions.py
import asyncio
import random
import os
import json
from urllib.parse import urlparse
from logger import log_event, capture_context
from PIL import Image

def get_supervisor_status():
    try:
        from google import genai
        if not os.getenv("GEMINI_API_KEY"):
            return "Offline 🔴 (Missing API Key in .env)"
        return "Online 🟢"
    except ImportError:
        return "Offline 🔴 (Missing 'google-genai' SDK)"

async def test_gemini_basic():
    print("\n🧠 [SUPERVISOR DIAGNOSTIC] Running Level 1 Gemini connection test...")
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("⚠️ [SUPERVISOR] Offline: No GEMINI_API_KEY found in your .env file!")
            return False
    
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=["Reply with exactly the word 'ONLINE' if you are active and receiving this message."]
        )
        if "ONLINE" in response.text.upper():
            print("✅ [SUPERVISOR] Level 1 Passed: Text Generation Pipeline is Active!\n")
            return True
        else:
            print(f"⚠️ [SUPERVISOR] Level 1 Failed: Unexpected response -> {response.text}\n")
            return False
    except Exception as e:
        print(f"❌ [SUPERVISOR] Connection test failed: {e}\n")
        return False

async def ask_supervisor(page, prompt, expect_json=False):
    try:
        from google import genai
        from google.genai import types
        api_key = os.getenv("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)
        os.makedirs("vision", exist_ok=True)
        shot_path = f"vision/supervisor_eyes_{random.randint(1000,9999)}.png"
        await page.screenshot(path=shot_path)
        config = types.GenerateContentConfig(response_mime_type="application/json" if expect_json else "text/plain")
        try:
            img = Image.open(shot_path)
            response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, img], config=config)
        except Exception:
            response = client.models.generate_content(model='gemini-2.5-pro', contents=[prompt, img], config=config)
        try: os.remove(shot_path)
        except: pass
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ [SUPERVISOR ERROR]: {e}")
        return None

async def gemini_double_check_totals(page):
    prompt = """
    Analyze this screenshot of a Gordon Food Service search results page.
    Look at the tab headers at the top of the item list.
    Return ONLY a valid JSON object containing the numerical totals for each tab.
    If a tab is not visible, set its value to 0.
    Format: {"all_results_total": 258, "order_guide_total": 19}
    """
    res = await ask_supervisor(page, prompt, expect_json=True)
    if res:
        try:
            clean_res = res.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_res)
        except: pass
    return None

async def identify_state(page, kb=None):
    url = page.url.lower()
    
    if kb is None:
        from brain import KnowledgeBase
        kb = KnowledgeBase()
    parsed_url = urlparse(url)
    base_path = parsed_url.netloc + parsed_url.path
    if any(x in url for x in ["sso.gfs.com", "okta"]): return "login_page"
    if "search" in url or "catalog" in url: return "search_results"
    if any(x in url for x in ["product/", "item/", "order.gfs.com/shopping"]): return "single_product"
    if "home" in url or "dashboard" in url or "categories" in url or "guides" in url: 
        return "dashboard"
    if "url_map" not in kb.data: kb.data["url_map"] = {}
    if base_path in kb.data["url_map"]: return kb.data["url_map"][base_path]
    prompt = f"""
    The bot landed on an unrecognized URL: {url}
    Look at the screenshot.
    Which internal state best describes it?
    Respond with ONLY ONE word: 'login_page', 'dashboard', 'search_results', 'single_product', 'transitioning'
    """
    ai_state = await ask_supervisor(page, prompt, expect_json=False)
    if ai_state:
        ai_state_clean = ai_state.lower().strip()
        for v in ["login_page", "dashboard", "search_results", "single_product", "transitioning"]:
            if v in ai_state_clean:
                kb.data["url_map"][base_path] = v
                kb.save()
                return v
    return "transitioning"

async def understand_page_context(page, kb):
    """Uses DOM context and Gemini to understand exactly what category of products it is viewing."""
    try:
        url = page.url
        dom_context = await page.evaluate("""() => {
            let breadcrumbs = Array.from(document.querySelectorAll('nav[aria-label="breadcrumb"] li, .breadcrumb li')).map(el => el.innerText).join(' > ');
            let title = document.title;
            let h1 = document.querySelector('h1') ? document.querySelector('h1').innerText : '';
            return {title, h1, breadcrumbs};
        }""")
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            prompt = f"""
            You are organizing a food service catalog.
            Based on this page data, what specific category of products is being shown?
            URL: {url}
            Title: {dom_context['title']}
            Header: {dom_context['h1']}
            Breadcrumbs: {dom_context['breadcrumbs']}
            Return ONLY a short string describing the category (e.g., 'Fresh Produce', 'Dairy & Eggs', 'Takeout Packaging', 'Mixed Search Results').
            """
            response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt])
            category_name = response.text.strip()
            print(f"🧠 [CONTEXT AWARENESS] Gemini identified this page as: 🏷️ {category_name}")
            kb.log_category(url, category_name)
            return category_name
        except Exception as e:
            print(f"⚠️ Context extraction via Gemini failed (Rate Limit?): {e}")
            fallback_name = dom_context.get('h1') or dom_context.get('title', '').split('|')[0].strip() or "Unknown Category"
            print(f"🔄 [LOCAL FALLBACK] Using DOM context: 🏷️ {fallback_name}")
            kb.log_category(url, fallback_name)
            return fallback_name
    except Exception as e:
        return "Unknown Category"

async def smart_sitemap_extraction(page, kb):
    """Extracts DOM links and uses Gemini (or Local Fallback) to build the exploration queue."""
    print("🕸️ Extracting raw DOM links...")
    try:
        raw_links = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href], [routerLink], [ng-href], [data-href]');
            return [...new Set(Array.from(anchors).map(a => {
                if (a.href) return a.href;
                let path = a.getAttribute('routerLink') || a.getAttribute('ng-href') || a.getAttribute('data-href');
                if (path) return new URL(path, window.location.origin).href;
                return '';
            }).filter(Boolean))];
        }""")
        valid_links = [l for l in raw_links if "gfs.com" in l and not any(junk in l.lower() for junk in ['javascript:', 'mailto:', 'logout', 'cart', 'support', 'login'])]
        if not valid_links: 
            print("⚠️ No valid DOM links found on this page to route.")
            return
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            prompt = f"""
            You are the routing brain for a web crawler.
            Review this list of URLs scraped from Gordon Food Service.
            Identify ONLY the URLs that lead to Categories, Product Lists, or Catalog sections.
            EXCLUDE individual product pages (e.g., /item/123), terms of service, or user accounts.
            Return ONLY a valid JSON object in this format: {{"valid_categories": ["url1", "url2"]}}
            URLs to analyze:
            {json.dumps(valid_links[:75])} 
            """
            config = types.GenerateContentConfig(response_mime_type="application/json")
            response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt], config=config)
            raw_json = response.text.strip()
      
            raw_json = raw_json.replace('```json', '').replace('```', '').strip()
            data = json.loads(raw_json)
            new_targets = data.get("valid_categories", [])
            added = kb.add_urls_to_queue(new_targets)
            print(f"🗺️ [SMART SITEMAP] Gemini found {len(new_targets)} valid category routes. Added {added} NEW routes to the exploration queue.")
        except Exception as e:
            print(f"⚠️ Smart sitemap extraction via Gemini failed: {e}")
            print("🔄 Falling back to Local Heuristic Router to bypass API limits...")
            new_targets = []
            for link in valid_links:
                l_lower = link.lower()
                if any(x in l_lower for x in ["/category/", "/categories", "/catalog/", "product-list"]):
                    new_targets.append(link)
            if new_targets:
                added = kb.add_urls_to_queue(new_targets)
                print(f"🗺️ [LOCAL FALLBACK] Found {len(new_targets)} valid category routes. Added {added} NEW routes.")
            else:
                print("⚠️ Local fallback found no new categories.")
    except Exception as e:
        print(f"⚠️ Link extraction failed entirely: {e}")

async def bezier_move(page, end_x, end_y, steps=15):
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
    if state in ["search_results", "login_page", "single_product", "dashboard"]: 
        return
    saved_depth = kb.get_coords(state, "scroll_depth")
    if saved_depth and "scrolls" in saved_depth:
        for _ in range(saved_depth["scrolls"]):
            await page.evaluate("window.scrollBy(0, 1000);")
            await page.keyboard.press("PageDown")
            await asyncio.sleep(random.uniform(0.3, 0.8))
        return
    last_height = await page.evaluate("document.body.scrollHeight")
    scrolls_taken = 0
    for _ in range(15):
        scrolls_taken += 1
        await page.evaluate("window.scrollBy(0, 1000);")
        await page.keyboard.press("PageDown")
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

async def apply_stealth(page):
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

async def dismiss_all_popups(page):
    selectors = [
        "button:has-text('Close')",
        "button:has-text('Dismiss')",
        "button:has-text('Just Browsing')",
        "button:has-text('No Thanks')",
        "button:has-text('Got it')",
        ".close-button",
        ".close",
        "[aria-label*='close' i]",
        "[title*='close' i]",
        "mat-icon:has-text('close')"
    ]
    dismissed_any = False
    try:
        for selector in selectors:
            locs = await page.locator(selector).all()
            for loc in locs:
                if await loc.is_visible():
                    try:
                        await loc.click(force=True, timeout=1000)
                        dismissed_any = True
                        await asyncio.sleep(0.5)
                    except: pass
        
        if dismissed_any:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
    except Exception: pass
    
    return dismissed_any

async def teach_and_click(page, kb, state, element, action="click", value=None):
    coords = kb.get_coords(state, element)
    if not coords:
        selectors = {
            "username_field": 'input[name*="user" i], input[type="email"], #okta-signin-username',
            "password_field": 'input[type="password"], #okta-signin-password',
            "search_bar": 'input[type="search"], input[placeholder*="search" i]'
        }
        if element in selectors:
            try:
                loc = page.locator(selectors[element]).first
                await loc.wait_for(state="visible", timeout=2000)
                box = await loc.bounding_box()
                if box: coords = {"x": int(box["x"] + box["width"]/2), "y": int(box["y"] + box["height"]/2)}
            except: pass
        if not coords:
            print(f"\n🚨 [CRITICAL ALERT] Bot needs coordinates for '{element}'.")
            print(f"👉 PLEASE CLICK THE '{element.upper()}' DIRECTLY ON THE BROWSER WINDOW NOW...")
            coords = await page.evaluate("""() => {
                return new Promise(resolve => {
                    const overlay = document.createElement('div');
                    overlay.style.position = 'fixed';
                    overlay.style.top = '0'; 
                    overlay.style.left = '0';
                    overlay.style.width = '100vw'; 
                    overlay.style.height = '100vh';
                    overlay.style.zIndex = '99999999';
                    overlay.style.backgroundColor = 'rgba(255, 0, 0, 0.15)';
                    overlay.style.cursor = 'crosshair';
                    overlay.addEventListener('click', (e) => {
                        e.preventDefault(); e.stopPropagation();
                        document.body.removeChild(overlay);
                        resolve({x: e.clientX, y: e.clientY});
                    });
                    document.body.appendChild(overlay);
                });
            }""")
    if coords:
        kb.learn(state, element, coords)
        await bezier_move(page, coords['x'], coords['y'])
        await human_click(page, coords['x'], coords['y'])
        if action.startswith("type") and value:
            await asyncio.sleep(0.5)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Meta+A") # Backup for Mac
            await page.keyboard.press("Backspace")
            await page.keyboard.type(value, delay=random.randint(50, 90))
            if action == "type": await page.keyboard.press("Enter")
        return True
    return False