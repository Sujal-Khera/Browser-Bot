"""
scripts/verify_env.py — Step 1.1 environment verification script.

Verifies that every component of the BrowserBot development environment
is correctly installed and functional.  Run this after a fresh checkout
or after adding dependencies.

Usage:
    python scripts/verify_env.py            # all checks
    python scripts/verify_env.py --no-ollama  # skip Ollama (if not installed)

Exit codes:
    0  — all checks passed
    1  — one or more checks failed

Checks performed:
    1. Python version >= 3.11
    2. Core package imports (playwright, fastmcp, ollama, litellm, jinja2,
       jsonschema, pydantic, pytest)
    3. Playwright Chromium browser binary present
    4. Ollama service reachable on localhost:11434  (skippable)
    5. BrowserBot package itself importable
    6. No API key required in default configuration
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import subprocess
import sys
from typing import Callable


# ---------------------------------------------------------------------------
# Colour helpers (no external dep — use ANSI codes directly)
# ---------------------------------------------------------------------------

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"


def _ok(msg: str) -> None:
    print(f"  {GREEN}[OK]{RESET}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}[FAIL]{RESET}  {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}[WARN]{RESET}  {msg}")


def _header(msg: str) -> None:
    print(f"\n{BOLD}{msg}{RESET}")


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_python_version() -> bool:
    _header("Python version")
    major, minor = sys.version_info.major, sys.version_info.minor
    if (major, minor) >= (3, 11):
        _ok(f"Python {major}.{minor} >= 3.11")
        return True
    _fail(f"Python {major}.{minor} — requires >= 3.11")
    return False


def check_imports() -> bool:
    _header("Core package imports")
    packages = [
        ("playwright", "Playwright"),
        ("fastmcp", "FastMCP"),
        ("ollama", "Ollama Python client"),
        ("litellm", "LiteLLM"),
        ("jinja2", "Jinja2"),
        ("jsonschema", "jsonschema"),
        ("pydantic", "Pydantic"),
        ("pytest", "pytest"),
        ("dotenv", "python-dotenv"),
        ("typer", "Typer"),
        ("rich", "Rich"),
    ]
    all_ok = True
    for module, label in packages:
        try:
            importlib.import_module(module)
            _ok(f"{label} ({module})")
        except ImportError as exc:
            _fail(f"{label} ({module}) — {exc}")
            all_ok = False
    return all_ok


def check_browserbot_import() -> bool:
    _header("BrowserBot package")
    try:
        import browserbot  # noqa: F401
        from browserbot.config.settings import settings  # noqa: F401
        from browserbot.logging import get_logger  # noqa: F401
        _ok("browserbot package imports cleanly")
        _ok(f"Settings: llm_backend={settings.llm_backend!r}")
        return True
    except ImportError as exc:
        _fail(f"browserbot import failed: {exc}")
        return False


async def _check_playwright_chromium_async() -> bool:
    """Inner async Playwright check."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("about:blank")
            await browser.close()
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"       Error: {exc}")
            return False


def check_playwright_chromium() -> bool:
    _header("Playwright Chromium browser")
    try:
        ok = asyncio.run(_check_playwright_chromium_async())
        if ok:
            _ok("Chromium launches and navigates to about:blank")
        else:
            _fail(
                "Chromium launch failed — run: "
                ".venv/Scripts/playwright install chromium"
            )
        return ok
    except Exception as exc:  # noqa: BLE001
        _fail(f"Playwright check failed: {exc}")
        return False


def check_ollama(*, skip: bool) -> bool:
    _header("Ollama local LLM service")
    if skip:
        _warn("Skipped (--no-ollama flag set)")
        return True  # don't penalise the exit code
    try:
        import httpx

        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "?") for m in models]
            _ok(f"Ollama service reachable — {len(models)} model(s) pulled")
            if model_names:
                for name in model_names:
                    _ok(f"  · {name}")
            else:
                _warn(
                    "No models pulled yet.  Run: ollama pull qwen2.5-coder:7b"
                )
            return True
        _fail(f"Ollama returned HTTP {response.status_code}")
        return False
    except Exception as exc:  # noqa: BLE001
        _fail(
            f"Ollama not reachable on localhost:11434 — {exc}\n"
            "       Install from https://ollama.com and run 'ollama serve'."
        )
        return False


def check_no_api_key_required() -> bool:
    _header("Zero-credential default configuration")
    import os

    suspicious = [k for k in os.environ if "API_KEY" in k.upper() and "GROQ" not in k]
    if suspicious:
        _warn(
            f"Non-Groq API key(s) found in environment: {suspicious}\n"
            "       The default Ollama path should require no API key."
        )
    else:
        _ok("No paid-API credentials detected in environment (Ollama path is clean)")
    return True  # warning only — doesn't fail the suite


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BrowserBot environment verification (Step 1.1)"
    )
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Skip the Ollama reachability check (useful if Ollama is not installed yet).",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}BrowserBot — Environment Verification{RESET}")
    print("=" * 50)

    checks: list[Callable[[], bool]] = [
        check_python_version,
        check_imports,
        check_browserbot_import,
        check_playwright_chromium,
        lambda: check_ollama(skip=args.no_ollama),
        check_no_api_key_required,
    ]

    results = [check() for check in checks]

    total = len(results)
    passed = sum(results)
    failed = total - passed

    print(f"\n{'='*50}")
    if failed == 0:
        print(f"{GREEN}All {total} checks passed [OK]{RESET}")
        print("Your BrowserBot development environment is ready.\n")
        sys.exit(0)
    else:
        print(f"{RED}{failed}/{total} check(s) failed [FAIL]{RESET}")
        print("Resolve the failures above before proceeding.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
