import asyncio
import os
from dotenv import load_dotenv
from actions import teach_and_click
from harvester import run_harvest

load_dotenv()

USERNAME = os.getenv("GFS_USERNAME")
PASSWORD = os.getenv("GFS_PASSWORD")
PRODUCT = os.getenv("GFS_DEFAULT_PRODUCT", "Butter") 

async def handle_popup_active(page, kb):
    print("🚨 Popup detected blocking the screen!")
    await teach_and_click(page, kb, "popup_active", "close_popup_btn", "click")
    await asyncio.sleep(3) 
    return "continue"

async def handle_login_page(page, kb):
    content = (await page.content()).lower()
    target = "password_field" if 'type="password"' in content else "username_field"
    val = PASSWORD if 'type="password"' in content else USERNAME
    if not val:
        print("⚠️ ERROR: Missing credentials! Check your .env file.")
        return "stop"
    await teach_and_click(page, kb, "login_page", target, "type", val)
    await asyncio.sleep(5)
    return "continue"

async def handle_location_selection(page, kb):
    await teach_and_click(page, kb, "location_selection", "brera_row")
    await asyncio.sleep(5)
    return "continue"

async def handle_dashboard(page, kb):
    # 🥋 THE SWAT: Press Escape to clear any unreadable visual popups
    print("🧹 Pressing 'Escape' to clear potential hidden popups...")
    await page.keyboard.press("Escape")
    await asyncio.sleep(1) # Let the popup animate away
    
    await teach_and_click(page, kb, "dashboard", "search_bar", "type", PRODUCT)
    await asyncio.sleep(8)
    return "continue"

# 👇 FIX: Renamed from handle_search_results to handle_product_page
async def handle_product_page(page, kb):
    print("🛒 Product page identified. Starting harvest...")
    await run_harvest(page)
    return "stop"

async def handle_dynamic_page(page, kb, current_state):
    action_directive = kb.get_coords(current_state, "__target_action__")
    if action_directive:
        el = action_directive["element"]
        act = action_directive["action"]
        val = action_directive["value"]
        await teach_and_click(page, kb, current_state, el, act, val)
        await asyncio.sleep(5)
        return "continue"

    print(f"\n🌟 [AUTONOMOUS DISCOVERY] Auto-learning new state: {current_state}")
    print("🔴 Waiting for human to click the target on the Red Overlay...")
    
    element_name = f"auto_target_for_{current_state}"
    action_type = 'click'
    val = None
        
    kb.learn(current_state, "__target_action__", {
        "element": element_name, "action": action_type, "value": val
    })
    
    await teach_and_click(page, kb, current_state, element_name, action_type, val)
    await asyncio.sleep(5)
    return "continue"

# 👇 FIX: Updated mapping to explicitly route "product_page"
STATE_ROUTER = {
    "login_page": handle_login_page,
    "location_selection": handle_location_selection,
    "dashboard": handle_dashboard,
    "product_page": handle_product_page,
    "popup_active": handle_popup_active,
}