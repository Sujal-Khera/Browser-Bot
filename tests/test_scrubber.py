"""
tests/test_scrubber.py — Step 2.4 automated tests for the PII scrubber.

Tests the pure-function API: scrub() returns a new ActionLog in
ScrubResult.action_log; the original ActionLog is never modified.

Tests:
  1. Password field is redacted
  2. Multiple distinct passwords get distinct placeholders
  3. Repeated same password reuses the same placeholder
  4. Username field is NOT redacted
  5. Normal form fields are preserved unchanged
  6. Configurable extra_selectors triggers redaction
  7. Mixed workflow — only sensitive steps are touched
  8. Session JSON validates against the Action Log schema after scrubbing
  9. field_label keyword match triggers redaction
  10. Scrub result carries correct metadata
  11. Token field is redacted
  12. Scrubber does not modify non-fill steps
  13. Original ActionLog is never mutated (pure function guarantee)

Run:
    python -m pytest tests/test_scrubber.py -v
"""

from __future__ import annotations

from browserbot.models.action_log import (
    ActionLog,
    ActionLogValidator,
    ClickStep,
    FillStep,
    GotoStep,
    SelectorInfo,
    SessionMetadata,
)
from browserbot.recorder.scrubber import Scrubber, ScrubResult, scrub


# ---------------------------------------------------------------------------
# Helpers — build minimal ActionLogs for testing
# ---------------------------------------------------------------------------

_METADATA = SessionMetadata(
    session_id="session_20260716T090000",
    site="example.com",
    recorded_at="2026-07-16T09:00:00Z",
    browserbot_version="0.1.0",
)


def _make_fill(
    index: int,
    selector_value: str,
    value: str,
    *,
    strategy: str = "css",
    field_label: str | None = None,
) -> FillStep:
    return FillStep(
        step_index=index,
        timestamp_offset=float(index) * 0.5,
        selector=SelectorInfo(value=selector_value, strategy=strategy),  # type: ignore[arg-type]
        value=value,
        is_sensitive=False,
        field_label=field_label,
    )


def _make_goto(index: int) -> GotoStep:
    return GotoStep(
        step_index=index,
        timestamp_offset=float(index) * 0.5,
        url="https://example.com/login",
        wait_until="networkidle",
    )


def _make_click(index: int, selector_value: str) -> ClickStep:
    return ClickStep(
        step_index=index,
        timestamp_offset=float(index) * 0.5,
        selector=SelectorInfo(value=selector_value, strategy="css"),
    )


def _build_log(*steps) -> ActionLog:
    return ActionLog(
        schema_version="1.0",
        metadata=_METADATA,
        steps=list(steps),
    )


# ---------------------------------------------------------------------------
# Test 1: password field is redacted
# ---------------------------------------------------------------------------


def test_password_field_is_redacted() -> None:
    original = _build_log(
        _make_goto(0),
        _make_fill(1, "input[type=password]", "hunter2"),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    assert result.scrubbed_count == 1
    assert result.secret_count == 1

    fill_step = scrubbed.steps[1]
    assert isinstance(fill_step, FillStep)
    assert fill_step.value == "__SECRET_1__"
    assert fill_step.is_sensitive is True
    assert "hunter2" not in fill_step.value


# ---------------------------------------------------------------------------
# Test 2: multiple distinct passwords get distinct placeholders
# ---------------------------------------------------------------------------


def test_multiple_distinct_passwords_get_distinct_placeholders() -> None:
    original = _build_log(
        _make_fill(0, "input[name=password]", "first_secret"),
        _make_fill(1, "input#confirm_password", "second_secret"),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    assert result.scrubbed_count == 2
    assert result.secret_count == 2

    fill_1 = scrubbed.steps[0]
    fill_2 = scrubbed.steps[1]
    assert isinstance(fill_1, FillStep)
    assert isinstance(fill_2, FillStep)
    assert fill_1.value == "__SECRET_1__"
    assert fill_2.value == "__SECRET_2__"
    assert fill_1.value != fill_2.value


# ---------------------------------------------------------------------------
# Test 3: repeated same password reuses the same placeholder
# ---------------------------------------------------------------------------


def test_repeated_secret_reuses_same_placeholder() -> None:
    same_password = "reused_password_123"
    original = _build_log(
        _make_fill(0, "input[type=password]", same_password),
        _make_fill(1, "input#confirm_password", same_password),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    # Two steps were scrubbed but only ONE unique secret was seen
    assert result.scrubbed_count == 2
    assert result.secret_count == 1

    fill_1 = scrubbed.steps[0]
    fill_2 = scrubbed.steps[1]
    assert isinstance(fill_1, FillStep)
    assert isinstance(fill_2, FillStep)
    # Same value → same placeholder
    assert fill_1.value == fill_2.value == "__SECRET_1__"


# ---------------------------------------------------------------------------
# Test 4: username field is NOT redacted
# ---------------------------------------------------------------------------


def test_username_not_redacted() -> None:
    original = _build_log(
        _make_fill(0, "input[name=username]", "john.doe@example.com"),
        _make_fill(1, "input[type=password]", "s3cr3t"),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    username_step = scrubbed.steps[0]
    password_step = scrubbed.steps[1]
    assert isinstance(username_step, FillStep)
    assert isinstance(password_step, FillStep)

    # Username untouched
    assert username_step.value == "john.doe@example.com"
    assert username_step.is_sensitive is False

    # Password scrubbed
    assert password_step.value == "__SECRET_1__"
    assert password_step.is_sensitive is True

    assert result.scrubbed_count == 1


# ---------------------------------------------------------------------------
# Test 5: normal form fields are preserved unchanged
# ---------------------------------------------------------------------------


def test_normal_fields_preserved() -> None:
    original = _build_log(
        _make_goto(0),
        _make_fill(1, "input[name=order_id]", "NBC-2026-8F3K2Q"),
        _make_fill(2, "input#email", "user@example.com"),
        _make_fill(3, "textarea#comments", "Please leave at the door"),
        _make_click(4, "button[type=submit]"),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    assert result.scrubbed_count == 0
    assert result.secret_count == 0

    # All fill steps in the scrubbed copy are untouched
    for step in scrubbed.steps:
        if isinstance(step, FillStep):
            assert step.is_sensitive is False
            assert not step.value.startswith("__SECRET_")


# ---------------------------------------------------------------------------
# Test 6: configurable extra_selectors triggers redaction
# ---------------------------------------------------------------------------


def test_configurable_extra_selectors() -> None:
    # Use a selector whose name contains NO sensitive keywords at all
    INERT_SELECTOR = "input#internal_employee_id"   # no keyword match

    # Without extra_selectors: does not match any keyword
    result_no_extra = scrub(_build_log(_make_fill(0, INERT_SELECTOR, "EMP-00123")))
    assert result_no_extra.scrubbed_count == 0, (
        f"Expected 0 scrubbed but got {result_no_extra.scrubbed_count} "
        f"(selector may have accidentally matched a keyword)"
    )

    # With extra_selectors: should be redacted
    result_with_extra = Scrubber(
        extra_selectors={INERT_SELECTOR}
    ).scrub(_build_log(_make_fill(0, INERT_SELECTOR, "EMP-00123")))
    assert result_with_extra.scrubbed_count == 1
    scrubbed = result_with_extra.action_log
    assert scrubbed is not None
    fill = scrubbed.steps[0]
    assert isinstance(fill, FillStep)
    assert fill.value == "__SECRET_1__"


# ---------------------------------------------------------------------------
# Test 7: mixed workflow — only sensitive steps are touched
# ---------------------------------------------------------------------------


def test_mixed_workflow_only_sensitive_steps_touched() -> None:
    original = _build_log(
        _make_goto(0),
        _make_fill(1, "input[name=username]", "alice"),
        _make_fill(2, "input[name=password]", "alice_password"),
        _make_click(3, "button[type=submit]"),
        _make_fill(4, "input[name=search]", "order 12345"),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    assert result.scrubbed_count == 1
    assert result.step_indices == [2]

    # Non-fill steps in scrubbed log
    assert isinstance(scrubbed.steps[0], GotoStep)
    assert isinstance(scrubbed.steps[3], ClickStep)

    # Non-sensitive fills untouched in scrubbed log
    username = scrubbed.steps[1]
    search = scrubbed.steps[4]
    assert isinstance(username, FillStep)
    assert isinstance(search, FillStep)
    assert username.value == "alice"
    assert search.value == "order 12345"

    # Sensitive fill scrubbed
    pw = scrubbed.steps[2]
    assert isinstance(pw, FillStep)
    assert pw.value == "__SECRET_1__"
    assert pw.is_sensitive is True


# ---------------------------------------------------------------------------
# Test 8: session JSON validates against schema after scrubbing
# ---------------------------------------------------------------------------


def test_scrubbed_session_validates_against_schema() -> None:
    original = _build_log(
        _make_goto(0),
        _make_fill(1, "input[type=password]", "super_secret"),
        _make_click(2, "button#login"),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    validator = ActionLogValidator()
    data = scrubbed.model_dump(mode="json", exclude_none=True)
    errors = validator.validate(data)

    assert errors == [], f"Schema validation errors after scrubbing: {errors}"


# ---------------------------------------------------------------------------
# Test 9: field_label keyword match triggers redaction
# ---------------------------------------------------------------------------


def test_field_label_keyword_triggers_redaction() -> None:
    original = _build_log(
        _make_fill(
            0,
            selector_value="input.form-control",   # No keyword in selector
            value="my_password_value",
            field_label="Password",                  # Keyword in label
        ),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    assert result.scrubbed_count == 1
    fill = scrubbed.steps[0]
    assert isinstance(fill, FillStep)
    assert fill.value == "__SECRET_1__"
    assert fill.is_sensitive is True


# ---------------------------------------------------------------------------
# Test 10: ScrubResult metadata is correct
# ---------------------------------------------------------------------------


def test_scrub_result_metadata() -> None:
    original = _build_log(
        _make_fill(0, "input[name=password]", "pass1"),
        _make_fill(1, "input#confirm_password", "pass2"),
        _make_fill(2, "input[name=username]", "user1"),
    )
    result = scrub(original)

    assert isinstance(result, ScrubResult)
    assert result.scrubbed_count == 2
    assert result.secret_count == 2
    assert set(result.step_indices) == {0, 1}
    # result.action_log is a NEW object, not the original
    assert result.action_log is not original
    assert result.action_log is not None
    # value_map has 2 entries (in-memory only)
    assert len(result.value_map) == 2
    assert "pass1" in result.value_map
    assert "pass2" in result.value_map


# ---------------------------------------------------------------------------
# Test 11: keyword match on 'token' field
# ---------------------------------------------------------------------------


def test_token_field_redacted() -> None:
    original = _build_log(
        _make_fill(0, "input[name=api_token]", "ghp_secretapitoken123"),
    )
    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    assert result.scrubbed_count == 1
    fill = scrubbed.steps[0]
    assert isinstance(fill, FillStep)
    assert fill.value == "__SECRET_1__"


# ---------------------------------------------------------------------------
# Test 12: scrubber does not modify non-fill steps
# ---------------------------------------------------------------------------


def test_scrubber_does_not_modify_non_fill_steps() -> None:
    goto = _make_goto(0)
    click = _make_click(1, "button#submit")
    original = _build_log(goto, click)

    original_goto_url = original.steps[0].url  # type: ignore[attr-defined]
    original_click_sel = original.steps[1].selector.value

    result = scrub(original)
    scrubbed = result.action_log
    assert scrubbed is not None

    assert result.scrubbed_count == 0
    assert scrubbed.steps[0].url == original_goto_url  # type: ignore[attr-defined]
    assert scrubbed.steps[1].selector.value == original_click_sel


# ---------------------------------------------------------------------------
# Test 13: original ActionLog is never mutated (pure function guarantee)
# ---------------------------------------------------------------------------


def test_original_action_log_is_never_mutated() -> None:
    """
    Architecture freeze test: scrub() must be a pure function.

    The original ActionLog passed to scrub() must be bit-for-bit identical
    to what it was before the call. Only result.action_log contains scrubbed data.
    """
    original = _build_log(
        _make_fill(0, "input[type=password]", "plaintext_password"),
        _make_fill(1, "input[name=username]", "alice"),
    )

    # Capture original state
    original_pw_value = original.steps[0].value  # type: ignore[attr-defined]
    original_pw_sensitive = original.steps[0].is_sensitive  # type: ignore[attr-defined]
    original_user_value = original.steps[1].value  # type: ignore[attr-defined]

    result = scrub(original)

    # Original must be completely unchanged
    assert original.steps[0].value == original_pw_value == "plaintext_password"  # type: ignore[attr-defined]
    assert original.steps[0].is_sensitive == original_pw_sensitive == False  # type: ignore[attr-defined]
    assert original.steps[1].value == original_user_value == "alice"  # type: ignore[attr-defined]

    # Only result.action_log contains scrubbed data
    scrubbed = result.action_log
    assert scrubbed is not None
    assert scrubbed.steps[0].value == "__SECRET_1__"  # type: ignore[attr-defined]
    assert scrubbed.steps[0].is_sensitive is True  # type: ignore[attr-defined]
    assert scrubbed is not original
