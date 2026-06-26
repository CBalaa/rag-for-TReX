"""IPC message types and serialization helpers for daemon communication."""

from __future__ import annotations

from typing import Any

import msgspec as _msgspec

# ---------------------------------------------------------------------------
# Requests (tagged union via struct tag)
# ---------------------------------------------------------------------------


class HandshakeRequest(_msgspec.Struct, tag="handshake"):
    version: str


class IndexRequest(_msgspec.Struct, tag="index"):
    project_root: str
    index_type: str = "code"


class SearchRequest(_msgspec.Struct, tag="search"):
    project_root: str
    query: str
    languages: list[str] | None = None
    paths: list[str] | None = None
    limit: int = 5
    offset: int = 0
    mode: str = "semantic"


class SearchDocsRequest(_msgspec.Struct, tag="search_docs"):
    project_root: str
    query: str
    path_prefix: str | None = None
    limit: int = 5
    offset: int = 0
    mode: str = "semantic"


class SearchRepoRequest(_msgspec.Struct, tag="search_repo"):
    project_root: str
    query: str
    content_type: str | None = None
    path_prefix: str | None = None
    limit: int = 5
    offset: int = 0
    mode: str = "semantic"


class ProjectStatusRequest(_msgspec.Struct, tag="project_status"):
    project_root: str


class DaemonStatusRequest(_msgspec.Struct, tag="daemon_status"):
    pass


class RemoveProjectRequest(_msgspec.Struct, tag="remove_project"):
    project_root: str


class StopRequest(_msgspec.Struct, tag="stop"):
    pass


class DoctorRequest(_msgspec.Struct, tag="doctor"):
    project_root: str | None = None


class DaemonEnvRequest(_msgspec.Struct, tag="daemon_env"):
    pass


Request = (
    HandshakeRequest
    | IndexRequest
    | SearchRequest
    | SearchDocsRequest
    | SearchRepoRequest
    | ProjectStatusRequest
    | DaemonStatusRequest
    | RemoveProjectRequest
    | StopRequest
    | DoctorRequest
    | DaemonEnvRequest
)

# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class HandshakeResponse(_msgspec.Struct, tag="handshake"):
    ok: bool
    daemon_version: str
    global_settings_mtime_us: int | None = None
    # Non-fatal daemon-side warnings surfaced to the client on every handshake.
    # The client dedupes and prints them to stderr (see client._print_handshake_warnings).
    warnings: list[str] = []


class IndexResponse(_msgspec.Struct, tag="index"):
    success: bool
    message: str | None = None


class IndexingProgress(_msgspec.Struct):
    """Indexing stats snapshot, shared between progress updates and status responses."""

    num_execution_starts: int
    num_unchanged: int
    num_adds: int
    num_deletes: int
    num_reprocesses: int
    num_errors: int


class IndexProgressUpdate(_msgspec.Struct, tag="index_progress"):
    """Streamed during indexing — one per stats change, before the final IndexResponse."""

    progress: IndexingProgress


class IndexWaitingNotice(_msgspec.Struct, tag="index_waiting"):
    """Sent when another indexing is already in progress and the client must wait."""

    pass


class SearchResult(_msgspec.Struct):
    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    score: float
    score_details: dict[str, float | None] = {}
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
    imports: list[str] = []
    docstring: str | None = None


class SearchResponse(_msgspec.Struct, tag="search"):
    success: bool
    results: list[SearchResult] = []
    total_returned: int = 0
    offset: int = 0
    message: str | None = None
    schema_version: str = "repo-rag-search-v1"
    query: str = ""
    mode: str = "semantic"
    index: str = "code"
    top_k: int = 5


class DocsSearchSource(_msgspec.Struct):
    path: str
    heading: str
    heading_path: list[str]
    line_start: int
    line_end: int
    content_hash: str
    chunk_hash: str
    char_start: int | None = None
    char_end: int | None = None
    chunk_index: int | None = None


class DocsSearchHit(_msgspec.Struct):
    content_type: str
    score: float
    content: str
    source: DocsSearchSource
    score_details: dict[str, float | None] = {}
    metadata: dict[str, Any] = {}


class DocsSearchResponse(_msgspec.Struct, tag="search_docs"):
    success: bool
    query: str
    hits: list[DocsSearchHit] = []
    total_returned: int = 0
    offset: int = 0
    message: str | None = None
    schema_version: str = "repo-rag-search-v1"
    mode: str = "semantic"
    index: str = "docs"
    top_k: int = 5


class RepoSearchSource(_msgspec.Struct):
    path: str
    line_start: int
    line_end: int
    heading: str | None = None
    heading_path: list[str] = []
    language: str | None = None
    symbol: str | None = None
    symbol_type: str | None = None
    signature: str | None = None
    parent_symbol: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    content_hash: str | None = None
    chunk_hash: str | None = None
    chunk_index: int | None = None


class RepoSearchHit(_msgspec.Struct):
    content_type: str
    score: float
    content: str
    source: RepoSearchSource
    score_details: dict[str, float | None] = {}
    metadata: dict[str, Any] = {}


class RepoSearchResponse(_msgspec.Struct, tag="search_repo"):
    success: bool
    query: str
    hits: list[RepoSearchHit] = []
    total_returned: int = 0
    offset: int = 0
    message: str | None = None
    schema_version: str = "repo-rag-search-v1"
    mode: str = "semantic"
    index: str = "repo"
    top_k: int = 5


class ProjectStatusResponse(_msgspec.Struct, tag="project_status"):
    indexing: bool
    total_chunks: int
    total_files: int
    languages: dict[str, int]
    progress: IndexingProgress | None = None
    index_exists: bool = True
    docs_total_chunks: int = 0
    docs_total_files: int = 0
    docs_index_exists: bool = False


class DaemonProjectInfo(_msgspec.Struct):
    project_root: str
    indexing: bool


class DaemonStatusResponse(_msgspec.Struct, tag="daemon_status"):
    version: str
    uptime_seconds: float
    projects: list[DaemonProjectInfo]


class RemoveProjectResponse(_msgspec.Struct, tag="remove_project"):
    ok: bool


class StopResponse(_msgspec.Struct, tag="stop"):
    ok: bool


class DoctorCheckResult(_msgspec.Struct):
    name: str
    ok: bool
    details: list[str]
    errors: list[str]
    # Full formatted traceback for a failed check, shown by `rag4trex doctor` to aid
    # debugging of daemon-side exceptions (e.g. a failing model check).
    traceback: str | None = None


class DoctorResponse(_msgspec.Struct, tag="doctor"):
    result: DoctorCheckResult
    final: bool = False


class DbPathMappingEntry(_msgspec.Struct):
    source: str
    target: str


class DaemonEnvResponse(_msgspec.Struct, tag="daemon_env"):
    env_names: list[str]
    settings_env_names: list[str]
    db_path_mappings: list[DbPathMappingEntry] = []
    host_path_mappings: list[DbPathMappingEntry] = []


class ErrorResponse(_msgspec.Struct, tag="error"):
    message: str
    # Full formatted traceback from the daemon, when the error originates from an
    # unhandled exception. Surfaced by the CLI so daemon-side failures are debuggable.
    traceback: str | None = None


Response = (
    HandshakeResponse
    | IndexResponse
    | IndexProgressUpdate
    | IndexWaitingNotice
    | SearchResponse
    | DocsSearchResponse
    | RepoSearchResponse
    | ProjectStatusResponse
    | DaemonStatusResponse
    | RemoveProjectResponse
    | StopResponse
    | DoctorResponse
    | DaemonEnvResponse
    | ErrorResponse
)

IndexStreamResponse = IndexProgressUpdate | IndexWaitingNotice | IndexResponse | ErrorResponse
SearchStreamResponse = (
    IndexWaitingNotice | SearchResponse | DocsSearchResponse | RepoSearchResponse | ErrorResponse
)
DoctorStreamResponse = DoctorResponse | ErrorResponse

# ---------------------------------------------------------------------------
# Encode / decode helpers (msgpack binary)
# ---------------------------------------------------------------------------

_request_encoder = _msgspec.msgpack.Encoder()
_request_decoder = _msgspec.msgpack.Decoder(Request)

_response_encoder = _msgspec.msgpack.Encoder()
_response_decoder = _msgspec.msgpack.Decoder(Response)


def encode_request(req: Request) -> bytes:
    return _request_encoder.encode(req)


def decode_request(data: bytes) -> Request:
    result: Request = _request_decoder.decode(data)
    return result


def encode_response(resp: Response) -> bytes:
    return _response_encoder.encode(resp)


def decode_response(data: bytes) -> Response:
    result: Response = _response_decoder.decode(data)
    return result
