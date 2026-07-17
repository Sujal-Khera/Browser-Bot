"""
browserbot/agents/pattern_extractor/generator.py — Step 3.4: Spec generation logic.

Compiles a validated ActionLog and a ConfirmedOutput (parameters + metadata)
into a WorkflowSpec (the Intermediate Representation).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from browserbot import __version__
from browserbot.agents.pattern_extractor.confirmer import ConfirmedOutput
from browserbot.logging import get_logger
from browserbot.models.action_log import ActionLog, ExtractTextStep, ExtractAttributeStep
from browserbot.models.workflow_spec import (
    IROutput,
    IRParameter,
    WorkflowInfo,
    WorkflowMetadata,
    WorkflowSpec,
)

log = get_logger(__name__)


def generate_workflow_spec(
    action_log: ActionLog,
    confirmed: ConfirmedOutput,
) -> WorkflowSpec:
    """
    Compile ActionLog and ConfirmedOutput into a WorkflowSpec (IR).

    Args:
        action_log: The validated ActionLog (Phase 2).
        confirmed:  The confirmed output (Phase 3.2).

    Returns:
        A validated WorkflowSpec object.
    """
    log.info(
        "Generating WorkflowSpec IR",
        extra={
            "session_id": action_log.metadata.session_id,
            "confirmed_params": len(confirmed.parameters),
        },
    )

    # 1. Build Metadata
    metadata = WorkflowMetadata(
        generator_version=__version__,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_session_id=action_log.metadata.session_id,
    )

    # 2. Build Workflow Info
    workflow_desc = (
        confirmed.workflow_description
        or action_log.metadata.workflow_hint
        or f"Automated browser workflow on {action_log.metadata.site}"
    )
    workflow_info = WorkflowInfo(
        site=action_log.metadata.site,
        start_url=action_log.metadata.start_url or "",
        description=workflow_desc,
    )

    # 3. Map parameters
    parameters: list[IRParameter] = []
    # Index parameters by log_step_index for fast lookup during step compilation
    param_map: dict[int, str] = {}

    for param in confirmed.parameters:
        parameters.append(
            IRParameter(
                name=param.name,
                example_value=param.example_value,
                log_step_index=param.log_step_index,
                description=param.description,
                is_sensitive=param.is_sensitive,
                is_optional=param.is_optional,
            )
        )
        param_map[param.log_step_index] = param.name

    # 4. Map steps and parameter references
    spec_steps: list[dict[str, Any]] = []
    for step in action_log.steps:
        step_dict = step.model_dump(mode="json", exclude_none=True)
        # Bind parameter reference if this step was parameterised
        if step.step_index in param_map:
            step_dict["parameter_name"] = param_map[step.step_index]
        spec_steps.append(step_dict)

    # 5. Extract Outputs from the log steps (extract_text / extract_attribute)
    outputs: list[IROutput] = []
    for step in action_log.steps:
        if isinstance(step, (ExtractTextStep, ExtractAttributeStep)):
            # Fallback variable name if not present or malformed
            var_name = getattr(step, "output_variable", "") or f"extracted_val_{step.step_index}"
            # Normalize to snake_case
            var_name = re.sub(r"[^a-z0-9]+", "_", var_name.lower()).strip("_")
            if not var_name or not var_name[0].isalpha():
                var_name = f"output_{step.step_index}"

            outputs.append(
                IROutput(
                    name=var_name,
                    log_step_index=step.step_index,
                    selector=step.selector.model_dump(mode="json", exclude_none=True),
                    description=f"Extracted output from field '{step.selector.value}'",
                )
            )

    # 6. Build the WorkflowSpec model
    spec = WorkflowSpec(
        schema_version="1.0",
        metadata=metadata,
        workflow=workflow_info,
        steps=spec_steps,
        parameters=parameters,
        fixed_step_indices=list(confirmed.fixed_step_indices),
        outputs=outputs,
    )

    log.info(
        "WorkflowSpec generation complete",
        extra={
            "steps": len(spec.steps),
            "parameters": len(spec.parameters),
            "outputs": len(spec.outputs),
        },
    )
    return spec
