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

POLL_INTERVAL = int(os.environ.get("TABLE_POLL_INTERVAL", "10"))

def run_crawler():
    token, url = pair()
    print("=" * 70, flush=True)
    print("📡 THE TABLE CRAWLER DAEMON ACTIVE", flush=True)
    print("=" * 70, flush=True)
    print(f"[*] Server:      https://table.developumaiengine.com", flush=True)
    print(f"[*] Mobile URL:  {url}", flush=True)
    print(f"[*] Direct Link: https://table.developumaiengine.com/t/ag", flush=True)
    print(f"[*] Interval:    {POLL_INTERVAL} seconds", flush=True)
    print("=" * 70, flush=True)
    print("[*] Crawler listening for incoming mobile messages from Brad...", flush=True)

    ticks = 0
    while True:
        try:
            queued = poll_server()
            if queued:
                print(f"\n[!] INCOMING MESSAGE FROM BRAD ({len(queued)}):", flush=True)
                for msg in queued:
                    text = msg.get("text", "")
                    ts = msg.get("ts", time.time())
                    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                    print(f"    [{time_str}] Brad: {text}", flush=True)
                add_to_inbox(queued)
                print("[✓] Injected into the_table/inbox.json for Antigravity prompt hook.", flush=True)
            
            ticks += 1
            if ticks % 10 == 0:
                print(".", end="", flush=True)

            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\n[*] Crawler stopped by operator.", flush=True)
            break
        except Exception as e:
            print(f"[!] Crawler error: {e}", flush=True)
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_crawler()
