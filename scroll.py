# FILE: scroll.py
import asyncio
import random

async def force_scroll_down(page, scrolls=1):
    """
    A highly robust, mechanical scroll engine that targets nested virtual viewports.
    No Gemini, no OS-dependent mouse wheel. Pure DOM manipulation and focused keystrokes.
    """
    for _ in range(scrolls):
        # 1. Aggressive DOM manipulation: finds the actual scrollable containers and forces their scrollTop down.
        await page.evaluate("""() => {
            const containers = document.querySelectorAll('cdk-virtual-scroll-viewport, .scroll-container, [class*="scroll"], main, .product-grid, .item-list');
            let scrolled = false;
            containers.forEach(c => {
                if (c && c.scrollHeight > c.clientHeight) {
                    c.scrollTop += (c.clientHeight || 1000) * 1.5;
                    c.dispatchEvent(new Event('scroll', { bubbles: true }));
                    scrolled = true;
                }
            });
            // Fallback to absolute window scroll
            window.scrollBy({ top: 1200, behavior: 'instant' });
        }""")
        
        await asyncio.sleep(0.5)

        # 2. Focus the container safely and press PageDown
        try:
            # CRITICAL FIX: Click the far RIGHT edge (scroll track area) 
            # to safely gain window focus without accidentally clicking product cards!
            viewport = page.viewport_size
            if viewport:
                safe_x = int(viewport['width'] - 10)
                safe_y = int(viewport['height'] * 0.5)
                await page.mouse.move(safe_x, safe_y)
                await page.mouse.click(safe_x, safe_y)
        except:
            pass

        await page.keyboard.press("PageDown")
        await asyncio.sleep(0.2)
        await page.keyboard.press("PageDown")
        
        await asyncio.sleep(random.uniform(2.0, 3.0))

async def deep_human_scan(page, kb, state, is_product_page=False):
    """Scans the page to calculate total depth."""
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
            await page.keyboard.press("End")
            await asyncio.sleep(2)
            if await page.evaluate("document.body.scrollHeight") == new_height:
                print(f"✅ Verified: Reached absolute bottom after {scrolls_taken} scrolls.")
                break
                
        last_height = new_height
        print(f"📉 Scrolled down... Page expanded (New height: {new_height}px)")
        
    kb.learn(state, "scroll_depth", {"scrolls": scrolls_taken})