# Design Brief: Collapsible Developer Console Drawer

This design brief defines the layout, interactions, states, and visual direction for the collapsible bottom console drawer in the BrowserBot Web UI Wizard.

---

## 1. Visual Direction Probe Mockup

Below is the visual mockup generated to test the aesthetic and layout lane ("The Monochromatic Lab") for the expanded console:

![Developer Console Mockup](file:///C:/Users/hp/.gemini/antigravity-ide/brain/116e3f8c-b0b9-4fa0-b8bf-4a26bc090cb4/developer_console_mockup_1784394996105.png)

---

## 2. Feature Summary
A collapsible bottom-docked terminal drawer that provides real-time, high-fidelity log telemetry from the FastAPI backend and browser subprocesses (such as Playwright steps) during tool extraction and dry-run validation. It acts as an developer-focused companion to the main guided stepper.

## 3. Primary User Action
* **Toggle & Inspect**: Expanding the console to diagnose step-by-step progress or analyze validation errors without interrupting the wizard path.

## 4. Design Direction
* **Color Strategy**: Restrained monochrome (deep slate/charcoal backgrounds, high-contrast text, minimal light border strokes).
* **Theme Scene Sentence**: *A developer monitors high-density Playwright execution events on a late-night workstation, focusing on readable status markers under dark-mode constraints.*
* **Named Anchor References**: Cursor's bottom terminal pane, GitHub Actions live log viewer, and VS Code's output drawer.

## 5. Scope
* **Fidelity**: High-fidelity UI mockup and code-ready components.
* **Breadth**: Single persistent component embedded globally in the wizard shell layout.
* **Interactivity**: Fully interactive prototype featuring height resizing, auto-scrolling toggle, and collapsible drawer.
* **Time Intent**: Polish until it is production-ready.

## 6. Layout Strategy
* Docked at the bottom of the main wizard container, spanning 100% of the workspace width.
* Fixed headers containing action controls (e.g., Clear, Auto-scroll check, Collapse button) and execution duration timers.
* Monospace grid layout for log lines, pairing each event line with a timestamp and a colored status indicator (success/info/error).

## 7. Key States
* **Collapsed**: A thin footer bar showing a pulse indicator (amber during runs, green on success, red on error), a count of warning/error logs, and an expand toggle.
* **Running (Streaming)**: Streams live logs, with auto-scroll active, keeping the newest lines in view.
* **Scroll Paused**: Triggered when the user scrolls up to read a previous event line; disables auto-scroll temporarily until they click a "Resume Auto-scroll" banner.
* **Error Triggered**: Auto-expands the drawer to height `300px` to instantly bubble up error details when any compilation or dry-run step fails.

## 8. Interaction Model
* **Click to Toggle**: Clicking the drawer header expands/collapses it.
* **Vertical Resize**: Dragging the top border of the drawer resizes its height between `150px` and `500px`.
* **Keyboard Navigation**: `Ctrl + \` key binding to toggle open/close.

## 9. Content Requirements
* **Log Lines**: Format: `[HH:MM:SS] [INFO/ERROR/WARN] Line message content`.
* **Actions**: Text label tags for `Clear Console`, `Auto-Scroll`, and `Minimize`.

## 10. Recommended References
* `reference/layout.md` for flexible relative height positioning.
* `reference/live.md` for server event stream hook details.
* `reference/harden.md` for error bounds handling.

## 11. Open Questions
* **Default Height**: *Decision:* Default expanded height is set to `240px` (preserving ample screen space for the wizard card above).
* **Maximum Log History**: *Decision:* Keep a maximum buffer of 1000 lines in memory to maintain memory performance.
