"""OpenAPI 스펙 raw fetch + 정규화.

fetch 관심사를 server.py / impact.py 에서 분리한다.
public GitHub raw URL 에서 openapi.json 을 받아 dict 로 파싱하고,
diff 노이즈가 되는 ``servers`` 필드를 정규화 단계에서 제거한다.

oasdiff 1.18.6 자체는 top-level ``servers`` 변경을 무시하지만(실측 확인),
스펙(path/operation 레벨 servers 등)의 향후 변화에 대비해 방어적으로 정규화한다.

예외 메시지에는 요청 URL 을 노출하지 않는다. (조직 정책: 내부/식별 정보 최소 노출)
"""

from __future__ import annotations

import httpx

# raw fetch 타임아웃 기본값(초). config 로 주입받지 못한 호출의 폴백.
_TIMEOUT_SECONDS = 15.0


class SpecFetchError(Exception):
    """스펙 fetch 실패. (네트워크/HTTP 오류. 메시지에 URL 미노출)"""


class SpecNotFoundError(SpecFetchError):
    """스펙을 찾을 수 없음 (HTTP 404). 대개 ref 철자 오류."""


class SpecRateLimitError(SpecFetchError):
    """GitHub raw 레이트리밋 (HTTP 429 또는 403 + ratelimit 소진)."""


def _ratelimit_remaining(response: httpx.Response) -> int | None:
    """응답에서 남은 레이트리밋을 읽는다. 헤더가 없으면 None."""
    raw = response.headers.get("x-ratelimit-remaining")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _get_json(url: str, *, timeout: float) -> dict:
    """URL 에서 JSON 본문을 받아 dict 로 반환한다. 상태코드별로 전용 예외를 던진다."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise SpecFetchError(f"스펙 fetch 중 네트워크 오류: {exc.__class__.__name__}") from exc

    status = response.status_code
    if status == 404:
        raise SpecNotFoundError("스펙을 찾을 수 없습니다 (404). ref 철자를 확인하세요.")
    if status == 429 or (status == 403 and _ratelimit_remaining(response) == 0):
        raise SpecRateLimitError(
            "GitHub raw 레이트리밋에 도달했습니다 (비인증 IP당 시간당 60회). 잠시 후 재시도하세요."
        )
    if status // 100 != 2:
        raise SpecFetchError(f"스펙 fetch 실패: status={status}")

    try:
        return response.json()
    except ValueError as exc:
        raise SpecFetchError("스펙 응답이 유효한 JSON 이 아닙니다.") from exc


async def fetch_spec(url_template: str, ref: str, *, timeout: float = _TIMEOUT_SECONDS) -> dict:
    """``{ref}`` 치환 템플릿에서 특정 ref 의 openapi.json 을 받아온다.

    예) ``be_spec_url_template`` + ref="develop".
    """
    url = url_template.format(ref=ref)
    return await _get_json(url, timeout=timeout)


async def fetch_spec_url(url: str, *, timeout: float = _TIMEOUT_SECONDS) -> dict:
    """ref 치환 없는 고정 URL(예: FE 벤더 스냅샷)에서 openapi.json 을 받아온다."""
    return await _get_json(url, timeout=timeout)


def normalize_spec(spec: dict) -> dict:
    """diff 노이즈를 제거한 사본을 반환한다.

    환경마다 달라지는 ``servers`` 필드를 top-level 및 중첩(path/operation) 레벨에서
    재귀적으로 제거한다. 원본은 변형하지 않는다.
    """

    def _strip(node: object) -> object:
        if isinstance(node, dict):
            return {k: _strip(v) for k, v in node.items() if k != "servers"}
        if isinstance(node, list):
            return [_strip(v) for v in node]
        return node

    return _strip(spec)  # type: ignore[return-value]
