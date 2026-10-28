import pytest
import json
from unittest.mock import patch, MagicMock
from dume.mcp_server import table_status, table_poll, table_reply

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

