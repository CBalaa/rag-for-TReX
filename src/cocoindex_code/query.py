"""Query implementation for codebase search."""

from __future__ import annotations

import heapq
import json
import sqlite3
from pathlib import Path
from typing import Any

from .schema import DocsQueryResult, QueryResult
from .shared import EMBEDDER, QUERY_EMBED_PARAMS, SQLITE_DB


def _l2_to_score(distance: float) -> float:
    """Convert L2 distance to cosine similarity (exact for unit vectors)."""
    return 1.0 - distance * distance / 2.0


_CODE_EXTRA_COLUMNS = [
    "char_start",
    "char_end",
    "content_hash",
    "chunk_hash",
    "chunk_index",
    "chunker_version",
    "symbol",
    "symbol_type",
    "signature",
    "parent_symbol",
    "imports",
    "docstring",
]


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _code_select_columns(conn: sqlite3.Connection) -> tuple[str, bool]:
    columns = _table_columns(conn, "code_chunks_vec")
    has_extra = all(col in columns for col in _CODE_EXTRA_COLUMNS)
    if not has_extra:
        return "file_path, language, content, start_line, end_line", False
    return (
        "file_path, language, content, start_line, end_line, "
        "char_start, char_end, content_hash, chunk_hash, chunk_index, chunker_version, "
        "symbol, symbol_type, signature, parent_symbol, imports, docstring",
        True,
    )


def _knn_query(
    conn: sqlite3.Connection,
    embedding_bytes: bytes,
    k: int,
    language: str | None = None,
) -> tuple[list[tuple[Any, ...]], bool]:
    """Run a vec0 KNN query, optionally constrained to a language partition."""
    select_columns, has_extra = _code_select_columns(conn)
    if language is not None:
        return conn.execute(
            f"""
            SELECT {select_columns}, distance
            FROM code_chunks_vec
            WHERE embedding MATCH ? AND k = ? AND language = ?
            ORDER BY distance
            """,
            (embedding_bytes, k, language),
        ).fetchall(), has_extra
    return conn.execute(
        f"""
        SELECT {select_columns}, distance
        FROM code_chunks_vec
        WHERE embedding MATCH ? AND k = ?
        ORDER BY distance
        """,
        (embedding_bytes, k),
    ).fetchall(), has_extra


def _full_scan_query(
    conn: sqlite3.Connection,
    embedding_bytes: bytes,
    limit: int,
    offset: int,
    languages: list[str] | None = None,
    paths: list[str] | None = None,
) -> tuple[list[tuple[Any, ...]], bool]:
    """Full scan with SQL-level distance computation and filtering."""
    select_columns, has_extra = _code_select_columns(conn)
    conditions: list[str] = []
    params: list[Any] = [embedding_bytes]

    if languages:
        placeholders = ",".join("?" for _ in languages)
        conditions.append(f"language IN ({placeholders})")
        params.extend(languages)

    if paths:
        path_clauses = " OR ".join("file_path GLOB ?" for _ in paths)
        conditions.append(f"({path_clauses})")
        params.extend(paths)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    return conn.execute(
        f"""
        SELECT {select_columns}, vec_distance_L2(embedding, ?) as distance
        FROM code_chunks_vec
        {where}
        ORDER BY distance
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall(), has_extra


def _docs_knn_query(
    conn: sqlite3.Connection,
    embedding_bytes: bytes,
    k: int,
) -> list[tuple[Any, ...]]:
    return conn.execute(
        """
        SELECT content_type, file_path, heading, heading_path, content,
               line_start, line_end, char_start, char_end, content_hash,
               chunk_hash, chunk_index, chunker_version, frontmatter, distance
        FROM docs_chunks_vec
        WHERE embedding MATCH ? AND k = ? AND content_type = 'documentation'
        ORDER BY distance
        """,
        (embedding_bytes, k),
    ).fetchall()


def _docs_full_scan_query(
    conn: sqlite3.Connection,
    embedding_bytes: bytes,
    limit: int,
    offset: int,
    path_prefix: str | None = None,
) -> list[tuple[Any, ...]]:
    conditions = ["content_type = 'documentation'"]
    params: list[Any] = [embedding_bytes]
    if path_prefix:
        conditions.append("file_path GLOB ?")
        params.append(_prefix_to_glob(path_prefix))
    params.extend([limit, offset])
    return conn.execute(
        f"""
        SELECT content_type, file_path, heading, heading_path, content,
               line_start, line_end, char_start, char_end, content_hash,
               chunk_hash, chunk_index, chunker_version, frontmatter,
               vec_distance_L2(embedding, ?) as distance
        FROM docs_chunks_vec
        WHERE {' AND '.join(conditions)}
        ORDER BY distance
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()


def _prefix_to_glob(path_prefix: str) -> str:
    prefix = path_prefix.strip("/")
    if not prefix:
        return "*"
    if any(ch in prefix for ch in "*?["):
        return prefix
    return f"{prefix}*"


def _json_list(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded]


def _json_dict(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _query_result_from_row(row: tuple[Any, ...], has_extra: bool) -> QueryResult:
    if not has_extra:
        file_path, language, content, start_line, end_line, distance = row
        return QueryResult(
            file_path=file_path,
            language=language,
            content=content,
            start_line=start_line,
            end_line=end_line,
            score=_l2_to_score(distance),
        )
    (
        file_path,
        language,
        content,
        start_line,
        end_line,
        char_start,
        char_end,
        content_hash,
        chunk_hash,
        chunk_index,
        chunker_version,
        symbol,
        symbol_type,
        signature,
        parent_symbol,
        imports,
        docstring,
        distance,
    ) = row
    return QueryResult(
        file_path=file_path,
        language=language,
        content=content,
        start_line=start_line,
        end_line=end_line,
        score=_l2_to_score(distance),
        char_start=char_start,
        char_end=char_end,
        content_hash=content_hash,
        chunk_hash=chunk_hash,
        chunk_index=chunk_index,
        chunker_version=chunker_version,
        symbol=symbol,
        symbol_type=symbol_type,
        signature=signature,
        parent_symbol=parent_symbol,
        imports=_json_list(imports or "[]"),
        docstring=docstring,
    )


async def query_codebase(
    query: str,
    target_sqlite_db_path: Path,
    env: Any,
    limit: int = 10,
    offset: int = 0,
    languages: list[str] | None = None,
    paths: list[str] | None = None,
) -> list[QueryResult]:
    """
    Perform vector similarity search using vec0 KNN index.

    Uses sqlite-vec's vec0 virtual table for indexed nearest-neighbor search.
    Language filtering uses vec0 partition keys for exact index-level filtering.
    Path filtering triggers a full scan with distance computation.
    """
    if not target_sqlite_db_path.exists():
        raise RuntimeError(
            f"Index database not found at {target_sqlite_db_path}. "
            "Please run a query with refresh_index=True first."
        )

    db = env.get_context(SQLITE_DB)
    embedder = env.get_context(EMBEDDER)
    query_params = env.get_context(QUERY_EMBED_PARAMS)

    # Generate query embedding.
    query_embedding = await embedder.embed(query, **query_params)

    embedding_bytes = query_embedding.astype("float32").tobytes()

    with db.readonly() as conn:
        if paths:
            rows, has_extra = _full_scan_query(
                conn, embedding_bytes, limit, offset, languages, paths
            )
        elif not languages or len(languages) == 1:
            lang = languages[0] if languages else None
            rows, has_extra = _knn_query(conn, embedding_bytes, limit + offset, lang)
        else:
            fetch_k = limit + offset
            rows_by_lang = [
                row
                for lang in languages
                for row in _knn_query(conn, embedding_bytes, fetch_k, lang)[0]
            ]
            _, has_extra = _knn_query(conn, embedding_bytes, 1, languages[0])
            rows = heapq.nsmallest(
                fetch_k,
                rows_by_lang,
                key=lambda r: r[-1],
            )

    if not paths:
        rows = rows[offset:]

    return [_query_result_from_row(row, has_extra) for row in rows]


async def query_docs(
    query: str,
    target_sqlite_db_path: Path,
    env: Any,
    limit: int = 10,
    offset: int = 0,
    path_prefix: str | None = None,
) -> list[DocsQueryResult]:
    """Perform vector similarity search against the docs index."""
    if not target_sqlite_db_path.exists():
        raise RuntimeError(
            f"Index database not found at {target_sqlite_db_path}. "
            "Please build the docs index first."
        )

    db = env.get_context(SQLITE_DB)
    embedder = env.get_context(EMBEDDER)
    query_params = env.get_context(QUERY_EMBED_PARAMS)
    query_embedding = await embedder.embed(query, **query_params)
    embedding_bytes = query_embedding.astype("float32").tobytes()

    with db.readonly() as conn:
        if path_prefix:
            rows = _docs_full_scan_query(conn, embedding_bytes, limit, offset, path_prefix)
        else:
            rows = _docs_knn_query(conn, embedding_bytes, limit + offset)

    if not path_prefix:
        rows = rows[offset:]

    return [
        DocsQueryResult(
            content_type=content_type,
            file_path=file_path,
            heading=heading,
            heading_path=_json_list(heading_path),
            content=content,
            line_start=line_start,
            line_end=line_end,
            char_start=char_start,
            char_end=char_end,
            content_hash=content_hash,
            chunk_hash=chunk_hash,
            chunk_index=chunk_index,
            chunker_version=chunker_version,
            frontmatter=_json_dict(frontmatter),
            score=_l2_to_score(distance),
        )
        for (
            content_type,
            file_path,
            heading,
            heading_path,
            content,
            line_start,
            line_end,
            char_start,
            char_end,
            content_hash,
            chunk_hash,
            chunk_index,
            chunker_version,
            frontmatter,
            distance,
        ) in rows
    ]
