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

    # Slack Incoming Webhook URL (채널별 발급). 미설정 시 notify_slack Tool 비활성.
    slack_webhook_url: str | None = None

    # 알림 발신자로 사용할 AI Agent 계정 이메일.
    # notify_slack 호출 시 sender 가 명시되지 않으면 이 값으로 채운다.
    # (추후 인증 게이트웨이가 헤더로 발신자를 내려주면 그 값이 우선한다.)
    agent_email: str | None = None


def get_settings() -> Settings:
    """설정 인스턴스를 생성해 반환한다."""
    return Settings()
