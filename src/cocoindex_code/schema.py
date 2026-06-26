"""Data models for CocoIndex Code."""

from dataclasses import dataclass
from typing import Any


@dataclass
class CodeChunk:
    """Represents an indexed code chunk stored in SQLite."""

    id: int
    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    embedding: Any  # NDArray - type hint relaxed for compatibility


@dataclass
class QueryResult:
    """Result from a vector similarity query."""

    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    score: float
    char_start: int | None = None
    char_end: int | None = None
    content_hash: str | None = None
    chunk_hash: str | None = None
    chunk_index: int | None = None
    chunker_version: str | None = None
    symbol: str | None = None
    symbol_type: str | None = None
    signature: str | None = None
    parent_symbol: str | None = None
    imports: list[str] | None = None
    docstring: str | None = None


@dataclass
class DocsQueryResult:
    """Result from a documentation vector similarity query."""

    content_type: str
    file_path: str
    heading: str
    heading_path: list[str]
    content: str
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    content_hash: str
    chunk_hash: str
    chunk_index: int
    chunker_version: str
    frontmatter: dict[str, Any]
    score: float
