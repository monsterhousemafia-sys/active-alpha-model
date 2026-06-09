#!/usr/bin/env python3
"""Full project export to E:\\Projektstand 28.05 (folder + ZIP)."""
from __future__ import annotations

import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST_ROOT = Path(r"E:\Projektstand 28.05")
DEST_DIR = DEST_ROOT / "active_alpha_model"
ZIP_PATH = DEST_ROOT / "active_alpha_model.zip"

EXCLUDE_DIR_NAMES = {".venv", "__pycache__", ".pytest_cache"}
EXCLUDE_PREFIXES = ("model_output", "robustness_results")


def should_skip(rel: Path) -> bool:
    if EXCLUDE_DIR_NAMES.intersection(rel.parts):
        return True
    return any(part.startswith(EXCLUDE_PREFIXES) for part in rel.parts)


def main() -> int:
    if DEST_DIR.exists():
        shutil.rmtree(DEST_DIR, ignore_errors=True)
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if should_skip(rel):
            continue
        target = DEST_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(rel.as_posix())

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(DEST_DIR.rglob("*")):
            if path.is_file():
                rel = path.relative_to(DEST_DIR)
                zf.write(path, arcname=Path("active_alpha_model") / rel)

    (DEST_ROOT / "PROJEKTSTAND.txt").write_text(
        "\n".join(
            [
                "Bezeichnung: Projektstand 28.05",
                f"Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Quelle: {ROOT}",
                f"Zielordner: {DEST_DIR}",
                f"ZIP: {ZIP_PATH}",
                f"Dateien: {len(copied)}",
                "",
                "Enthalten:",
                "- Vollstaendiger Quellcode mit Ordnerstruktur (aa_*, tests, tools, .github, BAT, Docs)",
                "- Marktanalyse.exe (Automatik: venv -> Bibliotheken -> Core-Check -> Backtest)",
                "",
                "Ausgeschlossen (neu erzeugbar):",
                "- .venv",
                "- model_output*",
                "- robustness_results*",
                "- __pycache__",
                "- .pytest_cache",
                "",
                "Verifikation nach Entpacken:",
                "  python -m venv .venv",
                "  .venv\\Scripts\\pip install -r requirements_active_alpha.txt",
                "  .venv\\Scripts\\python.exe tools\\run_quality_gate.py",
                "",
                "Start:",
                "  Doppelklick auf active_alpha_model\\Marktanalyse.exe",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (DEST_ROOT / "DATEILISTE.txt").write_text("\n".join(copied) + "\n", encoding="utf-8")

    folder_bytes = sum(p.stat().st_size for p in DEST_DIR.rglob("*") if p.is_file())
    print(f"OK: {DEST_ROOT}")
    print(f"Dateien: {len(copied)}")
    print(f"Ordner: {folder_bytes} bytes")
    print(f"ZIP: {ZIP_PATH.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
