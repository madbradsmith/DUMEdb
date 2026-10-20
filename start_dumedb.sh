#!/usr/bin/env bash
# ==============================================================================
# DUMEdb Studio — Universal Linux & POSIX Launcher
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

PORT="${1:-${DUME_PORT:-8095}}"
export DUME_PORT="$PORT"
export DUME_HOST="0.0.0.0"

echo "⚡ Starting DUMEdb Engine (Linux / POSIX) on port $PORT..."

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
elif command -v uv &> /dev/null; then
    PYTHON_EXEC="uv run python"
else
    PYTHON_EXEC="python3"
fi

mkdir -p ~/.dume/logs
nohup $PYTHON_EXEC -m dume --port "$PORT" > ~/.dume/logs/dumedb.log 2>&1 &

echo "Waiting for port $PORT..."
for i in {1..10}; do
    sleep 0.5
    if command -v curl &> /dev/null; then
        if curl -s "http://127.0.0.1:$PORT/health" > /dev/null; then
            break
        fi
    fi
done

echo "DUME Studio active at: http://localhost:$PORT/inspector/index.html"
if command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:$PORT/inspector/index.html"
fi

