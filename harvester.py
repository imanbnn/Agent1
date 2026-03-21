import asyncio
import csv
from logger import log_event

async def run_harvest(page, filename="gfs_results.csv"):
    log_event("HARVEST_START", {"file": filename})
    master_data = {}
    
    for i in range(25):
        raw_text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        
        for idx, line in enumerate(lines):
            if line.startswith('#') and any(c.isdigit() for c in line):
                iid = line.replace('#', '').strip()
                if iid not in master_data and len(iid) > 4:
                    window = lines[max(0, idx-8) : min(len(lines), idx+8)]
                    price = next((l for l in window if "$" in l and "." in l), "N/A")
                    name = next((l for l in window if len(l) > 15 and "$" not in l and "#" not in l), "Unknown")
                    master_data[iid] = {"id": iid, "name": name, "price": price}
        
        if i % 5 == 0: print(f"   📈 Items found: {len(master_data)}...")

        # Targeted scrolling for GFS
        await page.evaluate("""() => {
            const s = document.querySelector('cdk-virtual-scroll-viewport') || window;
            s.scrollBy(0, 800);
        }""")
        await asyncio.sleep(1.5)

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "price"])
        writer.writeheader()
        writer.writerows(master_data.values())
    
    log_event("HARVEST_COMPLETE", {"count": len(master_data)})
    print(f"✅ Success! Results saved to {filename}")