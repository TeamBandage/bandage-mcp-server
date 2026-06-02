# 원격 배포용 이미지
FROM python:3.12-slim

# - PYTHONUNBUFFERED:        stdout/stderr 즉시 flush (컨테이너 로그에 logger 출력 노출)
# - PYTHONDONTWRITEBYTECODE: .pyc 미생성 (이미지 슬림화)
# - PIP_NO_CACHE_DIR:        pip 캐시 미적재
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성 설치 (소스 메타데이터 먼저 복사해 캐시 활용)
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install .

# 비루트 유저로 실행 (권한 최소화)
RUN useradd --create-home --uid 10001 appuser
USER appuser

# streamable-http 기본 포트 (외부 노출은 nginx 가 담당, 컨테이너 간 통신용)
EXPOSE 8000

ENV BANDAGE_HOST=0.0.0.0 \
    BANDAGE_PORT=8000 \
    BANDAGE_TRANSPORT=streamable-http

CMD ["bandage-mcp-server"]
