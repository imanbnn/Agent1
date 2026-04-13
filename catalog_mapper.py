import asyncio
import os
import json
import random
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load credentials
load_dotenv()
USERNAME = os.getenv("GFS_USERNAME")
PASSWORD = os.getenv("GFS_PASSWORD")

BRAIN_FILE = "gfs_catalog_brain.json"

def load_brain():
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {}

def save_brain(brain_data):
    with open(BRAIN_FILE, "w") as f:
        json.dump(brain_data, f, indent=4)

async def extract_breadcrumbs_refined(page):
    """
    Surgically extracts the full hierarchy by targeting the discovered '.crumb' class.
    Preserves exact GFS tree structure: Categories > Grocery > Flour & Baking...
    """
    try:
        # 🛡️ Wait for at least one crumb to appear to ensure Angular data has loaded
        await page.wait_for_selector('.crumb', timeout=8000)
        
        result = await page.evaluate("""() => {
            // 1. Target all elements with the 'crumb' class found in your snippet
            let nodes = Array.from(document.querySelectorAll('.crumb, .breadcrumb-item, gfs-breadcrumbs a, gfs-breadcrumbs span'));
            
            // 2. Clean and Filter
            let pathParts = nodes.map(el => el.innerText.trim())
                .filter(t => {
                    return t && 
                           t.toLowerCase() !== 'home' && 
                           t !== '>' && 
                           t !== '/' && 
                           !t.includes('results for');
                })
                .map(t => t.replace(/[>|/\\n]/g, '').trim());

            // 3. Deduplicate (Angular occasionally renders mobile/desktop crumbs simultaneously)
            let cleanPath = [];
            pathParts.forEach(part => {
                if (cleanPath.length === 0 || cleanPath[cleanPath.length - 1] !== part) {
                    cleanPath.push(part);
                }
            });

            if (cleanPath.length > 0) return cleanPath.join(' > ');
            
            // 4. Fallback to H1 Header if the crumb list is physically empty
            let h1 = document.querySelector('h1');
            if (h1) {
                let h1Text = h1.innerText.trim().replace(/^\\d+\\s+results for\\s+"/i, '').replace(/"$/g, '');
                return "Categories > " + h1Text;
            }

            return "Unknown Category";
        }""")
        return result
    except Exception:
        return "Unknown Category"

async def login_to_gfs(page):
    print("🔑 Authenticating with GFS Okta 2-Step...")
    try:
        await page.goto("https://sso.gfs.com/", wait_until="networkidle")
        
        # Step 1: Identifier
        user_loc = page.locator('input[name*="identifier" i], input[name*="user" i]').first
        await user_loc.wait_for(state="visible", timeout=10000)
        await user_loc.fill(USERNAME)
        await page.keyboard.press("Enter")
        
        # Step 2: Password
        pass_loc = page.locator('input[type="password"], input[name*="pass" i]').first
        await pass_loc.wait_for(state="visible", timeout=10000)
        await pass_loc.fill(PASSWORD)
        await page.keyboard.press("Enter")
        
        print("⏳ Redirecting to Order Portal...")
        await page.wait_for_url("**/order.gfs.com/**", timeout=25000)
        await asyncio.sleep(5) 
    except Exception as e:
        print(f"⚠️ Login Handshake failed: {e}")

async def map_catalog():
    print("🧠 Catalog Mapper v2.0: Surgical Breadcrumb Mode")
    brain = load_brain()
    
    # URL Generator for Level 2 and Level 3
    targets = [f"https://order.gfs.com/categories/results/2~{i:03d}" for i in range(1, 201)]
    targets += [f"https://order.gfs.com/categories/results/3~{i:03d}" for i in range(1, 951)]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # Headful so you can watch the breadcrumbs change
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()
        
        await login_to_gfs(page)

        mapped_count = 0
        
        for url in targets:
            clean_url = url.split('?')[0]
            
            # Skip if already mapped
            if clean_url in brain and brain[clean_url] not in ["Unknown Category", "EMPTY_CATEGORY", "INVALID_REDIRECT"]:
                continue

            try:
                print(f"➡️ Mapping: {clean_url.split('/')[-1]}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Check for "No results" page
                body_text = await page.evaluate("document.body.innerText.toLowerCase()")
                if "0 results" in body_text or "no results found" in body_text:
                    print("  ↳ 🪹 Empty")
                    brain[clean_url] = "EMPTY_CATEGORY"
                elif "/results/" not in page.url and "search" not in page.url.lower():
                    print("  ↳ 🔀 Redirected (Invalid Category)")
                    brain[clean_url] = "INVALID_REDIRECT"
                else:
                    # 🚀 Perform Refined Extraction
                    breadcrumb = await extract_breadcrumbs_refined(page)
                    print(f"  ↳ ✅ Full Path: {breadcrumb}")
                    brain[clean_url] = breadcrumb
                    mapped_count += 1
                
                save_brain(brain)
                await asyncio.sleep(random.uniform(0.5, 1.2)) # High speed
                
            except Exception as e:
                print(f"  [!] Error on {url}: {e}")
                if "Connection closed" in str(e):
                    break 

    print(f"\n🎉 Mapping Phase Complete. Mapped {mapped_count} categories.")

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("❌ Error: GFS_USERNAME/PASSWORD missing in .env")
    else:
        asyncio.run(map_catalog())