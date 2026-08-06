import json
import os

PROFILES_FILE = "profiles.json"

def load_profiles():
    if not os.path.exists(PROFILES_FILE):
        return {}
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao carregar profiles: {e}")
        return {}

def save_profile(name, params):
    profiles = load_profiles()
    profiles[name] = params
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"Erro ao salvar profile: {e}")
        return False

def delete_profile(name):
    profiles = load_profiles()
    if name in profiles:
        del profiles[name]
        try:
            with open(PROFILES_FILE, "w", encoding="utf-8") as f:
                json.dump(profiles, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Erro ao deletar profile: {e}")
            return False
    return False
