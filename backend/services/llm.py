import json
import re
from typing import Any

import httpx

from backend.config import get_settings
from backend.services.ai_usage import collect_openrouter_usage
from backend.services.research_utils import has_live_api_key

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


class StructuredOutputError(RuntimeError):
    """Raised when a structured output request fails."""


class OpenRouterStructuredOutputService:
    """Minimal OpenRouter structured-output client for research tasks."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.model = model if model is not None else settings.openrouter_model
        self.api_key = (
            api_key if api_key is not None else settings.llm_api_key_for_model(self.model)
        )
        self.base_url = (
            base_url.rstrip("/")
            if base_url is not None
            else settings.llm_base_url_for_model(self.model).rstrip("/")
        )
        self.http_client = http_client
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.external_api_timeout_seconds
        )
        self.use_strict_json_schema = "openrouter.ai" in self.base_url

    def is_configured(self) -> bool:
        """Return whether live OpenRouter requests are available."""

        return has_live_api_key(self.api_key)

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 1_024,
        feature: str = "structured_output",
        temperature: float = 0,
    ) -> dict[str, Any]:
        """Generate a schema-constrained JSON payload with OpenRouter."""

        if not self.is_configured():
            raise StructuredOutputError("OpenRouter API credentials are not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        response_format: dict[str, Any]
        if self.use_strict_json_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "strict": True, "schema": schema},
            }
        else:
            response_format = {"type": "json_object"}

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": response_format,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if self.use_strict_json_schema:
            payload["provider"] = {"require_parameters": True, "sort": "price"}

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)

        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise StructuredOutputError("OpenRouter structured output request failed.") from error
        finally:
            if owns_client:
                await client.aclose()

        response_payload = response.json()
        collect_openrouter_usage(
            endpoint="chat/completions",
            feature=feature,
            model=self.model,
            response_payload=response_payload,
            metadata={"response_format": "json_schema"},
        )
        choices = response_payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise StructuredOutputError("OpenRouter response choices were missing.")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise StructuredOutputError("OpenRouter response choice must be an object.")

        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise StructuredOutputError("OpenRouter response exceeded max_tokens before completing.")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise StructuredOutputError("OpenRouter response message was missing.")

        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        if not isinstance(content, str) or not content.strip():
            raise StructuredOutputError("OpenRouter response did not contain text content.")
        if not self.use_strict_json_schema:
            fence_match = _JSON_FENCE_RE.search(content)
            content = fence_match.group(1) if fence_match else content.strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise StructuredOutputError("OpenRouter returned invalid JSON.") from error

        if not isinstance(parsed, dict):
            raise StructuredOutputError("OpenRouter JSON output must be an object.")

        return parsed


# Backwards-compatible alias so the agent code does not need to change immediately.
ClaudeStructuredOutputService = OpenRouterStructuredOutputService
