#!/usr/bin/env bash
# GPT-4o keyless — Berater-Tiers lokal via Ollama, kein OpenAI-Key.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== GPT-4o keyless (Ollama) ==="
python3 - <<'PY'
import json
from pathlib import Path

root = Path(".")
cfg_path = root / "control" / "r3_external_advisors.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
oai = cfg.setdefault("openai", {})
oai["keyless_mode"] = True
oai.setdefault("keyless_label_de", "GPT-4o lokal via Ollama — kein OpenAI-Key")
oai.setdefault(
    "local_tier_models",
    {
        "fast": "qwen2.5:14b",
        "plan": "qwen2.5-coder:32b",
        "deep": "qwen2.5-coder:32b",
        "trading": "qwen2.5:14b",
    },
)
cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("keyless_mode: true")
PY

python3 tools/ai_kernel.py llm-health 2>/dev/null | head -8 || true
echo ""
echo "Bereit: /tipp <frage> · /kombi <frage> — GPT-4o-Tiers lokal, kein Key."
