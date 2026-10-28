#!/usr/bin/env python3
"""
the_table/crawler.py — 30-Second Background Crawler Daemon for The Table
=======================================================================
Continuously polls table.developumaiengine.com/bridge/poll every 20-30s.
Injects incoming mobile messages from Brad into the local inbox.
"""

import sys
import time
import os
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure parent directory is in pythonpath
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPT_DIR.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from the_table.client import pair, poll_server, add_to_inbox

POLL_INTERVAL = int(os.environ.get("TABLE_POLL_INTERVAL", "20"))

def run_crawler():
    token, url = pair()
    print("=" * 70)
    print("📡 THE TABLE CRAWLER DAEMON ACTIVE")
    print("=" * 70)
    print(f"[*] Server:      https://table.developumaiengine.com")
    print(f"[*] Mobile URL:  {url}")
    print(f"[*] Direct Link: https://table.developumaiengine.com/t/ag")
    print(f"[*] Interval:    {POLL_INTERVAL} seconds")
    print("=" * 70)
    print("[*] Crawler listening for incoming mobile messages from Brad...")

    ticks = 0
    while True:
        try:
            queued = poll_server()
            if queued:
                print(f"\n[!] INCOMING MESSAGE FROM BRAD ({len(queued)}):")
                for msg in queued:
                    text = msg.get("text", "")
                    ts = msg.get("ts", time.time())
                    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                    print(f"    [{time_str}] Brad: {text}")
                add_to_inbox(queued)
                print("[✓] Injected into the_table/inbox.json for Antigravity prompt hook.")
            
            ticks += 1
            if ticks % 10 == 0:
                print(".", end="", flush=True)

            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\n[*] Crawler stopped by operator.")
            break
        except Exception as e:
            print(f"[!] Crawler error: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_crawler()
