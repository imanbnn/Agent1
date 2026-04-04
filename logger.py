import json
import os
import datetime

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
    """Updates the evolution log with high-level architectural changes."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"\n{'='*60}\n"
        f"SNAPSHOT: {timestamp}\n"
        f"CHANGE: {change_summary}\n"
        f"DETAILS: {technical_details}\n"
        f"{'='*60}\n"
    )
    with open("agent_code_evolution_snapshot.log", "a", encoding="utf-8") as f:
        f.write(entry)

def generate_evolution_manifest():
    """
    Bundles core logic files into the evolution log.
    This prevents agents from losing context on previous code changes.
    """
    files_to_track = ["main.py", "actions.py", "brain.py", "states/handlers.py", "logger.py"]
    manifest_path = "agent_code_evolution_snapshot.log"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not os.path.exists(manifest_path):
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write("# Evolution Log Started\n")

    with open(manifest_path, "a", encoding="utf-8") as manifest:
        manifest.write(f"\n\n# --- FULL ARCHITECTURE SNAPSHOT: {timestamp} ---\n")
        for file_path in files_to_track:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                manifest.write(f"\n# FILE: {file_path}\n{content}\n")
        manifest.write("# --- END SNAPSHOT ---\n")

async def capture_context(page, name):
    """Captures the URL and a snippet of HTML when a popup or error occurs."""
    try:
        url = page.url
        content = (await page.content())[:500]
        log_event("CONTEXT_SNAPSHOT", {"element": name, "url": url, "html": content})
    except Exception:
        log_event("CONTEXT_ERROR", {"msg": "Failed to capture page context"})