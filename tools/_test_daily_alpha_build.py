import sys
from pathlib import Path
import pandas as pd

ROOT = Path(r"E:\active_alpha_model")
sys.path.insert(0, str(ROOT))

ok = True

# --- Test 1: _momentum_score routing ---
from aa_portfolio import _momentum_score
snap = pd.DataFrame({
    "ticker": ["A", "B"],
    "mom_1": [0.03, -0.01],
    "mom_63_21": [0.5, 0.5],
    "mom_126_21": [0.9, 0.9],
    "mom_252_21": [0.7, 0.7],
})
s1 = _momentum_score(snap, "mom_1_top12")
if list(s1) != [0.03, -0.01]:
    print("FAIL mom_1_top12 ->", list(s1)); ok = False
else:
    print("OK   mom_1_top12 uses mom_1 column:", list(s1))

s126 = _momentum_score(snap, "mom_126_top12")
if list(s126) != [0.9, 0.9]:
    print("FAIL mom_126 wrongly routed ->", list(s126)); ok = False
else:
    print("OK   mom_126 still uses mom_126_21 (no clash with mom_1):", list(s126))

s252 = _momentum_score(snap, "mom_252_top12")
if list(s252) != [0.7, 0.7]:
    print("FAIL mom_252 wrongly routed ->", list(s252)); ok = False
else:
    print("OK   mom_252 unaffected:", list(s252))

# --- Test 2: _build_cmd for DAILY_ALPHA_H1 ---
import tools.run_validation_matrix as rvm

variant = next(v for v in rvm.MATRIX if v["key"] == "DAILY_ALPHA_H1")
cmd = rvm._build_cmd(variant, ROOT / "validation_runs" / "_probe_daily", force_predictions=True)
cs = " ".join(cmd)

def check(cond, msg):
    global ok
    print(("OK  " if cond else "FAIL") + " " + msg)
    if not cond:
        ok = False

check("--horizon 1" in cs, "horizon overridden to 1")
check("--rebalance-every 1" in cs, "rebalance-every overridden to 1")
check("--no-naive-momentum-baseline" not in cs, "naive baseline NOT suppressed (benchmark needs it)")
check("--naive-detailed-variants mom_1_top12" in cs, "mom_1_top12 detailed benchmark requested")
check("--force-rebuild-features" in cs, "features force-rebuilt (horizon changed)")
check("--alpha-model-mode ensemble" in cs, "ensemble ML drives daily alpha")

# Sanity: an UNRELATED existing variant must be untouched (no daily overrides)
r3 = next(v for v in rvm.MATRIX if v["key"] == "R3_w075_q065_noexit")
cr3 = " ".join(rvm._build_cmd(r3, ROOT / "validation_runs" / "_probe_r3", force_predictions=True))
check("--horizon 10" in cr3 and "--rebalance-every 5" in cr3, "R3 still horizon=10 rebalance=5 (untouched)")
check("--no-naive-momentum-baseline" in cr3, "R3 still suppresses naive baseline (untouched)")

print("\nRESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
sys.exit(0 if ok else 1)
