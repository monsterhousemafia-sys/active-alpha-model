"""Universal Lite Worker OS — Launch, Export, Auto-Install."""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/ulwo_os.json")
_EXPORT_REL = Path("evidence/exports/Universal_Lite_Worker_OS.zip")
MANIFEST_REL = Path("evidence/ulwo_launch_latest.json")
_MANIFEST_REL = MANIFEST_REL
_WORKER_PY = Path("tools/universal_preview_worker.py")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_ulwo_config(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CONFIG_REL)
    return doc or {"product_name": "Universal Lite Worker OS", "short_name": "ULWO"}


def _hub_base(root: Path) -> str:
    from tools.preview_hub import ensure_hub_running

    from analytics.preview_federation import hub_public_base_url

    port = int(ensure_hub_running(Path(root), restart=False))
    return hub_public_base_url(root, port=port).rstrip("/")


def _staging_dir(root: Path) -> Path:
    cfg = load_ulwo_config(root)
    return Path(root) / "evidence" / "exports" / str(cfg.get("bundle_dir_name") or "Universal_Lite_Worker_OS")


def build_ulwo_bundle(root: Path) -> Dict[str, Any]:
    """ZIP für Download — Win/Mac/Linux, Auto-Start-Skripte."""
    root = Path(root).resolve()
    cfg = load_ulwo_config(root)
    from analytics.preview_federation import prepare_worker_bundle_config

    join_cfg = prepare_worker_bundle_config(root)
    hub = str(join_cfg.get("hub_join_url") or "").rstrip("/")
    dest = _staging_dir(root)
    if dest.is_dir():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    (dest / "preview_worker_join.json").write_text(
        json.dumps({**join_cfg, "product": cfg.get("product_name"), "role": "ulwo_worker"}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(root / _WORKER_PY, dest / "worker.py")

    product = str(cfg.get("product_name") or "Universal Lite Worker OS")
    short = str(cfg.get("short_name") or "ULWO")

    (dest / "Windows_START.bat").write_text(
        f"""@echo off
cd /d "%~dp0"
title {product}
echo {product} — Verbinde mit R3 ...
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py -3
if not defined PY (
  echo Python 3 fehlt: https://www.python.org/downloads/
  pause
  exit / 1
)
%PY% worker.py
if errorlevel 1 pause
""",
        encoding="utf-8",
    )

    (dest / "Mac_START.command").write_text(
        f"""#!/bin/bash
cd "$(dirname "$0")"
echo "{product} — Verbinde mit R3 ..."
exec python3 worker.py
""",
        encoding="utf-8",
    )
    os.chmod(dest / "Mac_START.command", 0o755)

    (dest / "Linux_START.sh").write_text(
        f"""#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
echo "{product} — Verbinde mit R3 ..."
exec python3 worker.py
""",
        encoding="utf-8",
    )
    os.chmod(dest / "Linux_START.sh", 0o755)

    (dest / "Linux_INSTALL.sh").write_text(
        f"""#!/bin/bash
# {product} — lokale Installation + Start
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL="${{ULWO_HOME:-$HOME/.local/share/ulwo-worker}}"
mkdir -p "$INSTALL"
rsync -a "$DIR/" "$INSTALL/"
chmod +x "$INSTALL/Linux_START.sh" "$INSTALL/worker.py" 2>/dev/null || true
cat > "$HOME/.local/bin/ulwo" <<EOF
#!/usr/bin/env bash
exec bash "$INSTALL/Linux_START.sh"
EOF
chmod +x "$HOME/.local/bin/ulwo" 2>/dev/null || true
echo "[OK] {product} installiert unter $INSTALL"
echo "[OK] Start: ulwo  oder  $INSTALL/Linux_START.sh"
exec bash "$INSTALL/Linux_START.sh"
""",
        encoding="utf-8",
    )
    os.chmod(dest / "Linux_INSTALL.sh", 0o755)

    (dest / "README.md").write_text(
        f"""# {product}

{cfg.get('tagline_de') or ''}

## Schnellstart

| System | Aktion |
|--------|--------|
| Windows | `Windows_START.bat` |
| macOS | `Mac_START.command` |
| Linux | `./Linux_INSTALL.sh` (installiert + startet) |

## Ein-Zeilen-Install (Linux)

```
curl -fsSL {hub}/api/ulwo/install.sh | ULWO_HUB={hub} bash
```

## R3 König

{hub}/

Kein Broker. Kein Geld. Nur CPU.
""",
        encoding="utf-8",
    )

    zip_path = root / _EXPORT_REL
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.is_file():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in dest.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(dest.parent))

    doc = {
        "ok": True,
        "schema_version": 1,
        "built_at_utc": _utc_now(),
        "product_name": product,
        "short_name": short,
        "hub_join_url": hub,
        "bundle_dir": str(dest),
        "zip_path": str(zip_path),
        "zip_bytes": zip_path.stat().st_size if zip_path.is_file() else 0,
        "download_url": f"{hub}/api/ulwo/bundle.zip",
        "install_sh_url": f"{hub}/api/ulwo/install.sh",
        "install_one_liner": f"curl -fsSL {hub}/api/ulwo/install.sh | ULWO_HUB={hub} bash",
        "headline_de": f"{product} — Launch-Paket bereit",
    }
    atomic_write_json(root / _MANIFEST_REL, doc)
    return doc


def build_install_script(root: Path, *, hub: Optional[str] = None) -> str:
    cfg = load_ulwo_config(root)
    base = (hub or _hub_base(root)).rstrip("/")
    product = str(cfg.get("product_name") or "Universal Lite Worker OS")
    return f"""#!/usr/bin/env bash
# {product} — Auto-Installer
set -euo pipefail
HUB="${{ULWO_HUB:-{base}}}"
INSTALL="${{ULWO_HOME:-$HOME/.local/share/ulwo-worker}}"
TMP="${{TMPDIR:-/tmp}}/ulwo-bundle.zip"
echo "=== {product} ==="
echo "Hub: $HUB"
command -v python3 >/dev/null || {{ echo "Python 3 fehlt"; exit 1; }}
mkdir -p "$INSTALL" "$HOME/.local/bin"
curl -fsSL "$HUB/api/ulwo/bundle.zip" -o "$TMP"
rm -rf "$INSTALL"/*
unzip -oq "$TMP" -d "$INSTALL"
BUNDLE=$(find "$INSTALL" -maxdepth 1 -type d -name 'Universal_Lite_Worker_OS' | head -1)
[[ -n "$BUNDLE" ]] || BUNDLE="$INSTALL"
chmod +x "$BUNDLE/Linux_INSTALL.sh" "$BUNDLE/Linux_START.sh" 2>/dev/null || true
bash "$BUNDLE/Linux_INSTALL.sh"
"""


def render_download_page(root: Path, *, hub: Optional[str] = None) -> bytes:
    root = Path(root)
    cfg = load_ulwo_config(root)
    doc = _load_json(root / _MANIFEST_REL) or build_ulwo_bundle(root)
    base = (hub or str(doc.get("hub_join_url") or _hub_base(root))).rstrip("/")
    product = str(cfg.get("product_name") or "Universal Lite Worker OS")
    one_liner = str(doc.get("install_one_liner") or f"curl -fsSL {base}/api/ulwo/install.sh | ULWO_HUB={base} bash")
    page = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_esc(product)} — Download</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 24px;background:#0a0a0f;color:#f4f4f8}}
.card{{background:rgba(22,22,32,.9);border:1px solid rgba(255,255,255,.08);border-radius:20px;padding:24px;margin:16px 0}}
h1{{font-size:clamp(1.6rem,4vw,2.2rem)}}
.sub{{color:#9b9bb0;line-height:1.5}}
pre{{background:#161620;padding:14px;border-radius:12px;overflow:auto;font-size:13px}}
.btn{{display:inline-block;margin:8px 8px 0 0;padding:12px 18px;background:linear-gradient(135deg,#5e5ce6,#30d5c8);color:#fff;text-decoration:none;border-radius:12px;font-weight:700}}
</style></head><body>
<h1>{_esc(product)}</h1>
<p class="sub">{_esc(cfg.get('description_de'))}</p>
<div class="card">
  <h2>Linux — Ein Befehl</h2>
  <pre>{_esc(one_liner)}</pre>
  <a class="btn" href="{_esc(base)}/api/ulwo/install.sh">install.sh</a>
  <a class="btn" href="{_esc(base)}/api/ulwo/bundle.zip">ZIP Download</a>
</div>
<div class="card">
  <h2>Windows / macOS</h2>
  <p class="sub">ZIP entpacken → <code>Windows_START.bat</code> oder <code>Mac_START.command</code></p>
  <a class="btn" href="{_esc(base)}/api/ulwo/bundle.zip">ZIP herunterladen</a>
</div>
<div class="card">
  <h2>R3 König</h2>
  <a class="btn" href="{_esc(base)}/">Cockpit</a>
  <a class="btn" href="{_esc(base)}/join">Mitmachen</a>
</div>
<p class="sub">Linux-Kernel auf Worker-PC bleibt unverändert — ULWO ist nur die Worker-Schicht.</p>
</body></html>"""
    return page.encode("utf-8")


def launch_ulwo(root: Path) -> Dict[str, Any]:
    """Launch abschließen: Bundle bauen, Hub, Manifest."""
    root = Path(root).resolve()
    try:
        from analytics.r3_os_supremacy import install_r3_native

        native = install_r3_native(root)
    except Exception as exc:
        native = {"ok": False, "error_de": str(exc)[:200]}
    bundle = build_ulwo_bundle(root)
    try:
        from analytics.remote_hub_access import resolve_public_url

        public = str(resolve_public_url(root, "") or "").strip().rstrip("/")
    except Exception:
        public = ""
    if public:
        bundle["public_download_url"] = f"{public}/download"
        bundle["public_install_sh"] = f"{public}/api/ulwo/install.sh"
    bundle["r3_native"] = native
    bundle["launch_ready"] = bool(bundle.get("ok") and native.get("ok", True))
    atomic_write_json(root / _MANIFEST_REL, bundle)
    return bundle
