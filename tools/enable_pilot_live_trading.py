#!/usr/bin/env python3
"""Enable manual confirmed live trading for 500-EUR pilot (no auto-execute)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.confirmed_live.pilot_live_trading_policy import (
    activation_phrase,
    disable_pilot_live_trading,
    enable_pilot_live_trading,
    is_pilot_live_trading_enabled,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--disable", action="store_true")
    p.add_argument("--risk-ack", action="store_true", help="Required for --enable")
    p.add_argument("--phrase", default="", help="Activation phrase (see --show-phrase)")
    p.add_argument("--show-phrase", action="store_true")
    args = p.parse_args()

    if args.show_phrase:
        print(activation_phrase())
        return 0

    if args.disable:
        res = disable_pilot_live_trading(ROOT)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if not args.risk_ack:
        print("ERROR: --risk-ack required to enable pilot live trading")
        print("Phrase:", activation_phrase())
        return 1

    res = enable_pilot_live_trading(ROOT, phrase=args.phrase, risk_ack=True)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if res.get("ok"):
        print("\nNaechste Schritte in der App:")
        print("1. Trading 212 - Execution-Profil (Order-Key) speichern")
        print("2. Live-Pilot einrichten - Baseline/Scope")
        print("3. Risiko - Core-Live aktivieren")
        print("4. Order Review - Entwurf - Live senden")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
