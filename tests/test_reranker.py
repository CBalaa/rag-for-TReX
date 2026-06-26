"""Tests for optional reranking."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cocoindex_code.reranker import (
    LiteLLMReranker,
    ZhipuReranker,
    _zhipu_rerank_request,
    create_reranker,
)
from cocoindex_code.settings import RerankSettings


def test_create_reranker_disabled() -> None:
    assert create_reranker(RerankSettings()) is None


def test_create_reranker_litellm() -> None:
    reranker = create_reranker(
        RerankSettings(enabled=True, provider="litellm", model="cohere/rerank-v3.5")
    )
    assert isinstance(reranker, LiteLLMReranker)
    assert reranker.model == "cohere/rerank-v3.5"


def test_create_reranker_zhipu() -> None:
    reranker = create_reranker(
        RerankSettings(enabled=True, provider="zhipu", model="rerank")
    )
    assert isinstance(reranker, ZhipuReranker)
    assert reranker.model == "rerank"


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


async def test_zhipu_reranker_orders_by_relevance(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    def fake_request(**kwargs):
        calls.update(kwargs)
        return {
            "results": [
                {"document": "second", "relevance_score": 0.8},
                {"document": "first", "relevance_score": 0.3},
            ]
        }

    monkeypatch.setattr("cocoindex_code.reranker._zhipu_rerank_request", fake_request)
    reranker = ZhipuReranker(model="rerank", top_n=2, params={"base_url": "https://example.test"})
    hits = [SimpleNamespace(content="first"), SimpleNamespace(content="second")]

    ranked = await reranker.rerank("query", hits, content_getter=lambda hit: hit.content)

    assert [hit.content for hit, _ in ranked] == ["second", "first"]
    assert [score for _, score in ranked] == [0.8, 0.3]
    assert calls["model"] == "rerank"
    assert calls["query"] == "query"
    assert calls["documents"] == ["first", "second"]
    assert calls["top_n"] == 2
    assert calls["params"] == {"base_url": "https://example.test"}


async def test_zhipu_reranker_handles_duplicate_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(**kwargs):
        return {
            "results": [
                {"document": "same", "relevance_score": 0.9},
                {"document": "same", "relevance_score": 0.4},
            ]
        }

    monkeypatch.setattr("cocoindex_code.reranker._zhipu_rerank_request", fake_request)
    first = SimpleNamespace(content="same", name="first")
    second = SimpleNamespace(content="same", name="second")
    reranker = ZhipuReranker(model="rerank-pro", top_n=2)

    ranked = await reranker.rerank("query", [first, second], content_getter=lambda hit: hit.content)

    assert [(hit.name, score) for hit, score in ranked] == [("first", 0.9), ("second", 0.4)]


def test_zhipu_rerank_request_uses_open_platform_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"results":[{"document":"a","relevance_score":0.7}]}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("ZHIPUAI_API_KEY", "test-key")
    monkeypatch.setattr("cocoindex_code.reranker.urlopen", fake_urlopen)

    response = _zhipu_rerank_request(
        model="rerank",
        query="q",
        documents=["a", "b"],
        top_n=2,
        params={"base_url": "https://open.bigmodel.cn/api/paas/v4/", "timeout": 12},
    )

    assert response["results"][0]["relevance_score"] == 0.7
    assert captured["url"] == "https://open.bigmodel.cn/api/paas/v4/rerank"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["payload"] == {
        "model": "rerank",
        "query": "q",
        "documents": ["a", "b"],
        "top_n": 2,
    }
    assert captured["timeout"] == 12
