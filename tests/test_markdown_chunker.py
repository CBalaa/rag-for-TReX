"""Tests for Markdown documentation chunking."""

from __future__ import annotations

from pathlib import Path

from cocoindex_code.markdown_chunker import CHUNKER_VERSION, chunk_markdown


def test_chunks_by_heading_with_metadata() -> None:
    content = """\
# Guide

Intro text.

## Auth

Set AUTH_TOKEN before deploy.

## Database

Set DB_URL.
"""
    chunks = chunk_markdown(Path("docs/guide.md"), content)

    assert [c.heading for c in chunks] == ["Guide", "Auth", "Database"]
    assert chunks[1].heading_path == ["Guide", "Auth"]
    assert chunks[1].path == "docs/guide.md"
    assert chunks[1].content_type == "documentation"
    assert chunks[1].chunker_version == CHUNKER_VERSION
    assert chunks[1].content_hash.startswith("sha256:")
    assert chunks[1].chunk_hash.startswith("sha256:")
    assert "Heading: Guide > Auth" not in chunks[1].content


def test_line_and_char_ranges_are_source_ranges() -> None:
    content = "# Title\n\nAlpha\nBeta\n\n## Next\nGamma\n"
    chunks = chunk_markdown(Path("README.md"), content)
    first = chunks[0]
    second = chunks[1]

    assert first.line_start == 1
    assert first.line_end == 4
    assert content[first.char_start : first.char_end] == "# Title\n\nAlpha\nBeta\n"
    assert second.line_start == 6
    assert second.line_end == 7
    assert content[second.char_start : second.char_end] == "## Next\nGamma\n"


def test_fenced_code_block_is_not_split_or_treated_as_heading() -> None:
    content = """\
# Setup

Before.

```markdown
# Not a real heading
still code
```

After.

## Real
Done.
"""
    chunks = chunk_markdown(Path("docs/setup.md"), content, max_chars=45)

    setup_chunks = [c for c in chunks if c.heading == "Setup"]
    assert len(setup_chunks) >= 2
    assert any(
        "# Not a real heading" in c.content and "still code" in c.content
        for c in setup_chunks
    )
    assert all("Not a real heading" not in c.heading_path for c in chunks)
    assert chunks[-1].heading == "Real"


def test_frontmatter_is_parsed_and_omitted_from_source_chunks() -> None:
    content = """\
---
title: Deployment
tags:
  - auth
draft: false
---
# Deploy

Use production credentials.
"""
    chunks = chunk_markdown(Path("docs/deploy.md"), content)

    assert len(chunks) == 1
    assert chunks[0].frontmatter == {"title": "Deployment", "tags": ["auth"], "draft": False}
    assert chunks[0].line_start == 7
    assert chunks[0].heading_path == ["Deploy"]


def test_markdown_table_stays_together_when_splitting() -> None:
    content = """\
# Config

Intro paragraph that will form one block.

| Name | Value |
| ---- | ----- |
| AUTH_TOKEN | required |
| DB_URL | required |

Trailing paragraph that may split.
"""
    chunks = chunk_markdown(Path("docs/config.md"), content, max_chars=80)

    table_chunks = [c for c in chunks if "| AUTH_TOKEN | required |" in c.content]
    assert len(table_chunks) == 1
    assert "| Name | Value |" in table_chunks[0].content
    assert "| DB_URL | required |" in table_chunks[0].content
