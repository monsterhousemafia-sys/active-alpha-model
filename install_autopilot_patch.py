#!/usr/bin/env python3
from __future__ import annotations
import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
PAYLOAD = PACKAGE / '_autopilot_patch_payload'

def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def main() -> int:
    parser = argparse.ArgumentParser(description='Install Active Alpha Autopilot bootstrap patch safely.')
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    parser.add_argument('--replace-with-backup', action='store_true')
    args = parser.parse_args()
    root = args.project_root.resolve()
    if not any((root / f).exists() for f in ['active_alpha_model.py', 'aa_backtest.py', 'paper_trading_engine.py']):
        print('[ERROR] Active Alpha project markers not found. Run installer in the project root.')
        return 2
    if not PAYLOAD.exists():
        print('[ERROR] Missing payload:', PAYLOAD)
        return 2
    backup = root / 'autopilot_patch_backup' / stamp()
    installed, candidates, replaced = [], [], []
    for src in sorted(PAYLOAD.rglob('*')):
        if not src.is_file():
            continue
        rel = src.relative_to(PAYLOAD)
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and not args.replace_with_backup:
            candidate = dst.with_name(dst.name + '.autopilot_patch_candidate')
            shutil.copy2(src, candidate)
            candidates.append(str(rel))
        else:
            if dst.exists():
                b = backup / rel
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, b)
                replaced.append(str(rel))
            shutil.copy2(src, dst)
            installed.append(str(rel))
    print('[OK] Patch processed.')
    print('Installed:', len(installed))
    print('Replaced with backup:', len(replaced))
    print('Conflict candidates:', len(candidates))
    for rel in candidates:
        print('  [REVIEW]', rel + '.autopilot_patch_candidate')
    if replaced:
        print('Backup:', backup)
    print('Next: run_autopilot_control.bat init')
    print('Then: run_autopilot_control.bat self-test')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
