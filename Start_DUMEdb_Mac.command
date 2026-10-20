#!/bin/bash
# ==============================================================================
# DUMEdb Studio — 1-Click macOS Launcher
# Launches the background LMDB engine and opens DUME Studio in the default browser.
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

PORT="${1:-${DUME_PORT:-8095}}"
export DUME_PORT="$PORT"
export DUME_HOST="0.0.0.0"

echo "=========================================================="
echo "⚡ DUME STUDIO — DETERMINISTIC STATE & MEMORY ENGINE"
echo "Platform: macOS (Darwin)"
echo "Port: $PORT"
echo "Working Directory: $DIR"
echo "=========================================================="

# Check if server is already running on configured port
if nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
    echo "🟢 DUMEdb Engine already active on http://127.0.0.1:$PORT"
else
    echo "🚀 Starting DUMEdb Engine in background on port $PORT..."
    if [ -f ".venv/bin/python" ]; then
        PYTHON_EXEC=".venv/bin/python"
    elif command -v uv &> /dev/null; then
        PYTHON_EXEC="uv run python"
    else
        PYTHON_EXEC="python3"
    fi

    # Launch detached in background
    mkdir -p ~/.dume/logs
    nohup $PYTHON_EXEC -m dume --port "$PORT" > ~/.dume/logs/dumedb.log 2>&1 &
    
    # Wait for health
    for i in {1..10}; do
        sleep 0.5
        if nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
            break
        fi
    done
fi

echo "Opening DUME Studio in your default browser..."
open "http://localhost:$PORT/inspector/index.html"

echo "----------------------------------------------------------"
echo "DUME Studio is running. To terminate, close this window or"
echo "run: kill \$(lsof -t -i:$PORT)"
echo "----------------------------------------------------------"

