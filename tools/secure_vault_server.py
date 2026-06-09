#!/usr/bin/env python3
"""Lokaler Schlüssel-Tresor — bindet nur 127.0.0.1, Port 17891."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def main() -> int:
    p = argparse.ArgumentParser(description="Active Alpha — lokaler Schlüssel-Tresor")
    p.add_argument("--port", type=int, default=17891)
    p.add_argument("--daemon", action="store_true")
    args = p.parse_args()
    root = _root()
    sys.path.insert(0, str(root))

    from analytics.secure_credential_portal import run_vault_server
    from analytics.vault_airgap import verify_airgap

    if args.daemon:
        pid = os.fork()
        if pid > 0:
            time.sleep(0.3)
            print(f"[vault-portal] local=http://127.0.0.1:{args.port}/vault pid={pid}", flush=True)
            return 0
        os.setsid()

    server = run_vault_server(root, port=args.port, bind="127.0.0.1")
    verify_airgap(root, port=args.port)
    print(f"[vault-portal] airgap=127.0.0.1:{args.port} only", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
