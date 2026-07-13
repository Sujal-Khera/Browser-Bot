"""
browserbot.config.settings — project-wide configuration via environment variables.

Usage:
    from browserbot.config.settings import settings

    print(settings.llm_backend)       # "ollama" | "groq"
    print(settings.ollama_model)      # e.g. "qwen2.5-coder:7b"
    print(settings.ollama_base_url)   # "http://localhost:11434"

All secrets (e.g. GROQ_API_KEY) must live in a git-ignored .env file.
The default configuration requires no API key — Ollama runs fully locally.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env if it exists — no-op if absent (default Ollama path needs no .env)
_dotenv_path: Path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_dotenv_path, override=False)


class Settings:
    """
    Centralised, read-once configuration object.

    Reads from environment variables (populated from .env if present).
    Values are resolved at construction time; mutate os.environ before
    constructing if you need to override in tests.
    """

    # ------------------------------------------------------------------ #
    # LLM backend
    # ------------------------------------------------------------------ #

    @property
    def llm_backend(self) -> str:
        """
        Primary LLM backend selector.

        "ollama"  — default, fully local, $0 cost (no credential required).
        "groq"    — free-tier cloud fallback; requires GROQ_API_KEY in .env.
        """
        return os.getenv("BROWSERBOT_LLM_BACKEND", "ollama").lower()

    @property
    def ollama_base_url(self) -> str:
        """Base URL of the local Ollama service."""
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def ollama_model_extractor(self) -> str:
        """
        Ollama model used by the Pattern Extractor agent.
        General instruction-following model recommended.
        """
        return os.getenv("OLLAMA_MODEL_EXTRACTOR", "llama3.1:8b")

    @property
    def ollama_model_generator(self) -> str:
        """
        Ollama model used by the Code Generator agent.
        Code-specialised model recommended.
        """
        return os.getenv("OLLAMA_MODEL_GENERATOR", "qwen2.5-coder:7b")

    @property
    def groq_api_key(self) -> str | None:
        """
        Groq free-tier API key.  Only required when llm_backend == "groq".
        Must live in a git-ignored .env file — never committed.
        """
        return os.getenv("GROQ_API_KEY")

    @property
    def groq_model(self) -> str:
        """Groq model identifier (OpenAI-compatible endpoint)."""
        return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # ------------------------------------------------------------------ #
    # Playwright / browser
    # ------------------------------------------------------------------ #

    @property
    def headless(self) -> bool:
        """Run browser in headless mode (True) or visible mode (False)."""
        return os.getenv("BROWSERBOT_HEADLESS", "true").lower() in ("1", "true", "yes")

    @property
    def browser_slow_mo_ms(self) -> int:
        """
        Milliseconds of slow-motion delay injected between Playwright actions.
        Useful for debugging; set to 0 for production runs.
        """
        return int(os.getenv("BROWSERBOT_SLOW_MO_MS", "0"))

    # ------------------------------------------------------------------ #
    # Storage
    # ------------------------------------------------------------------ #

    @property
    def project_root(self) -> Path:
        """Absolute path to the repository root."""
        return Path(__file__).resolve().parents[2]

    @property
    def generated_tools_dir(self) -> Path:
        """Output directory for generated MCP tool packages (git-ignored)."""
        return self.project_root / "generated_tools"

    @property
    def logs_dir(self) -> Path:
        """Directory for structured JSON pipeline logs."""
        return self.project_root / "logs"

    # ------------------------------------------------------------------ #
    # Validation / retry
    # ------------------------------------------------------------------ #

    @property
    def llm_max_retries(self) -> int:
        """Maximum number of LLM call retries before surfacing failure to user."""
        return int(os.getenv("BROWSERBOT_LLM_MAX_RETRIES", "2"))

    @property
    def validator_timeout_ms(self) -> int:
        """Timeout in milliseconds for each Playwright action during validation."""
        return int(os.getenv("BROWSERBOT_VALIDATOR_TIMEOUT_MS", "30000"))

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Settings("
            f"llm_backend={self.llm_backend!r}, "
            f"ollama_model_extractor={self.ollama_model_extractor!r}, "
            f"ollama_model_generator={self.ollama_model_generator!r}, "
            f"headless={self.headless}, "
            f"project_root={self.project_root}"
            f")"
        )


# Module-level singleton — import and use directly.
settings = Settings()
