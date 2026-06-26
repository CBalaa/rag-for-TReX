---
name: ccc
description: "Use this skill when repository RAG search or location is needed through the provided MCP tools. Trigger phrases include 'search the codebase', 'find code related to', 'search docs', 'repo RAG', 'locate in repo', 'ccc', 'rag4trex'."
---

# ccc - MCP-Only Repo RAG

Use only the provided MCP tools for RAG discovery and repository location. Do not use the `ccc` CLI from this skill for search, indexing, or locate workflows.

## MCP Tools

Use these MCP tools:

- `search_code`: semantic search over code.
- `search_docs`: semantic search over Markdown documentation.
- `search_repo`: unified semantic search over code and documentation.
- `locate_repo`: compact location results for deciding which files/sections to inspect.
- `get_index_status`: structured code/docs index status.

Do not use RAG tools for final source-file reads.

## Search Rules

RAG is for fuzzy semantic discovery. Repository text/grep search is for exact strings, function names, class names, config keys, filenames, and error codes. File read is the authority for current contents before trusting or modifying code or docs.

不知道具体要找什么时，使用 RAG。

已经知道函数名、配置项、错误码、文件名时，使用 repository search。

准备相信或修改内容时，读取真实文件。

Never modify RAG database chunks directly.

Do not modify files based only on RAG chunks.

## Tool Selection

Use `search_repo` when the answer may be in either code or docs.

Use `search_docs` when the user asks about documentation, setup, configuration, runbooks, design notes, or Markdown content.

Use `search_code` when the user asks about implementation, symbols, code paths, behavior, or source files.

Use `locate_repo` when you only need candidate file/section locations before deciding what to read next.

Use `get_index_status` when you need to inspect whether code/docs indexes exist and how many files/chunks are indexed.

Use `rg` only for exact string search in real repository files. Do not use `rg` for fuzzy discovery.

## JSON Handling

MCP RAG tools return structured JSON. Treat that JSON as data, not text.

When extracting fields from RAG output, use `jq`.

When validating or formatting JSON, use `python -m json.tool`.

For complex JSON transforms or batch processing, use Python.

Do not parse JSON structure with `rg` or `sed`.

## Real File Confirmation

RAG returns discovery chunks and source locations. Before relying on content for an answer or edit, confirm the current real file contents with the editor's file-reading capability or shell commands such as:

```bash
nl -ba path/to/file | sed -n '40,90p'
```

Use `nl` / `sed` for real file line ranges, not for parsing JSON.

## Index Freshness

Prefer MCP tool calls with `refresh_index=true` for the first RAG search in a task, after file changes, after include/exclude or `.ragignore` changes, or when search results look stale.

For repeated searches in the same task with no file changes, use `refresh_index=false` to avoid unnecessary refresh work.

Let the underlying incremental indexer decide which files are added, changed, deleted, or unchanged. Do not manually infer exact staleness for every file.

## Expected Search Output

Search tools return `repo-rag-search-v1` JSON with hits containing:

- `content`
- `content_type`
- `score`
- `score_details`
- `source.path`
- `source.line_start`
- `source.line_end`
- `source.heading` for documentation
- `source.symbol` for code when available
- `source.content_hash`
- `source.chunk_hash`
- `metadata`

Locate returns `repo-rag-locate-v1` JSON with compact location-oriented hits.
