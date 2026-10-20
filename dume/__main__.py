import os
import sys
import argparse
import uvicorn
from dume.onboarding import load_user_config


def resolve_port(cli_port: int = None) -> int:
    """Resolves the active port: CLI argument > DUME_PORT/PORT env > dume_config.json > 8095 default."""
    if cli_port:
        return int(cli_port)
    env_port = os.environ.get("DUME_PORT") or os.environ.get("PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
    try:
        cfg = load_user_config()
        if hasattr(cfg, "port") and cfg.port:
            return int(cfg.port)
    except Exception:
        pass
    return 8095


def main():
    """CLI Entrypoint for running DUMEdb server with configurable port (default 8095)."""
    parser = argparse.ArgumentParser(description="DUMEdb — Deterministic Unit-Record Memory Engine")
    parser.add_argument("pos_port", nargs="?", type=int, help="Optional port number (default: 8095)")
    parser.add_argument("-p", "--port", type=int, default=None, help="Server port (default: 8095)")
    parser.add_argument("--host", type=str, default=None, help="Server host (default: 0.0.0.0 or DUME_HOST)")
    args, unknown = parser.parse_known_args()

    chosen_port = args.port or args.pos_port
    port = resolve_port(chosen_port)
    host = args.host or os.environ.get("DUME_HOST", "0.0.0.0")

    # Keep environment variable in sync so child processes/subsystems know the port
    os.environ["DUME_PORT"] = str(port)

    try:
        print(f"⚡ Starting DUMEdb Engine on http://{host}:{port} (Inspector: http://localhost:{port}/inspector/index.html)")
    except UnicodeEncodeError:
        print(f"[DUME] Starting DUMEdb Engine on http://{host}:{port} (Inspector: http://localhost:{port}/inspector/index.html)")
    uvicorn.run("dume.server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

