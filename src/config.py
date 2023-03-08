import json
import os


class Config:
    """
    Config is read-only
    """
    path = 'config.json'
    keys = [
        'user_agent', 'bykc_root',
        'sso_username', 'sso_password',
        'telegram_token', 'telegram_owner_id',
    ]

    def __init__(self):
        if not os.path.exists(self.path):
            self._save_default()
            print("please fill config.json")
            exit(0)
        self._load()

    def _save_default(self):
        c = {key: "" for key in self.keys}
        with open(self.path, 'w') as f:
            json.dump(c, f, indent=4)

    def _load(self):
        with open(self.path, 'r') as f:
            self.data = json.load(f)

    def get(self, item):
        if item in self.keys:
            return self.data.get(item)
        raise AttributeError


config = Config()
