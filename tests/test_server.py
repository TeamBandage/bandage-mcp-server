"""기본 동작 스모크 테스트."""

from __future__ import annotations

import pytest

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
