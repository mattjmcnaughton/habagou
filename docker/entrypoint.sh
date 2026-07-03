#!/usr/bin/env sh
set -eu

run_with_retry() {
  label="$1"
  shift
  attempt=1
  max_attempts="${HABAGOU_BOOTSTRAP_ATTEMPTS:-30}"
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

run_with_retry "database migration" alembic upgrade head
python scripts/import_stroke_data.py
python scripts/seed.py

exec "$@"
