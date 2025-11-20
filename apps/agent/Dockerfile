FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build tooling for numpy/shapely
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy Python sources
COPY packages ./packages
COPY apps/agent ./apps/agent

# Install package dependencies in editable mode
RUN pip install --no-cache-dir -e ./packages/route_planner_mcp \
    && pip install --no-cache-dir -e ./apps/agent

EXPOSE 8000

CMD ["uvicorn", "agent_app.main:app", "--app-dir", "apps/agent/src", "--host", "0.0.0.0", "--port", "8000"]
