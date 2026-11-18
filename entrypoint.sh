#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/data

if [[ -n "${LITESTREAM_RESTORE_URL:-}" ]]; then
  litestream restore -config /app/litestream.yml -if-db-not-exists -if-replica-exists /app/data/engine.db || true
fi

litestream replicate -config /app/litestream.yml /app/data/engine.db &
REPLICATOR_PID=$!

cleanup() {
  kill -TERM "$REPLICATOR_PID" 2>/dev/null || true
  wait "$REPLICATOR_PID" 2>/dev/null || true
}
trap cleanup EXIT TERM INT

python -m huey.consumer.memory.task_queue.huey &
HUEY_PID=$!

python -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-7860}" --workers 1 &
UVICORN_PID=$!

cleanup_all() {
  kill -TERM "$HUEY_PID" "$UVICORN_PID" 2>/dev/null || true
  wait "$HUEY_PID" 2>/dev/null || true
  wait "$UVICORN_PID" 2>/dev/null || true
  cleanup
}
trap cleanup_all EXIT TERM INT
wait -n "$HUEY_PID" "$UVICORN_PID"
