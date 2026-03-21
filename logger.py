import json
import datetime
import os

def log_event(event_type, details):
    """Logs data to 'evolution_log.jsonl' for future debugging."""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "type": event_type,
        "details": details
    }
    with open("evolution_log.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"📖 [LOG] {event_type}: {str(details)[:80]}...")

def log_evolution_snapshot(change_summary, technical_details):
    """
    Updates 'agent_code_evolution_snapshot.log' to help AI agents 
    understand the current state and 'why' of the codebase.
    """
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
    print(f"📝 [EVOLUTION] Logged update to snapshot.")

async def capture_context(page, name):
    """Captures the URL and a snippet of HTML when a popup or error occurs."""
    try:
        url = page.url
        content = (await page.content())[:500]
        log_event("CONTEXT_SNAPSHOT", {"element": name, "url": url, "html": content})
    except:
        log_event("CONTEXT_ERROR", {"msg": "Failed to capture page context"})