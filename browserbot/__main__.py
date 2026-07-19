"""
browserbot/__main__.py — Entry point for `python -m browserbot`.

Subcommands
-----------
    python -m browserbot doctor [--no-ollama]
        Run system diagnostics (Ollama, Playwright, Python, Claude Desktop config).

    python -m browserbot server [--port PORT]
        Start the local FastAPI orchestration server and Web UI.

    python -m browserbot recorder start [URL] [--hint TEXT]
        Launch recorder codegen.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m browserbot",
        description="BrowserBot — Local-First Browser Automation to MCP Tool Generator",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # doctor
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run environment diagnostics (Python, Playwright, Ollama, Claude Desktop config).",
    )
    doctor_parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Skip Ollama reachability check.",
    )

    # server
    server_parser = subparsers.add_parser(
        "server",
        help="Start the FastAPI orchestration server.",
    )
    server_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address to bind (default: 127.0.0.1).",
    )
    server_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind (default: 8765).",
    )

    # recorder
    rec_parser = subparsers.add_parser(
        "recorder",
        help="Recorder commands.",
    )
    rec_parser.add_argument(
        "rec_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to recorder sub-module.",
    )

    args = parser.parse_args(argv)

    if args.command == "doctor":
        from browserbot.cli.doctor import run_doctor

        success = run_doctor(skip_ollama=args.no_ollama)
        sys.exit(0 if success else 1)

    elif args.command == "server":
        import uvicorn
        from browserbot.server.app import app

        print(f"Starting BrowserBot Orchestration Server on http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)

    elif args.command == "recorder":
        from browserbot.recorder.__main__ import main as recorder_main

        # Pass remaining args to recorder main
        sys.argv = [sys.argv[0]] + (args.rec_args or [])
        recorder_main()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
