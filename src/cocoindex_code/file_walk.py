"""Shared source-file walking: pattern + .gitignore matching, reused by the
indexer, the daemon's doctor file-walk, and ``ccc grep``.

The matcher (include/exclude globs + nested ``.gitignore`` awareness) is the
single source of truth for "which files count as part of the project". The
indexer feeds it to CocoIndex's incremental file source; the daemon and ``ccc
grep`` drive a plain :func:`os.walk` over it via :func:`iter_included_files`.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePath

from cocoindex.resources.file import FilePathMatcher, PatternFilePathMatcher
from pathspec import GitIgnoreSpec

from .settings import FORCED_EXCLUDED_PATTERNS, load_gitignore_spec, load_ignore_spec


def _normalize_gitignore_lines(lines: Iterable[str], directory: PurePath) -> list[str]:
    """Normalize .gitignore lines to root-relative gitignore patterns."""
    if directory in (PurePath("."), PurePath("")):
        prefix = ""
    else:
        prefix = f"{directory.as_posix().rstrip('/')}/"

    normalized: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\n\r")
        if not line:
            continue
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("\\#") or line.startswith("\\!"):
            line = line[1:]
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        body = line.strip()
        if not body:
            continue
        anchor = body.startswith("/")
        if anchor:
            body = body.lstrip("/")
            pattern = f"{prefix}{body}" if prefix else body
        else:
            contains_slash = "/" in body
            base = prefix
            if contains_slash:
                pattern = f"{base}{body}"
            else:
                if base:
                    pattern = f"{base}**/{body}"
                else:
                    pattern = f"**/{body}"
        if negated:
            pattern = f"!{pattern}"
        normalized.append(pattern)
    return normalized


class GitignoreAwareMatcher(FilePathMatcher):
    """Wraps another matcher and applies .gitignore filtering."""

    def __init__(
        self,
        delegate: FilePathMatcher,
        root_spec: GitIgnoreSpec | None,
        project_root: Path,
    ) -> None:
        self._delegate = delegate
        self._root = project_root
        self._spec_cache: dict[PurePath, GitIgnoreSpec | None] = {PurePath("."): root_spec}

    def _spec_for(self, directory: PurePath) -> GitIgnoreSpec | None:
        if directory in self._spec_cache:
            return self._spec_cache[directory]

        parent_dir = directory.parent if directory != PurePath(".") else PurePath(".")
        parent_spec = self._spec_for(parent_dir)
        spec = parent_spec

        gitignore_path = (self._root / directory) / ".gitignore"
        if gitignore_path.is_file():
            try:
                lines = gitignore_path.read_text().splitlines()
            except (OSError, UnicodeDecodeError):
                lines = []
            normalized = _normalize_gitignore_lines(lines, directory)
            if normalized:
                new_spec = GitIgnoreSpec.from_lines(normalized)
                spec = new_spec if spec is None else spec + new_spec

        self._spec_cache[directory] = spec
        return spec

    def _is_ignored(self, path: PurePath, is_dir: bool) -> bool:
        directory = path if is_dir else path.parent
        if directory == PurePath(""):
            directory = PurePath(".")
        spec = self._spec_for(directory)
        if spec is None:
            return False
        match_path = path.as_posix()
        if is_dir and not match_path.endswith("/"):
            match_path = f"{match_path}/"
        return spec.match_file(match_path)

    def is_dir_included(self, path: PurePath) -> bool:
        if self._is_ignored(path, True):
            return False
        return self._delegate.is_dir_included(path)

    def is_file_included(self, path: PurePath) -> bool:
        if self._is_ignored(path, False):
            return False
        return self._delegate.is_file_included(path)


class SpecAwareMatcher(FilePathMatcher):
    """Wrap a matcher and exclude paths matching a root-relative GitIgnoreSpec."""

    def __init__(self, delegate: FilePathMatcher, spec: GitIgnoreSpec | None) -> None:
        self._delegate = delegate
        self._spec = spec

    def _is_ignored(self, path: PurePath, is_dir: bool) -> bool:
        if self._spec is None:
            return False
        match_path = path.as_posix()
        if is_dir and not match_path.endswith("/"):
            match_path = f"{match_path}/"
        return self._spec.match_file(match_path)

    def is_dir_included(self, path: PurePath) -> bool:
        if self._is_ignored(path, True):
            return False
        return self._delegate.is_dir_included(path)

    def is_file_included(self, path: PurePath) -> bool:
        if self._is_ignored(path, False):
            return False
        return self._delegate.is_file_included(path)


def find_git_root(start: Path) -> Path | None:
    """Walk up from ``start`` to the nearest directory holding a ``.git`` entry — a
    directory for a normal repo, or a *file* for a submodule or linked worktree.
    Returns that directory, or ``None`` if ``start`` is not inside a git repo.

    Used to anchor ``.gitignore`` resolution at the real repo root when grepping a
    subdirectory that isn't inside an initialized cocoindex project."""
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def build_matcher(
    project_root: Path,
    included_patterns: list[str],
    excluded_patterns: list[str],
    forced_excluded_patterns: list[str] | None = None,
    ragignore_file: str = ".ragignore",
) -> FilePathMatcher:
    """Build the project's file matcher: include/exclude globs plus nested
    ``.gitignore`` awareness anchored at ``project_root``."""
    base_matcher = PatternFilePathMatcher(
        included_patterns=included_patterns,
        excluded_patterns=[
            *excluded_patterns,
            *(forced_excluded_patterns or FORCED_EXCLUDED_PATTERNS),
        ],
    )
    matcher: FilePathMatcher = GitignoreAwareMatcher(
        base_matcher, load_gitignore_spec(project_root), project_root
    )
    return SpecAwareMatcher(matcher, load_ignore_spec(project_root, ragignore_file))


def build_docs_matcher(project_root: Path) -> FilePathMatcher:
    """Build matcher for documentation files using docs settings and ignore files."""
    from .settings import load_project_settings

    ps = load_project_settings(project_root)
    return build_matcher(
        project_root,
        ps.docs_include_patterns,
        ps.docs_exclude_patterns,
        forced_excluded_patterns=ps.always_exclude,
        ragignore_file=ps.scan.ragignore_file,
    )


def explain_path(
    project_root: Path,
    path: str | Path,
    *,
    index_type: str = "code",
) -> dict[str, object]:
    """Explain whether a path is included in a code/docs index and why."""
    from pathspec import GitIgnoreSpec

    from .settings import load_project_settings

    ps = load_project_settings(project_root)
    rel = Path(path)
    if rel.is_absolute():
        rel = rel.resolve().relative_to(project_root.resolve())
    rel_posix = rel.as_posix()
    is_dir = (project_root / rel).is_dir()
    match_path = f"{rel_posix}/" if is_dir and not rel_posix.endswith("/") else rel_posix
    if index_type == "docs":
        include = ps.docs_include_patterns
        exclude = ps.docs_exclude_patterns
    else:
        include = ps.include_patterns
        exclude = ps.exclude_patterns

    def matched(patterns: list[str]) -> list[str]:
        return [
            pattern
            for pattern in patterns
            if GitIgnoreSpec.from_lines([pattern]).match_file(match_path)
        ]

    always_matches = matched(ps.always_exclude)
    exclude_matches = matched(exclude)
    include_matches = matched(include)
    git_spec = load_gitignore_spec(project_root)
    gitignored = bool(git_spec and git_spec.match_file(match_path))
    rag_spec = load_ignore_spec(project_root, ps.scan.ragignore_file)
    ragignored = bool(rag_spec and rag_spec.match_file(match_path))

    matcher = build_matcher(
        project_root,
        include,
        exclude,
        forced_excluded_patterns=ps.always_exclude,
        ragignore_file=ps.scan.ragignore_file,
    )
    rel_pure = PurePath(rel_posix)
    included = matcher.is_dir_included(rel_pure) if is_dir else matcher.is_file_included(rel_pure)
    reasons: list[str] = []
    if always_matches:
        reasons.append("always_exclude")
    if gitignored:
        reasons.append(".gitignore")
    if ragignored:
        reasons.append(ps.scan.ragignore_file)
    if exclude_matches:
        reasons.append("exclude")
    if not include_matches:
        reasons.append("no_include_match")
    if included:
        reasons.append("included")
    return {
        "path": rel_posix,
        "index": index_type,
        "included": included,
        "reasons": reasons,
        "matches": {
            "include": include_matches,
            "exclude": exclude_matches,
            "always_exclude": always_matches,
            "gitignore": gitignored,
            "ragignore": ragignored,
        },
    }


def iter_included_files(
    start: Path,
    base: Path,
    matcher: FilePathMatcher,
) -> Iterator[tuple[Path, PurePath]]:
    """Walk ``start`` recursively, yielding ``(absolute_path, path_relative_to_base)``
    for every file ``matcher`` includes, pruning excluded directories.

    ``base`` anchors the relative paths the matcher sees (the project root, so
    its patterns line up); ``start`` is where traversal begins and may be a
    subdirectory of ``base``. Both must be absolute. Traversal is deterministic
    (directories and files are visited in sorted order).
    """
    for dirpath_str, dirnames, filenames in os.walk(start):
        dirpath = Path(dirpath_str)
        rel_dir = PurePath(dirpath.relative_to(base))
        if rel_dir != PurePath(".") and not matcher.is_dir_included(rel_dir):
            dirnames.clear()
            continue
        dirnames.sort()
        for fname in sorted(filenames):
            rel_path = rel_dir / fname if rel_dir != PurePath(".") else PurePath(fname)
            if matcher.is_file_included(rel_path):
                yield dirpath / fname, rel_path
