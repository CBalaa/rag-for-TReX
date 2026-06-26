"""Tests for Markdown docs indexing and repository search helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
from cocoindex.connectors import sqlite as coco_sqlite
from cocoindex.resources.schema import VectorSchema

from cocoindex_code.project import Project
from cocoindex_code.settings import ProjectSettings, save_project_settings

_EMBED_DIM = 4


class _StubEmbedder:
    def __coco_memo_key__(self) -> str:
        return "docs-stub-embedder"

    async def __coco_vector_schema__(self) -> VectorSchema:
        return VectorSchema(dtype=np.dtype("float32"), size=_EMBED_DIM)

    async def embed(self, text: str) -> np.ndarray:
        vec = np.zeros(_EMBED_DIM, dtype=np.float32)
        if "AUTH_TOKEN" in text or "auth" in text.lower():
            vec[0] = 1.0
        if "login" in text.lower():
            vec[1] = 1.0
        return vec


class _ReverseReranker:
    async def rerank(self, query, hits, *, content_getter, top_n=None):
        del query, content_getter, top_n
        reversed_hits = list(reversed(hits))
        return [(hit, float(len(reversed_hits) - i)) for i, hit in enumerate(reversed_hits)]


async def _project(tmp_path: Path) -> Project:
    save_project_settings(
        tmp_path,
        ProjectSettings(
            include_patterns=["**/*.py"],
            exclude_patterns=["**/.rag4trex"],
            docs_include_patterns=["**/*.md", "**/*.mdx", "**/*.markdown"],
            docs_exclude_patterns=["docs/private/**"],
        ),
    )
    return await Project.create(
        tmp_path,
        _StubEmbedder(),
        indexing_params={},
        query_params={},
    )


async def _project_with_reranker(tmp_path: Path) -> Project:
    save_project_settings(
        tmp_path,
        ProjectSettings(
            include_patterns=["**/*.py"],
            exclude_patterns=["**/.rag4trex"],
            docs_include_patterns=["**/*.md", "**/*.mdx", "**/*.markdown"],
            docs_exclude_patterns=[],
        ),
    )
    return await Project.create(
        tmp_path,
        _StubEmbedder(),
        indexing_params={},
        query_params={},
        reranker=_ReverseReranker(),
    )


def _docs_rows(project_root: Path) -> list[dict[str, Any]]:
    conn = coco_sqlite.connect(
        str(project_root / ".rag4trex" / "target_sqlite.db"),
        load_vec=True,
    )
    try:
        with conn.readonly() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """
                SELECT content_type, file_path, heading, heading_path, line_start, line_end,
                       content_hash, chunk_hash, chunker_version
                FROM docs_chunks_vec
                ORDER BY file_path, chunk_index
                """
            ).fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def _code_rows(project_root: Path) -> list[dict[str, Any]]:
    conn = coco_sqlite.connect(
        str(project_root / ".rag4trex" / "target_sqlite.db"),
        load_vec=True,
    )
    try:
        with conn.readonly() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """
                SELECT file_path, language, start_line, end_line, content_hash,
                       chunk_hash, symbol, symbol_type, signature
                FROM code_chunks_vec
                ORDER BY file_path, chunk_index
                """
            ).fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


async def test_docs_index_add_modify_delete(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()
    readme = docs / "auth.md"
    readme.write_text("# Auth\n\nSet AUTH_TOKEN.\n")

    project = await _project(tmp_path)
    await project.run_index(index_type="docs")
    rows = _docs_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["file_path"] == "docs/auth.md"
    assert rows[0]["content_type"] == "documentation"
    assert rows[0]["heading"] == "Auth"
    first_hash = rows[0]["chunk_hash"]

    readme.write_text("# Auth\n\nSet AUTH_TOKEN and LOGIN_URL.\n")
    await project.run_index(index_type="docs")
    rows = _docs_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["chunk_hash"] != first_hash

    readme.unlink()
    await project.run_index(index_type="docs")
    assert _docs_rows(tmp_path) == []


async def test_search_docs_returns_source_metadata(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "auth.md").write_text("# Deploy\n\n## Auth\n\nSet AUTH_TOKEN.\n")

    project = await _project(tmp_path)
    await project.run_index(index_type="docs")

    resp = await project.search_docs("auth token", limit=3)

    assert resp.success is True
    assert resp.hits
    hit = resp.hits[0]
    assert hit.content_type == "documentation"
    assert "AUTH_TOKEN" in hit.content
    assert hit.score > 0
    assert hit.source.path == "docs/auth.md"
    assert hit.source.heading_path == ["Deploy", "Auth"]
    assert hit.source.line_start >= 1
    assert hit.source.line_end >= hit.source.line_start
    assert hit.source.char_start is not None
    assert hit.source.chunk_index is not None
    assert hit.source.chunk_index >= 0
    assert hit.source.content_hash.startswith("sha256:")
    assert hit.source.chunk_hash.startswith("sha256:")
    assert hit.metadata["frontmatter"] == {}
    assert hit.score_details["vector_score"] == hit.score


async def test_search_code_returns_source_metadata_and_symbol(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "auth.py").write_text(
        "import jwt\n\n"
        "class AuthService:\n"
        "    def verify_token(self, token: str):\n"
        "        \"\"\"Verify an access token.\"\"\"\n"
        "        return jwt.decode(token, 'secret')\n"
    )

    project = await _project(tmp_path)
    await project.run_index(index_type="code")
    rows = _code_rows(tmp_path)
    assert rows
    assert rows[0]["content_hash"].startswith("sha256:")
    assert rows[0]["chunk_hash"].startswith("sha256:")

    hits = await project.search("verify token", limit=3)
    assert hits
    hit = hits[0]
    assert hit.file_path == "auth.py"
    assert hit.language == "python"
    assert hit.start_line >= 1
    assert hit.end_line >= hit.start_line
    assert hit.score > 0
    assert hit.symbol in {"AuthService", "AuthService.verify_token"}
    assert hit.symbol_type in {"class", "method"}
    assert hit.content_hash.startswith("sha256:")


async def test_search_repo_returns_code_and_docs(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "auth.md").write_text("# Auth\n\nSet AUTH_TOKEN.\n")
    (tmp_path / "auth.py").write_text("AUTH_TOKEN = 'dev'\n")

    project = await _project(tmp_path)
    await project.run_index(index_type="code")
    await project.run_index(index_type="docs")

    hits = await project.search_repo("AUTH_TOKEN", limit=10)
    assert {hit.content_type for hit in hits} >= {"code", "documentation"}
    for hit in hits:
        assert hit.source.path
        assert hit.source.line_start >= 1
        assert hit.score_details["vector_score"] == hit.score


async def test_ignore_files_and_always_exclude_for_docs(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("docs/gitignored.md\n")
    (tmp_path / ".ragignore").write_text("docs/ragignored.md\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "keep.md").write_text("# Keep\n\nAUTH_TOKEN\n")
    (tmp_path / "docs" / "gitignored.md").write_text("# Gitignored\n\nAUTH_TOKEN\n")
    (tmp_path / "docs" / "ragignored.md").write_text("# Ragignored\n\nAUTH_TOKEN\n")
    (tmp_path / "docs" / "secret.key").write_text("AUTH_TOKEN\n")

    project = await _project(tmp_path)
    await project.run_index(index_type="docs")
    rows = _docs_rows(tmp_path)
    assert [row["file_path"] for row in rows] == ["docs/keep.md"]


def test_search_schema_and_locate_schema_helpers() -> None:
    from cocoindex_code.protocol import (
        RepoSearchHit,
        RepoSearchResponse,
        RepoSearchSource,
    )
    from cocoindex_code.rag_schema import locate_response_to_dict, search_response_to_dict

    resp = RepoSearchResponse(
        success=True,
        query="auth",
        hits=[
            RepoSearchHit(
                content_type="code",
                score=0.8,
                content="def auth(): pass",
                source=RepoSearchSource(
                    path="auth.py",
                    line_start=1,
                    line_end=1,
                    language="python",
                    symbol="auth",
                    symbol_type="function",
                ),
            )
        ],
        top_k=1,
    )
    data = search_response_to_dict(resp)
    assert data["schema_version"] == "repo-rag-search-v1"
    assert data["hits"][0]["rank"] == 1
    assert data["hits"][0]["source"]["path"] == "auth.py"
    locate = locate_response_to_dict(resp)
    assert locate["schema_version"] == "repo-rag-locate-v1"
    assert locate["hits"][0]["content_type"] == "code"


async def test_search_docs_reranker_sets_final_score_and_details(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "auth.md").write_text(
        "# Auth\n\nSet AUTH_TOKEN.\n\n## Login\n\nLogin failure flow.\n"
    )

    project = await _project_with_reranker(tmp_path)
    await project.run_index(index_type="docs")
    resp = await project.search_docs("auth login", limit=2)

    assert len(resp.hits) == 2
    assert resp.hits[0].score == 2.0
    assert resp.hits[0].score_details["rerank_score"] == 2.0
    assert resp.hits[0].score_details["vector_score"] is not None
