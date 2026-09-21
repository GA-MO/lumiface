FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY main.py ./
EXPOSE 8020
# The venv binary directly: the machine stops when idle and must answer within seconds of starting.
CMD ["/srv/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020", "--proxy-headers"]
