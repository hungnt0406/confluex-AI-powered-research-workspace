from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.config import get_settings


@dataclass(frozen=True)
class TavilySearchResult:
    """Normalized Tavily result used by deep search."""

    title: str
    url: str | None
    content: str
    score: float | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TavilySearchResponse:
    """Tavily response plus recoverable warnings."""

    results: list[TavilySearchResult]
    warnings: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class TavilySearchService:
    """Small Tavily Search API client with explicit cheap defaults."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        max_results: int | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.tavily_api_key
        self.base_url = (
            base_url.rstrip("/") if base_url is not None else settings.tavily_base_url.rstrip("/")
        )
        self.max_results = (
            max_results
            if max_results is not None
            else settings.deep_search_max_results_per_query
        )
        self.http_client = http_client
        self.timeout_seconds = settings.external_api_timeout_seconds

    def is_configured(self) -> bool:
        """Return whether a Tavily API key is available."""

        return bool((self.api_key or "").strip())

    async def search(self, query: str, *, max_results: int | None = None) -> TavilySearchResponse:
        """Search Tavily, returning warnings instead of raising recoverable provider errors."""

        normalized_query = query.strip()
        if not normalized_query:
            return TavilySearchResponse(results=[], warnings=[], metadata={"skipped": "empty_query"})

        if not self.is_configured():
            return TavilySearchResponse(
                results=[],
                warnings=["Tavily API key is not configured; web search was skipped."],
                metadata={"configured": False},
            )

        requested_max_results = max_results if max_results is not None else self.max_results
        payload: dict[str, object] = {
            "query": normalized_query,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
            "max_results": requested_max_results,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_seconds)

        try:
            response = await client.post(f"{self.base_url}/search", headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as error:
            return TavilySearchResponse(
                results=[],
                warnings=[f"Tavily web search failed for query '{normalized_query}'."],
                metadata={"error": str(error), "configured": True},
            )
        finally:
            if owns_client:
                await client.aclose()

        raw_payload = response.json()
        if not isinstance(raw_payload, dict):
            return TavilySearchResponse(
                results=[],
                warnings=[f"Tavily web search returned an invalid payload for query '{normalized_query}'."],
                metadata={"configured": True},
            )

        raw_results = raw_payload.get("results", [])
        if not isinstance(raw_results, list):
            raw_results = []

        results = [
            self._normalize_result(raw_result)
            for raw_result in raw_results
            if isinstance(raw_result, dict)
        ]
        return TavilySearchResponse(
            results=results,
            warnings=[],
            metadata={
                "configured": True,
                "query": normalized_query,
                "response_time": raw_payload.get("response_time"),
                "result_count": len(results),
            },
        )

    def _normalize_result(self, raw_result: dict[str, object]) -> TavilySearchResult:
        title = str(raw_result.get("title", "")).strip() or "Untitled web source"
        raw_url = raw_result.get("url")
        url = raw_url.strip() if isinstance(raw_url, str) and raw_url.strip() else None
        content = str(raw_result.get("content", "")).strip()
        raw_score = raw_result.get("score")
        score = float(raw_score) if isinstance(raw_score, int | float) else None
        return TavilySearchResult(
            title=title,
            url=url,
            content=content,
            score=score,
            metadata={"raw_score": raw_score},
        )
