"""BE/FE 영향평가 Tool 의 오케스트레이션.

server.py 의 Tool 어댑터를 얇게 유지하기 위해, fetch → 정규화 → oasdiff → 필터
파이프라인을 여기서 조립한다.

- analyze_spec_change: 두 ref 의 스펙을 비교해 breaking/non-breaking 분류 (읽기전용·무상태)
- check_impacting_changes: since_ref(또는 FE 벤더 스냅샷) → develop-HEAD 의 net-diff 를
  fe_area 로 필터해 breaking/non-breaking 으로 나눠 반환 (읽기전용·무상태)
"""

from __future__ import annotations

import asyncio

from . import fe_areas, openapi_diff, spec_fetch
from .config import Settings

# Tool 출력에 항상 포함하는 한계(§9). 사용자에게 그대로 전달되도록 docstring 에 안내한다.
_BASE_LIMITATIONS = [
    "servers 필드는 환경값이라 비교에서 제외됩니다.",
    "응답의 Map(자유 키) 필드는 값 타입만 비교되며 키 집합 변경은 탐지되지 않습니다.",
    "memberId phantom query 교정(커밋 556fd77) 이전 ref 를 base 로 비교하면 "
    "85개 endpoint 의 'query 파라미터 삭제'가 breaking 으로 잡힐 수 있으나, 이는 실제 "
    "breaking 이 아닌 스펙 교정입니다.",
    "비인증 GitHub raw 는 IP당 시간당 60회 레이트리밋이 있습니다.",
]


def _limitations(changes: list[openapi_diff.Change]) -> list[str]:
    """기본 한계 + 조건부 한계(operationId 누락 등)를 합쳐 반환한다."""
    notes = list(_BASE_LIMITATIONS)
    if any(c.operation_id is None for c in changes):
        notes.append(
            "일부 변경에 operationId 가 없어, prefix 에 걸리지 않는 endpoint"
            "(예: createJamsFromSetlist)는 매칭에서 누락될 수 있습니다."
        )
    return notes


async def _fetch_be_spec(settings: Settings, ref: str) -> dict:
    spec = await spec_fetch.fetch_spec(
        settings.be_spec_url_template, ref, timeout=settings.spec_fetch_timeout_seconds
    )
    return spec_fetch.normalize_spec(spec)


async def _run_diff(
    settings: Settings, base_spec: dict, head_spec: dict
) -> list[openapi_diff.Change]:
    return await openapi_diff.diff_specs(
        settings.oasdiff_bin,
        base_spec,
        head_spec,
        timeout=settings.oasdiff_timeout_seconds,
    )


async def analyze_spec_change(
    settings: Settings, *, base_ref: str, head_ref: str
) -> dict:
    """두 ref 스펙을 비교해 breaking/non-breaking 으로 분류한다. (DB 미기록)"""
    base_spec, head_spec = await asyncio.gather(
        _fetch_be_spec(settings, base_ref),
        _fetch_be_spec(settings, head_ref),
    )
    changes = await _run_diff(settings, base_spec, head_spec)

    breaking = [c for c in changes if c.is_breaking]
    non_breaking = [c for c in changes if not c.is_breaking]
    return {
        "base_ref": base_ref,
        "head_ref": head_ref,
        "summary": {
            "total": len(changes),
            "breaking_count": len(breaking),
            "non_breaking_count": len(non_breaking),
        },
        "breaking_changes": [c.as_dict() for c in breaking],
        "non_breaking_changes": [c.as_dict() for c in non_breaking],
        "limitations": _limitations(changes),
    }


async def check_impacting_changes(
    settings: Settings, *, fe_area: str, since_ref: str | None
) -> dict:
    """fe_area 에 영향을 주는 변경을 net-diff 로 조회한다. (DB 미기록)

    매칭된 변경을 breaking / non-breaking 으로 나눠 반환한다(신규 API 추가 등
    non-breaking 도 FE 작업 트리거가 되므로 함께 보고).
    base 는 since_ref 지정 시 해당 ref 의 BE 스펙, 미지정 시 FE 벤더 스냅샷.
    head 는 항상 BE develop-HEAD.
    """
    doc = await fe_areas.fetch_fe_areas(
        settings.fe_areas_url, timeout=settings.spec_fetch_timeout_seconds
    )
    areas = fe_areas.parse_areas(doc)
    area = fe_areas.resolve_area(areas, fe_area)

    # mock-only: 매핑된 endpoint 가 없어 어떤 BE 변경에도 걸리지 않음 → 평가 불가.
    if area.is_mock_only:
        return {
            "fe_area": area.id,
            "area_status": area.status,
            "status": "mock-only",
            "message": "미연동 영역 — 평가 불가 (BE endpoint 매핑 없음).",
            "impacting_breaking": [],
            "impacting_non_breaking": [],
            "limitations": list(_BASE_LIMITATIONS),
        }

    # base 스펙 결정
    if since_ref:
        base_spec = await _fetch_be_spec(settings, since_ref)
        base_label = since_ref
    else:
        snapshot = await spec_fetch.fetch_spec_url(
            settings.fe_vendor_snapshot_url, timeout=settings.spec_fetch_timeout_seconds
        )
        base_spec = spec_fetch.normalize_spec(snapshot)
        base_label = "fe-vendor-snapshot"

    head_spec = await _fetch_be_spec(settings, settings.be_develop_ref)
    changes = await _run_diff(settings, base_spec, head_spec)

    # 전체 변경을 영역에 매칭한 뒤 breaking/non-breaking 으로 나눈다.
    # (신규 API 추가 등 non-breaking 도 FE 작업 트리거가 되므로 누락하지 않는다.)
    impacting = fe_areas.match_changes(area, changes)
    impacting_breaking = [c for c in impacting if c.is_breaking]
    impacting_non_breaking = [c for c in impacting if not c.is_breaking]

    flags: dict = {}
    if area.is_partial_mock:
        flags["partial_mock"] = (
            "이 영역은 일부 화면이 mock 데이터와 병존합니다. mock 구간 변경은 BE diff 로 "
            "잡히지 않으니 별도 점검하세요."
        )

    return {
        "fe_area": area.id,
        "area_label": area.label,
        "area_status": area.status,
        "base": base_label,
        "head_ref": settings.be_develop_ref,
        "summary": {
            "impacting_total": len(impacting),
            "impacting_breaking_count": len(impacting_breaking),
            "impacting_non_breaking_count": len(impacting_non_breaking),
        },
        "impacting_breaking": [c.as_dict() for c in impacting_breaking],
        "impacting_non_breaking": [c.as_dict() for c in impacting_non_breaking],
        "flags": flags,
        "limitations": _limitations(changes),
    }
