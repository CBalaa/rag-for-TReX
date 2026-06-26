"""Shared JSON schemas for Repo RAG search, locate, read, and errors."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

SEARCH_SCHEMA_VERSION = "repo-rag-search-v1"
LOCATE_SCHEMA_VERSION = "repo-rag-locate-v1"
ERROR_SCHEMA_VERSION = "repo-rag-error-v1"

DEFAULT_SEARCH_MODE = "semantic"


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def score_details(score: float | None) -> dict[str, float | None]:
    return {
        "vector_score": score,
        "keyword_score": None,
        "rerank_score": None,
    }


def error_envelope(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": ERROR_SCHEMA_VERSION,
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def file_content_hash(path: Path) -> str:
    return sha256_text(path.read_text())


def extension_for_path(path: str) -> str:
    return Path(path).suffix


def code_hit_to_dict(rank: int, hit: Any) -> dict[str, Any]:
    source = hit.source if hasattr(hit, "source") else hit
    score = float(hit.score)
    line_start = getattr(source, "line_start", None)
    if line_start is None:
        line_start = getattr(source, "start_line")
    line_end = getattr(source, "line_end", None)
    if line_end is None:
        line_end = getattr(source, "end_line")
    return {
        "rank": rank,
        "content_type": "code",
        "score": score,
        "score_details": getattr(hit, "score_details", None) or score_details(score),
        "content": hit.content,
        "source": {
            "path": getattr(source, "path", None) or getattr(source, "file_path", None),
            "language": source.language,
            "symbol": getattr(source, "symbol", None),
            "symbol_type": getattr(source, "symbol_type", None),
            "signature": getattr(source, "signature", None),
            "parent_symbol": getattr(source, "parent_symbol", None),
            "line_start": line_start,
            "line_end": line_end,
            "char_start": getattr(source, "char_start", None),
            "char_end": getattr(source, "char_end", None),
            "content_hash": getattr(source, "content_hash", None),
            "chunk_hash": getattr(source, "chunk_hash", None),
            "chunk_index": getattr(source, "chunk_index", None),
        },
        "metadata": getattr(hit, "metadata", None)
        or {
            "imports": getattr(source, "imports", []),
            "docstring": getattr(source, "docstring", None),
            "chunker_version": getattr(source, "chunker_version", None),
            "embedding_version": None,
        },
    }


def docs_hit_to_dict(rank: int, hit: Any) -> dict[str, Any]:
    source = hit.source
    score = float(hit.score)
    return {
        "rank": rank,
        "content_type": "documentation",
        "score": score,
        "score_details": getattr(hit, "score_details", None) or score_details(score),
        "content": hit.content,
        "source": {
            "path": source.path,
            "heading": source.heading,
            "heading_path": source.heading_path,
            "line_start": source.line_start,
            "line_end": source.line_end,
            "char_start": getattr(source, "char_start", None),
            "char_end": getattr(source, "char_end", None),
            "content_hash": source.content_hash,
            "chunk_hash": source.chunk_hash,
            "chunk_index": getattr(source, "chunk_index", None),
        },
        "metadata": getattr(hit, "metadata", None)
        or {
            "frontmatter": {},
            "extension": extension_for_path(source.path),
            "chunker_version": None,
            "embedding_version": None,
        },
    }


def search_response_to_dict(response: Any, *, index: str | None = None) -> dict[str, Any]:
    response_index = index or getattr(response, "index", "repo")
    if hasattr(response, "results"):
        hits = [
            code_hit_to_dict(rank, hit)
            for rank, hit in enumerate(response.results, start=getattr(response, "offset", 0) + 1)
        ]
    else:
        hits = []
        for rank, hit in enumerate(response.hits, start=getattr(response, "offset", 0) + 1):
            if hit.content_type == "code":
                hits.append(code_hit_to_dict(rank, hit))
            else:
                hits.append(docs_hit_to_dict(rank, hit))
    return {
        "schema_version": SEARCH_SCHEMA_VERSION,
        "query": getattr(response, "query", ""),
        "mode": getattr(response, "mode", DEFAULT_SEARCH_MODE),
        "index": response_index,
        "top_k": getattr(response, "top_k", len(hits)),
        "hits": hits,
    }


def locate_response_to_dict(response: Any, *, index: str = "repo") -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for rank, hit in enumerate(response.hits, start=getattr(response, "offset", 0) + 1):
        src = hit.source
        item = {
            "rank": rank,
            "content_type": hit.content_type,
            "score": hit.score,
            "path": src.path,
            "line_start": src.line_start,
            "line_end": src.line_end,
            "content_hash": getattr(src, "content_hash", None),
            "chunk_hash": getattr(src, "chunk_hash", None),
        }
        if hit.content_type == "code":
            item.update(
                {
                    "language": src.language,
                    "symbol": src.symbol,
                    "symbol_type": src.symbol_type,
                }
            )
        else:
            item.update(
                {
                    "heading": src.heading,
                    "heading_path": src.heading_path,
                }
            )
        hits.append(item)
    return {
        "schema_version": LOCATE_SCHEMA_VERSION,
        "query": response.query,
        "index": index,
        "hits": hits,
    }
