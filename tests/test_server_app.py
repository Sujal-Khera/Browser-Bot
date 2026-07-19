"""
tests/test_server_app.py — FastAPI Orchestration Server REST Route Tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from browserbot.server.app import app
from browserbot.server.db import SessionStateStore


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fixture that initializes a clean test SQLite state DB for the FastAPI client."""
    db_file = tmp_path / "test_state.db"
    
    # Patch the state DB path environment variable to point to our test database
    monkeypatch.setenv("BROWSERBOT_STATE_DB_PATH", str(db_file))
    
    # Trigger DB initialization
    SessionStateStore(db_path=db_file)
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient) -> None:
    """Verifies the REST API server can successfully run and respond to liveness check."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sessions_list_and_record_flow(client: TestClient) -> None:
    """Tests the record REST API endpoint and background recording task registration."""
    # List is initially empty
    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert resp.json() == []

    # Post record request
    payload = {"url": "https://example.com/login", "workflow_hint": "User login process"}
    with patch("browserbot.server.routes.sessions.run_recording_in_background") as mock_bg_task:
        resp = client.post("/sessions/record", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["stage"] == "recording"
        assert "session_" in data["session_id"]
        assert "raw_script" in data["artifact_paths"]
        assert "action_log" in data["artifact_paths"]
        
        # Verify background recording task was scheduled
        mock_bg_task.assert_called_once()

    # Get details for created session
    session_id = data["session_id"]
    resp_details = client.get(f"/sessions/{session_id}")
    assert resp_details.status_code == 200
    assert resp_details.json()["session_id"] == session_id


def test_extract_endpoint(client: TestClient, tmp_path: Path) -> None:
    """Verifies endpoint extracts parameters from session action logs."""
    session_id = "session_extract_123"
    action_log_file = tmp_path / f"{session_id}.json"
    
    # Pre-populate session log with a valid dummy structure (min_length=1)
    action_log_content = {
        "schema_version": "1.0",
        "metadata": {
            "session_id": session_id,
            "recorded_at": "2026-07-17T12:00:00Z",
            "site": "example.com",
            "browserbot_version": "0.1.0",
            "step_count": 1,
        },
        "steps": [
            {
                "step_index": 0,
                "action": "goto",
                "timestamp_offset": 0.0,
                "url": "https://example.com",
                "wait_until": "networkidle",
            }
        ]
    }
    action_log_file.write_text(json.dumps(action_log_content), encoding="utf-8")

    db = SessionStateStore()
    db.create_session(session_id, "recorded", {"action_log": str(action_log_file)})

    # Mock PatternExtractor behavior
    mock_extractor_inst = MagicMock()
    mock_extractor_inst.extract.return_value.model_dump_json.return_value = json.dumps({
        "parameters": [
            {
                "name": "username",
                "example_value": "alice",
                "log_step_index": 0,
                "description": "User field",
                "is_sensitive": False,
                "is_optional": False
            }
        ]
    })

    with patch("browserbot.server.routes.sessions.PatternExtractor", return_value=mock_extractor_inst):
        resp = client.post(f"/sessions/{session_id}/extract?dry_run=true")
        assert resp.status_code == 200
        extracted_data = resp.json()
        assert "parameters" in extracted_data
        assert extracted_data["parameters"][0]["name"] == "username"
        
        # Verify DB stage transitioned
        sess = db.get_session(session_id)
        assert sess["stage"] == "extracted"
        assert Path(sess["artifact_paths"]["extractor_output"]).exists()


def test_confirm_endpoint(client: TestClient, tmp_path: Path) -> None:
    """Verifies parameters confirmation compiles intermediate WorkflowSpec IR."""
    session_id = "session_confirm_123"
    action_log_file = tmp_path / f"{session_id}.json"
    action_log_content = {
        "schema_version": "1.0",
        "metadata": {
            "session_id": session_id,
            "recorded_at": "2026-07-17T12:00:00Z",
            "site": "example.com",
            "browserbot_version": "0.1.0",
            "step_count": 1,
        },
        "steps": [
            {
                "step_index": 0,
                "action": "goto",
                "timestamp_offset": 0.0,
                "url": "https://example.com",
                "wait_until": "networkidle",
            }
        ]
    }
    action_log_file.write_text(json.dumps(action_log_content), encoding="utf-8")

    db = SessionStateStore()
    db.create_session(session_id, "extracted", {"action_log": str(action_log_file)})

    # Confirm parameters payload
    confirm_payload = {
        "parameters": [
            {
                "name": "user_id",
                "example_value": "standard_user",
                "log_step_index": 0,
                "description": "Login identifier",
                "is_sensitive": False,
                "is_optional": False
            }
        ]
    }

    resp = client.post(f"/sessions/{session_id}/confirm", json=confirm_payload)
    assert resp.status_code == 200
        
    # Verify DB stage transitioned to confirmed
    sess = db.get_session(session_id)
    assert sess["stage"] == "confirmed"
    assert "workflow_spec" in sess["artifact_paths"]


def test_generate_endpoint(client: TestClient, tmp_path: Path) -> None:
    """Verifies REST endpoints for running code generation, validation and retry coordinator."""
    session_id = "session_gen_123"
    spec_file = tmp_path / "workflow_spec.json"
    spec_file_content = {
        "schema_version": "1.0",
        "metadata": {
            "generator_version": "0.1.0",
            "created_at": "2026-07-17T12:00:00Z",
            "source_session_id": session_id,
        },
        "workflow": {
            "site": "example.com",
            "start_url": "https://example.com",
            "description": "Example test",
        },
        "steps": [],
        "parameters": [],
        "fixed_step_indices": [],
        "outputs": []
    }
    spec_file.write_text(json.dumps(spec_file_content), encoding="utf-8")

    # Pre-write dummy validation report that will be read by the endpoint
    report_file = tmp_path / "validation_report.json"
    report_content = {"overall_success": True, "violations": []}
    report_file.write_text(json.dumps(report_content), encoding="utf-8")

    db = SessionStateStore()
    db.create_session(
        session_id, 
        "confirmed", 
        {
            "workflow_spec": str(spec_file), 
            "output_dir": str(tmp_path),
            "action_log": str(tmp_path / "action_log.json")
        }
    )

    mock_report = MagicMock()
    mock_report.overall_success = True
    mock_coordinator_inst = MagicMock()
    mock_coordinator_inst.run.return_value = mock_report

    with patch("browserbot.server.routes.sessions.PipelineCoordinator", return_value=mock_coordinator_inst):
        resp = client.post(f"/sessions/{session_id}/generate", json={})
        assert resp.status_code == 200
        assert resp.json()["overall_success"] is True
        
        sess = db.get_session(session_id)
        assert sess["stage"] == "generated"


def test_package_endpoint(client: TestClient, tmp_path: Path) -> None:
    """Verifies compilation of validated server script into packages."""
    session_id = "session_pkg_123"
    mcp_tool_file = tmp_path / "mcp_tool.json"
    mcp_tool_content = {
        "schema_version": "1.0",
        "mcp_tool_name": "execute_test",
        "description": "Runs tests",
        "parameters_schema": {
            "type": "object",
            "properties": {}
        },
        "metadata": {
            "browserbot_version": "0.1.0",
            "generated_at": "2026-07-17T12:00:00Z",
            "source_session_id": "session_pkg_123",
            "site": "example.com"
        }
    }
    mcp_tool_file.write_text(json.dumps(mcp_tool_content), encoding="utf-8")

    db = SessionStateStore()
    db.create_session(
        session_id,
        "generated",
        {
            "output_dir": str(tmp_path),
        }
    )

    # Pre-write dummy browserbot_package.json that will be read by the endpoint
    package_dir = tmp_path / "package_dir"
    package_dir.mkdir()
    pkg_manifest_file = package_dir / "browserbot_package.json"
    
    pkg_manifest_content = {
        "package_version": "1.0",
        "package_name": "execute_test",
        "entry_point": "server.py",
        "dependencies": ["fastmcp>=3.0.0", "playwright>=1.40.0"],
        "claude_config_snippet": {
            "command": "python",
            "args": ["server.py"],
            "env": {"BROWSERBOT_HEADLESS": "true"}
        },
        "metadata": {
            "browserbot_version": "0.1.0",
            "generated_at": "2026-07-17T00:00:00Z",
            "source_session_id": "session_test",
            "site": "test.site"
        }
    }
    pkg_manifest_file.write_text(json.dumps(pkg_manifest_content), encoding="utf-8")

    mock_packager_inst = MagicMock()
    # Mock packager method to return our custom pkg_manifest_file parent
    mock_packager_inst.package.return_value = MagicMock()
    mock_packager_inst.verify_installation.return_value = True

    with patch("browserbot.server.routes.sessions.Packager", return_value=mock_packager_inst):
         resp = client.post(f"/sessions/{session_id}/package", json={"package_dir": str(package_dir)})
         assert resp.status_code == 200
         assert resp.json()["package_name"] == "execute_test"
         
         sess = db.get_session(session_id)
         assert sess["stage"] == "packaged"


def test_register_endpoint(client: TestClient) -> None:
    """Verifies registry endpoint updates Claude Desktop configuration settings."""
    package_name = "execute_test_register"
    package_dir = Path("packages") / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    pkg_manifest_file = package_dir / "browserbot_package.json"
    
    pkg_manifest_content = {
        "package_version": "1.0",
        "package_name": package_name,
        "entry_point": "server.py",
        "dependencies": ["fastmcp>=3.0.0", "playwright>=1.40.0"],
        "claude_config_snippet": {
            "command": "python",
            "args": ["server.py"],
            "env": {"BROWSERBOT_HEADLESS": "true"}
        },
        "metadata": {
            "browserbot_version": "0.1.0",
            "generated_at": "2026-07-17T00:00:00Z",
            "source_session_id": "session_test",
            "site": "test.site"
        }
    }
    pkg_manifest_file.write_text(json.dumps(pkg_manifest_content), encoding="utf-8")
    
    mock_registry_inst = MagicMock()
    mock_registry_inst.register.return_value = {"mcpServers": {package_name: {"command": "python"}}}

    try:
        with patch("browserbot.server.routes.packages.ClaudeDesktopRegistry", return_value=mock_registry_inst):
             resp = client.post(f"/packages/{package_name}/register", json={})
             assert resp.status_code == 200
             assert "mcpServers" in resp.json()
             assert package_name in resp.json()["mcpServers"]
    finally:
        # Clean up created package directory
        if pkg_manifest_file.exists():
            pkg_manifest_file.unlink()
        if package_dir.exists():
            package_dir.rmdir()


def test_stage_update_endpoint(client: TestClient) -> None:
    """Verifies that the session stage update endpoint correctly changes stage in DB."""
    session_id = "session_stage_update_123"
    db = SessionStateStore()
    db.create_session(session_id, "recording", {"action_log": "log.json"})

    resp = client.post(f"/sessions/{session_id}/stage?stage=registered")
    assert resp.status_code == 200
    assert resp.json()["stage"] == "registered"

    sess = db.get_session(session_id)
    assert sess["stage"] == "registered"


def test_confirm_endpoint_parameter_customization(client: TestClient, tmp_path: Path) -> None:
    """Verifies that parameter edits (optional, sensitive, custom) save and compile cleanly."""
    session_id = "session_confirm_cust_123"
    action_log_file = tmp_path / f"{session_id}.json"
    action_log_content = {
        "schema_version": "1.0",
        "metadata": {
            "session_id": session_id,
            "recorded_at": "2026-07-17T12:00:00Z",
            "site": "example.com",
            "browserbot_version": "0.1.0",
            "step_count": 1,
        },
        "steps": [
            {
                "step_index": 0,
                "action": "goto",
                "timestamp_offset": 0.0,
                "url": "https://example.com",
                "wait_until": "networkidle",
            }
        ]
    }
    action_log_file.write_text(json.dumps(action_log_content), encoding="utf-8")

    db = SessionStateStore()
    db.create_session(session_id, "extracted", {"action_log": str(action_log_file)})

    # Payload matching frontend parameter customizations
    confirm_payload = {
        "parameters": [
            {
                "name": "user_id_custom", # Renamed
                "example_value": "custom_user",
                "log_step_index": 0,
                "description": "Customized login input",
                "is_sensitive": True, # Marked sensitive
                "is_optional": True # Marked optional
            },
            {
                "name": "added_manually", # Manually added
                "example_value": "dummy",
                "log_step_index": 0,
                "description": "Manual addition",
                "is_sensitive": False,
                "is_optional": False
            }
        ]
    }

    resp = client.post(f"/sessions/{session_id}/confirm", json=confirm_payload)
    assert resp.status_code == 200
    
    # Load generated spec and verify changes
    sess = db.get_session(session_id)
    spec_path = Path(sess["artifact_paths"]["workflow_spec"])
    assert spec_path.exists()
    
    spec_content = json.loads(spec_path.read_text(encoding="utf-8"))
    params = spec_content["parameters"]
    assert len(params) == 2
    
    p1 = next(p for p in params if p["name"] == "user_id_custom")
    assert p1["is_sensitive"] is True
    assert p1["is_optional"] is True
    assert p1["example_value"] == "custom_user"
    
    p2 = next(p for p in params if p["name"] == "added_manually")
    assert p2["is_sensitive"] is False
    assert p2["is_optional"] is False


def test_confirm_endpoint_invalid_names(client: TestClient, tmp_path: Path) -> None:
    """Verifies that invalid parameter names are rejected by schema validation."""
    session_id = "session_confirm_invalid_123"
    action_log_file = tmp_path / f"{session_id}.json"
    action_log_content = {
        "schema_version": "1.0",
        "metadata": {
            "session_id": session_id,
            "recorded_at": "2026-07-17T12:00:00Z",
            "site": "example.com",
            "browserbot_version": "0.1.0",
            "step_count": 1,
        },
        "steps": [
            {
                "step_index": 0,
                "action": "goto",
                "timestamp_offset": 0.0,
                "url": "https://example.com",
                "wait_until": "networkidle",
            }
        ]
    }
    action_log_file.write_text(json.dumps(action_log_content), encoding="utf-8")

    db = SessionStateStore()
    db.create_session(session_id, "extracted", {"action_log": str(action_log_file)})

    # Invalid parameter name with uppercase / spaces / starting with number
    confirm_payload = {
        "parameters": [
            {
                "name": "Invalid-Name",
                "example_value": "val",
                "log_step_index": 0,
                "description": "Invalid parameter name",
                "is_sensitive": False,
                "is_optional": False
            }
        ]
    }

    with pytest.raises(ValueError) as exc_info:
        client.post(f"/sessions/{session_id}/confirm", json=confirm_payload)
    assert "Workflow Spec validation failed" in str(exc_info.value)


def test_logs_stream_endpoint(client: TestClient, tmp_path: Path) -> None:
    """Verifies that the session logs endpoint streams log files in SSE format."""
    session_id = "session_logs_stream_123"
    
    # Write some mock logs to the telemetry log file
    action_log_file = tmp_path / f"{session_id}.json"
    action_log_content = {
        "schema_version": "1.0",
        "metadata": {
            "session_id": session_id,
            "recorded_at": "2026-07-17T12:00:00Z",
            "site": "example.com",
            "browserbot_version": "0.1.0",
            "step_count": 1,
        },
        "steps": []
    }
    action_log_file.write_text(json.dumps(action_log_content), encoding="utf-8")
    
    # Pre-populate telemetry log
    log_file = tmp_path / f"{session_id}_telemetry.log"
    log_file.write_text("[22:30:15] [INFO] Starting workflow compilation\n[22:30:16] [WARNING] Small warning\n", encoding="utf-8")

    db = SessionStateStore()
    db.create_session(session_id, "recorded", {"action_log": str(action_log_file)})

    # Call logs endpoint using TestClient.stream (to read SSE chunked data)
    with client.stream("GET", f"/sessions/{session_id}/logs") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        # Read the first few lines of the stream
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 2:
                break
                
        assert len(lines) == 2
        assert "Starting workflow compilation" in lines[0]
        assert "Small warning" in lines[1]


