# BrowserBot — Phase-by-Phase Execution Plan
**Role:** Technical Project Manager / Lead System Architect
**Source docs:** BrowserBot Deep Research Feasibility Analysis (PDF) + Executive Summary (DOCX)
**Plan basis:** "Record once → auto-generate a reusable MCP tool → invoke via Claude"

---

## How to Read This Plan

Every phase starts with a short **Objective** and **Exit Criteria** (the gate you must clear before moving on). Every step inside a phase is broken into the four elements you asked for:

- **Actionable Implementation** — exactly what to build/do
- **Expected Outcome** — the technical/functional result
- **Deliverable / Demo** — the tangible artifact you show stakeholders
- **Verification & Testing** — how you prove it's correct before moving on

Scope assumption (stated explicitly so nothing is ambiguous): MVP targets **one authenticated, form/click-based workflow on one website** (e.g., "check order status"), matching the feasibility doc's own scoping advice. Multi-site generalization is deliberately pushed to Phase 8, not Phase 1 — trying to generalize before one flow works end-to-end is the single biggest risk of this project blowing its timeline.

---

## ⚠️ Architecture Change Note — Zero-Budget LLM Backend

**What changed:** The original plan used the **Claude API** (pay-per-token) as the LLM backend for the Pattern Extractor and Code Generator agents. Per an updated hard budget constraint of $0, that backend is removed entirely and replaced with:

- **Primary: Ollama running a local, open-weight model** — installed once, runs on your own machine, $0 marginal cost no matter how many times you invoke it, no signup, no credit card, no rate limit, no network dependency for the core pipeline.
- **Optional fallback: Groq's free API tier** — also genuinely $0 (no credit card required), for anyone whose laptop can't run a capable model at a usable speed. It's cloud-hosted and rate-limited (roughly 30 requests/min, ~14,400 requests/day depending on model, as of mid-2026 — verify current numbers at `console.groq.com/docs/rate-limits` since free-tier terms shift), but it never bills you a dollar.
- **A thin provider-abstraction layer** (`litellm`, or a 15-line wrapper if you want zero extra dependencies) so the Pattern Extractor and Code Generator call one interface regardless of which backend is active — switching from local to Groq (or back) is a one-line config change, not a rewrite.

**What did *not* change:** Claude Desktop remains the **runtime** MCP host the generated tool gets installed into — that's the whole point of the project, and using Claude Desktop as a chat client isn't the same thing as paying for the Claude API. It's unaffected by this constraint and stays exactly as originally planned.

**Why this is actually a good fit, not just a workaround:** the research doc's own differentiation angle #6 was "local-first, zero-cloud-account MVP" as a privacy/trust wedge against Skyvern's enterprise/cloud posture. Running the LLM agents locally doesn't just satisfy your budget — it makes that claim *literally* true instead of carving out an exception for LLM calls, which strengthens the demo narrative in Phase 10 for free.

Every phase below has been updated to reflect this. Affected: Steps 0.2, 0.3, 0.4, 1.1, 3.1, 4.2, 5.3, 8.3, 9.2, and the Cross-Phase Notes.

---

## PHASE 0 — Initial Planning & Architecture

**Objective:** Turn the research doc into a concrete, buildable spec: locked scope, defined interfaces between agents, and a diagram set that lets any stakeholder (recruiter, teammate, future-you) understand the system in under 5 minutes.

**Exit Criteria:** Written scope doc + 6-diagram architecture pack approved (even if "approved" just means you've reviewed it against the risk register and it holds up).

### Step 0.1 — Stakeholder & Requirement Gathering

- **Actionable Implementation:** Since this is a solo/small-team portfolio build, "stakeholders" = you-as-builder, you-as-demo-audience, and any recruiter/reviewer who'll eventually watch the demo. Run a structured self-interview and write answers down: What's the one sentence pitch? What's the exact demo script (verbatim: "Claude, did my order ship?")? What's the *one* website/task the MVP proves this on? What's explicitly out of scope for v1 (multi-site, 2FA, CAPTCHA, mobile)?
- **Expected Outcome:** A single-page **Product Requirements Note** (functional requirements: record → generalize → generate MCP tool → invoke via Claude; non-functional requirements deferred to 0.2).
- **Deliverable / Demo:** `docs/requirements.md` containing: problem statement, target user, one locked demo scenario, in-scope/out-of-scope list.
- **Verification & Testing:** Read the requirements note aloud as if pitching to a stranger in 60 seconds. If it takes longer or needs a diagram to make sense, the scope is still too broad — tighten it before proceeding.

### Step 0.2 — Non-Functional Requirements (NFRs) & Success Metrics

- **Actionable Implementation:** Define measurable targets, not vibes: (1) end-to-end generation time budget (e.g., recorder stop → installable tool ≤ 3 minutes — expect this to run longer on CPU-only hardware with a local model than it would with a hosted API, so measure it on your actual machine rather than assuming), (2) runtime invocation latency budget (Claude asks → answer ≤ 15–20 seconds for a headless run — this is a Playwright/network number and is unaffected by the LLM backend swap, since runtime invocation never calls an LLM at all), (3) reliability target (≥ 8/10 successful runs on the demo site before you consider it "demo-ready"), (4) zero persistence of credentials/PII (hard requirement, not aspirational), (5) local-first constraint — with the default Ollama backend, zero data leaves the machine at all, including LLM inference; if the optional Groq free-tier fallback is ever enabled, only the minimal prompt payload leaves the machine, and it must never include raw credentials/PII (already scrubbed per Step 2.4), (6) **cost ceiling — $0**, tracked explicitly as its own NFR since it's now a hard constraint, not an assumption: no step in this plan may require a credit card or paid API account to complete end-to-end.
- **Expected Outcome:** A short NFR table stakeholders can hold you accountable to, and that later becomes your acceptance test criteria in Phase 9.
- **Deliverable / Demo:** `docs/nfr.md` — a table of metric, target, measurement method.
- **Verification & Testing:** Cross-check each NFR is actually testable (e.g., "reliability ≥ 8/10" is testable via a scripted 10-run loop; "feels fast" is not — reject vague NFRs).

### Step 0.3 — Risk Register & Assumption Log

- **Actionable Implementation:** Transcribe the feasibility doc's risk section into a living register with owner, likelihood, impact, and mitigation columns. Minimum entries: LLM misinterprets the demo log; site DOM changes break selectors; login/2FA blocks automation; complex JS-driven UI doesn't record cleanly; headless run is too slow for a live demo; **a free local/open-weight model produces lower-quality or less consistent output than a frontier hosted model would have (new entry, direct consequence of the zero-budget constraint) → mitigation: the constrained-template + allow-list-validation + retry-loop design (Steps 4.1, 4.2, 5.3) already absorbs most of the reliability gap between a 7B–14B local model and a frontier API model, since the local model's job is narrowed to filling a small DSL slot rather than open-ended reasoning; keep the Groq free-tier fallback documented and ready to flip on for any single step that proves unreliable on your chosen local model, at zero additional cost**.
- **Expected Outcome:** A prioritized risk list that directly drives which phases get extra buffer time (Phases 3, 4, and 8 absorb most of this risk).
- **Deliverable / Demo:** `docs/risk_register.md`, reviewed and re-scored at the end of every phase (5-minute ritual, not a formal ceremony).
- **Verification & Testing:** At each phase gate, confirm at least one register item was either mitigated or downgraded — if the register never changes, it isn't being used.

### Step 0.4 — Technology Stack Decision

- **Actionable Implementation:** Lock the stack now so Phase 1 doesn't stall on indecision: **Python 3.11+**, **Playwright (Python)** for automation, **FastMCP** for the generated server scaffold, **Ollama running a local open-weight model** as the LLM backend for both the Pattern Extractor and Code Generator agents (this replaces the Claude API entirely — $0 marginal cost regardless of call volume, no signup, no credit card), **Groq's free API tier** (no credit card, OpenAI-compatible endpoint) wired in as an optional cloud fallback only, a thin **LiteLLM wrapper** (or a ~15-line custom function) so agent code calls one interface regardless of which backend is active, **Playwright's built-in codegen/trace viewer** as the recording mechanism (cheaper and more reliable than hand-rolling a Chrome extension for MVP), SQLite or flat JSON files for local session storage, `mcpb` CLI for packaging as a Claude Desktop extension (Claude Desktop is the *runtime* MCP host the tool installs into — a chat client, not a billed API, so it's untouched by the budget constraint).

  Pick the local model by hardware tier — confirm the current recommended tag at `ollama.com/library` before pulling, since the catalog updates monthly:

  | Your hardware | Recommended local model | Notes |
  |---|---|---|
  | 8 GB RAM, no dedicated GPU | `qwen2.5-coder:7b` or `llama3.1:8b` (Q4) | Runs CPU-only; slower per call (tens of seconds), but this is a build-time-only cost, not runtime |
  | 16 GB RAM / 8–12 GB VRAM | `qwen2.5-coder:14b` | Noticeably more reliable instruction-following than the 7B tier — worth the jump if you have the RAM |
  | 24 GB+ VRAM, or Apple Silicon with 32 GB+ unified memory | `qwen2.5-coder:32b` or a MoE coder tag such as `qwen3-coder:30b` | Local quality roughly comparable to a mid-tier hosted model for this narrow, template-constrained task |
  | Any tier, if local proves too slow/unreliable for a given step | Groq free tier, e.g. `llama-3.3-70b-versatile` (OpenAI-compatible endpoint, no card) | Still $0; trades "fully offline" for speed and a (generous, but real) rate limit |

  It's reasonable to use *two different* local models for the two agent roles since both are free to run side-by-side on disk: a general instruction-following model (e.g., `llama3.1:8b`) for the Pattern Extractor's structured-JSON-reasoning task, and a code-specialized model (e.g., `qwen2.5-coder:7b`) for the Code Generator's DSL-filling task — code-tuned models are measurably better at producing syntactically correct, constrained output.
- **Expected Outcome:** A stack decision doc that removes ambiguity for every later phase; anyone reading it can `pip install`, pull a model, and start building on day one with zero accounts and zero spend anywhere in the loop.
- **Deliverable / Demo:** `docs/tech_stack.md` with versions pinned (including the exact Ollama model tags chosen), plus a `requirements.txt` / `pyproject.toml` stub.
- **Verification & Testing:** `pip install -r requirements.txt` succeeds in a clean virtualenv on a second machine (proves reproducibility), and separately confirm `env | grep -i api_key` returns nothing in the default configuration — proving no paid credential is required anywhere in the base setup. If the Groq fallback is configured, confirm its key lives only in a git-ignored `.env` file, never committed.

### Step 0.5 — System Architecture & Required Diagram Suite

This is the deliverable stakeholders will actually look at. Six diagrams are required — fewer and you can't explain the pipeline; more and you're gold-plating a demo.

| # | Diagram | Purpose | Audience |
|---|---|---|---|
| 1 | **System / Container Architecture Diagram** | Shows the 7 major containers (Recorder, Backend Orchestrator, Pattern Extractor Agent, Code Generator Agent, Validator Agent, Generated MCP Server, Claude Desktop) and how data flows between them | Recruiters, teammates, first-glance understanding |
| 2 | **Data Flow Diagram (DFD), Level 0 + Level 1** | Level 0: user demo → tool artifact as a single black box. Level 1: expands into Raw Action Log (JSON) → Parameterized Workflow Spec → Generated Script → MCP Manifest → Validation Report | Explains *what data* moves, distinct from *what components* exist |
| 3 | **Sequence Diagram — "Record & Generate"** | User → Recorder → Backend → Pattern Extractor (LLM) → Code Generator (LLM) → Validator → Packaged Tool | Shows the offline, one-time generation flow |
| 4 | **Sequence Diagram — "Runtime Invocation"** | User → Claude Desktop → Generated MCP Server → Playwright → Target Website → back to Claude | Shows the repeatable, runtime flow — this is the actual "wow" moment, so it deserves its own diagram |
| 5 | **State Diagram — Recording Session Lifecycle** | `Idle → Recording → Stopped → Parameterizing → Generating → Validating → (Installed | Failed→Retry)` | Drives your UI/UX design in Phase 7 directly |
| 6 | **Deployment Diagram** | Local-first layout: user's OS, Python venv, Chromium instance, Claude Desktop process, `~/.browserbot/tools/<tool_name>/` file layout | Proves the "no cloud, nothing leaves your machine" privacy claim from the research doc |

- **Actionable Implementation:** Build diagrams 1–4 in a tool with source-controllable syntax (Mermaid or PlantUML in-repo, or draw.io/Excalidraw exported as SVG) — do not use a screenshot-only tool you can't diff in git. A minimal Mermaid sketch for diagram #1, to seed the real one:

  ```mermaid
  graph LR
    A[User's Browser] --> B[Recorder / Codegen]
    B --> C[Backend Orchestrator]
    C --> D[Pattern Extractor Agent LLM]
    D --> E[Code Generator Agent LLM]
    E --> F[Validator Agent]
    F --> G[Generated MCP Server]
    G --> H[Claude Desktop]
    H --> I[Playwright Runtime]
    I --> J[Target Website]
    J --> I --> H
  ```

- **Expected Outcome:** A `docs/architecture/` folder with 6 versioned diagram source files + rendered PNG/SVG exports, each with a 2–3 sentence caption.
- **Deliverable / Demo:** A single-page architecture README that embeds all 6 diagrams in order — this is literally what you screen-share when someone asks "how does this work?"
- **Verification & Testing:** Hand the architecture README to someone unfamiliar with the project (or re-read it cold after 48 hours) and confirm they can explain, unprompted, the difference between "generation time" and "runtime" — if that distinction isn't obvious from the diagrams alone, diagram #3 vs #4 needs clearer separation.

---

## PHASE 1 — Environment, Tooling & Project Scaffolding

**Objective:** A reproducible dev environment and a repo skeleton that mirrors the architecture diagram, so every later phase has an obvious place to put code.

**Exit Criteria:** A committed skeleton repo where `python -m browserbot.recorder --demo` and a placeholder FastMCP server both run without error.

### Step 1.1 — Local Dev Environment Setup

- **Actionable Implementation:** Create a virtualenv, `pip install playwright fastmcp ollama litellm pytest`, run `playwright install chromium`. Separately, install Ollama itself (`curl -fsSL https://ollama.com/install.sh | sh` on Mac/Linux, or the installer from `ollama.com` on Windows) and pull your chosen model per the Step 0.4 hardware table, e.g. `ollama pull qwen2.5-coder:7b`. Install Node only if you later need the `mcpb` packaging CLI (`npm install -g @anthropic-ai/mcpb` or equivalent per current docs) — that's for packaging the *generated tool* for Claude Desktop and is unrelated to the LLM backend swap.
- **Expected Outcome:** A working local environment where `playwright codegen https://example.com` opens a browser and records a click-through, and separately `ollama run qwen2.5-coder:7b "reply with the word OK"` returns a response with the Ollama service running on `localhost:11434` — no network call to any paid provider.
- **Deliverable / Demo:** A terminal recording (asciinema or screen capture) showing both `playwright codegen` producing a script for a trivial site, and a local `ollama run` call succeeding with no API key set anywhere in the environment.
- **Verification & Testing:** Re-create the environment from a clean checkout (`rm -rf venv && python -m venv venv && pip install -r requirements.txt`) and confirm identical behavior — catches "works on my machine" drift early. Also confirm `ollama list` shows the pulled model, and that a fresh shell with no `.env` file loaded can still complete a full Ollama round-trip — proving the default path never depends on a credential.

### Step 1.2 — Repository & Project Structure Scaffolding

- **Actionable Implementation:** Create the skeleton:
  ```
  browserbot/
    recorder/          # capture layer (Phase 2)
    agents/
      pattern_extractor.py   # Phase 3
      code_generator.py      # Phase 4
      validator.py            # Phase 5
    templates/
      mcp_server_template/    # Phase 4
    generated_tools/          # output dir, git-ignored
    ui/                        # Phase 7
    docs/
    tests/
  ```
- **Expected Outcome:** A folder structure that maps 1:1 onto the architecture diagram — anyone can find "where does codegen happen" without asking.
- **Deliverable / Demo:** Initial commit pushed to a git repo with this skeleton and a `README.md` linking back to `docs/architecture/`.
- **Verification & Testing:** `tree -L 2` output matches the architecture diagram's component list exactly — if a component in the diagram has no corresponding folder, fix one or the other.

### Step 1.3 — Baseline Playwright Script Against the Chosen Demo Site

- **Actionable Implementation:** Manually write (not generate yet) a Playwright script that performs the exact MVP demo task end-to-end (e.g., navigate → log in with a test account → enter an order ID → read the status text). This is your "ground truth" — the generation pipeline's job later is to reproduce this automatically.
- **Expected Outcome:** A hand-written script proving the underlying automation is *possible* on the chosen site before any AI is involved — de-risks the biggest unknown first.
- **Deliverable / Demo:** `tests/fixtures/ground_truth_script.py`, runnable standalone, printing the scraped status text to stdout.
- **Verification & Testing:** Run the script 10 times in a row (`for i in {1..10}; do python ground_truth_script.py; done`) and log the success rate — this becomes your Phase 9 baseline reliability number.

### Step 1.4 — FastMCP "Hello Tool" Scaffold

- **Actionable Implementation:** Build the smallest possible FastMCP server exposing one hard-coded tool function (no generation yet), confirm it starts and registers correctly.
- **Expected Outcome:** Proof that the FastMCP → Claude Desktop plumbing works before you add any generated-code complexity on top.
- **Deliverable / Demo:** A `hello_tool` MCP server that Claude Desktop can call, returning a static string.
- **Verification & Testing:** In Claude Desktop, ask "call the hello tool" and confirm the exact static string comes back — isolates MCP wiring issues from codegen issues later.

---

## PHASE 2 — Browser Recorder (Capture Layer)

**Objective:** Reliably capture one human demonstration as a structured, replayable action log.

**Exit Criteria:** A JSON log of the ground-truth demo task that, when replayed verbatim through Playwright, reproduces the same result.

### Step 2.1 — Define the Action Log JSON Schema

- **Actionable Implementation:** Design the schema up front so every downstream agent has a stable contract:
  ```json
  {
    "steps": [
      {"action": "goto", "url": "https://…", "timestamp": 0},
      {"action": "fill", "selector": "#order-id", "value": "12345", "timestamp": 1.2},
      {"action": "click", "selector": "button[type=submit]", "timestamp": 2.0},
      {"action": "extract_text", "selector": ".order-status", "timestamp": 3.5}
    ],
    "metadata": {"site": "example.com", "recorded_at": "…"}
  }
  ```
- **Expected Outcome:** A frozen (versioned) schema that Phase 3's Pattern Extractor consumes — changing it later means updating one contract, not every downstream component.
- **Deliverable / Demo:** `docs/schemas/action_log_schema.json` (JSON Schema format) + one hand-crafted example file.
- **Verification & Testing:** Validate the example file against the schema with `jsonschema` — fails loudly if a future recorder change silently breaks the contract.

### Step 2.2 — Wrap Playwright Codegen as the Recording Mechanism

- **Actionable Implementation:** Use `playwright codegen --target python -o raw_script.py <url>` under the hood, then post-process the generated `.py` script's action calls into your JSON schema (parse Playwright's own script output rather than reinventing DOM event capture — this reuses a battle-tested recorder instead of building one from scratch).
- **Expected Outcome:** A converter (`recorder/convert_codegen.py`) that turns Playwright's native script output into your structured JSON log.
- **Deliverable / Demo:** Run the converter on the Step 1.3 ground-truth flow and produce a valid JSON log automatically.
- **Verification & Testing:** Diff the auto-generated JSON log's replayed behavior against the hand-written ground-truth script's behavior — same final extracted text = pass.

### Step 2.3 — Minimal Recording UI (Start/Stop Control)

- **Actionable Implementation:** Build a thin CLI or single-page local web UI with Start/Stop buttons that shells out to `playwright codegen`, waits for the process to exit, and triggers the Step 2.2 converter automatically.
- **Expected Outcome:** A one-command (or one-click) recording experience — no manual file-juggling between "record" and "convert."
- **Deliverable / Demo:** `python -m browserbot.recorder start` opens a browser, user performs the task, closes the browser, and a `session_<timestamp>.json` file appears automatically.
- **Verification & Testing:** A person who has never seen the codebase can run the one command, perform the demo task, and produce a valid log file without being told the internal steps — usability test, not just a unit test.

### Step 2.4 — Explicit PII/Secret Scrubbing at Capture Time

- **Actionable Implementation:** Before anything is written to disk, redact `password`/`type=password` field values and any field explicitly flagged as sensitive, replacing the value with a placeholder token (`__SECRET_1__`) rather than storing it. This is called out here — not deferred to Phase 9 — because it's an NFR from Step 0.2, and it's much easier to never write the data than to scrub it after the fact.
- **Expected Outcome:** Session logs are safe to commit to a private repo or share for debugging without ever containing a real password.
- **Deliverable / Demo:** Record a login flow, inspect the resulting JSON, and confirm the password field shows `__SECRET_1__`, not the plaintext value.
- **Verification & Testing:** Unit test asserting that for every input field of `type="password"` in a recorded session, the corresponding JSON value never matches the raw typed string.

---

## PHASE 3 — Pattern Extraction & Parameterization (LLM Agent 1)

**Objective:** Turn a raw, demo-specific action log into a generalized workflow with named variables (e.g., `order_id`) instead of hard-coded values.

**Exit Criteria:** Given the ground-truth session log, the agent correctly identifies `order_id` as the only variable and everything else as fixed.

### Step 3.1 — Design the Pattern Extractor Prompt & Output Contract

- **Actionable Implementation:** Write a system prompt instructing the **local LLM (served by Ollama, e.g. `llama3.1:8b`, called through the LiteLLM/Ollama client from Step 0.4)** to read the action-log JSON and output a strict JSON object: `{"parameters": [{"name": "order_id", "example_value": "12345", "log_step_index": 1}], "fixed_steps": [...]}`. Enforce output format via a JSON schema passed in the prompt and validated on the response side (reject and retry on malformed JSON, don't hand-parse with regex) — this schema-validate-and-retry loop matters *more* here than it would with a frontier hosted model, since smaller open-weight models drift from strict JSON more often; budget for a few extra retries and consider Ollama's built-in structured-output/JSON-mode grammar constraints if your installed version supports them, which cuts malformed output substantially.
- **Expected Outcome:** A deterministic, machine-parseable contract between "raw demo" and "generalized workflow," isolating LLM unpredictability behind a strict schema boundary — this boundary is exactly what makes a smaller, free local model viable for this narrow task despite being less capable than a frontier model in open-ended use.
- **Deliverable / Demo:** `agents/pattern_extractor.py` with a `--dry-run` mode that prints the extracted parameters for a given log file, and a `--backend` flag (`ollama` default, `groq` fallback) that swaps the LLM call with no other code changes.
- **Verification & Testing:** Run against the ground-truth log 5 times; confirm `order_id` is identified as a parameter in all 5 runs (LLMs are non-deterministic, and local open-weight models can be somewhat more so than frontier hosted models — this test matters more here, not less). If the local model's pass rate is noticeably below 5/5, that's your signal to move that step to the Groq fallback rather than fighting the prompt indefinitely.

### Step 3.2 — Implement the Parameter Confirmation UX

- **Actionable Implementation:** Since the feasibility doc explicitly notes the MVP can ask the user to confirm/label variables, build a simple confirmation step: show the LLM's guessed parameters, let the user accept, rename, or add a missed one, before generation proceeds.
- **Expected Outcome:** A human-in-the-loop safety net that catches LLM misidentification without requiring a fully autonomous (and riskier) pipeline for MVP.
- **Deliverable / Demo:** A CLI prompt: `Detected parameter: order_id (example: "12345"). Confirm? [Y/n/rename]`.
- **Verification & Testing:** Deliberately feed a log where the LLM mislabels a parameter (e.g., misses a second variable) and confirm the user-confirmation step lets you correct it before it propagates to codegen.

### Step 3.3 — Handle the "No Variables" and "Multiple Variables" Edge Cases

- **Actionable Implementation:** Test the extractor against three log types: (a) zero-parameter flow (e.g., "check homepage banner text"), (b) single-parameter flow (the MVP case), (c) two-parameter flow (e.g., order ID + zip code for verification). Adjust the prompt/schema to handle a `parameters: []` array gracefully rather than assuming exactly one.
- **Expected Outcome:** The extractor doesn't silently break or hallucinate a parameter when there isn't one, and correctly returns a list (not a single object) when there are several.
- **Deliverable / Demo:** Three example logs in `tests/fixtures/` with their expected extractor output committed alongside them.
- **Verification & Testing:** Automated test asserting extractor output parameter count matches expected count for all three fixtures.

### Step 3.4 — Output the Intermediate Representation (IR)

- **Actionable Implementation:** Persist the confirmed, parameterized workflow as a versioned IR file (`workflow_spec.json`) — this is the artifact Phase 4's Code Generator actually consumes, decoupling "understanding the demo" from "writing the code."
- **Expected Outcome:** A clean handoff point: you can unit test Phase 3 and Phase 4 independently against this IR contract.
- **Deliverable / Demo:** `workflow_spec.json` for the ground-truth flow, human-readable enough that you could hand-write the equivalent Playwright script from it alone.
- **Verification & Testing:** Manually write a Playwright script purely from reading `workflow_spec.json` (no peeking at the original log) — if you can do it correctly, the IR is expressive enough for the LLM to do it too in Phase 4.

---

## PHASE 4 — Code Generation Engine (LLM Agent 2)

**Objective:** Turn the IR into a runnable Playwright script wrapped in a FastMCP server, using a template + LLM hybrid (not free-form LLM code generation, which is far less reliable).

**Exit Criteria:** Generated server, when run, produces the same result as the Step 1.3 ground-truth script.

### Step 4.1 — Build the FastMCP Server Template

- **Actionable Implementation:** Write a **static, hand-crafted Jinja2 template** for the FastMCP server (`templates/mcp_server_template/server.py.j2`) with placeholders for: tool function name, parameter list, and a slot for the Playwright step sequence. Do NOT ask the LLM to write the FastMCP boilerplate — only the templated step sequence — this is the single highest-leverage reliability decision in the whole project.
- **Expected Outcome:** A template that guarantees valid FastMCP structure regardless of what the LLM produces for the business logic slot.
- **Deliverable / Demo:** Manually fill the template with the ground-truth flow's values and confirm it runs as a real MCP server.
- **Verification & Testing:** Render the template with dummy/placeholder values and confirm the output is syntactically valid Python (`python -m py_compile generated.py`) even before real values are filled in.

### Step 4.2 — Implement the Code Generator Agent (LLM fills the template slot)

- **Actionable Implementation:** Prompt the LLM — use a **code-specialized local model here specifically** (e.g. `qwen2.5-coder:7b`/`14b` rather than a general instruction model; code-tuned models are measurably better at producing syntactically correct, constrained output, and this step benefits from that more than the Pattern Extractor did) — with the IR (`workflow_spec.json`) and ask it to emit only the Playwright step sequence as Python statements matching a constrained mini-DSL (`page.goto(...)`, `page.fill(...)`, `page.click(...)`, `page.text_content(...)`) — not arbitrary Python. Validate the output against an allow-list of permitted Playwright calls before inserting it into the template (reject anything outside the allow-list rather than executing it).
- **Expected Outcome:** Generated code that is both LLM-authored (flexible) and mechanically constrained (safe/predictable) — the allow-list is what prevents a hallucinated or malicious call from ever running.
- **Deliverable / Demo:** `agents/code_generator.py --input workflow_spec.json --output generated_tools/check_order_status/`.
- **Verification & Testing:** Static-analyze the generated file (`ast.parse` + walk the AST) to confirm every function call is on the allow-list before ever executing it — this is a security gate, not just a correctness check.

### Step 4.3 — Generate the MCP Tool Manifest

- **Actionable Implementation:** Auto-generate `mcp_tool.json` (or the FastMCP-native equivalent) with the tool name, parameter schema (types, descriptions), and a human-readable tool description string — the description is what Claude reads to decide when to call the tool, so generate it thoughtfully (e.g., "Checks the shipping status of an order on example.com given an order ID").
- **Expected Outcome:** A manifest good enough that Claude reliably picks the right tool for a natural-language request without the user needing to name the tool explicitly.
- **Deliverable / Demo:** Manifest file + a side-by-side: user says "did my order ship?" and Claude selects `check_order_status` unprompted.
- **Verification & Testing:** Test the manifest description against 5 paraphrased user requests ("is my package on its way", "order status please", etc.) and confirm Claude selects the correct tool for all 5 — a weak description is a common, invisible failure mode.

### Step 4.4 — First Full Codegen Run (Log → Server, Zero Manual Edits)

- **Actionable Implementation:** Run the entire Phase 2→3→4 pipeline back-to-back on the ground-truth recorded session with no manual intervention beyond the Phase 3.2 parameter confirmation, and start the resulting server.
- **Expected Outcome:** The first true "record once → get a tool" milestone — this is the moment the core thesis of the project is proven or disproven.
- **Deliverable / Demo:** A screen recording: record → confirm parameter → server starts → server called directly (curl or a test client) → correct order status returned.
- **Verification & Testing:** Run this full pipeline 5 times end-to-end and log the success rate — this is your first real reliability number for the *generated* (not hand-written) path, distinct from the Step 1.3 baseline.

---

## PHASE 5 — Validator Agent & Dry-Run Harness

**Objective:** Never hand a broken tool to the user (or to Claude) — auto-verify generated code before it's considered "done."

**Exit Criteria:** A generated tool that fails at runtime is automatically caught and flagged *before* packaging, not discovered live during a demo.

### Step 5.1 — Build the Dry-Run Harness

- **Actionable Implementation:** Write a harness that imports the generated tool function directly (not through MCP/Claude) and calls it with the example parameter value captured back in Phase 3, in a headless browser, capturing stdout/stderr/exceptions and a final screenshot.
- **Expected Outcome:** A fast (~seconds), Claude-independent way to sanity-check generated code before it's ever exposed as an MCP tool.
- **Deliverable / Demo:** `agents/validator.py --tool generated_tools/check_order_status/` printing PASS/FAIL plus a screenshot on failure.
- **Verification & Testing:** Feed the harness a deliberately broken generated script (bad selector) and confirm it reports FAIL with a useful error, not a silent hang.

### Step 5.2 — Auto-Trigger Validation After Every Generation

- **Actionable Implementation:** Wire the Phase 4 pipeline so that the Validator runs automatically immediately after codegen, before the tool is marked "ready to install."
- **Expected Outcome:** No generated tool ever reaches the packaging/install step without having been executed at least once successfully.
- **Deliverable / Demo:** The end-to-end CLI (`browserbot generate`) now ends with either `✅ Ready to install` or `❌ Validation failed — see report.html`.
- **Verification & Testing:** Confirm via a code review / integration test that there is no code path from "codegen complete" to "install" that skips the validator call.

### Step 5.3 — Basic Failure-Feedback Loop (Retry with Error Context)

- **Actionable Implementation:** On validator failure, feed the error message and stack trace back into the Code Generator agent's prompt as additional context ("the previous attempt failed with X — fix it") and retry generation once or twice before surfacing the failure to the user.
- **Expected Outcome:** A meaningful chunk of transient LLM mistakes (wrong selector guess, off-by-one step ordering) self-correct without user intervention — this is a lightweight precursor to the "self-healing" concept from the research doc, scoped down to something achievable in MVP.
- **Deliverable / Demo:** Deliberately trigger a first-attempt failure (e.g., ambiguous selector) and show the second attempt succeeding automatically.
- **Verification & Testing:** Cap and log retry counts; confirm the system gives up gracefully (clear error to user) after 2 failed attempts rather than looping indefinitely. With a local model this protects against runaway generation *time* rather than dollar cost (a 7B model on CPU-only hardware can take tens of seconds per call, so an unbounded retry loop is a real time sink, not just a cost risk) — and if the Groq fallback is ever active for this step, the same cap also protects against burning through its free-tier rate limit.

---

## PHASE 6 — MCP Packaging & Claude Desktop Integration

**Objective:** The generated tool is not just "runnable" but installable into a real MCP host and callable through natural language.

**Exit Criteria:** Asking Claude Desktop the demo question in plain English produces the correct real-world answer.

### Step 6.1 — Package as an Installable MCP/Desktop Extension

- **Actionable Implementation:** Use the `mcpb` CLI (or current equivalent — verify against up-to-date Anthropic docs, since packaging tooling evolves) to bundle the generated server directory into an installable extension package, including the manifest from Step 4.3.
- **Expected Outcome:** A single artifact (`.mcpb` or directory + install script) a user can add to Claude Desktop without manually editing config files.
- **Deliverable / Demo:** The packaged extension file for `check_order_status`.
- **Verification & Testing:** Install on a second, clean Claude Desktop profile (or after fully removing local config) to confirm the packaging is self-contained, not dependent on leftover state from development.

### Step 6.2 — Local Install & Registration Test

- **Actionable Implementation:** Install the packaged tool into Claude Desktop through its normal extension-install flow (not developer shortcuts) to test the real user path.
- **Expected Outcome:** The tool appears in Claude Desktop's available tools/extensions list with the correct name and description.
- **Deliverable / Demo:** Screenshot of Claude Desktop's extension list showing `check_order_status` installed.
- **Verification & Testing:** Restart Claude Desktop entirely and confirm the tool persists across restarts (catches "works until you close the app" bugs).

### Step 6.3 — Natural-Language Invocation Test

- **Actionable Implementation:** In a fresh Claude Desktop chat, type the exact demo-script question ("Claude, did my order ship?") with no additional hints, and observe whether Claude selects and calls the tool correctly.
- **Expected Outcome:** This is the literal "wow moment" from the research doc — proof the whole pipeline works from a cold start.
- **Deliverable / Demo:** Screen recording of the exact question → Claude invoking the tool → correct real answer, unedited.
- **Verification & Testing:** Repeat with 3 paraphrased questions to confirm reliability isn't a fluke of one specific phrasing (ties back to Step 4.3's verification).

### Step 6.4 — Result Formatting & Error Surfacing Back to Claude

- **Actionable Implementation:** Ensure the tool's return value is structured text (not raw HTML/JSON dumps) so Claude can present it conversationally, and ensure runtime errors (site down, selector not found) return a clear error message rather than a raw Python traceback.
- **Expected Outcome:** Both the happy path and the failure path read naturally in the chat, rather than the failure path dumping a stack trace into the conversation.
- **Deliverable / Demo:** Trigger a deliberate failure (e.g., point the tool at an unreachable URL) and confirm Claude relays a sensible "I couldn't check the order status right now" instead of raw exception text.
- **Verification & Testing:** Unit test the tool function's return contract: success returns `{"status": "ok", "result": str}`, failure returns `{"status": "error", "message": str}` — never an unhandled exception escaping to the MCP layer.

---

## PHASE 7 — Orchestration UI & End-to-End UX Polish

**Objective:** Turn the phase-by-phase pipeline (record → extract → generate → validate → package → install) into one coherent user-facing flow.

**Exit Criteria:** A person who has never seen the code can go from "nothing" to "installed, working Claude tool" using only the UI, in under 5 minutes.

### Step 7.1 — Build the Unified Flow UI

- **Actionable Implementation:** Build a minimal local web page (Flask/FastAPI serving a simple HTML/JS page, or a small React app) with 4 visible stages mirroring the Step 0.5 state diagram: Record → Confirm Parameters → Generate & Validate → Install. Each stage's backend call reuses the CLI functions already built in Phases 2–6 — the UI is a thin wrapper, not new logic.
- **Expected Outcome:** One coherent tool instead of 6 separate CLI scripts the user has to remember to run in order.
- **Deliverable / Demo:** A working local webpage demoing the full flow live, start to finish.
- **Verification & Testing:** Time a full run through the UI end-to-end; confirm it matches or beats the Step 0.2 NFR (≤ 3 minutes generation budget).

### Step 7.2 — Progress & Transparency Visualization

- **Actionable Implementation:** Surface what's happening at each stage — show the raw action count after recording, the detected parameters for confirmation, a live log/screenshot during validation — directly addressing the research doc's point that users need to trust "it's doing exactly what I taught it."
- **Expected Outcome:** The system reads as transparent and inspectable, not a black-box "magic" tool a cautious user wouldn't trust with their browser.
- **Deliverable / Demo:** During the Generate & Validate stage, the UI streams the validator's screenshot/log in near real-time rather than showing a blank spinner.
- **Verification & Testing:** User-test with someone unfamiliar with the project; ask afterward "did you understand what it was doing at each step?" — a "no" here is a UX bug, not a technical one.

### Step 7.3 — Error States & Manual Override

- **Actionable Implementation:** For every failure mode surfaced in Phase 5 (validation failed after retries) and Phase 6 (install failed), design an explicit UI state with a clear next action (e.g., "view generated code," "retry," "edit parameter and regenerate") rather than a dead end.
- **Expected Outcome:** The tool degrades gracefully instead of leaving the user staring at a spinner or a raw error.
- **Deliverable / Demo:** Deliberately fail a generation (bad site) and walk through the resulting UI error state end-to-end.
- **Verification & Testing:** Confirm every failure path identified in the Phase 5/6 risk register has a corresponding, tested UI state — no silent failures.

---

## PHASE 8 — Robustness, Generalization & Self-Healing

**Objective:** Move past "works on the one demo site" toward the resilience claims in the research doc, without over-scoping into a full multi-site platform.

**Exit Criteria:** The pipeline succeeds on a second, previously-unseen site of similar structure, and demonstrably recovers from at least one class of site-change failure.

### Step 8.1 — Robust Selector Strategy

- **Actionable Implementation:** Update the Step 4.2 allow-list and Code Generator prompt to prefer Playwright's role/text/label-based locators (`get_by_role`, `get_by_text`, `get_by_label`) over brittle CSS/XPath selectors, matching the research doc's explicit mitigation for "site variability."
- **Expected Outcome:** Generated scripts survive minor DOM/CSS changes (class name churn) that would break naive `document.querySelector`-style automation.
- **Deliverable / Demo:** Before/after: show a selector-based script breaking after a cosmetic HTML change, and the role/text-based version surviving the same change.
- **Verification & Testing:** Maintain a small "mutation test" fixture — a copy of the demo site's HTML with class names renamed but structure/text intact — and confirm the generated script still passes against it.

### Step 8.2 — Second-Site Generalization Test

- **Actionable Implementation:** Run the entire pipeline (record → extract → generate → validate) on a second, structurally similar but distinct site (e.g., a different mock order-tracking page) without changing any pipeline code.
- **Expected Outcome:** Evidence the approach generalizes rather than being secretly hard-coded to one site's quirks — directly answers the research doc's "moderate-high MVP feasibility, but generalization is the hard part" concern.
- **Deliverable / Demo:** Two working tools (`check_order_status_site_a`, `check_order_status_site_b`) generated from the same unmodified codebase.
- **Verification & Testing:** Confirm zero pipeline-code diffs were needed between the two runs — any required code change here is a signal the abstraction in Phase 3/4 was too specific to site A.

### Step 8.3 — Basic Self-Healing on Detected Drift

- **Actionable Implementation:** Extend the Step 5.3 retry loop into a standing capability: when a *previously validated* tool starts failing at runtime (not generation time), automatically re-run the Pattern Extractor + Code Generator (same local Ollama-served models from Step 0.4) against a fresh recording/DOM snapshot of the same site, and flag the tool for re-validation — a scoped-down version of the research doc's "Moss"-style self-healing concept. Because the LLM backend is local and free, self-healing can trigger as often as needed with zero marginal cost — a real advantage over a pay-per-call API for a feature that's inherently unpredictable in frequency.
- **Expected Outcome:** A tool that breaks after a site redesign has an automatic recovery path, rather than silently failing forever.
- **Deliverable / Demo:** Simulate drift by modifying the mock demo site's markup after a tool is already installed, then trigger the self-heal path and show the tool working again.
- **Verification & Testing:** Confirm the self-heal path re-runs the full Phase 5 validator before re-marking the tool healthy — never auto-promote unvalidated "fixed" code.

### Step 8.4 — Network & Timing Resilience

- **Actionable Implementation:** Add explicit waits (`wait_for_load_state("networkidle")`, retry-with-backoff around navigation/click steps) to the code generator's template rather than fixed `sleep()` calls, addressing the research doc's "dynamic pages" risk.
- **Expected Outcome:** Generated tools tolerate normal network jitter and slow-loading pages instead of racing the DOM.
- **Deliverable / Demo:** Run the generated tool against the demo site under artificially throttled network conditions (Chrome DevTools network throttling) and confirm it still succeeds, just slower.
- **Verification & Testing:** Run 10 iterations under throttled conditions and confirm the success rate doesn't meaningfully drop versus the Step 4.4 baseline.

---

## PHASE 9 — Security, Privacy & QA Hardening

**Objective:** Make the "safe, local-first, no-PII-persisted" claims from the research doc actually verifiable, not just asserted.

**Exit Criteria:** A documented audit trail proving no credentials/PII are ever persisted, plus a full regression suite passing.

### Step 9.1 — Credential/PII Audit

- **Actionable Implementation:** Grep every artifact type the pipeline produces (`session_*.json`, `workflow_spec.json`, generated `.py` files, validator screenshots/logs) for common secret patterns and for the literal test password/PII used in your ground-truth recording.
- **Expected Outcome:** Written confirmation that the Step 2.4 scrubbing actually holds across every downstream artifact, not just the raw log.
- **Deliverable / Demo:** An audit script (`scripts/pii_audit.py`) plus its output log run against a full sample pipeline run.
- **Verification & Testing:** The audit script exits non-zero (fails the build) if it finds the test secret anywhere in the generated artifact tree — wire this into your test suite so it can't silently regress.

### Step 9.2 — Generated-Code Sandboxing / Permission Review

- **Actionable Implementation:** Confirm the Step 4.2 allow-list is still enforced at generation time (no arbitrary `subprocess`, `os.system`, `eval`, or filesystem writes outside the tool's own directory are ever permitted in generated code), and run generated tools with a restricted OS user or container where feasible. Additionally, confirm the Groq fallback API key (if ever used) is loaded only from a git-ignored `.env`/environment variable and never embedded in any generated tool artifact — the *generated tools themselves* must never make outbound LLM calls at runtime regardless of which backend built them, since runtime invocation was never supposed to touch an LLM at all (that's the whole "compiled once, runs deterministically forever" pitch from the research doc).
- **Expected Outcome:** A generated tool cannot do anything beyond drive a browser and return text, even if the LLM were to hallucinate something dangerous into the code slot, and no API credential of any kind ever ships inside a generated package.
- **Deliverable / Demo:** Deliberately prompt-inject a malicious instruction into a fake action log (e.g., "also run `rm -rf`") and confirm the allow-list rejects it at generation time.
- **Verification & Testing:** This adversarial test becomes a permanent regression test — re-run it whenever the Code Generator prompt changes.

### Step 9.3 — Full Regression Test Suite

- **Actionable Implementation:** Assemble everything built incrementally in Phases 2–8 (schema validation, extractor fixture tests, allow-list AST checks, validator harness, mutation tests, second-site test, PII audit) into one runnable suite (`pytest`), plus the 10-run reliability loop from Step 1.3/4.4 automated as a scheduled check.
- **Expected Outcome:** A single command (`pytest` or `make test`) that gives a pass/fail verdict on the entire system's health.
- **Deliverable / Demo:** CI badge or local `make test` output showing green across all suites.
- **Verification & Testing:** Intentionally break one component (e.g., corrupt the allow-list) and confirm the suite catches it — a test suite that can't fail isn't verifying anything.

### Step 9.4 — Latency & Reliability Benchmark Against NFRs

- **Actionable Implementation:** Run the full record→install pipeline and the runtime invocation path N times (N ≥ 10) each, logging timing and pass/fail, and compare directly against the Step 0.2 NFR table.
- **Expected Outcome:** A data-backed answer to "does this meet the targets we set," not a subjective "feels fine."
- **Deliverable / Demo:** `docs/benchmark_report.md` with actual measured numbers next to the original targets.
- **Verification & Testing:** Any NFR missed by a wide margin gets its own follow-up task before Phase 10 — don't launch on an NFR you know you're failing.

---

## PHASE 10 — Documentation, Demo Packaging & Launch

**Objective:** Package the technical result into the "wow" artifact the research doc identifies as the actual point of this project — a shareable, recruiter-legible demo.

**Exit Criteria:** A recorded demo + written narrative ready to post, plus documentation good enough that you (or anyone) could rebuild this from scratch in 6 months.

### Step 10.1 — Auto-Generated Per-Tool Documentation

- **Actionable Implementation:** Have the Phase 4 pipeline auto-emit a `README.md` per generated tool (function signature, parameter description, example invocation, "how it was taught" note) — this was explicitly listed as a required artifact in the research doc's "Generated Artifacts" section.
- **Expected Outcome:** Every generated tool is self-documenting without extra manual work per tool.
- **Deliverable / Demo:** `generated_tools/check_order_status/README.md`, readable by someone who's never seen BrowserBot.
- **Verification & Testing:** Hand the README (only) to someone and ask them to explain what the tool does and how to call it — no verbal context allowed.

### Step 10.2 — Project-Level Documentation

- **Actionable Implementation:** Consolidate `docs/requirements.md`, `docs/nfr.md`, `docs/architecture/`, `docs/risk_register.md`, and `docs/benchmark_report.md` into a top-level `README.md` with a clear "Quickstart" section.
- **Expected Outcome:** A GitHub-ready repo that reads as a serious engineering project, not just a demo script — this is what recruiters and technical reviewers will actually open.
- **Deliverable / Demo:** The finished repo README, rendered on GitHub (check formatting, image embeds, code block rendering).
- **Verification & Testing:** Clone the repo fresh and follow only the Quickstart section, timing how long it takes to get the demo running — if it doesn't work as written, the docs aren't done.

### Step 10.3 — Demo Script & Recording

- **Actionable Implementation:** Write and rehearse a tight demo script matching the research doc's suggested hook ("I recorded myself checking an order once, and now Claude can just do it"), record a clean screen-capture of: record → confirm → generate → Claude invocation → correct answer, trimmed to under 60 seconds.
- **Expected Outcome:** A polished, low-flakiness demo asset — the single artifact most likely to actually be watched by a recruiter.
- **Deliverable / Demo:** Final `demo.mp4` (or `.gif`) file.
- **Verification & Testing:** Watch the recording start to finish as a first-time viewer would, with sound off (many viewers scroll with muted video) — confirm on-screen text/captions carry the story without narration.

### Step 10.4 — Launch Package (LinkedIn/Portfolio)

- **Actionable Implementation:** Draft the post using the research doc's suggested hook and structure (problem → 30-second demo → what makes it novel → link to repo), and prepare a one-paragraph project summary for a resume/portfolio site.
- **Expected Outcome:** A ready-to-publish package, not just a working project sitting unannounced in a repo.
- **Deliverable / Demo:** Final drafted post text + attached demo video, staged and ready to publish.
- **Verification & Testing:** Have one outside reader review the post copy for clarity before publishing — confirm the "wow" lands without requiring them to already understand MCP or agentic AI.

---

## Cross-Phase Notes

- **Sequencing discipline:** Phases 2→6 form the true critical path (recorder → extractor → generator → validator → MCP packaging). Phases 7–10 can be lightly parallelized once Phase 6 is stable, but don't start UI polish (Phase 7) before the underlying pipeline (Phase 6) actually works — polishing an unreliable core wastes the time budget the research doc already flags as tight.
- **Buffer allocation:** Per the risk register (Step 0.3), Phases 3, 4, and 8 are where LLM unpredictability and site-variability risk concentrate — if the timeline slips, absorb the slip there, not by cutting Phase 9 (security/QA) or Phase 5 (validation), since those protect the demo from failing live.
- **Definition of "MVP done":** You can stop confidently after Phase 6 for a minimum viable "wow" demo. Phases 8–9 are what separate a fragile one-off demo from something you can show a technical interviewer and defend under follow-up questions.
- **Budget discipline:** the entire LLM backend (Pattern Extractor, Code Generator, and self-healing) runs on Ollama at $0 marginal cost by default, with Groq's free tier documented purely as a fallback for weak hardware — also $0. No step in this plan, from Phase 0 through Phase 10, requires a credit card or a paid API account to complete end-to-end. If you later *want* to swap in a frontier hosted model for quality reasons, the LiteLLM abstraction from Step 0.4 makes that a config change, not a re-architecture — but it's an upgrade to make deliberately later, not a dependency to build around now.
