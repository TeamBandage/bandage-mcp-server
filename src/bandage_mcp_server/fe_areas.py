"""FE 영역(fe_area) 매핑 로드 + 변경 매칭.

check_impacting_changes 의 조회 단위인 fe_area 정의를 FE 리포의 fe-areas.json
(source of truth)에서 읽어, 특정 영역에 귀속되는 스펙 변경만 골라낸다.

매칭 규칙: ``endpointPrefixes`` (longest-prefix ``startswith``) ∪ ``operationIds``.
operationIds 합집합이 필요한 이유: jam 영역의 createJamsFromSetlist 는
``/api/v1/setlists/{id}/jams`` 경유라 ``/api/v1/jams`` prefix 에 안 걸린다.

status 정책(area-status-policy.md):
  active       정상 평가
  partial-mock 평가하되 "일부 mock 병존" 경고 병기
  mock-only    endpointPrefixes 비어 있음 → 조회 제외, "미연동" 반환
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

# fe-areas.json fetch 타임아웃 기본값(초).
_TIMEOUT_SECONDS = 15.0


class FeAreasError(Exception):
    """fe-areas.json 로드/파싱 실패."""


class FeAreaNotFoundError(FeAreasError):
    """요청한 fe_area 가 매핑에 없음."""


@dataclass(frozen=True)
class Area:
    """fe_area 1건."""

    id: str
    label: str
    routes: list[str] = field(default_factory=list)
    endpoint_prefixes: list[str] = field(default_factory=list)
    status: str = "active"  # active | partial-mock | mock-only
    operation_ids: list[str] = field(default_factory=list)
    notes: str | None = None

    @property
    def is_mock_only(self) -> bool:
        return self.status == "mock-only" or not self.endpoint_prefixes

    @property
    def is_partial_mock(self) -> bool:
        return self.status == "partial-mock"


async def fetch_fe_areas(url: str, *, timeout: float = _TIMEOUT_SECONDS) -> dict:
    """fe-areas.json 을 raw URL 에서 받아 dict 로 반환한다."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise FeAreasError(f"fe-areas.json fetch 중 네트워크 오류: {exc.__class__.__name__}") from exc

    if response.status_code // 100 != 2:
        raise FeAreasError(f"fe-areas.json fetch 실패: status={response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise FeAreasError("fe-areas.json 이 유효한 JSON 이 아닙니다.") from exc


def parse_areas(doc: dict) -> dict[str, Area]:
    """fe-areas.json 문서를 {id: Area} 로 파싱한다."""
    areas: dict[str, Area] = {}
    for raw in doc.get("areas", []):
        area = Area(
            id=raw["id"],
            label=raw.get("label", raw["id"]),
            routes=list(raw.get("routes", [])),
            endpoint_prefixes=list(raw.get("endpointPrefixes", [])),
            status=raw.get("status", "active"),
            operation_ids=list(raw.get("operationIds", [])),
            notes=raw.get("notes"),
        )
        areas[area.id] = area
    return areas


def resolve_area(areas: dict[str, Area], fe_area: str) -> Area:
    """fe_area 를 id 또는 label 로 찾는다. 없으면 FeAreaNotFoundError."""
    if fe_area in areas:
        return areas[fe_area]
    for area in areas.values():
        if area.label == fe_area:
            return area
    valid = ", ".join(sorted(areas)) or "(없음)"
    raise FeAreaNotFoundError(f"알 수 없는 fe_area: {fe_area!r}. 유효한 영역: {valid}")


def match_changes(area: Area, changes):
    """endpointPrefixes(longest-prefix) ∪ operationIds 로 변경을 필터한다.

    - change.path 가 area.endpoint_prefixes 중 하나로 시작하면 매치.
    - change.operation_id 가 area.operation_ids 에 있으면 매치(prefix 미포함 op 포착).
    둘 중 하나라도 만족하면 포함(합집합).
    """
    op_ids = set(area.operation_ids)
    matched = []
    for c in changes:
        by_prefix = bool(c.path) and any(
            c.path.startswith(p) for p in area.endpoint_prefixes
        )
        by_op = bool(c.operation_id) and c.operation_id in op_ids
        if by_prefix or by_op:
            matched.append(c)
    return matched
