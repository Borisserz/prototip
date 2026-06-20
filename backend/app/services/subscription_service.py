import json
import os
import uuid

from pydantic import BaseModel

SUBSCRIPTION_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'subscriptions.json')

class Subscription(BaseModel):
    id: str
    email: str
    report_type: str  # e.g., 'dashboard', 'sql_log'
    schedule: str     # e.g., 'daily', 'weekly'
    active: bool

def _load_subscriptions() -> list[dict]:
    if not os.path.exists(SUBSCRIPTION_FILE):
        return []
    with open(SUBSCRIPTION_FILE, encoding='utf-8') as f:
        return json.load(f)

def _save_subscriptions(subs: list[dict]):
    os.makedirs(os.path.dirname(SUBSCRIPTION_FILE), exist_ok=True)
    with open(SUBSCRIPTION_FILE, 'w', encoding='utf-8') as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)

def get_subscriptions() -> list[dict]:
    return _load_subscriptions()

def add_subscription(sub: dict) -> dict:
    subs = _load_subscriptions()
    sub['id'] = uuid.uuid4().hex
    if 'active' not in sub:
        sub['active'] = True
    subs.append(sub)
    _save_subscriptions(subs)
    return sub

def delete_subscription(sub_id: str) -> bool:
    subs = _load_subscriptions()
    new_subs = [s for s in subs if s.get('id') != sub_id]
    if len(subs) != len(new_subs):
        _save_subscriptions(new_subs)
        return True
    return False

def toggle_subscription(sub_id: str) -> bool:
    subs = _load_subscriptions()
    found = False
    for s in subs:
        if s.get('id') == sub_id:
            s['active'] = not s.get('active', True)
            found = True
            break
    if found:
        _save_subscriptions(subs)
        return True
    return False
