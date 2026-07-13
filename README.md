# BrowserBot

> **Record once. Auto-generate a reusable MCP tool. Invoke via Claude.**

BrowserBot records a single browser workflow and automatically generates a
validated, installable MCP (Model Context Protocol) tool that Claude Desktop
can invoke through natural language.

---

## Quick Demo

```
User: "Claude, did my order ship?"

Claude identifies the generated BrowserBot MCP tool
  → BrowserBot launches Chromium
  → Logs into the demo site
  → Enters the Order ID
  → Retrieves the shipment status
  → Returns: "Order #12345 shipped via FedEx. Expected delivery: July 14."
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Product Requirements](docs/1.%20ProductRequirement.md) | Problem statement, target user, demo scenario, scope |
| [Non-Functional Requirements](docs/2.%20NonFunctionalRequirements_%26_SuccessMetrics.md) | Performance, reliability, privacy, cost targets |
| [Risk Register](docs/3.%20Risks%20%26%20Assumptions.md) | Prioritised risks, mitigations, assumptions |
| [Technology Stack](docs/4.%20Tech-Stack.md) | Stack decisions, dependency policy, rationale |
| [System Design](docs/5.%20High%20Level%20System%20Design.md) | Architecture, components, data flow, principles |
| [Execution Plan](BrowserBot_Execution_Plan_updated.md) | Phase-by-phase build plan (authoritative) |

### Architecture Diagrams

Diagrams live in [`diagrams/`](diagrams/).

| Diagram | File |
|---------|------|
| Container Architecture | [container_architecture.svg](diagrams/container_architecture.svg) |
| Data Flow (L0) | [dfd_l0.png](diagrams/dfd_l0.png) |
| Data Flow (L1) | [dfd_l1.png](diagrams/dfd_l1.png) |
| Sequence: Record & Generate | [sequence_diagram-record&generate.png](diagrams/sequence_diagram-record%26generate.png) |
| Sequence: Runtime Invocation | [state_diagram-runtime_invocation.png](diagrams/state_diagram-runtime_invocation.png) |
| Recording Session Lifecycle | [seq_diagram-recording_session_lifecycle.png](diagrams/seq_diagram-recording_session_lifecycle.png) |
| Deployment Diagram | [deployment_diagram.png](diagrams/deployment_diagram.png) |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Browser Automation | Playwright (Chromium) |
| LLM Backend (primary) | Ollama — local, $0, fully offline |
| LLM Backend (fallback) | Groq free tier — $0, no credit card |
| LLM Abstraction | LiteLLM |
| MCP Framework | FastMCP |
| Templating | Jinja2 |
| Validation | Python AST + jsonschema |
| Testing | pytest |

No paid API account is required. The default configuration runs entirely offline.

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (dependency management)
- [Ollama](https://ollama.com) (local LLM service)
- Claude Desktop (runtime MCP host — no API key needed)

### Install

```bash
# Clone
git clone <repo-url>
cd BrowserBot

# Create virtual environment and install dependencies
uv sync

# Install Chromium browser
uv run playwright install chromium

# Pull an Ollama model (choose per your hardware — see docs/4. Tech-Stack.md)
ollama pull qwen2.5-coder:7b    # Code Generator
ollama pull llama3.1:8b         # Pattern Extractor
```

### Verify environment

```bash
python scripts/verify_env.py
```

### Verify Playwright installation

```bash
python -m browserbot.recorder --demo
```

Expected output: `✅  Playwright smoke-test passed`

---

## Project Structure

```
browserbot/
  recorder/           Phase 2  — capture layer
  agents/
    pattern_extractor/  Phase 3  — action log → workflow spec (LLM)
    code_generator/     Phase 4  — workflow spec → Playwright script (LLM + template)
    validator/          Phase 5  — generated script validation
  templates/
    mcp_server_template/  Phase 4  — Jinja2 FastMCP server template
  config/             Project-wide settings
  logging/            Structured JSON logging
  models/             Pydantic data models for pipeline artifacts
  orchestrator/       Pipeline coordinator
  action_logger/      Recording normaliser
  cli/                Typer CLI (Phase 7)
  packaging/          MCP package bundler (Phase 6)
  runtime/            Generated tool runtime (Phase 6)
  utils/              Shared utilities

tests/
  fixtures/
    ground_truth_script.py  Step 1.3 hand-written baseline automation

scripts/
  verify_env.py     Step 1.1 environment verification

generated_tools/    Output directory (git-ignored)
docs/               Project documentation
diagrams/           Architecture diagrams (PNG/SVG + Mermaid source)
context/            Per-run implementation notes
```

---

## Build Status

| Phase | Status |
|-------|--------|
| Phase 0 — Planning & Architecture | ✅ Complete |
| Phase 1 — Environment & Scaffolding | 🔄 In Progress |
| Phase 2 — Browser Recorder | ⏳ Pending |
| Phase 3 — Pattern Extractor | ⏳ Pending |
| Phase 4 — Code Generator | ⏳ Pending |
| Phase 5 — Validator | ⏳ Pending |
| Phase 6 — MCP Packaging | ⏳ Pending |
| Phase 7 — Orchestration UI | ⏳ Pending |
| Phase 8 — Robustness | ⏳ Pending |
| Phase 9 — Security & QA | ⏳ Pending |
| Phase 10 — Demo & Launch | ⏳ Pending |
