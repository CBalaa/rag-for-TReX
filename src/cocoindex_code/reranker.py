"""Optional search result reranking."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from cocoindex.ops.litellm import litellm

from .settings import RerankSettings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Reranker(Protocol):
    async def rerank(
        self,
        query: str,
        hits: list[T],
        *,
        content_getter: Any,
        top_n: int | None = None,
    ) -> list[tuple[T, float]]:
        """Return hits sorted by rerank relevance score descending."""


@dataclass
class LiteLLMReranker:
    model: str
    top_n: int = 50
    min_interval_ms: int | None = None
    params: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self._request_lock: asyncio.Lock | None = None
        self._next_request_at = 0.0
        self._min_request_interval_seconds = max(
            0.0,
            float(self.min_interval_ms or 0) / 1000.0,
        )

    def _get_request_lock(self) -> asyncio.Lock:
        if self._request_lock is None:
            self._request_lock = asyncio.Lock()
        return self._request_lock

    async def _pace(self) -> None:
        lock = self._get_request_lock()
        async with lock:
            now = time.monotonic()
            if self._next_request_at > now:
                await asyncio.sleep(self._next_request_at - now)
            self._next_request_at = time.monotonic() + self._min_request_interval_seconds

    async def rerank(
        self,
        query: str,
        hits: list[T],
        *,
        content_getter: Any,
        top_n: int | None = None,
    ) -> list[tuple[T, float]]:
        if not hits:
            return []
        limit = min(len(hits), top_n or self.top_n)
        candidates = hits[:limit]
        documents = [str(content_getter(hit)) for hit in candidates]
        await self._pace()
        response = await litellm.arerank(
            model=self.model,
            query=query,
            documents=documents,
            top_n=limit,
            return_documents=False,
            **dict(self.params or {}),
        )
        pairs = _pairs_from_response(response, candidates)
        if not pairs:
            logger.warning("Reranker %s returned no results; preserving vector order", self.model)
            return [(hit, 0.0) for hit in candidates]
        return sorted(pairs, key=lambda item: item[1], reverse=True)


def _pairs_from_response(response: Any, candidates: list[T]) -> list[tuple[T, float]]:
    results = getattr(response, "results", None)
    if results is None and isinstance(response, dict):
        results = response.get("results")
    if results is None:
        return []

    pairs: list[tuple[T, float]] = []
    for item in results:
        index = getattr(item, "index", None)
        score = getattr(item, "relevance_score", None)
        if isinstance(item, dict):
            index = item.get("index", index)
            score = item.get("relevance_score", item.get("score", score))
        if index is None or score is None:
            continue
        index_int = int(index)
        if index_int < 0 or index_int >= len(candidates):
            continue
        pairs.append((candidates[index_int], float(score)))
    return pairs


def create_reranker(settings: RerankSettings) -> Reranker | None:
    if not settings.enabled:
        return None
    if settings.provider != "litellm":
        raise ValueError("Only rerank.provider: litellm is currently supported")
    if not settings.model:
        raise ValueError("rerank.model is required when rerank.enabled is true")
    return LiteLLMReranker(
        model=settings.model,
        top_n=settings.top_n,
        min_interval_ms=settings.min_interval_ms,
        params=settings.params,
    )
