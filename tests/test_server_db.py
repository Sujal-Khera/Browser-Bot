"""
tests/test_server_db.py — Unit tests for the SQLite session state store.
"""

from __future__ import annotations

from pathlib import Path
from browserbot.server.db import SessionStateStore


def test_session_state_store_lifecycle(tmp_path: Path) -> None:
    db_file = tmp_path / "state.db"
    store = SessionStateStore(db_path=db_file)

    # 1. Verify DB file is created
    assert db_file.exists()

    # 2. Test create_session
    session_id = "session_test_123"
    stage = "recording"
    artifact_paths = {"raw_script": "path/to/raw.py"}
    
    res = store.create_session(session_id, stage, artifact_paths)
    assert res["session_id"] == session_id
    assert res["stage"] == stage
    assert res["artifact_paths"] == artifact_paths

    # 3. Test get_session
    retrieved = store.get_session(session_id)
    assert retrieved is not None
    assert retrieved["session_id"] == session_id
    assert retrieved["stage"] == stage
    assert retrieved["artifact_paths"] == artifact_paths

    # 4. Test update_session stage only
    updated = store.update_session(session_id, "recorded")
    assert updated["stage"] == "recorded"
    assert updated["artifact_paths"] == artifact_paths

    # 5. Test update_session stage and paths
    new_paths = {"raw_script": "path/to/raw.py", "action_log": "path/to/log.json"}
    updated_paths = store.update_session(session_id, "extracted", new_paths)
    assert updated_paths["stage"] == "extracted"
    assert updated_paths["artifact_paths"] == new_paths

    # 6. Test list_sessions
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == session_id

    # 7. Test non-existent session
    assert store.get_session("does_not_exist") is None
