# 원격 배포용 이미지
FROM python:3.12-slim

WORKDIR /app

# 의존성 설치 (소스 메타데이터 먼저 복사해 캐시 활용)
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

# streamable-http 기본 포트
EXPOSE 8000

ENV BANDAGE_HOST=0.0.0.0 \
    BANDAGE_PORT=8000 \
    BANDAGE_TRANSPORT=streamable-http

CMD ["bandage-mcp-server"]
