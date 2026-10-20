import os
import sys
import uvicorn


def main():
    """CLI Entrypoint for running DUMEdb server."""
    host = os.environ.get("DUME_HOST", "0.0.0.0")
    port = int(os.environ.get("DUME_PORT", "8090"))
    uvicorn.run("dume.server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
