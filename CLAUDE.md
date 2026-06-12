# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

AI 프로젝트 관리를 위한 Python 기반 MCP(Model Context Protocol) 서버입니다. 원격 배포를 전제로 합니다. 등록된 Tool: 헬스체크 `ping`, Slack 알림 `notify_slack`, OpenAPI 스펙 비교 `analyze_spec_change`, FE 영역 영향평가 `check_impacting_changes`.

`analyze_spec_change` / `check_impacting_changes`는 BE/FE 영향평가용으로, [oasdiff](https://github.com/oasdiff/oasdiff)(OpenAPI 3.1 diff 엔진)를 서브프로세스로 호출합니다. 무상태(DB 없음)·무인증으로 동작하며 public GitHub raw URL에서 스펙·fe-areas.json을 fetch합니다. 로컬 개발 시 `brew install oasdiff` 필요(컨테이너 이미지엔 포함). 동작 원리는 `spec_fetch.py`(fetch+정규화) → `openapi_diff.py`(oasdiff 래퍼+파싱) → `fe_areas.py`(영역 매칭) → `impact.py`(조립) 순.

## 명령어

```bash
# 개발 환경 설치 (editable + dev 의존성)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 서버 실행 (기본 transport: streamable-http → http://0.0.0.0:8000/mcp)
python -m bandage_mcp_server

# 로컬 stdio 모드 실행
BANDAGE_TRANSPORT=stdio python -m bandage_mcp_server

# 테스트
pytest -q
pytest tests/test_server.py::test_ping_tool_registered   # 단일 테스트

# 린트 (ruff, line-length 100)
ruff check .

# 컨테이너 빌드/실행
docker build -t bandage-mcp-server .
docker run -p 8000:8000 bandage-mcp-server
```

## 아키텍처

`src/bandage_mcp_server/` 패키지는 세 개의 모듈로 설정·생성·실행 관심사를 분리합니다.

- **config.py** — `pydantic-settings` 기반 `Settings`. 모든 환경변수는 `BANDAGE_` prefix를 사용하며 `.env` 파일도 읽습니다. (`BANDAGE_HOST`, `BANDAGE_PORT`, `BANDAGE_TRANSPORT`, `BANDAGE_MOUNT_PATH`, `BANDAGE_LOG_LEVEL`)
- **server.py** — `create_server(settings)`가 `FastMCP` 인스턴스를 만들고 `register_tools()`로 Tool을 등록합니다. 모듈 레벨 `app = create_server()`는 uvicorn 등에서 직접 import할 수 있도록 노출됩니다.
- **\_\_main\_\_.py** — `main()` 진입점. `transport == "stdio"`면 stdio로, 아니면 설정된 transport(streamable-http/sse)로 `mcp.run()`을 호출합니다.

**새 Tool 추가 위치**: `server.py`의 `register_tools()` 안에서 `@mcp.tool()` 데코레이터로 함수를 등록합니다. docstring이 Tool 설명으로 사용됩니다.

**transport 선택**: 원격 배포 기본값은 `streamable-http`(마운트 경로 `/mcp`). 로컬 클라이언트 연동 시 `stdio`로 전환합니다.

## 커밋 컨벤션

모든 커밋 메시지는 아래 형식을 따릅니다.

```
[{issue-key}] {type}: {summary}
- {detail 1}
- {detail 2}
- {detail n}

{smart-commit-commands}
```

- **type** — `chore` | `feat` | `ai` | `test` | `refactor` | `fix` 중 하나
- **`[{issue-key}]`** — Jira 이슈에 연결된 브랜치에서 작업할 때 **필수**. 브랜치명에서 추출합니다(예: `feat/BAND-12-practice-crud` → `[BAND-12]`). 항상 첫 줄 맨 앞에 둡니다. 관련 이슈가 정말 없을 때만 생략합니다.
- **{summary}** — 변경 내용을 한 줄로 간결하게
- **bullet list** — 의미 있는 변경 1건당 한 줄(사소한 단일 변경이면 생략)
- **{smart-commit-commands}** — 선택. Jira Smart Commit 명령(`#done`, `#time 1h 30m`, `#comment ...` 등). 항상 빈 줄 뒤 맨 마지막 줄에 단독으로 둡니다.

예시:

```
[BAND-12] feat: 합주 생성 API 구현
- PracticeCreateRequest, PracticeResponse DTO 추가
- PracticeService.createPractice 구현
- POST /practices 엔드포인트 추가

#done #time 2h
```

## PR 컨벤션

PR 설명은 항상 `.github/PULL_REQUEST_TEMPLATE.md` 양식을 따르고, 모든 내용은 유효한 Markdown 문법으로 작성합니다.
