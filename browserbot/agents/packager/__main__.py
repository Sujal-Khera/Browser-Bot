"""
browserbot/agents/packager/__main__.py — Phase 6: Package Compiler CLI interface.

Compile and verify packages from CLI:
    python -m browserbot.agents.packager --input generated_tools/nobuycart_tracker --output packages/execute_nobuycart_com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from browserbot.agents.packager.packager import Packager


def main() -> int:
    parser = argparse.ArgumentParser(description="BrowserBot Package Compiler")
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to validated tool directory containing server.py and validation_report.json",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to destination package directory",
    )
    args = parser.parse_args()

    packager = Packager()
    try:
        packager.package(args.input, args.output)
        print(f"\n[BrowserBot] Package compiled successfully under: {args.output}")

        # Run installation verification
        verified = packager.verify_installation(args.output)
        if not verified:
            print("[error] Installation verification checks failed!", file=sys.stderr)
            return 1
        print("[BrowserBot] Package installation verification checks passed.")
    except Exception as exc:
        print(f"[error] Packaging execution failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
