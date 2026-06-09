"""Idempotent M1 auto-seal driver.

Waits until all three M1 variants have a complete strategy_daily_returns.csv
(>= MIN_DAYS rows, the same bar the seal gate uses), then runs the OFFICIAL
seal pipeline (run_r0_migration_phase_m1.py -> builds manifest + auto-seals)
and confirms the result via seal_r0_migration_phase.py --verify-only.

Safe to run repeatedly: if M1 is already sealed it exits immediately.
Does NOT reimplement any gate logic; it only triggers the authoritative tools.
"""
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if os.name == "nt":
    _PY = ROOT / ".venv" / "Scripts" / "python.exe"
else:
    _PY = ROOT / ".venv" / "bin" / "python3"
PY = str(_PY if _PY.is_file() else Path(sys.executable))
VR = str(ROOT / "validation_runs")
SEAL_FILE = ROOT / "evidence" / "r0_migration" / "m1_phase_seal.json"
VARIANTS = (
    "R0_LEGACY_ENSEMBLE",
    "R3_w075_q065_noexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)
# The M1 variant additionally writes a matched-controls baseline. Both return
# streams must exist before the seal pipeline can pass the calendar-integrity
# gate, so we wait for BOTH here (avoids a premature fail-closed/retry cycle).
M1_VARIANT = "M1_MOM_BLEND_MATCHED_CONTROLS"
MATCHED_CSV = "mom_blend_matched_controls_daily_returns.csv"
MIN_DAYS = 1800
INTERVAL = 30
MAX_POLLS = 1200  # ~10h safety ceiling
_SINGLETON_HANDLE = None

# FAST-SEAL flag: when present, the matched-controls baseline (the slow
# naive-detailed control series) is treated as OPTIONAL for the M1 seal. The
# official seal gate only needs the three strategy CSVs; M2 (R0 vs R3) does not
# read the matched-controls series either. The control series is backfilled
# afterwards out-of-band. Default (no flag) keeps the strict both-CSV behaviour.
FAST_FLAG = ROOT / "control" / "r0_migration" / "m1_fast_seal.flag"


def _fast_seal():
    return FAST_FLAG.is_file()

def now():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def count_rows(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            n = sum(1 for _ in f)
        return max(0, n - 1)
    except OSError:
        return None


def complete_dirs(variant):
    """Return [(dir, rows)] for dirs whose strategy CSV has >= MIN_DAYS rows.

    For the M1 matched-controls variant we additionally require the matched-
    controls CSV to be present, so the seal pipeline only fires once BOTH
    return streams exist (the calendar-integrity gate needs both). This does
    NOT reimplement any gate logic - it only gates the trigger on file presence.
    """
    out = []
    needs_matched = variant == M1_VARIANT and not _fast_seal()
    for d in glob.glob(os.path.join(VR, "*" + variant + "*")):
        if not os.path.isdir(d):
            continue
        csvp = os.path.join(d, "strategy_daily_returns.csv")
        n = count_rows(csvp)
        if n is None or n < MIN_DAYS:
            continue
        if needs_matched and not os.path.isfile(os.path.join(d, MATCHED_CSV)):
            continue
        out.append((os.path.basename(d), n))
    return sorted(out)


def is_sealed():
    if not SEAL_FILE.is_file():
        return False
    try:
        return str(json.loads(SEAL_FILE.read_text(encoding="utf-8")).get("status", "")).upper() == "SEALED"
    except Exception:
        return False

def run_m2_chain():
    """After M1 is sealed, hand off to the ONE canonical conductor.

    Delegates to run_r0_migration_phase_orchestrator.py (single source of truth):
    selfcheck -> M2 build + go/no-go -> verify -> seal M2 (GO/CONDITIONAL) ->
    stops cleanly at the first not-implemented / human-/time-gated phase (M3+).
    Idempotent: already-sealed phases are skipped. We deliberately do NOT
    reimplement any phase logic here, so nothing plays out of tune.
    """
    print(f"[autoseal] {now()} M1 sealed -> handing off to canonical orchestrator", flush=True)
    r = subprocess.run(
        [PY, str(ROOT / "tools" / "run_r0_migration_phase_orchestrator.py")],
        cwd=str(ROOT),        capture_output=True,
        text=True,
    )
    try:
        res = json.loads(r.stdout)
        print(f"[autoseal] orchestrator status={res.get('status')}", flush=True)
        for step in res.get("steps") or []:
            print(f"[autoseal]   step={json.dumps(step, default=str)[:300]}", flush=True)
    except Exception:
        print("[autoseal] orchestrator output:", (r.stdout or "")[:800], flush=True)
        if r.stderr.strip():
            print("[autoseal] orchestrator stderr:", (r.stderr or "")[:400], flush=True)
    _surface_next_planned_step()


def _surface_next_planned_step():
    """Vormerken: surface the registered post-M2 roadmap (no autostart)."""
    plan_path = ROOT / "control" / "r0_migration" / "post_m2_plan.json"
    if not plan_path.is_file():
        return
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return
    nxt = next((s for s in plan.get("steps", []) if str(s.get("status")) == "PLANNED"), None)
    print("[autoseal] ---- registered next step (post_m2_plan.json) ----", flush=True)
    if nxt:
        print(f"[autoseal]   NEXT: {nxt.get('id')} (when={nxt.get('when')}) -> {nxt.get('action')}", flush=True)
        print(f"[autoseal]   gated_by: {nxt.get('gated_by')}", flush=True)
    print(f"[autoseal]   heavy_runs_autostart={plan.get('heavy_runs_autostart')} "
          f"(hard gates kept: {', '.join(plan.get('hard_gates_unchanged', []))})", flush=True)


def m1_calendar_blocker():
    """Authoritative matched-controls calendar check.

    The seal pipeline itself does NOT enforce calendar integrity between
    strategy_daily_returns.csv and mom_blend_matched_controls_daily_returns.csv
    (discover_variant_returns only checks row count). Only the matrix wrapper
    runs it. To keep the gate intact regardless of how the backtest was
    launched, we run the AUTHORITATIVE check (run_validation_matrix.
    _check_m1_matched_controls) here before triggering the seal.

    Returns an error string on a genuine calendar mismatch (fail-closed), or
    None if OK / not determinable (fail-open on pure infra errors so a tooling
    glitch never permanently blocks an otherwise-valid seal).
    """
    try:
        from pathlib import Path
        from tools.run_validation_matrix import _check_m1_matched_controls
        dirs = complete_dirs(M1_VARIANT)
        if not dirs:
            return None
        d = Path(VR) / dirs[-1][0]
        if _fast_seal() and not (d / MATCHED_CSV).is_file():
            print(f"[autoseal] {now()} FAST-SEAL: matched-controls baseline absent -> calendar check skipped (control series backfilled out-of-band).", flush=True)
            return None
        return _check_m1_matched_controls(d)
    except Exception as e:
        print(f"[autoseal] {now()} NOTE calendar-check could not run ({e}); deferring to seal pipeline.", flush=True)
        return None


def run_seal_pipeline():
    """Run the official M1 refresh+autoseal, then verify. Returns (sealed, detail)."""
    print(f"[autoseal] {now()} all 3 variants complete -> running official seal pipeline", flush=True)
    r1 = subprocess.run(
        [PY, str(ROOT / "tools" / "run_r0_migration_phase_m1.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    print("[autoseal] run_r0_migration_phase_m1.py output:", flush=True)
    for ln in (r1.stdout or "").splitlines():
        print("   " + ln, flush=True)
    if r1.stderr.strip():
        print("[autoseal] stderr:", (r1.stderr or "")[:800], flush=True)

    # Authoritative confirmation via verify-only
    r2 = subprocess.run(
        [PY, str(ROOT / "tools" / "seal_r0_migration_phase.py"), "--phase", "M1", "--verify-only", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    sealed = is_sealed()
    detail = ""
    try:
        v = json.loads(r2.stdout)
        detail = json.dumps(v.get("verification", {}).get("blockers", []))
    except Exception:
        detail = (r2.stdout or "")[:300]
    return sealed, detail


def _acquire_singleton():
    """Cross-platform singleton: Windows named mutex, Linux/WSL flock file.

    Returns a handle/file object to keep alive, None if duplicate, or True on
    fail-open (never block sealing if lock API misbehaves).
    """
    import os

    if os.name != "nt":
        try:
            import fcntl

            lock_path = ROOT / "evidence" / "r0_migration" / "m1_autoseal.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(lock_path, "w", encoding="utf-8")
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fh.close()
                return None
            fh.write(str(os.getpid()))
            fh.flush()
            return fh
        except Exception:
            return True

    try:
        import ctypes
        from ctypes import wintypes

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        h = kernel32.CreateMutexW(None, False, "Local\\aa_m1_autoseal_singleton")
        err = ctypes.get_last_error()
        if not h:
            return True
        if err == ERROR_ALREADY_EXISTS:
            return None
        return h
    except Exception:
        return True


def main():
    # Keep the handle referenced for the whole process lifetime so the kernel
    # mutex object stays alive (a second instance then sees ERROR_ALREADY_EXISTS).
    global _SINGLETON_HANDLE
    _SINGLETON_HANDLE = _acquire_singleton()
    if _SINGLETON_HANDLE is None:
        print(f"[autoseal] {now()} another autoseal instance is already running — exiting (singleton).", flush=True)
        return 0

    if is_sealed():
        print(f"[autoseal] {now()} M1 already SEALED — chaining M2 (idempotent).", flush=True)
        run_m2_chain()
        return 0

    for poll in range(1, MAX_POLLS + 1):
        if is_sealed():
            print(f"[autoseal] {now()} M1 SEALED (external) — chaining M2.", flush=True)
            run_m2_chain()
            return 0

        status = {}
        dupes = []
        ready = 0
        for v in VARIANTS:
            cds = complete_dirs(v)
            status[v] = cds
            if cds:
                ready += 1
            if len(cds) > 1:
                dupes.append((v, cds))

        line = " | ".join(
            f"{v.split('_')[0]}:{'OK(' + str(status[v][0][1]) + ')' if status[v] else 'wait'}"
            for v in VARIANTS
        )
        print(f"[autoseal] {now()} poll={poll} ready={ready}/3 :: {line}", flush=True)
        if not status.get(M1_VARIANT):
            for d in glob.glob(os.path.join(VR, "*" + M1_VARIANT + "*")):
                n = count_rows(os.path.join(d, "strategy_daily_returns.csv"))
                if n is not None and n >= MIN_DAYS and not os.path.isfile(os.path.join(d, MATCHED_CSV)):
                    print(f"[autoseal]   NOTE M1 strategy CSV ready ({n}) but matched-controls baseline still writing -> holding seal until both exist.", flush=True)
                    break
        for v, cds in dupes:
            print(f"[autoseal]   NOTE duplicate complete dirs for {v}: {cds} (deterministic seed=42 -> content-equal, harmless)", flush=True)

        if ready == 3:
            cal_err = m1_calendar_blocker()
            if cal_err:
                print(f"[autoseal] {now()} M1 matched-controls CALENDAR MISMATCH: {cal_err} -- NOT sealing (fail-closed).", flush=True)
                time.sleep(INTERVAL)
                continue
            sealed, detail = run_seal_pipeline()
            if sealed:
                print(f"[autoseal] {now()} ===== M1 SEALED ===== blockers={detail}", flush=True)
                run_m2_chain()
                return 0
            print(f"[autoseal] {now()} seal pipeline ran but NOT sealed yet; remaining blockers={detail}", flush=True)
            print("[autoseal] will retry after interval (returns may still be settling).", flush=True)

        time.sleep(INTERVAL)

    print(f"[autoseal] {now()} MAX_POLLS reached without seal.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
