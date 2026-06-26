"""CocoIndex app for indexing Markdown documentation."""

from __future__ import annotations

import json

import cocoindex as coco
from cocoindex.connectors import localfs, sqlite
from cocoindex.connectors.sqlite import Vec0TableDef
from cocoindex.resources.id import IdGenerator

from .file_walk import build_docs_matcher
from .markdown_chunker import MarkdownChunk, chunk_markdown
from .shared import (
    CODEBASE_DIR,
    EMBEDDER,
    INDEXING_EMBED_PARAMS,
    SQLITE_DB,
    DocsChunk,
)


@coco.fn(memo=True)
async def process_docs_file(
    file: localfs.File,
    table: sqlite.TableTarget[DocsChunk],
) -> None:
    """Process a Markdown file into documentation chunks."""
    embedder = coco.use_context(EMBEDDER)
    indexing_params = coco.use_context(INDEXING_EMBED_PARAMS)

    try:
        content = await file.read_text()
    except UnicodeDecodeError:
        return

    if not content.strip():
        return

    chunks = chunk_markdown(file.file_path.path, content)
    id_gen = IdGenerator()

    async def process(chunk: MarkdownChunk) -> None:
        table.declare_row(
            row=DocsChunk(
                id=await id_gen.next_id(chunk.chunk_hash),
                content_type=chunk.content_type,
                file_path=file.file_path.path.as_posix(),
                heading=chunk.heading or "",
                heading_path=json.dumps(chunk.heading_path, ensure_ascii=False),
                content=chunk.content,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                content_hash=chunk.content_hash,
                chunk_hash=chunk.chunk_hash,
                chunk_index=chunk.chunk_index,
                chunker_version=chunk.chunker_version,
                frontmatter=json.dumps(chunk.frontmatter, ensure_ascii=False),
                embedding=await embedder.embed(chunk.content, **indexing_params),
            )
        )

    await coco.map(process, chunks)


@coco.fn
async def docs_indexer_main() -> None:
    """Main docs indexing function."""
    project_root = coco.use_context(CODEBASE_DIR)

    table = await sqlite.mount_table_target(
        db=SQLITE_DB,
        table_name="docs_chunks_vec",
        table_schema=await sqlite.TableSchema.from_class(
            DocsChunk,
            primary_key=["id"],
        ),
        virtual_table_def=Vec0TableDef(
            partition_key_columns=["content_type"],
            auxiliary_columns=[
                "file_path",
                "heading",
                "heading_path",
                "content",
                "line_start",
                "line_end",
                "char_start",
                "char_end",
                "content_hash",
                "chunk_hash",
                "chunk_index",
                "chunker_version",
                "frontmatter",
            ],
        ),
    )

    files = localfs.walk_dir(
        CODEBASE_DIR,
        recursive=True,
        path_matcher=build_docs_matcher(project_root),
    )

    await coco.mount_each(
        coco.component_subpath(coco.Symbol("process_docs_file")),
        process_docs_file,
        files.items(),
        table,
    )
