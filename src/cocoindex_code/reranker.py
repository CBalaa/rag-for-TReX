"""Optional search result reranking."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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


@dataclass
class ZhipuReranker:
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
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _zhipu_rerank_request(
                model=self.model,
                query=query,
                documents=documents,
                top_n=limit,
                params=dict(self.params or {}),
            ),
        )
        pairs = _pairs_from_zhipu_response(response, candidates, documents)
        if not pairs:
            logger.warning(
                "Zhipu reranker %s returned no results; preserving vector order",
                self.model,
            )
            return [(hit, 0.0) for hit in candidates]
        return sorted(pairs, key=lambda item: item[1], reverse=True)


def _zhipu_rerank_request(
    *,
    model: str,
    query: str,
    documents: list[str],
    top_n: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    api_key = (
        params.pop("api_key", None)
        or os.environ.get("ZHIPUAI_API_KEY")
        or os.environ.get("ZHIPU_API_KEY")
    )
    if not api_key:
        raise ValueError("Zhipu rerank requires ZHIPUAI_API_KEY")
    base_url = str(
        params.pop("base_url", None)
        or os.environ.get("ZHIPUAI_API_BASE")
        or os.environ.get("ZHIPU_BASE_URL")
        or "https://open.bigmodel.cn/api/paas/v4/"
    ).rstrip("/")
    timeout = float(params.pop("timeout", 60))
    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": top_n,
        **params,
    }
    request = Request(
        f"{base_url}/rerank",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Zhipu rerank failed: HTTP {e.code}: {body}") from e


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


def _pairs_from_zhipu_response(
    response: Any,
    candidates: list[T],
    documents: list[str],
) -> list[tuple[T, float]]:
    """Parse Zhipu rerank responses.

    Zhipu's `/v4/rerank` response returns sorted items with the original
    `document` text and `relevance_score`, but no explicit candidate index.
    Map each returned document back to the first unused matching candidate.
    """
    results = getattr(response, "results", None)
    if results is None and isinstance(response, dict):
        results = response.get("results")
    if results is None:
        return []

    by_document: dict[str, list[int]] = {}
    for index, document in enumerate(documents):
        by_document.setdefault(document, []).append(index)

    pairs: list[tuple[T, float]] = []
    for item in results:
        document = getattr(item, "document", None)
        score = getattr(item, "relevance_score", None)
        if isinstance(item, dict):
            document = item.get("document", document)
            score = item.get("relevance_score", item.get("score", score))
        if document is None or score is None:
            continue
        indexes = by_document.get(str(document))
        if not indexes:
            continue
        index = indexes.pop(0)
        pairs.append((candidates[index], float(score)))
    return pairs


def create_reranker(settings: RerankSettings) -> Reranker | None:
    if not settings.enabled:
        return None
    if not settings.model:
        raise ValueError("rerank.model is required when rerank.enabled is true")
    if settings.provider == "litellm":
        return LiteLLMReranker(
            model=settings.model,
            top_n=settings.top_n,
            min_interval_ms=settings.min_interval_ms,
            params=settings.params,
        )
    if settings.provider in {"zhipu", "glm"}:
        return ZhipuReranker(
            model=settings.model,
            top_n=settings.top_n,
            min_interval_ms=settings.min_interval_ms,
            params=settings.params,
        )
    raise ValueError("rerank.provider must be one of: litellm, zhipu")
