FROM python:3.12-slim

WORKDIR /workspace
COPY workspace/aura-sdk /workspace/aura-sdk
RUN pip install --no-cache-dir /workspace/aura-sdk[log]

WORKDIR /app
COPY services/llm-gateway/pyproject.toml .
COPY services/llm-gateway/src ./src
COPY services/llm-gateway/tests ./tests
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "llm_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
