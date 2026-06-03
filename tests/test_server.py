"""기본 동작 스모크 테스트."""

from __future__ import annotations

import httpx
import pytest

from bandage_mcp_server import slack
from bandage_mcp_server.config import Settings
from bandage_mcp_server.server import create_server


def test_create_server_returns_instance() -> None:
    server = create_server(Settings())
    assert server.name == "bandage-mcp-server"


@pytest.mark.asyncio
async def test_ping_tool_registered() -> None:
    server = create_server(Settings())
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "ping" in names


@pytest.mark.asyncio
async def test_notify_slack_tool_registered() -> None:
    server = create_server(Settings())
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "notify_slack" in names


def test_resolve_sender_priority() -> None:
    # 명시적 인자가 최우선
    assert slack.resolve_sender("정선우", "agent@example.com", "srv") == "정선우"
    # 인자가 없으면 설정된 AI Agent 이메일
    assert slack.resolve_sender(None, "agent@example.com", "srv") == "agent@example.com"
    # 공백뿐이면 빈 값으로 간주하고 다음 후보로
    assert slack.resolve_sender("   ", None, "srv") == "srv"
    # 모두 비면 fallback
    assert slack.resolve_sender(None, None, "srv") == "srv"


def test_build_payload_includes_metadata() -> None:
    """발신자/목적 메타데이터가 항상 포함되어야 한다."""
    payload = slack.build_payload(
        text="배포 완료",
        sender="CI",
        purpose=slack.NotifyPurpose.TASK_DONE,
    )
    text = payload["text"]
    assert text.startswith(f"{slack._PURPOSE_EMOJI[slack.NotifyPurpose.TASK_DONE]} *작업 완료*")
    assert "배포 완료" in text
    assert "_발신: CI_" in text


def test_build_payload_with_title_and_link() -> None:
    payload = slack.build_payload(
        text="develop에 머지됨",
        sender="willjsw",
        purpose=slack.NotifyPurpose.CHANGE,
        title="BD-53",
        link="https://example.com/pr/1",
    )
    text = payload["text"]
    assert "🔔 *변경사항 알림*" in text
    assert "*BD-53*" in text
    assert "<https://example.com/pr/1|열기>" in text
    assert "_발신: willjsw_" in text


def _patched_client_factory(transport: httpx.MockTransport):
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    return _PatchedClient


@pytest.mark.asyncio
async def test_send_to_slack_raises_on_non_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))
    monkeypatch.setattr(slack.httpx, "AsyncClient", _patched_client_factory(transport))

    with pytest.raises(slack.SlackNotifyError):
        await slack.send_to_slack(
            "https://hooks.slack.test/xxx",
            text="hi",
            sender="CI",
            purpose=slack.NotifyPurpose.ANNOUNCEMENT,
        )


@pytest.mark.asyncio
async def test_send_to_slack_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="ok"))
    monkeypatch.setattr(slack.httpx, "AsyncClient", _patched_client_factory(transport))

    # 예외가 발생하지 않으면 성공.
    await slack.send_to_slack(
        "https://hooks.slack.test/xxx",
        text="hi",
        sender="CI",
        purpose=slack.NotifyPurpose.ANNOUNCEMENT,
    )


@pytest.mark.asyncio
async def test_send_to_slack_rejects_empty_sender() -> None:
    """빈 발신자는 거부한다 (전송 시도 없이 예외)."""
    with pytest.raises(slack.SlackNotifyError):
        await slack.send_to_slack(
            "https://hooks.slack.test/xxx",
            text="hi",
            sender="   ",
            purpose=slack.NotifyPurpose.CHANGE,
        )
