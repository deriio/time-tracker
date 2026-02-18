import json
import os
from unittest.mock import MagicMock

# Mock the class to avoid imports
class GoogleSheetManager:
    def __init__(self, json_path, drive_folder_id, template_file_id):
        self.CACHE_FILE = "users_cache_test.json"
        
    def get_users_v2(self, use_cache=True):
        with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def normalize_username(self, username):
        if not username: return ""
        return username.lower().replace("@", "").strip()

    def find_user(self, tg_id: str = None, username: str = None):
        users = self.get_users_v2()
        target_id = str(tg_id).strip() if tg_id else None
        
        if target_id:
            for u in users:
                # Debug print
                # print(f"Checking {u['tg_id']} vs {target_id}")
                if str(u.get("tg_id")) == target_id:
                    return u
        return None

    def get_team_settings(self, team_name: str):
        t = str(team_name).strip().lower()
        TEAM_CONFIGS = [
            {"match_key": "ташкент", "name": "Ташкент(офис)", "group_env": "TASHKENT"},
            {"match_key": "цех(офис)", "name": "Цех(офис)", "group_env": "CEH_OFFICE"},
            {"match_key": "офис", "name": "Офис", "group_env": "OFFICE"},
            {"match_key": "цех", "name": "Цех", "group_env": "WORKSHOP"},
        ]
        for config in TEAM_CONFIGS:
            if config["match_key"] in t:
                return config
        return None

# Create dummy cache
cache_data = [
  {
    "name": "Усманова Асель Камилевна",
    "username": "asel3103",
    "tg_id": "421036907",
    "role": "employee",
    "team": "офис",
    "department": "Проектный_отдел",
    "status": "active"
  }
]
with open("users_cache_test.json", "w", encoding="utf-8") as f:
    json.dump(cache_data, f, ensure_ascii=False)

def test_logic():
    sm = GoogleSheetManager(json_path="x", drive_folder_id="x", template_file_id="x")
    
    print("--- Test 1: Find User by ID ---")
    user = sm.find_user(tg_id="421036907")
    print(f"User Found: {user['name'] if user else 'None'}")
    
    if user:
        print(f"Team in DB: '{user.get('team')}'")
        print("--- Test 2: Routing Logic ---")
        settings = sm.get_team_settings(user.get('team'))
        print(f"Resolved Settings: {settings}")
        
        if settings['name'] == 'Офис':
            print("SUCCESS: Routed to Office")
        else:
            print(f"FAILURE: Routed to {settings['name']}")

if __name__ == "__main__":
    test_logic()
