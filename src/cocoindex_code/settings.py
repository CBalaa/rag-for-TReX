"""YAML settings schema, loading, saving, and path helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml as _yaml

if TYPE_CHECKING:
    from pathspec import GitIgnoreSpec

# ---------------------------------------------------------------------------
# Default file patterns (moved from indexer.py)
# ---------------------------------------------------------------------------

DEFAULT_INCLUDED_PATTERNS: list[str] = [
    "**/*.py",  # Python
    "**/*.pyi",  # Python stubs
    "**/*.js",  # JavaScript
    "**/*.jsx",  # JavaScript React
    "**/*.ts",  # TypeScript
    "**/*.tsx",  # TypeScript React
    "**/*.mjs",  # JavaScript ES modules
    "**/*.cjs",  # JavaScript CommonJS
    "**/*.rs",  # Rust
    "**/*.go",  # Go
    "**/*.java",  # Java
    "**/*.c",  # C
    "**/*.h",  # C/C++ headers
    "**/*.cpp",  # C++
    "**/*.hpp",  # C++ headers
    "**/*.cc",  # C++
    "**/*.cxx",  # C++
    "**/*.hxx",  # C++ headers
    "**/*.hh",  # C++ headers
    "**/*.cs",  # C#
    "**/*.dart",  # Dart
    "**/*.sql",  # SQL
    "**/*.sh",  # Shell
    "**/*.bash",  # Bash
    "**/*.zsh",  # Zsh
    "**/*.txt",  # Plain text
    "**/*.rst",  # reStructuredText
    "**/*.php",  # PHP
    "**/*.lua",  # Lua
    "**/*.rb",  # Ruby
    "**/*.swift",  # Swift
    "**/*.kt",  # Kotlin
    "**/*.kts",  # Kotlin script
    "**/*.scala",  # Scala
    "**/*.r",  # R
    "**/*.html",  # HTML
    "**/*.htm",  # HTML
    "**/*.svelte",  # Svelte
    "**/*.vue",  # Vue
    "**/*.css",  # CSS
    "**/*.scss",  # SCSS
    "**/*.json",  # JSON
    "**/*.xml",  # XML
    "**/*.yaml",  # YAML
    "**/*.yml",  # YAML
    "**/*.toml",  # TOML
    "**/*.sol",  # Solidity
    "**/*.pas",  # Pascal
    "**/*.dpr",  # Pascal/Delphi
    "**/*.dtd",  # DTD
    "**/*.f",  # Fortran
    "**/*.f90",  # Fortran
    "**/*.f95",  # Fortran
    "**/*.f03",  # Fortran
]

DEFAULT_EXCLUDED_PATTERNS: list[str] = [
    "**/.*",  # Hidden directories
    ".rag4trex.yml",
    "**/.rag4trex.yml",
    ".rag4trex",
    ".rag4trex/**",
    "**/.rag4trex",
    "**/.rag4trex/**",
    ".cocoindex_code",
    ".cocoindex_code/**",
    "**/.cocoindex_code",
    "**/.cocoindex_code/**",
    "**/__pycache__",  # Python cache
    "**/node_modules",  # Node.js dependencies
    "**/target",  # Rust/Maven build output
    "**/build/assets",  # Build assets directories
    "**/dist",  # Distribution directories
    "**/vendor/*.*/*",  # Go vendor directory (domain-based paths)
    "**/vendor/*",  # PHP vendor directory
    "**/.rag4trex",  # Our own index directory
    "**/.cocoindex_code",  # Legacy index directory
]

DEFAULT_DOCS_INCLUDED_PATTERNS: list[str] = [
    "**/*.md",
    "**/*.mdx",
    "**/*.markdown",
]

DEFAULT_DOCS_EXCLUDED_PATTERNS: list[str] = []

DEFAULT_CODE_ROOTS: list[str] = ["src", "packages", "tests", "scripts"]
DEFAULT_DOCS_ROOTS: list[str] = ["docs", "README.md"]
DEFAULT_SEARCH_MODE = "semantic"
DEFAULT_SEARCH_TOP_K = 8
DEFAULT_SEARCH_MAX_TOP_K = 50
DEFAULT_RETURN_CONTENT_MAX_CHARS = 4000

FORCED_EXCLUDED_PATTERNS: list[str] = [
    ".git",
    ".git/**",
    "**/.git",
    "**/.git/**",
    ".rag4trex.yml",
    "**/.rag4trex.yml",
    "node_modules",
    "node_modules/**",
    "**/node_modules",
    "**/node_modules/**",
    "dist",
    "dist/**",
    "**/dist",
    "**/dist/**",
    "build",
    "build/**",
    "**/build",
    "**/build/**",
    "venv",
    "venv/**",
    "**/venv",
    "**/venv/**",
    ".venv",
    ".venv/**",
    "**/.venv",
    "**/.venv/**",
    "__pycache__",
    "__pycache__/**",
    "**/__pycache__",
    "**/__pycache__/**",
    ".env",
    "**/.env",
    "**/*.pem",
    "**/*.key",
    "secrets",
    "secrets/**",
    "**/secrets",
    "**/secrets/**",
    "**/*.db",
    "**/*.sqlite",
    "**/*.sqlite3",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.pdf",
    "**/*.zip",
    "**/*.tar",
    "**/*.gz",
]

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingSettings:
    model: str
    provider: str = "litellm"
    device: str | None = None
    min_interval_ms: int | None = None
    # Extra kwargs spread into ``embedder.embed()`` during indexing/query.
    # ``None`` means the user did not set the key; ``{}`` is an explicit empty
    # dict (used to opt out of the legacy-bridge warning).
    indexing_params: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None


@dataclass
class RerankSettings:
    enabled: bool = False
    model: str | None = None
    provider: str = "litellm"
    top_n: int = 50
    min_interval_ms: int | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserSettings:
    embedding: EmbeddingSettings
    rerank: RerankSettings = field(default_factory=RerankSettings)
    envs: dict[str, str] = field(default_factory=dict)


@dataclass
class LanguageOverride:
    ext: str  # without dot, e.g. "inc"
    lang: str  # e.g. "php"


@dataclass
class ChunkerMapping:
    ext: str  # without dot, e.g. "toml"
    module: str  # "module.path:callable", e.g. "cocoindex_code.toml_chunker:toml_chunker"


@dataclass
class IndexSettings:
    enabled: bool = True
    roots: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)
    collection: str = ""
    chunker: str = ""


@dataclass
class ScanSettings:
    respect_gitignore: bool = True
    ragignore_file: str = ".ragignore"
    follow_symlinks: bool = False
    max_file_size_kb: int = 512


@dataclass
class SearchSettings:
    default_mode: str = DEFAULT_SEARCH_MODE
    default_top_k: int = DEFAULT_SEARCH_TOP_K
    max_top_k: int = DEFAULT_SEARCH_MAX_TOP_K
    return_content_max_chars: int = DEFAULT_RETURN_CONTENT_MAX_CHARS


@dataclass
class ProjectSettings:
    include_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDED_PATTERNS))
    exclude_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDED_PATTERNS))
    docs_include_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_DOCS_INCLUDED_PATTERNS)
    )
    docs_exclude_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_DOCS_EXCLUDED_PATTERNS)
    )
    docs_roots: list[str] = field(default_factory=lambda: list(DEFAULT_DOCS_ROOTS))
    code_roots: list[str] = field(default_factory=lambda: list(DEFAULT_CODE_ROOTS))
    scan: ScanSettings = field(default_factory=ScanSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    always_exclude: list[str] = field(default_factory=lambda: list(FORCED_EXCLUDED_PATTERNS))
    language_overrides: list[LanguageOverride] = field(default_factory=list)
    chunkers: list[ChunkerMapping] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Default factories
# ---------------------------------------------------------------------------


DEFAULT_ST_MODEL = "Snowflake/snowflake-arctic-embed-xs"


def default_user_settings() -> UserSettings:
    return UserSettings(
        embedding=EmbeddingSettings(
            provider="sentence-transformers",
            model=DEFAULT_ST_MODEL,
        ),
        rerank=RerankSettings(),
    )


def default_project_settings() -> ProjectSettings:
    return ProjectSettings()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_SETTINGS_DIR_NAME = ".rag4trex"
_LEGACY_SETTINGS_DIR_NAME = ".cocoindex_code"
_PROJECT_SETTINGS_FILE_NAME = ".rag4trex.yml"  # project-level
_LEGACY_SETTINGS_FILE_NAME = "settings.yml"  # legacy project-level
_USER_SETTINGS_FILE_NAME = "global_settings.yml"  # user-level

_ENV_USER_SETTINGS_DIR = "RAG4TREX_DIR"
_LEGACY_ENV_USER_SETTINGS_DIR = "COCOINDEX_CODE_DIR"
_ENV_DB_PATH_MAPPING = "RAG4TREX_DB_PATH_MAPPING"
_LEGACY_ENV_DB_PATH_MAPPING = "COCOINDEX_CODE_DB_PATH_MAPPING"
_ENV_HOST_PATH_MAPPING = "RAG4TREX_HOST_PATH_MAPPING"
_LEGACY_ENV_HOST_PATH_MAPPING = "COCOINDEX_CODE_HOST_PATH_MAPPING"


@dataclass
class PathMapping:
    source: Path
    target: Path


def _getenv_preferred(env_var: str, legacy_env_var: str | None = None) -> tuple[str, str | None]:
    """Return a preferred env var value, falling back to a legacy name."""
    raw = os.environ.get(env_var)
    if raw is not None:
        return env_var, raw
    if legacy_env_var is not None:
        legacy_raw = os.environ.get(legacy_env_var)
        if legacy_raw is not None:
            return legacy_env_var, legacy_raw
    return env_var, None


def _parse_path_mapping(env_var: str, legacy_env_var: str | None = None) -> list[PathMapping]:
    """Parse a ``source=target[,source=target...]`` env var.

    Both source and target must be absolute paths. Returns an empty list when
    the env var is unset or blank. Raises ``ValueError`` on malformed entries.
    """
    actual_env_var, raw = _getenv_preferred(env_var, legacy_env_var)
    if raw is None or not raw.strip():
        return []

    mappings: list[PathMapping] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("=", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                f"{actual_env_var}: invalid entry {entry!r}, expected format 'source=target'"
            )
        source = Path(parts[0])
        target = Path(parts[1])
        if not source.is_absolute():
            raise ValueError(f"{actual_env_var}: source path must be absolute, got {source!r}")
        if not target.is_absolute():
            raise ValueError(f"{actual_env_var}: target path must be absolute, got {target!r}")
        mappings.append(PathMapping(source=source.resolve(), target=target.resolve()))
    return mappings


def _apply_mapping(mappings: list[PathMapping], path: str | Path, reverse: bool = False) -> str:
    """Rewrite ``path`` through ``mappings``. First prefix match wins.

    ``reverse=False``: rewrites source-prefix → target-prefix (forward).
    ``reverse=True``: rewrites target-prefix → source-prefix (reverse).

    Relative paths and absolute paths with no matching prefix are returned
    unchanged (as ``str``).
    """
    p = Path(path)
    if not p.is_absolute():
        return str(path)
    resolved = p.resolve()
    for m in mappings:
        src, dst = (m.target, m.source) if reverse else (m.source, m.target)
        if resolved == src or resolved.is_relative_to(src):
            rel = resolved.relative_to(src)
            return str(dst / rel) if str(rel) != "." else str(dst)
    return str(path)


_db_path_mapping: list[PathMapping] | None = None
_host_path_mapping: list[PathMapping] | None = None


def resolve_db_dir(project_root: Path) -> Path:
    """Return the directory for database files given a project root.

    Applies ``RAG4TREX_DB_PATH_MAPPING`` if set, otherwise falls back
    to ``project_root / ".rag4trex"``. The legacy
    ``COCOINDEX_CODE_DB_PATH_MAPPING`` env var is still accepted.
    """
    global _db_path_mapping  # noqa: PLW0603
    if _db_path_mapping is None:
        _db_path_mapping = _parse_path_mapping(_ENV_DB_PATH_MAPPING, _LEGACY_ENV_DB_PATH_MAPPING)

    resolved = project_root.resolve()
    for mapping in _db_path_mapping:
        if resolved == mapping.source or resolved.is_relative_to(mapping.source):
            rel = resolved.relative_to(mapping.source)
            return mapping.target / rel
    preferred = project_root / _SETTINGS_DIR_NAME
    legacy = project_root / _LEGACY_SETTINGS_DIR_NAME
    if not (preferred / _COCOINDEX_DB_NAME).exists() and (legacy / _COCOINDEX_DB_NAME).exists():
        return legacy
    return project_root / _SETTINGS_DIR_NAME


def get_db_path_mappings() -> list[PathMapping]:
    """Return the parsed DB path mappings from ``RAG4TREX_DB_PATH_MAPPING``."""
    global _db_path_mapping  # noqa: PLW0603
    if _db_path_mapping is None:
        _db_path_mapping = _parse_path_mapping(_ENV_DB_PATH_MAPPING, _LEGACY_ENV_DB_PATH_MAPPING)
    return list(_db_path_mapping)


def get_host_path_mappings() -> list[PathMapping]:
    """Return the parsed host path mappings from ``RAG4TREX_HOST_PATH_MAPPING``."""
    global _host_path_mapping  # noqa: PLW0603
    if _host_path_mapping is None:
        _host_path_mapping = _parse_path_mapping(
            _ENV_HOST_PATH_MAPPING, _LEGACY_ENV_HOST_PATH_MAPPING
        )
    return list(_host_path_mapping)


def format_path_for_display(p: str | Path) -> str:
    """Translate a container path to its host equivalent for user-facing output.

    No-op when ``RAG4TREX_HOST_PATH_MAPPING`` is unset or when ``p`` is a
    relative path / unmatched absolute path.
    """
    return _apply_mapping(get_host_path_mappings(), p, reverse=False)


def normalize_input_path(p: str | Path) -> str:
    """Translate a host path back to its container form before using it internally.

    Inverse of :func:`format_path_for_display`. No-op when the env var is unset
    or when ``p`` is relative / unmatched.
    """
    return _apply_mapping(get_host_path_mappings(), p, reverse=True)


def _reset_db_path_mapping_cache() -> None:
    """Reset the cached mapping (for tests)."""
    global _db_path_mapping  # noqa: PLW0603
    _db_path_mapping = None


def _reset_host_path_mapping_cache() -> None:
    """Reset the cached mapping (for tests)."""
    global _host_path_mapping  # noqa: PLW0603
    _host_path_mapping = None


_TARGET_SQLITE_DB_NAME = "target_sqlite.db"
_COCOINDEX_DB_NAME = "cocoindex.db"


def target_sqlite_db_path(project_root: Path) -> Path:
    """Return the path to the vector index SQLite database for a project."""
    return resolve_db_dir(project_root) / _TARGET_SQLITE_DB_NAME


def cocoindex_db_path(project_root: Path) -> Path:
    """Return the path to the CocoIndex state database for a project."""
    return resolve_db_dir(project_root) / _COCOINDEX_DB_NAME


def user_settings_dir() -> Path:
    """Return the user-level rag4trex settings directory.

    Respects ``RAG4TREX_DIR`` for overriding the base directory. The legacy
    ``COCOINDEX_CODE_DIR`` env var and ``~/.cocoindex_code`` path are still
    accepted when present.
    """
    _, override = _getenv_preferred(_ENV_USER_SETTINGS_DIR, _LEGACY_ENV_USER_SETTINGS_DIR)
    if override:
        return Path(override)
    preferred = Path.home() / _SETTINGS_DIR_NAME
    legacy = Path.home() / _LEGACY_SETTINGS_DIR_NAME
    if not (preferred / _USER_SETTINGS_FILE_NAME).exists() and (
        legacy / _USER_SETTINGS_FILE_NAME
    ).exists():
        return legacy
    return preferred


def user_settings_path() -> Path:
    """Return the preferred or existing user-level ``global_settings.yml`` path."""
    return user_settings_dir() / _USER_SETTINGS_FILE_NAME


def project_settings_path(project_root: Path) -> Path:
    """Return the preferred project settings path: ``$PROJECT_ROOT/.rag4trex.yml``."""
    return project_root / _PROJECT_SETTINGS_FILE_NAME


def legacy_project_settings_path(project_root: Path) -> Path:
    """Return the legacy project settings path."""
    return project_root / _LEGACY_SETTINGS_DIR_NAME / _LEGACY_SETTINGS_FILE_NAME


def project_settings_paths(project_root: Path) -> list[Path]:
    """Return project settings paths in load-preference order."""
    return [project_settings_path(project_root), legacy_project_settings_path(project_root)]


def existing_project_settings_path(project_root: Path) -> Path | None:
    """Return the first existing project settings path, preferring .rag4trex.yml."""
    for path in project_settings_paths(project_root):
        if path.is_file():
            return path
    return None


def find_project_root(start: Path) -> Path | None:
    """Walk up from *start* looking for project settings.

    Returns the directory containing it, or ``None``.
    """
    current = start.resolve()
    while True:
        if existing_project_settings_path(current) is not None:
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def find_legacy_project_root(start: Path) -> Path | None:
    """Walk up from *start* looking for an existing index directory.

    Used by compatibility paths to re-anchor to a previously-indexed project
    tree. Returns the first matching directory, or ``None``.
    """
    current = start.resolve()
    while True:
        if (current / _SETTINGS_DIR_NAME / _COCOINDEX_DB_NAME).exists() or (
            current / _LEGACY_SETTINGS_DIR_NAME / _COCOINDEX_DB_NAME
        ).exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def find_parent_with_marker(start: Path) -> Path | None:
    """Walk up from *start* looking for an initialized project or a git repo.

    Match criteria: ``.rag4trex.yml`` or legacy ``.cocoindex_code/settings.yml``
    (real project markers, distinct from a workspace-root
    ``.cocoindex_code/global_settings.yml`` which should not trigger this check)
    or ``.git/``.

    Returns the first directory found, or ``None``. Does not consider the home
    directory or above, to avoid false positives on CI runners where ~/.git
    may exist.
    """
    home = Path.home().resolve()
    current = start.resolve()
    while True:
        if current == home:
            return None
        parent = current.parent
        if parent == current:
            return None
        if existing_project_settings_path(current) is not None or (current / ".git").is_dir():
            return current
        current = parent


def global_settings_mtime_us() -> int | None:
    """Return the mtime of ``global_settings.yml`` as integer microseconds.

    Returns ``None`` if the file does not exist.  Used by the daemon to record
    the mtime at startup and by the client to detect staleness.
    """
    path = user_settings_path()
    try:
        return int(path.stat().st_mtime * 1_000_000)
    except FileNotFoundError:
        return None


def load_ignore_spec(project_root: Path, filename: str) -> GitIgnoreSpec | None:
    """Load a GitIgnoreSpec for an ignore file in the project root."""
    from pathspec import GitIgnoreSpec

    ignore_file = project_root / filename
    if not ignore_file.is_file():
        return None
    try:
        lines = ignore_file.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not lines:
        return None
    return GitIgnoreSpec.from_lines(lines)


def load_gitignore_spec(project_root: Path) -> GitIgnoreSpec | None:
    """Load a GitIgnoreSpec for the project's ``.gitignore`` if present."""
    return load_ignore_spec(project_root, ".gitignore")


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _embedding_settings_to_dict(embedding: EmbeddingSettings) -> dict[str, Any]:
    d: dict[str, Any] = {
        "provider": embedding.provider,
        "model": embedding.model,
    }
    if embedding.device is not None:
        d["device"] = embedding.device
    if embedding.min_interval_ms is not None:
        d["min_interval_ms"] = embedding.min_interval_ms
    if embedding.indexing_params is not None:
        d["indexing_params"] = dict(embedding.indexing_params)
    if embedding.query_params is not None:
        d["query_params"] = dict(embedding.query_params)
    return d


def _rerank_settings_to_dict(rerank: RerankSettings) -> dict[str, Any]:
    d: dict[str, Any] = {
        "enabled": rerank.enabled,
        "provider": rerank.provider,
        "top_n": rerank.top_n,
    }
    if rerank.model is not None:
        d["model"] = rerank.model
    if rerank.min_interval_ms is not None:
        d["min_interval_ms"] = rerank.min_interval_ms
    if rerank.params:
        d["params"] = dict(rerank.params)
    return d


def _user_settings_to_dict(settings: UserSettings) -> dict[str, Any]:
    d: dict[str, Any] = {"embedding": _embedding_settings_to_dict(settings.embedding)}
    if settings.rerank.enabled or settings.rerank.model is not None:
        d["rerank"] = _rerank_settings_to_dict(settings.rerank)
    if settings.envs:
        d["envs"] = dict(settings.envs)
    return d


def _user_settings_from_dict(d: dict[str, Any]) -> UserSettings:
    emb_dict = d.get("embedding")
    if not emb_dict or "model" not in emb_dict:
        raise ValueError("Must contain 'embedding' with at least 'model' field")
    # Only pass keys that are present; provider uses dataclass default ("litellm") if omitted
    emb_kwargs: dict[str, Any] = {"model": emb_dict["model"]}
    if "provider" in emb_dict:
        emb_kwargs["provider"] = emb_dict["provider"]
    if "device" in emb_dict:
        emb_kwargs["device"] = emb_dict["device"]
    if "min_interval_ms" in emb_dict:
        emb_kwargs["min_interval_ms"] = emb_dict["min_interval_ms"]
    # indexing_params / query_params: missing → None (dataclass default);
    # present-but-null → {} (treat the same as an empty dict, since both mean
    # "user acknowledged the key and wants no extra kwargs").
    if "indexing_params" in emb_dict:
        emb_kwargs["indexing_params"] = dict(emb_dict["indexing_params"] or {})
    if "query_params" in emb_dict:
        emb_kwargs["query_params"] = dict(emb_dict["query_params"] or {})
    embedding = EmbeddingSettings(**emb_kwargs)
    rerank_dict = d.get("rerank") or {}
    rerank = RerankSettings(
        enabled=bool(rerank_dict.get("enabled", False)),
        provider=str(rerank_dict.get("provider", "litellm")),
        model=rerank_dict.get("model"),
        top_n=int(rerank_dict.get("top_n", 50)),
        min_interval_ms=rerank_dict.get("min_interval_ms"),
        params=dict(rerank_dict.get("params") or {}),
    )
    if rerank.enabled and not rerank.model:
        raise ValueError("rerank.enabled is true but rerank.model is missing")
    if rerank.provider not in {"litellm", "zhipu", "glm"}:
        raise ValueError("rerank.provider must be one of: litellm, zhipu")
    if rerank.top_n < 1:
        raise ValueError("rerank.top_n must be >= 1")
    envs = d.get("envs", {})
    return UserSettings(embedding=embedding, rerank=rerank, envs=envs)


def _project_settings_to_dict(settings: ProjectSettings) -> dict[str, Any]:
    d: dict[str, Any] = {
        "include_patterns": settings.include_patterns,
        "exclude_patterns": settings.exclude_patterns,
        "docs_include_patterns": settings.docs_include_patterns,
        "docs_exclude_patterns": settings.docs_exclude_patterns,
        "indexes": {
            "docs": {
                "enabled": True,
                "roots": settings.docs_roots,
                "include": settings.docs_include_patterns,
                "exclude": settings.docs_exclude_patterns,
                "extensions": [".md", ".mdx", ".markdown"],
                "collection": "project_docs",
                "chunker": "markdown-v1",
            },
            "code": {
                "enabled": True,
                "roots": settings.code_roots,
                "include": settings.include_patterns,
                "exclude": settings.exclude_patterns,
                "collection": "project_code",
                "chunker": "code-ast-v1",
            },
        },
        "scan": {
            "respect_gitignore": settings.scan.respect_gitignore,
            "ragignore_file": settings.scan.ragignore_file,
            "follow_symlinks": settings.scan.follow_symlinks,
            "max_file_size_kb": settings.scan.max_file_size_kb,
        },
        "always_exclude": settings.always_exclude,
        "search": {
            "default_mode": settings.search.default_mode,
            "default_top_k": settings.search.default_top_k,
            "max_top_k": settings.search.max_top_k,
            "return_content_max_chars": settings.search.return_content_max_chars,
        },
    }
    if settings.language_overrides:
        d["language_overrides"] = [
            {"ext": lo.ext, "lang": lo.lang} for lo in settings.language_overrides
        ]
    if settings.chunkers:
        d["chunkers"] = [{"ext": cm.ext, "module": cm.module} for cm in settings.chunkers]
    return d


def _project_settings_from_dict(d: dict[str, Any]) -> ProjectSettings:
    overrides = [
        LanguageOverride(ext=lo["ext"], lang=lo["lang"]) for lo in d.get("language_overrides", [])
    ]
    chunkers = [ChunkerMapping(ext=cm["ext"], module=cm["module"]) for cm in d.get("chunkers", [])]
    indexes = d.get("indexes") or {}
    docs_index = indexes.get("docs") or {}
    code_index = indexes.get("code") or {}
    scan_dict = d.get("scan") or {}
    search_dict = d.get("search") or {}
    return ProjectSettings(
        include_patterns=d.get(
            "include_patterns", code_index.get("include", list(DEFAULT_INCLUDED_PATTERNS))
        ),
        exclude_patterns=d.get(
            "exclude_patterns", code_index.get("exclude", list(DEFAULT_EXCLUDED_PATTERNS))
        ),
        docs_include_patterns=d.get(
            "docs_include_patterns",
            docs_index.get("include", list(DEFAULT_DOCS_INCLUDED_PATTERNS)),
        ),
        docs_exclude_patterns=d.get(
            "docs_exclude_patterns",
            docs_index.get("exclude", list(DEFAULT_DOCS_EXCLUDED_PATTERNS)),
        ),
        docs_roots=docs_index.get("roots", list(DEFAULT_DOCS_ROOTS)),
        code_roots=code_index.get("roots", list(DEFAULT_CODE_ROOTS)),
        scan=ScanSettings(
            respect_gitignore=bool(scan_dict.get("respect_gitignore", True)),
            ragignore_file=str(scan_dict.get("ragignore_file", ".ragignore")),
            follow_symlinks=bool(scan_dict.get("follow_symlinks", False)),
            max_file_size_kb=int(scan_dict.get("max_file_size_kb", 512)),
        ),
        search=SearchSettings(
            default_mode=str(search_dict.get("default_mode", DEFAULT_SEARCH_MODE)),
            default_top_k=int(search_dict.get("default_top_k", DEFAULT_SEARCH_TOP_K)),
            max_top_k=int(search_dict.get("max_top_k", DEFAULT_SEARCH_MAX_TOP_K)),
            return_content_max_chars=int(
                search_dict.get("return_content_max_chars", DEFAULT_RETURN_CONTENT_MAX_CHARS)
            ),
        ),
        always_exclude=d.get("always_exclude", list(FORCED_EXCLUDED_PATTERNS)),
        language_overrides=overrides,
        chunkers=chunkers,
    )


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def load_user_settings() -> UserSettings:
    """Read user-level ``global_settings.yml``.

    Raises ``FileNotFoundError`` if missing, ``ValueError`` if incomplete.
    """
    path = user_settings_path()
    if not path.is_file():
        raise FileNotFoundError(f"User settings not found: {path}")
    try:
        with open(path) as f:
            data = _yaml.safe_load(f)
        if not data:
            raise ValueError("File is empty")
        return _user_settings_from_dict(data)
    except Exception as e:
        raise type(e)(f"Error loading {path}: {e}") from e


def save_user_settings(settings: UserSettings) -> Path:
    """Write user settings YAML. Returns path written."""
    path = user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        _yaml.safe_dump(_user_settings_to_dict(settings), f, default_flow_style=False)
    return path


_INITIAL_HEADER = (
    "# rag4trex global settings.\n"
    "# After editing this file, run `rag4trex doctor` to verify your configuration.\n"
    "\n"
)

_INITIAL_ENVS_COMMENT = (
    "\n"
    "# Environment variables to inject into the daemon running in the background.\n"
    "# Uncomment and fill in keys for the LiteLLM providers you plan to use.\n"
    "#\n"
    "# envs:\n"
    "#   OPENAI_API_KEY: ...\n"
    "#   GEMINI_API_KEY: ...\n"
    "#   ANTHROPIC_API_KEY: ...\n"
    "#   VOYAGE_API_KEY: ...\n"
)

_INITIAL_RERANK_COMMENT = (
    "\n"
    "# Optional reranker for search result reordering. Disabled by default.\n"
    "# When enabled, search first retrieves vector candidates, then reranks the\n"
    "# candidate chunks and fills score_details.rerank_score.\n"
    "#\n"
    "# rerank:\n"
    "#   enabled: true\n"
    "#   provider: litellm  # or zhipu\n"
    "#   model: cohere/rerank-v3.5\n"
    "#   top_n: 50\n"
    "#   min_interval_ms: 300\n"
    "#   params: {}\n"
)

# Comment-template blocks inserted after `embedding:` when we don't have
# curated defaults for the chosen model, so users know the fields exist.
# Keyed by provider name.
_PARAMS_COMMENT_BY_PROVIDER: dict[str, str] = {
    "sentence-transformers": (
        "  #\n"
        "  # Extra kwargs passed to the embedder. Supported keys:\n"
        "  #   prompt_name\n"
        "  # indexing_params: {}\n"
        "  # query_params: {}\n"
    ),
    "litellm": (
        "  #\n"
        "  # Extra kwargs passed to the embedder. Supported keys:\n"
        "  #   input_type\n"
        "  # indexing_params: {}\n"
        "  # query_params: {}\n"
    ),
}


def save_initial_user_settings(
    embedding: EmbeddingSettings,
    defaults_applied: bool,
) -> Path:
    """Write the initial global_settings.yml with comment hints and env examples.

    Only used by `rag4trex init` on first-time setup. Emits only the `embedding:`
    block from the input; the `envs:` section is a commented-out template.
    Subsequent programmatic writes use `save_user_settings` and do not
    preserve comments.

    When ``defaults_applied`` is False, a provider-specific commented-out
    template for ``indexing_params`` / ``query_params`` is inserted under the
    ``embedding:`` block so the user sees the fields exist.
    """
    emb_block = _yaml.safe_dump(
        {"embedding": _embedding_settings_to_dict(embedding)},
        default_flow_style=False,
        sort_keys=False,
    )
    content = _INITIAL_HEADER + emb_block
    if not defaults_applied:
        hint = _PARAMS_COMMENT_BY_PROVIDER.get(embedding.provider)
        if hint is not None:
            content += hint
    content += _INITIAL_RERANK_COMMENT
    content += _INITIAL_ENVS_COMMENT

    path = user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def load_project_settings(project_root: Path) -> ProjectSettings:
    """Read project settings, preferring ``$PROJECT_ROOT/.rag4trex.yml``.

    Raises ``FileNotFoundError`` if the file does not exist.
    """
    path = existing_project_settings_path(project_root)
    if path is None:
        expected = " or ".join(str(p) for p in project_settings_paths(project_root))
        raise FileNotFoundError(f"Project settings not found: {expected}")
    try:
        with open(path) as f:
            data = _yaml.safe_load(f)
        if not data:
            return default_project_settings()
        return _project_settings_from_dict(data)
    except Exception as e:
        raise type(e)(f"Error loading {path}: {e}") from e


def save_project_settings(project_root: Path, settings: ProjectSettings) -> Path:
    """Write project settings YAML. Returns path written."""
    path = project_settings_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        _yaml.safe_dump(_project_settings_to_dict(settings), f, default_flow_style=False)
    return path
