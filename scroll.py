import asyncio
import random

async def force_scroll_down(page, scrolls=1):
    """
    A dedicated scroll engine to guarantee DOWNWARD movement.
    Bypasses OS-level 'Natural Scrolling' quirks by using pure JavaScript 
    injection to target the exact GFS Angular containers.
    """
    for _ in range(scrolls):
        # 1. Move mouse to center so wheel events hit the actual products, not the margins
        viewport = page.viewport_size
        if viewport:
            await page.mouse.move(viewport['width'] / 2, viewport['height'] / 2)
        
        # 2. Playwright Wheel Backup (Positive 1000 = Down)
        await page.mouse.wheel(0, random.randint(800, 1200))
        
        # 3. 🚨 THE FIX: JavaScript Force-Scroll (Guarantees downward movement)
        await page.evaluate("""() => {
            // Scroll the main window down
            window.scrollBy({ top: 1000, behavior: 'smooth' });
            
            // Scroll GFS's specific internal containers down
            const containers = document.querySelectorAll('cdk-virtual-scroll-viewport, .scroll-container, main, .product-grid');
            containers.forEach(c => {
                c.scrollBy({ top: 1000, behavior: 'smooth' });
            });
        }""")
        
        # Wait for the network to catch up and load the next batch of products
        await asyncio.sleep(random.uniform(2.0, 3.5))

async def deep_human_scan(page, kb, state, is_product_page=False):
    """
    Scans the page to calculate total depth.
    """
    print(f"📜 Initiating Universal Downward Scan for: {state}...")
    
    if is_product_page:
        print("🛒 Product page detected. Yielding scroll control to Harvester.")
        return

    last_height = await page.evaluate("document.body.scrollHeight")
    scrolls_taken = 0
    max_scrolls = 15 
    
    for _ in range(max_scrolls):
        scrolls_taken += 1
        await force_scroll_down(page, scrolls=1)
        
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            print(f"✅ Verified: Reached absolute bottom after {scrolls_taken} scrolls.")
            break
            
        last_height = new_height
        print(f"📉 Scrolled down... Page expanded (New height: {new_height}px)")
        
    kb.learn(state, "scroll_depth", {"scrolls": scrolls_taken})