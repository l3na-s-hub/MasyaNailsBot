"""Хранение сессий записи при ожидании ответа мастера по фото.
Не зависит от MemoryStorage — переживает рестарты и сброс FSM клиентки.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from config import DATA_DIR

logger = logging.getLogger(__name__)
STORE_PATH = DATA_DIR / "pending_admin_sessions.json"
# автоочистка старше 24ч
TTL_SEC = 24 * 3600


def _load() -> dict:
    try:
        if STORE_PATH.exists():
            return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"pending sessions load: {e}")
    return {}


def _save(data: dict) -> None:
    try:
        DATA_DIR.mkdir(exist_ok=True)
        STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning(f"pending sessions save: {e}")


def save_session(client_id: int, data: dict, step: str) -> None:
    store = _load()
    # чистим старые
    now = time.time()
    store = {
        k: v for k, v in store.items()
        if isinstance(v, dict) and now - float(v.get("_ts", 0)) < TTL_SEC
    }
    payload = dict(data)
    payload["_ts"] = now
    payload["_step"] = step
    store[str(client_id)] = payload
    _save(store)


def get_session(client_id: int) -> dict | None:
    store = _load()
    item = store.get(str(client_id))
    if not item or not isinstance(item, dict):
        return None
    if time.time() - float(item.get("_ts", 0)) > TTL_SEC:
        pop_session(client_id)
        return None
    return item


def pop_session(client_id: int) -> dict | None:
    store = _load()
    item = store.pop(str(client_id), None)
    _save(store)
    return item if isinstance(item, dict) else None


def update_session(client_id: int, data: dict) -> None:
    store = _load()
    key = str(client_id)
    if key not in store:
        return
    payload = dict(data)
    payload["_ts"] = store[key].get("_ts", time.time())
    payload["_step"] = store[key].get("_step") or data.get("photo_after_step")
    store[key] = payload
    _save(store)
