"""Xiaomi MiMo structured-output + chat client (OpenAI-compatible)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from backend.config import get_settings
from backend.services.ai_usage import collect_xiaomi_usage
from backend.services.llm import (
    _JSON_FENCE_RE,
    ChatCompletion,
    ChatTurn,
    StructuredOutputError,
    StructuredOutputTransportError,
    _extract_chat_content,
)
from backend.services.research_utils import has_live_api_key


class XiaomiStructuredOutputService:
    """Minimal Xiaomi MiMo structured-output / chat client.

    Xiaomi's endpoint is OpenAI-compatible (`POST {base}/chat/completions` with
    `Authorization: Bearer {key}`). Structured output is attempted via
    `response_format=json_schema` when available; otherwise we fall back to
    `json_object` and fence-strip parsing.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        http_client: httpx.AsyncClient | None = None,
        use_json_schema: bool = False,
    ) -> None:
        settings = get_settings()
        self.model = model or settings.xiaomi_chat_model
        self.api_key = api_key if api_key is not None else settings.xiaomi_mimo_api_key
        self.base_url = (
            (base_url or settings.xiaomi_mimo_base_url).rstrip("/")
        )
        self.http_client = http_client
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.external_api_timeout_seconds
        )
        self.use_json_schema = use_json_schema

    def is_configured(self) -> bool:
        return has_live_api_key(self.api_key) and bool(self.model)

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 1_024,
        feature: str = "structured_output",
        temperature: float = 0,
        image_data: str | None = None,
        image_media_type: str = "image/png",
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise StructuredOutputError("Xiaomi MiMo API credentials are not configured.")

        response_format: dict[str, Any]
        if self.use_json_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": schema,
                },
            }
        else:
            response_format = {"type": "json_object"}

        if image_data:
            user_content: str | list[dict[str, Any]] = [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image_media_type};base64,{image_data}"},
                },
            ]
        else:
            user_content = user_prompt

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": response_format,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        response_payload = await self._post(payload, feature=feature)
        content = _extract_chat_content(response_payload)
        if not content.strip():
            raise StructuredOutputError("Xiaomi MiMo returned empty content.")
        if not self.use_json_schema:
            fence_match = _JSON_FENCE_RE.search(content)
            content = fence_match.group(1) if fence_match else content.strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise StructuredOutputError("Xiaomi MiMo returned invalid JSON.") from error
        if not isinstance(parsed, dict):
            raise StructuredOutputError("Xiaomi MiMo JSON output must be an object.")
        return parsed

    async def generate_chat(
        self,
        *,
        messages: list[ChatTurn],
        max_tokens: int = 2_048,
        temperature: float = 0.2,
        feature: str = "chat_completion",
    ) -> ChatCompletion:
        if not self.is_configured():
            raise StructuredOutputError("Xiaomi MiMo API credentials are not configured.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        response_payload = await self._post(payload, feature=feature)
        content = _extract_chat_content(response_payload)
        usage = response_payload.get("usage") if isinstance(response_payload, dict) else None
        if not isinstance(usage, dict):
            usage = {}
        return ChatCompletion(content=content, usage=usage)

    async def _post(self, payload: dict[str, Any], *, feature: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
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
                f"Xiaomi MiMo request failed: {type(error).__name__}: {error}"
            ) from error
        finally:
            if owns_client:
                await client.aclose()

        response_payload = response.json()
        collect_xiaomi_usage(
            endpoint="chat/completions",
            feature=feature,
            model=self.model,
            response_payload=response_payload,
            metadata={"response_format": payload.get("response_format", "chat")},
        )
        if not isinstance(response_payload, dict):
            raise StructuredOutputError("Xiaomi MiMo response must be an object.")
        return response_payload
