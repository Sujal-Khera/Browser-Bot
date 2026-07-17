"""
tests/test_result_formatting.py — Phase 6.4: Result formatting & error surfacing tests.

Verifies the return-value contract for generated tools:
  - Success path  → human-readable prose, Claude can relay it directly
  - Failure path  → clean error sentence, no raw Python tracebacks

Run:
    python -m pytest tests/test_result_formatting.py -v
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Import the formatting helpers from the runtime formatter module
# ---------------------------------------------------------------------------
from browserbot.runtime.result_formatter import format_success, format_error


# ===========================================================================
# Success-path tests (Step 6.4)
# ===========================================================================


def test_format_success_with_no_outputs() -> None:
    """No extracted outputs → completion message, no crash."""
    result = format_success({})
    assert isinstance(result, str)
    assert len(result) > 0
    assert "completed successfully" in result.lower()


def test_format_success_with_single_output() -> None:
    result = format_success({"order_status": "Shipped"})
    assert "Shipped" in result
    assert "Order Status" in result   # snake_case → Title Case


def test_format_success_with_multiple_outputs() -> None:
    result = format_success({
        "order_status": "Delivered",
        "delivery_date": "2026-07-20",
    })
    assert "Order Status" in result
    assert "Delivered" in result
    assert "Delivery Date" in result
    assert "2026-07-20" in result


def test_format_success_never_exposes_raw_json() -> None:
    result = format_success({"order_status": "Processing"})
    # Should not look like a JSON payload
    assert not result.startswith("{")
    assert '"status"' not in result


def test_format_success_never_raises() -> None:
    """format_success must never raise, even on edge-case inputs."""
    for outputs in [{}, {"a": ""}, {"b": "  whitespace  "}, {"c": None}]:
        result = format_success(outputs)
        assert isinstance(result, str)


# ===========================================================================
# Error-path tests (Step 6.4)
# ===========================================================================


def test_format_error_returns_user_friendly_sentence() -> None:
    result = format_error("TimeoutError: 30000ms exceeded")
    assert isinstance(result, str)
    assert len(result) > 0
    # Must not expose raw Python prefix
    assert "TimeoutError:" not in result
    # Must include a helpful message
    assert "wasn't able to complete" in result.lower() or "could not" in result.lower() or "unable" in result.lower()


def test_format_error_strips_workflow_execution_prefix() -> None:
    result = format_error("Workflow execution failed: selector 'div.gone' not found")
    assert "Workflow execution failed:" not in result


def test_format_error_never_exposes_traceback() -> None:
    tb_text = (
        "Traceback (most recent call last):\n"
        "  File 'server.py', line 55, in run_workflow\n"
        "    await page.click('.btn')\n"
        "playwright._impl._errors.TimeoutError: Timeout 30000ms exceeded."
    )
    result = format_error(tb_text)
    # No raw file path, no 'Traceback' header
    assert "Traceback" not in result
    assert "File 'server.py'" not in result


def test_format_error_never_raises() -> None:
    """format_error must never raise, even on extreme inputs."""
    for msg in ["", "   ", "x" * 5000, None]:
        result = format_error(msg)  # type: ignore[arg-type]
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_error_includes_retry_hint() -> None:
    """The error message should hint at retrying or checking the site."""
    result = format_error("connection refused")
    assert "try again" in result.lower() or "reachable" in result.lower()


# ===========================================================================
# Contract invariants
# ===========================================================================


@pytest.mark.parametrize("outputs", [
    {},
    {"status": "ok"},
    {"order_id": "123", "eta": "tomorrow"},
])
def test_success_result_is_non_empty_string(outputs: dict) -> None:
    assert isinstance(format_success(outputs), str)
    assert format_success(outputs).strip() != ""


@pytest.mark.parametrize("msg", [
    "some error",
    "TimeoutError: something timed out",
    "Workflow execution failed: unknown selector",
])
def test_error_result_is_non_empty_string(msg: str) -> None:
    assert isinstance(format_error(msg), str)
    assert format_error(msg).strip() != ""


def test_error_sentinel_matches_harness(tmp_path) -> None:
    """
    Verify the error sentinel in the harness matches the _format_error output
    so harness correctly detects error returns.
    """
    error_output = format_error("something went wrong")
    ERROR_SENTINEL = "I wasn't able to complete the workflow"
    assert error_output.startswith(ERROR_SENTINEL), (
        f"format_error output does not start with sentinel.\n"
        f"Got: {error_output!r}"
    )
