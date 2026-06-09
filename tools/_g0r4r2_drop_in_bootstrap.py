from pathlib import Path
import hashlib
import sys
import zipfile

EXPECTED_DROP_IN_SHA256 = "65e7cfa79325cc110adae59d700bcab3e7f82040044bf78fbe4a9c92d16b0343"
EXPECTED_INNER_BUNDLE_SHA256 = "fe2a76e49bf6e6d385e0cf5666f2d74317ab68bfed0f473f2b8f1bb6bf98908f"

EXPECTED_MEMBERS = {
    "incoming_external_reviews/g0r4r2/G0R4R2_CODEX_INPUT_BUNDLE.zip",
    "incoming_external_reviews/g0r4r2/G0R4R2_CODEX_INPUT_BUNDLE.zip.sha256",
}

root = Path.cwd().resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(message: str) -> None:
    print("G0R4R2_INPUT_INSTALL_STATUS = BLOCKED")
    print(f"BLOCKER = {message}")
    sys.exit(1)


expected_project_markers = ["control", "docs", "tools"]
missing_markers = [name for name in expected_project_markers if not (root / name).exists()]
if missing_markers:
    fail(
        "SCRIPT_NOT_RUN_FROM_PROJECT_ROOT; missing markers: "
        + ", ".join(missing_markers)
    )

candidates = sorted(root.glob("G0R4R2_CURSOR_DROP_IN_PROJECT_ROOT*.zip"))
if not candidates:
    fail("DROP_IN_ZIP_NOT_FOUND_IN_PROJECT_ROOT")

valid_candidates = []
candidate_results = []
for candidate in candidates:
    actual_hash = sha256_file(candidate)
    candidate_results.append((candidate.name, actual_hash))
    if actual_hash == EXPECTED_DROP_IN_SHA256:
        valid_candidates.append(candidate)

print("Detected ZIP candidates:")
for name, actual_hash in candidate_results:
    print(f"- {name}: {actual_hash}")

if len(valid_candidates) == 0:
    fail("NO_DROP_IN_ZIP_WITH_EXPECTED_SHA256_FOUND")

if len(valid_candidates) > 1:
    print("Multiple byte-identical valid copies found; using the first one.")

drop_in_zip = valid_candidates[0]
print(f"Selected drop-in ZIP: {drop_in_zip}")

with zipfile.ZipFile(drop_in_zip, "r") as z:
    names = z.namelist()

    if len(names) != len(set(names)):
        fail("DROP_IN_ZIP_CONTAINS_DUPLICATE_PATHS")

    if set(names) != EXPECTED_MEMBERS:
        fail(
            "DROP_IN_ZIP_CONTENTS_UNEXPECTED; found: "
            + ", ".join(sorted(names))
        )

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

inner_bundle = root / "incoming_external_reviews/g0r4r2/G0R4R2_CODEX_INPUT_BUNDLE.zip"
inner_sidecar = root / "incoming_external_reviews/g0r4r2/G0R4R2_CODEX_INPUT_BUNDLE.zip.sha256"

actual_inner_hash = sha256_file(inner_bundle)
if actual_inner_hash != EXPECTED_INNER_BUNDLE_SHA256:
    fail(
        "INNER_BUNDLE_SHA256_MISMATCH; "
        f"expected={EXPECTED_INNER_BUNDLE_SHA256}; actual={actual_inner_hash}"
    )

sidecar_text = inner_sidecar.read_text(encoding="utf-8-sig").strip()
sidecar_hash = sidecar_text.split()[0] if sidecar_text else ""
if sidecar_hash != actual_inner_hash:
    fail(
        "INNER_BUNDLE_SIDECAR_MISMATCH; "
        f"sidecar={sidecar_hash}; actual={actual_inner_hash}"
    )

print("")
print("G0R4R2_INPUT_INSTALL_STATUS = PASS")
print(f"PROJECT_ROOT = {root}")
print("INSTALLED_FILES:")
print("- incoming_external_reviews/g0r4r2/G0R4R2_CODEX_INPUT_BUNDLE.zip")
print("- incoming_external_reviews/g0r4r2/G0R4R2_CODEX_INPUT_BUNDLE.zip.sha256")
print(f"INNER_BUNDLE_SHA256 = {actual_inner_hash}")
print("")
print("NEXT_ACTION = Execute the G0R4R2-only autonomous remediation prompt.")
