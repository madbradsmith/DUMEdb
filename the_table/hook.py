#!/usr/bin/env python3
"""
the_table/hook.py — Antigravity Lifecycle Hook Handler for The Table
===================================================================
Called by Antigravity on "Stop" or "PreInvocation" lifecycle events.
Checks for incoming mobile messages from Brad and injects them into the prompt.
"""

import sys
import json
import time
from pathlib import Path

# Ensure parent directory is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPT_DIR.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from the_table.client import poll_server, add_to_inbox, get_unread_messages

def main():
    # Read hook context from stdin
    raw_input = sys.stdin.read().strip()
    hook_data = {}
    if raw_input:
        try:
            hook_data = json.loads(raw_input)
        except Exception:
            pass

    # Determine event type (Stop hook provides 'terminationReason', PreInvocation provides 'invocationNum')
    is_stop_hook = "terminationReason" in hook_data or "fullyIdle" in hook_data

    # 1. Quick poll from server to catch any messages that just landed
    try:
        new_server_msgs = poll_server()
        if new_server_msgs:
            add_to_inbox(new_server_msgs)
    except Exception:
        pass

    # 2. Check local inbox for pending unread messages
    unread = get_unread_messages()

    if unread:
        # Build prompt injection string
        formatted_msgs = []
        for m in unread:
            text = m.get("text", "")
            ts = m.get("ts", time.time())
            time_str = time.strftime("%H:%M:%S", time.localtime(ts))
            formatted_msgs.append(f'[{time_str}] "{text}"')

        combined_text = "\n".join(formatted_msgs)
        instruction = (
            f"📱 **[THE TABLE // INCOMING MESSAGE FROM BRAD (PHONE)]**\n"
            f"{combined_text}\n\n"
            f"*(Note: You can reply back to Brad's phone by running: `python -m the_table.reply \"Your message here\"`)*"
        )

        if is_stop_hook:
            # Force agent loop to continue so agent addresses Brad's message
            out = {
                "decision": "continue",
                "reason": instruction
            }
        else:
            # PreInvocation hook injects as user message
            out = {
                "injectSteps": [
                    {
                        "userMessage": instruction
                    }
                ]
            }
    else:
        # No pending messages: allow normal execution or termination
        if is_stop_hook:
            out = {"decision": "stop"}
        else:
            out = {}

    print(json.dumps(out))

if __name__ == "__main__":
    main()
