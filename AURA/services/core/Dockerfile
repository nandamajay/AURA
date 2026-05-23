FROM python:3.12-slim

WORKDIR /workspace
COPY constraints /workspace/constraints
COPY workspace/aura-sdk /workspace/aura-sdk
RUN pip install --no-cache-dir --constraint /workspace/constraints/py312.txt /workspace/aura-sdk[db,log]
COPY agents /workspace/agents
RUN pip install --no-cache-dir --constraint /workspace/constraints/py312.txt -e /workspace/agents

WORKDIR /app
COPY services/core/pyproject.toml .
COPY services/core/src ./src
COPY services/core/tests ./tests
COPY governance/src ./governance
COPY knowledge/src ./knowledge
COPY knowledge/schema /workspace/knowledge/schema
COPY simulation/src ./simulation
COPY validation/src ./validation
RUN pip install --no-cache-dir --constraint /workspace/constraints/py312.txt -e .

EXPOSE 8000
CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8000"]
