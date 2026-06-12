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

    # --- BE/FE 영향평가 Tool (analyze_spec_change / check_impacting_changes) ---
    # BE OpenAPI 스펙 raw URL 템플릿. {ref} 자리에 git ref(브랜치/태그/SHA)를 치환한다. (public 무인증)
    be_spec_url_template: str = (
        "https://raw.githubusercontent.com/TeamBandage/bandage-band-manager"
        "/{ref}/docs/openapi.json"
    )
    # FE 영역 매핑(fe-areas.json) raw URL. check_impacting_changes 의 조회 단위 source of truth.
    fe_areas_url: str = (
        "https://raw.githubusercontent.com/TeamBandage/bandage-fe-web/develop/fe-areas.json"
    )
    # FE 벤더 스냅샷(openapi/openapi.json) raw URL.
    # check_impacting_changes 에서 since_ref 미지정 시 비교 base 로 사용한다.
    fe_vendor_snapshot_url: str = (
        "https://raw.githubusercontent.com/TeamBandage/bandage-fe-web/develop/openapi/openapi.json"
    )
    # 영향평가의 head ref. 항상 BE develop-HEAD 와 비교한다.
    be_develop_ref: str = "develop"
    # oasdiff 바이너리 경로. 컨테이너에서는 절대경로로 덮어쓴다.
    oasdiff_bin: str = "oasdiff"
    # raw 스펙 fetch 타임아웃(초).
    spec_fetch_timeout_seconds: float = 15.0
    # oasdiff 서브프로세스 타임아웃(초).
    oasdiff_timeout_seconds: float = 30.0


def get_settings() -> Settings:
    """설정 인스턴스를 생성해 반환한다."""
    return Settings()
