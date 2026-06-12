# 원격 배포용 이미지
FROM python:3.12-slim

# - PYTHONUNBUFFERED:        stdout/stderr 즉시 flush (컨테이너 로그에 logger 출력 노출)
# - PYTHONDONTWRITEBYTECODE: .pyc 미생성 (이미지 슬림화)
# - PIP_NO_CACHE_DIR:        pip 캐시 미적재
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# oasdiff 바이너리 설치 (영향평가 Tool 의 diff 엔진).
# 버전 핀 + sha256 검증 + arch 자동 감지(amd64/arm64). ca-certificates 는 런타임
# httpx HTTPS(raw GitHub fetch)에 필요하므로 유지하고, 빌드용 curl 만 제거한다.
ARG OASDIFF_VERSION=1.18.6
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) sha="80e6ad3a70239a96f5452622aabf9eab4f7b260eebd1af27b512eca586d89112" ;; \
      arm64) sha="84507a63613b8bbc518de78ff64fe4a8a7b8abfd383b03500512c9e36b67193b" ;; \
      *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    url="https://github.com/oasdiff/oasdiff/releases/download/v${OASDIFF_VERSION}/oasdiff_${OASDIFF_VERSION}_linux_${arch}.tar.gz"; \
    curl -fsSL -o /tmp/oasdiff.tar.gz "$url"; \
    echo "${sha}  /tmp/oasdiff.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/oasdiff.tar.gz -C /usr/local/bin oasdiff; \
    rm /tmp/oasdiff.tar.gz; \
    apt-get purge -y curl; apt-get autoremove -y; rm -rf /var/lib/apt/lists/*; \
    oasdiff --version

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
    BANDAGE_TRANSPORT=streamable-http \
    BANDAGE_OASDIFF_BIN=/usr/local/bin/oasdiff

CMD ["bandage-mcp-server"]
