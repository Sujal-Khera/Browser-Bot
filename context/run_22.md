# run_22 — Phase v2.1: Orchestration Server Foundation

This document details the design, implementation, and verification of the local FastAPI orchestration server skeleton, SQLite session state caching layer, and REST endpoints wrapper.

---

## Work Completed

1. **FastAPI Application Skeleton**:
   - Implemented `browserbot/server/app.py` containing the core `app = FastAPI(...)` app declaration, routers registration, and `/health` check.
   - Bind strictly to `127.0.0.1` loopback on port `8765` (configurable via `BROWSERBOT_SERVER_PORT`).
   - Created `browserbot/server/__main__.py` to run the server via `python -m browserbot.server`.
   - Setup `browserbot/server/config.py` for environment-driven setup.

2. **Session State Store (SQLite)**:
   - Configured `browserbot/server/db.py` setting up an SQLite cache database (`~/.browserbot/state.db`) with WAL journal mode enabled.
   - Designed schema: `sessions(id, stage, created_at, updated_at, artifact_paths_json)` to track session lifecycle.
   - Created CRUD queries for starting, updating, retrieving, and listing sessions.

3. **REST Route Mappings**:
   - Setup `browserbot/server/routes/sessions.py` mapping:
     - `POST /sessions/record`: Starts a background browser recording session.
     - `POST /sessions/{id}/extract`: Runs PatternExtractor over recorded action log.
     - `POST /sessions/{id}/confirm`: Receives parameters confirmation and generates spec.
     - `POST /sessions/{id}/generate`: Runs PipelineCoordinator to compile code.
     - `POST /sessions/{id}/package`: Invokes Packager to output installable directory.
   - Setup `browserbot/server/routes/packages.py` mapping:
     - `POST /packages/{name}/register`: Adds the compiled package to Claude Desktop.

---

## Files Modified / Added

- **New files**:
  - `browserbot/server/__init__.py`
  - `browserbot/server/__main__.py`
  - `browserbot/server/app.py`
  - `browserbot/server/config.py`
  - `browserbot/server/db.py`
  - `browserbot/server/schemas.py`
  - `browserbot/server/routes/__init__.py`
  - `browserbot/server/routes/sessions.py`
  - `browserbot/server/routes/packages.py`
  - `tests/test_server_db.py`
  - `tests/test_server_app.py`
- **Modified files**:
  - `pyproject.toml` (Added `fastapi` and `uvicorn`)
  - `requirements.txt` (Added `fastapi` and `uvicorn`)
  - `context/ORIENTATION.md` (Added Section 22)

---

## Design Decisions

- **Local Loopback Security**: The server config explicitly binds strictly to `127.0.0.1` and throws errors if any attempt is made to bind to `0.0.0.0`, protecting against unauthorized network access to user browser profiles.
- **Source of Truth Invariant**: The local SQLite database tracks session stage details, but the JSON artifacts on disk (e.g. `workflow_spec.json`, `action_log.json`) remain the canonical source of truth for the pipeline, preserving the design integrity established in v1.
- **Robust Background Threading**: In order to preventblocking the asynchronous FastAPI process event loop, interactive elements like Playwright codegen run in separate processes via `BackgroundTasks` threads.

---

## Testing Performed

- Implemented `tests/test_server_db.py` to test state storage database operations.
- Implemented `tests/test_server_app.py` leveraging FastAPI `TestClient` and temporary folder paths to test all routing schemas, requests, response mappings, and database integration checks.
- Ran entire test suite (123 tests total) verifying zero regressions on existing pipeline logic.

---

## Known Limitations

- **Headed Codegen Loop**: `POST /sessions/record` requires a headed window environment to launch Playwright. In headless CI/CD environments, this endpoint must be mocked or disabled.
- **Session State Cache Sync**: If on-disk files are deleted manually without the database being updated, database listings may point to stale paths. However, individual route checks validate file existence at stage invocation.

---

## Verification Results

### Unit Tests Check
```powershell
uv run pytest tests/test_server_db.py tests/test_server_app.py -v
```
**Output**: `8 passed`

### Smoke Verification
```powershell
curl http://127.0.0.1:8765/health
```
**Response**: `{"status":"ok"}`
