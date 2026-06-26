"""Unit tests for the protocol module."""

from __future__ import annotations

from cocoindex_code.protocol import (
    DaemonEnvRequest,
    DaemonEnvResponse,
    DaemonProjectInfo,
    DaemonStatusRequest,
    DaemonStatusResponse,
    DocsSearchHit,
    DocsSearchResponse,
    DocsSearchSource,
    DoctorCheckResult,
    DoctorRequest,
    DoctorResponse,
    ErrorResponse,
    HandshakeRequest,
    IndexingProgress,
    IndexProgressUpdate,
    IndexRequest,
    IndexResponse,
    IndexWaitingNotice,
    ProjectStatusRequest,
    ProjectStatusResponse,
    RemoveProjectRequest,
    RemoveProjectResponse,
    RepoSearchHit,
    RepoSearchResponse,
    RepoSearchSource,
    Request,
    Response,
    SearchDocsRequest,
    SearchRepoRequest,
    SearchRequest,
    SearchResponse,
    SearchResult,
    StopRequest,
    StopResponse,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)


def test_encode_decode_handshake_request() -> None:
    req = HandshakeRequest(version="1.0.0")
    data = encode_request(req)
    decoded = decode_request(data)
    assert isinstance(decoded, HandshakeRequest)
    assert decoded.version == "1.0.0"


def test_encode_decode_search_request_with_defaults() -> None:
    req = SearchRequest(project_root="/tmp", query="test")
    data = encode_request(req)
    decoded = decode_request(data)
    assert isinstance(decoded, SearchRequest)
    assert decoded.languages is None
    assert decoded.limit == 5
    assert decoded.offset == 0


def test_encode_decode_search_request_with_all_fields() -> None:
    req = SearchRequest(
        project_root="/tmp/proj",
        query="hello world",
        languages=["python", "rust"],
        paths=["src/*"],
        limit=20,
        offset=5,
    )
    data = encode_request(req)
    decoded = decode_request(data)
    assert isinstance(decoded, SearchRequest)
    assert decoded.project_root == "/tmp/proj"
    assert decoded.query == "hello world"
    assert decoded.languages == ["python", "rust"]
    assert decoded.paths == ["src/*"]
    assert decoded.limit == 20
    assert decoded.offset == 5


def test_encode_decode_search_response_with_results() -> None:
    resp = SearchResponse(
        success=True,
        results=[
            SearchResult(
                file_path="main.py",
                language="python",
                content="def foo(): pass",
                start_line=1,
                end_line=1,
                score=0.95,
                symbol="foo",
                symbol_type="function",
                content_hash="sha256:file",
                chunk_hash="sha256:chunk",
            ),
        ],
        total_returned=1,
        offset=0,
        query="foo",
        top_k=1,
    )
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, SearchResponse)
    assert decoded.success is True
    assert len(decoded.results) == 1
    assert decoded.results[0].file_path == "main.py"
    assert decoded.results[0].score == 0.95
    assert decoded.results[0].symbol == "foo"
    assert decoded.query == "foo"


def test_encode_decode_docs_search_request_and_response() -> None:
    req = SearchDocsRequest(project_root="/tmp/proj", query="auth", path_prefix="docs/", limit=3)
    decoded_req = decode_request(encode_request(req))
    assert isinstance(decoded_req, SearchDocsRequest)
    assert decoded_req.path_prefix == "docs/"

    resp = DocsSearchResponse(
        success=True,
        query="auth",
        hits=[
            DocsSearchHit(
                content_type="documentation",
                score=0.9,
                content="Set AUTH_TOKEN.",
                source=DocsSearchSource(
                    path="docs/auth.md",
                    heading="Auth",
                    heading_path=["Deploy", "Auth"],
                    line_start=10,
                    line_end=20,
                    char_start=1,
                    char_end=20,
                    content_hash="sha256:a",
                    chunk_hash="sha256:b",
                    chunk_index=0,
                ),
                score_details={"vector_score": 0.9, "keyword_score": None, "rerank_score": None},
                metadata={"extension": ".md"},
            )
        ],
    )
    decoded_resp = decode_response(encode_response(resp))
    assert isinstance(decoded_resp, DocsSearchResponse)
    assert decoded_resp.hits[0].source.heading_path == ["Deploy", "Auth"]
    assert decoded_resp.hits[0].source.chunk_index == 0


def test_encode_decode_repo_search() -> None:
    req = SearchRepoRequest(
        project_root="/tmp/proj",
        query="login",
        content_type="docs",
        path_prefix="docs/",
    )
    decoded_req = decode_request(encode_request(req))
    assert isinstance(decoded_req, SearchRepoRequest)
    assert decoded_req.content_type == "docs"

    resp = RepoSearchResponse(
        success=True,
        query="login",
        hits=[
            RepoSearchHit(
                content_type="code",
                score=0.8,
                content="def login(): pass",
                source=RepoSearchSource(
                    path="auth.py",
                    line_start=1,
                    line_end=1,
                    language="python",
                    symbol="login",
                    symbol_type="function",
                ),
                score_details={"vector_score": 0.8, "keyword_score": None, "rerank_score": None},
            )
        ],
    )
    decoded_resp = decode_response(encode_response(resp))
    assert isinstance(decoded_resp, RepoSearchResponse)
    assert decoded_resp.hits[0].source.language == "python"
    assert decoded_resp.hits[0].source.symbol == "login"

def test_encode_decode_error_response() -> None:
    resp = ErrorResponse(message="something failed")
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, ErrorResponse)
    assert decoded.message == "something failed"


def test_project_status_docs_fields_default() -> None:
    resp = ProjectStatusResponse(indexing=False, total_chunks=1, total_files=1, languages={})
    decoded = decode_response(encode_response(resp))
    assert isinstance(decoded, ProjectStatusResponse)
    assert decoded.docs_total_chunks == 0
    assert decoded.docs_total_files == 0
    assert decoded.docs_index_exists is False


def test_encode_decode_daemon_status_response() -> None:
    resp = DaemonStatusResponse(
        version="1.0.0",
        uptime_seconds=42.5,
        projects=[
            DaemonProjectInfo(project_root="/tmp/proj", indexing=False),
        ],
    )
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, DaemonStatusResponse)
    assert decoded.version == "1.0.0"
    assert decoded.uptime_seconds == 42.5
    assert len(decoded.projects) == 1
    assert decoded.projects[0].project_root == "/tmp/proj"
    assert decoded.projects[0].indexing is False


def test_tagged_union_dispatch() -> None:
    req = IndexRequest(project_root="/tmp")
    data = encode_request(req)
    decoded = decode_request(data)
    assert isinstance(decoded, IndexRequest)
    assert decoded.index_type == "code"
    assert not isinstance(decoded, HandshakeRequest)


def test_encode_decode_doctor_request() -> None:
    req = DoctorRequest(project_root="/tmp/proj")
    data = encode_request(req)
    decoded = decode_request(data)
    assert isinstance(decoded, DoctorRequest)
    assert decoded.project_root == "/tmp/proj"


def test_encode_decode_doctor_request_no_project() -> None:
    req = DoctorRequest()
    data = encode_request(req)
    decoded = decode_request(data)
    assert isinstance(decoded, DoctorRequest)
    assert decoded.project_root is None


def test_encode_decode_doctor_response() -> None:
    result = DoctorCheckResult(
        name="Model Check", ok=True, details=["Embedding dimension: 384"], errors=[]
    )
    resp = DoctorResponse(result=result, final=False)
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, DoctorResponse)
    assert decoded.result.name == "Model Check"
    assert decoded.result.ok is True
    assert decoded.result.details == ["Embedding dimension: 384"]
    assert decoded.final is False


def test_encode_decode_doctor_response_final() -> None:
    result = DoctorCheckResult(name="done", ok=True, details=[], errors=[])
    resp = DoctorResponse(result=result, final=True)
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, DoctorResponse)
    assert decoded.final is True


def test_encode_decode_daemon_env_request() -> None:
    req = DaemonEnvRequest()
    data = encode_request(req)
    decoded = decode_request(data)
    assert isinstance(decoded, DaemonEnvRequest)


def test_encode_decode_daemon_env_response() -> None:
    resp = DaemonEnvResponse(
        env_names=["HOME", "PATH", "GEMINI_API_KEY"],
        settings_env_names=["GEMINI_API_KEY"],
    )
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, DaemonEnvResponse)
    assert decoded.env_names == ["HOME", "PATH", "GEMINI_API_KEY"]
    assert decoded.settings_env_names == ["GEMINI_API_KEY"]


def test_all_request_types_round_trip() -> None:
    requests: list[Request] = [
        HandshakeRequest(version="1.0.0"),
        IndexRequest(project_root="/tmp"),
        SearchRequest(project_root="/tmp", query="test"),
        ProjectStatusRequest(project_root="/tmp"),
        DaemonStatusRequest(),
        RemoveProjectRequest(project_root="/tmp"),
        StopRequest(),
        DoctorRequest(project_root="/tmp"),
        DaemonEnvRequest(),
    ]
    for req in requests:
        data = encode_request(req)
        decoded = decode_request(data)
        assert type(decoded) is type(req)


def test_encode_decode_index_waiting_notice() -> None:
    resp = IndexWaitingNotice()
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, IndexWaitingNotice)


def test_encode_decode_index_progress_update() -> None:
    progress = IndexingProgress(
        num_execution_starts=10,
        num_unchanged=3,
        num_adds=5,
        num_deletes=1,
        num_reprocesses=0,
        num_errors=1,
    )
    resp = IndexProgressUpdate(progress=progress)
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, IndexProgressUpdate)
    assert decoded.progress.num_execution_starts == 10
    assert decoded.progress.num_unchanged == 3
    assert decoded.progress.num_adds == 5
    assert decoded.progress.num_deletes == 1
    assert decoded.progress.num_reprocesses == 0
    assert decoded.progress.num_errors == 1


def test_encode_decode_project_status_with_progress() -> None:
    progress = IndexingProgress(
        num_execution_starts=7,
        num_unchanged=2,
        num_adds=4,
        num_deletes=0,
        num_reprocesses=1,
        num_errors=0,
    )
    resp = ProjectStatusResponse(
        indexing=True,
        total_chunks=50,
        total_files=10,
        languages={"python": 50},
        progress=progress,
    )
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, ProjectStatusResponse)
    assert decoded.progress is not None
    assert decoded.progress.num_execution_starts == 7
    assert decoded.progress.num_adds == 4


def test_encode_decode_project_status_without_progress() -> None:
    resp = ProjectStatusResponse(
        indexing=False,
        total_chunks=50,
        total_files=10,
        languages={"python": 50},
    )
    data = encode_response(resp)
    decoded = decode_response(data)
    assert isinstance(decoded, ProjectStatusResponse)
    assert decoded.progress is None


def test_all_response_types_round_trip() -> None:
    responses: list[Response] = [
        IndexResponse(success=True),
        IndexProgressUpdate(
            progress=IndexingProgress(
                num_execution_starts=0,
                num_unchanged=0,
                num_adds=0,
                num_deletes=0,
                num_reprocesses=0,
                num_errors=0,
            )
        ),
        IndexWaitingNotice(),
        SearchResponse(success=True),
        ProjectStatusResponse(indexing=False, total_chunks=0, total_files=0, languages={}),
        DaemonStatusResponse(version="1.0.0", uptime_seconds=0.0, projects=[]),
        RemoveProjectResponse(ok=True),
        StopResponse(ok=True),
        DoctorResponse(
            result=DoctorCheckResult(name="test", ok=True, details=[], errors=[]),
        ),
        DaemonEnvResponse(env_names=["HOME"], settings_env_names=[]),
        ErrorResponse(message="err"),
    ]
    for resp in responses:
        data = encode_response(resp)
        decoded = decode_response(data)
        assert type(decoded) is type(resp)
