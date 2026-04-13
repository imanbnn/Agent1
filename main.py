import asyncio
import os
import sys
import glob
import subprocess
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright
import threading
from dotenv import load_dotenv

from brain import KnowledgeBase
from actions import identify_state, apply_stealth, test_gemini_basic

load_dotenv()

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        if parsed_url.path == '/api/start':
            import states.handlers
            states.handlers.BOT_MODE = query_params.get("mode", ["search"])[0]
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "started"}')
            return

        if self.path == '/' or self.path == '/dashboard.html':
            try:
                with open('dashboard.html', 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
            return

        if self.path.startswith('/status.json'):
            try:
                with open('status.json', 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"state": "idle", "message": "Waiting...", "current": 0, "total": 0}')
            return
            
        if self.path.startswith('/dashboard_images/'):
            try:
                with open(self.path[1:], 'rb') as f:
                    self.send_response(200)
                    if self.path.endswith('.jpg') or self.path.endswith('.jpeg'):
                        self.send_header('Content-type', 'image/jpeg')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        # 🛡️ FIX: Handles massive URL lists safely
        if self.path == '/api/start':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)

            import states.handlers
            custom_urls = data.get("urls", [])
            mode = data.get("mode", "search")

            if custom_urls:
                with open("active_search_queue.json", "w") as f:
                    json.dump({"terms": custom_urls}, f)
                states.handlers.BOT_MODE = "custom_search"
            else:
                states.handlers.BOT_MODE = mode

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "started"}')
            return

def run_server():
    server = HTTPServer(('localhost', 8001), DashboardHandler)
    server.serve_forever()

async def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    from harvester import generate_html_dashboard, update_status
    generate_html_dashboard()
    await test_gemini_basic()

    print("\n==================================================")
    print("🌐 [DASHBOARD ACTIVE] Control Panel available at:")
    print("👉 http://localhost:8001/dashboard.html")
    print("==================================================\n")

    update_status("idle", "Awaiting signal from Dashboard Control Panel...", 0, 0)
    
    import states.handlers
    states.handlers.BOT_MODE = "idle"
    while states.handlers.BOT_MODE == "idle":
        await asyncio.sleep(1)

    print(f"🚀 Launching Bot ({states.handlers.BOT_MODE.upper()})...")

    os.makedirs("videos", exist_ok=True)
    
    for f in glob.glob("videos/*.webm"):
        try: os.remove(f)
        except: pass

    kb = KnowledgeBase()
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
            
            context = await browser.new_context(
                no_viewport=True,
                record_video_dir="videos/",
                record_video_size={"width": 1280, "height": 720}
            )
            
            page = await context.new_page()
            from actions import apply_stealth
            await apply_stealth(page)

            print("📍 State Changed -> login_page")
            await page.goto("https://sso.gfs.com/")
            await asyncio.sleep(3)

            while True:
                try:
                    current_state = await identify_state(page, kb)
                    
                    if current_state not in states.handlers.STATE_ROUTER:
                        print(f"❓ Unknown state '{current_state}'. Forcing redirect to dashboard...")
                        await page.goto("https://order.gfs.com/")
                        await asyncio.sleep(5)
                        continue

                    status = await states.handlers.STATE_ROUTER[current_state](page, kb)
                    if status == "stop":
                        break
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"\n⚠️ [MAIN LOOP EXCEPTION] {e}")
                    print("🔄 Attempting to recover and return to Dashboard...")
                    try:
                        await page.goto("https://order.gfs.com/", wait_until="domcontentloaded", timeout=15000)
                    except: pass
                    await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\n🛑 Manual shutdown requested.")
    finally:
        print("\n🛑 Finalizing systems...")
        generate_html_dashboard()
        update_status("idle", "Awaiting signal from Dashboard Control Panel...", 0, 0)
        
        video_files = glob.glob("videos/*.webm")
        if video_files:
            latest_video = max(video_files, key=os.path.getctime)
            target_path = "fast_debug.webm"
            print(f"\n🎬 Encoding high-speed timelapse to {target_path} (Please wait 5-10 seconds)...")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", latest_video, 
                    "-filter:v", "setpts=0.2*PTS,scale=854:480", 
                    "-r", "15", "-crf", "35", "-an", target_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("✅ Video encoding complete! (File is tiny and fast)")
                
                try: os.remove(latest_video)
                except: pass
                
            except subprocess.CalledProcessError as e:
                print(f"⚠️ ffmpeg encoding failed: {e}")
            except FileNotFoundError:
                print("⚠️ ffmpeg is not installed on your system. Skipping compression.")
            except KeyboardInterrupt:
                print("\n⚠️ Encoding interrupted by user. Raw video left in videos/ folder.")
        else:
            print("⚠️ No video file was generated by Playwright.")
            
        sys.exit(0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Process terminated by user.")
        sys.exit(0)