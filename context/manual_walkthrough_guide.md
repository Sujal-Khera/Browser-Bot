# BrowserBot — Manual Walkthrough & Testing Playbook

This playbook provides step-by-step instructions to manually execute, verify, and understand every phase of BrowserBot. Follow this guide to set up the environment, run the recording pipeline, parameterize workflows, generate tools, validate code, package results, and register/test tools with Claude Desktop.

---

## Prerequisites & System Setup

Before executing any phase, ensure the baseline environment is ready.

### 1. Python & Dependencies
1. Open PowerShell in the project root directory.
2. Activate the virtual environment:
   ```powershell
   .venv\Scripts\activate
   ```
3. Install/verify all packages:
   ```powershell
   pip install -r requirements.txt
   ```
4. Install Playwright browser binaries:
   ```powershell
   playwright install chromium
   ```

### 2. Ollama Setup (Local LLM)
BrowserBot uses Ollama by default for fully local, zero-budget pattern extraction and code generation.
1. Download and install Ollama from [ollama.com](https://ollama.com).
2. Start the Ollama background service (or run `ollama serve` in a separate terminal).
3. Pull the required models:
   ```powershell
   # For Step 3 (Pattern Extractor)
   ollama pull llama3.1:8b
   
   # For Step 4 (Code Generator)
   ollama pull qwen2.5-coder:7b
   ```

### 3. Groq API Setup (Optional Fallback)
If your hardware is too slow to run local models:
1. Get a free API key from [console.groq.com](https://console.groq.com).
2. Create a `.env` file in the repository root:
   ```env
   BROWSERBOT_LLM_BACKEND=groq
   GROQ_API_KEY=your_actual_api_key_here
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

---

## Phase-by-Phase Walkthrough

---

### Phase 1 — Environment & Baseline Ground Truth

Verify that your system dependencies, Playwright, and baseline benchmark scripts are running correctly.

#### 1. Run Environment Diagnostics
Ensure all files, templates, and environment requirements are met:
```powershell
python scripts/verify_env.py --no-ollama
```
* **Expected Outcome:** Prints `6/6 checks passed`.

#### 2. Run Playwright Smoke Test
Verify that Playwright can launch chromium and navigate:
```powershell
python -m browserbot.recorder --demo
```
* **Expected Outcome:** Opens a browser temporarily (or in background) and prints page metadata.

#### 3. Run and Understand the Ground Truth Script
Understand the baseline tracking script that the automation mimics.
1. Inspect the hand-written baseline at [ground_truth_script.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/tests/fixtures/ground_truth_script.py).
2. Run it manually:
   ```powershell
   python tests/fixtures/nobuycart_tracking_script.py
   ```
* **Expected Outcome:** A chromium browser opens, enters a mock tracking ID (`NBC-2026-E3ZXJC`) on `nobuycart.com/tracking/`, submits the form, reads the timeline, and closes.

---

### Phase 2 — Browser Recorder & PII Scrubber

Capture browser steps interactively, validate the resulting action log schema, and verify PII sanitization.

#### 1. Record a New Workflow Session
Start the recording browser on the demo tracking site:
```powershell
python -m browserbot.recorder start https://nobuycart.com/tracking/
```
1. Perform actions on the page:
   - Click the input field.
   - Type `NBC-2026-E3ZXJC`.
   - Click "Show fake timeline".
   - Highlight or click the header "Final status: happily never".
2. Close the browser window.
* **Expected Outcome:** A timestamped action log JSON is generated under `workflows/sessions/session_TIMESTAMP.json`.

#### 2. Inspect the Action Log
Open the newly generated action log file. Note:
- Actions are recorded sequentially (`step_index` = 0, 1, 2...).
- The input value `NBC-2026-E3ZXJC` has been automatically parsed.
- Any selector matching sensitive patterns (like password, token, etc.) would be automatically redacted by the scrubber to `__SECRET_1__`.
- You can run the scrubber tests to verify security mappings:
  ```powershell
  python -m pytest tests/test_scrubber.py -v
  ```

---

### Phase 3 — Pattern Extractor & Confirmer UX

Analyze the action log with the LLM to classify dynamic parameters versus fixed steps, and confirm inputs interactively.

#### 1. Run the Pattern Extractor in Dry-Run (Auto-Accept)
This bypasses the LLM and flags fill steps as parameters automatically:
```powershell
python -m browserbot.agents.pattern_extractor --dry-run --yes --output workflows/sessions/workflow_spec_nobuycart.json tests/fixtures/extractor_test_session.json
```
* **Expected Outcome:** Generates a clean Intermediate Representation (IR) spec at `workflows/sessions/workflow_spec_nobuycart.json`.

#### 2. Run Interactively (With Ollama or Groq)
Run the real extractor and handle parameters manually:
```powershell
python -m browserbot.agents.pattern_extractor workflows/sessions/session_20260716T140748.json
```
The CLI will pause for confirmation. Use these hotkeys:
* `Enter` — Accept the proposed parameter classification and name.
* `r` — Rename parameter (e.g., change `fake_order_code` to `order_id`).
* `o` — Toggle parameter as optional (`is_optional: true`).
* `n` — Reject step as a parameter.
* At the end, you can choose to manually add any parameter that the LLM missed.

---

### Phase 4 — Deterministic Code Generation

Generate the standalone FastMCP Python script and standard manifest schema directly from the workflow spec IR.

#### 1. Run Code Generator in Dry-Run
Create a tool server from the workflow spec using the template generator:
```powershell
python -m browserbot.agents.code_generator --dry-run --input workflows/sessions/workflow_spec_nobuycart.json --output generated_tools/nobuycart_tracker
```
* **Expected Outcome:** Writes `server.py` and `mcp_tool.json` under `generated_tools/nobuycart_tracker/`.

#### 2. Run AST DSL Validation Checks
Verify that the security validator successfully screens dangerous system statements:
```powershell
python -m pytest tests/test_code_generator.py -v
```
* **Key Concept:** The DSL validator visitor blocks imports, definitions, and functions outside the approved Playwright sequence (e.g. blocking `subprocess`, `os`, custom files).

---

### Phase 5 — Validation Pipeline & Bounded Retries

Execute validation checks to verify that the generated code is fully functional.

#### 1. Trigger Verification Manually
Run the generation pipeline end-to-end. This automatically spins up a dry-run harness, dynamically imports the generated module, executes the script, and verifies its output:
```powershell
python -m browserbot.agents.code_generator --input workflows/sessions/workflow_spec_nobuycart.json --output generated_tools/nobuycart_tracker
```
* **Expected Outcome:** The console prints passing states for all 4 stages: File Existence, Python Compilation, Import Check, and Runtime Dry-Run.

#### 2. Run a Headed (Visible) Dry-Run Validation
To watch the generated code execute visually:
1. In PowerShell, temporarily set headless to false:
   ```powershell
   $env:BROWSERBOT_HEADLESS="false"
   ```
2. Re-run the validation pipeline:
   ```powershell
   python -m browserbot.agents.code_generator --input workflows/sessions/workflow_spec_nobuycart.json --output generated_tools/nobuycart_tracker
   ```
3. Set headless mode back to true when finished:
   ```powershell
   $env:BROWSERBOT_HEADLESS="true"
   ```

---

### Phase 6 — Packaging, Claude Installation & Invocation

Package the validated tool and integrate it directly with the Claude Desktop application.

#### 1. Package the Validated Server
Bundle the script, manifests, requirements, and helper scripts:
```powershell
python -m browserbot.agents.packager --input generated_tools/nobuycart_tracker --output packages/execute_nobuycart_com
```
* **Expected Outcome:** Compiles the package under `packages/execute_nobuycart_com/` and prints confirmation that all installation verification checks passed.

#### 2. Review the Package Artifacts
Navigate to `packages/execute_nobuycart_com/` and inspect:
* `browserbot_package.json` — The integration metadata and Claude config command arguments.
* `install.ps1` — Helper installation instructions showing the config JSON block.

#### 3. Register Tool with Claude Desktop (Step 6.3)
1. Run a dry-run to preview what will be written:
   ```powershell
   python -m browserbot.runtime register --package packages/execute_nobuycart_com --dry-run
   ```
2. Commit the registration (this writes to your system's Claude Desktop config file):
   ```powershell
   python -m browserbot.runtime register --package packages/execute_nobuycart_com
   ```
   *Note: A backup of your config is saved automatically next to your configuration file (suffix `.bak.json`).*

#### 4. Natural-Language Invocation Test
1. Close and **restart Claude Desktop** completely.
2. In a fresh chat window, ask Claude in plain English:
   > *"Check my order status for order code NBC-2026-E3ZXJC"*
3. Watch the browser run in the background (or foreground if `BROWSERBOT_HEADLESS="false"` is set).
4. Claude should reply with clean, conversational prose formatted by the formatting engine:
   ```
   The workflow completed successfully.
   
   • Final status: happily never
   ```

#### 5. Verify the Clean Error Surfacing Path (Step 6.4)
1. Open the packaged server script: [packages/execute_nobuycart_com/server.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/packages/execute_nobuycart_com/server.py).
2. Change the URL in line 49 to an invalid URL:
   ```python
   await page.goto("https://this-site-does-not-exist.invalid/")
   ```
3. In Claude Desktop, ask again:
   > *"Check my order status for order code NBC-2026-E3ZXJC"*
4. **Expected Outcome:** Claude should reply with a clean conversational message (e.g. *"I wasn't able to complete the workflow right now. Reason: net::ERR_NAME_NOT_RESOLVED..."*), rather than throwing a raw Python stack trace or crashing the MCP connection.
5. Revert the URL change in `server.py` when finished testing.

#### 6. Clean Up & Unregister
To remove the tool from Claude Desktop:
```powershell
python -m browserbot.runtime unregister --tool execute_nobuycart_com
```

---

## General Troubleshooting

* **PowerShell script execution policy error:**
  If PowerShell blocks running any script, set the execution policy to bypass for your session:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
  ```
* **Port / Server Conflicts:**
  If Claude Desktop hangs or fails to call the tool, ensure you don't have another instance of `server.py` running in the background. Kill any rogue Python processes.
* **LLM generation is slow:**
  When running locally on CPU-only hardware, LLM steps can take 30–60 seconds. Set `BROWSERBOT_LLM_MAX_RETRIES=1` in your environment to iteration-test faster.
