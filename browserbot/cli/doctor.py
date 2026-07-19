"""
browserbot/cli/doctor.py — Phase v2.5 Step v2.5.2: Environment Diagnostics Command.

Consolidates environment checks, dependencies, Playwright, Ollama, required directories,
permissions, server health, and Claude Desktop config path resolution into a read-only,
human-readable diagnostic report with actionable recommendations.

Usage:
    python -m browserbot doctor [--no-ollama] [--json]
    python -m browserbot.cli.doctor [--no-ollama] [--json]
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from browserbot.config.settings import settings
from browserbot.logging import get_logger

log = get_logger(__name__)

# Color formatting helpers (ANSI codes)
RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"


@dataclass
class CheckItem:
    name: str
    status: str  # "OK" | "FAIL" | "WARN"
    message: str
    recommendation: str | None = None


@dataclass
class DoctorReport:
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_checks: int = 0
    all_passed: bool = True
    checks: list[CheckItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ok(msg: str, name: str, report: DoctorReport, quiet: bool = False) -> None:
    if not quiet:
        print(f"  {GREEN}[OK]{RESET}  {msg}")
    report.checks.append(CheckItem(name=name, status="OK", message=msg))
    report.passed_checks += 1


def _fail(msg: str, name: str, report: DoctorReport, recommendation: str | None = None, quiet: bool = False) -> None:
    if not quiet:
        print(f"  {RED}[FAIL]{RESET}  {msg}")
        if recommendation:
            print(f"       {YELLOW}Fix:{RESET} {recommendation}")
    report.checks.append(CheckItem(name=name, status="FAIL", message=msg, recommendation=recommendation))
    report.failed_checks += 1
    report.all_passed = False


def _warn(msg: str, name: str, report: DoctorReport, recommendation: str | None = None, quiet: bool = False) -> None:
    if not quiet:
        print(f"  {YELLOW}[WARN]{RESET}  {msg}")
        if recommendation:
            print(f"       {YELLOW}Recommendation:{RESET} {recommendation}")
    report.checks.append(CheckItem(name=name, status="WARN", message=msg, recommendation=recommendation))
    report.warning_checks += 1
    report.passed_checks += 1


def _header(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(f"\n{BOLD}{msg}{RESET}")


def check_python_version(report: DoctorReport, quiet: bool = False) -> None:
    _header("Python Environment & OS", quiet=quiet)
    v = sys.version_info
    major, minor = v[0], v[1]
    if (major, minor) >= (3, 11):
        _ok(f"Python {major}.{minor} >= 3.11 on {platform.system()}", "Python Version", report, quiet=quiet)
    else:
        msg = f"Python {major}.{minor} — BrowserBot requires Python >= 3.11"
        rec = "Upgrade your Python runtime to version 3.11 or newer."
        _fail(msg, "Python Version", report, recommendation=rec, quiet=quiet)


def check_imports(report: DoctorReport, quiet: bool = False) -> None:
    _header("Core Package Dependencies", quiet=quiet)
    packages = [
        ("playwright", "Playwright"),
        ("fastmcp", "FastMCP"),
        ("ollama", "Ollama Client"),
        ("litellm", "LiteLLM"),
        ("jinja2", "Jinja2"),
        ("jsonschema", "jsonschema"),
        ("pydantic", "Pydantic"),
        ("pytest", "pytest"),
        ("dotenv", "python-dotenv"),
        ("typer", "Typer"),
        ("rich", "Rich"),
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
    ]
    for module, label in packages:
        try:
            importlib.import_module(module)
            _ok(f"{label} ({module})", f"Dependency: {module}", report, quiet=quiet)
        except ImportError as exc:
            _fail(
                f"{label} ({module}) missing: {exc}",
                f"Dependency: {module}",
                report,
                f"Install dependencies using 'uv sync' or 'pip install {module}'.",
                quiet=quiet,
            )


def check_browserbot_import(report: DoctorReport, quiet: bool = False) -> None:
    _header("BrowserBot Package & Config", quiet=quiet)
    try:
        import browserbot  # noqa: F401
        from browserbot.config.settings import settings

        _ok(f"browserbot package v{getattr(browserbot, '__version__', '0.1.0')}", "BrowserBot Package", report, quiet=quiet)
        _ok(f"LLM Backend: {settings.llm_backend!r}", "LLM Backend Setting", report, quiet=quiet)
    except ImportError as exc:
        _fail(
            f"browserbot import failed: {exc}",
            "BrowserBot Package",
            report,
            "Re-install BrowserBot in editable mode using 'pip install -e .'.",
            quiet=quiet,
        )


def check_playwright_chromium(report: DoctorReport, quiet: bool = False) -> None:
    _header("Playwright Chromium Browser", quiet=quiet)
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("about:blank")
            browser.close()
        _ok("Chromium binary launches and navigates to about:blank", "Playwright Chromium", report, quiet=quiet)
    except Exception as exc:  # noqa: BLE001
        _fail(
            f"Playwright Chromium check failed: {exc}",
            "Playwright Chromium",
            report,
            "Run 'playwright install chromium' or 'uv run playwright install chromium'.",
            quiet=quiet,
        )


def check_ollama(report: DoctorReport, *, skip: bool, quiet: bool = False) -> None:
    _header("Ollama Local LLM Service", quiet=quiet)
    if skip:
        _warn("Skipped (--no-ollama flag set)", "Ollama Service", report, quiet=quiet)
        return
    try:
        import httpx

        res = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        if res.status_code == 200:
            models = res.json().get("models", [])
            names = [m.get("name", "?") for m in models]
            _ok(f"Ollama service reachable on localhost:11434 ({len(models)} model(s))", "Ollama Service", report, quiet=quiet)
            if not names:
                _warn("No Ollama models pulled yet", "Ollama Models", report, "Run 'ollama pull qwen2.5-coder:7b'.", quiet=quiet)
        else:
            _fail(f"Ollama returned HTTP status {res.status_code}", "Ollama Service", report, "Ensure Ollama service is running properly.", quiet=quiet)
    except Exception as exc:  # noqa: BLE001
        _fail(
            f"Ollama service unreachable on localhost:11434: {exc}",
            "Ollama Service",
            report,
            "Install Ollama from https://ollama.com and run 'ollama serve'.",
            quiet=quiet,
        )


def check_directories_and_permissions(report: DoctorReport, quiet: bool = False) -> None:
    _header("Required Directories & Permissions", quiet=quiet)
    dirs = [
        ("Sessions Directory", settings.sessions_dir),
        ("Generated Tools Directory", settings.generated_tools_dir),
        ("Packages Directory", settings.project_root / "packages"),
        ("Logs Directory", settings.logs_dir),
    ]

    for label, dir_path in dirs:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            if os.access(dir_path, os.W_OK):
                _ok(f"{label}: {dir_path} (exists & writable)", label, report, quiet=quiet)
            else:
                _fail(f"{label}: {dir_path} is NOT writable", label, report, f"Grant write permissions to {dir_path}.", quiet=quiet)
        except Exception as exc:  # noqa: BLE001
            _fail(f"{label} error ({dir_path}): {exc}", label, report, f"Check permissions and path validity for {dir_path}.", quiet=quiet)


def check_claude_desktop_config(report: DoctorReport, quiet: bool = False) -> None:
    _header("Claude Desktop Configuration", quiet=quiet)
    try:
        from browserbot.runtime.registry import _claude_config_path

        cfg_path = _claude_config_path()
        _ok(f"Resolved config path: {cfg_path}", "Claude Config Path", report, quiet=quiet)
        parent_dir = cfg_path.parent
        if parent_dir.exists():
            if os.access(parent_dir, os.W_OK):
                _ok(f"Config directory exists and writable: {parent_dir}", "Claude Config Dir", report, quiet=quiet)
            else:
                _warn(f"Config directory exists but not writable: {parent_dir}", "Claude Config Dir", report, f"Ensure write permissions for {parent_dir}.", quiet=quiet)
        else:
            _warn(
                f"Config directory does not exist yet: {parent_dir}",
                "Claude Config Dir",
                report,
                "It will be created automatically when registering your first tool.",
                quiet=quiet,
            )

        if cfg_path.exists():
            _ok("Existing claude_desktop_config.json file found", "Claude Config File", report, quiet=quiet)
    except Exception as exc:  # noqa: BLE001
        _fail(f"Claude Desktop config check failed: {exc}", "Claude Config Path", report, quiet=quiet)


def check_server_health(report: DoctorReport, quiet: bool = False) -> None:
    _header("Local Orchestration Server Health", quiet=quiet)
    port = int(os.getenv("BROWSERBOT_SERVER_PORT", "8765"))
    health_url = f"http://127.0.0.1:{port}/health"
    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "BrowserBot-Doctor"})
        with urllib.request.urlopen(req, timeout=2.0) as res:
            if res.status == 200:
                _ok(f"Local server is RUNNING and healthy on port {port}", "Orchestration Server", report, quiet=quiet)
                return
    except Exception:  # noqa: BLE001
        pass
    _warn(
        f"Local server is offline (not running on port {port})",
        "Orchestration Server",
        report,
        f"Start local server using 'python -m browserbot server' or 'uv run python -m browserbot server'.",
        quiet=quiet,
    )


def check_no_api_key_required(report: DoctorReport, quiet: bool = False) -> None:
    _header("Zero-Credential Audit", quiet=quiet)
    suspicious = [k for k in os.environ if "API_KEY" in k.upper() and "GROQ" not in k]
    if suspicious:
        _warn(
            f"Non-Groq API key(s) detected in environment: {suspicious}",
            "Zero Credential Audit",
            report,
            "The default Ollama path operates with zero API keys required.",
            quiet=quiet,
        )
    else:
        _ok("No paid API credentials required in environment (Ollama path clean)", "Zero Credential Audit", report, quiet=quiet)


def check_package_versions(report: DoctorReport, quiet: bool = False, packages_dir: Path | None = None) -> None:
    _header("Package Versioning & Upgrade Status", quiet=quiet)
    from browserbot.version import detect_package_upgrade, CompatibilityStatus

    target_dir = packages_dir or (settings.project_root / "packages")
    if not target_dir.exists():
        _ok("No generated packages directory found yet", "Package Versions", report, quiet=quiet)
        return

    pkg_dirs = [d for d in target_dir.iterdir() if d.is_dir() and (d / "browserbot_package.json").exists()]
    if not pkg_dirs:
        _ok("No packages found in packages/ directory", "Package Versions", report, quiet=quiet)
        return

    for pdir in pkg_dirs:
        status = detect_package_upgrade(pdir)
        pkg_name = pdir.name
        if status.status == CompatibilityStatus.COMPATIBLE:
            _ok(f"Package '{pkg_name}' version matches installed (v{status.generator_version})", f"Package Version: {pkg_name}", report, quiet=quiet)
        elif status.status == CompatibilityStatus.STALE:
            _warn(
                f"Package '{pkg_name}' (v{status.generator_version}) is stale relative to installed BrowserBot (v{status.installed_version})",
                f"Package Version: {pkg_name}",
                report,
                recommendation=status.recommendation,
                quiet=quiet,
            )
        else:
            _warn(
                f"Package '{pkg_name}' (v{status.generator_version}) is incompatible: {status.warning_message}",
                f"Package Version: {pkg_name}",
                report,
                recommendation=status.recommendation,
                quiet=quiet,
            )


def run_doctor(*, skip_ollama: bool = False, json_output: bool = False) -> DoctorReport:
    """
    Run all BrowserBot environment, system, and configuration diagnostic checks.
    Returns a structured DoctorReport object.
    """
    report = DoctorReport()

    if not json_output:
        print(f"\n{BOLD}BrowserBot Doctor — Diagnostic Report{RESET}")
        print("=" * 55)

    quiet = json_output
    check_python_version(report, quiet=quiet)
    check_imports(report, quiet=quiet)
    check_browserbot_import(report, quiet=quiet)
    check_playwright_chromium(report, quiet=quiet)
    check_ollama(report, skip=skip_ollama, quiet=quiet)
    check_directories_and_permissions(report, quiet=quiet)
    check_claude_desktop_config(report, quiet=quiet)
    check_server_health(report, quiet=quiet)
    check_no_api_key_required(report, quiet=quiet)
    check_package_versions(report, quiet=quiet)

    report.total_checks = len(report.checks)

    if not json_output:
        print(f"\n{'='*55}")
        if report.all_passed:
            print(f"{GREEN}All {report.passed_checks} check(s) passed [OK]{RESET}")
            print("Your BrowserBot workstation environment is fully operational.\n")
        else:
            print(f"{RED}{report.failed_checks} of {report.total_checks} check(s) failed [FAIL]{RESET}")
            print("Review the failure recommendations above to resolve configuration issues.\n")
    else:
        print(json.dumps(report.to_dict(), indent=2))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m browserbot doctor",
        description="BrowserBot Doctor — Read-only environment, dependency, and configuration diagnostic utility.",
    )
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Skip Ollama reachability check.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print diagnostic report as JSON to stdout.",
    )
    args = parser.parse_args()

    report = run_doctor(skip_ollama=args.no_ollama, json_output=args.json)
    sys.exit(0 if report.all_passed else 1)


if __name__ == "__main__":
    main()
