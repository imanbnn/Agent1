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
    # Append to a JSON Lines file
    with open("evolution_log.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"📖 [LOG] {event_type}: {str(details)[:80]}...")

async def capture_context(page, name):
    """Captures the URL and a snippet of HTML when a popup or error occurs."""
    try:
        url = page.url
        # Grab the first 500 characters of the page HTML
        content = (await page.content())[:500]
        log_event("CONTEXT_SNAPSHOT", {"element": name, "url": url, "html": content})
    except:
        log_event("CONTEXT_ERROR", {"msg": "Failed to capture page context"})