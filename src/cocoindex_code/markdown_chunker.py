"""Markdown-aware chunking for documentation indexing."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CHUNKER_VERSION = "markdown-v1"
DEFAULT_MAX_CHARS = 3000
DEFAULT_MIN_CHARS = 300

_HEADING_RE = re.compile(r"^(?P<indent> {0,3})(?P<marks>#{1,6})[ \t]+(?P<title>.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


@dataclass
class MarkdownChunk:
    """A documentation chunk with source-range and semantic metadata."""

    content: str
    path: str
    heading: str | None
    heading_path: list[str]
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    content_hash: str
    chunk_hash: str
    chunk_index: int
    chunker_version: str = CHUNKER_VERSION
    content_type: str = "documentation"
    frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Heading:
    line: int
    level: int
    title: str
    path: tuple[str, ...]


@dataclass(frozen=True)
class _Section:
    start_line: int
    end_line: int
    heading: _Heading | None


@dataclass(frozen=True)
class _Block:
    start_line: int
    end_line: int


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _line_offsets(lines: list[str]) -> list[int]:
    offsets: list[int] = []
    current = 0
    for line in lines:
        offsets.append(current)
        current += len(line)
    return offsets


def _line_char_start(offsets: list[int], line: int) -> int:
    if not offsets:
        return 0
    return offsets[max(0, line - 1)]


def _line_char_end(offsets: list[int], lines: list[str], line: int, content_len: int) -> int:
    if not lines:
        return 0
    if line >= len(lines):
        return content_len
    return offsets[line]


def _strip_heading_title(raw: str) -> str:
    title = raw.strip()
    if " #" in title:
        title = re.sub(r"\s+#+\s*$", "", title).strip()
    return title


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, Any], int]:
    """Return parsed frontmatter and first content line number."""
    if not lines or lines[0].strip() != "---":
        return {}, 1

    end_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() in {"---", "..."}:
            end_idx = idx
            break
    if end_idx is None:
        return {}, 1

    raw = "".join(lines[1:end_idx])
    try:
        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        parsed = {}
    frontmatter = parsed if isinstance(parsed, dict) else {}
    return frontmatter, end_idx + 2


def _heading_at(line: str, *, in_fence: bool) -> tuple[int, str] | None:
    if in_fence:
        return None
    match = _HEADING_RE.match(line.rstrip("\n\r"))
    if match is None:
        return None
    return len(match.group("marks")), _strip_heading_title(match.group("title"))


def _scan_headings(lines: list[str], first_content_line: int) -> list[_Heading]:
    headings: list[_Heading] = []
    stack: list[tuple[int, str]] = []
    in_fence = False
    fence_marker = ""

    for idx, line in enumerate(lines, start=1):
        fence_match = _FENCE_RE.match(line)
        if fence_match is not None:
            marker = fence_match.group("marker")
            if not in_fence:
                in_fence = True
                fence_marker = marker[0] * len(marker)
            elif marker.startswith(fence_marker[0]) and len(marker) >= len(fence_marker):
                in_fence = False
                fence_marker = ""
            continue

        if idx < first_content_line:
            continue
        heading = _heading_at(line, in_fence=in_fence)
        if heading is None:
            continue
        level, title = heading
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        headings.append(
            _Heading(line=idx, level=level, title=title, path=tuple(t for _, t in stack))
        )

    return headings


def _sections(
    lines: list[str], first_content_line: int, headings: list[_Heading]
) -> list[_Section]:
    if not lines:
        return []

    last_line = len(lines)
    sections: list[_Section] = []
    if not headings:
        if first_content_line <= last_line:
            sections.append(_Section(first_content_line, last_line, None))
        return sections

    if first_content_line < headings[0].line:
        sections.append(_Section(first_content_line, headings[0].line - 1, None))

    for idx, heading in enumerate(headings):
        end_line = headings[idx + 1].line - 1 if idx + 1 < len(headings) else last_line
        sections.append(_Section(heading.line, end_line, heading))
    return sections


def _is_table_start(lines: list[str], idx: int, end_idx: int) -> bool:
    if idx + 1 > end_idx:
        return False
    return "|" in lines[idx - 1] and _TABLE_SEPARATOR_RE.match(lines[idx]) is not None


def _blocks_for_section(lines: list[str], section: _Section) -> list[_Block]:
    blocks: list[_Block] = []
    current_start: int | None = None
    line = section.start_line
    in_fence = False
    fence_marker = ""

    def flush(end_line: int) -> None:
        nonlocal current_start
        if current_start is not None and end_line >= current_start:
            blocks.append(_Block(current_start, end_line))
        current_start = None

    while line <= section.end_line:
        text = lines[line - 1]
        stripped = text.strip()

        fence_match = _FENCE_RE.match(text)
        if fence_match is not None:
            if current_start is None:
                current_start = line
            marker = fence_match.group("marker")
            if not in_fence:
                in_fence = True
                fence_marker = marker[0] * len(marker)
            elif marker.startswith(fence_marker[0]) and len(marker) >= len(fence_marker):
                in_fence = False
                fence_marker = ""
                flush(line)
            line += 1
            continue

        if in_fence:
            if current_start is None:
                current_start = line
            line += 1
            continue

        if _is_table_start(lines, line, section.end_line):
            flush(line - 1)
            table_start = line
            line += 2
            while line <= section.end_line and "|" in lines[line - 1] and lines[line - 1].strip():
                line += 1
            blocks.append(_Block(table_start, line - 1))
            continue

        if not stripped:
            flush(line - 1)
            line += 1
            continue

        if current_start is None:
            current_start = line
        line += 1

    flush(section.end_line)
    return blocks


def _range_text(lines: list[str], start_line: int, end_line: int) -> str:
    return "".join(lines[start_line - 1 : end_line]).strip("\n")


def _prefix_heading_context(text: str, heading_path: list[str]) -> str:
    if not heading_path:
        return text
    first_line = text.lstrip().splitlines()[0] if text.strip() else ""
    if first_line.startswith("#"):
        return text
    return f"Heading: {' > '.join(heading_path)}\n\n{text}"


def _split_section(
    lines: list[str],
    section: _Section,
    offsets: list[int],
    path: str,
    content: str,
    content_hash: str,
    frontmatter: dict[str, Any],
    next_index: int,
    max_chars: int,
) -> tuple[list[MarkdownChunk], int]:
    blocks = _blocks_for_section(lines, section)
    if not blocks:
        return [], next_index

    heading = section.heading.title if section.heading is not None else None
    heading_path = list(section.heading.path) if section.heading is not None else []
    chunks: list[MarkdownChunk] = []
    group_start: int | None = None
    group_end: int | None = None

    def emit(start_line: int, end_line: int) -> None:
        nonlocal next_index
        raw_text = _range_text(lines, start_line, end_line)
        if not raw_text.strip():
            return
        chunk_content = _prefix_heading_context(raw_text, heading_path)
        char_start = _line_char_start(offsets, start_line)
        char_end = _line_char_end(offsets, lines, end_line, len(content))
        chunk_hash = _sha256(
            "\n".join(
                [
                    path,
                    str(start_line),
                    str(end_line),
                    str(char_start),
                    str(char_end),
                    chunk_content,
                    CHUNKER_VERSION,
                ]
            )
        )
        chunks.append(
            MarkdownChunk(
                content=chunk_content,
                path=path,
                heading=heading,
                heading_path=heading_path,
                line_start=start_line,
                line_end=end_line,
                char_start=char_start,
                char_end=char_end,
                content_hash=content_hash,
                chunk_hash=chunk_hash,
                chunk_index=next_index,
                frontmatter=dict(frontmatter),
            )
        )
        next_index += 1

    for block in blocks:
        if group_start is None:
            group_start = block.start_line
            group_end = block.end_line
            continue
        assert group_end is not None
        candidate = _range_text(lines, group_start, block.end_line)
        if len(candidate) > max_chars:
            emit(group_start, group_end)
            group_start = block.start_line
            group_end = block.end_line
        else:
            group_end = block.end_line

    if group_start is not None and group_end is not None:
        emit(group_start, group_end)

    return chunks, next_index


def chunk_markdown(
    path: Path,
    content: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[MarkdownChunk]:
    """Split Markdown content into source-range-preserving documentation chunks."""
    del min_chars  # Reserved for future cross-section merging.
    if not content.strip():
        return []

    lines = content.splitlines(keepends=True)
    offsets = _line_offsets(lines)
    frontmatter, first_content_line = _parse_frontmatter(lines)
    headings = _scan_headings(lines, first_content_line)
    sections = _sections(lines, first_content_line, headings)
    content_hash = _sha256(content)

    chunks: list[MarkdownChunk] = []
    next_index = 0
    for section in sections:
        section_chunks, next_index = _split_section(
            lines=lines,
            section=section,
            offsets=offsets,
            path=path.as_posix(),
            content=content,
            content_hash=content_hash,
            frontmatter=frontmatter,
            next_index=next_index,
            max_chars=max_chars,
        )
        chunks.extend(section_chunks)
    return chunks
