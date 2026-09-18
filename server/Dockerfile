FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY weights/*.onnx ./weights/
COPY weights/cvpr2024/resnet50.onnx ./weights/cvpr2024/
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh
ENV DATABASE_URL=sqlite:////srv/data/lumiface.db WEIGHTS_DIR=/srv/weights FRAMES_DIR=/srv/data/frames
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
