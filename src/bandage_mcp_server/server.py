"""FastMCP 서버 정의.

여기에는 아직 도메인 Tool/Resource를 정의하지 않는다.
원격 배포와 동작 확인을 위한 최소한의 헬스체크 Tool만 등록한다.
실제 프로젝트 관리용 Tool은 이후 단계에서 추가한다.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from . import slack
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


# 모듈 레벨 인스턴스 (uvicorn 등에서 직접 import 가능)
app = create_server()
