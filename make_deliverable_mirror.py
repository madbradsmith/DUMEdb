import os
import shutil
from pathlib import Path

src = Path(r"c:\Users\c6182\Desktop\folders\DUMEdb-WORK")
dest = Path(r"c:\Users\c6182\Desktop\folders\DUMEdb-Deliverable")

if dest.exists():
    shutil.rmtree(dest, ignore_errors=True)
dest.mkdir(parents=True, exist_ok=True)

# Copy dume package without pycache or lmdb stores
ignore_pat = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "lmdb_store", "test_lmdb_store", "*.mdb", "*.lock", "dume_config.json"
)
shutil.copytree(src / "dume", dest / "dume", ignore=ignore_pat, dirs_exist_ok=True)

# Copy data directory with registered_schemas.json only (clean 0-state, NO lmdb_store, NO dume_config.json)
(dest / "data").mkdir(parents=True, exist_ok=True)
if (src / "data" / "registered_schemas.json").exists():
    shutil.copy2(src / "data" / "registered_schemas.json", dest / "data" / "registered_schemas.json")

# Copy presets
if (src / "dume" / "schemas" / "presets").exists():
    (dest / "dume" / "schemas" / "presets").mkdir(parents=True, exist_ok=True)

# Create Start_DUMEdb_Deliverable.bat for running on port 8095 (with optional %1 override)
bat_content = """@echo off
set DUME_PORT=%1
if "%DUME_PORT%"=="" set DUME_PORT=8095
set DUME_HOST=0.0.0.0
set DUME_STORAGE_PATH=%~dp0data\\lmdb_store
echo Starting DUMEdb Deliverable (Clean State) on port %DUME_PORT%...
start http://localhost:%DUME_PORT%/inspector/index.html
python -m dume.server.app --port %DUME_PORT%
"""
(dest / "Start_DUMEdb_Deliverable.bat").write_text(bat_content, encoding="utf-8")

# Create Mac/Linux runner
sh_content = """#!/bin/bash
PORT="${1:-${DUME_PORT:-8095}}"
export DUME_PORT="$PORT"
export DUME_HOST=0.0.0.0
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export DUME_STORAGE_PATH="$DIR/data/lmdb_store"
echo "Starting DUMEdb Deliverable (Clean State) on port $PORT..."
open "http://localhost:$PORT/inspector/index.html" 2>/dev/null || xdg-open "http://localhost:$PORT/inspector/index.html" 2>/dev/null
python3 -m dume.server.app --port "$PORT"
"""
(dest / "Start_DUMEdb_Deliverable.sh").write_text(sh_content, encoding="utf-8")

# Copy project files
for fname in ["pyproject.toml", "requirements.txt", "README.md"]:
    s = src / fname
    if s.exists():
        shutil.copy2(s, dest / fname)

print(f"SUCCESS: Deliverable mirrored to {dest}")
