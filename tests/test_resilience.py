"""
tests/test_resilience.py — Phase 8A: Selector Resilience Unit Tests.

Validates the deterministic prioritised selector fallback resolution strategy,
verifying priority routing, fallback paths, and graceful failure behaviors.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from browserbot.runtime.resilience import resolve_locator


@pytest.mark.asyncio
async def test_resolve_locator_aria_role_priority() -> None:
    """Verifies that ARIA Role strategy takes highest priority when available."""
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)

    mock_page.get_by_role = MagicMock(return_value=mock_locator)
    mock_page.get_by_label = MagicMock()

    selector = {
        "strategy": "role",
        "value": "textbox:Fake order code",
        "aria_role": "textbox",
        "aria_name": "Fake order code",
    }

    resolved = await resolve_locator(mock_page, selector, timeout_ms=50)
    assert resolved == mock_locator
    mock_page.get_by_role.assert_called_once_with("textbox", name="Fake order code")
    # Higher priority succeeded immediately, so label lookup should not be called
    mock_page.get_by_label.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_locator_label_fallback() -> None:
    """Verifies that resolution falls back to label strategy if ARIA role is absent."""
    mock_page = MagicMock()
    
    # ARIA role candidate returns count 0 (not found)
    mock_role_loc = MagicMock()
    mock_role_loc.count = AsyncMock(return_value=0)
    mock_page.get_by_role = MagicMock(return_value=mock_role_loc)

    # Label candidate returns count 1 (found)
    mock_label_loc = MagicMock()
    mock_label_loc.count = AsyncMock(return_value=1)
    mock_page.get_by_label = MagicMock(return_value=mock_label_loc)

    selector = {
        "strategy": "role",
        "value": "textbox:Fake order code",
        "aria_role": "textbox",
        "aria_name": "Fake order code",
    }

    resolved = await resolve_locator(mock_page, selector, timeout_ms=50)
    assert resolved == mock_label_loc
    mock_page.get_by_role.assert_called_with("textbox", name="Fake order code")
    mock_page.get_by_label.assert_called_with("Fake order code")


@pytest.mark.asyncio
async def test_resolve_locator_placeholder_fallback() -> None:
    """Verifies that resolution falls back to placeholder strategy if higher priorities fail."""
    mock_page = MagicMock()

    # Role and Label candidates return count 0
    mock_fail_loc = MagicMock()
    mock_fail_loc.count = AsyncMock(return_value=0)
    mock_page.get_by_role = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_label = MagicMock(return_value=mock_fail_loc)

    # Placeholder candidate returns count 1
    mock_placeholder_loc = MagicMock()
    mock_placeholder_loc.count = AsyncMock(return_value=1)
    mock_page.get_by_placeholder = MagicMock(return_value=mock_placeholder_loc)

    selector = {
        "strategy": "role",
        "value": "textbox:Fake order code",
        "aria_role": "textbox",
        "aria_name": "Fake order code",
    }

    resolved = await resolve_locator(mock_page, selector, timeout_ms=50)
    assert resolved == mock_placeholder_loc
    mock_page.get_by_placeholder.assert_called_with("Fake order code")


@pytest.mark.asyncio
async def test_resolve_locator_text_fallback() -> None:
    """Verifies that resolution falls back to text matching if role/label/placeholder fail."""
    mock_page = MagicMock()

    mock_fail_loc = MagicMock()
    mock_fail_loc.count = AsyncMock(return_value=0)
    mock_page.get_by_role = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_label = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_placeholder = MagicMock(return_value=mock_fail_loc)

    # Text candidate returns count 1
    mock_text_loc = MagicMock()
    mock_text_loc.count = AsyncMock(return_value=1)
    mock_page.get_by_text = MagicMock(return_value=mock_text_loc)

    selector = {
        "strategy": "role",
        "value": "textbox:Fake order code",
        "aria_role": "textbox",
        "aria_name": "Fake order code",
    }

    resolved = await resolve_locator(mock_page, selector, timeout_ms=50)
    assert resolved == mock_text_loc
    mock_page.get_by_text.assert_called_with("Fake order code")


@pytest.mark.asyncio
async def test_resolve_locator_raw_selector_fallback() -> None:
    """Verifies that resolution falls back to raw selector (CSS/XPath) as last resort."""
    mock_page = MagicMock()

    mock_fail_loc = MagicMock()
    mock_fail_loc.count = AsyncMock(return_value=0)
    mock_page.get_by_role = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_label = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_placeholder = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_text = MagicMock(return_value=mock_fail_loc)

    # Raw CSS selector candidate returns count 1
    mock_raw_loc = MagicMock()
    mock_raw_loc.count = AsyncMock(return_value=1)
    mock_page.locator = MagicMock(return_value=mock_raw_loc)

    selector = {
        "strategy": "role",
        "value": "textbox:Fake order code",
        "aria_role": "textbox",
        "aria_name": "Fake order code",
    }

    resolved = await resolve_locator(mock_page, selector, timeout_ms=50)
    assert resolved == mock_raw_loc
    mock_page.locator.assert_called_with("textbox:Fake order code")


@pytest.mark.asyncio
async def test_resolve_locator_timeout_raises_timeout_error() -> None:
    """Verifies that resolution times out gracefully and raises TimeoutError when no candidates match."""
    mock_page = MagicMock()

    # All candidates return count 0
    mock_fail_loc = MagicMock()
    mock_fail_loc.count = AsyncMock(return_value=0)
    mock_page.get_by_role = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_label = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_placeholder = MagicMock(return_value=mock_fail_loc)
    mock_page.get_by_text = MagicMock(return_value=mock_fail_loc)
    mock_page.locator = MagicMock(return_value=mock_fail_loc)

    selector = {
        "strategy": "role",
        "value": "textbox:Fake order code",
        "aria_role": "textbox",
        "aria_name": "Fake order code",
    }

    with pytest.raises(TimeoutError, match="Could not resolve any element for selector"):
        await resolve_locator(mock_page, selector, timeout_ms=10)
