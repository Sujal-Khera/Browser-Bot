"""
tests/test_pattern_extractor.py — Step 3.1/3.2 automated tests.

All tests use the dry-run mode or mock the LLM call via unittest.mock.
No Ollama connection is required.

Tests:
  1.  Extractor accepts ActionLog (dry-run)
  2.  Dry-run returns one parameter for one fill step
  3.  Dry-run marks fill steps as parameters, all others as fixed
  4.  Schema validation passes on valid extractor output
  5.  Schema validation rejects malformed output (missing required fields)
  6.  Schema validation rejects bad parameter name (not snake_case)
  7.  Retry logic: succeeds on second attempt after first returns bad JSON
  8.  Retry logic: raises ExtractionError after all retries exhausted
  9.  Retry logic: succeeds after first attempt returns markdown-fenced JSON
  10. Confirmer: auto_confirm accepts all parameters without interaction
  11. Confirmer: confirmed output validates against schema
  12. Confirmer: empty extractor output produces valid confirmed output
  13. Confirmer: to_extractor_output() round-trip preserves all fields
  14. _extract_json_from_text handles direct JSON
  15. _extract_json_from_text handles markdown-fenced JSON
  16. _extract_json_from_text handles trailing text after JSON
  17. _extract_json_from_text returns None for pure text

Run:
    python -m pytest tests/test_pattern_extractor.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from browserbot.agents.pattern_extractor.confirmer import ConfirmedOutput, confirm_parameters
from browserbot.agents.pattern_extractor.extractor import (
    ExtractionError,
    PatternExtractor,
    _extract_json_from_text,
)
from browserbot.agents.pattern_extractor.models import (
    ExtractedParameter,
    ExtractorOutput,
    ExtractorOutputValidator,
)
from browserbot.agents.pattern_extractor.generator import generate_workflow_spec
from browserbot.models.action_log import ActionLog
from browserbot.models.workflow_spec import WorkflowSpec, WorkflowSpecValidator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_SESSION = Path(__file__).parent / "fixtures" / "extractor_test_session.json"


def _load_fixture() -> ActionLog:
    return ActionLog.from_file(FIXTURE_SESSION)


def _make_valid_output(**kwargs) -> dict:
    """Build a minimal valid extractor output dict."""
    return {
        "parameters": kwargs.get(
            "parameters",
            [
                {
                    "name": "order_id",
                    "example_value": "NBC-2026-8F3K2Q",
                    "log_step_index": 2,
                }
            ],
        ),
        "fixed_step_indices": kwargs.get("fixed_step_indices", [0, 1, 3, 4, 5, 6]),
    }


# ---------------------------------------------------------------------------
# Test 1: Extractor accepts ActionLog (dry-run)
# ---------------------------------------------------------------------------


def test_extractor_accepts_action_log_dry_run() -> None:
    log = _load_fixture()
    extractor = PatternExtractor(dry_run=True)
    result = extractor.extract(log)
    assert isinstance(result, ExtractorOutput)


# ---------------------------------------------------------------------------
# Test 2: Dry-run returns one parameter for one fill step
# ---------------------------------------------------------------------------


def test_dry_run_returns_one_parameter_for_one_fill_step() -> None:
    log = _load_fixture()
    extractor = PatternExtractor(dry_run=True)
    result = extractor.extract(log)
    # The fixture has exactly one fill step (step_index=2)
    assert len(result.parameters) == 1
    assert result.parameters[0].log_step_index == 2
    assert result.parameters[0].example_value == "NBC-2026-8F3K2Q"


# ---------------------------------------------------------------------------
# Test 3: Dry-run classifies non-fill steps as fixed
# ---------------------------------------------------------------------------


def test_dry_run_fixed_step_indices_excludes_fill_steps() -> None:
    log = _load_fixture()
    extractor = PatternExtractor(dry_run=True)
    result = extractor.extract(log)
    # All non-fill step indices should be in fixed_step_indices
    # Fixture has 7 steps (0-6), step 2 is fill
    assert 2 not in result.fixed_step_indices
    for idx in [0, 1, 3, 4, 5, 6]:
        assert idx in result.fixed_step_indices


# ---------------------------------------------------------------------------
# Test 4: Schema validation passes on valid output
# ---------------------------------------------------------------------------


def test_schema_validation_passes_on_valid_output() -> None:
    validator = ExtractorOutputValidator()
    data = _make_valid_output()
    errors = validator.validate(data)
    assert errors == [], f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# Test 5: Schema validation rejects missing required fields
# ---------------------------------------------------------------------------


def test_schema_validation_rejects_missing_required_fields() -> None:
    validator = ExtractorOutputValidator()
    # Missing 'fixed_step_indices'
    data = {"parameters": []}
    errors = validator.validate(data)
    assert len(errors) > 0
    assert any("fixed_step_indices" in e for e in errors)


# ---------------------------------------------------------------------------
# Test 6: Schema validation rejects bad parameter name
# ---------------------------------------------------------------------------


def test_schema_validation_rejects_bad_parameter_name() -> None:
    validator = ExtractorOutputValidator()
    data = _make_valid_output(
        parameters=[
            {
                "name": "Order ID",   # spaces not allowed — must be snake_case
                "example_value": "123",
                "log_step_index": 2,
            }
        ]
    )
    errors = validator.validate(data)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# Test 7: Retry logic succeeds on second attempt (first returns bad JSON)
# ---------------------------------------------------------------------------


def test_retry_succeeds_on_second_attempt() -> None:
    log = _load_fixture()
    valid_response = json.dumps(_make_valid_output())
    call_count = {"n": 0}

    def fake_call(messages, *, model, temperature):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "This is not JSON at all."
        return valid_response

    with patch(
        "browserbot.agents.pattern_extractor.extractor._call_llm",
        side_effect=fake_call,
    ):
        extractor = PatternExtractor(dry_run=False, backend="ollama", max_retries=1)
        result = extractor.extract(log)

    assert call_count["n"] == 2
    assert isinstance(result, ExtractorOutput)
    assert len(result.parameters) == 1
    assert result.parameters[0].name == "order_id"


# ---------------------------------------------------------------------------
# Test 8: Retry logic raises ExtractionError after all retries exhausted
# ---------------------------------------------------------------------------


def test_retry_raises_after_all_retries_exhausted() -> None:
    log = _load_fixture()

    def always_bad(messages, *, model, temperature):
        return "Not JSON."

    with patch(
        "browserbot.agents.pattern_extractor.extractor._call_llm",
        side_effect=always_bad,
    ):
        extractor = PatternExtractor(dry_run=False, backend="ollama", max_retries=1)
        with pytest.raises(ExtractionError) as exc_info:
            extractor.extract(log)

    assert exc_info.value.attempts == 2  # initial + 1 retry


# ---------------------------------------------------------------------------
# Test 9: Succeeds after first attempt returns markdown-fenced JSON
# ---------------------------------------------------------------------------


def test_retry_handles_markdown_fenced_json() -> None:
    log = _load_fixture()
    valid_data = _make_valid_output()
    markdown_response = f"```json\n{json.dumps(valid_data)}\n```"

    with patch(
        "browserbot.agents.pattern_extractor.extractor._call_llm",
        return_value=markdown_response,
    ):
        extractor = PatternExtractor(dry_run=False, backend="ollama", max_retries=0)
        result = extractor.extract(log)

    assert isinstance(result, ExtractorOutput)
    assert len(result.parameters) == 1


# ---------------------------------------------------------------------------
# Test 10: Confirmer auto_confirm accepts all parameters
# ---------------------------------------------------------------------------


def test_confirmer_auto_confirm_accepts_all() -> None:
    extractor_output = ExtractorOutput(
        parameters=[
            ExtractedParameter(
                name="order_id",
                example_value="NBC-2026-8F3K2Q",
                log_step_index=2,
            ),
            ExtractedParameter(
                name="zip_code",
                example_value="10001",
                log_step_index=5,
            ),
        ],
        fixed_step_indices=[0, 1, 3, 4, 6],
    )
    confirmed = confirm_parameters(extractor_output, auto_confirm=True)
    assert len(confirmed.parameters) == 2
    assert confirmed.parameters[0].name == "order_id"
    assert confirmed.parameters[1].name == "zip_code"


# ---------------------------------------------------------------------------
# Test 11: Confirmed output validates against schema
# ---------------------------------------------------------------------------


def test_confirmed_output_validates_against_schema() -> None:
    extractor_output = ExtractorOutput(
        parameters=[
            ExtractedParameter(
                name="order_id",
                example_value="NBC-2026-8F3K2Q",
                log_step_index=2,
                description="The order code to look up",
            ),
        ],
        fixed_step_indices=[0, 1, 3, 4],
        workflow_description="Looks up order status on NoBuyCart.",
    )
    confirmed = confirm_parameters(extractor_output, auto_confirm=True)
    output = confirmed.to_extractor_output()

    validator = ExtractorOutputValidator()
    errors = validator.validate(output.model_dump_for_schema())
    assert errors == [], f"Schema errors: {errors}"


# ---------------------------------------------------------------------------
# Test 12: Empty extractor output produces valid confirmed output
# ---------------------------------------------------------------------------


def test_confirmed_output_with_no_parameters() -> None:
    extractor_output = ExtractorOutput(
        parameters=[],
        fixed_step_indices=[0, 1, 2, 3],
        workflow_description="Checks the homepage banner.",
    )
    confirmed = confirm_parameters(extractor_output, auto_confirm=True)
    assert confirmed.parameters == []
    output = confirmed.to_extractor_output()
    validator = ExtractorOutputValidator()
    errors = validator.validate(output.model_dump_for_schema())
    assert errors == []


# ---------------------------------------------------------------------------
# Test 13: to_extractor_output() round-trip preserves all fields
# ---------------------------------------------------------------------------


def test_confirmed_to_extractor_output_round_trip() -> None:
    param = ExtractedParameter(
        name="tracking_number",
        example_value="TRK-001",
        log_step_index=3,
        description="Shipment tracking number",
        is_sensitive=False,
    )
    extractor_output = ExtractorOutput(
        parameters=[param],
        fixed_step_indices=[0, 1, 2],
        workflow_description="Tracks a shipment.",
    )
    confirmed = ConfirmedOutput(
        parameters=[param],
        fixed_step_indices=[0, 1, 2],
        workflow_description="Tracks a shipment.",
    )
    output = confirmed.to_extractor_output()
    assert output.parameters[0].name == "tracking_number"
    assert output.fixed_step_indices == [0, 1, 2]
    assert output.workflow_description == "Tracks a shipment."


# ---------------------------------------------------------------------------
# Tests 14-17: _extract_json_from_text helpers
# ---------------------------------------------------------------------------


def test_extract_json_direct() -> None:
    data = {"parameters": [], "fixed_step_indices": [0, 1]}
    result = _extract_json_from_text(json.dumps(data))
    assert result == data


def test_extract_json_markdown_fenced() -> None:
    data = {"parameters": [], "fixed_step_indices": [0, 1]}
    fenced = f"```json\n{json.dumps(data)}\n```"
    result = _extract_json_from_text(fenced)
    assert result == data


def test_extract_json_trailing_text() -> None:
    data = {"parameters": [], "fixed_step_indices": [0]}
    text = json.dumps(data) + "\n\nNote: this is the output."
    result = _extract_json_from_text(text)
    assert result == data


def test_extract_json_returns_none_for_pure_text() -> None:
    result = _extract_json_from_text("I cannot do this task.")
    assert result is None


# ---------------------------------------------------------------------------
# Tests 18-20: Edge Case / WorkflowSpec IR Generation (Step 3.3 / 3.4)
# ---------------------------------------------------------------------------


def test_edge_case_zero_parameters() -> None:
    log_path = Path(__file__).parent / "fixtures" / "session_zero_params.json"
    log = ActionLog.from_file(log_path)

    extractor = PatternExtractor(dry_run=True)
    extractor_output = extractor.extract(log)

    # Assert extractor output has 0 parameters
    assert len(extractor_output.parameters) == 0
    assert len(extractor_output.fixed_step_indices) == 2

    confirmed = confirm_parameters(extractor_output, auto_confirm=True)
    assert len(confirmed.parameters) == 0

    spec = generate_workflow_spec(log, confirmed)
    assert isinstance(spec, WorkflowSpec)
    assert spec.schema_version == "1.0"
    assert len(spec.parameters) == 0
    assert len(spec.fixed_step_indices) == 2

    # Outputs: one extract_text step in zero_params
    assert len(spec.outputs) == 1
    assert spec.outputs[0].name == "header"

    # Validation passes
    validator = WorkflowSpecValidator()
    validator.assert_valid(spec.model_dump(mode="json", exclude_none=True))


def test_edge_case_single_parameter() -> None:
    log_path = Path(__file__).parent / "fixtures" / "session_single_param.json"
    log = ActionLog.from_file(log_path)

    extractor = PatternExtractor(dry_run=True)
    extractor_output = extractor.extract(log)

    # In dry-run, fill steps are parameters (1 fill step)
    assert len(extractor_output.parameters) == 1

    confirmed = confirm_parameters(extractor_output, auto_confirm=True)
    assert len(confirmed.parameters) == 1

    spec = generate_workflow_spec(log, confirmed)
    assert isinstance(spec, WorkflowSpec)
    assert len(spec.parameters) == 1
    assert spec.parameters[0].name == "search_input"
    assert spec.parameters[0].is_optional is False

    # Validation passes
    validator = WorkflowSpecValidator()
    validator.assert_valid(spec.model_dump(mode="json", exclude_none=True))


def test_edge_case_multiple_parameters() -> None:
    log_path = Path(__file__).parent / "fixtures" / "session_multi_params.json"
    log = ActionLog.from_file(log_path)

    extractor = PatternExtractor(dry_run=True)
    extractor_output = extractor.extract(log)

    # 4 fill steps in session_multi_params
    assert len(extractor_output.parameters) == 4

    # Mark referral_code optional manually for the test
    raw_params = list(extractor_output.parameters)
    # referral_code is the 4th parameter (index 3)
    raw_params[3] = raw_params[3].model_copy(update={"is_optional": True})
    extractor_output = extractor_output.model_copy(update={"parameters": raw_params})

    confirmed = confirm_parameters(extractor_output, auto_confirm=True)
    assert len(confirmed.parameters) == 4
    assert confirmed.parameters[3].is_optional is True

    spec = generate_workflow_spec(log, confirmed)
    assert isinstance(spec, WorkflowSpec)
    assert len(spec.parameters) == 4

    # Assert usernames/passwords/confirm_password mapped correctly
    assert spec.parameters[0].name == "username"
    assert spec.parameters[1].name == "password"
    assert spec.parameters[2].name == "confirm_password"
    assert spec.parameters[3].name == "referral_code"

    assert spec.parameters[1].is_sensitive is True
    assert spec.parameters[2].is_sensitive is True
    assert spec.parameters[3].is_optional is True

    # Verify parameter reference mapping in steps
    assert spec.steps[1]["parameter_name"] == "username"
    assert spec.steps[2]["parameter_name"] == "password"
    assert spec.steps[3]["parameter_name"] == "confirm_password"
    assert spec.steps[4]["parameter_name"] == "referral_code"

    # Validation passes
    validator = WorkflowSpecValidator()
    validator.assert_valid(spec.model_dump(mode="json", exclude_none=True))
