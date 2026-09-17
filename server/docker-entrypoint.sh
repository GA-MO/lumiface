#!/bin/sh
set -e
# buffalo_l (~300MB) is fetched on first start into the mounted models volume
if [ ! -f /root/.insightface/models/buffalo_l/w600k_r50.onnx ]; then
  uv run python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']).prepare(ctx_id=0)"
fi
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-1}
