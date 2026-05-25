FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash git ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/AURA

COPY constraints/py312.txt /tmp/py312.txt

RUN pip install --no-cache-dir --constraint /tmp/py312.txt \
    pip==24.2 \
    setuptools==75.1.0 \
    wheel==0.44.0 \
    pytest==8.3.2 \
    pytest-asyncio==0.24.0 \
    fastapi==0.111.1 \
    "uvicorn[standard]==0.30.6" \
    httpx==0.27.0 \
    "python-jose[cryptography]==3.3.0" \
    "passlib[bcrypt]==1.7.4" \
    pydantic==2.8.2 \
    pydantic-settings==2.4.0 \
    psutil==6.0.0 \
    aiosqlite==0.20.0 \
    structlog==24.4.0

CMD ["bash"]
