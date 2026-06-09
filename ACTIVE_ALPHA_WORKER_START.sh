#!/usr/bin/env bash
# Worker-Bundle: beim ersten Öffnen/Kopieren — Rechenleistung an König melden.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec bash "$ROOT/tools/bootstrap_preview_federation.sh" "$@"
