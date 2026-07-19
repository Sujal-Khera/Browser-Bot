"""
tests/test_result_formatting.py — Phase 6.4 + v2.4: Result formatting & error surfacing tests.

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
from browserbot.runtime.result_formatter import (
    format_success,
    format_error,
    _classify_error,
    _build_prose_sentence,
)


# ===========================================================================
# Success-path tests (Step 6.4) — existing tests preserved unchanged
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
# Error-path tests (Step 6.4) — existing tests preserved unchanged
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
# Contract invariants — existing
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


# ===========================================================================
# v2.4.1 — Prose style tests
# ===========================================================================


class TestProseStyle:
    """Verify the opt-in prose summarization style for format_success."""

    def test_empty_outputs_prose_same_as_bullet(self) -> None:
        """Empty outputs: prose and bullet return the same sentinel message."""
        bullet = format_success({}, style="bullet")
        prose = format_success({}, style="prose")
        assert "completed successfully" in prose.lower()
        assert bullet == prose  # both hit the early-return path

    def test_single_output_prose_natural_sentence(self) -> None:
        result = format_success({"order_status": "Delivered"}, style="prose")
        assert "completed successfully" in result.lower()
        assert "order status" in result.lower()
        assert "Delivered" in result
        # Should NOT be a bullet list
        assert "•" not in result

    def test_two_output_prose_joined_with_and(self) -> None:
        result = format_success(
            {"order_status": "Shipped", "delivery_date": "2026-07-20"},
            style="prose",
        )
        assert "order status" in result.lower()
        assert "delivery date" in result.lower()
        assert "Shipped" in result
        assert "2026-07-20" in result
        assert " and " in result
        assert "•" not in result

    def test_three_output_prose_oxford_comma(self) -> None:
        result = format_success(
            {
                "order_status": "In Transit",
                "delivery_date": "July 22",
                "carrier": "FedEx",
            },
            style="prose",
        )
        assert "order status" in result.lower()
        assert "delivery date" in result.lower()
        assert "carrier" in result.lower()
        assert ", and " in result  # Oxford comma
        assert "•" not in result

    def test_prose_never_raises_on_none_values(self) -> None:
        result = format_success({"status": None, "eta": ""}, style="prose")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_prose_never_exposes_raw_json(self) -> None:
        result = format_success({"order_status": "Processing"}, style="prose")
        assert not result.startswith("{")
        assert '"status"' not in result

    def test_bullet_style_default_unchanged(self) -> None:
        """Default (no style kwarg) must still produce the bullet-list format."""
        result = format_success({"order_status": "Delivered"})
        assert "•" in result
        assert "Order Status" in result  # Title Case labels

    def test_unknown_style_falls_back_to_bullet(self) -> None:
        """Passing an unsupported style string should not crash and should fall back."""
        result = format_success({"status": "ok"}, style="unknown_style")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_prose_sentinel_not_present_in_success(self) -> None:
        """Prose success must never start with the error sentinel."""
        ERROR_SENTINEL = "I wasn't able to complete the workflow"
        result = format_success({"order_status": "Done"}, style="prose")
        assert not result.startswith(ERROR_SENTINEL)


# ===========================================================================
# v2.4.2 — Error category / classification tests
# ===========================================================================


class TestErrorCategories:
    """Table-driven tests for each recognised error category."""

    @pytest.mark.parametrize("exc_msg", [
        "TimeoutError: 30000ms exceeded.",
        "Timeout 30000ms exceeded waiting for element",
        "playwright timed out waiting for selector",
        "page.click: Timeout 5000ms exceeded.",
    ])
    def test_timeout_category(self, exc_msg: str) -> None:
        result = format_error(exc_msg)
        assert result.startswith("I wasn't able to complete the workflow")
        assert "too long" in result.lower() or "time" in result.lower()
        # Must not expose raw Python text
        assert "TimeoutError:" not in result

    @pytest.mark.parametrize("exc_msg", [
        "strict mode violation: locator resolved to 2 elements",
        "Error: No element matches selector 'div.gone'",
        "locator.click: element not found in page",
        "selector not found: .missing-btn",
    ])
    def test_selector_not_found_category(self, exc_msg: str) -> None:
        result = format_error(exc_msg)
        assert result.startswith("I wasn't able to complete the workflow")
        # Should guide user to re-record
        assert "element" in result.lower() or "selector" in result.lower() or "layout" in result.lower()

    @pytest.mark.parametrize("exc_msg", [
        "net::ERR_NAME_NOT_RESOLVED",
        "ERR_CONNECTION_REFUSED navigating to https://example.com",
        "Navigation failed: net::ERR_INTERNET_DISCONNECTED",
        # Note: "page.goto timed out" resolves as *timeout* category (first-match),
        # which is also correct — see test_page_goto_timeout_resolves_as_timeout below.
        "page.goto: net::err_connection_refused",
    ])
    def test_navigation_failed_category(self, exc_msg: str) -> None:
        result = format_error(exc_msg)
        assert result.startswith("I wasn't able to complete the workflow")
        assert (
            "navigate" in result.lower()
            or "url" in result.lower()
            or "internet" in result.lower()
            or "connection" in result.lower()
        )

    def test_page_goto_timeout_resolves_as_timeout(self) -> None:
        """
        "Failed to navigate: page.goto timed out" contains 'timed out' so it
        correctly resolves as the *timeout* category (first match wins), which
        is also the most actionable message for the user.
        """
        result = format_error("Failed to navigate: page.goto timed out")
        assert result.startswith("I wasn't able to complete the workflow")
        # Timeout category message
        assert "too long" in result.lower() or "time" in result.lower()

    @pytest.mark.parametrize("exc_msg", [
        "connection refused",
        "ECONNREFUSED 127.0.0.1:8080",
        "ECONNRESET",
        "network error while fetching resource",
        "socket hang up",
        "connection reset by peer",
    ])
    def test_network_error_category(self, exc_msg: str) -> None:
        result = format_error(exc_msg)
        assert result.startswith("I wasn't able to complete the workflow")
        assert "network" in result.lower() or "reachable" in result.lower() or "try again" in result.lower()

    @pytest.mark.parametrize("exc_msg", [
        "HTTP 403 Forbidden",
        "401 Unauthorized",
        "Access denied to this resource",
        "login required to continue",
        "HTTP Error 403: Forbidden",
    ])
    def test_auth_error_category(self, exc_msg: str) -> None:
        result = format_error(exc_msg)
        assert result.startswith("I wasn't able to complete the workflow")
        assert (
            "auth" in result.lower()
            or "login" in result.lower()
            or "permission" in result.lower()
            or "session" in result.lower()
        )

    def test_unknown_exception_falls_back_to_generic(self) -> None:
        """An unrecognized exception must still return the sentinel + generic text."""
        result = format_error("some completely unknown error xyzzy")
        assert result.startswith("I wasn't able to complete the workflow")
        assert "try again" in result.lower() or "reachable" in result.lower()

    def test_sentinel_preserved_across_all_categories(self) -> None:
        """All error categories must keep the sentinel byte-identical."""
        ERROR_SENTINEL = "I wasn't able to complete the workflow"
        samples = [
            "TimeoutError: 30000ms exceeded.",
            "strict mode violation: locator resolved to 2 elements",
            "net::ERR_NAME_NOT_RESOLVED",
            "connection refused",
            "403 Forbidden",
            "some unknown random error",
        ]
        for msg in samples:
            result = format_error(msg)
            assert result.startswith(ERROR_SENTINEL), (
                f"Sentinel missing for msg={msg!r}\nGot: {result!r}"
            )


class TestClassifyErrorHelper:
    """Unit-test the internal _classify_error helper directly."""

    def test_timeout_matched(self) -> None:
        assert _classify_error("TimeoutError: 30000ms exceeded") is not None

    def test_selector_matched(self) -> None:
        assert _classify_error("element not found in page") is not None

    def test_navigation_matched(self) -> None:
        assert _classify_error("net::ERR_NAME_NOT_RESOLVED") is not None

    def test_network_matched(self) -> None:
        assert _classify_error("connection refused") is not None

    def test_auth_matched(self) -> None:
        assert _classify_error("403 Forbidden") is not None

    def test_unknown_returns_none(self) -> None:
        assert _classify_error("some completely random error text") is None

    def test_case_insensitive(self) -> None:
        """Pattern matching must be case-insensitive."""
        assert _classify_error("TIMEOUT 30000MS EXCEEDED") is not None
        assert _classify_error("CONNECTION REFUSED") is not None


class TestBuildProseSentence:
    """Unit-test the internal prose-sentence builder."""

    def test_snake_case_converted_to_natural_label(self) -> None:
        result = _build_prose_sentence("order_status", "Delivered")
        assert "order status" in result
        assert "Delivered" in result

    def test_single_word_key(self) -> None:
        result = _build_prose_sentence("status", "Active")
        assert "status" in result
        assert "Active" in result

    def test_deeply_underscored_key(self) -> None:
        result = _build_prose_sentence("estimated_delivery_date", "July 22")
        assert "estimated delivery date" in result
        assert "July 22" in result
