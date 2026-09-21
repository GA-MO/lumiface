#!/bin/sh
set -e
# On a host with one persistent disk (Fly), INSIGHTFACE_HOME puts the downloaded models on it next to the database.
if [ -n "$INSIGHTFACE_HOME" ]; then
  mkdir -p "$INSIGHTFACE_HOME/models"
  rm -rf /root/.insightface
  ln -s "$INSIGHTFACE_HOME" /root/.insightface
fi
# buffalo_l (~300MB) is fetched on first start into the mounted models volume
if [ ! -f /root/.insightface/models/buffalo_l/w600k_r50.onnx ]; then
  uv run --no-sync python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']).prepare(ctx_id=0)"
fi
exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-1}
