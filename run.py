#!/usr/bin/env python
"""SI Sizing Tool Ver.2.0 — Application Entry Point

Usage:
    python run.py              # Start Flask server (default port 5000)
    python run.py --port 8080  # Custom port
    python run.py --debug      # Debug mode
    python run.py --host 127.0.0.1 --port 8080 --debug
"""
import argparse
import sys
import os

# Add project root to path so `backend` package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app.main import create_app

# For gunicorn: `gunicorn run:app`
app = create_app()


def main():
    parser = argparse.ArgumentParser(
        description="SI Sizing Tool Ver.2.0 — Flask server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=5000, help="TCP port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    app = create_app()
    print(f"SI Sizing Tool Ver.2.0 starting on http://{args.host}:{args.port}")
    if args.debug:
        print("  Debug mode: ON")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
