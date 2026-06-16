#!/usr/bin/env bash
# Projekt absichern — Safety, Secrets, Leak-Preflight.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/.venv/bin/python3" "$ROOT/tools/project_security_lockdown.py"
