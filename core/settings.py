import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(BASE_DIR, "data", "settings.json")

DEFAULTS = {
    "round_size": 20,
    "exam_date": "",
    "ai_diagnose_enabled": True,
    "ai_overall_enabled": True,
    "similar_by_chapter_fallback": False,
    "chapter_importance": {},
}


def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULTS)
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        if not isinstance(merged.get("chapter_importance"), dict):
            merged["chapter_importance"] = {}
        return merged
    except Exception:
        return dict(DEFAULTS)


def save_settings(d):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def get(key, default=None):
    return load_settings().get(key, default)


def set_value(key, value):
    d = load_settings()
    d[key] = value
    save_settings(d)


def get_chapter_importance(chapter_name):
    d = load_settings()
    return d.get("chapter_importance", {}).get(chapter_name, 3)


def set_chapter_importance(chapter_name, value):
    d = load_settings()
    d.setdefault("chapter_importance", {})[chapter_name] = value
    save_settings(d)

