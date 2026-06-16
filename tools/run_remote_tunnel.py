#!/usr/bin/env python3
"""Quick Cloudflare Tunnel — systemd aa-tunnel (fail-closed ohne Token)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from analytics.remote_hub_access import start_cloudflared_quick_tunnel

    doc = start_cloudflared_quick_tunnel(ROOT)
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0 if doc.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
