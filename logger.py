import json
import os
import datetime
import platform
import sys
import shutil

def backup_codebase(change_summary, timestamp_str):
    """Creates a physical backup of core python files."""
    history_dir = os.path.join(".history", timestamp_str)
    os.makedirs(history_dir, exist_ok=True)
    files_to_backup = ["CHANGELOG.md", "main.py", "actions.py", "brain.py", "harvester.py", "scroll.py", "logger.py"]
    for file in files_to_backup:
        if os.path.exists(file):
            shutil.copy2(file, os.path.join(history_dir, file))
    os.makedirs(os.path.join(history_dir, "states"), exist_ok=True)
    if os.path.exists("states/handlers.py"):
        shutil.copy2("states/handlers.py", os.path.join(history_dir, "states/handlers.py"))
    with open(os.path.join(history_dir, "meta.txt"), "w", encoding="utf-8") as f:
        f.write(change_summary)

def enforce_file_line_limit(filepath, max_lines, header=""):
    """Prevents log files from growing infinitely by keeping only the most recent lines."""
    if not os.path.exists(filepath): return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(filepath, "w", encoding="utf-8") as f:
                if header: f.write(header + "\n")
                f.writelines(lines[-max_lines:])
    except Exception: pass

def log_event(event_type, details):
    """Logs runtime data to JSONL and aggressively trims it."""
    log_entry = {"timestamp": datetime.datetime.now().isoformat(), "type": event_type, "details": details}
    with open("evolution_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, separators=(',', ':')) + "\n")
    enforce_file_line_limit("evolution_log.jsonl", 30)

def log_evolution_snapshot(change_summary, technical_details):
    """Updates history and triggers codebase backup."""
    now = datetime.datetime.now()
    timestamp_readable = now.strftime("%Y-%m-%d %H:%M:%S")
    backup_codebase(change_summary, now.strftime("%Y%m%d_%H%M%S"))
    log_event("ARCHITECTURE_UPDATE", {"summary": change_summary, "details": technical_details})
    
    changelog_path = "CHANGELOG.md"
    if not os.path.exists(changelog_path):
        with open(changelog_path, "w", encoding="utf-8") as f:
            f.write("# 🤖 Agent Architecture Changelog\n\n")
    entry = f"### [{timestamp_readable}] UPDATE\n* **Summary:** {change_summary}\n* **Details:** {technical_details}\n\n"
    with open(changelog_path, "a", encoding="utf-8") as f:
        f.write(entry)
        
    enforce_file_line_limit(changelog_path, 20, "# 🤖 Agent Architecture Changelog\n")

def generate_evolution_manifest():
    """Bundles logic with PRUNED logs and STRIPPED code to fit within Gemini's context window."""
    files_to_track = ["main.py", "actions.py", "brain.py", "harvester.py", "scroll.py", "states/handlers.py", "logger.py"]
    manifest_path = "agent_code_evolution_snapshot.log"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(manifest_path, "w", encoding="utf-8") as manifest:
        manifest.write(f"# GEMINI COMPRESSED MANIFEST | {timestamp}\n")
        
        # 1. PRUNED MEMORY: Minify knowledge and hide massive link lists
        if os.path.exists("knowledge.json"):
            manifest.write("\n# --- MINIFIED MEMORY ---\n")
            try:
                with open("knowledge.json", "r") as f:
                    kb = json.load(f)
                    if "sitemap" in kb:
                        kb["sitemap"]["dom_links"] = f"<{len(kb['sitemap'].get('dom_links', []))} links hidden>"
                        kb["sitemap"]["xml_links"] = f"<{len(kb['sitemap'].get('xml_links', []))} links hidden>"
                    manifest.write(json.dumps(kb, separators=(',', ':')) + "\n")
            except: pass

        # 2. PRUNED CHANGELOG
        if os.path.exists("CHANGELOG.md"):
            manifest.write("\n# --- RECENT CHANGELOG ENTRIES ---\n")
            with open("CHANGELOG.md", "r") as f:
                lines = f.readlines()
                manifest.writelines(lines[-20:])

        # 3. COMPRESSED CODEBASE: Strip empty lines and comments to save massive context limits
        manifest.write("\n# --- COMPRESSED ARCHITECTURE SNAPSHOT ---\n")
        for file_path in files_to_track:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    cleaned_code = ""
                    for line in lines:
                        stripped = line.strip()
                        # Ignore empty lines and lines that are strictly comments
                        if stripped and not stripped.startswith("#"):
                            cleaned_code += line
                    manifest.write(f"\n# FILE: {file_path}\n{cleaned_code}\n")

async def capture_context(page, name):
    try:
        url = page.url
        content = (await page.content())[:200]
        log_event("CONTEXT", {"element": name, "url": url, "html": content})
    except Exception: pass