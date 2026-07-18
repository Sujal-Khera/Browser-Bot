"""
browserbot/runtime/benchmark.py — Step 9.4 Latency & Reliability Benchmark.

Programmatically benchmarks generated MCP tool packages for latency, reliability,
and NFR compliance using async execution.
"""

from __future__ import annotations

import os
import importlib.util
import json
import math
import sys
import time
from pathlib import Path
from typing import Any
from browserbot.logging import get_logger
from browserbot.runtime.pii_audit import audit_artifacts

log = get_logger(__name__)

# NFR Targets as defined in docs/2. NonFunctionalRequirements_&_SuccessMetrics.md
NFR_TARGETS = {
    "generation_time_s": 180.0,
    "runtime_latency_s": 20.0,
    "reliability_rate": 0.90,  # 90%
    "pii_violations": 0,
}


async def run_benchmark(
    package_dir: Path | str,
    iterations: int = 3,
    run_workflow_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Runs the latency and reliability benchmark over a generated tool package.

    Args:
        package_dir: Path to the BrowserBot package folder.
        iterations: Number of consecutive executions to benchmark.
        run_workflow_args: Arguments to pass to run_workflow.

    Returns:
        A dictionary containing structured latency, reliability, and audit results.
    """
    package_dir = Path(package_dir).resolve()
    manifest_path = package_dir / "browserbot_package.json"
    server_path = package_dir / "server.py"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Package manifest not found: {manifest_path}")
    if not server_path.exists():
        raise FileNotFoundError(f"Server script not found: {server_path}")

    log.info(
        "Starting BrowserBot NFR benchmark",
        extra={"package": str(package_dir), "iterations": iterations}
    )

    # 1. Load Compilation Timings from diagnostics
    diagnostics_path = package_dir / "pipeline_diagnostics.json"
    # Fallback to scanning parent folder generated_tools/
    if not diagnostics_path.exists():
        parent_dir = Path("generated_tools") / package_dir.name.replace("execute_", "")
        diagnostics_path = parent_dir / "pipeline_diagnostics.json"

    compilation_metrics = {}
    total_compilation_time = 0.0

    if diagnostics_path.exists():
        try:
            diag = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            compilation_metrics = diag.get("stages", {})
            total_compilation_time = diag.get("total_duration_seconds", 0.0)
            log.info("Loaded compilation metrics from diagnostics", extra={"total": total_compilation_time})
        except Exception as exc:
            log.warning("Could not read pipeline diagnostics", extra={"error": str(exc)})

    # 2. Dynamic Import of generated run_workflow tool
    spec = importlib.util.spec_from_file_location("generated_server", str(server_path))
    if not spec or not spec.loader:
        raise ImportError(f"Could not load module spec for: {server_path}")
    
    module = importlib.util.module_from_spec(spec)
    # Prevent conflict in sys.modules
    sys.modules["generated_server"] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "run_workflow"):
        raise AttributeError(f"run_workflow function not found in generated: {server_path}")

    run_workflow = getattr(module, "run_workflow")

    # 3. Perform Consecutive Async Executions
    run_workflow_args = run_workflow_args or {}
    latencies: list[float] = []
    successes = 0

    # Ensure headless mode during benchmarking to run faster/offline
    original_headless = os.environ.get("BROWSERBOT_HEADLESS")
    os.environ["BROWSERBOT_HEADLESS"] = "true"

    for i in range(1, iterations + 1):
        log.info("Executing benchmark iteration", extra={"run": i, "total": iterations})
        t_start = time.perf_counter()
        try:
            # Await the async tool method directly
            result = await run_workflow(**run_workflow_args)
            duration = time.perf_counter() - t_start
            latencies.append(duration)
            
            # Check success condition (Success = non-empty string that does NOT start with ERROR_SENTINEL)
            ERROR_SENTINEL = "I wasn't able to complete the workflow"
            if result and result.strip() and not result.strip().startswith(ERROR_SENTINEL):
                successes += 1
                log.info("Benchmark iteration succeeded", extra={"run": i, "duration": duration})
            else:
                log.warning("Benchmark iteration returned error string", extra={"run": i, "result": result})
        except Exception as exc:
            duration = time.perf_counter() - t_start
            latencies.append(duration)
            log.error("Benchmark iteration raised exception", extra={"run": i, "error": str(exc)})

    # Restore original environment setting
    if original_headless is not None:
        os.environ["BROWSERBOT_HEADLESS"] = original_headless
    else:
        os.environ.pop("BROWSERBOT_HEADLESS", None)

    # Calculate statistics
    num_runs = len(latencies)
    reliability = successes / num_runs if num_runs > 0 else 0.0

    min_l = min(latencies) if latencies else 0.0
    max_l = max(latencies) if latencies else 0.0
    mean_l = sum(latencies) / num_runs if num_runs > 0 else 0.0
    
    # Standard deviation
    variance = sum((x - mean_l) ** 2 for x in latencies) / num_runs if num_runs > 1 else 0.0
    std_dev = math.sqrt(variance)

    # 4. Perform Credential and PII Audit
    # Pass common test secrets if present
    violations = audit_artifacts(package_dir, forbidden_strings=["NBC_TEST_SECRET_PASSWORD"])
    num_violations = len(violations)

    # 5. Compile NFR Compliance Results
    compliance = {
        "generation_time_ok": total_compilation_time <= NFR_TARGETS["generation_time_s"] if total_compilation_time > 0 else True,
        "runtime_latency_ok": mean_l <= NFR_TARGETS["runtime_latency_s"],
        "reliability_rate_ok": reliability >= NFR_TARGETS["reliability_rate"],
        "pii_violations_ok": num_violations == NFR_TARGETS["pii_violations"],
    }
    
    overall_compliant = all(compliance.values())

    report = {
        "package_name": package_dir.name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "iterations": iterations,
        "metrics": {
            "total_compilation_time_s": total_compilation_time,
            "compilation_stages_s": compilation_metrics,
            "runtime_success_rate": reliability,
            "runtime_runs": num_runs,
            "runtime_successes": successes,
            "latency": {
                "min_s": min_l,
                "max_s": max_l,
                "mean_s": mean_l,
                "std_dev_s": std_dev,
                "raw_runs_s": latencies,
            },
            "pii_audit_violations": num_violations,
            "pii_audit_details": violations,
        },
        "nfr_targets": NFR_TARGETS,
        "compliance": compliance,
        "overall_compliant": overall_compliant,
    }

    # Save benchmark report as JSON
    json_report_path = package_dir / "benchmark_report.json"
    json_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Benchmark JSON report written", extra={"path": str(json_report_path)})

    # Generate user-friendly markdown report
    markdown_report_path = package_dir / "benchmark_report.md"
    md_content = _build_markdown_report(report)
    markdown_report_path.write_text(md_content, encoding="utf-8")
    log.info("Benchmark Markdown report written", extra={"path": str(markdown_report_path)})

    return report


def _build_markdown_report(report: dict[str, Any]) -> str:
    """Helper to compile a clean, professional markdown representation of NFR benchmarks."""
    metrics = report["metrics"]
    comp = report["compliance"]
    targets = report["nfr_targets"]

    status_symbol = lambda ok: "✅ Compliant" if ok else "❌ Non-Compliant"

    md = []
    md.append(f"# BrowserBot — NFR Benchmark Report ({report['package_name']})")
    md.append(f"**Generated at:** `{report['timestamp']}`  ")
    md.append(f"**Iterations:** `{report['iterations']}`  ")
    md.append(f"**Overall Compliance:** `{'COMPLIANT' if report['overall_compliant'] else 'NON-COMPLIANT'}`")
    md.append("")
    md.append("## NFR Performance Metrics")
    md.append("")
    md.append("| Metric | Target | Actual | Status |")
    md.append("|--------|--------|--------|--------|")
    
    comp_time = f"{metrics['total_compilation_time_s']:.2f}s" if metrics['total_compilation_time_s'] > 0 else "N/A"
    md.append(f"| **Generation Time** | ≤ {targets['generation_time_s']}s | {comp_time} | {status_symbol(comp['generation_time_ok'])} |")
    md.append(f"| **Runtime Latency (Mean)** | ≤ {targets['runtime_latency_s']}s | {metrics['latency']['mean_s']:.2f}s | {status_symbol(comp['runtime_latency_ok'])} |")
    md.append(f"| **Reliability** | ≥ {targets['reliability_rate']*100:.0f}% | {metrics['runtime_success_rate']*100:.1f}% ({metrics['runtime_successes']}/{metrics['runtime_runs']}) | {status_symbol(comp['reliability_rate_ok'])} |")
    md.append(f"| **PII Violations** | {targets['pii_violations']} | {metrics['pii_audit_violations']} | {status_symbol(comp['pii_violations_ok'])} |")
    md.append("")
    md.append("## Runtime Latency Details")
    md.append(f"- **Minimum Latency:** `{metrics['latency']['min_s']:.2f}s`")
    md.append(f"- **Maximum Latency:** `{metrics['latency']['max_s']:.2f}s`")
    md.append(f"- **Mean Latency:** `{metrics['latency']['mean_s']:.2f}s`")
    md.append(f"- **Standard Deviation:** `{metrics['latency']['std_dev_s']:.2f}s`")
    md.append(f"- **Raw Execution Durations:** `{[round(x, 2) for x in metrics['latency']['raw_runs_s']]}`")
    md.append("")

    if metrics["compilation_stages_s"]:
        md.append("## Compilation Stage Durations")
        md.append("")
        md.append("| Stage | Duration |")
        md.append("|---|---|")
        for stage, stage_info in metrics["compilation_stages_s"].items():
            if isinstance(stage_info, dict):
                duration = stage_info.get("duration_seconds")
            else:
                duration = None
            duration_str = f"{duration:.2f}s" if isinstance(duration, (int, float)) else "N/A"
            md.append(f"| {stage} | {duration_str} |")
        md.append("")

    if metrics["pii_audit_violations"] > 0:
        md.append("## PII Audit Violations Details")
        md.append("")
        for v in metrics["pii_audit_details"]:
            md.append(f"- ⚠️ {v}")
        md.append("")

    return "\n".join(md)
