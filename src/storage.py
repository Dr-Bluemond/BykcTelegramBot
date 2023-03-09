import json
import os


class Storage:
    """
    """
    path = 'data/storage.json'

    def __init__(self):
        if not os.path.exists(self.path):
            self.data = {}
        else:
            self._load()

    def _save(self):
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def _load(self):
        with open(self.path, 'r') as f:
            try:
                self.data = json.load(f)
            except json.decoder.JSONDecodeError:
                self.data = {}

    def get(self, item):
        return self.data.get(item)

    def set(self, key, value):
        self.data[key] = value
        self._save()


storage = Storage()
