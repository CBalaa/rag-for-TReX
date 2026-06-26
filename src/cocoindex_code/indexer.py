"""CocoIndex app for indexing codebases."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import cocoindex as coco
from cocoindex.connectors import localfs, sqlite
from cocoindex.connectors.sqlite import Vec0TableDef
from cocoindex.ops.text import RecursiveSplitter, detect_code_language
from cocoindex.resources.chunk import Chunk
from cocoindex.resources.id import IdGenerator

from .chunking import CHUNKER_REGISTRY
from .file_walk import build_matcher
from .settings import load_project_settings
from .shared import (
    CODEBASE_DIR,
    EMBEDDER,
    INDEXING_EMBED_PARAMS,
    SQLITE_DB,
    CodeChunk,
)

# Chunking configuration
CHUNK_SIZE = 1000
MIN_CHUNK_SIZE = 250
CHUNK_OVERLAP = 150
CODE_CHUNKER_VERSION = "code-ast-v1"

# Chunking splitter (stateless, can be module-level)
splitter = RecursiveSplitter()


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


def _signature_from_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if len(stripped) > 240:
        return stripped[:237] + "..."
    return stripped


def _python_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.extend(f"{module}.{alias.name}".strip(".") for alias in node.names)
    return sorted(set(imports))


def _python_symbols(content: str) -> tuple[list[dict[str, Any]], list[str], str | None]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return [], [], None

    symbols: list[dict[str, Any]] = []
    module_doc = ast.get_docstring(tree)

    def visit_body(body: list[ast.stmt], parents: list[str]) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                name = ".".join([*parents, node.name])
                symbols.append(
                    {
                        "name": name,
                        "type": "class",
                        "line_start": node.lineno,
                        "line_end": getattr(node, "end_lineno", node.lineno),
                        "parent": ".".join(parents) if parents else None,
                        "docstring": ast.get_docstring(node),
                    }
                )
                visit_body(node.body, [*parents, node.name])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = ".".join([*parents, node.name])
                symbols.append(
                    {
                        "name": name,
                        "type": "method" if parents else "function",
                        "line_start": node.lineno,
                        "line_end": getattr(node, "end_lineno", node.lineno),
                        "parent": ".".join(parents) if parents else None,
                        "docstring": ast.get_docstring(node),
                    }
                )
                visit_body(node.body, [*parents, node.name])

    visit_body(tree.body, [])
    return symbols, _python_imports(tree), module_doc


def _best_symbol_for_range(
    symbols: list[dict[str, Any]],
    start_line: int,
    end_line: int,
) -> dict[str, Any] | None:
    overlapping = [
        sym
        for sym in symbols
        if int(sym["line_start"]) <= end_line and int(sym["line_end"]) >= start_line
    ]
    if not overlapping:
        return None
    return max(
        overlapping,
        key=lambda sym: (
            int(sym["line_start"]) >= start_line and int(sym["line_end"]) <= end_line,
            len(str(sym["name"]).split(".")),
            -int(sym["line_end"]) + int(sym["line_start"]),
        ),
    )


def _heuristic_symbol(chunk_text: str, language: str) -> tuple[str | None, str | None, str | None]:
    del language
    for line in chunk_text.splitlines():
        stripped = line.strip()
        match = re.match(
            r"(?:async\s+)?(?:function\s+|def\s+|class\s+)?([A-Za-z_$][\w$]*)\s*(?:\(|[:{=])",
            stripped,
        )
        if match:
            symbol_type = "class" if stripped.startswith("class ") else "function"
            return match.group(1), symbol_type, _signature_from_line(stripped)
    return None, None, None


@coco.fn(memo=True)
async def process_file(
    file: localfs.File,
    table: sqlite.TableTarget[CodeChunk],
) -> None:
    """Process a single file: chunk, embed, and store."""
    embedder = coco.use_context(EMBEDDER)
    indexing_params = coco.use_context(INDEXING_EMBED_PARAMS)

    try:
        content = await file.read_text()
    except UnicodeDecodeError:
        return

    if not content.strip():
        return

    suffix = file.file_path.path.suffix
    project_root = coco.use_context(CODEBASE_DIR)
    ps = load_project_settings(project_root)
    ext_lang_map = {f".{lo.ext}": lo.lang for lo in ps.language_overrides}
    language = (
        ext_lang_map.get(suffix)
        or detect_code_language(filename=file.file_path.path.name)
        or "text"
    )

    chunker_registry = coco.use_context(CHUNKER_REGISTRY)
    chunker = chunker_registry.get(suffix)
    if chunker is not None:
        language_override, chunks = chunker(Path(file.file_path.path), content)
        if language_override is not None:
            language = language_override
    else:
        chunks = splitter.split(
            content,
            chunk_size=CHUNK_SIZE,
            min_chunk_size=MIN_CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            language=language,
        )

    id_gen = IdGenerator()
    lines = content.splitlines(keepends=True)
    offsets = _line_offsets(lines)
    content_hash = _sha256(content)
    py_symbols: list[dict[str, Any]] = []
    imports: list[str] = []
    module_docstring: str | None = None
    if language == "python":
        py_symbols, imports, module_docstring = _python_symbols(content)

    async def process(indexed: tuple[int, Chunk]) -> None:
        chunk_index, chunk = indexed
        char_start = _line_char_start(offsets, chunk.start.line)
        char_end = _line_char_end(offsets, lines, chunk.end.line, len(content))
        chunk_hash = _sha256(
            "\n".join(
                [
                    file.file_path.path.as_posix(),
                    str(chunk.start.line),
                    str(chunk.end.line),
                    str(char_start),
                    str(char_end),
                    chunk.text,
                    CODE_CHUNKER_VERSION,
                ]
            )
        )
        symbol = _best_symbol_for_range(py_symbols, chunk.start.line, chunk.end.line)
        if symbol is None:
            symbol_name, symbol_type, signature = _heuristic_symbol(chunk.text, language)
            parent_symbol = None
            docstring = module_docstring
        else:
            symbol_name = str(symbol["name"])
            symbol_type = str(symbol["type"])
            parent_symbol = symbol["parent"]
            signature = _signature_from_line(lines[int(symbol["line_start"]) - 1])
            docstring = symbol["docstring"] or module_docstring
        table.declare_row(
            row=CodeChunk(
                id=await id_gen.next_id(chunk_hash),
                file_path=file.file_path.path.as_posix(),
                language=language,
                content=chunk.text,
                start_line=chunk.start.line,
                end_line=chunk.end.line,
                char_start=char_start,
                char_end=char_end,
                content_hash=content_hash,
                chunk_hash=chunk_hash,
                chunk_index=chunk_index,
                chunker_version=CODE_CHUNKER_VERSION,
                symbol=symbol_name,
                symbol_type=symbol_type,
                signature=signature,
                parent_symbol=parent_symbol,
                imports=json.dumps(imports, ensure_ascii=False),
                docstring=docstring,
                embedding=await embedder.embed(chunk.text, **indexing_params),
            )
        )

    await coco.map(process, list(enumerate(chunks)))


@coco.fn
async def indexer_main() -> None:
    """Main indexing function - walks files and processes each."""
    project_root = coco.use_context(CODEBASE_DIR)
    ps = load_project_settings(project_root)

    table = await sqlite.mount_table_target(
        db=SQLITE_DB,
        table_name="code_chunks_vec",
        table_schema=await sqlite.TableSchema.from_class(
            CodeChunk,
            primary_key=["id"],
        ),
        virtual_table_def=Vec0TableDef(
            partition_key_columns=["language"],
            auxiliary_columns=[
                "file_path",
                "content",
                "start_line",
                "end_line",
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
            ],
        ),
    )

    matcher = build_matcher(
        project_root,
        ps.include_patterns,
        ps.exclude_patterns,
        forced_excluded_patterns=ps.always_exclude,
        ragignore_file=ps.scan.ragignore_file,
    )

    files = localfs.walk_dir(
        CODEBASE_DIR,
        recursive=True,
        path_matcher=matcher,
    )

    await coco.mount_each(
        coco.component_subpath(coco.Symbol("process_file")), process_file, files.items(), table
    )
