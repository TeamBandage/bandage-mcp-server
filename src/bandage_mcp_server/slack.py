"""Slack Incoming Webhook 전송 로직.

전송 관심사를 server.py 에서 분리한다.
payload 구성(build_payload)과 실제 전송(send_to_slack)을 나눠
추후 Block Kit 등으로 확장할 때 build_payload 만 교체하면 되도록 한다.

모든 알림은 다음 두 규칙을 강제한다.
  1. 메타데이터(발신자 + 목적)를 항상 포함한다.
  2. 본문은 항상 Slack mrkdwn(Markdown) 문법으로 작성한다.
이 규칙은 send_to_slack 의 시그니처(필수 인자)로 강제되어,
호출자가 메타데이터 없이 임의 payload 를 전송할 수 없다.
"""

from __future__ import annotations

from enum import Enum

import httpx

# Webhook POST 타임아웃(초)
_TIMEOUT_SECONDS = 10.0


class NotifyPurpose(str, Enum):
    """알림 목적. 발신 시 반드시 명시해야 하는 메타데이터."""

    TASK_DONE = "작업 완료"
    ANNOUNCEMENT = "공지"
    CHANGE = "변경사항 알림"


# 목적별 헤더 이모지 (mrkdwn 헤더 라인에 사용)
_PURPOSE_EMOJI = {
    NotifyPurpose.TASK_DONE: "✅",
    NotifyPurpose.ANNOUNCEMENT: "📢",
    NotifyPurpose.CHANGE: "🔔",
}


class SlackNotifyError(Exception):
    """Slack 전송 실패 시 발생한다. (메시지에 Webhook URL 을 포함하지 않는다)"""


def resolve_sender(explicit: str | None, configured: str | None, fallback: str) -> str:
    """발신자를 우선순위에 따라 결정한다.

    우선순위: 명시적 인자 > 설정된 AI Agent 이메일 > fallback(server_name).
    공백뿐인 값은 비어 있는 것으로 본다.
    """
    for candidate in (explicit, configured, fallback):
        if candidate and candidate.strip():
            return candidate.strip()
    return fallback


def build_payload(
    text: str,
    *,
    sender: str,
    purpose: NotifyPurpose,
    title: str | None = None,
    link: str | None = None,
) -> dict:
    """Incoming Webhook 표준 페이로드(``{"text": ...}``)를 구성한다.

    메타데이터(발신자/목적)를 항상 포함하고, 전체를 Slack mrkdwn 문법으로 조합한다.
    (Incoming Webhook 의 top-level ``text`` 는 Slack 에서 mrkdwn 으로 렌더링된다.)

    구성:
      {emoji} *{목적}*       <- 목적 헤더
      *{title}*              <- title 이 있으면
      {text}                <- 본문 (호출자가 mrkdwn 으로 작성)
      <{link}|열기>          <- link 가 있으면
      _발신: {sender}_       <- 발신자 푸터
    """
    lines: list[str] = [f"{_PURPOSE_EMOJI[purpose]} *{purpose.value}*", ""]
    if title:
        lines.append(f"*{title}*")
    lines.append(text)
    if link:
        lines.append(f"<{link}|열기>")
    lines.append("")
    lines.append(f"_발신: {sender}_")

    return {"text": "\n".join(lines)}


async def send_to_slack(
    webhook_url: str,
    *,
    text: str,
    sender: str,
    purpose: NotifyPurpose,
    title: str | None = None,
    link: str | None = None,
) -> None:
    """알림을 Webhook URL 로 POST 한다.

    메타데이터(발신자/목적)는 필수 인자이며, 본문은 mrkdwn 으로 조합되어 전송된다.
    빈 발신자는 거부한다.

    비-2xx 응답 또는 네트워크 예외 시 :class:`SlackNotifyError` 를 발생시킨다.
    예외 메시지에는 Webhook URL 을 노출하지 않는다.
    """
    if not sender or not sender.strip():
        raise SlackNotifyError("발신자(sender)는 필수입니다.")

    payload = build_payload(text, sender=sender, purpose=purpose, title=title, link=link)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(webhook_url, json=payload)
    except httpx.HTTPError as exc:
        raise SlackNotifyError(f"Slack 전송 중 네트워크 오류: {exc.__class__.__name__}") from exc

    if response.status_code // 100 != 2:
        raise SlackNotifyError(
            f"Slack 전송 실패: status={response.status_code} body={response.text[:200]!r}"
        )
