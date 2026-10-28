import pytest
import json
from unittest.mock import patch, MagicMock
from dume.mcp_server import table_status, table_poll, table_reply, table_notify
from the_table.client import (
    get_notification_settings,
    update_notification_settings,
    notify_completion,
    DEFAULT_NOTIFICATION_SETTINGS
)

def test_table_status_offline():
    with patch("the_table.client.pair", side_effect=Exception("Connection refused")):
        res = table_status()
        assert "🔴 The Table Bridge Offline" in res

def test_table_status_online():
    with patch("the_table.client.pair", return_value=("mock_token_123", "https://table.developumaiengine.com/t/mock_token_123")):
        res = table_status()
        assert "🟢 The Table Mobile Bridge: ONLINE" in res
        assert "https://table.developumaiengine.com/t/ag" in res
        assert "mock_token_123" in res

def test_table_poll_no_messages():
    with patch("the_table.client.poll_server", return_value=[]), \
         patch("the_table.client.get_unread_messages", return_value=[]):
        res = table_poll()
        assert "No new unread messages" in res

def test_table_poll_with_messages():
    mock_msgs = [{"ts": 1793220000, "text": "Testing mobile voice"}]
    with patch("the_table.client.poll_server", return_value=mock_msgs), \
         patch("the_table.client.add_to_inbox"), \
         patch("the_table.client.get_unread_messages", return_value=mock_msgs):
        res = table_poll()
        assert "Testing mobile voice" in res
        assert "Brad:" in res

def test_table_reply_success():
    with patch("the_table.client.send_reply", return_value=True):
        res = table_reply("Hello back from tests!")
        assert "✅ Delivered reply" in res

def test_table_reply_failure():
    with patch("the_table.client.send_reply", return_value=False):
        res = table_reply("Failed message")
        assert "❌ Failed to deliver reply" in res

def test_notification_settings_lifecycle(tmp_path):
    mock_state_file = tmp_path / "bridge_state.json"
    with patch("the_table.client.STATE_FILE", mock_state_file):
        # Default settings
        settings = get_notification_settings()
        assert settings["enabled"] is True
        assert settings["sound"] is True
        assert settings["vibrate"] is True
        assert settings["push"] is True

        # Update settings
        updated = update_notification_settings({"sound": False, "push": False})
        assert updated["sound"] is False
        assert updated["push"] is False
        assert updated["enabled"] is True

        # Re-read
        read_back = get_notification_settings()
        assert read_back["sound"] is False
        assert read_back["push"] is False

def test_notify_completion_enabled(tmp_path):
    mock_outbox_file = tmp_path / "outbox.json"
    with patch("the_table.client.OUTBOX_FILE", mock_outbox_file), \
         patch("the_table.client._request", return_value=(200, {"ok": True})), \
         patch("the_table.client.get_notification_settings", return_value={"enabled": True}):
        ok = notify_completion("Build Done", "All tests passed")
        assert ok is True
        assert mock_outbox_file.exists()
        outbox_entries = json.loads(mock_outbox_file.read_text(encoding="utf-8"))
        assert len(outbox_entries) == 1
        assert outbox_entries[0]["title"] == "Build Done"
        assert outbox_entries[0]["type"] == "notification"

def test_notify_completion_disabled():
    with patch("the_table.client.get_notification_settings", return_value={"enabled": False}):
        ok = notify_completion("Build Done", "All tests passed")
        assert ok is False

def test_table_notify_tool_success():
    with patch("the_table.client.notify_completion", return_value=True):
        res = table_notify("Deploy Complete", "Release v1.2.2 is live.")
        assert "🔔 Completion alert sent to The Table" in res
        assert "Deploy Complete" in res

def test_table_notify_tool_disabled():
    with patch("the_table.client.notify_completion", return_value=False):
        res = table_notify("Deploy Complete", "Release v1.2.2 is live.")
        assert "⚠️ Notification disabled in settings" in res


