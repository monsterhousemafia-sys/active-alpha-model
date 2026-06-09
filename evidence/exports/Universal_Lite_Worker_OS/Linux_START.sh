#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Universal Lite Worker OS — Verbinde mit R3 ..."
exec python3 worker.py
