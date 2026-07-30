"""
Centralized application configuration.

All environment-driven settings live here so the rest of the codebase
never touches `os.environ` directly. This keeps secrets out of business
logic and makes it easy to see everything the app depends on at a glance.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # --- OpenAI / LLM provider settings -----------------------------------------------
    openai_api_key: str = Field(..., description="Secret API key for the OpenAI API")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for the OpenAI API",
    )
    openai_model: str = Field(
        default="gpt-5-nano",
        description="OpenAI model name to use; gpt-5-nano is the lowest-cost GPT model",
    )

    # --- Behavior tuning ----------------------------------------------------------------
    openai_timeout_seconds: float = Field(default=30.0, description="Hard timeout for a single OpenAI call")
    openai_max_retries: int = Field(default=2, description="Retries for transient network/provider errors")
    openai_max_completion_tokens: int = Field(
        default=4096,
        description="Maximum completion tokens OpenAI may generate per response",
    )

    # --- Request limits -------------------------------------------------------------------
    max_syllabus_chars: int = Field(default=20_000, description="Hard cap on syllabus_text length")
    min_syllabus_chars: int = Field(default=200, description="Minimum syllabus_text length")

    # --- Rate limiting --------------------------------------------------------------------
    rate_limit_per_minute: int = Field(default=20, description="Requests allowed per client per minute")

    # --- App metadata ---------------------------------------------------------------------
    app_name: str = Field(default="Syllabus-to-Career Mapper")
    environment: str = Field(default="development")
    log_full_syllabus: bool = Field(
        default=False,
        description="If false (default), syllabus text is never written to logs",
    )

    class Config:
        env_file = ".env"
        case_sensitive = False
        # Ignore legacy GROQ_* entries while a local .env is being migrated.
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance so .env is parsed only once per process."""
    return Settings()
