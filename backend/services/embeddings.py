import hashlib
from typing import Any

import httpx

from backend.config import get_settings
from backend.services.research_utils import has_live_api_key, tokenize_text

MAX_EMBEDDING_CHARS = 8_000


class EmbeddingServiceError(RuntimeError):
    """Raised when an embedding request fails."""


class EmbeddingService:
    """Generate embeddings using OpenRouter or a deterministic local fallback."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.model = model if model is not None else settings.openrouter_embedding_model
        self.dimensions = dimensions if dimensions is not None else settings.embedding_dimensions
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self.http_client = http_client
        self.timeout_seconds = settings.external_api_timeout_seconds

    def is_configured(self) -> bool:
        """Return whether live OpenRouter embeddings are available."""

        return has_live_api_key(self.api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed text payloads using OpenRouter when available."""

        if not texts:
            return []

        if not self.is_configured():
            return self.embed_texts_locally(texts)

        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        normalized_inputs = [text[:MAX_EMBEDDING_CHARS] for text in texts]
        payload: dict[str, Any] = {
            "input": normalized_inputs,
            "model": self.model,
            "encoding_format": "float",
            "provider": {
                "sort": "price",
            },
        }
        if self.model.startswith("openai/text-embedding-3") or self.model.startswith(
            "text-embedding-3"
        ):
            payload["dimensions"] = self.dimensions

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)

        try:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise EmbeddingServiceError("OpenRouter embedding request failed.") from error
        finally:
            if owns_client:
                await client.aclose()

        response_payload = response.json()
        items = response_payload.get("data", [])
        if not isinstance(items, list):
            raise EmbeddingServiceError("Embedding response data must be a list.")

        embeddings: list[list[float]] = []
        for item in items:
            if not isinstance(item, dict):
                raise EmbeddingServiceError("Embedding response item must be an object.")
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingServiceError("Embedding response item is missing its embedding vector.")
            embeddings.append([float(value) for value in embedding])

        return embeddings

    def embed_texts_locally(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic local embeddings for offline and test flows."""

        return [self._embed_text_locally(text) for text in texts]

    def _embed_text_locally(self, text: str) -> list[float]:
        tokens = tokenize_text(text)
        vector = [0.0] * self.dimensions

        for token in tokens:
            token_digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(token_digest[:4], byteorder="big") % self.dimensions
            sign = 1.0 if token_digest[4] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 12) / 12
            vector[index] += sign * weight

        return vector
