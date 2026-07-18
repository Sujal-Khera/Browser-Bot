"""
scripts/run_benchmark.py — Step 9.4 Latency & Reliability Benchmark.

Runs consecutive workflow benchmark runs, outputs performance timing statistics,
checks PII violations, and determines compliance against NFR targets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from browserbot.runtime.benchmark import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BrowserBot Step 9.4 Latency & Reliability Benchmark Runner"
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Path to the BrowserBot package folder to benchmark",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of consecutive runs to execute (default: 3)",
    )
    args = parser.parse_args()

    package_dir = Path(args.package)
    if not package_dir.exists():
        print(f"[error] Package directory does not exist: {package_dir}", file=sys.stderr)
        return 1

    print(f"[*] Starting latency & reliability benchmark for: {package_dir}")
    print(f"[*] Iterations: {args.iterations}")

    try:
        import asyncio
        report = asyncio.run(run_benchmark(package_dir, iterations=args.iterations))
    except Exception as exc:
        print(f"[error] Benchmark run failed: {exc}", file=sys.stderr)
        return 1

    print(f"\n[+] Benchmark finished successfully.")
    print(f"[*] Report JSON: {package_dir / 'benchmark_report.json'}")
    print(f"[*] Report Markdown: {package_dir / 'benchmark_report.md'}\n")

    # Output summaries to stdout
    metrics = report["metrics"]
    latency = metrics["latency"]
    comp = report["compliance"]

    print("--------------------------------------------------------------------------------")
    print(f"NFR Benchmark Summary — {package_dir.name}")
    print("--------------------------------------------------------------------------------")
    print(f"  Overall Compliance   : {'PASS' if report['overall_compliant'] else 'FAIL'}")
    print(f"  Runs Executed        : {metrics['runtime_runs']}")
    print(f"  Success Rate         : {metrics['runtime_success_rate']*100:.1f}% ({'PASS' if comp['reliability_rate_ok'] else 'FAIL'})")
    print(f"  Mean Latency         : {latency['mean_s']:.2f}s ({'PASS' if comp['runtime_latency_ok'] else 'FAIL'})")
    print(f"  Latency Std Dev      : {latency['std_dev_s']:.2f}s")
    print(f"  PII Violations       : {metrics['pii_audit_violations']} ({'PASS' if comp['pii_violations_ok'] else 'FAIL'})")
    print(f"  Total Gen Duration   : {metrics['total_compilation_time_s']:.2f}s ({'PASS' if comp['generation_time_ok'] else 'FAIL'})")
    print("--------------------------------------------------------------------------------")

    return 0 if report["overall_compliant"] else 1


if __name__ == "__main__":
    sys.exit(main())
