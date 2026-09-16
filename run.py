"""Start the race server and the terminal. Then open the page (cd web && npm run dev) at http://localhost:3000."""
import argparse
import threading
import time

import uvicorn

from server import console
from server.api import app, engine


def main():
    parser = argparse.ArgumentParser(description="F1 Strategy Agents")
    parser.add_argument("--seed", type=int, default=42, help="same seed = same race")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    engine.restart(args.seed)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started and thread.is_alive():
        time.sleep(0.05)
    if not server.started:
        raise SystemExit(f"Could not start the server on port {args.port} (is it already in use?)")

    console.run(engine)
    server.should_exit = True
    thread.join(timeout=5)


if __name__ == "__main__":
    main()
