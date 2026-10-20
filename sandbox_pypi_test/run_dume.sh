#!/bin/bash
export DUME_PUBLIC_DIST=1
export DUME_HOST="0.0.0.0"
export DUME_PORT="8090"

echo "[SYSTEM] Starting DUMEdb Web Terminal on Linux / ChromeOS..."
python3 -m dume
