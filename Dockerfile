FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY pyproject.toml README.md ./
COPY amp/ ./amp/

RUN pip install --no-cache-dir -e ".[server]"

# 포트 노출
EXPOSE 3010

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3010/health || exit 1

# 기본: MCP 서버 실행
CMD ["python", "-m", "uvicorn", "amp.mcp_server:app", "--host", "0.0.0.0", "--port", "3010"]
