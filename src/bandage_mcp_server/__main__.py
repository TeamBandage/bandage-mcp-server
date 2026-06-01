"""실행 진입점.

사용법:
    python -m bandage_mcp_server
    bandage-mcp-server            # (설치 후 콘솔 스크립트)

transport 는 BANDAGE_TRANSPORT 환경변수로 제어한다.
원격 배포 시 기본값 "streamable-http" 를 그대로 사용하면 된다.
"""

from __future__ import annotations
import logging
from .config import get_settings
from .server import create_server
logger = logging.getLogger("bandage-mcp-server")

def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logger = logging.getLogger(settings.server_name)

    mcp = create_server(settings)

    if settings.transport == "stdio":
        logger.info("Starting MCP server over stdio")
        mcp.run(transport="stdio")
    else:
        logger.info(
            "Starting MCP server: transport=%s host=%s port=%s path=%s",
            settings.transport,
            settings.host,
            settings.port,
            settings.mount_path,
        )
        mcp.run(transport=settings.transport)


if __name__ == "__main__":
    main()
