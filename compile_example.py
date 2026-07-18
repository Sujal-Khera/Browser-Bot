from browserbot.orchestrator import OrchestrationPipeline

pipeline = OrchestrationPipeline(dry_run=True)
pipeline.run(
    raw_action_log_path="workflows/sessions/session_20260718T120828.json",
    output_dir="generated_tools/practice_test_login",
    package_dir="packages/execute_practice_test_login",
    register=False
)