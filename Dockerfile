FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for C extensions (e.g. lmdb)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir -e ".[mcp]"

ENV PYTHONUNBUFFERED=1
ENV DUME_STORAGE_DIR=/app/data

ENTRYPOINT ["python", "-m", "dume.mcp_server"]
