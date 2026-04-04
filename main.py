import asyncio
import random
import os
import glob
import shutil
import subprocess
from playwright.async_api import async_playwright
from brain import KnowledgeBase
from actions import identify_state, apply_stealth, dismiss_all_popups, deep_human_scroll
from states.handlers import STATE_ROUTER
from logger import log_event, generate_evolution_manifest, log_evolution_snapshot

async def main():
    # 📝 Self-Updating Evolution Log
    log_evolution_snapshot("Hyper-Accelerated Video", "Updated FFmpeg post-processing to 3.5x playback speed.")
    generate_evolution_manifest()
    
    kb = KnowledgeBase()
    
    async with async_playwright() as p:
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        
        # 🔴 Enable Video Recording in the Browser Context
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800}, 
            user_agent=ua,
            record_video_dir="videos/",  # Save raw videos here temporarily
            record_video_size={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        await apply_stealth(page)

        print("🚀 Launching Beefed-up Autonomous Scraper with Debug Recording...")
        await page.goto("https://order.gfs.com/")

        last_state = None
        
        try:
            while True:
                await dismiss_all_popups(page)
                current_state = await identify_state(page)
                
                if current_state != last_state:
                    log_event("STATE_CHANGE", {"from": last_state, "to": current_state})
                    print(f"📍 State Changed -> {current_state}")
                    
                    if current_state not in ["transitioning", "unknown_page"]:
                        try:
                            await page.wait_for_load_state("networkidle", timeout=5000)
                        except: 
                            pass
                        
                    await deep_human_scroll(page, kb, current_state)
                    current_state = await identify_state(page)
                    last_state = current_state

                if current_state in ["transitioning", "unknown_page"]:
                    await asyncio.sleep(2)
                    continue

                if current_state in STATE_ROUTER:
                    status = await STATE_ROUTER[current_state](page, kb)
                    if status == "stop": break
                
                await asyncio.sleep(random.uniform(1.5, 3.5))
                
        finally:
            print("\n🛑 Stopping bot. Finalizing debug video...")
            
            await context.close()
            await browser.close()
            
            # ♻️ 3.5x Speed Compression & Overwrite Logic
            video_files = glob.glob("videos/*.webm")
            if video_files:
                latest_video = max(video_files, key=os.path.getctime)
                target_path = "debug_recording.webm"
                
                print("📼 Compressing and accelerating video (3.5x speed)...")
                try:
                    # FFmpeg command: 1 / 3.5 = 0.2857
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", latest_video, "-filter:v", "setpts=0.2857*PTS", "-an", target_path],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    print(f"✅ Success! 3.5x Speed video saved to: {target_path}")
                except (subprocess.CalledProcessError, FileNotFoundError):
                    print("⚠️ FFmpeg not installed or failed. Falling back to normal 1x raw video.")
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    shutil.move(latest_video, target_path)
                    print(f"📼 Raw video saved over: {target_path}")

                for f in glob.glob("videos/*.webm"):
                    try: os.remove(f)
                    except: pass
                try: os.rmdir("videos")
                except: pass

if __name__ == "__main__":
    asyncio.run(main())