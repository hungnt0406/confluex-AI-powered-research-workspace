import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from backend.config import LlmProvider, get_settings
from backend.services.ai_usage import collect_openrouter_usage
from backend.services.research_utils import has_live_api_key

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


class StructuredOutputError(RuntimeError):
    """Raised when a structured output request fails."""


class StructuredOutputTransportError(StructuredOutputError):
    """Raised when the request to the LLM provider could not be completed
    (timeout, connection error, HTTP error). A stricter prompt will not help."""


@dataclass(frozen=True)
class ChatTurn:
    """One message in a chat conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ChatCompletion:
    """Result of a free-form chat completion call."""

    content: str
    usage: dict[str, Any] = field(default_factory=dict)


class StructuredOutputClient(Protocol):
    """Provider-agnostic interface for structured output and free-form chat."""

    def is_configured(self) -> bool: ...

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 1024,
        feature: str = "structured_output",
        temperature: float = 0,
    ) -> dict[str, Any]: ...

    async def generate_chat(
        self,
        *,
        messages: list[ChatTurn],
        max_tokens: int = 2048,
        temperature: float = 0.2,
        feature: str = "chat_completion",
    ) -> ChatCompletion: ...


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
            raise StructuredOutputTransportError(
                f"OpenRouter structured output request failed: {type(error).__name__}: {error}"
            ) from error
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

    async def generate_chat(
        self,
        *,
        messages: list[ChatTurn],
        max_tokens: int = 2_048,
        temperature: float = 0.2,
        feature: str = "chat_completion",
    ) -> ChatCompletion:
        """Generate a free-form chat completion via OpenRouter."""

        if not self.is_configured():
            raise StructuredOutputError("OpenRouter API credentials are not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

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
            raise StructuredOutputTransportError(
                f"OpenRouter chat request failed: {type(error).__name__}: {error}"
            ) from error
        finally:
            if owns_client:
                await client.aclose()

        response_payload = response.json()
        collect_openrouter_usage(
            endpoint="chat/completions",
            feature=feature,
            model=self.model,
            response_payload=response_payload,
            metadata={"response_format": "chat"},
        )
        content = _extract_chat_content(response_payload)
        usage_dict = response_payload.get("usage") if isinstance(response_payload, dict) else None
        if not isinstance(usage_dict, dict):
            usage_dict = {}
        return ChatCompletion(content=content, usage=usage_dict)


_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)


def _extract_chat_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise StructuredOutputError("Chat response choices were missing.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise StructuredOutputError("Chat response choice must be an object.")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise StructuredOutputError("Chat response message was missing.")
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if not isinstance(content, str):
        content = ""
    # Reasoning models (MiMo, DeepSeek-style) wrap chain-of-thought in <think>...</think>
    # blocks inside `content`, or split it out into `reasoning_content`. Strip the
    # think tags; if nothing is left, recover the model's final answer from
    # `reasoning_content` as a last resort.
    cleaned = _THINK_BLOCK_RE.sub("", content).strip()
    if cleaned:
        return cleaned
    reasoning = message.get("reasoning_content") or message.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return _THINK_BLOCK_RE.sub("", reasoning).strip()
    raise StructuredOutputError(
        "Chat response had no content — the model may have used the entire token "
        "budget on reasoning. Try raising WRITER_CHAT_MAX_TOKENS or narrowing the request."
    )


# Backwards-compatible alias so the agent code does not need to change immediately.
ClaudeStructuredOutputService = OpenRouterStructuredOutputService


def get_structured_client(
    provider: LlmProvider | None = None,
    *,
    timeout_seconds: float | None = None,
) -> StructuredOutputClient:
    """Return a structured-output client for the requested provider.

    Existing module callers that already construct `OpenRouterStructuredOutputService`
    directly stay on OpenRouter; this factory is used by the chat code path so it can
    target Xiaomi without disturbing the rest of the pipeline.
    """

    settings = get_settings()
    selected = provider or LlmProvider.OPENROUTER
    if selected == LlmProvider.XIAOMI:
        from backend.services.llm_xiaomi import XiaomiStructuredOutputService

        return XiaomiStructuredOutputService(
            model=settings.xiaomi_chat_model,
            timeout_seconds=timeout_seconds,
        )
    return OpenRouterStructuredOutputService(timeout_seconds=timeout_seconds)
