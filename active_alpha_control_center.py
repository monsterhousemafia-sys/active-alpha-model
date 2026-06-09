#!/usr/bin/env python3
"""Operational control layer for the Active Alpha system.

This script does not change model logic and does not place trades. It reads the
existing model/paper outputs, validates operational preconditions, writes compact
status/summary files, and returns non-zero exit codes for failed preflight checks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path.cwd()
CONTROL_DIR_NAME = "control_output"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_set_file(path: Path) -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    if not path.exists():
        return cfg
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("rem ") or line.startswith("::"):
            continue
        m = re.match(r'^set\s+"?([^=\"]+)=([^\"]*)"?\s*$', line, flags=re.I)
        if not m:
            continue
        key = m.group(1).strip()
        val = m.group(2).strip()
        if key:
            cfg[key] = val
    return cfg


def load_config(root: Path) -> Dict[str, str]:
    cfg = parse_set_file(root / "active_alpha_settings.bat")
    user = parse_set_file(root / "active_alpha_user_config.bat")
    cfg.update({k: v for k, v in user.items() if v != ""})
    return cfg


def cfg_path(cfg: Dict[str, str], key: str, default: str) -> Path:
    val = cfg.get(key, default) or default
    p = Path(val)
    return p if p.is_absolute() else ROOT / p


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        y = float(str(x).replace(",", "."))
        if y == y and abs(y) != float("inf"):
            return y
    except Exception:
        pass
    return default


def safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(str(x).replace(",", ".")))
    except Exception:
        return default


def file_age_hours(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    return max(0.0, (datetime.now().timestamp() - path.stat().st_mtime) / 3600.0)


def sha256_file(path: Path, limit_mb: int = 100) -> str:
    if not path.exists() or not path.is_file():
        return ""
    if path.stat().st_size > limit_mb * 1024 * 1024:
        return "too_large"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return {}


def read_csv_rows(path: Path, max_rows: int = 10000) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.exists() or path.stat().st_size == 0:
        return [], []
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            rows = []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append({str(k): "" if v is None else str(v) for k, v in row.items()})
            return rows, list(reader.fieldnames or [])
    except Exception:
        return [], []


def latest_existing(paths: Iterable[Path]) -> Optional[Path]:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


@dataclass
class CheckResult:
    level: str
    item: str
    detail: str


class ControlCenter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cfg = load_config(root)
        self.control_dir = root / CONTROL_DIR_NAME
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.backtest_dir = cfg_path(self.cfg, "AA_BACKTEST_OUT_DIR", "model_output_sp500_pit_t212")
        self.paper_model_dir = cfg_path(self.cfg, "AA_PAPER_MODEL_OUT_DIR", "model_output")
        self.paper_dir = cfg_path(self.cfg, "AA_PAPER_DIR", "paper_output")
        self.membership_file = cfg_path(self.cfg, "AA_MEMBERSHIP_FILE", "ticker_membership.csv")
        self.asset_master_file = cfg_path(self.cfg, "AA_ASSET_MASTER_FILE", "asset_master.csv")

    def _write_text(self, name: str, text: str) -> Path:
        path = self.control_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def _write_json(self, name: str, obj: Any) -> Path:
        path = self.control_dir / name
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def _append_audit(self, mode: str, status: str, detail: str) -> None:
        path = self.control_dir / "control_audit.csv"
        new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if new:
                writer.writerow(["timestamp_utc", "mode", "status", "detail"])
            writer.writerow([utc_stamp(), mode, status, detail])

    def get_paper_equity(self) -> Dict[str, float]:
        state = read_json(self.paper_dir / "paper_state.json")
        cash = safe_float(state.get("cash", self.cfg.get("AA_PAPER_CAPITAL", 0)), safe_float(self.cfg.get("AA_PAPER_CAPITAL", 0)))
        positions, _ = read_csv_rows(self.paper_dir / "paper_positions.csv")
        positions_value = sum(safe_float(r.get("market_value", 0)) for r in positions)
        if positions_value == 0:
            positions_value = sum(safe_float(r.get("shares", 0)) * safe_float(r.get("last_price", 0)) for r in positions)
        equity = cash + positions_value
        equity_rows, _ = read_csv_rows(self.paper_dir / "paper_equity.csv")
        if equity_rows:
            last = equity_rows[-1]
            cash = safe_float(last.get("cash", cash), cash)
            positions_value = safe_float(last.get("positions_value", positions_value), positions_value)
            equity = safe_float(last.get("equity", last.get("total_equity", equity)), equity)
        return {"cash": cash, "positions_value": positions_value, "equity": equity, "n_positions": float(len(positions))}

    def summarize_target(self) -> Dict[str, Any]:
        target_path = self.paper_model_dir / "latest_target_portfolio.csv"
        misplaced_target_path = self.backtest_dir / "latest_target_portfolio.csv"
        rows, fields = read_csv_rows(target_path)
        signal_manifest_path = self.paper_model_dir / "run_manifest.json"
        signal_manifest = read_json(signal_manifest_path)
        manifest_cfg = signal_manifest.get("config", {}) if isinstance(signal_manifest, dict) else {}
        manifest_output_files = signal_manifest.get("output_files", []) if isinstance(signal_manifest, dict) else []
        manifest_output_names = [Path(str(x)).name for x in manifest_output_files]
        out: Dict[str, Any] = {
            "target_file": str(target_path),
            "target_exists": target_path.exists(),
            "target_age_hours": file_age_hours(target_path),
            "misplaced_backtest_target_file": str(misplaced_target_path),
            "misplaced_backtest_target_exists": misplaced_target_path.exists(),
            "misplaced_backtest_target_age_hours": file_age_hours(misplaced_target_path),
            "signal_manifest_file": str(signal_manifest_path),
            "signal_manifest_exists": signal_manifest_path.exists(),
            "signal_manifest_mode": str(manifest_cfg.get("runtime_mode", "")),
            "signal_manifest_has_target": "latest_target_portfolio.csv" in manifest_output_names,
            "n_target_rows": len(rows),
            "target_weight_sum": 0.0,
            "top_holdings": [],
            "fields": fields,
        }
        if not rows:
            return out
        weights = []
        for r in rows:
            ticker = r.get("ticker", "")
            w = safe_float(r.get("target_weight", 0.0))
            weights.append((ticker, w, r))
        out["target_weight_sum"] = sum(w for _, w, _ in weights)
        top = sorted(weights, key=lambda x: abs(x[1]), reverse=True)[:10]
        out["top_holdings"] = [{"ticker": t, "weight": w} for t, w, _ in top]
        diag_fields = [
            "desired_exposure", "regime_target_exposure", "final_validated_exposure",
            "cash_reason", "max_beta_binding", "max_cluster_binding", "gross_exposure_binding",
            "exposure_controller_score", "cash_filler_mode", "cluster_mode",
        ]
        first = rows[0]
        for f in diag_fields:
            if f in first:
                out[f] = first.get(f, "")
        return out

    def read_next_rebalance(self) -> Dict[str, str]:
        path = self.paper_dir / "next_rebalance_due.txt"
        out = {"file": str(path), "exists": str(path.exists()), "recommendation": "UNKNOWN"}
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ":" in raw:
                k, v = raw.split(":", 1)
                out[k.strip()] = v.strip()
        return out

    def status(self, json_mode: bool = False) -> int:
        eq = self.get_paper_equity()
        target = self.summarize_target()
        nxt = self.read_next_rebalance()
        files = {
            "backtest_report": self.backtest_dir / "backtest_report.txt",
            "benchmark_comparison": self.backtest_dir / "benchmark_comparison.csv",
            "statistical_diagnostics": self.backtest_dir / "statistical_diagnostics.csv",
            "constraint_binding_history": self.backtest_dir / "constraint_binding_history.csv",
            "paper_report": self.paper_dir / "paper_report.txt",
            "paper_dashboard": self.paper_dir / "paper_dashboard.txt",
            "paper_model_diagnostics": self.paper_dir / "paper_model_diagnostics.csv",
            "run_manifest_backtest": self.backtest_dir / "run_manifest.json",
            "run_manifest_signal": self.paper_model_dir / "run_manifest.json",
        }
        file_status = {k: {"exists": p.exists(), "age_hours": file_age_hours(p), "path": str(p)} for k, p in files.items()}
        obj = {
            "timestamp": now_stamp(),
            "root": str(self.root),
            "config": self.selected_config(),
            "paper_equity": eq,
            "target": target,
            "next_rebalance": nxt,
            "files": file_status,
        }
        self._write_json("control_status.json", obj)
        text = self.render_status(obj)
        self._write_text("control_status.txt", text)
        self._append_audit("status", "OK", "status written")
        if json_mode:
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        else:
            print(text)
        return 0

    def selected_config(self) -> Dict[str, str]:
        keys = [
            "AA_BENCHMARK", "AA_START_DATE", "AA_BACKTEST_CAPITAL", "AA_RESEARCH_BACKTEST_CAPITAL", "AA_PAPER_CAPITAL", "AA_BACKTEST_OUT_DIR",
            "AA_PAPER_MODEL_OUT_DIR", "AA_PAPER_DIR", "AA_UNIVERSE_TOP_N", "AA_TOP_K",
            "AA_ALPHA_MODEL_MODE", "AA_N_JOBS", "AA_PARALLEL_BACKTEST_BACKEND", "AA_RISK_REGIME_MODE", "AA_EXPOSURE_CONTROLLER",
            "AA_CASH_FILLER_MODE", "AA_BENCHMARK_COMPLETION_TICKER", "AA_BENCHMARK_COMPLETION_MAX_WEIGHT", "AA_CLUSTER_MODE", "AA_CLUSTER_CONSTRAINT_MODE", "AA_STATIC_CLUSTER_CAP", "AA_DYNAMIC_CLUSTER_CAP", "AA_MAX_PORTFOLIO_BETA",
            "AA_MAX_CORRELATION_CLUSTER", "AA_MAX_TURNOVER", "AA_NO_TRADE_BAND",
            "AA_SLIPPAGE_BPS", "AA_TRADING212_FX_BPS", "AA_REPRODUCIBILITY_MODE",
        ]
        return {k: self.cfg.get(k, "") for k in keys}

    def render_status(self, obj: Dict[str, Any]) -> str:
        cfg = obj["config"]
        eq = obj["paper_equity"]
        target = obj["target"]
        nxt = obj["next_rebalance"]
        lines = []
        lines.append("Active Alpha Operational Status")
        lines.append("=" * 39)
        lines.append(f"Zeit: {obj['timestamp']}")
        lines.append(f"Arbeitsordner: {obj['root']}")
        lines.append("")
        lines.append("Konfiguration")
        lines.append("-------------")
        for k, v in cfg.items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("Paper-Ledger")
        lines.append("------------")
        lines.append(f"Cash: {eq['cash']:.2f}")
        lines.append(f"Positionswert: {eq['positions_value']:.2f}")
        lines.append(f"Equity: {eq['equity']:.2f}")
        lines.append(f"Positionen: {int(eq['n_positions'])}")
        lines.append("")
        lines.append("Target / Modellzustand")
        lines.append("----------------------")
        lines.append(f"Target-Datei vorhanden: {target['target_exists']}")
        lines.append(f"Target-Alter Stunden: {target.get('target_age_hours')}")
        lines.append(f"Target-Zeilen: {target['n_target_rows']}")
        lines.append(f"Target-Gewichtssumme: {target['target_weight_sum']:.4f}")
        lines.append(f"Signal-Manifest vorhanden: {target.get('signal_manifest_exists')}")
        lines.append(f"Signal-Manifest Mode: {target.get('signal_manifest_mode', '')}")
        lines.append(f"Signal-Manifest enthaelt Target: {target.get('signal_manifest_has_target')}")
        if target.get("misplaced_backtest_target_exists") and not target.get("target_exists"):
            lines.append(f"WARNUNG: Target liegt im Backtest-Ordner: {target.get('misplaced_backtest_target_file')}")
        for key in ["final_validated_exposure", "cash_reason", "max_beta_binding", "max_cluster_binding", "exposure_controller_score", "cash_filler_mode", "cluster_mode"]:
            if key in target:
                lines.append(f"{key}: {target[key]}")
        if target.get("top_holdings"):
            lines.append("Top-Holdings:")
            for h in target["top_holdings"][:10]:
                lines.append(f"  {h['ticker']}: {safe_float(h['weight']):.2%}")
        lines.append("")
        lines.append("Rebalance")
        lines.append("---------")
        lines.append(f"Empfehlung: {nxt.get('recommendation', 'UNKNOWN')}")
        for k in ["last_rebalance_date", "days_since_last_rebalance", "rebalance_every_days", "next_due_date"]:
            if k in nxt:
                lines.append(f"{k}: {nxt[k]}")
        lines.append("")
        lines.append("Wichtige Dateien")
        lines.append("----------------")
        for k, item in obj["files"].items():
            age = item.get("age_hours")
            age_s = "-" if age is None else f"{float(age):.1f}h"
            lines.append(f"{k}: {'OK' if item['exists'] else 'FEHLT'} | Alter {age_s} | {item['path']}")
        return "\n".join(lines) + "\n"

    def preflight(self, scope: str = "rebalance", json_mode: bool = False, max_signal_age_hours: float = 36.0) -> int:
        checks: List[CheckResult] = []
        def ok(item: str, detail: str) -> None:
            checks.append(CheckResult("OK", item, detail))
        def warn(item: str, detail: str) -> None:
            checks.append(CheckResult("WARN", item, detail))
        def fail(item: str, detail: str) -> None:
            checks.append(CheckResult("ERROR", item, detail))

        required_core = ["active_alpha_model.py", "paper_trading_engine.py", "check_active_alpha_core.py"]
        for name in required_core:
            p = self.root / name
            ok(name, "vorhanden") if p.exists() else fail(name, "fehlt")

        if self.membership_file.exists():
            ok("membership_file", str(self.membership_file))
        elif self.cfg.get("AA_BACKTEST_MEMBERSHIP_MODE", "").lower() == "strict" or scope in {"backtest", "robustness"}:
            fail("membership_file", f"fehlt: {self.membership_file}")
        else:
            warn("membership_file", f"fehlt: {self.membership_file}; im Auto-Modus ggf. tolerierbar")

        if self.asset_master_file.exists():
            ok("asset_master_file", str(self.asset_master_file))
        else:
            warn("asset_master_file", f"fehlt: {self.asset_master_file}")

        if scope in {"rebalance", "paper", "all"}:
            target = self.paper_model_dir / "latest_target_portfolio.csv"
            misplaced_target = self.backtest_dir / "latest_target_portfolio.csv"
            if not target.exists():
                if misplaced_target.exists():
                    fail(
                        "latest_target_portfolio_location",
                        f"Target liegt im Backtest-Ordner ({misplaced_target}); Paper erwartet {target}. Backtest-Launcher nicht mit --mode both ausfuehren.",
                    )
                else:
                    fail("latest_target_portfolio", f"fehlt: {target}")
            else:
                age = file_age_hours(target)
                rows, fields = read_csv_rows(target)
                if "ticker" not in fields or "target_weight" not in fields:
                    fail("latest_target_portfolio_schema", "Spalten ticker und target_weight erforderlich")
                elif not rows:
                    fail("latest_target_portfolio_rows", "keine Zielpositionen")
                else:
                    tw = sum(safe_float(r.get("target_weight", 0.0)) for r in rows)
                    if tw <= 0:
                        fail("latest_target_portfolio_weight", "Gewichtssumme <= 0")
                    elif tw > safe_float(self.cfg.get("AA_MAX_GROSS_EXPOSURE", 1.0), 1.0) + 0.05:
                        fail("latest_target_portfolio_weight", f"Gewichtssumme wirkt zu hoch: {tw:.4f}")
                    else:
                        ok("latest_target_portfolio", f"{len(rows)} Zeilen, Gewichtssumme {tw:.4f}")
                if age is not None and age > max_signal_age_hours:
                    warn("latest_target_portfolio_age", f"Target-Datei ist {age:.1f} Stunden alt")
                else:
                    ok("latest_target_portfolio_age", f"Alter {age:.1f} Stunden" if age is not None else "unbekannt")

            manifest = self.paper_model_dir / "run_manifest.json"
            if manifest.exists():
                manifest_obj = read_json(manifest)
                manifest_cfg = manifest_obj.get("config", {}) if isinstance(manifest_obj, dict) else {}
                manifest_mode = str(manifest_cfg.get("runtime_mode", "")).lower().strip()
                output_names = [Path(str(x)).name for x in manifest_obj.get("output_files", [])] if isinstance(manifest_obj, dict) else []
                if manifest_mode not in {"signal", "both"}:
                    warn("signal_run_manifest_mode", f"Manifest-Mode ist '{manifest_mode or 'unbekannt'}', erwartet signal/both: {manifest}")
                elif "latest_target_portfolio.csv" not in output_names:
                    warn("signal_run_manifest_target", f"Manifest enthaelt latest_target_portfolio.csv nicht: {manifest}")
                else:
                    ok("signal_run_manifest", f"{manifest}; mode={manifest_mode}")
            else:
                warn("signal_run_manifest", f"fehlt: {manifest}")

            if self.paper_dir.exists():
                ok("paper_dir", str(self.paper_dir))
            else:
                warn("paper_dir", f"fehlt; wird bei Engine-Lauf angelegt: {self.paper_dir}")
            eq = self.get_paper_equity()
            if eq["equity"] <= 0:
                fail("paper_equity", f"Equity <= 0: {eq['equity']:.2f}")
            else:
                ok("paper_equity", f"Equity {eq['equity']:.2f}; Cash {eq['cash']:.2f}; Positionen {int(eq['n_positions'])}")

        if scope in {"backtest", "robustness", "all"}:
            if self.backtest_dir.exists():
                ok("backtest_out_dir", str(self.backtest_dir))
            else:
                warn("backtest_out_dir", f"fehlt; wird beim Backtest angelegt: {self.backtest_dir}")
            if scope == "robustness" and not (self.root / "run_robustness_tests.py").exists():
                fail("run_robustness_tests.py", "fehlt")

        errors = [c for c in checks if c.level == "ERROR"]
        warnings = [c for c in checks if c.level == "WARN"]
        status = "ERROR" if errors else ("WARN" if warnings else "OK")
        obj = {
            "timestamp": now_stamp(),
            "scope": scope,
            "status": status,
            "errors": len(errors),
            "warnings": len(warnings),
            "checks": [asdict(c) for c in checks],
        }
        self._write_json("preflight_report.json", obj)
        text = self.render_checks("Active Alpha Preflight", obj)
        self._write_text("preflight_report.txt", text)
        self._append_audit("preflight", status, f"scope={scope}; errors={len(errors)}; warnings={len(warnings)}")
        if json_mode:
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        else:
            print(text)
        return 1 if errors else 0

    def render_checks(self, title: str, obj: Dict[str, Any]) -> str:
        lines = [title, "=" * len(title), f"Zeit: {obj['timestamp']}", f"Scope: {obj.get('scope', '-')}", f"Status: {obj['status']}", ""]
        for c in obj["checks"]:
            lines.append(f"[{c['level']}] {c['item']}: {c['detail']}")
        return "\n".join(lines) + "\n"

    def summary(self, json_mode: bool = False) -> int:
        sections: Dict[str, Any] = {}
        for name, path in {
            "backtest_report": self.backtest_dir / "backtest_report.txt",
            "paper_report": self.paper_dir / "paper_report.txt",
            "paper_dashboard": self.paper_dir / "paper_dashboard.txt",
            "benchmark_comparison": self.backtest_dir / "benchmark_comparison.csv",
            "statistical_diagnostics": self.backtest_dir / "statistical_diagnostics.csv",
            "constraint_binding_history": self.backtest_dir / "constraint_binding_history.csv",
            "paper_model_diagnostics": self.paper_dir / "paper_model_diagnostics.csv",
            "run_manifest_backtest": self.backtest_dir / "run_manifest.json",
            "run_manifest_signal": self.paper_model_dir / "run_manifest.json",
        }.items():
            sections[name] = self.summarize_file(path)
        obj = {"timestamp": now_stamp(), "sections": sections}
        self._write_json("control_summary.json", obj)
        text = self.render_summary(obj)
        self._write_text("control_summary.txt", text)
        self._append_audit("summary", "OK", "summary written")
        if json_mode:
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        else:
            print(text)
        return 0

    def summarize_file(self, path: Path) -> Dict[str, Any]:
        out: Dict[str, Any] = {"path": str(path), "exists": path.exists(), "age_hours": file_age_hours(path), "size_bytes": path.stat().st_size if path.exists() else 0}
        if not path.exists():
            return out
        if path.suffix.lower() == ".json":
            data = read_json(path)
            out["keys"] = sorted(list(data.keys()))[:30] if isinstance(data, dict) else []
            for key in ["timestamp", "run_id", "mode", "benchmark", "start", "config_hash"]:
                if isinstance(data, dict) and key in data:
                    out[key] = data[key]
            return out
        if path.suffix.lower() == ".csv":
            rows, fields = read_csv_rows(path, max_rows=100000)
            out["rows_sampled"] = len(rows)
            out["columns"] = fields[:50]
            if rows:
                out["last_row"] = rows[-1]
            return out
        text = path.read_text(encoding="utf-8", errors="ignore")[:12000]
        out["excerpt"] = text[:3000]
        metrics = {}
        for line in text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                key = k.strip().lower().replace(" ", "_")
                if key in {"total_return", "cagr", "annual_vol", "sharpe_0rf", "max_drawdown", "information_ratio", "tracking_error", "excess_cagr_approx"}:
                    metrics[key] = v.strip()
        if metrics:
            out["metrics"] = metrics
        return out

    def render_summary(self, obj: Dict[str, Any]) -> str:
        lines = ["Active Alpha Report Summary", "=" * 27, f"Zeit: {obj['timestamp']}", ""]
        for name, item in obj["sections"].items():
            lines.append(name)
            lines.append("-" * len(name))
            lines.append(f"Pfad: {item['path']}")
            lines.append(f"Vorhanden: {item['exists']}")
            if item.get("age_hours") is not None:
                lines.append(f"Alter: {float(item['age_hours']):.1f} Stunden")
            if "metrics" in item:
                for k, v in item["metrics"].items():
                    lines.append(f"{k}: {v}")
            if "rows_sampled" in item:
                lines.append(f"Zeilen: {item['rows_sampled']}")
                lines.append(f"Spalten: {', '.join(item.get('columns', [])[:12])}")
            if "last_row" in item:
                small = {k: item["last_row"].get(k, "") for k in list(item["last_row"].keys())[:8]}
                lines.append(f"Letzte Zeile: {small}")
            lines.append("")
        return "\n".join(lines)

    def config(self, json_mode: bool = False) -> int:
        obj = {"timestamp": now_stamp(), "config": self.cfg, "selected": self.selected_config()}
        self._write_json("control_config.json", obj)
        if json_mode:
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        else:
            print("Active Alpha Configuration")
            print("=" * 26)
            for k, v in self.selected_config().items():
                print(f"{k}={v}")
        return 0

    def self_test(self) -> int:
        required = ["active_alpha_model.py", "paper_trading_engine.py", "run_active_alpha_model.bat", "run_paper_trading.bat"]
        missing = [name for name in required if not (self.root / name).exists()]
        if missing:
            print("[ERROR] Fehlende Datei(en): " + ", ".join(missing))
            return 1
        # Test parsers and writers.
        self.status(json_mode=False)
        rc = self.preflight(scope="paper", json_mode=False)
        # Preflight may warn/fail in a clean directory without signals; parser itself is the concern.
        if not (self.control_dir / "control_status.txt").exists() or not (self.control_dir / "preflight_report.txt").exists():
            print("[ERROR] Control-Center-Self-Test konnte Reports nicht schreiben.")
            return 1
        print("[OK] Control-Center-Self-Test bestanden.")
        return 0 if rc in (0, 1) else rc


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Operational control layer for Active Alpha")
    parser.add_argument("--mode", choices=["status", "preflight", "summary", "config"], default="status")
    parser.add_argument("--scope", choices=["rebalance", "paper", "backtest", "robustness", "all"], default="rebalance")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-signal-age-hours", type=float, default=36.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    cc = ControlCenter(ROOT)
    if args.self_test:
        return cc.self_test()
    if args.mode == "status":
        return cc.status(json_mode=args.json)
    if args.mode == "preflight":
        return cc.preflight(scope=args.scope, json_mode=args.json, max_signal_age_hours=args.max_signal_age_hours)
    if args.mode == "summary":
        return cc.summary(json_mode=args.json)
    if args.mode == "config":
        return cc.config(json_mode=args.json)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
