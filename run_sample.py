from pathlib import Path
from browserbot.orchestrator import OrchestrationPipeline

pipeline = OrchestrationPipeline(dry_run=True)
pipeline.run(
    raw_action_log_path="workflows/sessions/session_20260717T150935.json",
    output_dir="generated_tools/nobuycart_tracker",
    package_dir="packages/execute_nobuycart_com",
    register=True
)