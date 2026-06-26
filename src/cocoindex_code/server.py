"""MCP server for codebase indexing and querying.

Supports two modes:
1. Daemon-backed: ``create_mcp_server(client, project_root)`` — lightweight MCP
   server that delegates to the daemon via per-request client functions.
2. Legacy entry point: ``main()`` — backward-compatible server entry point that
   auto-creates settings from env vars and delegates to the daemon.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .rag_schema import (
    error_envelope,
    locate_response_to_dict,
    search_response_to_dict,
)

_MCP_INSTRUCTIONS = (
    "Code, documentation, and repository understanding tools."
    "\n"
    "Use when you need to find code, understand how something works,"
    " locate implementations, find documentation, or explore an unfamiliar codebase."
    "\n"
    "RAG search is for fuzzy semantic discovery. Repository text search is better"
    " for exact strings, function names, config keys, and error codes. File reading"
    " is required for current authoritative contents before modifying code or docs."
    " Never modify vector database chunks directly."
    "\n"
    "Provides semantic search that understands meaning --"
    " unlike grep or text matching,"
    " it finds relevant code even when exact keywords are unknown."
)


# === Pydantic Models for Tool Inputs/Outputs ===


class CodeChunkResult(BaseModel):
    """A single code chunk result."""

    file_path: str = Field(description="Relative path to the file")
    language: str = Field(description="Programming language")
    content: str = Field(description="The code content")
    start_line: int = Field(description="Starting line number (1-indexed)")
    end_line: int = Field(description="Ending line number (1-indexed)")
    score: float = Field(description="Similarity score (0-1, higher is better)")


class SearchResultModel(BaseModel):
    """Result from search tool."""

    success: bool
    results: list[CodeChunkResult] = Field(default_factory=list)
    total_returned: int = Field(default=0)
    offset: int = Field(default=0)
    message: str | None = None


class RepoSourceModel(BaseModel):
    path: str
    line_start: int
    line_end: int
    heading: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    language: str | None = None
    content_hash: str | None = None
    chunk_hash: str | None = None


class RepoHitModel(BaseModel):
    content_type: str
    score: float
    content: str
    source: RepoSourceModel


class RepoSearchResultModel(BaseModel):
    success: bool
    query: str
    hits: list[RepoHitModel] = Field(default_factory=list)
    total_returned: int = 0
    offset: int = 0
    message: str | None = None


class FileRangeResultModel(BaseModel):
    success: bool
    path: str
    line_start: int
    line_end: int
    content: str = ""
    message: str | None = None


# === Daemon-backed MCP server factory ===


def create_mcp_server(project_root: str) -> FastMCP:
    """Create a lightweight MCP server that delegates to the daemon."""
    mcp = FastMCP("rag4trex", instructions=_MCP_INSTRUCTIONS)

    @mcp.tool(
        name="search",
        description=(
            "Semantic code search across the entire codebase"
            " -- finds code by meaning, not just text matching."
            " Use this instead of grep/glob when you need to find implementations,"
            " understand how features work,"
            " or locate related code without knowing exact names or keywords."
            " Accepts natural language queries"
            " (e.g., 'authentication logic', 'database connection handling')"
            " or code snippets."
            " Returns matching code chunks with file paths,"
            " line numbers, and relevance scores."
            " Start with a small limit (e.g., 5);"
            " if most results look relevant, use offset to paginate for more."
        ),
    )
    async def search(
        query: str = Field(
            description=(
                "Natural language query or code snippet to search for."
                " Examples: 'error handling middleware',"
                " 'how are users authenticated',"
                " 'database connection pool',"
                " or paste a code snippet to find similar code."
            )
        ),
        limit: int = Field(
            default=5,
            ge=1,
            le=100,
            description="Maximum number of results to return (1-100)",
        ),
        offset: int = Field(
            default=0,
            ge=0,
            description="Number of results to skip for pagination",
        ),
        refresh_index: bool = Field(
            default=True,
            description=(
                "Whether to incrementally update the index before searching."
                " Set to False for faster consecutive queries"
                " when the codebase hasn't changed."
            ),
        ),
        languages: list[str] | None = Field(
            default=None,
            description="Filter by programming language(s). Example: ['python', 'typescript']",
        ),
        paths: list[str] | None = Field(
            default=None,
            description=(
                "Filter by file path pattern(s) using GLOB wildcards (* and ?)."
                " Example: ['src/utils/*', '*.py']"
            ),
        ),
        mode: str = Field(
            default="semantic",
            description=(
                "Search mode. Currently semantic is implemented; hybrid/keyword"
                " are accepted for schema stability."
            ),
        ),
    ) -> dict[str, Any]:
        """Query the codebase index via the daemon."""
        from . import client as _client

        loop = asyncio.get_event_loop()
        try:
            if refresh_index:
                await loop.run_in_executor(None, lambda: _client.index(project_root))
            resp = await loop.run_in_executor(
                None,
                lambda: _client.search(
                    project_root=project_root,
                    query=query,
                    languages=languages,
                    paths=paths,
                    limit=limit,
                    offset=offset,
                    mode=mode,
                ),
            )
            return search_response_to_dict(resp, index="code")
        except Exception as e:
            return error_envelope("CONFIG_INVALID", f"Query failed: {e!s}", {"query": query})

    @mcp.tool(
        name="search_code",
        description="Semantic code search returning repo-rag-search-v1 JSON envelope.",
    )
    async def search_code(
        query: str = Field(description="Natural language query or code snippet."),
        language: str | None = Field(default=None, description="Optional single language filter."),
        path_prefix: str | None = Field(default=None, description="Optional relative path prefix."),
        top_k: int = Field(default=5, ge=1, le=100, description="Maximum results to return"),
        mode: str = Field(default="semantic", description="Search mode."),
        refresh_index: bool = Field(
            default=True,
            description="Refresh code index before searching.",
        ),
    ) -> dict[str, Any]:
        paths = None
        if path_prefix:
            paths = [path_prefix if any(ch in path_prefix for ch in "*?[") else f"{path_prefix}*"]
        return await search(
            query=query,
            limit=top_k,
            offset=0,
            refresh_index=refresh_index,
            languages=[language] if language else None,
            paths=paths,
            mode=mode,
        )

    @mcp.tool(
        name="search_docs",
        description=(
            "Semantic search across Markdown documentation. Use for fuzzy discovery of"
            " documentation sections. Use shell/editor file reads afterward for"
            " authoritative current file contents."
        ),
    )
    async def search_docs(
        query: str = Field(description="Natural language documentation query."),
        path_prefix: str | None = Field(
            default=None,
            description="Optional relative path prefix such as 'docs/' or 'README'.",
        ),
        top_k: int = Field(default=5, ge=1, le=100, description="Maximum results to return"),
        mode: str = Field(default="semantic", description="Search mode."),
        refresh_index: bool = Field(
            default=True,
            description="Whether to incrementally update the docs index before searching.",
        ),
    ) -> dict[str, Any]:
        from . import client as _client

        loop = asyncio.get_event_loop()
        try:
            if refresh_index:
                await loop.run_in_executor(
                    None, lambda: _client.index(project_root, index_type="docs")
                )
            resp = await loop.run_in_executor(
                None,
                lambda: _client.search_docs(
                    project_root=project_root,
                    query=query,
                    path_prefix=path_prefix,
                    limit=top_k,
                    mode=mode,
                ),
            )
            return search_response_to_dict(resp, index="docs")
        except Exception as e:
            return error_envelope("CONFIG_INVALID", f"Query failed: {e!s}", {"query": query})

    @mcp.tool(
        name="search_repo",
        description=(
            "Semantic search across code and docs indexes. Use content_type to limit"
            " to 'code' or 'docs'. Results are discovery hints, not a replacement for"
            " reading real files before editing."
        ),
    )
    async def search_repo(
        query: str = Field(description="Natural language query or code/documentation snippet."),
        content_type: str | None = Field(
            default=None,
            description="Optional filter: 'code' or 'docs'.",
        ),
        path_prefix: str | None = Field(default=None, description="Optional relative path prefix."),
        top_k: int = Field(default=5, ge=1, le=100, description="Maximum results to return"),
        mode: str = Field(default="semantic", description="Search mode."),
        refresh_index: bool = Field(
            default=True,
            description="Whether to incrementally update relevant indexes before searching.",
        ),
    ) -> dict[str, Any]:
        from . import client as _client

        loop = asyncio.get_event_loop()
        try:
            if refresh_index:
                if content_type in {"docs", "documentation"}:
                    index_type = "docs"
                elif content_type == "code":
                    index_type = "code"
                else:
                    index_type = "all"
                await loop.run_in_executor(
                    None,
                    lambda: _client.index(project_root, index_type=index_type),
                )
            resp = await loop.run_in_executor(
                None,
                lambda: _client.search_repo(
                    project_root=project_root,
                    query=query,
                    content_type=content_type,
                    path_prefix=path_prefix,
                    limit=top_k,
                    mode=mode,
                ),
            )
            index = "repo" if content_type is None else content_type
            return search_response_to_dict(resp, index=index)
        except Exception as e:
            return error_envelope("CONFIG_INVALID", f"Query failed: {e!s}", {"query": query})

    @mcp.tool(
        name="locate_repo",
        description="Locate likely files or documentation sections across repository indexes.",
    )
    async def locate_repo(
        query: str = Field(description="Natural language query for what to locate."),
        content_type: str | None = Field(
            default=None,
            description="Optional filter: 'code' or 'docs'.",
        ),
        path_prefix: str | None = Field(default=None, description="Optional relative path prefix."),
        top_k: int = Field(default=5, ge=1, le=100, description="Maximum results to return"),
    ) -> dict[str, Any]:
        from . import client as _client

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                lambda: _client.search_repo(
                    project_root=project_root,
                    query=query,
                    content_type=content_type,
                    path_prefix=path_prefix,
                    limit=top_k,
                ),
            )
            index = "repo" if content_type is None else content_type
            return locate_response_to_dict(resp, index=index)
        except Exception as e:
            return error_envelope("CONFIG_INVALID", f"Locate failed: {e!s}", {"query": query})

    @mcp.tool(
        name="get_index_status",
        description="Return structured code/docs index status for the current project.",
    )
    async def get_index_status() -> dict[str, Any]:
        from . import client as _client

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, lambda: _client.project_status(project_root))
            return {
                "schema_version": "repo-rag-index-status-v1",
                "indexing": resp.indexing,
                "code": {
                    "index_exists": resp.index_exists,
                    "chunks": resp.total_chunks,
                    "files": resp.total_files,
                    "languages": resp.languages,
                },
                "docs": {
                    "index_exists": resp.docs_index_exists,
                    "chunks": resp.docs_total_chunks,
                    "files": resp.docs_total_files,
                },
            }
        except Exception as e:
            return error_envelope("CONFIG_INVALID", f"Status failed: {e!s}")

    return mcp


# Keep the old `mcp` global for backward compatibility in __init__.py
mcp: FastMCP | None = None


# === Backward-compatible entry point ===


def _convert_embedding_model(env_model: str) -> tuple[str, str]:
    """Convert old COCOINDEX_CODE_EMBEDDING_MODEL to (provider, model)."""
    sbert_prefix = "sbert/"
    if env_model.startswith(sbert_prefix):
        return "sentence-transformers", env_model[len(sbert_prefix) :]
    return "litellm", env_model


def main() -> None:
    """Backward-compatible entry point for the MCP server CLI.

    Auto-detects/creates settings from env vars, then delegates to daemon.
    """
    import argparse

    from .settings import (
        EmbeddingSettings,
        LanguageOverride,
        default_project_settings,
        default_user_settings,
        existing_project_settings_path,
        find_legacy_project_root,
        find_project_root,
        save_project_settings,
        save_user_settings,
        user_settings_path,
    )

    parser = argparse.ArgumentParser(
        prog="rag4trex",
        description="MCP server for codebase indexing and querying.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Run the MCP server (default)")
    subparsers.add_parser("index", help="Build/refresh the index and report stats")
    args = parser.parse_args()

    # --- Discover project root ---
    cwd = Path.cwd()
    project_root = find_project_root(cwd)

    if project_root is None:
        # Try env var
        env_root = os.environ.get("COCOINDEX_CODE_ROOT_PATH")
        if env_root:
            project_root = Path(env_root).resolve()
        else:
            # Use marker-based discovery
            legacy_root = find_legacy_project_root(cwd)
            project_root = legacy_root if legacy_root is not None else cwd

    # --- Auto-create project settings if needed ---
    proj_settings_file = existing_project_settings_path(project_root)
    if proj_settings_file is None:
        ps = default_project_settings()

        # Migrate COCOINDEX_CODE_EXCLUDED_PATTERNS
        raw_excluded = os.environ.get("COCOINDEX_CODE_EXCLUDED_PATTERNS", "").strip()
        if raw_excluded:
            try:
                extra_excluded = json.loads(raw_excluded)
                if isinstance(extra_excluded, list):
                    ps.exclude_patterns.extend(
                        p.strip() for p in extra_excluded if isinstance(p, str) and p.strip()
                    )
            except json.JSONDecodeError:
                pass

        # Migrate COCOINDEX_CODE_EXTRA_EXTENSIONS
        raw_extra = os.environ.get("COCOINDEX_CODE_EXTRA_EXTENSIONS", "")
        for token in raw_extra.split(","):
            token = token.strip()
            if not token:
                continue
            if ":" in token:
                ext, lang = token.split(":", 1)
                ext = ext.strip()
                lang = lang.strip()
                ps.include_patterns.append(f"**/*.{ext}")
                if lang:
                    ps.language_overrides.append(LanguageOverride(ext=ext, lang=lang))
            else:
                ps.include_patterns.append(f"**/*.{token}")

        save_project_settings(project_root, ps)

    # --- Auto-create user settings if needed ---
    user_file = user_settings_path()
    if not user_file.is_file():
        us = default_user_settings()

        # Migrate COCOINDEX_CODE_EMBEDDING_MODEL
        env_model = os.environ.get("COCOINDEX_CODE_EMBEDDING_MODEL", "")
        if env_model:
            provider, model = _convert_embedding_model(env_model)
            us.embedding = EmbeddingSettings(provider=provider, model=model)

        # Migrate COCOINDEX_CODE_DEVICE
        env_device = os.environ.get("COCOINDEX_CODE_DEVICE")
        if env_device:
            us.embedding.device = env_device

        save_user_settings(us)

    # --- Delegate to daemon ---
    from . import client as _client
    from .protocol import IndexingProgress

    if args.command == "index":
        import sys

        from rich.console import Console
        from rich.live import Live
        from rich.spinner import Spinner

        from .cli import _format_progress

        err_console = Console(stderr=True)
        last_progress_line: str | None = None

        with Live(Spinner("dots", "Indexing..."), console=err_console, transient=True) as live:

            def _on_waiting() -> None:
                live.update(
                    Spinner(
                        "dots",
                        "Another indexing is ongoing, waiting for it to finish...",
                    )
                )

            def _on_progress(progress: IndexingProgress) -> None:
                nonlocal last_progress_line
                last_progress_line = f"Indexing: {_format_progress(progress)}"
                live.update(Spinner("dots", last_progress_line))

            resp = _client.index(
                str(project_root), on_progress=_on_progress, on_waiting=_on_waiting
            )

        if last_progress_line is not None:
            print(last_progress_line, file=sys.stderr)

        if resp.success:
            st = _client.project_status(str(project_root))
            print("\nIndex stats:")
            print(f"  Chunks: {st.total_chunks}")
            print(f"  Files:  {st.total_files}")
            if st.languages:
                print("  Languages:")
                for lang, count in sorted(st.languages.items(), key=lambda x: -x[1]):
                    print(f"    {lang}: {count} chunks")
        else:
            print(f"Indexing failed: {resp.message}")
    else:
        # Default: run MCP server
        mcp_server = create_mcp_server(str(project_root))

        async def _serve() -> None:
            from .cli import _bg_index

            asyncio.create_task(_bg_index(str(project_root)))
            await mcp_server.run_stdio_async()

        asyncio.run(_serve())
