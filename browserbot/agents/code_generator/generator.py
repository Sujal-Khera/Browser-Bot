"""
browserbot/agents/code_generator/generator.py — Step 4.2: Code Generator Agent.

Consumes a WorkflowSpec (IR), calls a code-specialized LLM to generate the
Playwright workflow body, validates the code against the approved DSL,
renders the static Jinja2 template, and compiles the final script.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import jinja2
import litellm

from browserbot.agents.code_generator.prompt import build_system_prompt, build_user_prompt
from browserbot.agents.code_generator.validator import validate_dsl, DSLValidationError
from browserbot.config.settings import settings
from browserbot.logging import get_logger
from browserbot.models.workflow_spec import WorkflowSpec

log = get_logger(__name__)

# Template paths
TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "mcp_server_template"
TEMPLATE_FILE = "server.py.j2"


# ---------------------------------------------------------------------------
# LiteLLM call helper
# ---------------------------------------------------------------------------


def _call_llm(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float = 0.0,
) -> str:
    """Invoke the code generator LLM using LiteLLM."""
    try:
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        return content.strip()
    except Exception as exc:
        raise RuntimeError(f"LLM generator call failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Dry-run / Stub generator
# ---------------------------------------------------------------------------


def _build_dry_run_body(spec: WorkflowSpec) -> str:
    """
    Deterministically generate the workflow body without calling the LLM.
    Acts as a reference implementation of the approved Playwright DSL.
    """
    lines = []
    for step in spec.steps:
        action = step.get("action")
        step_idx = step.get("step_index")
        
        # Determine parameter variable if bound
        param_var = step.get("parameter_name")

        if action == "goto":
            url = step.get("url", "")
            lines.append(f'await page.goto("{url}")')

        elif action == "click":
            sel = step.get("selector", {})
            lines.append(f'await resilient_click(page, {repr(sel)})')

        elif action == "fill":
            sel = step.get("selector", {})
            # Use parameter variable name or fallback to hardcoded value
            fill_value = param_var if param_var else f'"{step.get("value", "")}"'
            lines.append(f'await resilient_fill(page, {repr(sel)}, {fill_value})')

        elif action == "wait":
            wait_for = step.get("wait_for")
            if wait_for == "selector":
                sel = step.get("selector", {})
                lines.append(f'await resolve_locator(page, {repr(sel)})')
            elif wait_for == "network_idle":
                # Wait for network idle state
                lines.append('await page.wait_for_load_state("networkidle")')
            else:
                lines.append('await page.wait_for_timeout(1000)')

        elif action in ("extract_text", "extract_attribute"):
            # Extraction is structural/fixed and handled by output block in the template,
            # but we can wait for the element here.
            sel = step.get("selector", {})
            if sel:
                lines.append(f'await resolve_locator(page, {repr(sel)})')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Code Generator class
# ---------------------------------------------------------------------------


class CodeGenerator:
    """
    Phase 4 LLM agent: Translates WorkflowSpec IR into a runnable FastMCP server.
    """

    def __init__(
        self,
        *,
        dry_run: bool = False,
        backend: str | None = None,
        max_retries: int = 2,
    ) -> None:
        self._dry_run = dry_run
        self._backend = (backend or settings.llm_backend).lower()
        self._max_retries = max_retries

        # Resolve model name
        if self._dry_run:
            self._model = "(dry-run)"
        elif self._backend == "ollama":
            self._model = f"ollama/{settings.ollama_model_generator}"
        elif self._backend == "groq":
            self._model = f"groq/{settings.groq_model}"
        else:
            raise ValueError(f"Unknown LLM backend: {self._backend}")

        # Setup Jinja2 Environment
        self._jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        log.info(
            "CodeGenerator initialised",
            extra={
                "model": self._model,
                "dry_run": self._dry_run,
                "backend": self._backend,
            },
        )

    def generate(self, spec: WorkflowSpec, correction: CorrectionPayload | None = None) -> str:
        """
        Generate the complete FastMCP server Python code from a WorkflowSpec.

        Args:
            spec: The validated WorkflowSpec IR.
            correction: Optional CorrectionPayload from a prior validation failure.

        Returns:
            The complete, rendered and compiled Python source code string.
        """
        log.info(
            "Starting code generation",
            extra={
                "source_session": spec.metadata.source_session_id,
                "steps": len(spec.steps),
                "params": len(spec.parameters),
                "has_correction": correction is not None,
            },
        )

        # 1. Generate workflow body
        if self._dry_run:
            body = _build_dry_run_body(spec)
        else:
            body = self._generate_body_with_llm(spec, correction=correction)

        # 2. Validate workflow body (DSL allow-list & safety checks)
        allowed_vars = {param.name for param in spec.parameters}
        try:
            validate_dsl(body, allowed_variables=allowed_vars)
        except DSLValidationError as err:
            log.error("Generated workflow body failed DSL validation", extra={"error": str(err)})
            raise

        # 3. Render Jinja2 template
        server_name = f"BrowserBot {spec.workflow.site.title()}"
        tool_name = f"execute_{spec.workflow.site.replace('.', '_').replace('-', '_')}"

        try:
            template = self._jinja_env.get_template(TEMPLATE_FILE)
            rendered_code = template.render(
                server_name=server_name,
                tool_name=tool_name,
                workflow_description=spec.workflow.description,
                parameters=spec.parameters,
                outputs=spec.outputs,
                workflow_body=body,
            )
        except Exception as err:
            log.error("Failed to render Jinja2 template", extra={"error": str(err)})
            raise RuntimeError(f"Template rendering failed: {err}") from err

        # 4. Compile check (ensure generated script compiles successfully)
        try:
            ast.parse(rendered_code)
            log.info("Generated code successfully compiled")
        except SyntaxError as syntax_err:
            log.error("Generated full script failed to compile", extra={"error": str(syntax_err)})
            raise RuntimeError(
                f"Generated Python code is syntactically invalid: {syntax_err}"
            ) from syntax_err

        return rendered_code

    def _generate_body_with_llm(self, spec: WorkflowSpec, correction: CorrectionPayload | None = None) -> str:
        """Invoke LLM to translate spec steps to Playwright statements with retries."""
        spec_json = spec.model_dump_json(indent=2)
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(workflow_spec_json=spec_json, correction=correction)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        allowed_vars = {param.name for param in spec.parameters}
        last_error = ""

        for attempt in range(1, self._max_retries + 2):
            log.info(
                "Code generator LLM call",
                extra={"attempt": attempt, "max": self._max_retries + 1, "model": self._model},
            )

            response = _call_llm(messages, model=self._model)
            
            # Clean response of backticks if LLM didn't follow prompt instructions
            cleaned = self._clean_llm_response(response)

            try:
                validate_dsl(cleaned, allowed_variables=allowed_vars)
                return cleaned
            except DSLValidationError as err:
                last_error = str(err)
                log.warning(
                    "LLM body failed DSL validation",
                    extra={"attempt": attempt, "error": last_error},
                )
                if attempt <= self._max_retries:
                    correction_msg = (
                        f"Your previous code output failed validation:\n\n{response}\n\n"
                        f"Errors:\n{last_error}\n\n"
                        "Output ONLY Python Playwright statement lines from the approved DSL. "
                        "Do not include imports, helper functions, loops, conditions, or markdown blocks."
                    )
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": correction_msg})

        raise RuntimeError(
            f"Code generation failed after {self._max_retries + 1} attempt(s). "
            f"Last validation error:\n{last_error}"
        )

    def _clean_llm_response(self, text: str) -> str:
        """Strip markdown ticks and comments if LLM included them."""
        text = text.strip()
        
        # Match ```python ... ``` or ``` ... ```
        match = re.match(r"^```(?:python)?\s*(.*?)\s*```$", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
            
        return text
