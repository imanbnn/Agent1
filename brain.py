import json
import os

class KnowledgeBase:
    def __init__(self, file_path="knowledge.json"):
        self.file_path = file_path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as f:
                return json.load(f)
        return {}

    def learn(self, state, element, coords):
        if state not in self.data: self.data[state] = {}
        self.data[state][element] = coords
        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def get_coords(self, state, element):
        return self.data.get(state, {}).get(element)