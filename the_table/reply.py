#!/usr/bin/env python3
"""
the_table/reply.py — One-Line CLI & Function to Send Reply to The Table
======================================================================
Usage:
    python -m the_table.reply "Message text here"
"""

import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure parent directory is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPT_DIR.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from the_table.client import send_reply

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m the_table.reply \"Your message here\"")
        sys.exit(1)

    text = " ".join(sys.argv[1:])
    success = send_reply(text)
    if success:
        print(f"[✓] Successfully delivered reply to The Table mobile chat: {text[:60]}...")
    else:
        print("[!] Failed to deliver reply to The Table server.")
        sys.exit(1)

if __name__ == "__main__":
    main()
