FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY data ./data

# Install dependencies only. Keep the project on PYTHONPATH so StubPolicyClient
# still finds data/policies.json at Path(__file__).parents[2] / "data".
RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "claims.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]
