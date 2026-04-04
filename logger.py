import json
import os
import datetime
import platform
import sys

def log_event(event_type, details):
    """Logs runtime data to JSONL for debugging."""
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "type": event_type,
        "details": details
    }
    with open("evolution_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

def log_evolution_snapshot(change_summary, technical_details):
    """Maintains a persistent history of every run session in CHANGELOG.md."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Log to the machine-readable JSONL
    log_event("ARCHITECTURE_UPDATE", {"summary": change_summary, "details": technical_details})
    
    # 2. Append to a persistent CHANGELOG.md
    changelog_path = "CHANGELOG.md"
    
    if not os.path.exists(changelog_path):
        with open(changelog_path, "w", encoding="utf-8") as f:
            f.write("# 🤖 Agent Architecture Changelog\n\n")
            
    # FIXED: We removed the 'if' gatekeeper. 
    # Every execution now adds a new timestamped entry to the log.
    entry = (
        f"### [{timestamp}] SESSION START\n"
        f"* **Change/Run Context:** {change_summary}\n"
        f"* **Technical Details:** {technical_details}\n\n"
    )
    with open(changelog_path, "a", encoding="utf-8") as f:
        f.write(entry)

def generate_evolution_manifest():
    """
    Bundles core logic files, the changelog, and environment context.
    Provides the ultimate 'God View' for Gemini troubleshooting.
    """
    files_to_track = [
        "CHANGELOG.md", 
        "main.py", 
        "actions.py", 
        "brain.py", 
        "harvester.py", 
        "scroll.py", 
        "states/handlers.py", 
        "logger.py"
    ]
    manifest_path = "agent_code_evolution_snapshot.log"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Overwrite the snapshot file so it is always fresh and clean
    with open(manifest_path, "w", encoding="utf-8") as manifest:
        manifest.write(f"# {'='*60}\n")
        manifest.write(f"# 🧠 GEMINI TROUBLESHOOTING MANIFEST\n")
        manifest.write(f"# GENERATED: {timestamp}\n")
        manifest.write(f"# OS: {platform.system()} {platform.release()}\n")
        manifest.write(f"# PYTHON: {sys.version.split(' ')[0]}\n")
        manifest.write(f"# {'='*60}\n\n")

        # --- 1. LOG THE BOT'S MEMORY STATE ---
        manifest.write("# --- 🧠 CURRENT KNOWLEDGE BASE (MEMORY) ---\n")
        if os.path.exists("knowledge.json"):
            try:
                with open("knowledge.json", "r") as f:
                    kb_data = json.load(f)
                    # Truncate massive sitemap arrays for brevity
                    if "sitemap" in kb_data:
                        dom_len = len(kb_data["sitemap"].get("dom_links", []))
                        xml_len = len(kb_data["sitemap"].get("xml_links", []))
                        kb_data["sitemap"]["dom_links"] = f"<... {dom_len} links hidden ...>"
                        kb_data["sitemap"]["xml_links"] = f"<... {xml_len} links hidden ...>"
                    manifest.write(json.dumps(kb_data, indent=4) + "\n")
            except Exception as e:
                manifest.write(f"# Error reading knowledge.json: {e}\n")
        else:
            manifest.write("# No knowledge.json found yet.\n")

        # --- 2. LOG DIRECTORY STRUCTURE ---
        manifest.write("\n# --- 📂 DIRECTORY STRUCTURE ---\n")
        for root, dirs, files in os.walk("."):
            if any(ignored in root for ignored in [".git", "__pycache__", "venv", "env", "videos", "vision"]):
                continue
            level = root.replace(".", "").count(os.sep)
            indent = " " * 4 * (level)
            manifest.write(f"{indent}{os.path.basename(root)}/\n")
            subindent = " " * 4 * (level + 1)
            for f in files:
                if f.endswith((".py", ".json", ".csv", ".env", ".md")):
                    manifest.write(f"{subindent}{f}\n")

        # --- 3. DUMP THE CODEBASE & CHANGELOG ---
        manifest.write(f"\n\n# --- 💻 FULL ARCHITECTURE SNAPSHOT ---\n")
        for file_path in files_to_track:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                manifest.write(f"\n# FILE: {file_path}\n{content}\n")
            else:
                manifest.write(f"\n# FILE: {file_path} (⚠️ NOT FOUND)\n")
        
        manifest.write("\n# --- END SNAPSHOT ---\n")

async def capture_context(page, name):
    """Captures the URL and a snippet of HTML when a popup or error occurs."""
    try:
        url = page.url
        content = (await page.content())[:500]
        log_event("CONTEXT_SNAPSHOT", {"element": name, "url": url, "html": content})
    except Exception:
        log_event("CONTEXT_ERROR", {"msg": "Failed to capture page context"})