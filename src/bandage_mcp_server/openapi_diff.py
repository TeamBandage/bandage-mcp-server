"""oasdiff 서브프로세스 래퍼 + JSON 출력 파싱.

diff 엔진(oasdiff, Go 단일 바이너리) 호출을 한 모듈에 격리한다.
정규화된 두 스펙(dict)을 임시 파일로 떨군 뒤 ``oasdiff changelog --format json`` 을
실행하고, 출력 JSON 을 :class:`Change` 리스트로 파싱한다.

oasdiff 1.18.6 출력 구조(실측 확정):
  {id, text, comment, level(int), operation(METHOD), operationId, path, section, fingerprint}
  level 매핑: 1=INFO, 2=WARN, 3=ERR
  breaking(= ``oasdiff breaking``) = level >= WARN(2)
  변경 없음이면 ``[]`` 출력. operationId 는 SpringDoc 스펙에서 항상 포함되나,
  미제공 케이스를 대비해 매칭 측에서 path fallback 을 둔다.

oasdiff 는 top-level ``servers`` 변경을 무시한다(실측). 정규화는 방어적 보조.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

# oasdiff 서브프로세스 타임아웃 기본값(초).
_TIMEOUT_SECONDS = 30.0

# oasdiff 정수 level → 심각도 이름.
_LEVEL_NAMES = {1: "INFO", 2: "WARN", 3: "ERR"}

# breaking 으로 간주하는 최소 level (oasdiff `breaking` 서브커맨드와 동일하게 WARN 이상).
_BREAKING_MIN_LEVEL = 2


class OasdiffError(Exception):
    """oasdiff 실행 실패 (비정상 종료/타임아웃)."""


class OasdiffNotFoundError(OasdiffError):
    """oasdiff 바이너리를 찾을 수 없음 (미설치/경로 오류)."""


class OasdiffParseError(OasdiffError):
    """oasdiff 출력 JSON 파싱 실패."""


@dataclass(frozen=True)
class Change:
    """개별 스펙 변경 1건."""

    id: str  # oasdiff change id (예: "request-parameter-removed")
    level: int  # 1=INFO, 2=WARN, 3=ERR
    path: str | None  # 영향받는 endpoint 경로
    method: str | None  # HTTP 메서드(대문자)
    operation_id: str | None  # operationId (없을 수 있음 → 매칭 측 fallback)
    text: str  # 사람이 읽는 설명

    @property
    def level_name(self) -> str:
        return _LEVEL_NAMES.get(self.level, str(self.level))

    @property
    def is_breaking(self) -> bool:
        return self.level >= _BREAKING_MIN_LEVEL

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "level": self.level_name,
            "path": self.path,
            "method": self.method,
            "operation_id": self.operation_id,
            "detail": self.text,
        }


def is_breaking(change: Change) -> bool:
    """level 이 WARN 이상이면 breaking 으로 본다 (oasdiff `breaking` 과 동일)."""
    return change.is_breaking


def _parse_changelog(raw: list) -> list[Change]:
    """oasdiff changelog --format json 출력(list)을 Change 리스트로 변환한다.

    구조화 필드(path/operationId)를 우선 사용하고, 누락 시 text 에서 경로를
    정규식으로 추출하는 fallback 을 둔다(신뢰도 낮음).
    """
    import re

    _PATH_RE = re.compile(r"/api/v\d+/\S+")

    changes: list[Change] = []
    for item in raw:
        path = item.get("path")
        if not path:
            m = _PATH_RE.search(item.get("text", ""))
            path = m.group(0) if m else None
        changes.append(
            Change(
                id=item.get("id", "unknown"),
                level=int(item.get("level", 0)),
                path=path,
                method=(item.get("operation") or None),
                operation_id=(item.get("operationId") or None),
                text=item.get("text", ""),
            )
        )
    return changes


async def run_oasdiff_changelog(
    bin_path: str, base_path: str, head_path: str, *, timeout: float = _TIMEOUT_SECONDS
) -> list:
    """oasdiff changelog --format json 을 실행하고 파싱된 JSON(list)을 반환한다.

    shell 을 거치지 않고 인자를 직접 전달한다(인젝션 방지).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            bin_path,
            "changelog",
            base_path,
            head_path,
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise OasdiffNotFoundError(
            f"oasdiff 바이너리를 찾을 수 없습니다: {bin_path}. 설치 또는 BANDAGE_OASDIFF_BIN 설정을 확인하세요."
        ) from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise OasdiffError(f"oasdiff 실행이 {timeout}s 내에 끝나지 않았습니다.") from exc

    if proc.returncode != 0:
        err = stderr.decode("utf-8", "replace").strip()[:300]
        raise OasdiffError(f"oasdiff 비정상 종료 (code={proc.returncode}): {err}")

    text = stdout.decode("utf-8", "replace").strip()
    if not text:  # 변경 없음 시 빈 출력일 수 있음 → 빈 리스트
        return []
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise OasdiffParseError("oasdiff 출력 JSON 파싱 실패") from exc
    if not isinstance(data, list):
        raise OasdiffParseError(f"oasdiff 출력이 list 가 아닙니다: {type(data).__name__}")
    return data


async def diff_specs(
    bin_path: str, base_spec: dict, head_spec: dict, *, timeout: float = _TIMEOUT_SECONDS
) -> list[Change]:
    """정규화된 두 스펙(dict)을 비교해 Change 리스트를 반환한다.

    임시 파일은 호출 스코프 내에서만 존재한다(무상태 유지).
    """
    with tempfile.TemporaryDirectory(prefix="bandage-oasdiff-") as tmp:
        base_file = Path(tmp) / "base.json"
        head_file = Path(tmp) / "head.json"
        base_file.write_text(json.dumps(base_spec), encoding="utf-8")
        head_file.write_text(json.dumps(head_spec), encoding="utf-8")
        raw = await run_oasdiff_changelog(
            bin_path, str(base_file), str(head_file), timeout=timeout
        )
    return _parse_changelog(raw)
