"""Tests for optional reranking."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cocoindex_code.reranker import LiteLLMReranker, create_reranker
from cocoindex_code.settings import RerankSettings


def test_create_reranker_disabled() -> None:
    assert create_reranker(RerankSettings()) is None


def test_create_reranker_litellm() -> None:
    reranker = create_reranker(
        RerankSettings(enabled=True, provider="litellm", model="cohere/rerank-v3.5")
    )
    assert isinstance(reranker, LiteLLMReranker)
    assert reranker.model == "cohere/rerank-v3.5"


async def test_litellm_reranker_orders_by_relevance(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    async def fake_arerank(**kwargs):
        calls.update(kwargs)
        return {
            "results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.2},
            ]
        }

    monkeypatch.setattr("cocoindex_code.reranker.litellm.arerank", fake_arerank)
    reranker = LiteLLMReranker(model="cohere/rerank-v3.5", top_n=2)
    hits = [SimpleNamespace(content="first"), SimpleNamespace(content="second")]

    ranked = await reranker.rerank("query", hits, content_getter=lambda hit: hit.content)

    assert [hit.content for hit, _ in ranked] == ["second", "first"]
    assert [score for _, score in ranked] == [0.9, 0.2]
    assert calls["model"] == "cohere/rerank-v3.5"
    assert calls["query"] == "query"
    assert calls["documents"] == ["first", "second"]
