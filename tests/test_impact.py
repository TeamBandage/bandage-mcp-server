"""BE/FE 영향평가 Tool 단위/통합(모킹) 테스트.

실제 oasdiff 실행이나 네트워크에 의존하지 않는다.
oasdiff 출력은 T1 spike 에서 캡처한 픽스처(tests/fixtures/)를 사용하고,
httpx fetch 와 oasdiff 서브프로세스는 monkeypatch 로 모킹한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from bandage_mcp_server import fe_areas, impact, openapi_diff, spec_fetch
from bandage_mcp_server.config import Settings
from bandage_mcp_server.server import create_server

_FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> list:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Tool 등록
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_impact_tools_registered() -> None:
    server = create_server(Settings())
    names = {t.name for t in await server.list_tools()}
    assert "analyze_spec_change" in names
    assert "check_impacting_changes" in names


# --------------------------------------------------------------------------- #
# normalize_spec — servers 제거
# --------------------------------------------------------------------------- #
def test_normalize_strips_servers_recursively() -> None:
    spec = {
        "openapi": "3.1.0",
        "servers": [{"url": "http://x"}],
        "paths": {"/a": {"get": {"servers": [{"url": "http://y"}], "operationId": "a"}}},
    }
    out = spec_fetch.normalize_spec(spec)
    assert "servers" not in out
    assert "servers" not in out["paths"]["/a"]["get"]
    assert out["paths"]["/a"]["get"]["operationId"] == "a"
    # 원본 불변
    assert "servers" in spec


# --------------------------------------------------------------------------- #
# _parse_changelog — 실측 픽스처
# --------------------------------------------------------------------------- #
def test_parse_warn_fixture() -> None:
    changes = openapi_diff._parse_changelog(_load("oasdiff_changelog_warn.json"))
    assert len(changes) == 85
    assert all(c.level == 2 and c.level_name == "WARN" for c in changes)
    assert all(c.operation_id for c in changes)  # operationId 항상 포함
    assert all(c.is_breaking for c in changes)  # WARN 이상 = breaking
    sample = next(c for c in changes if c.operation_id == "createBand")
    assert sample.path == "/api/v1/bands"
    assert sample.method == "POST"
    assert sample.id == "request-parameter-removed"


def test_parse_err_fixture() -> None:
    changes = openapi_diff._parse_changelog(_load("oasdiff_changelog_err.json"))
    assert len(changes) == 1
    c = changes[0]
    assert c.level == 3 and c.level_name == "ERR" and c.is_breaking
    assert c.id == "api-path-removed-without-deprecation"
    assert c.operation_id == "login"


def test_parse_path_fallback_from_text() -> None:
    """path 누락 시 text 에서 경로 추출."""
    raw = [{"id": "x", "level": 3, "text": "removed /api/v1/jams/{id}", "operation": "GET"}]
    c = openapi_diff._parse_changelog(raw)[0]
    assert c.path == "/api/v1/jams/{id}"
    assert c.operation_id is None


# --------------------------------------------------------------------------- #
# match_changes — prefix ∪ operationId, mock-only/partial-mock
# --------------------------------------------------------------------------- #
def _change(path=None, op=None, level=3):
    return openapi_diff.Change(id="x", level=level, path=path, method="GET", operation_id=op, text="")


def test_match_by_prefix() -> None:
    area = fe_areas.Area(id="band", label="밴드", endpoint_prefixes=["/api/v1/bands"])
    changes = [_change(path="/api/v1/bands/1"), _change(path="/api/v1/auth/login")]
    matched = fe_areas.match_changes(area, changes)
    assert len(matched) == 1 and matched[0].path == "/api/v1/bands/1"


def test_match_by_operation_id_cross_prefix() -> None:
    """createJamsFromSetlist 는 /api/v1/setlists/.. 경유라 prefix 미포함 → operationId 로 포착."""
    area = fe_areas.Area(
        id="jam",
        label="jam",
        endpoint_prefixes=["/api/v1/jams"],
        operation_ids=["createJamsFromSetlist"],
    )
    changes = [_change(path="/api/v1/setlists/9/jams", op="createJamsFromSetlist")]
    assert len(fe_areas.match_changes(area, changes)) == 1


def test_resolve_area_by_id_and_label() -> None:
    areas = {"jam": fe_areas.Area(id="jam", label="합주(Jam)")}
    assert fe_areas.resolve_area(areas, "jam").id == "jam"
    assert fe_areas.resolve_area(areas, "합주(Jam)").id == "jam"
    with pytest.raises(fe_areas.FeAreaNotFoundError):
        fe_areas.resolve_area(areas, "nope")


def test_area_mock_only_detection() -> None:
    assert fe_areas.Area(id="s", label="s", status="mock-only").is_mock_only
    # endpoint_prefixes 가 비면 status 무관하게 mock-only 취급
    assert fe_areas.Area(id="s", label="s", status="active").is_mock_only


# --------------------------------------------------------------------------- #
# fetch 모킹 — 상태코드별 예외
# --------------------------------------------------------------------------- #
def _patched_client_factory(transport: httpx.MockTransport):
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    return _PatchedClient


@pytest.mark.asyncio
async def test_fetch_spec_404(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(404, text="not found"))
    monkeypatch.setattr(spec_fetch.httpx, "AsyncClient", _patched_client_factory(transport))
    with pytest.raises(spec_fetch.SpecNotFoundError):
        await spec_fetch.fetch_spec("http://x/{ref}/o.json", "bad-ref")


@pytest.mark.asyncio
async def test_fetch_spec_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(429, text="slow down"))
    monkeypatch.setattr(spec_fetch.httpx, "AsyncClient", _patched_client_factory(transport))
    with pytest.raises(spec_fetch.SpecRateLimitError):
        await spec_fetch.fetch_spec("http://x/{ref}/o.json", "develop")


@pytest.mark.asyncio
async def test_fetch_spec_403_ratelimit_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, text="")
    )
    monkeypatch.setattr(spec_fetch.httpx, "AsyncClient", _patched_client_factory(transport))
    with pytest.raises(spec_fetch.SpecRateLimitError):
        await spec_fetch.fetch_spec("http://x/{ref}/o.json", "develop")


# --------------------------------------------------------------------------- #
# oasdiff 서브프로세스 모킹
# --------------------------------------------------------------------------- #
class _FakeProc:
    def __init__(self, stdout: bytes, returncode: int = 0, stderr: bytes = b""):
        self._stdout, self._stderr, self.returncode = stdout, stderr, returncode

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):  # pragma: no cover - 타임아웃 경로에서만
        pass


def _fake_exec_returning(stdout: bytes, returncode: int = 0, stderr: bytes = b""):
    async def _exec(*args, **kwargs):
        return _FakeProc(stdout, returncode, stderr)

    return _exec


@pytest.mark.asyncio
async def test_run_oasdiff_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openapi_diff.asyncio, "create_subprocess_exec", _fake_exec_returning(b"  "))
    assert await openapi_diff.run_oasdiff_changelog("oasdiff", "b", "h") == []


@pytest.mark.asyncio
async def test_run_oasdiff_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(openapi_diff.asyncio, "create_subprocess_exec", _raise)
    with pytest.raises(openapi_diff.OasdiffNotFoundError):
        await openapi_diff.run_oasdiff_changelog("oasdiff", "b", "h")


@pytest.mark.asyncio
async def test_run_oasdiff_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openapi_diff.asyncio,
        "create_subprocess_exec",
        _fake_exec_returning(b"", returncode=1, stderr=b"boom"),
    )
    with pytest.raises(openapi_diff.OasdiffError):
        await openapi_diff.run_oasdiff_changelog("oasdiff", "b", "h")


# --------------------------------------------------------------------------- #
# E2E (모킹) — check_impacting_changes
# --------------------------------------------------------------------------- #
_FE_AREAS_DOC = {
    "areas": [
        {"id": "band", "label": "밴드", "endpointPrefixes": ["/api/v1/bands"], "status": "active"},
        {
            "id": "schedule-coordination",
            "label": "일정 조율",
            "endpointPrefixes": [],
            "status": "mock-only",
        },
    ]
}


@pytest.mark.asyncio
async def test_check_impacting_changes_filters_breaking(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()

    async def _fake_fetch_fe_areas(url, *, timeout):
        return _FE_AREAS_DOC

    async def _fake_fetch_spec(template, ref, *, timeout):
        return {"openapi": "3.1.0", "paths": {}}

    async def _fake_fetch_url(url, *, timeout):
        return {"openapi": "3.1.0", "paths": {}}

    # band 영역에 걸리는 ERR 1건 + 다른 영역 1건
    async def _fake_diff(bin_path, base, head, *, timeout):
        return [
            openapi_diff.Change("api-removed", 3, "/api/v1/bands/1", "DELETE", "deleteBand", "x"),
            openapi_diff.Change("api-removed", 3, "/api/v1/auth/login", "POST", "login", "x"),
        ]

    monkeypatch.setattr(impact.fe_areas, "fetch_fe_areas", _fake_fetch_fe_areas)
    monkeypatch.setattr(impact.spec_fetch, "fetch_spec", _fake_fetch_spec)
    monkeypatch.setattr(impact.spec_fetch, "fetch_spec_url", _fake_fetch_url)
    monkeypatch.setattr(impact.openapi_diff, "diff_specs", _fake_diff)

    result = await impact.check_impacting_changes(settings, fe_area="band", since_ref=None)
    assert result["base"] == "fe-vendor-snapshot"
    assert result["summary"]["impacting_breaking_count"] == 1
    assert result["summary"]["impacting_non_breaking_count"] == 0
    assert result["impacting_breaking"][0]["path"] == "/api/v1/bands/1"
    assert result["impacting_non_breaking"] == []
    assert result["limitations"]


@pytest.mark.asyncio
async def test_check_impacting_changes_includes_non_breaking(monkeypatch: pytest.MonkeyPatch) -> None:
    """신규 API 추가(level 1, non-breaking)도 영역에 매칭되면 보고된다."""
    settings = Settings()

    async def _fake_fetch_fe_areas(url, *, timeout):
        return _FE_AREAS_DOC

    async def _fake_fetch_spec(template, ref, *, timeout):
        return {"openapi": "3.1.0", "paths": {}}

    async def _fake_fetch_url(url, *, timeout):
        return {"openapi": "3.1.0", "paths": {}}

    # band 영역: breaking 1건(삭제) + non-breaking 1건(신규 엔드포인트), 그리고 타 영역 1건
    async def _fake_diff(bin_path, base, head, *, timeout):
        return [
            openapi_diff.Change("api-removed", 3, "/api/v1/bands/1", "DELETE", "deleteBand", "x"),
            openapi_diff.Change(
                "endpoint-added", 1, "/api/v1/bands/9/members", "POST", "addBandMember", "x"
            ),
            openapi_diff.Change("api-removed", 3, "/api/v1/auth/login", "POST", "login", "x"),
        ]

    monkeypatch.setattr(impact.fe_areas, "fetch_fe_areas", _fake_fetch_fe_areas)
    monkeypatch.setattr(impact.spec_fetch, "fetch_spec", _fake_fetch_spec)
    monkeypatch.setattr(impact.spec_fetch, "fetch_spec_url", _fake_fetch_url)
    monkeypatch.setattr(impact.openapi_diff, "diff_specs", _fake_diff)

    result = await impact.check_impacting_changes(settings, fe_area="band", since_ref=None)
    assert result["summary"]["impacting_total"] == 2
    assert result["summary"]["impacting_breaking_count"] == 1
    assert result["summary"]["impacting_non_breaking_count"] == 1
    assert result["impacting_breaking"][0]["path"] == "/api/v1/bands/1"
    assert result["impacting_non_breaking"][0]["path"] == "/api/v1/bands/9/members"
    assert result["impacting_non_breaking"][0]["level"] == "INFO"


@pytest.mark.asyncio
async def test_check_impacting_changes_mock_only(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_fetch_fe_areas(url, *, timeout):
        return _FE_AREAS_DOC

    monkeypatch.setattr(impact.fe_areas, "fetch_fe_areas", _fake_fetch_fe_areas)
    result = await impact.check_impacting_changes(
        Settings(), fe_area="schedule-coordination", since_ref=None
    )
    assert result["status"] == "mock-only"
    assert result["impacting_breaking"] == []
    assert result["impacting_non_breaking"] == []
