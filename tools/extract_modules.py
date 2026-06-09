from pathlib import Path

root = Path(__file__).resolve().parents[1]
lines = (root / "active_alpha_model.py").read_text(encoding="utf-8").splitlines()
COMMON = "from __future__ import annotations\n\n"
RANGES = {
    "aa_constants.py": [(263, 469)],
    "aa_config.py": [(471, 1060), (4605, 4617)],
    "aa_universe.py": [(1097, 1763)],
    "aa_features.py": [(1765, 2424)],
    "aa_models.py": [(2426, 2531)],
    "aa_parallel.py": [(2533, 2763)],
    "aa_backtest_ml.py": [(2775, 2958)],
    "aa_portfolio.py": [(2960, 4802)],
    "aa_reporting.py": [(4804, 5438), (6327, 6469)],
    "aa_execution.py": [(5440, 5854)],
    "aa_backtest.py": [(4912, 5050), (5856, 6326)],
    "aa_runtime.py": [(6471, 6996)],
}
backup = root / "active_alpha_model_monolith_backup.py"
if not backup.exists():
    backup.write_text("\n".join(lines) + "\n", encoding="utf-8")
for name, ranges in RANGES.items():
    chunks: list[str] = []
    for start, end in ranges:
        chunks.extend(lines[start - 1 : end])
    (root / name).write_text(COMMON + "\n".join(chunks) + "\n", encoding="utf-8")
    print("wrote", name, sum(end - start + 1 for start, end in ranges), "lines")
