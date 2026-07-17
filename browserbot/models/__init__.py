"""
browserbot.models — shared Pydantic data models for pipeline artifacts.

These models define the JSON contracts between pipeline stages.
Each model maps 1-to-1 to an artifact file produced by one stage and
consumed by the next.

Step 2.1 deliverable: ActionLog and ActionLogValidator.
"""

from browserbot.models.action_log import (
    ActionLog,
    ActionLogValidator,
    ClickStep,
    ExtractAttributeStep,
    ExtractTextStep,
    FillStep,
    GotoStep,
    HoverStep,
    PressKeyStep,
    ScreenshotStep,
    ScrollStep,
    SelectStep,
    CheckStep,
    SelectorInfo,
    SessionMetadata,
    WaitStep,
    Step,
    SCHEMA_PATH,
)
from browserbot.models.workflow_spec import (
    WorkflowSpec,
    WorkflowSpecValidator,
    IRParameter,
    IROutput,
)
from browserbot.models.mcp_tool import (
    MCPToolManifest,
    MCPToolManifestValidator,
)
from browserbot.models.validation_report import (
    ValidationReport,
    StageResult,
)
from browserbot.models.correction_payload import (
    CorrectionPayload,
)
from browserbot.models.package import (
    BrowserBotPackage,
    BrowserBotPackageValidator,
)

__all__ = [
    "ActionLog",
    "ActionLogValidator",
    "ClickStep",
    "ExtractAttributeStep",
    "ExtractTextStep",
    "FillStep",
    "GotoStep",
    "HoverStep",
    "PressKeyStep",
    "ScreenshotStep",
    "ScrollStep",
    "SelectStep",
    "CheckStep",
    "SelectorInfo",
    "SessionMetadata",
    "WaitStep",
    "Step",
    "SCHEMA_PATH",
    "WorkflowSpec",
    "WorkflowSpecValidator",
    "IRParameter",
    "IROutput",
    "MCPToolManifest",
    "MCPToolManifestValidator",
    "ValidationReport",
    "StageResult",
    "CorrectionPayload",
    "BrowserBotPackage",
    "BrowserBotPackageValidator",
]

