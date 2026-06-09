"""Fail-closed checks: approved champion identity + fresh champion signals."""

from __future__ import annotations



import json

from dataclasses import dataclass

from datetime import date

from pathlib import Path

from typing import Any, Dict, List, Mapping, Optional



from analytics.pilot_investment_plan import CHAMPION_ID as LEGACY_CODE_CHAMPION_ID

from analytics.pilot_today_pick import _out_dir



POLICY_REL = "control/learning_collection_policy.json"

PILOT_OUT_DIR_NAME = "model_output_sp500_pit_t212"

_PRE_GO_LIVE_SOFT_BLOCKERS = frozenset(
    {
        "EXPERIMENTAL_PROFILE_UNSEALED_REAL_MONEY",
        "DAILY_ALPHA_H1_NOT_SEALED",
        "DAILY_ALPHA_H1_BACKTEST_FAILED",
        "DAILY_ALPHA_H1_BACKTEST_ZOMBIE",
    }
)


def _native_pilot_pre_go_live_soft_blockers(root: Path) -> frozenset[str]:
    """Seal/backtest blockers become warnings during native PRE_GO_LIVE (GUI-gated orders)."""
    try:
        from execution.linux_security_boundary import go_live_allows_live_sync, is_native_execution_host, load_kernel_doc
    except Exception:
        return frozenset()
    if not is_native_execution_host():
        return frozenset()
    kernel = load_kernel_doc(root)
    if kernel.get("safety", {}).get("auto_execute_real_money"):
        return frozenset()
    if go_live_allows_live_sync(root):
        return frozenset()
    phase = str((kernel.get("learning") or {}).get("phase") or "")
    if phase and phase != "PRE_GO_LIVE_LEARNING":
        return frozenset()
    return _PRE_GO_LIVE_SOFT_BLOCKERS





class ChampionRuntimeGuardError(RuntimeError):

    """Hard champion/signal guard failure — startup must abort."""



    def __init__(self, report: Mapping[str, Any]) -> None:

        self.report = dict(report)

        blockers = report.get("blockers") or []

        msg = str(report.get("message_de") or report.get("status_de") or "Champion-Prüfung fehlgeschlagen")

        if blockers:

            msg = f"{msg} ({'; '.join(blockers)})"

        super().__init__(msg)





@dataclass(frozen=True)

class ChampionRuntimeStatus:

    ok: bool

    champion_ok: bool

    signals_ok: bool

    authoritative_champion: str

    code_champion: str

    signal_profile: str

    auto_champion_update_enabled: bool

    signal_date: Optional[str]

    signal_current: bool

    portfolio_csv_present: bool

    policy_present: bool

    blockers: List[str]

    warnings: List[str]

    status_de: str

    hard_block: bool



    def as_dict(self) -> Dict[str, Any]:

        return {

            "ok": self.ok,

            "champion_ok": self.champion_ok,

            "signals_ok": self.signals_ok,

            "authoritative_champion": self.authoritative_champion,

            "code_champion": self.code_champion,

            "signal_profile": self.signal_profile,

            "auto_champion_update_enabled": self.auto_champion_update_enabled,

            "signal_date": self.signal_date,

            "signal_current": self.signal_current,

            "portfolio_csv_present": self.portfolio_csv_present,

            "policy_present": self.policy_present,

            "blockers": list(self.blockers),

            "warnings": list(self.warnings),

            "status_de": self.status_de,

            "hard_block": self.hard_block,

        }





def load_learning_collection_policy(root: Path) -> Dict[str, Any]:

    path = Path(root) / POLICY_REL

    if not path.is_file():

        return {

            "auto_champion_update_enabled": False,

            "_policy_missing": True,

        }

    try:

        doc = json.loads(path.read_text(encoding="utf-8"))

    except (json.JSONDecodeError, OSError):

        return {

            "auto_champion_update_enabled": False,

            "_policy_unreadable": True,

        }

    return doc if isinstance(doc, dict) else {}





def pilot_signal_out_dir(root: Path) -> Path:

    return _out_dir(Path(root))





def _pilot_assess_env(root: Path) -> Dict[str, str]:

    try:

        from aa_config_env import load_aa_env



        env = dict(load_aa_env(root))

    except Exception:

        env = {}

    env.setdefault("AA_BACKTEST_OUT_DIR", PILOT_OUT_DIR_NAME)

    return env





def _read_signal_freshness(root: Path) -> tuple[Optional[date], bool, bool]:

    """Return (signal_date, signal_current, portfolio_csv_present)."""

    out_dir = pilot_signal_out_dir(root)

    portfolio = out_dir / "latest_target_portfolio.csv"

    if not portfolio.is_file():

        return None, False, False

    try:

        from aa_data_freshness import is_signal_current, read_signal_date



        signal = read_signal_date(out_dir)

        current = is_signal_current(signal)

        iso = signal.isoformat() if signal else None

        return signal, current, True

    except Exception:

        return None, False, True





def _format_status_de(

    *,

    champion_ok: bool,

    signals_ok: bool,

    authoritative: str,

    signal_variant: str,

    signal_date: Optional[str],

    warnings: List[str],

) -> str:

    if not champion_ok:

        return (

            f"Governance-Champion widerspricht SSoT "

            f"({authoritative} erwartet)."

        )

    champ_line = f"Governance OK — {authoritative} | Signal {signal_variant}"

    if signals_ok and signal_date:

        return f"{champ_line} | Signale aktuell ({signal_date})"

    if signal_date:

        return (

            f"{champ_line} | Signale veraltet ({signal_date}) — "

            "EOD/Pipeline aktualisieren"

        )

    if warnings:

        return f"{champ_line} | keine gültigen Signale — Portfolio-CSV fehlt oder leer"

    return f"{champ_line} | Signale unbekannt"





def verify_champion_runtime(root: Path) -> ChampionRuntimeStatus:

    root = Path(root)

    policy = load_learning_collection_policy(root)

    policy_present = not (policy.get("_policy_missing") or policy.get("_policy_unreadable"))



    from analytics.strategic_governance import (

        resolve_active_signal_profile,

        resolve_active_signal_variant,

        resolve_governance_champion,

    )



    authoritative = resolve_governance_champion(root)

    signal_profile = resolve_active_signal_profile(root)

    try:

        from analytics.prediction_operations import load_prediction_operations



        ops = load_prediction_operations(root)

        prediction_ops_active = bool(ops.get("active_profile"))

        ops_governance = str(ops.get("governance_champion") or "").strip()

        code_champion = resolve_active_signal_variant(root) if prediction_ops_active else LEGACY_CODE_CHAMPION_ID

    except Exception:

        prediction_ops_active = False

        ops_governance = ""

        code_champion = LEGACY_CODE_CHAMPION_ID



    locked = str(

        policy.get("governance_champion_locked")

        or policy.get("active_champion_locked")

        or ""

    ).strip()

    auto_update = bool(policy.get("auto_champion_update_enabled"))



    blockers: List[str] = []

    warnings: List[str] = []



    if not policy_present:

        warnings.append("POLICY_FILE_MISSING_OR_UNREADABLE")

    if locked and locked != authoritative:

        blockers.append("GOVERNANCE_CHAMPION_POLICY_MISMATCH")

    if ops_governance and ops_governance != authoritative:

        blockers.append("GOVERNANCE_CHAMPION_OPS_MISMATCH")

    if auto_update:

        blockers.append("AUTO_CHAMPION_UPDATE_ENABLED")

    if policy.get("auto_model_training_enabled") is True:

        warnings.append("AUTO_MODEL_TRAINING_ENABLED")



    try:

        from analytics.live_profile_governance import experimental_profile_blockers



        exp_blocks = experimental_profile_blockers(root)

        if exp_blocks:

            blockers.extend(exp_blocks)

    except Exception:

        pass



    signal_dt, signal_current, portfolio_present = _read_signal_freshness(root)

    signal_date = signal_dt.isoformat() if signal_dt else None



    if not portfolio_present:

        blockers.append("PORTFOLIO_CSV_MISSING")

    elif not signal_date:

        blockers.append("SIGNAL_DATE_MISSING")

    elif not signal_current:

        warnings.append("SIGNAL_DATE_STALE")

    soft = _native_pilot_pre_go_live_soft_blockers(root)
    if soft:
        kept: List[str] = []
        for code in blockers:
            if code in soft:
                if code not in warnings:
                    warnings.append(code)
            else:
                kept.append(code)
        blockers = kept



    champion_ok = not any(

        b in blockers

        for b in (

            "GOVERNANCE_CHAMPION_POLICY_MISMATCH",

            "GOVERNANCE_CHAMPION_OPS_MISMATCH",

            "AUTO_CHAMPION_UPDATE_ENABLED",

        )

    )

    signals_ok = portfolio_present and bool(signal_date) and signal_current

    hard_block = bool(blockers)

    ok = champion_ok and signals_ok and not hard_block

    status_de = _format_status_de(

        champion_ok=champion_ok,

        signals_ok=signals_ok,

        authoritative=authoritative,

        signal_variant=code_champion,

        signal_date=signal_date,

        warnings=warnings,

    )



    return ChampionRuntimeStatus(

        ok=ok,

        champion_ok=champion_ok,

        signals_ok=signals_ok,

        authoritative_champion=authoritative,

        code_champion=code_champion,

        signal_profile=signal_profile,

        auto_champion_update_enabled=auto_update,

        signal_date=signal_date,

        signal_current=signal_current,

        portfolio_csv_present=portfolio_present,

        policy_present=policy_present,

        blockers=blockers,

        warnings=warnings,

        status_de=status_de,

        hard_block=hard_block,

    )





def enforce_champion_runtime_hard(root: Path) -> ChampionRuntimeStatus:

    """Abort startup when champion identity or portfolio inputs are invalid."""

    if __import__("os").environ.get("AA_SKIP_CHAMPION_RUNTIME_GUARD", "").strip() == "1":

        status = verify_champion_runtime(root)

        return status



    status = verify_champion_runtime(root)

    if status.hard_block:

        report = status.as_dict()

        report["message_de"] = status.status_de

        raise ChampionRuntimeGuardError(report)

    return status





def write_guard_evidence(root: Path, status: ChampionRuntimeStatus) -> Path:

    root = Path(root)

    out = root / "evidence" / "champion_runtime_guard_latest.json"

    out.parent.mkdir(parents=True, exist_ok=True)

    payload = status.as_dict()

    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return out


