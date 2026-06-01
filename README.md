# bandage-mcp-server

MCP Server for AI Project Managing.

원격 배포를 전제로 한 Python 기반 MCP 서버의 기본 골격입니다.
현재는 동작 확인용 `ping` Tool만 등록되어 있으며, 실제 프로젝트 관리 Tool은 이후 단계에서 추가합니다.

## 구조

```
bandage-mcp-server/
├── pyproject.toml              # 패키지/의존성 정의 (uv·pip 호환)
├── Dockerfile                  # 원격 배포용 이미지
├── src/bandage_mcp_server/
│   ├── config.py               # 환경변수 기반 설정 (BANDAGE_ prefix)
│   ├── server.py               # FastMCP 인스턴스 및 Tool 등록
│   └── __main__.py             # 실행 진입점
└── tests/
    └── test_server.py          # 스모크 테스트
```

## 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
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

## 테스트

```bash
pytest -q
```

## 컨테이너 배포

```bash
docker build -t bandage-mcp-server .
docker run -p 8000:8000 bandage-mcp-server
```
