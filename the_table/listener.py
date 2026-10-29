#!/usr/bin/env python3
"""
the_table/listener.py — Event-Driven Mobile Listener for Antigravity
===================================================================
Polls The Table for incoming messages from Brad.
As soon as a new message arrives:
1. Writes it to the local inbox (inbox.json).
2. Prints the message details to stdout.
3. Exits with code 0 immediately.

Because Antigravity automatically wakes the agent when a background task
finishes, this triggers an INSTANT, zero-token reactive wakeup!
"""

import sys
import time
import os
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure parent directory is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPT_DIR.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from the_table.client import pair, poll_server, add_to_inbox

POLL_INTERVAL = int(os.environ.get("TABLE_POLL_INTERVAL", "3"))
MAX_WAIT_SECONDS = int(os.environ.get("TABLE_MAX_WAIT", "0"))  # 0 = infinite wait until message arrives

def listen():
    token, url = pair()
    print(f"[*] The Table Listener active. Polling every {POLL_INTERVAL}s (timeout: {MAX_WAIT_SECONDS}s)...", flush=True)
    
    start_time = time.time()
    while True:
        try:
            queued = poll_server()
            if queued:
                print(f"\n[⚡] INCOMING MESSAGE RECEIVED FROM BRAD ({len(queued)}):", flush=True)
                for msg in queued:
                    text = msg.get("text", "")
                    ts = msg.get("ts", time.time())
                    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                    print(f"    [{time_str}] Brad: {text}", flush=True)
                add_to_inbox(queued)
                print("[✓] Queued in inbox.json. Waking Antigravity agent now!", flush=True)
                # Exit cleanly so Antigravity resumes execution
                sys.exit(0)
            
            if MAX_WAIT_SECONDS > 0 and time.time() - start_time > MAX_WAIT_SECONDS:
                print("[*] Listener reached cycle timeout. Exiting to allow clean re-arm.", flush=True)
                sys.exit(0)

            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("[*] Listener stopped by user.", flush=True)
            sys.exit(0)
        except BaseException as e:
            if isinstance(e, SystemExit):
                raise
            print(f"[!] Listener recovered from error: {e}", flush=True)
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    listen()

