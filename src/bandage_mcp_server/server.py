"""FastMCP 서버 정의.

여기에는 아직 도메인 Tool/Resource를 정의하지 않는다.
원격 배포와 동작 확인을 위한 최소한의 헬스체크 Tool만 등록한다.
실제 프로젝트 관리용 Tool은 이후 단계에서 추가한다.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from . import fe_areas, impact, openapi_diff, slack, spec_fetch
from .config import Settings, get_settings

logger = logging.getLogger("bandage-mcp-server")


def create_server(settings: Settings | None = None) -> FastMCP:
    """설정을 받아 FastMCP 인스턴스를 생성하고 Tool을 등록한다."""
    settings = settings or get_settings()

    mcp = FastMCP(
        name=settings.server_name,
        host=settings.host,
        port=settings.port,
        # streamable-http 사용 시 마운트 경로
        streamable_http_path=settings.mount_path,
    )

    register_tools(mcp, settings)

    return mcp


def register_tools(mcp: FastMCP, settings: Settings) -> None:
    """Tool을 등록한다."""

    @mcp.tool()
    def ping() -> str:
        """서버 동작 확인용 헬스체크. 'pong'을 반환한다."""
        logger.info("tool called: ping")
        return "pong"

    @mcp.tool()
    async def notify_slack(
        text: str,
        purpose: slack.NotifyPurpose,
        sender: str | None = None,
        title: str | None = None,
        link: str | None = None,
    ) -> str:
        """변경사항/공지/작업 완료를 Slack 채널로 알린다.

        모든 알림에는 메타데이터(발신자·목적)가 항상 포함되며,
        본문은 Slack mrkdwn(Markdown) 문법으로 렌더링된다.

        text: 알림 본문(필수). mrkdwn 문법으로 작성한다.
        purpose: 알림 목적(필수). "작업 완료" | "공지" | "변경사항 알림".
        sender: 발신자(선택). 미지정 시 서버에 설정된 AI Agent 계정 이메일을 사용한다.
        title: 강조 제목(선택). link: 참고 URL(선택).
        성공 시 'sent'를 반환한다.
        """
        logger.info("tool called: notify_slack (purpose=%s)", purpose.value)

        if not settings.slack_webhook_url:
            logger.warning("notify_slack: BANDAGE_SLACK_WEBHOOK_URL 미설정")
            return (
                "Slack Webhook URL이 설정되지 않았습니다. "
                "환경변수 BANDAGE_SLACK_WEBHOOK_URL을 설정하세요."
            )

        resolved_sender = slack.resolve_sender(
            sender, settings.agent_email, settings.server_name
        )

        try:
            await slack.send_to_slack(
                settings.slack_webhook_url,
                text=text,
                sender=resolved_sender,
                purpose=purpose,
                title=title,
                link=link,
            )
        except slack.SlackNotifyError as exc:
            logger.error("notify_slack 실패: %s", exc)
            return f"전송 실패: {exc}"

        logger.info("notify_slack: sent")
        return "sent"

    @mcp.tool()
    async def analyze_spec_change(base_ref: str, head_ref: str) -> dict:
        """두 git ref 의 OpenAPI 스펙을 비교해 BE 변경의 breaking/non-breaking 을 분류한다.

        BE/FE 영향평가용. 읽기전용이며 어떤 것도 저장하지 않는다.

        base_ref: 비교 기준 ref (브랜치/태그/커밋 SHA). 예: "develop".
        head_ref: 비교 대상 ref. 예: 작업 브랜치명 또는 SHA.
        servers 필드(환경값)는 비교에서 제외된다.

        반환: {base_ref, head_ref, summary, breaking_changes[], non_breaking_changes[],
        limitations[]}. limitations 는 결과 해석상의 주의사항이니 사용자에게 함께 전달한다.
        """
        logger.info("tool called: analyze_spec_change (%s..%s)", base_ref, head_ref)
        try:
            return await impact.analyze_spec_change(
                settings, base_ref=base_ref, head_ref=head_ref
            )
        except spec_fetch.SpecNotFoundError as exc:
            return {"error": "ref 를 찾을 수 없습니다. ref 철자를 확인하세요.", "detail": str(exc)}
        except spec_fetch.SpecRateLimitError as exc:
            return {"error": "GitHub raw 레이트리밋. 잠시 후 재시도하세요.", "detail": str(exc)}
        except openapi_diff.OasdiffNotFoundError as exc:
            return {"error": "oasdiff 바이너리를 찾을 수 없습니다. 서버 환경을 확인하세요.", "detail": str(exc)}
        except (openapi_diff.OasdiffError, spec_fetch.SpecFetchError) as exc:
            return {"error": "스펙 비교 실패", "detail": str(exc)}

    @mcp.tool()
    async def check_impacting_changes(fe_area: str, since_ref: str | None = None) -> dict:
        """특정 FE 영역(fe_area)에 영향을 주는 BE breaking 변경을 조회한다.

        since_ref(또는 미지정 시 FE 벤더 스냅샷)부터 BE develop-HEAD 까지의 변경 중,
        해당 영역의 endpoint prefix 또는 operationId 에 매칭되는 breaking 만 반환한다.
        읽기전용이며 저장하지 않는다.

        fe_area: FE 영역 id 또는 label (예: "jam", "band", "auth").
        since_ref: 비교 기준 ref (선택). 미지정 시 FE 가 마지막으로 vendoring 한 스냅샷 기준.
        mock-only 영역은 "미연동"으로 반환되고, partial-mock 영역은 경고가 병기된다.

        반환: {fe_area, area_status, base, head_ref, impacting_breaking[], flags, limitations[]}.
        limitations 는 사용자에게 함께 전달한다.
        """
        logger.info("tool called: check_impacting_changes (area=%s since=%s)", fe_area, since_ref)
        try:
            return await impact.check_impacting_changes(
                settings, fe_area=fe_area, since_ref=since_ref
            )
        except fe_areas.FeAreaNotFoundError as exc:
            return {"error": "알 수 없는 fe_area", "detail": str(exc)}
        except fe_areas.FeAreasError as exc:
            return {"error": "fe-areas.json 로드 실패", "detail": str(exc)}
        except spec_fetch.SpecNotFoundError as exc:
            return {"error": "ref 를 찾을 수 없습니다. since_ref 철자를 확인하세요.", "detail": str(exc)}
        except spec_fetch.SpecRateLimitError as exc:
            return {"error": "GitHub raw 레이트리밋. 잠시 후 재시도하세요.", "detail": str(exc)}
        except openapi_diff.OasdiffNotFoundError as exc:
            return {"error": "oasdiff 바이너리를 찾을 수 없습니다. 서버 환경을 확인하세요.", "detail": str(exc)}
        except (openapi_diff.OasdiffError, spec_fetch.SpecFetchError) as exc:
            return {"error": "영향평가 실패", "detail": str(exc)}


# 모듈 레벨 인스턴스 (uvicorn 등에서 직접 import 가능)
app = create_server()
