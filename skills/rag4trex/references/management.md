# ccc Skill Management

## Install From Python Package

After installing `rag4trex`, install the bundled Codex skill:

```bash
rag4trex install-skill
```

The default destination is `$CODEX_HOME/skills/rag4trex`, or `~/.codex/skills/rag4trex`
when `CODEX_HOME` is unset.

Use `--force` to replace an existing local copy:

```bash
rag4trex install-skill --force
```

Use `--target-dir` or `--codex-home` for custom locations:

```bash
rag4trex install-skill --target-dir /path/to/skills
rag4trex install-skill --codex-home ~/.codex
```

## MCP Requirement

This skill is MCP-only for RAG discovery. Configure the MCP server separately:

```bash
codex mcp add rag4trex -- rag4trex mcp
```

After MCP is configured, the skill uses the provided tools:

- `search_code`
- `search_docs`
- `search_repo`
- `locate_repo`
- `get_index_status`

Do not use this skill to run CLI search/index commands. The skill should call
the MCP tools for RAG discovery and use normal file-reading tools for real
source-file confirmation.
