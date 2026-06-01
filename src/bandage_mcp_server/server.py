"""FastMCP 서버 정의.

여기에는 아직 도메인 Tool/Resource를 정의하지 않는다.
원격 배포와 동작 확인을 위한 최소한의 헬스체크 Tool만 등록한다.
실제 프로젝트 관리용 Tool은 이후 단계에서 추가한다.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

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

    register_tools(mcp)

    return mcp


def register_tools(mcp: FastMCP) -> None:
    """Tool을 등록한다."""

    @mcp.tool()
    def ping() -> str:
        """서버 동작 확인용 헬스체크. 'pong'을 반환한다."""
        logger.info("tool called: ping")
        return "pong"


# 모듈 레벨 인스턴스 (uvicorn 등에서 직접 import 가능)
app = create_server()
