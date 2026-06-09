"""Install G0R4R3 transport bundle from project-root drop-in ZIP."""
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

EXPECTED_DROP_IN_SHA256 = "02b1d97f845d5d666ef852bf3c4cd725bfe54efb05f73cc47663e772c3b879c7"
EXPECTED_INNER_BUNDLE_SHA256 = "b974af8cd9bbaa22a8f018ab8f67ecdcb00b3f2d4a18345aca7ddc8d43632d85"

EXPECTED_MEMBERS = {
    "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip",
    "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip.sha256",
}

root = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(message: str) -> None:
    print("G0R4R3_INPUT_INSTALL_STATUS = BLOCKED")
    print(f"BLOCKER = {message}")
    sys.exit(1)


def main() -> int:
    for name in ("control", "docs", "tools"):
        if not (root / name).is_dir():
            fail(f"SCRIPT_NOT_RUN_FROM_PROJECT_ROOT; missing marker: {name}")

    candidates = sorted(root.glob("G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT*.zip"))
    if not candidates:
        inner = root / "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip"
        sidecar = root / "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip.sha256"
        if inner.is_file() and sidecar.is_file():
            actual = sha256_file(inner)
            if actual != EXPECTED_INNER_BUNDLE_SHA256:
                fail(f"INNER_BUNDLE_SHA256_MISMATCH; actual={actual}")
            sidecar_hash = sidecar.read_text(encoding="utf-8-sig").strip().split()[0]
            if sidecar_hash != actual:
                fail("INNER_BUNDLE_SIDECAR_MISMATCH")
            print("G0R4R3_INPUT_INSTALL_STATUS = PASS")
            print("INSTALLED_FILES:")
            print("- incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip")
            print("- incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip.sha256")
            print(f"INNER_BUNDLE_SHA256 = {actual}")
            return 0
        fail("DROP_IN_ZIP_NOT_FOUND_IN_PROJECT_ROOT")

    valid = [c for c in candidates if sha256_file(c) == EXPECTED_DROP_IN_SHA256]
    print("Detected ZIP candidates:")
    for c in candidates:
        print(f"- {c.name}: {sha256_file(c)}")
    if not valid:
        fail("NO_DROP_IN_ZIP_WITH_EXPECTED_SHA256_FOUND")
    drop_in_zip = valid[0]
    print(f"Selected drop-in ZIP: {drop_in_zip}")

    with zipfile.ZipFile(drop_in_zip, "r") as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            fail("DROP_IN_ZIP_CONTAINS_DUPLICATE_PATHS")
        if set(names) != EXPECTED_MEMBERS:
            fail("DROP_IN_ZIP_CONTENTS_UNEXPECTED; found: " + ", ".join(sorted(names)))
        for name in names:
            target = (root / name).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                fail(f"UNSAFE_ZIP_PATH: {name}")
        for name in sorted(EXPECTED_MEMBERS):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
            print(f"Written: {target.relative_to(root)}")

    inner = root / "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip"
    sidecar = root / "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip.sha256"
    actual = sha256_file(inner)
    if actual != EXPECTED_INNER_BUNDLE_SHA256:
        fail(f"INNER_BUNDLE_SHA256_MISMATCH; expected={EXPECTED_INNER_BUNDLE_SHA256}; actual={actual}")
    sidecar_hash = sidecar.read_text(encoding="utf-8-sig").strip().split()[0]
    if sidecar_hash != actual:
        fail(f"INNER_BUNDLE_SIDECAR_MISMATCH; sidecar={sidecar_hash}; actual={actual}")

    print("")
    print("G0R4R3_INPUT_INSTALL_STATUS = PASS")
    print(f"PROJECT_ROOT = {root}")
    print("INSTALLED_FILES:")
    print("- incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip")
    print("- incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip.sha256")
    print(f"INNER_BUNDLE_SHA256 = {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
