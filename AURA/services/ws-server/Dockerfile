FROM python:3.12-slim

WORKDIR /workspace
COPY constraints /workspace/constraints
COPY workspace/aura-sdk /workspace/aura-sdk
RUN pip install --no-cache-dir --constraint /workspace/constraints/py312.txt /workspace/aura-sdk[log]

WORKDIR /app
COPY services/ws-server/pyproject.toml .
COPY services/ws-server/src ./src
COPY services/ws-server/tests ./tests
RUN pip install --no-cache-dir --constraint /workspace/constraints/py312.txt -e .

EXPOSE 8000
CMD ["uvicorn", "ws_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
