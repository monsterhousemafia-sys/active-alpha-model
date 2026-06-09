"""Lightweight M1 liveness probe: per-variant worker CPU + autoseal state.

Kept as the single M1 monitor (replaces the deleted one-shot probes).
Run: python tools/_m1_progress.py
"""
import ctypes
import glob
import os
import subprocess
import time
from ctypes import wintypes

ROOT = r"E:\active_alpha_model"
PQI = 0x0400


class FT(ctypes.Structure):
    _fields_ = [("l", wintypes.DWORD), ("h", wintypes.DWORD)]


def _sec(ft):
    return ((ft.h << 32) | ft.l) / 1e7


def cpu_sec(pid):
    k = ctypes.windll.kernel32
    h = k.OpenProcess(PQI, False, pid)
    if not h:
        return None
    try:
        c, e, kt, ut = FT(), FT(), FT(), FT()
        if k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
            return _sec(kt) + _sec(ut)
        return None
    finally:
        k.CloseHandle(h)


def python_procs():
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"],
        capture_output=True, text=True)
    out = {}
    for line in ps.stdout.splitlines():
        parts = line.split("|", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            out[int(parts[0].strip())] = parts[1]
    return out


def main():
    procs = python_procs()
    variants = {
        "R0": "210245Z_R0",
        "R3": "203857Z_R3",
        "M1": "211142Z_M1",
    }
    pids = {v: [p for p, c in procs.items() if tag in c] for v, tag in variants.items()}
    t0 = {p: cpu_sec(p) for vp in pids.values() for p in vp}
    time.sleep(6.0)
    t1 = {p: cpu_sec(p) for vp in pids.values() for p in vp}
    for v, vp in pids.items():
        delta = sum((t1[p] - t0[p]) for p in vp if t0.get(p) and t1.get(p))
        csv = glob.glob(os.path.join(ROOT, "validation_runs", f"*{variants[v]}*", "strategy_daily_returns.csv"))
        rows = (sum(1 for _ in open(csv[0])) - 1) if csv else None
        state = f"DONE rows={rows}" if rows is not None else f"running {delta / 6:.1f} cores"
        print(f"  {v}: pids={vp or '-'}  {state}")
    seal = os.path.join(ROOT, "evidence", "r0_migration", "m1_phase_seal.json")
    print(f"  M1 seal file: {'PRESENT' if os.path.isfile(seal) else 'not yet'}")


if __name__ == "__main__":
    main()
