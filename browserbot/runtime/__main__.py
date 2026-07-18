"""
browserbot/runtime/__main__.py — Step 6.3: Claude Desktop Registration CLI.

Registers a packaged BrowserBot tool into Claude Desktop, or removes it,
or lists all currently registered tools.

Usage::

    # Register a package (writes claude_desktop_config.json)
    python -m browserbot.runtime register \\
        --package packages/execute_nobuycart_com

    # Dry-run — print the snippet that WOULD be written, do not write
    python -m browserbot.runtime register \\
        --package packages/execute_nobuycart_com --dry-run

    # Unregister
    python -m browserbot.runtime unregister --tool execute_nobuycart_com

    # List all registered tools
    python -m browserbot.runtime list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from browserbot.models.package import BrowserBotPackage
from browserbot.runtime.registry import ClaudeDesktopRegistry, RegistrationError
from browserbot.orchestrator.self_healing import self_heal_package


def _cmd_register(args: argparse.Namespace) -> int:
    package_dir = Path(args.package)
    manifest_path = package_dir / "browserbot_package.json"

    if not manifest_path.exists():
        print(
            f"[error] No browserbot_package.json found in: {package_dir}\n"
            f"        Run 'python -m browserbot.agents.packager' first.",
            file=sys.stderr,
        )
        return 1

    try:
        package = BrowserBotPackage.from_file(manifest_path)
    except Exception as exc:
        print(f"[error] Could not load package manifest: {exc}", file=sys.stderr)
        return 1

    registry = ClaudeDesktopRegistry()
    try:
        registry.register(package, dry_run=args.dry_run)
    except RegistrationError as exc:
        print(f"[error] Registration failed: {exc}", file=sys.stderr)
        return 1

    if not args.dry_run:
        # Print a concise invocation hint
        print(
            f"\n--- Invocation hint ------------------------------------------\n"
            f"   Ask Claude Desktop (after restart):\n"
            f"   \"Check my order status for order code NBC-2026-E3ZXJC\"\n"
            f"-------------------------------------------------------------\n"
        )

    return 0


def _cmd_unregister(args: argparse.Namespace) -> int:
    registry = ClaudeDesktopRegistry()
    removed = registry.unregister(args.tool, dry_run=args.dry_run)
    if not removed:
        print(f"[warn] Tool '{args.tool}' was not in the Claude Desktop config.")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    registry = ClaudeDesktopRegistry()
    tools = registry.list_registered()
    if tools:
        print("Registered MCP servers in Claude Desktop:")
        for t in tools:
            print(f"  • {t}")
    else:
        print("No MCP servers currently registered in Claude Desktop.")
    return 0


def _cmd_self_heal(args: argparse.Namespace) -> int:
    package_dir = Path(args.package)
    try:
        healed = self_heal_package(
            package_dir,
            registry_config_path=Path(args.registry_config) if args.registry_config else None,
            force=args.force,
        )
        if healed:
            print(f"[BrowserBot] Package '{package_dir.name}' successfully healed and re-registered.")
        else:
            print(f"[BrowserBot] Package '{package_dir.name}' did not require healing (no flag present). Use --force to run anyway.")
    except Exception as exc:
        print(f"[error] Self-healing failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m browserbot.runtime",
        description="BrowserBot Phase 6.3 — Claude Desktop Registration CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── register ──────────────────────────────────────────────────────
    reg = sub.add_parser("register", help="Register a packaged tool with Claude Desktop")
    reg.add_argument(
        "--package",
        required=True,
        type=str,
        help="Path to the BrowserBot package directory (must contain browserbot_package.json)",
    )
    reg.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the config snippet without writing the file",
    )

    # ── unregister ────────────────────────────────────────────────────
    un = sub.add_parser("unregister", help="Remove a tool from Claude Desktop config")
    un.add_argument("--tool", required=True, help="Tool name (package_name) to remove")
    un.add_argument("--dry-run", action="store_true", default=False)

    # ── list ──────────────────────────────────────────────────────────
    sub.add_parser("list", help="List all tools registered in Claude Desktop config")

    # ── self-heal ─────────────────────────────────────────────────────
    sh = sub.add_parser("self-heal", help="Trigger self-healing execution on a package")
    sh.add_argument(
        "--package",
        required=True,
        type=str,
        help="Path to the BrowserBot package directory",
    )
    sh.add_argument(
        "--registry-config",
        type=str,
        default=None,
        help="Custom path to the Claude config JSON (for testing)",
    )
    sh.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force self-healing even if no failure flag exists",
    )

    args = parser.parse_args(argv)

    dispatch = {
        "register": _cmd_register,
        "unregister": _cmd_unregister,
        "list": _cmd_list,
        "self-heal": _cmd_self_heal,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
