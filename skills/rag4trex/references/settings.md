# ccc Settings Reference

Use this reference only to understand where RAG configuration lives. The skill
itself should use MCP tools for discovery and normal file-reading tools for
authoritative source content.

## User Settings

User-level settings live at:

```text
~/.cocoindex_code/global_settings.yml
```

They configure embedding and rerank models:

```yaml
embedding:
  provider: sentence-transformers
  model: Snowflake/snowflake-arctic-embed-xs
  device: cpu

rerank:
  enabled: false
  provider: litellm
  model: cohere/rerank-v3.5
  top_n: 50

envs:
  OPENAI_API_KEY: your-key
  COHERE_API_KEY: your-key
```

Switching embedding models changes vector dimensions, so the repository index
must be rebuilt by the user or by the service workflow that owns indexing.

## Project Settings

Project-level RAG settings live at:

```text
<repo>/.rag4trex.yml
```

The legacy fallback path is:

```text
<repo>/.cocoindex_code/settings.yml
```

The project file controls docs/code roots, include patterns, exclude patterns,
`.gitignore` handling, `.ragignore`, and forced safety excludes:

```yaml
indexes:
  docs:
    enabled: true
    roots: [docs, README.md]
    include: ["docs/**/*.md", "docs/**/*.mdx", "README.md", "**/*.markdown"]
    exclude: ["docs/archive/**", "**/*.generated.md"]
    extensions: [".md", ".mdx", ".markdown"]
    collection: "project_docs"
    chunker: "markdown-v1"

  code:
    enabled: true
    roots: [src, packages, tests, scripts]
    include: ["src/**", "packages/**", "tests/**", "scripts/**"]
    exclude: ["**/*.generated.*", "**/fixtures/**", "**/snapshots/**"]
    collection: "project_code"
    chunker: "code-ast-v1"

scan:
  respect_gitignore: true
  ragignore_file: ".ragignore"
  follow_symlinks: false
  max_file_size_kb: 512

always_exclude:
  - ".git/**"
  - "node_modules/**"
  - "vendor/**"
  - "venv/**"
  - ".venv/**"
  - "dist/**"
  - "build/**"
  - "coverage/**"
  - ".cache/**"
  - "__pycache__/**"
  - "**/.env"
  - "**/*.pem"
  - "**/*.key"
  - "**/secrets/**"
  - "**/*.sqlite"
  - "**/*.db"

search:
  default_mode: "semantic"
  default_top_k: 8
  max_top_k: 50
  return_content_max_chars: 4000
```

`always_exclude` is a safety boundary and should not be overridden by ordinary
include rules.
