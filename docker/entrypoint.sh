#!/usr/bin/env sh
set -eu

run_with_retry() {
  label="$1"
  shift
  attempt=1
  max_attempts="${HABAGOU_BOOTSTRAP_ATTEMPTS:-10}"
  delay_seconds="${HABAGOU_BOOTSTRAP_RETRY_SECONDS:-2}"

  while ! "$@"; do
    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "$label failed after $attempt attempts" >&2
      return 1
    fi
    echo "$label failed; retrying in ${delay_seconds}s ($attempt/$max_attempts)" >&2
    attempt=$((attempt + 1))
    sleep "$delay_seconds"
  done
}

# Fly release machines set RELEASE_COMMAND=1. Local/compose default to
# HABAGOU_RUN_BOOTSTRAP=1. Fly app machines set HABAGOU_RUN_BOOTSTRAP=0.
if [ "${RELEASE_COMMAND:-}" = "1" ] || [ "${HABAGOU_RUN_BOOTSTRAP:-1}" = "1" ]; then
  run_with_retry "database migration" alembic upgrade head
  python scripts/import_stroke_data.py
  python scripts/seed.py
else
  echo "skipping bootstrap (HABAGOU_RUN_BOOTSTRAP=${HABAGOU_RUN_BOOTSTRAP:-} RELEASE_COMMAND=${RELEASE_COMMAND:-})"
fi

exec "$@"
