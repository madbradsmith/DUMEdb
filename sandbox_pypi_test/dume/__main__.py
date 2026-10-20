import os
import sys
import uvicorn
from dume.server.app import app

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    """CLI Entrypoint for running DUMEdb server."""
    host = os.environ.get("DUME_HOST", "0.0.0.0")
    port = int(os.environ.get("DUME_PORT", "8090"))
    display_host = "localhost" if host == "0.0.0.0" else host
    print("=======================================================", flush=True)
    print("DUMEdb Studio v1 is Live!", flush=True)
    print(f"Inspector UI: http://{display_host}:{port}/inspector/index.html", flush=True)
    print(f"Proxy Gateway: http://{display_host}:{port}/v1", flush=True)
    print("=======================================================", flush=True)
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
