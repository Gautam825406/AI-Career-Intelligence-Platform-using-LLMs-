"""Thin async wrapper around OpenAI's Chat Completions API.

Kept separate from route handlers and from the career-mapping prompt logic
so it can be unit-tested and reused independently. Handles: a reusable
HTTP client, timeouts, retries on transient errors only, and never logging
secrets.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config import Settings
from app.core.exceptions import ProviderConnectionError, ProviderTimeoutError

logger = logging.getLogger("syllabus_career_mapper")

# Errors worth retrying: connection resets, timeouts, and 5xx / 429 from the provider.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class OpenAICompletionResult:
    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: str


class OpenAIClient:
    """Wraps a single reusable httpx.AsyncClient. Instantiate once per app
    lifespan, not per-request, so connections are pooled and reused."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.openai_base_url,
            timeout=httpx.Timeout(settings.openai_timeout_seconds),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat_completion_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
    ) -> OpenAICompletionResult:
        """Call OpenAI requesting a JSON-object response. Retries transient
        errors up to `openai_max_retries` times. Raises ProviderTimeoutError or
        ProviderConnectionError on unrecoverable failure -- never lets a raw
        httpx exception or the API key escape this function."""

        body: dict[str, Any] = {
            "model": self._settings.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_completion_tokens": max_tokens or self._settings.openai_max_completion_tokens,
            "response_format": {"type": "json_object"},
        }

        last_exception: Optional[Exception] = None

        for attempt in range(self._settings.openai_max_retries + 1):
            try:
                response = await self._client.post("/chat/completions", json=body)

                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < self._settings.openai_max_retries:
                    logger.info(
                        json.dumps(
                            {
                                "event": "openai_retry",
                                "attempt": attempt + 1,
                                "status_code": response.status_code,
                            }
                        )
                    )
                    continue

                response.raise_for_status()
                data = response.json()

                choice = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                return OpenAICompletionResult(
                    content=choice,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    model=data.get("model", self._settings.openai_model),
                )

            except httpx.TimeoutException as exc:
                last_exception = exc
                if attempt >= self._settings.openai_max_retries:
                    raise ProviderTimeoutError("The AI provider took too long to respond.") from exc
                continue

            except httpx.HTTPStatusError as exc:
                # Non-retryable status (e.g. 400/401) or retries exhausted.
                if exc.response.status_code in _RETRYABLE_STATUS_CODES and attempt < self._settings.openai_max_retries:
                    last_exception = exc
                    continue
                raise ProviderConnectionError(
                    "The AI provider returned an error and could not complete the request."
                ) from exc

            except (httpx.ConnectError, httpx.ReadError, httpx.NetworkError) as exc:
                last_exception = exc
                if attempt >= self._settings.openai_max_retries:
                    raise ProviderConnectionError("Could not reach the AI provider.") from exc
                continue

        # Should not normally be reached, but guards against silent fallthrough.
        raise ProviderConnectionError("The AI provider request failed after all retries.") from last_exception
