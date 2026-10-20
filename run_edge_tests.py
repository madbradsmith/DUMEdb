"""
Run edge-case tests with full output capture and stale lock cleanup.
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEST_LMDB = BASE_DIR / "data" / "test_lmdb_store"
LOCK_FILE = TEST_LMDB / "lock.mdb"

# Step 1: Clear stale lock.mdb if it exists
if LOCK_FILE.exists():
    try:
        LOCK_FILE.unlink()
        print(f"[SETUP] Removed stale lock.mdb from {TEST_LMDB}")
    except PermissionError as e:
        print(f"[WARNING] Could not remove lock.mdb: {e}")
        print(f"[WARNING] This may indicate a running server still has the LMDB env open.")
        print(f"[WARNING] Tests may hang. Stop the DUMEdb server and re-run.")
else:
    print(f"[SETUP] No stale lock.mdb found. Clean state.")

# Step 2: Check if port 8090 is in use (server running)
import socket
sock_check = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
port_in_use = sock_check.connect_ex(("127.0.0.1", 8090)) == 0
sock_check.close()
print(f"[SETUP] Port 8090 in use (server running): {port_in_use}")

# Step 3: Run the edge case test suite
venv_python = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
if not Path(venv_python).exists():
    venv_python = sys.executable

print(f"\n[RUN] Starting: {venv_python} -m pytest tests/test_v1_edge_cases.py -v\n")
print("=" * 70)

result = subprocess.run(
    [venv_python, "-m", "pytest", "tests/test_v1_edge_cases.py", "-v", "--tb=short", "-x"],
    capture_output=False,
    cwd=str(BASE_DIR),
    timeout=120
)

print("=" * 70)
print(f"\n[RESULT] Exit code: {result.returncode}")
sys.exit(result.returncode)
