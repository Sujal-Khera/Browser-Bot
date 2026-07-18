"""
browserbot/runtime/pii_audit.py — Step 9.1 Credential/PII Audit.

Scans generated package artifacts for credentials, high-entropy secrets, and
unredacted test parameters.
"""

from __future__ import annotations

import re
from pathlib import Path
from browserbot.logging import get_logger

log = get_logger(__name__)

# Regular expressions for identifying common secret assignments and high-entropy API keys
SECRET_PATTERNS: list[re.Pattern] = [
    # Match assignment: password/secret/token/key = "..." (6+ chars, excluding redacted templates)
    re.compile(
        r"(?i)(?:password|secret|token|api_key|auth_token)\s*[:=]\s*['\"](?!(?:__SECRET_\d+__|redacted|\*+))([^'\"]{6,})['\"]"
    ),
    # Match standard JWT tokens or high-entropy hex/base64-like keys
    re.compile(r"\b[A-Za-z0-9-_=]{32,}\b"),
]


def audit_artifacts(
    package_dir: Path | str,
    forbidden_strings: list[str] | None = None,
) -> list[str]:
    """
    Performs a security and PII audit over generated files in a package directory.

    Args:
        package_dir: Path to the BrowserBot package folder.
        forbidden_strings: Optional list of literal values (e.g., raw passwords)
                           to scan and explicitly prohibit.

    Returns:
        A list of violation descriptions (empty if package is completely clean).
    """
    package_dir = Path(package_dir).resolve()
    if not package_dir.exists():
        raise FileNotFoundError(f"Package directory not found: {package_dir}")

    violations: list[str] = []
    forbidden_strings = forbidden_strings or []

    # Files to audit
    files_to_scan = [
        package_dir / "server.py",
        package_dir / "mcp_tool.json",
        package_dir / "browserbot_package.json",
        package_dir / "validation_report.json",
    ]

    for file_path in files_to_scan:
        if not file_path.exists():
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            violations.append(f"Failed to read {file_path.name}: {exc}")
            continue

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            # 1. Check for literal forbidden strings (unredacted secrets)
            for forbidden in forbidden_strings:
                if forbidden and forbidden in line:
                    # Ignore lines defining whitelisted patterns in the test suite itself
                    if "NBC_TEST_SECRET_PASSWORD" in forbidden and "test_" in file_path.name:
                        continue
                    violations.append(
                        f"{file_path.name}:{idx}: Found literal forbidden string placeholder: "
                        f"{forbidden[:3]}... (redaction failure)"
                    )

            # 2. Check against secret/key regex patterns
            for pattern in SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    matched_val = match.group(0)
                    # Exclude whitelisted non-secrets that trigger regex
                    if any(
                        w in matched_val.lower()
                        for w in [
                            "resolve_locator",
                            "resilient_click",
                            "resilient_fill",
                            "fastmcp",
                            "browserbot",
                            "pipeline_diagnostics",
                            "validation_report",
                            "claude_config_snippet",
                            "browserbot_package",
                            "execute_",
                            "practicetestautomation",
                        ]
                    ):
                        continue

                    # If match length is suspiciously long/high entropy
                    if len(match.group(1) if len(match.groups()) > 0 else matched_val) >= 6:
                        violations.append(
                            f"{file_path.name}:{idx}: Suspicious unredacted secret match: "
                            f"{matched_val[:20]}..."
                        )

    if violations:
        log.warning(
            "PII audit failed with violations",
            extra={"package": str(package_dir), "violations": violations}
        )
    else:
        log.info("PII audit passed cleanly", extra={"package": str(package_dir)})

    return violations
