#!/usr/bin/env python3
"""
the_table/client.py — Core HTTP client for The Table (table.developumaiengine.com)
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

SERVER_URL = os.environ.get("TABLE_SERVER_URL", "https://table.developumaiengine.com")
AGENT_ID = os.environ.get("TABLE_AGENT_ID", "a9e102f8b912c34d")
AGENT_KEY = os.environ.get("TABLE_AGENT_KEY", "evolum_super_secret_key_brad_ag_2026")
AGENT_NAME = os.environ.get("TABLE_AGENT_NAME", "AG")

TABLE_DIR = Path(__file__).resolve().parent
INBOX_FILE = Path(os.environ.get("TABLE_INBOX_FILE", TABLE_DIR / f"inbox_{AGENT_NAME.lower()}.json"))
OUTBOX_FILE = Path(os.environ.get("TABLE_OUTBOX_FILE", TABLE_DIR / f"outbox_{AGENT_NAME.lower()}.json"))
STATE_FILE = Path(os.environ.get("TABLE_STATE_FILE", TABLE_DIR / f"bridge_state_{AGENT_NAME.lower()}.json"))

def _request(path: str, data: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Tuple[int, Dict[str, Any]]:
    url = f"{SERVER_URL}{path}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"raw": raw}
            return resp.getcode(), parsed
    except urllib.error.HTTPError as e:
        try:
            parsed = json.loads(e.read().decode("utf-8"))
        except Exception:
            parsed = {"error": str(e)}
        return e.code, parsed
    except Exception as e:
        return 500, {"error": str(e)}

def pair() -> Tuple[Optional[str], Optional[str]]:
    """Pairs the agent with The Table server, obtaining a persistent token and mobile URL."""
    payload = {"agent_id": AGENT_ID, "key": AGENT_KEY, "name": AGENT_NAME}
    code, data = _request("/pair", payload)
    if code == 200:
        token = data.get("token")
        url = data.get("url")
        _update_state({"token": token, "url": url, "last_paired": time.time()})
        return token, url
    return None, None

def poll_server() -> List[Dict[str, Any]]:
    """Polls the server queue for unread messages sent by Brad from his phone."""
    payload = {"agent_id": AGENT_ID, "key": AGENT_KEY}
    code, data = _request("/bridge/poll", payload)
    if code == 200:
        return data.get("queued", [])
    return []

def send_reply(text: str, audio_url: Optional[str] = None) -> bool:
    """Sends a reply message back to The Table mobile chat."""
    if not text.strip():
        return False
    payload = {
        "agent_id": AGENT_ID,
        "key": AGENT_KEY,
        "text": text.strip()
    }
    if audio_url:
        payload["audio_url"] = audio_url
    code, data = _request("/bridge/reply", payload)
    if code == 200 and data.get("ok"):
        _append_outbox({"ts": time.time(), "sender": AGENT_NAME, "text": text.strip()})
        return True
    return False

def _update_state(updates: Dict[str, Any]):
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    state.update(updates)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def _append_outbox(entry: Dict[str, Any]):
    entries = []
    if OUTBOX_FILE.exists():
        try:
            entries = json.loads(OUTBOX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    entries.append(entry)
    OUTBOX_FILE.write_text(json.dumps(entries[-200:], indent=2), encoding="utf-8")

DEFAULT_NOTIFICATION_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "sound": True,
    "vibrate": True,
    "push": True,
    "volume": 0.8,
}

def get_notification_settings() -> Dict[str, Any]:
    """Retrieves current notification settings from bridge state."""
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    settings = dict(DEFAULT_NOTIFICATION_SETTINGS)
    settings.update(state.get("notifications", {}))
    return settings

def update_notification_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Updates and persists notification preferences in bridge_state.json."""
    current = get_notification_settings()
    current.update(updates)
    _update_state({"notifications": current})
    return current

def notify_completion(title: str = "Task Complete", text: str = "DUMEdb Sentinel operation finished.") -> bool:
    """Dispatches a completion notification event to The Table mobile bridge and outbox."""
    settings = get_notification_settings()
    if not settings.get("enabled", True):
        return False
    entry = {
        "ts": time.time(),
        "sender": AGENT_NAME,
        "type": "notification",
        "title": title,
        "text": text,
        "settings": settings
    }
    _append_outbox(entry)
    # Also push to server as notification event if supported
    try:
        payload = {
            "agent_id": AGENT_ID,
            "key": AGENT_KEY,
            "type": "notification",
            "title": title,
            "text": text
        }
        _request("/bridge/notify", payload, timeout=3)
    except Exception:
        pass
    return True

def get_unread_messages() -> List[Dict[str, Any]]:
    """Returns unread messages from local inbox and marks them as read."""
    if not INBOX_FILE.exists():
        return []
    try:
        inbox = json.loads(INBOX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    
    unread = [m for m in inbox if not m.get("read", False)]
    if unread:
        for m in inbox:
            m["read"] = True
        INBOX_FILE.write_text(json.dumps(inbox, indent=2), encoding="utf-8")
    return unread

def add_to_inbox(messages: List[Dict[str, Any]]):
    """Appends newly crawled server messages to the local inbox."""
    if not messages:
        return
    existing = []
    if INBOX_FILE.exists():
        try:
            existing = json.loads(INBOX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    for m in messages:
        m["read"] = False
        m["received_at"] = time.time()
        existing.append(m)
        
    INBOX_FILE.write_text(json.dumps(existing[-200:], indent=2), encoding="utf-8")
