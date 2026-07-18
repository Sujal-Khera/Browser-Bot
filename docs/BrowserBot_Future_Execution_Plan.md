# BrowserBot Future Execution Plan

**Status:** Official post-v1.0 roadmap
**Predecessor:** BrowserBot v1.0 (released, audited, 115/115 tests passing — see `run_20.md`, `run_21.md`)
**Scope of this document:** Execution planning only. All architectural recommendations are treated as final and approved. This document sequences, scopes, tests, and de-risks the work — it does not re-litigate design decisions.

---

## How This Document Is Organized

- **Release I — BrowserBot v2**: Product polish. Turns the working pipeline into a one-click, self-serve product.
- **Release II — BrowserBot v3**: Platform intelligence. Multi-site, conditional workflows, advanced page interactions, enterprise readiness.
- **Release III — BrowserBot Future Research**: Everything realistically beyond v3, scoped as research spikes, not committed engineering.
- **Final Section**: Cross-release dependency graph, critical path, staffing/delegation guidance, timeline, and final recommendation.

Every phase preserves the v1 architectural principles established in `5. High Level System Design.md`: single-responsibility components, explicit versioned JSON contracts between stages, deterministic template-first generation, AST/schema validation gates, and local-first execution. **No phase in this plan replaces the Recorder → Scrubber → Pattern Extractor → IR → Code Generator → Validator → Packager → Registry pipeline.** All new capability is added by extending existing contracts (new optional fields, new IR node types, new DSL verbs) or adding new components that sit beside the pipeline (orchestration server, UI), never by forking or rewriting it.

---

# RELEASE I — BrowserBot v2

## Release Goals

- Reduce time-to-first-working-tool for a new user from "read the operator handbook" to "click through a UI."
- Replace PowerShell/CLI-driven operation with a local orchestration server + web UI, without removing the CLI (CLI remains the automation-friendly interface; UI is a client of the same orchestrator API).
- Improve the quality and reliability of runtime responses, recordings, and packaging so the product feels finished, not like a research prototype.

## Release Non-Goals

- No multi-site abstraction work (that's v3).
- No conditional/branching workflows (that's v3).
- No cloud or distributed execution (that's Future Research).
- No breaking changes to the `workflow_spec_schema.json`, `action_log_schema.json`, or `mcp_tool_schema.json` contracts — v2 only *adds* optional fields.

## Major Features

1. Local Orchestration Server (FastAPI) wrapping `OrchestrationPipeline`.
2. Web UI: Record → Confirm Parameters → Generate & Validate → Install, as a 4-stage wizard.
3. Live progress streaming (stage transitions, logs, screenshots) over WebSocket/SSE.
4. Improved runtime response quality (richer prose formatting, multi-output summarization).
5. Recorder UX improvements (hint capture, inline element picker feedback, auto-naming).
6. Packaging/DX improvements (dependency pinning validation, one-command "doctor" script, package versioning/upgrade flow).

## Architecture Changes

- New top-level component: `browserbot/server/` (FastAPI app, WebSocket log/screenshot streaming, REST endpoints wrapping existing orchestrator/registry/packager calls).
- New top-level component: `browserbot/ui/` (a local single-page app, framework TBD by implementer — React recommended for consistency with `frontend-design` conventions already used elsewhere in the org).
- `OrchestrationPipeline` gains a callback/observer interface so the server can subscribe to stage events without polling `pipeline_diagnostics.json`.
- No change to `browserbot/agents/*`, `browserbot/models/*`, or `browserbot/runtime/registry.py` internals — only additive.

## Breaking Changes

None. v2 is purely additive at the schema and CLI level. The CLI (`python -m browserbot.recorder`, `python -m browserbot.agents.*`, `python -m browserbot.runtime`) continues to work unmodified throughout v2.

## Migration Notes

Existing `packages/` and `workflows/sessions/` directories from v1 installs are directly usable by the v2 server and UI with no migration script required, because the server is a thin wrapper over the same orchestrator and registry code paths.

## Success Metrics

- A first-time user can go from "clone repo" to "tool registered in Claude Desktop" using only the UI, in under 10 minutes, with zero manual JSON editing.
- Generation Time NFR (≤3 minutes, per `2. NonFunctionalRequirements_&_SuccessMetrics.md`) is preserved — the orchestration server adds ≤2 seconds of overhead versus direct CLI invocation.
- Zero regressions in the 115-test v1 suite.
- New UI/server test suite reaches ≥90% coverage of new server route logic.

## Release Checklist

- [ ] All v2 phases below marked Definition-of-Done complete.
- [ ] Full regression suite green (v1 tests + new v2 tests).
- [ ] `scripts/pii_audit.py` passes against a UI-generated package.
- [ ] `scripts/run_benchmark.py` NFR targets still met for a UI-generated package.
- [ ] Manual end-to-end demo run through the UI, recorded as a checkpoint artifact.
- [ ] Documentation updated: `USER_WORKFLOW_GUIDE.md` gets a new "Using the UI" section (does not replace the CLI section).

---

## Phase v2.1 — Orchestration Server Foundation

### Why This Phase Comes First
Every other v2 feature (UI, progress streaming, one-click install) depends on having a stable local HTTP/WebSocket API in front of the pipeline. Building the UI before the server exists would force UI code to shell out to CLI commands directly, which is exactly the tight-coupling anti-pattern the v1 architecture avoided between pipeline stages. Nothing in Phase v2.2 (UI) or v2.3 (progress streaming) can start until the server's REST contract is frozen.

### What Must Never Be Implemented Before This Phase
- The Web UI (v2.2) — it has nothing to call.
- Live progress streaming (v2.3) — there is no server process to hold WebSocket connections.

### Step v2.1.1 — FastAPI Application Skeleton

- **Objective:** Stand up `browserbot/server/app.py` as a FastAPI application that can be started with `python -m browserbot.server`.
- **Problem being solved:** There is currently no long-running process; every pipeline invocation is a fresh CLI process. A UI needs a persistent local server to talk to.
- **Why this step exists:** It is the load-bearing wall for every subsequent v2 feature.
- **Dependencies:** None (first step of v2).
- **Files likely to change:** none existing.
- **New modules:** `browserbot/server/__init__.py`, `browserbot/server/app.py`, `browserbot/server/__main__.py`, `browserbot/server/config.py`.
- **Existing modules affected:** None directly; the server *imports* `browserbot.orchestrator`, `browserbot.runtime.registry`, `browserbot.agents.packager` but does not modify them.
- **Architecture impact:** Adds a new "Interface Layer" beside the CLI in `5. High Level System Design.md`'s component diagram. The Pipeline Orchestrator becomes a shared dependency of both the CLI and the server, not owned by either.
- **Implementation strategy:** Use FastAPI + uvicorn, bind to `127.0.0.1` only (never `0.0.0.0`) to preserve the local-first NFR. Add a `/health` endpoint first as the smoke test.
- **Testing strategy:** `tests/test_server_app.py` — unit test with FastAPI `TestClient`, no real browser/LLM calls.
- **Verification checklist:** `curl http://127.0.0.1:8765/health` returns `200 {"status":"ok"}`; server refuses to bind to any interface other than loopback; server starts in <2s.
- **Definition of Done:** `python -m browserbot.server` runs, `/health` passes, unit tests green.
- **Risks:** Port conflicts with other local dev tools. **Mitigation:** configurable port via `BROWSERBOT_SERVER_PORT` env var, default `8765`.
- **Rollback strategy:** Server is additive and optional; deleting `browserbot/server/` fully reverts with zero impact on the CLI pipeline.
- **Estimated complexity:** Low.
- **Estimated effort:** 0.5–1 day.

### Step v2.1.2 — REST Endpoints for Each Pipeline Stage

- **Objective:** Expose `POST /sessions/record`, `POST /sessions/{id}/extract`, `POST /sessions/{id}/confirm`, `POST /sessions/{id}/generate`, `POST /sessions/{id}/package`, `POST /packages/{name}/register` as REST endpoints wrapping the existing agent entry points.
- **Problem being solved:** The UI wizard needs discrete, resumable steps rather than one monolithic "run everything" call, so a user can review/confirm parameters between extraction and generation exactly as the CLI confirmer already allows.
- **Why this step exists:** Mirrors the existing `OrchestrationPipeline` stage boundaries 1:1 — no new business logic, purely an HTTP facade.
- **Dependencies:** v2.1.1.
- **Files likely to change:** None in `browserbot/agents/*` (reused as-is).
- **New modules:** `browserbot/server/routes/sessions.py`, `browserbot/server/routes/packages.py`, `browserbot/server/schemas.py` (Pydantic request/response models — distinct from and NOT a replacement for the domain models in `browserbot/models/`).
- **Existing modules affected:** `browserbot/orchestrator/pipeline.py` may need a small refactor to expose stage-level entry points if it currently only exposes a single `run()` — this is an extension (new method signatures), not a rewrite.
- **Architecture impact:** Formalizes stage boundaries as an external contract for the first time; internal stage contracts (`workflow_spec.json`, `mcp_tool.json`, etc.) become directly addressable via HTTP.
- **Implementation strategy:** Each endpoint reads/writes the exact same on-disk artifacts (`workflows/sessions/*.json`, `generated_tools/*/workflow_spec.json`, etc.) that the CLI already produces, so CLI and UI sessions are always interchangeable and inspectable.
- **Testing strategy:** Unit tests per route using pre-recorded fixture sessions (reuse `tests/fixtures/session_multi_params.json` etc. from v1) with mocked LLM calls (`dry_run=True` mode already exists in `OrchestrationPipeline`).
- **Verification checklist:** Each endpoint returns the same artifact content the CLI produces for an identical fixture input (byte-for-byte JSON comparison, excluding timestamps).
- **Definition of Done:** All 6 endpoints implemented, tested, and manually verified to produce identical output to the CLI equivalents.
- **Risks:** Endpoint/CLI drift over time if someone edits one path and not the other. **Mitigation:** both call into the same underlying `browserbot.agents.*` functions — never duplicate logic in route handlers.
- **Rollback strategy:** Revert `browserbot/server/routes/`; no data format is changed so no artifact migration is needed.
- **Estimated complexity:** Medium.
- **Estimated effort:** 3–4 days.

### Step v2.1.3 — Session State Store

- **Objective:** Track in-flight wizard sessions (which stage they're on, which artifacts exist) in a lightweight local SQLite table, consistent with the `Storage` row in `4. Tech-Stack.md` ("JSON stores workflow artifacts, SQLite manages lightweight metadata").
- **Problem being solved:** The UI needs to know "where was this session left off" across page reloads/browser restarts.
- **Why this step exists:** Without persisted stage state, refreshing the browser mid-wizard would lose progress, which is unacceptable UX.
- **Dependencies:** v2.1.2.
- **New modules:** `browserbot/server/db.py`, `browserbot/server/models_db.py` (SQLite schema: `sessions(id, stage, created_at, updated_at, artifact_paths_json)`).
- **Existing modules affected:** None.
- **Architecture impact:** First introduction of a mutable local database in the pipeline layer; must remain purely a *state cache* over the on-disk JSON artifacts, never the source of truth (source of truth remains the JSON files, matching v1's "Explicit Contracts" principle).
- **Implementation strategy:** Use Python's built-in `sqlite3` (no new dependency) with a simple migrations file executed at server startup.
- **Testing strategy:** `tests/test_server_db.py` covering create/read/update/idempotent-migration.
- **Verification checklist:** Killing and restarting the server mid-wizard resumes at the correct stage.
- **Definition of Done:** Session state survives server restart; DB file lives at `~/.browserbot/state.db` (git-ignored, matches `workflows/sessions/` gitignore precedent).
- **Risks:** SQLite file corruption on abrupt shutdown. **Mitigation:** WAL mode enabled; state DB is a cache, safely rebuildable by rescanning `workflows/sessions/` and `generated_tools/` directories if corrupted.
- **Rollback strategy:** Delete `~/.browserbot/state.db`; server rebuilds state from disk scan on next start.
- **Estimated complexity:** Low–Medium.
- **Estimated effort:** 1–2 days.

---

## Phase v2.2 — Web UI Wizard

### Why This Phase Depends on v2.1
The UI is purely a client of the REST/WebSocket contract established in v2.1. Building UI screens before the contract is frozen risks churn and rework.

### What Future Phases Depend On This
v2.4 (Live Progress Visualization) attaches directly to the wizard's "Generate & Validate" screen. v3's site-profile picker (v3.1) will be a new step inserted into this same wizard shell.

### Step v2.2.1 — Wizard Shell & Routing

- **Objective:** Build the 4-stage wizard shell (Record → Confirm Parameters → Generate & Validate → Install) as a local single-page app served by the FastAPI server (e.g., `GET /` serves the built static bundle).
- **Problem being solved:** Gives non-CLI users a guided, linear path through the pipeline that mirrors `USER_WORKFLOW_GUIDE.md` section 3 exactly.
- **Why this step exists:** This is the primary deliverable of v2 from a product perspective.
- **Dependencies:** v2.1.2, v2.1.3.
- **New modules:** `browserbot/ui/` (React app: `src/pages/Record.tsx`, `ConfirmParameters.tsx`, `GenerateValidate.tsx`, `Install.tsx`, `src/api/client.ts`).
- **Existing modules affected:** None (frontend is fully decoupled, talks only via the REST contract).
- **Architecture impact:** None on the pipeline; purely additive presentation layer.
- **Implementation strategy:** Wizard state machine mirrors the `sessions` DB stage field 1:1, so the "current stage" the UI shows is always sourced from the server, never client-only state — avoids UI/server state desync.
- **Testing strategy:** Component tests (Vitest/React Testing Library) for each screen; Playwright-based UI smoke test (ironically using the same automation library BrowserBot itself wraps) driving the wizard against a running dev server with `dry_run=True`.
- **Verification checklist:** A user can go Record → Confirm → Generate → Install without touching a terminal, for the NoBuyCart demo workflow.
- **Definition of Done:** Full wizard flow works end-to-end against the dry-run pipeline; visually reviewed against `frontend-design` conventions.
- **Risks:** Frontend framework churn/build tooling overhead for a "local-first" tool. **Mitigation:** ship a pre-built static bundle in the repo/release artifact so end users never need Node.js installed — Node is only a *build-time* dependency for BrowserBot maintainers.
- **Rollback strategy:** UI is fully optional; CLI remains fully functional if UI is removed.
- **Estimated complexity:** High.
- **Estimated effort:** 2–3 weeks.

### Step v2.2.2 — Parameter Confirmation Screen (Interactive Equivalent of `confirmer.py`)

- **Objective:** Reproduce every capability of the CLI confirmer (`[Enter]`=accept, `r`=rename, `n`=reject, `o`=mark optional, manual-add) as UI controls.
- **Problem being solved:** The CLI confirmer is currently the only way to correct LLM-guessed parameter names; UI users need equivalent control, not a reduced subset.
- **Why this step exists:** Parameter confirmation is identified in `USER_WORKFLOW_GUIDE.md` section 5 as a first-class human decision point — the UI cannot skip or automate it away.
- **Dependencies:** v2.2.1, v2.1.2 (`/sessions/{id}/confirm` endpoint).
- **Files likely to change:** None in `browserbot/agents/pattern_extractor/confirmer.py` (UI calls the same `ConfirmedOutput`-producing logic via the REST layer, refactored if necessary to accept a structured confirmation payload instead of only interactive stdin).
- **New modules:** `browserbot/ui/src/pages/ConfirmParameters.tsx`, `browserbot/agents/pattern_extractor/confirmer_api.py` (a small adapter exposing the same accept/rename/reject/optional operations programmatically, sitting beside the existing CLI-driven `confirmer.py`, not replacing it).
- **Architecture impact:** None — confirms the "confirmed_schema.json"/`ConfirmedOutput` contract is UI-addressable without altering its shape.
- **Implementation strategy:** Table UI listing extracted parameters with inline rename/reject/optional toggles and an "Add parameter manually" row, submitting one `ConfirmedOutput` payload matching the existing Pydantic model exactly.
- **Testing strategy:** Snapshot tests for each interaction; integration test asserting UI-submitted `ConfirmedOutput` validates against the same `WorkflowSpecValidator` used by the CLI path.
- **Verification checklist:** Renaming `fake_order_code` → `order_id` in the UI produces an identical `workflow_spec.json` to doing the same rename via CLI.
- **Definition of Done:** UI-driven and CLI-driven confirmation produce schema-identical IR output for the same fixture.
- **Risks:** Divergent validation logic between CLI and UI paths. **Mitigation:** both paths call the single shared `WorkflowSpecValidator`; no duplicate validation code.
- **Rollback strategy:** Revert new screen; CLI confirmer unaffected.
- **Estimated complexity:** Medium.
- **Estimated effort:** 3–5 days.

---

## Phase v2.3 — Live Progress & Diagnostics Streaming

### Dependency Rationale
Depends on v2.1 (server must exist) and benefits from, but does not strictly require, v2.2 (could theoretically be consumed by CLI too via `--watch`). Must exist before v2.4 polish work, since screenshot/log streaming is what "Generate & Validate" screen renders live.

### Step v2.3.1 — WebSocket Log & Stage-Event Channel

- **Objective:** Stream `pipeline_diagnostics.json`-equivalent stage transition events live over a WebSocket (`/ws/sessions/{id}`) instead of only writing them to disk after the fact.
- **Problem being solved:** Today diagnostics are only visible after the pipeline finishes (or fails) and the file is written; users watching the UI need real-time feedback exactly like the terminal `[INFO] browserbot.orchestrator.pipeline — ...` lines already provide for CLI users.
- **Why this step exists:** Matches the Phase 9A (`run_18.md`) pipeline timing instrumentation and Phase 7B (`run_15.md`) diagnostics work already completed — v2 extends it to a live transport rather than post-hoc file reads.
- **Dependencies:** v2.1.1, v2.1.3, and the existing `OrchestrationPipeline` timing instrumentation from `run_18.md`.
- **New modules:** `browserbot/server/ws_manager.py`, `browserbot/orchestrator/events.py` (an observer/callback interface added to `OrchestrationPipeline.run()`).
- **Existing modules affected:** `browserbot/orchestrator/pipeline.py` — add optional `on_stage_event` callback parameter; **strictly additive**, default `None` preserves current CLI behavior unchanged.
- **Architecture impact:** Introduces an observer pattern into the orchestrator for the first time; must not introduce any behavior difference in headless/CLI mode when no observer is attached.
- **Implementation strategy:** Each of the orchestrator's 7 stages emits a `StageEvent(stage, status, message, timestamp)`; the WebSocket manager fans this out to any connected UI clients for that session id.
- **Testing strategy:** `tests/test_orchestrator_events.py` verifying event emission order/content matches `pipeline_diagnostics.json` stage list exactly; WebSocket integration test using `TestClient.websocket_connect`.
- **Verification checklist:** Running a dry-run pipeline via the UI shows all 7 stage transitions live, in order, matching the diagnostics file written at completion.
- **Definition of Done:** Live event stream content is provably identical (same stage names/order) to the static `pipeline_diagnostics.json` for the same run.
- **Risks:** Event callback exceptions could crash the pipeline. **Mitigation:** wrap callback invocation in try/except that logs but never propagates — pipeline execution must never depend on UI connectivity.
- **Rollback strategy:** Remove `on_stage_event` parameter usage; orchestrator behavior is unchanged with it absent.
- **Estimated complexity:** Medium.
- **Estimated effort:** 3–4 days.

### Step v2.3.2 — Screenshot Streaming on Validator Failure

- **Objective:** Push the failure screenshots already captured by `server.py.j2`'s diagnostic handler (established in `run_10.md`) to the UI in real time instead of requiring the user to browse `screenshots/`.
- **Problem being solved:** Debugging a failed dry-run currently requires manually opening a PNG file from disk.
- **Why this step exists:** Directly improves the "Explicit UI error states for every failure mode" goal called out as the Phase 7 recommendation in `run_13.md`.
- **Dependencies:** v2.3.1.
- **Files likely to change:** `browserbot/agents/validator/harness.py` (emit a stage event with the screenshot path when captured).
- **New modules:** None; extends `ws_manager.py` to support binary/base64 image frames.
- **Architecture impact:** None structural; the validator's screenshot capture behavior (Phase 5.1/5.2) is unchanged — only additionally reported.
- **Implementation strategy:** Base64-encode the PNG and attach it to the relevant `StageEvent.metadata`; UI renders it inline in the "Generate & Validate" screen.
- **Testing strategy:** Integration test with a deliberately broken selector fixture (mirrors `run_16.md`'s resilience test setup) verifying a screenshot event is emitted and matches the file written to `screenshots/`.
- **Verification checklist:** Deliberately breaking a selector in a fixture spec and running via UI displays the failure screenshot inline within 2 seconds of the dry-run failing.
- **Definition of Done:** Screenshot events fire reliably on failure and are visually confirmed in the wizard.
- **Risks:** Large screenshots could bloat WebSocket payloads. **Mitigation:** downscale/compress before transmission; full-resolution file remains on disk for detailed inspection.
- **Rollback strategy:** Remove the screenshot event emission line; file-based diagnostics remain fully functional.
- **Estimated complexity:** Low–Medium.
- **Estimated effort:** 1–2 days.

---

## Phase v2.4 — Runtime Response Quality

### Dependency Rationale
Independent of the server/UI work (v2.1–v2.3); can be executed in parallel by a different engineer/workstream. Builds directly on `browserbot/runtime/result_formatter.py` from `run_13.md`.

### Step v2.4.1 — Multi-Output Prose Summarization

- **Objective:** Improve `format_success()` to produce more natural, context-aware prose for tools with multiple outputs (today it emits a flat bullet list per `run_13.md`'s contract table).
- **Problem being solved:** Bullet-list output ("• Order Status: Delivered") is functional but reads mechanically; richer natural phrasing improves the end-user experience inside Claude Desktop.
- **Why this step exists:** Directly extends the Result Formatting Contract frozen in `run_13.md` without violating its "never returns raw JSON" invariant or its error-sentinel contract.
- **Dependencies:** None beyond v1 (`browserbot/runtime/result_formatter.py`).
- **Files likely to change:** `browserbot/runtime/result_formatter.py` (`format_success` gains an optional `style` parameter, default preserves current bullet-list behavior for backward compatibility with already-generated `server.py` files).
- **Existing modules affected:** `browserbot/templates/mcp_server_template/server.py.j2` (opts in to `style="prose"` for newly generated tools only — previously packaged tools are unaffected until regenerated).
- **Architecture impact:** None; stays within the existing Runtime layer responsibility boundary.
- **Implementation strategy:** Deterministic templated prose assembly (e.g., "Order Status: Delivered, Estimated Delivery: July 20" → "Your order is currently **Delivered**, with an estimated delivery date of July 20.") — remains rule-based/templated, **not** LLM-generated, to preserve the "no runtime LLM calls" NFR and the R-21/R-01 risk mitigations already in place.
- **Testing strategy:** Extend `tests/test_result_formatting.py` (18 existing tests) with new cases for 1-output, multi-output, and empty-output scenarios under the new style.
- **Verification checklist:** New style never raises on `None`/empty input (per existing belt-and-suspenders invariant); sentinel constant unchanged.
- **Definition of Done:** New prose style available, opt-in, fully tested, zero change to default behavior for existing packages.
- **Risks:** Over-engineering prose templates into pseudo-NLG that becomes hard to maintain. **Mitigation:** cap complexity — simple slot-filling templates only, no conditional grammar engine.
- **Rollback strategy:** Revert `style` parameter; default path untouched throughout, so rollback has zero blast radius.
- **Estimated complexity:** Low.
- **Estimated effort:** 1–2 days.

### Step v2.4.2 — Error Message Enrichment

- **Objective:** Extend `format_error()` to classify common failure categories (selector-not-found, timeout, network error) and give the user a more specific, actionable sentence, while still starting with the frozen `"I wasn't able to complete the workflow"` sentinel.
- **Problem being solved:** Current error prose is a generic strip-and-clean of the exception text; users can't tell "the site changed" apart from "the network is down."
- **Why this step exists:** Improves debuggability without violating the sentinel contract that `DryRunHarness` depends on (`run_13.md`, Known Limitation: "Error sentinel is a plain string constant").
- **Dependencies:** v2.4.1 is not required but recommended to land first for consistency review.
- **Files likely to change:** `browserbot/runtime/result_formatter.py`.
- **Existing modules affected:** None beyond result_formatter; `harness.py`'s sentinel-prefix check is unaffected since the prefix is preserved exactly.
- **Architecture impact:** None.
- **Implementation strategy:** Pattern-match on known Playwright exception types (`TimeoutError`, `Error: strict mode violation`, etc.) before falling back to the existing generic stripping logic.
- **Testing strategy:** Table-driven tests in `tests/test_result_formatting.py` — one case per known exception category plus the existing generic fallback case.
- **Verification checklist:** Sentinel prefix byte-identical across all new branches (re-verify `harness.py` detection still matches).
- **Definition of Done:** At least 4 distinct, user-actionable error categories implemented and tested; fallback path unchanged for unknown exceptions.
- **Risks:** Misclassifying an error category could produce a misleading message. **Mitigation:** conservative pattern matching; unmatched exceptions always fall through to the existing generic (already-safe) path.
- **Rollback strategy:** Revert new classification branches; generic path remains default.
- **Estimated complexity:** Low–Medium.
- **Estimated effort:** 2 days.

---

## Phase v2.5 — Recording & Developer Experience

### Step v2.5.1 — Recorder Hint Capture & Auto-Naming

- **Objective:** Persist the `--hint` text (already accepted by `browserbot.recorder start ... --hint "..."` per `USER_WORKFLOW_GUIDE.md`) into the Action Log metadata, and use it plus the site hostname to auto-suggest a tool name instead of requiring manual naming at packaging time.
- **Problem being solved:** Today the hint is captured but its downstream use is unclear/unused after recording; tool naming is manual (`execute_nobuycart_com` is currently derived only from hostname per `run_09.md`'s Manifest Design section).
- **Why this step exists:** Reduces manual steps in the CLI *and* gives the UI wizard's "Record" screen a sensible pre-filled tool name.
- **Dependencies:** None (independent of server/UI track — can run in parallel with v2.1–v2.4).
- **Files likely to change:** `browserbot/models/action_log.py` (add optional `hint` metadata field — additive, `additionalProperties: false` schemas require the field to be explicitly added to `action_log_schema.json`, matching the AN-03 discipline noted in `run_02.md`), `browserbot/agents/code_generator/manifest.py` (use hint in `mcp_tool_name`/`description` derivation when present, falling back to hostname-only when absent).
- **New modules:** None.
- **Existing modules affected:** `docs/schemas/action_log_schema.json` (new optional field), `docs/schemas/extractor_output_schema.json` unaffected.
- **Architecture impact:** Minor — schema gains one optional field; must be backward compatible with pre-v2 session JSON files that lack it.
- **Implementation strategy:** Default `hint: null`; all downstream consumers treat absence identically to v1 behavior.
- **Testing strategy:** Regression test loading a v1-era fixture session (no `hint` field) through the full pipeline, confirming unchanged output; new test with `hint` present confirming it influences manifest description.
- **Verification checklist:** `ActionLog.from_file()` successfully loads both old and new fixture files.
- **Definition of Done:** Hint field flows from recorder through to manifest description end-to-end; old sessions still load without error.
- **Risks:** Schema evolution breaking old sessions. **Mitigation:** field is optional with explicit default; add a regression fixture using an actual pre-v2 session file to CI permanently.
- **Rollback strategy:** Remove field usage in manifest generation; schema field can remain unused harmlessly.
- **Estimated complexity:** Low.
- **Estimated effort:** 1–2 days.

### Step v2.5.2 — `doctor` Command (Environment Diagnostics)

- **Objective:** Add `python -m browserbot doctor` consolidating `verify_env.py`, Ollama reachability check, Playwright/Chromium check, and Claude Desktop config path detection into one command with a clear pass/fail report.
- **Problem being solved:** Today a new user runs several separate scripts (`verify_env.py`, `recorder --demo`) to diagnose setup issues; consolidating improves onboarding, directly serving the v2 "reduce time-to-first-tool" success metric.
- **Why this step exists:** Support/DX improvement with no architectural risk; ideal parallel workstream.
- **Dependencies:** None.
- **New modules:** `browserbot/cli/doctor.py`.
- **Existing modules affected:** `scripts/verify_env.py` is called as a library function, not duplicated.
- **Architecture impact:** None.
- **Implementation strategy:** Aggregate existing check functions; do not reimplement checks that already exist (`verify_env.py`'s 6 checks, Ollama ping, `ClaudeDesktopRegistry`'s path resolution logic from `run_13.md`).
- **Testing strategy:** `tests/test_doctor.py` mocking each subsystem check independently (Ollama down, Playwright missing, config path unwritable).
- **Verification checklist:** Running `doctor` on a known-good machine reports all green; deliberately stopping the Ollama service produces a specific, actionable red line (not a stack trace).
- **Definition of Done:** Single command surfaces all v1 environment prerequisites with clear pass/fail per check.
- **Risks:** Low — read-only diagnostics tool.
- **Rollback strategy:** Trivial; purely additive CLI command.
- **Estimated complexity:** Low.
- **Estimated effort:** 1 day.

---

## Phase v2.6 — Package Versioning & Upgrade Flow

### Step v2.6.1 — `browserbot_package.json` Version Field & Upgrade Detection

- **Objective:** Add a `package_version` (semantic, auto-incremented) field to `browserbot_package.json` (schema defined in `run_12.md`) and a CLI/UI affordance to detect "this package was generated by an older BrowserBot version and should be regenerated."
- **Problem being solved:** `USER_WORKFLOW_GUIDE.md` FAQ already documents the manual re-record/re-package/re-register update flow; this step makes staleness *detectable* rather than only manually recoverable.
- **Why this step exists:** As BrowserBot's own template/schema versions evolve (v2, v3), operators need a way to know which installed packages are out of date relative to the currently installed BrowserBot version.
- **Dependencies:** None structurally, but logically pairs well with v2.5.2 (`doctor` can report stale packages).
- **Files likely to change:** `browserbot/models/package.py`, `docs/schemas/package_schema.json` (additive field), `browserbot/agents/packager/packager.py` (stamps current `browserbot.__version__` at package time).
- **Architecture impact:** None structural; matches the existing "Artifact Metadata" standard fields (`schema_version`, `generator_version`) already specified in `5. High Level System Design.md`.
- **Implementation strategy:** Compare `package.generator_version` against the running BrowserBot's version at `register`/`list` time; print a warning (not a failure) if mismatched.
- **Testing strategy:** `tests/test_packager.py` extension — version stamping test; `tests/test_registry.py` extension — staleness warning test.
- **Verification checklist:** `python -m browserbot.runtime list` shows a `[STALE]` marker next to packages built with an older generator version.
- **Definition of Done:** Version stamping and staleness detection implemented and tested; purely advisory (never blocks registration).
- **Risks:** False positives if version string parsing is too strict. **Mitigation:** simple string inequality check, not strict semver range logic, for v2.
- **Rollback strategy:** Revert field usage; existing packages continue to function (field is additive/optional, matches v1's forward-compatible metadata pattern).
- **Estimated complexity:** Low.
- **Estimated effort:** 1–2 days.

---

# RELEASE II — BrowserBot v3

## Release Goals

- Generalize the pipeline from "one linear sequence of steps" to a system that can express **branches**, **multi-site** compiled tools, and **richer page interactions** (tables, pagination, iframes, uploads/downloads), while preserving the AST-validated, template-first security model that is BrowserBot's core differentiator.
- Introduce **persistent authenticated sessions** so recorded workflows behind a login do not need credentials re-entered on every run.
- Reach **enterprise readiness**: stronger validation, auditability, and multi-tool governance suitable for a team (not just a single operator's laptop).

## Release Non-Goals

- No cloud execution (Future Research).
- No visual/no-code workflow editor (Future Research) — v3's "conditional workflows" are still authored via recording + IR editing, not a drag-and-drop canvas.
- No removal of the local-first, $0-marginal-cost architecture — Ollama remains the default LLM backend; Groq remains the fallback.

## Major Features

1. Multi-site support: a single package can bundle multiple recorded workflows/sites under one registered MCP server (or clearly separated multi-package generation) with a shared "site profile" concept.
2. Conditional/branching IR: the `WorkflowSpec` gains a constrained branch node type (`if_present`, `if_text_matches`) validated with the same AST-style discipline used for the code DSL.
3. Advanced extraction: tables, pagination, iframes, file uploads/downloads as new DSL verbs.
4. Persistent authenticated sessions: Playwright `storage_state` capture/reuse, isolated per tool, encrypted at rest.
5. Advanced validation: property-based/fuzz testing of generated tools, multi-run reliability scoring built into the validator pipeline (not just the standalone benchmark script).
6. Enterprise readiness: audit logging, multi-operator package ownership metadata, config export/import for CI-based re-registration.

## Architecture Changes

- `WorkflowSpec` IR evolves from a flat step list to a **step list with optional branch nodes** — this is the single largest architectural change in v3 and is treated as its own phase (v3.2) with the most conservative, incremental design possible: branch nodes are opt-in and a spec with zero branch nodes is byte-identical in shape to a v1/v2 linear spec.
- New DSL verbs added to the AST allow-list in `browserbot/agents/code_generator/validator.py` (table row iteration is implemented as a **bounded, deterministically-unrolled** construct, not a general-purpose `for` loop, to preserve the R-15/AST-sandboxing risk mitigation).
- New `browserbot/runtime/session_store.py` for encrypted `storage_state` persistence.
- New `browserbot/models/site_profile.py` for multi-site package metadata.

## Breaking Changes

- **Schema version bump**: `workflow_spec_schema.json` moves to v2.0 to accommodate branch nodes. v1 specs remain valid under v2.0 (branch nodes are optional/absent), so this is additive-breaking only in the sense that new spec-consuming code must handle the new node type — no existing v1 spec becomes invalid.
- **AST validator allow-list expansion**: adding new verbs is additive and does not remove any v1/v2 approved statement.

## Migration Notes

- All v1/v2-generated packages continue to run unmodified under a v3 BrowserBot installation (the runtime template and DSL are strict supersets).
- Operators wishing to use v3 features (branching, tables, persistent auth) must re-record or manually extend affected workflows; this is explicitly a re-recording model, consistent with the existing "Can I reuse one recording for multiple tools? No" FAQ answer in `USER_WORKFLOW_GUIDE.md`.

## Success Metrics

- A conditional workflow (e.g., "if a cookie banner is present, dismiss it, then proceed") can be recorded and compiled without hand-editing the generated `server.py`.
- A table-extraction workflow (e.g., "list all orders from page 1") produces structured, itemized output via `format_success`, not a single flattened string.
- Persistent session reuse cuts login-workflow runtime latency by removing repeated login steps, measured via `run_benchmark.py`.
- Zero regressions against the full v1+v2 regression suite.

## Release Checklist

- [ ] Schema v2.0 published with a documented migration guide for spec-authoring tooling.
- [ ] AST validator allow-list expansion independently security-reviewed (see Phase v3.5 adversarial testing).
- [ ] Full regression suite (v1 + v2 + v3) green.
- [ ] `pii_audit.py` extended and passing for packages using persistent session storage (must confirm encrypted storage state is never flagged as *unencrypted* plaintext credential leakage, and conversely must confirm it never leaks unencrypted to disk).
- [ ] Enterprise readiness checklist (audit log presence, multi-operator metadata) verified against a simulated 3-operator/5-package scenario.

---

## Phase v3.1 — Multi-Site Support

### Why This Phase Comes Before Conditional Workflows (v3.2)
Multi-site support only requires new *packaging/metadata* concepts (a "site profile" wrapping existing, unmodified per-site `WorkflowSpec`s) — it does not touch the IR's step representation at all. It is the lower-risk, schema-additive change and should land first to validate the v3 release process before the higher-risk IR schema change (branching) ships.

### What Must Never Be Implemented Before This Phase
Nothing downstream in v3 strictly requires it first, but it establishes the `SiteProfile` concept that Phase v3.6 (enterprise multi-tool governance) builds directly on top of.

### Step v3.1.1 — `SiteProfile` Model & Multi-Workflow Package Layout

- **Objective:** Introduce `browserbot/models/site_profile.py` (`SiteProfile` Pydantic model: site hostname, list of `workflow_spec` references, shared auth/session config) and extend the package layout so `packages/<name>/` can optionally bundle multiple `server.py` tool entry points registered as separate MCP tools sharing one package directory and one `requirements.txt`.
- **Problem being solved:** Today, per `USER_WORKFLOW_GUIDE.md` section 8, every workflow gets a fully separate package directory even when two workflows target the same authenticated site (e.g., "check order status" and "download invoice" on the same portal) — this duplicates dependency declarations and, after v3.4, would duplicate persistent session storage unnecessarily.
- **Why this step exists:** Reduces operational overhead for the common case of "several workflows, one site, one login."
- **Dependencies:** v1/v2 packaging system (`browserbot/agents/packager/packager.py`) unchanged in its single-workflow mode; this step adds an alternate multi-workflow mode alongside it.
- **Files likely to change:** `browserbot/agents/packager/packager.py` (new `PackageMultiWorkflow` code path), `docs/schemas/package_schema.json` (new optional `workflows: []` array superseding, but not replacing, the existing single-workflow fields).
- **New modules:** `browserbot/models/site_profile.py`, `browserbot/agents/packager/multi_workflow.py`.
- **Existing modules affected:** `browserbot/runtime/registry.py` — must register N tool entries from one package directory instead of assuming a strict 1:1 package:tool mapping.
- **Architecture impact:** The previously implicit "one package = one tool" assumption throughout `run_12.md`/`run_13.md` becomes explicit and optional; single-workflow packages remain the default and are structurally unchanged (schema is additive).
- **Implementation strategy:** `SiteProfile` composes N already-validated, already-generated `WorkflowSpec`/`server.py` pairs; the packager's job is purely aggregation — it does not alter how any individual workflow is extracted, generated, or validated.
- **Testing strategy:** Extend `tests/test_packager.py` with a multi-workflow fixture (two small dry-run specs on the same mock hostname) verifying both tools register correctly and independently under one package.
- **Verification checklist:** `python -m browserbot.runtime list` shows two distinct tool names originating from one package directory; invoking either tool independently succeeds without cross-tool interference (matches the existing "Browser Profile Isolation" guarantee from `USER_WORKFLOW_GUIDE.md` section 8).
- **Definition of Done:** Multi-workflow packaging implemented, tested, documented; single-workflow packaging behavior is provably unchanged (existing v1/v2 packager tests still pass unmodified).
- **Risks:** Registry name collisions between two workflows on the same site. **Mitigation:** tool names remain globally unique via existing hostname+workflow-hint derivation from v2.5.1.
- **Rollback strategy:** Multi-workflow code path is additive; deleting `multi_workflow.py` reverts to single-workflow-only packaging with zero impact on existing packages.
- **Estimated complexity:** Medium.
- **Estimated effort:** 1 week.

### Step v3.1.2 — Cross-Workflow Site Metadata Reuse

- **Objective:** When recording a second workflow against an already-known site (matched by hostname), pre-populate recorder hints and suggest reusing the existing `SiteProfile`'s auth configuration rather than starting from a blank slate.
- **Problem being solved:** Avoids re-deriving obvious metadata (site name, base URL) for every new workflow on a site BrowserBot has already automated once.
- **Why this step exists:** Direct DX improvement building on v3.1.1; also lays groundwork for v3.4's shared persistent session reuse across workflows on the same site.
- **Dependencies:** v3.1.1.
- **Files likely to change:** `browserbot/recorder/__main__.py` (CLI: detect known hostname, print a suggestion), UI Record screen (v2.2.1) gains a "known sites" dropdown.
- **Architecture impact:** None structural.
- **Implementation strategy:** Simple hostname lookup against locally stored `SiteProfile` records (SQLite state store from v2.1.3, extended with a `site_profiles` table).
- **Testing strategy:** Unit test verifying hostname matching and correct suggestion surfaced; no behavior change if no match found.
- **Verification checklist:** Recording a second NoBuyCart-hostname workflow shows a "Reuse existing NoBuyCart site profile?" prompt.
- **Definition of Done:** Suggestion feature implemented and tested; declining the suggestion behaves identically to v1/v2 (no forced coupling).
- **Risks:** Low.
- **Rollback strategy:** Trivial; purely a UX suggestion layer.
- **Estimated complexity:** Low.
- **Estimated effort:** 2 days.

---

## Phase v3.2 — Conditional / Branching Workflows

### Dependency Rationale
This is the highest-architectural-risk phase in v3 and must be scoped, designed, and security-reviewed independently before implementation begins. It depends on nothing else in v3 but should be scheduled *after* v3.1 so the team has already exercised the v3 release process (schema versioning, migration testing) once on a lower-risk change.

### What Must Never Be Implemented Before This Phase
Advanced extraction (v3.3, tables/pagination) should ideally land after branching lands, because a natural table/pagination use case ("keep clicking Next while a Next button is present") is most cleanly expressed as a bounded loop construct that reuses the same AST-allow-list-expansion process this phase establishes. Implementing v3.3 first would risk two independent, inconsistent extensions to the DSL allow-list.

### Step v3.2.1 — Branch Node IR Schema Design (`workflow_spec_schema.json` v2.0)

- **Objective:** Define a minimal, constrained branch node type in the IR: `{"type": "conditional", "condition": {"kind": "element_present"|"text_matches", "selector": "...", "value": "..."}, "then_steps": [...], "else_steps": [...]}`, added as one new possible entry in the existing `steps` array.
- **Problem being solved:** v1/v2 IR is a strictly linear step list (per `run_07.md`'s explicit design: "It has no concept of... arbitrary Python details"); real-world workflows sometimes need a single bounded conditional (e.g., dismiss a cookie banner only if present) without opening the door to arbitrary control flow.
- **Why this step exists:** This is the architectural core of v3's "intelligent" positioning — but must be scoped as narrowly as possible to avoid reintroducing the exact code-injection risk (R-15) that the v1 AST validator was built to prevent.
- **Dependencies:** v1's `WorkflowSpec` Pydantic model (`browserbot/models/workflow_spec.py`) and `docs/schemas/workflow_spec_schema.json`.
- **Files likely to change:** `docs/schemas/workflow_spec_schema.json` (bump to `2.0`, add `oneOf` for step types), `browserbot/models/workflow_spec.py` (add `ConditionalStep` model), `browserbot/agents/pattern_extractor/generator.py` (only emits conditional nodes when explicitly flagged during confirmation — the LLM extractor never autonomously invents branches in v3.2; branch authoring is a manual IR-editing/confirmer capability, not automatic LLM inference, to bound R-01 risk).
- **New modules:** None yet (schema/model only in this step; codegen support is v3.2.2).
- **Existing modules affected:** `WorkflowSpecValidator` (schema validation must accept both v1-shape and v2-shape specs — backward compatible).
- **Architecture impact:** This is the first non-linear structure in the IR since the project's inception; it is deliberately kept to **one level of nesting, no loops, no nested conditionals** in v3.2 to keep the AST/DSL validator's job tractable.
- **Implementation strategy:** Design-review checkpoint required before implementation: circulate the schema diff, get explicit sign-off that scope is capped at single-level if/else with no loops before writing any generator/validator code.
- **Testing strategy:** Schema-only unit tests: valid v1 specs still validate under v2.0 schema; new conditional-shaped specs validate; malformed nested-conditional specs are rejected.
- **Verification checklist:** Every existing v1/v2 fixture spec (`tests/fixtures/*_expected.json`) validates unmodified against the new v2.0 schema.
- **Definition of Done:** Schema + model shipped, 100% backward compatible with existing fixtures, explicit nesting-depth-1 constraint enforced and tested.
- **Risks:** Schema over-scoping under pressure to support "just one more" control-flow feature. **Mitigation:** hard product decision, documented here: **no loops, no nested conditionals in v3.2** — revisit only in a future major version after this ships and is proven safe in production.
- **Rollback strategy:** Schema bump is versioned; a v3 installation could pin back to schema `1.x` handling if the conditional feature needed to be pulled, with zero impact on non-conditional specs.
- **Estimated complexity:** High (design risk, not implementation volume).
- **Estimated effort:** 1 week design + review, 3–4 days implementation.

### Step v3.2.2 — Conditional Code Generation & AST Validator Extension

- **Objective:** Extend the Jinja2 template and code generator to render `if <condition>: <then_steps> else: <else_steps>` for a `ConditionalStep`, and extend `DSLSecurityVisitor` (`browserbot/agents/code_generator/validator.py`) to allow exactly this one constrained `if` shape — condition must be one of the two enumerated kinds, both branches must contain only already-approved DSL statements, and nothing else.
- **Problem being solved:** v1's AST validator currently rejects **all** `if` statements outright (`run_08.md`: "Flow Control & Declarations: ... `if` blocks... [rejected]"). This step is the one deliberate, carefully bounded exception to that rule.
- **Why this step exists:** Without this, the schema from v3.2.1 has no runnable target.
- **Dependencies:** v3.2.1 (schema must be frozen first).
- **Files likely to change:** `browserbot/agents/code_generator/validator.py`, `browserbot/agents/code_generator/prompt.py` (LLM is told to emit conditionals **only** when explicitly instructed by a `ConditionalStep` in the spec — it does not decide on its own to add branching, preserving the "narrow prompt" philosophy from `run_06.md`), `browserbot/templates/mcp_server_template/server.py.j2` (template gains a conditional-rendering macro, still deterministic/Jinja2-owned, not LLM-owned, for the `if`/`else` scaffolding itself — the LLM only fills each branch's statement list, exactly as it already does for the linear case).
- **Existing modules affected:** `DSLSecurityVisitor` gains a new `visit_If` handler; every other visitor method is unchanged.
- **Architecture impact:** The Template vs. LLM split established in `run_08.md` is preserved: **the `if`/`else` Python syntax itself is template-rendered, never LLM-generated** — the LLM only ever produces the same flat, linear Playwright statement lists it already produces for non-conditional steps, now once per branch.
- **Implementation strategy:** `visit_If` verifies: (a) test expression matches one of exactly two whitelisted condition-check helper calls (e.g. `await element_present(page, selector)`), (b) both `body` and `orelse` contain only nodes that pass the existing statement-level checks, (c) no nested `If` nodes (enforced structurally, not just by convention).
- **Testing strategy:** Extend `tests/test_code_generator.py`: valid single-level conditional accepted; nested conditional rejected; non-whitelisted condition expression rejected; conditional with a disallowed statement in either branch rejected. Add to the adversarial suite from `run_19.md`'s `test_adversarial_prompt_injection_rejected` pattern — specifically test an LLM output attempting to smuggle an `eval()` call inside an `else` branch.
- **Verification checklist:** `python -m py_compile` succeeds on generated conditional code; adversarial injection tests specifically targeting the new `if` allowance all fail (are rejected) as expected.
- **Definition of Done:** Conditional generation works end-to-end for the "dismiss cookie banner if present" reference workflow; full adversarial test suite (v1's + new conditional-specific cases) passes.
- **Risks:** This is the single highest security-risk change in v3 — expanding what the AST validator accepts is inherently risk-additive. **Mitigation:** independent security review (Phase v3.5) required as a hard gate before this step is considered done, not just before release.
- **Rollback strategy:** Revert `visit_If` addition — validator reverts to unconditionally rejecting all `if` statements, exactly as in v1/v2; any already-generated conditional tools would fail to regenerate but continue running as already-compiled artifacts.
- **Estimated complexity:** Very High.
- **Estimated effort:** 2 weeks (including the mandatory security review cycle).

### Step v3.2.3 — Confirmer/UI Support for Marking a Branch Point

- **Objective:** Extend the parameter/step confirmation UX (CLI `confirmer.py` and UI `ConfirmParameters.tsx`) so an operator can mark a recorded step as conditional ("only do this if element X is present") during confirmation, rather than requiring hand-edited IR JSON.
- **Problem being solved:** Without this, v3.2.1/v3.2.2's branching capability would only be usable by manually editing `workflow_spec.json`, defeating the product's no-hand-editing goal.
- **Why this step exists:** Closes the loop from "capability exists in the IR/codegen" to "an operator can actually author it."
- **Dependencies:** v3.2.1, v3.2.2, v2.2.2 (UI confirmation screen), v2.5.1's confirmer patterns.
- **Files likely to change:** `browserbot/agents/pattern_extractor/confirmer.py` (new `[c]` choice key, mirroring the existing `[o]` optional-marking pattern from `run_07.md`), `browserbot/ui/src/pages/ConfirmParameters.tsx`.
- **Architecture impact:** None beyond what v3.2.1/v3.2.2 already introduced; this is purely an authoring UX for the already-defined schema.
- **Implementation strategy:** Marking a step conditional prompts for the condition selector and value inline, producing a `ConditionalStep` in the emitted `ConfirmedOutput`.
- **Testing strategy:** CLI interaction test (mirrors existing `test_pattern_extractor.py` confirmer CLI tests) and UI component test for the new control.
- **Verification checklist:** An operator can, without touching JSON, mark the "dismiss cookie banner" step conditional and produce a valid v2.0 spec.
- **Definition of Done:** End-to-end authoring flow (record → mark conditional in confirmer → generate → validate → package → register) works for the reference cookie-banner workflow via both CLI and UI.
- **Risks:** Low, given schema/codegen risk was already retired in v3.2.1/v3.2.2.
- **Rollback strategy:** Trivial UI/CLI-only revert.
- **Estimated complexity:** Medium.
- **Estimated effort:** 4–5 days.

---

## Phase v3.3 — Advanced Page Interaction (Tables, Pagination, Iframes, Upload/Download)

### Dependency Rationale
Depends on v3.2 for the bounded-iteration pattern precedent (pagination is naturally expressed as "repeat while element present," reusing the exact condition-check helpers introduced in v3.2.2) and for the now-established, reviewed process for extending the AST allow-list safely.

### Step v3.3.1 — Table Extraction DSL Verb

- **Objective:** Add a new, bounded DSL verb `extract_table(page, selector, max_rows=N)` that deterministically unrolls into N `inner_text()` calls at code-generation time (the unroll count is fixed by the template based on a `max_rows` value confirmed by the operator, not a runtime loop), producing a structured list output.
- **Problem being solved:** Today, `ExtractTextStep` only supports single-element extraction; there's no way to represent "read all rows of this results table" without either (a) manually recording N nearly-identical extraction steps, or (b) writing a real `for` loop, which the AST validator correctly rejects (R-15).
- **Why this step exists:** Tables are among the most common real-world extraction targets (order histories, search results, account listings) called out explicitly as a v3 goal.
- **Dependencies:** v3.2.2 (establishes the precedent and review process for allow-list expansion); does not depend on branching itself.
- **Files likely to change:** `browserbot/agents/code_generator/validator.py` (whitelist `extract_table` as an approved call, with strict argument-shape checking — literal selector string, literal integer `max_rows` bound to a sane maximum, e.g. 50, enforced at validation time to prevent unbounded generation), `browserbot/templates/mcp_server_template/server.py.j2` (adds a macro that renders the deterministic unroll — **the unrolling is template logic, not LLM-authored code, and not a runtime loop in the generated file** — the loop happens at *generation time* in Jinja2/Python, and the emitted `server.py` contains N straight-line statements).
- **New modules:** None; extends existing generator/validator/template trio.
- **Existing modules affected:** `browserbot/models/workflow_spec.py` (`IROutput` gains an optional `is_table` / `max_rows` field), `docs/schemas/workflow_spec_schema.json`.
- **Architecture impact:** Reinforces, rather than compromises, the "no runtime loops" security invariant — the appearance of iteration is achieved entirely through deterministic compile-time unrolling, keeping the generated Python fully linear and AST-checkable exactly as before.
- **Implementation strategy:** Bound `max_rows` hard at the schema level (reject values >50 at validation, matching the spirit of R-15's "restrict to allow-listed subset" mitigation) to prevent pathological generation-time blowup.
- **Testing strategy:** Unit tests for the unroll macro at `max_rows` boundary values (0, 1, 50, 51-rejected); AST validator test confirming `extract_table` with a non-literal or out-of-range argument is rejected; adversarial test attempting to pass an expression instead of a literal integer for `max_rows`.
- **Verification checklist:** Generated code for a `max_rows=5` table spec compiles, contains exactly 5 straight-line extraction statements (verifiable via `ast.parse` node count in the test), and runs successfully against a mock table fixture page.
- **Definition of Done:** Table extraction works end-to-end for a reference "list first page of orders" workflow; bound enforcement tested at both schema and AST-validator layers (defense in depth).
- **Risks:** `max_rows` bound chosen too low limits real-world usefulness; chosen too high risks large generated files. **Mitigation:** default cap of 50 is configurable per-deployment via an env var, but never unbounded.
- **Rollback strategy:** Remove `extract_table` from the allow-list; any already-generated tools using it continue running as compiled, but cannot be regenerated until reverted back.
- **Estimated complexity:** High.
- **Estimated effort:** 1.5 weeks.

### Step v3.3.2 — Pagination Support (Bounded "Next Page" Repetition)

- **Objective:** Combine the v3.2 conditional primitive with the v3.3.1 table-unroll pattern to support "extract table, then click Next if present, then extract again," bounded to a configurable `max_pages` (default 5, hard cap 20).
- **Problem being solved:** Single-page table extraction (v3.3.1) is insufficient for paginated result sets, a very common real-world case.
- **Why this step exists:** Direct extension combining two already-reviewed primitives rather than inventing a third new control-flow concept — deliberately reuses v3.2's condition-check helper and v3.3.1's deterministic unroll rather than introducing a genuine loop construct.
- **Dependencies:** v3.2.2, v3.3.1.
- **Files likely to change:** Same trio as v3.3.1, extended.
- **Architecture impact:** None beyond the already-reviewed patterns; this step is explicitly an integration of two existing capabilities, not a new security surface.
- **Implementation strategy:** Template unrolls `max_pages` repetitions of: extract-table → check-next-present → conditionally click-next, entirely at generation time.
- **Testing strategy:** Integration test against a mock multi-page fixture site (extend `tests/fixtures/` with a paginated results mock), verifying correct row aggregation across pages and correct early-stop when "Next" disappears before `max_pages` is reached.
- **Verification checklist:** Generated tool correctly stops at the actual last page even when `max_pages` is set higher than the real page count.
- **Definition of Done:** Reference "list all orders across pages" workflow works end-to-end and is benchmarked against the existing NFR latency target (may require a higher timeout ceiling for multi-page workflows — document this exception explicitly rather than silently exceeding the 20s target).
- **Risks:** Multi-page workflows may violate the v1 20-second runtime latency NFR. **Mitigation:** document a distinct, explicitly-labeled latency budget for pagination-class tools in `2. NonFunctionalRequirements_&_SuccessMetrics.md`'s v3 addendum, rather than silently redefining the existing metric.
- **Rollback strategy:** Disable pagination unrolling; single-page extraction (v3.3.1) remains fully functional independently.
- **Estimated complexity:** Medium (given v3.2/v3.3.1 already landed).
- **Estimated effort:** 1 week.

### Step v3.3.3 — Iframe-Scoped Locators

- **Objective:** Extend locator resolution (building on the resilience/fallback locator work from `run_16.md`) to support an explicit `frame_selector` field so recorded actions inside an iframe correctly scope to `page.frame_locator(...)` instead of failing against the top-level page.
- **Problem being solved:** Playwright requires explicit frame scoping for iframe content; v1/v2's recorder and generator have no concept of frame boundaries, so any recorded workflow involving an iframe (common in embedded widgets, payment forms, third-party login panels) currently fails silently or errors at validation.
- **Why this step exists:** Closes a known, common real-world gap without touching the branching/table work above — can be implemented and shipped independently and in parallel with v3.3.1/v3.3.2.
- **Dependencies:** v1's `resolve_locator` helper (`browserbot/runtime/resilience.py`, `run_16.md`) — extended, not replaced.
- **Files likely to change:** `browserbot/recorder/convert_codegen.py` (detect and record frame context from Playwright codegen output), `browserbot/models/action_log.py` (steps gain optional `frame_selector`), `browserbot/runtime/resilience.py` (`resolve_locator` gains frame-scoping support), `browserbot/agents/code_generator/validator.py` (whitelist `page.frame_locator()` chained with already-approved locator/action methods).
- **Architecture impact:** Additive field on existing step models; no change to the linear step-list shape (orthogonal to the v3.2 branching work).
- **Implementation strategy:** Recorder-side detection first (can this even be captured reliably from Playwright codegen output?) is treated as a research spike sub-step before committing to full implementation — if codegen doesn't reliably expose frame context, a manual "mark this step as inside frame X" confirmer affordance is the fallback plan.
- **Testing strategy:** Fixture-based test against a mock page embedding a same-origin iframe (Playwright test fixtures support this natively); AST validator test confirming `frame_locator` is only accepted chained with already-approved methods.
- **Verification checklist:** A workflow requiring a click inside an iframe compiles, validates, and executes successfully against the mock fixture.
- **Definition of Done:** Iframe-scoped actions work end-to-end for at least one reference fixture; recorder detection reliability documented (including known limitations if automatic detection proves unreliable).
- **Risks:** Cross-origin iframes may be blocked by browser security policy regardless of BrowserBot's implementation. **Mitigation:** explicitly scope v3.3.3 to same-origin and permissive cross-origin iframes only; document cross-origin restricted iframes as an out-of-scope known limitation, consistent with how CAPTCHA/2FA are already handled as accepted-risk exclusions (R-07).
- **Rollback strategy:** `frame_selector` field is optional; absence preserves exact v1/v2 top-level-page-only behavior.
- **Estimated complexity:** Medium–High (recorder detection is the uncertain part).
- **Estimated effort:** 1–1.5 weeks, plus up to 3 days for the recorder-detection research spike.

### Step v3.3.4 — File Upload & Download Support

- **Objective:** Add `set_input_files()` (upload) support scoped to operator-approved local file paths, and download-event capture (`page.expect_download()`) with the downloaded file's path surfaced as a tool output.
- **Problem being solved:** Workflows like "download my latest invoice" are common and currently entirely unsupported — file steps are not part of the v1/v2 recorded action vocabulary.
- **Why this step exists:** Closes another common real-world workflow gap; deliberately scoped narrowly given the security sensitivity of file-system interaction.
- **Dependencies:** None beyond v1 architecture; independent of v3.2/v3.3.1–3.3.3, can be parallelized.
- **Files likely to change:** `browserbot/models/action_log.py` (new `UploadStep`, `DownloadStep`), `browserbot/agents/code_generator/validator.py` (whitelist `set_input_files` restricted to a parameter-bound path only — **never a literal filesystem path baked into generated code**, to prevent the generator from ever hardcoding a path to an arbitrary local file; whitelist the download-wait pattern, restricted to writing only inside a sandboxed `downloads/<tool_name>/` directory, never an operator-supplied arbitrary path), `browserbot/runtime/result_formatter.py` (format a download path/filename in the success prose).
- **Architecture impact:** Introduces the pipeline's first read/write filesystem interaction beyond its own artifacts (`packages/`, `workflows/sessions/`) — this is a meaningful new security surface and must be treated with the same rigor as R-13/R-14 (credential/PII persistence risks).
- **Implementation strategy:** Upload file paths are always supplied as a runtime **tool parameter** (never hardcoded), and are validated at runtime to reside within an operator-configured allow-listed directory before being passed to Playwright — enforced in the template's runtime wrapper, not merely at generation time. Downloads are always written to a fixed, sandboxed, tool-scoped subdirectory, never an LLM- or user-supplied arbitrary path.
- **Testing strategy:** Security-focused tests: attempt to pass a path traversal string (`../../etc/passwd`) as an upload parameter and confirm rejection at runtime; confirm downloads cannot escape the sandboxed directory even under adversarial parameter input.
- **Verification checklist:** `pii_audit.py` extended to also scan the `downloads/` sandbox directory structure for accidentally-persisted secrets in downloaded filenames/content is explicitly out of scope for automated scanning (documented limitation) but the *path containment* guarantee is fully tested.
- **Definition of Done:** Upload and download reference workflows work end-to-end; path-traversal and sandbox-escape adversarial tests all pass (fail to escape, as expected).
- **Risks:** File system interaction is inherently higher-risk than pure browser-DOM interaction. **Mitigation:** strict path allow-listing/sandboxing as above; explicit security review sign-off required (shared with Phase v3.5) before this step is considered done.
- **Rollback strategy:** Remove `set_input_files`/download-wait from the allow-list; no existing v1/v2 tool is affected since this is wholly new capability.
- **Estimated complexity:** High (security-sensitive).
- **Estimated effort:** 1.5–2 weeks including security review.

---

## Phase v3.4 — Persistent Authenticated Sessions

### Dependency Rationale
Independent of v3.2/v3.3 at the schema level, but logically most valuable once multi-site/multi-workflow packages (v3.1) exist, since session reuse is most beneficial when multiple workflows share one login. Schedule after v3.1, can run in parallel with v3.2/v3.3.

### Step v3.4.1 — `storage_state` Capture During Recording

- **Objective:** After a successful recorded login sequence, capture Playwright's `context.storage_state()` (cookies + localStorage) and offer to save it as a named, reusable session artifact.
- **Problem being solved:** Every current tool invocation starts from a fully clean browser context (`USER_WORKFLOW_GUIDE.md` section 8: "Browser Profile Isolation... fresh, stateless browser contexts for every invocation") — this is correct and safe by default, but means any workflow requiring login must re-authenticate on every single run, which is slow and, for sites with bot-detection on repeated logins, potentially unreliable.
- **Why this step exists:** Directly targets the v3 goal of persistent authenticated sessions while preserving the existing per-invocation isolation as the *default* — session reuse is strictly opt-in per tool.
- **Dependencies:** None beyond v1 recorder.
- **Files likely to change:** `browserbot/recorder/__main__.py` (post-recording prompt: "Save authenticated session for reuse? [y/N]").
- **New modules:** `browserbot/runtime/session_store.py` (encrypted storage-state persistence — encryption key derived from a local machine-bound secret, never transmitted, never embedded in generated packages).
- **Existing modules affected:** None in the extraction/generation/validation pipeline — this is purely a recorder-time and runtime-loading concern.
- **Architecture impact:** New encrypted-at-rest artifact class (`~/.browserbot/sessions/<site_profile_id>.enc`), stored outside `workflows/sessions/` and outside any `packages/` directory to ensure it is never accidentally included in a distributed/shared package bundle.
- **Implementation strategy:** Use `cryptography`'s Fernet symmetric encryption with a key stored in the OS-appropriate credential store where available (Windows Credential Manager / macOS Keychain / Linux Secret Service), falling back to a file-permission-restricted local key file with an explicit warning if no OS credential store is available.
- **Testing strategy:** `tests/test_session_store.py` — encryption round-trip test, verifies plaintext session data is never written to disk at any point (inspect all temp files created during a save operation), verifies file permissions on the fallback key file.
- **Verification checklist:** `pii_audit.py` extended with a new check confirming no `storage_state` plaintext ever appears in `packages/` or `generated_tools/` directories.
- **Definition of Done:** Session capture works, is opt-in, is encrypted at rest, and is provably excluded from any distributable package artifact.
- **Risks:** This is a **Critical** risk item — mishandling authenticated session data is more sensitive than the credential-scrubbing problem v1 already solved, because a `storage_state` is a live, directly-usable authentication bypass, not just a redacted field. **Mitigation:** encryption-at-rest is non-negotiable and must be independently security-reviewed (Phase v3.5) before this ships; session artifacts are never included in any package that could be shared/distributed between machines — they are explicitly machine-local only.
- **Rollback strategy:** Feature is fully opt-in; disabling it reverts every tool to v1/v2's default fresh-context-per-invocation behavior with zero migration needed.
- **Estimated complexity:** Very High (security-critical).
- **Estimated effort:** 2 weeks including mandatory security review.

### Step v3.4.2 — Session Reuse at Runtime & Expiry Handling

- **Objective:** Extend the `server.py.j2` template so a tool flagged as using a persistent session loads the decrypted `storage_state` into its browser context at launch, and gracefully falls back to the recorded login sequence (if still present in the spec) when the session has expired or is rejected by the site.
- **Problem being solved:** A saved session alone (v3.4.1) is useless without runtime logic to load it and to detect/handle expiry without crashing.
- **Why this step exists:** Completes the persistent-session feature loop.
- **Dependencies:** v3.4.1.
- **Files likely to change:** `browserbot/templates/mcp_server_template/server.py.j2`, `browserbot/runtime/session_store.py` (add `load_session`, `is_expired` heuristics).
- **Architecture impact:** Template gains a new, deterministic (non-LLM) session-loading and fallback-to-login code block, following the same Template vs. LLM split discipline as everything else — session handling logic is entirely hand-crafted Jinja2, never LLM-generated.
- **Implementation strategy:** Expiry detection via a lightweight heuristic (attempt the workflow; if it lands on what looks like a login page per a confirmed "login page indicator" selector captured during recording, treat the session as expired and re-run the login sequence, then retry once).
- **Testing strategy:** `tests/test_session_reuse.py` — mock fixture with an artificially expired session, verifying correct fallback-and-retry behavior; verify a valid session skips the login steps entirely (assert login step selectors are never invoked when a fresh valid session is loaded).
- **Verification checklist:** Benchmark (`run_benchmark.py`, extended) shows measurably reduced latency for a session-reuse-enabled tool versus its non-reuse equivalent on repeated invocations.
- **Definition of Done:** Session reuse demonstrably reduces runtime latency for a reference login-gated workflow; expiry fallback verified against a simulated expired-session fixture.
- **Risks:** False-positive expiry detection could cause unnecessary re-logins; false-negative could cause confusing failures on a genuinely expired session. **Mitigation:** conservative "login indicator selector" is explicitly confirmed by the operator at recording time (not inferred), making detection deterministic rather than heuristic-guessed.
- **Rollback strategy:** Disable session-loading in the template; tool falls back to full login-every-time behavior, matching v1/v2 exactly.
- **Estimated complexity:** High.
- **Estimated effort:** 1.5 weeks.

---

## Phase v3.5 — Advanced Validation & Security Hardening

### Dependency Rationale
This phase is a **hard gate**, not a sequential phase — it must run continuously alongside v3.2, v3.3, and v3.4 (every AST-allow-list expansion and every new filesystem/session interaction in those phases explicitly requires sign-off from this phase's work before being considered done, as already called out in each relevant step above). It is listed separately here to give it its own budget, ownership, and testing strategy rather than treating security review as an afterthought.

### Step v3.5.1 — Property-Based / Fuzz Testing of the AST Validator

- **Objective:** Introduce property-based testing (e.g., via `hypothesis`) that generates large numbers of synthetic, potentially-malicious Python AST trees and asserts the `DSLSecurityVisitor` never accepts anything outside the documented allow-list, across all allow-list versions (v1's original set plus v3.2's conditional and v3.3's table/upload extensions).
- **Problem being solved:** The existing adversarial test suite (`run_19.md`) is example-based (hand-written attack payloads); as the allow-list grows in v3, manually enumerated examples become an increasingly weak guarantee. Property-based testing explores a much larger space of possible malicious inputs automatically.
- **Why this step exists:** Directly mitigates the compounded R-02/R-15 risk introduced by v3's multiple AST allow-list expansions (v3.2.2, v3.3.1, v3.3.4).
- **Dependencies:** v3.2.2 and v3.3.1/v3.3.4 allow-list changes should exist (even in draft/branch form) before this step's test generators can target them, but the *framework* for this step can be built in parallel starting from day one of v3.
- **Files likely to change:** None in `browserbot/agents/code_generator/validator.py` itself (this step tests it, doesn't modify it, unless it discovers and forces fixes for a real gap — in which case the fix is scoped as its own small, targeted follow-up step).
- **New modules:** `tests/test_validator_fuzz.py`, `tests/fuzz_strategies.py` (hypothesis strategies for generating AST node trees biased toward edge cases: deeply nested calls, unusual attribute-access chains, string-based obfuscation attempts).
- **Architecture impact:** None (test-only addition); may surface bugs requiring small validator patches.
- **Implementation strategy:** Start with the full v1 allow-list surface (retrofit this testing to v1/v2's *existing* validator first, as a v3.5 warm-up task, establishing the harness before targeting the new v3.2/v3.3 verbs).
- **Testing strategy:** This step *is* a testing strategy; its own correctness is verified by seeding known-bad payloads (from `run_19.md`'s existing adversarial suite) and confirming the fuzz harness reliably flags them, before trusting it to find *new* issues.
- **Verification checklist:** Fuzz harness runs for a fixed, CI-budgeted duration (e.g., 5 minutes) on every PR touching `validator.py`; any newly discovered acceptance of a disallowed construct blocks merge.
- **Definition of Done:** Fuzz harness integrated into CI, running against the full v1+v2+v3 allow-list surface, zero unresolved findings.
- **Risks:** Fuzz testing can be flaky/slow if not carefully bounded. **Mitigation:** fixed time budget per CI run, deterministic random seed for reproducibility of any discovered failure.
- **Rollback strategy:** N/A — test-only infrastructure, no production code path depends on it.
- **Estimated complexity:** High.
- **Estimated effort:** 2 weeks.

### Step v3.5.2 — Multi-Run Reliability Scoring Integrated into the Validator Pipeline

- **Objective:** Extend `ValidationPipeline` (`run_10.md`) to optionally run the dry-run harness N times (default 5, configurable) and report a reliability percentage as part of `validation_report.json`, rather than reliability only being measurable via the separate standalone `run_benchmark.py` script (`run_18.md`).
- **Problem being solved:** Today, single-run validation can pass while the tool is still flaky (e.g., 3/5 real-world success rate) — this isn't caught until someone manually runs the benchmark script. Making multi-run reliability part of the standard validation gate catches this earlier, directly serving the v3 "Advanced Validation" goal.
- **Why this step exists:** Closes the gap between "generation-time validation" and "operational reliability," which the NFR doc already targets (≥90% success, `2. NonFunctionalRequirements_&_SuccessMetrics.md`) but which v1/v2 only measures via a separate, manually-triggered script.
- **Dependencies:** v1's `ValidationPipeline` and `run_benchmark.py`'s existing reliability-measurement logic (reused, not duplicated).
- **Files likely to change:** `browserbot/agents/validator/pipeline.py` (new optional Stage 6: Multi-Run Reliability, off by default to preserve the existing ≤3-minute Generation Time NFR — opt-in via `--reliability-check` flag), `browserbot/models/validation_report.py` (new fields for per-run results and aggregate reliability percentage).
- **Architecture impact:** None structural; reuses the existing `DryRunHarness` in a loop, exactly as `run_benchmark.py` already does — this step's real contribution is *surfacing* that capability inside the standard validation gate as an explicit, optional stage rather than requiring a separate script invocation.
- **Implementation strategy:** Because running the harness 5x adds meaningful time, this stage is opt-in and explicitly documented as trading Generation Time NFR compliance for a stronger reliability guarantee — never silently enabled by default.
- **Testing strategy:** `tests/test_validator.py` extension — mock harness with intentionally flaky (e.g., alternating pass/fail) results, verify correct aggregate percentage calculation and correct pass/fail threshold behavior (default gate: ≥80%, configurable).
- **Verification checklist:** Running with `--reliability-check` against the NoBuyCart reference workflow produces a `validation_report.json` reliability score consistent with a manually-run `run_benchmark.py` invocation on the same package.
- **Definition of Done:** Opt-in multi-run reliability stage implemented, tested, and documented as an explicit NFR trade-off.
- **Risks:** Confusing two similar-but-distinct reliability measurement paths (this stage vs. the standalone benchmark script) could create maintenance drift. **Mitigation:** this stage's implementation directly calls into the same underlying harness-invocation function `run_benchmark.py` uses — no duplicated logic.
- **Rollback strategy:** Feature is opt-in; disabling leaves validation pipeline behavior identical to v1/v2.
- **Estimated complexity:** Medium.
- **Estimated effort:** 1 week.

---

## Phase v3.6 — Enterprise Readiness

### Step v3.6.1 — Audit Logging

- **Objective:** Add structured audit log entries (who/what/when, using the existing structured JSON logging standard from `5. High Level System Design.md`'s Observability section) for every registration, unregistration, self-heal, and package regeneration event.
- **Problem being solved:** In a multi-operator or team setting, there is currently no record of *who* registered or modified which tool, or *when* — acceptable for a single-operator local tool, insufficient for team/enterprise use.
- **Why this step exists:** Baseline requirement for any team-shared BrowserBot deployment.
- **Dependencies:** v1's structured logging conventions (reused, extended, not replaced).
- **Files likely to change:** `browserbot/runtime/registry.py` (log entries on register/unregister), `browserbot/agents/self_healing.py` (log entries on heal events), `browserbot/agents/packager/packager.py` (log entries on package regeneration).
- **New modules:** `browserbot/runtime/audit_log.py` (append-only structured log writer, local file, e.g. `~/.browserbot/audit.log.jsonl`).
- **Architecture impact:** None structural; purely additive observability, consistent with the existing "every component emits structured JSON logs" principle.
- **Implementation strategy:** Append-only JSONL format (one JSON object per line) for easy tailing/ingestion by external log aggregation if a team later wants it, without BrowserBot itself needing to own any log-shipping infrastructure (stays local-first).
- **Testing strategy:** `tests/test_audit_log.py` — verify every registry/self-heal/packaging operation writes exactly one well-formed audit entry.
- **Verification checklist:** `audit.log.jsonl` entries are individually valid JSON and collectively form a complete, ordered history of a multi-operation test scenario.
- **Definition of Done:** All four operation types (register, unregister, self-heal, regenerate) produce audit entries; log is append-only and local-first (no network transmission).
- **Risks:** Log file could grow unbounded over long-term use. **Mitigation:** document manual/periodic rotation guidance; automated rotation is out of scope for v3 (candidate for Future Research if genuinely needed).
- **Rollback strategy:** Purely additive; removing the audit writer has zero impact on core pipeline function.
- **Estimated complexity:** Low–Medium.
- **Estimated effort:** 3–4 days.

### Step v3.6.2 — Config Export/Import for CI-Based Re-Registration

- **Objective:** Add `python -m browserbot.runtime export --output team_tools.json` and `... import team_tools.json` so a team's set of registered tools can be version-controlled and re-applied on a new machine or in a CI pipeline that provisions a fresh Claude Desktop environment.
- **Problem being solved:** Today, registration is entirely local and manual per machine; teams standardizing on a shared set of BrowserBot tools have no way to reproduce that set elsewhere without manually re-running `register` for every package.
- **Why this step exists:** Enterprise/team reproducibility, directly extending the existing NFR "Reproducibility" requirement (`2. NonFunctionalRequirements_&_SuccessMetrics.md`) from "clean environment can run the pipeline" to "clean environment can reproduce a *specific team's tool set*."
- **Dependencies:** v3.6.1 (export format reuses/complements audit log structure where sensible), v1's `ClaudeDesktopRegistry`.
- **Files likely to change:** `browserbot/runtime/registry.py` (`export`/`import_config` methods), `browserbot/runtime/__main__.py` (new subcommands).
- **Architecture impact:** None structural; the export format is a manifest referencing package directories (assumed to be separately synced, e.g., via the team's existing source control or shared drive) — it does not attempt to embed or transport the packages themselves, keeping this step's scope tightly bounded.
- **Implementation strategy:** Export format is a simple JSON list of `{tool_name, package_path, checksum}`; `import` verifies each referenced package directory exists locally (with its checksum matching) before registering, failing loudly and specifically (not silently skipping) if a package is missing.
- **Testing strategy:** `tests/test_registry.py` extension — export/import round-trip test; import test with a deliberately missing package directory verifying the correct, specific error message.
- **Verification checklist:** Exporting from one test registry state and importing into a fresh, empty registry state reproduces an identical `mcpServers` config block (byte-for-byte, excluding backup timestamps).
- **Definition of Done:** Export/import round-trips correctly; missing-package error handling is clear and actionable; documented in `USER_WORKFLOW_GUIDE.md` as a new team-workflow section.
- **Risks:** Checksum mismatch handling could be too strict (blocking legitimate minor package updates) or too loose (silently accepting a tampered package). **Mitigation:** default to strict (exact match required), with an explicit `--allow-mismatch` override flag for intentional cases, defaulting to the safer behavior.
- **Rollback strategy:** Purely additive CLI subcommands; no impact on existing single-machine registration workflow.
- **Estimated complexity:** Medium.
- **Estimated effort:** 1 week.

---

# RELEASE III — BrowserBot Future Research

This release is explicitly **research, not committed engineering**. Each phase below is scoped as a time-boxed spike with a clear "go/no-go" decision output, not a guaranteed shipped feature. Only items judged technically realistic given BrowserBot's local-first, deterministic-generation architecture are included; anything requiring a fundamental architectural rewrite (e.g., abandoning the AST-validated DSL approach entirely) is deliberately excluded as unrealistic.

## Research Area F.1 — API-Mode Generation

**Problem being explored:** Many "browser automations" are actually thin wrappers around a site's underlying REST/GraphQL API that the browser calls internally. Could BrowserBot detect this during recording (via Playwright's network-request capture) and, when safe/reliable, generate a direct HTTP-client tool instead of a full browser-automation tool — trading generality for dramatically better runtime latency?

- **Why this is realistic:** Playwright already captures network traffic during codegen sessions; the *detection* half of this is low-risk. The *generation* half reuses the exact same Template + constrained-LLM-fill + AST-validation pattern already proven for Playwright code, just targeting a `requests`/`httpx` DSL subset instead of a Playwright DSL subset.
- **Why this is deferred past v3:** Requires new risk analysis (a generated HTTP client bypasses the browser's own CSRF/session handling, which needs its own security model distinct from the browser-automation threat model already solved) and reliable API detection is nontrivial (many sites' internal APIs are unstable/undocumented/versioned unpredictably).
- **Research spike scope:** Prototype network-capture-based API detection against 3–5 real sites; assess how often a clean, stable, direct-callable endpoint is actually identifiable; do not build production generation until detection reliability is empirically established.
- **Go/no-go criterion:** ≥60% of a sample of 20 recorded workflows yield a cleanly-identifiable, directly-callable API endpoint. Below that threshold, this research area is shelved indefinitely rather than force-fit.

## Research Area F.2 — Workflow Graphs (Beyond Single-Level Conditionals)

**Problem being explored:** v3.2 deliberately caps branching at one level with no loops. Could a genuine, small, bounded workflow-graph representation (state machine with named states/transitions) replace the flat-with-conditionals IR for advanced use cases, while still being fully AST-validatable?

- **Why this is realistic:** State machines are a well-understood, boundable formalism; each state's action list is still just a linear DSL-verb sequence, so the *validation* problem doesn't fundamentally change in kind, only in the graph structure wrapping it.
- **Why this is deferred:** This is a genuinely large IR redesign (schema v3.0) and should only be pursued once v3.2's much narrower conditional feature has real production usage data showing operators actually need more than single-level branching.
- **Research spike scope:** Design-only spike producing a schema proposal and a security analysis memo; no implementation until v3.2 has shipped and been used in production for at least one full release cycle.

## Research Area F.3 — Component Library (Reusable Recorded Sub-Workflows)

**Problem being explored:** Could common sub-sequences (e.g., "dismiss cookie banner," "handle a generic login form") be recorded once and referenced/composed into multiple workflows, rather than re-recorded every time?

- **Why this is realistic:** This is primarily a packaging/IR-composition problem, not a new codegen or security problem — a "component" is just a named, reusable `WorkflowSpec` step-list fragment, spliced into a parent spec at generation time, validated exactly as today.
- **Why this is deferred:** Needs a versioning/compatibility story (what happens when a shared component is updated — do all consuming workflows need regeneration?) that is worth designing carefully rather than rushing.
- **Research spike scope:** Prototype a single hard-coded "cookie banner dismissal" component reused across 2 existing reference workflows; evaluate whether the composition model is ergonomic before generalizing.

## Research Area F.4 — Cloud & Distributed Execution

**Problem being explored:** Could generated tools optionally run in a remote/cloud headless-browser farm instead of the operator's local machine, for scale or for running many tools' scheduled jobs without keeping a laptop on?

- **Why this is realistic:** Playwright itself already supports remote browser connections (`connect_over_cdp`); the generated tool's DSL-validated logic doesn't inherently care whether `page` came from a local or remote browser context.
- **Why this is deferred and treated with caution:** This is in direct tension with BrowserBot's core local-first, $0-marginal-cost, zero-cloud-account architectural identity (`4. Tech-Stack.md`, `1. ProductRequirement.md`'s out-of-scope list explicitly excludes "Cloud deployment"). Any cloud execution mode must be strictly **optional and clearly separated** from the default local-first path, never assumed or defaulted to.
- **Research spike scope:** Cost/complexity/privacy-tradeoff memo only. Explicitly requires executive/product sign-off before any implementation spike, given the architectural identity tension.

## Research Area F.5 — Team Collaboration & Shared Workflow Repositories

**Problem being explored:** Building on v3.6's export/import (Step v3.6.2), could BrowserBot support a lightweight shared repository model (e.g., a git-backed `packages/` convention with a documented merge/conflict strategy) for teams collaboratively maintaining a shared tool set?

- **Why this is realistic:** Packages are already just directories of files; git already handles this class of problem for source code generally. This may require very little new BrowserBot-specific engineering — possibly just documentation and conventions on top of v3.6.2's export/import.
- **Why this is deferred:** Should follow real usage data from v3.6's enterprise features rather than being speculatively over-engineered.
- **Research spike scope:** Documentation-first spike: write the recommended git-based team workflow using only v3.6 primitives, pilot it internally, and only propose new tooling if the pilot reveals genuine friction that documentation alone can't solve.

## Research Area F.6 — Marketplace

**Problem being explored:** A public or semi-public marketplace for sharing pre-built BrowserBot tool packages across organizations/users.

- **Why this is realistic:** Technically, package structure already supports distribution; the packaging format from v1/v2 could underlie a marketplace listing format with modest changes.
- **Why this is deferred and treated with significant caution:** This is the single highest trust/security-risk research area in this entire document — a marketplace of executable browser-automation code (even AST-validated) authored by third parties is a fundamentally different threat model than a single operator generating and running their own tools. Any AST-validated DSL guarantee protects against a *misbehaving LLM*, not against a *malicious human* who deliberately crafts a spec to abuse a real site (e.g., scraping at scale, credential stuffing) while staying within the DSL's technical bounds.
- **Research spike scope:** Threat-modeling memo only, explicitly evaluating whether AST/DSL validation is *sufficient* trust boundary for third-party-authored specs (likely conclusion: it is necessary but not sufficient — additional sandboxing, rate-limiting, and human review processes would be required). No implementation planning until this threat model is resolved.

## Research Area F.7 — Enterprise Deployments (Managed/Hosted BrowserBot)

**Problem being explored:** A managed deployment model for organizations wanting centralized administration of BrowserBot across many employee machines (policy enforcement, centralized package approval, centralized audit log aggregation building on v3.6.1).

- **Why this is realistic:** v3.6's audit logging and export/import primitives are a legitimate foundation; centralized *aggregation* of already-local audit logs is a modest extension, not a rearchitecture.
- **Why this is deferred:** Genuinely large scope (identity/SSO integration, centralized policy distribution) that only makes sense to pursue if v3's enterprise features (v3.6) see real organizational adoption first.
- **Research spike scope:** Customer-discovery-style spike (interviews/surveys with prospective enterprise users of v3.6), not an engineering spike, until real demand signal exists.

## Research Area F.8 — Browser Extension–Based Recording

**Problem being explored:** Instead of launching a separate Playwright Codegen Chromium instance, could recording happen via a browser extension inside the operator's *own*, already-logged-in browser profile, capturing the same structured action data?

- **Why this is realistic:** Would meaningfully improve the recording UX (no separate browser profile, no re-login for sites the operator is already authenticated to) and browser extensions have mature APIs for exactly this class of DOM-event capture.
- **Why this is deferred:** A real architectural fork of the Capture Layer (`5. High Level System Design.md`'s Recorder component) — the current Recorder is fundamentally Playwright-Codegen-based; an extension-based recorder would need its own event-to-ActionLog conversion path, likely reusing `run_03.md`'s existing schema target but not its existing converter implementation.
- **Research spike scope:** Prototype a minimal browser extension capturing clicks/fills into the existing `action_log_schema.json` shape for a single reference site; evaluate conversion fidelity against the existing Playwright-Codegen-based converter's output for the identical workflow before considering this a Recorder replacement/alternative.

## Research Area F.9 — Visual Workflow Editor

**Problem being explored:** A drag-and-drop / node-graph visual editor for authoring and editing `WorkflowSpec` IR directly (especially valuable once F.2's workflow-graph IR exists), rather than authoring exclusively through record-then-confirm.

- **Why this is realistic:** The IR is already a structured, versioned JSON contract designed for programmatic consumption (`run_07.md`'s explicit design goal); a visual editor is "just" another IR-consuming client, architecturally no different in kind from the Code Generator or the v2 UI wizard.
- **Why this is deferred:** Depends on F.2's graph-shaped IR to be worth building (a visual editor for a purely linear-plus-single-conditional IR offers limited value over the existing confirmer UX) — sequenced explicitly after F.2, not before.
- **Research spike scope:** No implementation spike until F.2 reaches at least a design-approved state; at that point, a low-fidelity clickable prototype (not production code) evaluating editor ergonomics against a handful of real recorded workflows.

---

# FINAL SECTION — Cross-Release Planning

## 1. Overall Dependency Graph

```
v1.0 (DONE)
  │
  ├──────────────────────────────────────────────────────────┐
  ▼                                                            ▼
v2.1 Orchestration Server                              v2.4 Runtime Response Quality (parallel)
  │                                                      v2.5 Recorder/DX (parallel)
  ▼                                                      v2.6 Package Versioning (parallel)
v2.2 Web UI Wizard
  │
  ▼
v2.3 Live Progress Streaming
  │
  ▼
════════ v2 RELEASE ════════
  │
  ▼
v3.1 Multi-Site Support
  │
  ├─────────────┬─────────────────────┐
  ▼             ▼                     ▼
v3.2 Branching  v3.4 Persistent      (v3.5 Advanced Validation
  │             Sessions              runs continuously beside
  ▼                                   v3.2 / v3.3 / v3.4 as a
v3.3 Tables/Pagination/Iframes/Files  hard security gate)
  │
  ▼
v3.6 Enterprise Readiness
  │
  ▼
════════ v3 RELEASE ════════
  │
  ▼
Future Research (F.1–F.9)
  — F.9 explicitly depends on F.2
  — F.5/F.7 depend on real v3.6 adoption data
  — F.6 requires a resolved threat model before any implementation
```

## 2. Critical Path

`v2.1 → v2.2 → v2.3 → [v2 release] → v3.1 → v3.2 → v3.3 → v3.6 → [v3 release]`

This is the critical path because: the UI (v2.2) cannot start without the server (v2.1); progress streaming (v2.3) is the last piece needed for a complete, polished wizard experience and is treated as a release blocker rather than a nice-to-have; v3.1 must land before v3.2 to validate the v3 release/migration process on a lower-risk change first; v3.2's branching capability is a prerequisite pattern for v3.3's table/pagination work; v3.6 (enterprise readiness) is scheduled last within v3 since it has the fewest hard technical dependencies but benefits from the multi-site (v3.1) foundation being in place first.

## 3. Parallelizable Workstreams

- **Workstream A (Server/UI):** v2.1 → v2.2 → v2.3. Single dedicated frontend+backend pair.
- **Workstream B (Runtime Quality):** v2.4, independent, can run entirely in parallel with Workstream A.
- **Workstream C (DX/Tooling):** v2.5, v2.6, independent, can run in parallel with A and B.
- **Workstream D (v3 Advanced Interaction):** v3.3.3 (iframes) and v3.3.4 (uploads/downloads) are independent of each other and of v3.3.1/v3.3.2 (tables/pagination) — all four can be staffed as separate parallel engineers once v3.2's review-process precedent is established.
- **Workstream E (Security):** v3.5 runs continuously in parallel with all of v3.2–v3.4, as a dedicated reviewer/gate function, not a sequential phase.
- **Workstream F (Enterprise):** v3.6.1 (audit logging) has no dependency on v3.2/v3.3/v3.4 and could actually be pulled forward to run in parallel with v3.1 if staffing allows.

## 4. High-Risk Components

Ranked by risk severity:

1. **v3.4 Persistent Authenticated Sessions** — highest risk; live credential-bypass artifact, encryption-at-rest is non-negotiable, independent security review is a hard gate.
2. **v3.2 Conditional/Branching IR + AST validator `if` allowance** — expands the sandboxed code-execution surface for the first time since v1's inception; requires the same rigor as the original R-15 mitigation design.
3. **v3.3.4 File Upload/Download** — first filesystem read/write surface beyond the pipeline's own artifacts; path-traversal/sandbox-escape risk.
4. **F.6 Marketplace (Future Research only)** — highest long-term risk in the entire roadmap; explicitly gated behind an unresolved threat-modeling question and not scheduled for implementation in this document.
5. **v2.1 Orchestration Server** — moderate risk (must not bind beyond loopback, must not become a new network attack surface) but well-understood and mitigated by binding to `127.0.0.1` only.

## 5. Estimated Timeline

Assuming a small dedicated team (2–3 engineers) working the workstreams above with the parallelization described in Section 3:

| Release | Estimated Duration | Notes |
|---|---|---|
| v2 (all phases) | ~8–10 weeks | Workstreams A/B/C run mostly in parallel; A is the long pole at ~6 weeks alone. |
| v3 (all phases) | ~16–20 weeks | v3.2/v3.5 security review cycles are the long pole; v3.3's four sub-steps parallelize well once v3.2 lands. |
| **Total v2 + v3** | **~24–30 weeks (≈6–7 months)** | |
| Future Research spikes (F.1–F.9, selectively pursued) | Ongoing, opportunistic | Not on the critical path; pursued as capacity and demand signals allow, over the following ~12 months. |

This totals to roughly **18 months** from v1 completion through a mature Future Research exploration phase, matching the scope implied by the original planning brief.

## 6. Suggested Implementation Order

1. v2.1 → v2.2 → v2.3 (server + UI, sequential, Workstream A)
2. v2.4, v2.5, v2.6 in parallel with the above (Workstreams B & C)
3. **v2 release checkpoint**
4. v3.1 (multi-site)
5. v3.6.1 (audit logging) — can start as early as step 4, in parallel
6. v3.2 (branching) — with v3.5 security review running alongside from day one
7. v3.3.1 → v3.3.2 (tables → pagination, sequential; reuses v3.2 patterns)
8. v3.3.3, v3.3.4 in parallel with step 7 (independent sub-features)
9. v3.4 (persistent sessions) — can start in parallel with step 6 onward, given independence, but its security review (part of Workstream E) must complete before release
10. v3.6.2 (export/import) after v3.6.1
11. **v3 release checkpoint**
12. Future Research spikes, prioritized by product/demand signal, not by this document

## 7. Which Phases Should Be Implemented by Humans

- **v3.2 (branching IR + AST validator extension)** — the security-critical design decisions (scope-capping at single-level, no loops) require human product/security judgment calls that should not be delegated.
- **v3.4 (persistent sessions)** — encryption design and key-management strategy require human security engineering review; this is the single most sensitive piece of new infrastructure in the roadmap.
- **v3.3.4 (upload/download sandboxing)** — path-containment security logic warrants human implementation and human-led adversarial testing design.
- **v3.5 (security hardening)** in its entirety — by definition, the reviewer function should be human-led, though the fuzz-testing *harness* itself (v3.5.1) can be LLM-assisted once the review criteria are human-defined.
- **Any Future Research threat-modeling memos (F.4, F.6, F.7)** — these are judgment/strategy documents, not implementation, and should be human-authored.

## 8. Which Phases Can Safely Be Delegated to an Implementation LLM

- **v2.1 (server skeleton/REST endpoints)** — well-specified, mirrors existing CLI entry points 1:1, low ambiguity.
- **v2.2 (UI wizard)** — once the REST contract (v2.1) is frozen, UI implementation against a fixed API contract is a strong LLM-delegation candidate.
- **v2.3 (progress streaming)** — mechanical extension of existing diagnostics instrumentation.
- **v2.4, v2.5, v2.6** — all low-risk, additive, well-scoped; excellent delegation candidates.
- **v3.1 (multi-site packaging)** — additive aggregation logic over already-proven single-workflow packaging; good delegation candidate with human review of the final schema diff.
- **v3.3.1, v3.3.2 (tables/pagination)** — once the *review process and bound constraints* are human-approved (per v3.2's precedent), the mechanical implementation of the deterministic-unroll templates is delegable.
- **v3.6 (enterprise readiness)** — audit logging and export/import are mechanical, well-specified, low-risk.

**General rule of thumb applied throughout this document:** any step whose primary risk is *implementation correctness* is LLM-delegable with human code review; any step whose primary risk is *security boundary design* (what should the sandbox allow, how should secrets be stored, what is the trust model) requires human authorship of the design, even if implementation details are then delegated.

## 9. Recommended Checkpoints After Every Release

- **After v2:** Full regression suite green; live demo of the complete UI wizard flow to stakeholders; NFR re-verification (`run_benchmark.py`) confirming no latency/generation-time regression versus v1 CLI-only operation.
- **After v3.1 (mid-v3 checkpoint):** Verify multi-site packaging in production-like conditions (at least 2 real sites, 3+ workflows) before proceeding to the higher-risk v3.2.
- **After v3.2 (mid-v3 checkpoint, security gate):** Independent security sign-off document required and archived before v3.3 begins consuming the same allow-list-expansion pattern.
- **After v3.4 (mid-v3 checkpoint, security gate):** Independent security sign-off on the encryption/key-management implementation required before v3 release.
- **After v3 (full release):** Full regression suite (v1+v2+v3) green; `pii_audit.py` extended-check suite green including the new session-storage and download-sandbox checks; enterprise readiness checklist verified against a simulated multi-operator scenario; retrospective document capturing what from Future Research (F.1–F.9) now looks more or less realistic given what was learned building v3.

## 10. Final Recommendation

If I were leading BrowserBot development, this is exactly how I would execute the next 18 months of work: ship v2 fast and mostly in parallel — it is almost entirely additive, low-risk product polish sitting on top of an already-audited v1 pipeline, and the biggest lever for adoption is simply making the existing capability easier to reach. Treat the v2 → v3 boundary as a real checkpoint, not just a version number, because v3 is where BrowserBot's risk profile changes materially: v3.2's branching, v3.3.4's filesystem access, and above all v3.4's persistent-session storage each expand the security boundary that v1's AST-validator and scrubber were specifically designed to hold. Sequence v3.1 first specifically to rehearse the release process on a safe change before touching anything security-sensitive. Run security review (v3.5) as a continuous, staffed function throughout v3, not a final audit — the same discipline that produced a clean 115/115-test, independently-audited v1.0 is exactly what a security-surface-expanding v3 requires, doubly so. Treat everything in Future Research as genuinely optional: F.6 (Marketplace) in particular should not be scheduled until its threat model is resolved, and F.4 (Cloud Execution) should not be pursued without explicit reaffirmation that it doesn't compromise the local-first identity that is BrowserBot's core differentiator. Delegate mechanical, well-specified implementation work to an LLM aggressively — v2 in particular is close to entirely delegable with human review — but keep every security-boundary *design* decision, and the v3.5 review function itself, firmly human-owned.

---

*BrowserBot Future Execution Plan — v1.0 of this document.*
