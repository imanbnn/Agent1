import json
import os

class KnowledgeBase:
    def __init__(self, file_path="knowledge.json"):
        self.file_path = file_path
        self.data = self._load()
        
        # Initialize Autonomous Spider Memory
        if "queue" not in self.data: self.data["queue"] = []
        if "visited" not in self.data: self.data["visited"] = []
        if "catalog_map" not in self.data: self.data["catalog_map"] = {}

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}
        
    def save(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4)

    def learn(self, state, element, coords):
        if state not in self.data: self.data[state] = {}
        self.data[state][element] = coords
        self.save()

    def get_coords(self, state, element):
        return self.data.get(state, {}).get(element)

    # --- AUTONOMOUS SPIDER METHODS ---
    def add_urls_to_queue(self, urls):
        added = 0
        for u in urls:
            clean_url = u.split('?')[0].split('#')[0] # Remove tracking params
            if clean_url not in self.data["visited"] and clean_url not in self.data["queue"]:
                self.data["queue"].append(clean_url)
                added += 1
        if added > 0:
            self.save()
        return added

    def get_next_url(self):
        while self.data["queue"]:
            url = self.data["queue"].pop(0)
            if url not in self.data["visited"]:
                self.data["visited"].append(url)
                self.save()
                return url
        return None
        
    def log_category(self, url, category_name):
        self.data["catalog_map"][url] = category_name
        self.save()