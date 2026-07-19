"""
tests/test_orchestrator_events.py — Comprehensive tests for WebSocket Log & Stage-Event Channel,
screenshot streaming, callback isolation, session isolation, and multiple clients support.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from browserbot.models.stage_event import StageEvent, get_base64_screenshot
from browserbot.orchestrator.pipeline import OrchestrationPipeline
from browserbot.server.app import app
from browserbot.server.db import SessionStateStore
from browserbot.server.ws_manager import ws_manager


def test_stage_event_model() -> None:
    """Verifies that the StageEvent model compiles, serializes and formats correctly."""
    event = StageEvent(
        stage="stage_1_scrubbing",
        status="in_progress",
        message="Scrubbing data",
        metadata={"detail": "PII scrubbing"}
    )
    data = event.to_dict()
    assert data["stage"] == "stage_1_scrubbing"
    assert data["status"] == "in_progress"
    assert data["message"] == "Scrubbing data"
    assert data["metadata"] == {"detail": "PII scrubbing"}
    assert "timestamp" in data

    json_str = event.to_json()
    decoded = json.loads(json_str)
    assert decoded["stage"] == "stage_1_scrubbing"


def test_get_base64_screenshot_helper(tmp_path: Path) -> None:
    """Verifies screenshot base64 serialization and missing file returns None."""
    # Test missing file
    assert get_base64_screenshot(str(tmp_path / "nonexistent.png")) is None

    # Test existing file
    file_path = tmp_path / "test.png"
    content = b"fake_png_data"
    file_path.write_bytes(content)
    encoded = get_base64_screenshot(str(file_path))
    assert encoded == base64.b64encode(content).decode("utf-8")


def test_callback_failure_isolation(tmp_path: Path) -> None:
    """Verifies that an observer callback raising an exception does not crash the pipeline."""
    pipeline = OrchestrationPipeline(dry_run=True)

    # Simple bad callback that raises unconditionally
    def bad_callback(event: StageEvent) -> None:
        raise ValueError("Simulated callback exception")

    # Use the existing valid fixture so ActionLog.from_file succeeds
    fixture_path = Path(__file__).parent / "fixtures" / "session_zero_params.json"

    from browserbot.models.action_log import ActionLog
    valid_action_log = ActionLog.from_file(fixture_path)

    # Mock all downstream stages to run fast and succeed
    with patch("browserbot.orchestrator.pipeline.ActionLog") as mock_al_cls, \
         patch("browserbot.orchestrator.pipeline.scrub") as mock_scrub, \
         patch("browserbot.orchestrator.pipeline.PatternExtractor.extract") as mock_extract, \
         patch("browserbot.orchestrator.pipeline.confirm_parameters") as mock_confirm, \
         patch("browserbot.orchestrator.pipeline.generate_workflow_spec") as mock_spec, \
         patch("browserbot.orchestrator.pipeline.CodeGenerator"), \
         patch("browserbot.orchestrator.pipeline.ValidationPipeline"), \
         patch("browserbot.orchestrator.pipeline.PipelineCoordinator.run") as mock_coord, \
         patch("browserbot.orchestrator.pipeline.Packager") as mock_pkg:

        # Ensure pipeline gets a valid ActionLog object when it loads the file
        mock_al_cls.from_file.return_value = valid_action_log

        # Configure downstream mock return values
        mock_scrub.return_value = MagicMock(action_log=valid_action_log, value_map={})
        mock_extract.return_value = MagicMock()
        mock_confirm.return_value = MagicMock()
        mock_spec.return_value = MagicMock()
        mock_coord.return_value = MagicMock(overall_success=True)
        mock_pkg.return_value.package.return_value = MagicMock()
        mock_pkg.return_value.verify_installation.return_value = True

        # Running the pipeline with bad_callback must succeed despite exceptions in callback
        res = pipeline.run(
            raw_action_log_path=fixture_path,
            output_dir=tmp_path / "dummy_out",
            package_dir=tmp_path / "dummy_pkg",
            on_stage_event=bad_callback,
        )
        assert res is not None


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fixture that initializes a clean test SQLite state DB for the FastAPI client."""
    db_file = tmp_path / "test_state.db"
    monkeypatch.setenv("BROWSERBOT_STATE_DB_PATH", str(db_file))
    SessionStateStore(db_path=db_file)
    with TestClient(app) as test_client:
        yield test_client


def test_websocket_connection_and_streaming(client: TestClient) -> None:
    """Verifies that the WebSocket endpoint accepts connections and streams events."""
    session_id = "session_ws_test"
    db = SessionStateStore()
    
    # Setup mock session state
    paths = {
        "action_log": "dummy_log.json",
        "extractor_output": "dummy_extractor_output.json",
        "confirmed_output": "dummy_confirmed_output.json",
        "workflow_spec": "dummy_spec.json",
        "output_dir": "dummy_out"
    }
    db.update_session(session_id, "recording", paths)

    with client.websocket_connect(f"/sessions/ws/sessions/{session_id}") as websocket:
        # Send an event
        event = StageEvent(stage="stage_1_scrubbing", status="success", message="Success!")
        
        import asyncio
        asyncio.run(ws_manager.broadcast(session_id, event.to_dict()))
        
        # Verify receipt
        data = websocket.receive_json()
        assert data["stage"] == "stage_1_scrubbing"
        assert data["status"] == "success"
        assert data["message"] == "Success!"


def test_multiple_clients_receive_broadcast(client: TestClient) -> None:
    """Verifies that multiple clients connected to the same session receive identical broadcasts."""
    session_id = "session_multi_test"
    db = SessionStateStore()
    db.update_session(session_id, "recording", {})

    with client.websocket_connect(f"/sessions/ws/sessions/{session_id}") as ws1, \
         client.websocket_connect(f"/sessions/ws/sessions/{session_id}") as ws2:
        
        event = StageEvent(stage="stage_2_pattern_extraction", status="in_progress", message="Running extraction")
        import asyncio
        asyncio.run(ws_manager.broadcast(session_id, event.to_dict()))

        # Both websockets should receive it
        data1 = ws1.receive_json()
        data2 = ws2.receive_json()

        assert data1["stage"] == "stage_2_pattern_extraction"
        assert data2["stage"] == "stage_2_pattern_extraction"


def test_client_disconnect_recovery(client: TestClient) -> None:
    """Verifies that ws_manager handles disconnected clients gracefully without breaking broadcasts."""
    session_id = "session_disconnect_test"
    db = SessionStateStore()
    db.update_session(session_id, "recording", {})

    with client.websocket_connect(f"/sessions/ws/sessions/{session_id}") as ws1:
        # Establish connection then disconnect immediately by closing ws1 block
        pass

    # A subsequent broadcast should run cleanly without failing
    event = StageEvent(stage="stage_3_parameter_confirmation", status="success", message="Confirmed")
    import asyncio
    asyncio.run(ws_manager.broadcast(session_id, event.to_dict()))


def test_session_isolation(client: TestClient) -> None:
    """Verifies that events are routed only to clients connected to that specific session ID."""
    session_a = "session_a"
    session_b = "session_b"
    
    db = SessionStateStore()
    db.update_session(session_a, "recording", {})
    db.update_session(session_b, "recording", {})

    with client.websocket_connect(f"/sessions/ws/sessions/{session_a}") as ws_a, \
         client.websocket_connect(f"/sessions/ws/sessions/{session_b}") as ws_b:
        
        # Broadcast to Session A
        event_a = StageEvent(stage="stage_1_scrubbing", status="success", message="A success")
        import asyncio
        asyncio.run(ws_manager.broadcast(session_a, event_a.to_dict()))

        # ws_a should receive it
        data_a = ws_a.receive_json()
        assert data_a["message"] == "A success"

        # ws_b should NOT receive it (Starlette TestClient websocket raises RuntimeError if queue is empty)
        with pytest.raises(RuntimeError):
            ws_b.receive_json()


def test_screenshot_event_generation_and_delivery(tmp_path: Path) -> None:
    """Verifies screenshot streaming on validator failure."""
    from browserbot.agents.validator.pipeline import ValidationPipeline
    from browserbot.agents.validator.harness import DryRunResult
    
    # Write dummy files to bypass file existence check, compilation check, and import check
    server_py = tmp_path / "server.py"
    server_py.write_text("def run_workflow(**kwargs):\n    pass\n", encoding="utf-8")
    
    mcp_tool_json = tmp_path / "mcp_tool.json"
    mcp_tool_json.write_text("{}", encoding="utf-8")

    # Mock DryRunHarness to return failure and generate a screenshot path
    mock_screenshot = tmp_path / "failure_mock.png"
    mock_screenshot.write_bytes(b"mock_screenshot_bytes")

    with patch("browserbot.agents.validator.pipeline.DryRunHarness") as mock_harness:
        mock_inst = MagicMock()
        mock_inst.run.return_value = DryRunResult(
            success=False,
            duration=1.2,
            output="I wasn't able to complete the workflow because strict mode failed",
            exception="Strict mode violation",
            screenshot_path=mock_screenshot
        )
        mock_harness.return_value = mock_inst

        # Track emitted events
        emitted_events = []
        def observer(event: StageEvent):
            emitted_events.append(event)

        spec = MagicMock()
        spec.workflow.site = "mocksite"
        spec.parameters = []
        spec.outputs = []

        pipeline = ValidationPipeline(screenshot_dir=tmp_path)
        report = pipeline.validate(spec, tool_dir=tmp_path, on_stage_event=observer)

        # Check that runtime event has screenshot in metadata
        runtime_events = [e for e in emitted_events if e.stage == "stage_5_runtime_dry_run"]
        assert len(runtime_events) > 0
        
        last_event = runtime_events[-1]
        assert last_event.status == "failed"
        assert "screenshot" in last_event.metadata
        assert last_event.metadata["screenshot"] == base64.b64encode(b"mock_screenshot_bytes").decode("utf-8")
