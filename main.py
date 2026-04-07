import sys
import subprocess

def ensure_ai_environment():
    try:
        from google import genai
        import PIL
    except ImportError:
        print("\n📦 [SYSTEM] Gemini Supervisor SDKs are missing from THIS specific Python environment.")
        print("⚙️ Auto-installing 'google-genai' and fixing dependencies. Please wait...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "google-genai", "pillow", "requests", "urllib3", "chardet", "charset-normalizer", "--break-system-packages"])
            print("✅ [SYSTEM] AI SDKs and dependencies successfully updated! Resuming boot sequence...\n")
        except Exception as e:
            print(f"❌ [SYSTEM FATAL] Auto-install failed: {e}")
            print(f"👉 Please manually run: {sys.executable} -m pip install google-genai pillow --break-system-packages")
            sys.exit(1)

ensure_ai_environment()

import asyncio
import random
import os
import glob
import shutil
import threading
import http.server
import socketserver
from playwright.async_api import async_playwright

from brain import KnowledgeBase
from actions import identify_state, apply_stealth, dismiss_all_popups, deep_human_scroll, test_gemini_basic
from states.handlers import STATE_ROUTER
import states.handlers  # For updating BOT_MODE
from logger import log_event, generate_evolution_manifest, log_evolution_snapshot
from harvester import generate_html_dashboard, update_status

def start_server(loop, bot_trigger_event):
    """Spins up a local HTTP Server in the background to serve the Control Panel."""
    def trigger_bot(mode):
        states.handlers.BOT_MODE = mode
        loop.call_soon_threadsafe(bot_trigger_event.set)

    class APIHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass 
        def do_GET(self):
            if self.path.startswith('/api/start'):
                from urllib.parse import urlparse, parse_qs
                query = parse_qs(urlparse(self.path).query)
                mode = query.get('mode', ['search'])[0]
                trigger_bot(mode)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "started"}')
            else:
                super().do_GET()

    class ReusableTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    port = 8000
    while port <= 8010:
        try:
            httpd = ReusableTCPServer(("", port), APIHandler)
            print("\n" + "="*50)
            print("🌐 [DASHBOARD ACTIVE] Control Panel available at:")
            print(f"👉 http://localhost:{port}/dashboard.html")
            print("="*50 + "\n")
            httpd.serve_forever()
            break
        except OSError:
            port += 1
    if port > 8010:
        print("🚨 ERROR: Could not bind a port for the web server!")

async def main():
    log_evolution_snapshot("Data Optimization Update", "Migrated to google.genai, fixed circular imports, isolated phase memory dumps.")
    generate_evolution_manifest()
    generate_html_dashboard()
    
    kb = KnowledgeBase()
    loop = asyncio.get_running_loop()
    bot_trigger = asyncio.Event()
    
    server_thread = threading.Thread(target=start_server, args=(loop, bot_trigger), daemon=True)
    server_thread.start()
    
    await test_gemini_basic()

    while True:
        update_status("idle", "Ready to Launch. Select a mode to start.", 0, 0)
        print("⏳ Awaiting signal from Dashboard Control Panel...")
        await bot_trigger.wait() 
        bot_trigger.clear() 
        
        update_status("running", f"Launching Browser in {states.handlers.BOT_MODE.upper()} mode...", 0, 100)
        print(f"🚀 Launching Bot ({states.handlers.BOT_MODE.upper()})...")
        
        context = None
        browser = None
        try:
            async with async_playwright() as p:
                ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 800}, 
                    user_agent=ua,
                    record_video_dir="videos/",  
                    record_video_size={"width": 1280, "height": 800}
                )
                
                page = await context.new_page()
                await apply_stealth(page)
                await page.goto("https://order.gfs.com/")
                
                last_state = None
                while True:
                    await dismiss_all_popups(page)
                    current_state = await identify_state(page, kb)
                    
                    if current_state != last_state:
                        log_event("STATE_CHANGE", {"from": last_state, "to": current_state})
                        print(f"📍 State Changed -> {current_state}")
                        if current_state not in ["transitioning", "unknown_page"]:
                            try: await page.wait_for_load_state("networkidle", timeout=5000)
                            except: pass
                            
                    await deep_human_scroll(page, kb, current_state)
                    current_state = await identify_state(page, kb)
                    last_state = current_state
                    
                    if current_state in ["transitioning", "unknown_page"]:
                        await asyncio.sleep(2)
                        continue
                        
                    if current_state in STATE_ROUTER:
                        status = await STATE_ROUTER[current_state](page, kb)
                        if status == "stop": break
                        
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                    
        except Exception as e:
            print(f"⚠️ [CRITICAL EXCEPTION] Playwright loop broken: {e}")
            log_event("CRASH", str(e))
        finally:
            print("\n🛑 Stopping bot. Finalizing systems...")
            update_status("processing", "Saving CSV and regenerating Dashboard...", 95, 100)
            try: await context.close()
            except: pass
            try: await browser.close()
            except: pass
            
            video_files = glob.glob("videos/*.webm")
            if video_files:
                latest_video = max(video_files, key=os.path.getctime)
                target_path = "debug_recording.webm"
                try:
                    subprocess.run(["ffmpeg", "-y", "-i", latest_video, "-filter:v", "setpts=0.2857*PTS,scale=854:480", "-r", "15", "-crf", "35", "-an", target_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    if os.path.exists(target_path): os.remove(target_path)
                    shutil.move(latest_video, target_path)
                for f in glob.glob("videos/*.webm"):
                    try: os.remove(f)
                    except: pass
                try: os.rmdir("videos")
                except: pass
                
            generate_html_dashboard() 
            update_status("complete", "Harvest Complete! Dashboard updated.", 100, 100)
            await asyncio.sleep(5) 

if __name__ == "__main__":
    asyncio.run(main())