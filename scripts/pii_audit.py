"""
scripts/pii_audit.py — Step 9.1 PII and Credential Audit Tool.

Scans the generated tool package files for plain text secrets or PII leaks.
Exits with code 0 on success, or code 1 on violations.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from browserbot.runtime.pii_audit import audit_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="BrowserBot Step 9.1 PII Audit")
    parser.add_argument(
        "--package",
        required=True,
        help="Path to the BrowserBot package folder to scan",
    )
    parser.add_argument(
        "--secret",
        action="append",
        default=[],
        help="Literal secret string value to explicitly scan for (can be specified multiple times)",
    )
    args = parser.parse_args()

    package_dir = Path(args.package)
    if not package_dir.exists():
        print(f"[error] Package directory does not exist: {package_dir}", file=sys.stderr)
        return 1

    # Include common default test secrets in search if none specified
    secrets = args.secret if args.secret else ["NBC_TEST_SECRET_PASSWORD", "NBC-TEST-KEY-12345"]

    print(f"[*] Running PII & Credential Audit on: {package_dir}")
    print(f"[*] Scanning for forbidden strings: {secrets}")

    violations = audit_artifacts(package_dir, forbidden_strings=secrets)

    if violations:
        print(f"\n[!] PII Audit Failed! Found {len(violations)} violation(s):", file=sys.stderr)
        for v in violations:
            print(f"    - {v}", file=sys.stderr)
        return 1

    print("\n[+] PII Audit passed successfully! No credentials or secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
