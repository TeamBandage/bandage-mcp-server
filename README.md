# bandage-mcp-server

MCP Server for AI Project Managing.

원격 배포를 전제로 한 Python 기반 MCP 서버입니다. 등록된 Tool:

- `ping` — 헬스체크
- `notify_slack` — Slack 변경사항/공지/작업완료 알림
- `analyze_spec_change` — 두 git ref 의 OpenAPI 스펙을 비교해 breaking/non-breaking 분류
- `check_impacting_changes` — 특정 FE 영역(fe_area)에 영향을 주는 BE breaking 변경 조회

## 구조

```
bandage-mcp-server/
├── pyproject.toml              # 패키지/의존성 정의 (uv·pip 호환)
├── Dockerfile                  # 원격 배포용 이미지 (oasdiff 바이너리 포함)
├── src/bandage_mcp_server/
│   ├── config.py               # 환경변수 기반 설정 (BANDAGE_ prefix)
│   ├── server.py               # FastMCP 인스턴스 및 Tool 등록
│   ├── slack.py                # Slack Incoming Webhook 전송
│   ├── spec_fetch.py           # OpenAPI 스펙 raw fetch + servers 정규화
│   ├── openapi_diff.py         # oasdiff 서브프로세스 래퍼 + 출력 파싱
│   ├── fe_areas.py             # fe-areas.json 로드 + fe_area 매칭
│   ├── impact.py               # 영향평가 Tool 오케스트레이션
│   └── __main__.py             # 실행 진입점
└── tests/
    ├── test_server.py          # 스모크 테스트
    ├── test_impact.py          # 영향평가 단위/통합(모킹) 테스트
    └── fixtures/               # oasdiff 출력 픽스처 (T1 spike 캡처)
```

## 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

`analyze_spec_change` / `check_impacting_changes` Tool 은 [oasdiff](https://github.com/oasdiff/oasdiff)
바이너리를 사용합니다(OpenAPI 3.1 diff). 로컬 개발 시 설치하세요. 컨테이너 이미지에는 이미 포함됩니다.

```bash
brew install oasdiff           # macOS
# 또는 release 바이너리를 PATH 에 배치. 경로는 BANDAGE_OASDIFF_BIN 으로 오버라이드 가능.
```

## 실행

기본 transport 는 원격 배포에 적합한 `streamable-http` 입니다.

```bash
python -m bandage_mcp_server          # http://0.0.0.0:8000/mcp
```

로컬 stdio 모드로 실행하려면:

```bash
BANDAGE_TRANSPORT=stdio python -m bandage_mcp_server
```

## 설정

환경변수(`.env` 또는 OS 환경)로 제어합니다. `BANDAGE_` prefix 를 사용합니다.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `BANDAGE_HOST` | `0.0.0.0` | 바인딩 호스트 |
| `BANDAGE_PORT` | `8000` | 바인딩 포트 |
| `BANDAGE_TRANSPORT` | `streamable-http` | `streamable-http` \| `sse` \| `stdio` |
| `BANDAGE_MOUNT_PATH` | `/mcp` | streamable-http 마운트 경로 |
| `BANDAGE_LOG_LEVEL` | `INFO` | 로그 레벨 |
| `BANDAGE_OASDIFF_BIN` | `oasdiff` | oasdiff 바이너리 경로 (컨테이너는 절대경로 주입) |
| `BANDAGE_BE_SPEC_URL_TEMPLATE` | (BE raw URL) | `{ref}` 치환 BE 스펙 URL |
| `BANDAGE_FE_AREAS_URL` | (FE raw URL) | fe-areas.json URL |
| `BANDAGE_FE_VENDOR_SNAPSHOT_URL` | (FE raw URL) | since_ref 미지정 시 base 스냅샷 |
| `BANDAGE_BE_DEVELOP_REF` | `develop` | 영향평가 head ref |

## 테스트

```bash
pytest -q
```

## 컨테이너 배포

```bash
docker build -t bandage-mcp-server .
docker run -p 8000:8000 bandage-mcp-server
```
