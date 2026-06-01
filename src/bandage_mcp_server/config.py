"""환경변수 기반 서버 설정."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """런타임 설정.

    환경변수 또는 `.env` 파일에서 읽어온다. (prefix: ``BANDAGE_``)
    예) ``BANDAGE_HOST=0.0.0.0``, ``BANDAGE_PORT=8000``
    """

    model_config = SettingsConfigDict(
        env_prefix="BANDAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 서버 메타데이터
    server_name: str = "bandage-mcp-server"

    # 네트워크 바인딩 (원격 배포 시 0.0.0.0 권장)
    host: str = "0.0.0.0"
    port: int = 8000

    # transport: "streamable-http" | "sse" | "stdio"
    transport: str = "streamable-http"

    # streamable-http 마운트 경로
    mount_path: str = "/mcp"

    # 로그 레벨
    log_level: str = "INFO"


def get_settings() -> Settings:
    """설정 인스턴스를 생성해 반환한다."""
    return Settings()
