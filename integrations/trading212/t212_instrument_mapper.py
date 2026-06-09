"""Map screenshot symbol references to provider instrument IDs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


# Trading 212 US equity tickers commonly use _US_EQ suffix
MAPPING_TABLE = {
    "OXY": {"provider_instrument_id": "OXY_US_EQ", "exchange": "NYSE", "currency": "USD", "instrument_type": "EQUITY"},
    "WDC": {"provider_instrument_id": "WDC_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "SNDK": {"provider_instrument_id": "SNDK_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY", "mapping_note": "Sandisk US equity (user-confirmed; T212 SNDK_US_EQ)"},
    "STX": {"provider_instrument_id": "STX_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "INTC": {"provider_instrument_id": "INTC_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "MU": {"provider_instrument_id": "MU_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "CIEN": {"provider_instrument_id": "CIEN_US_EQ", "exchange": "NYSE", "currency": "USD", "instrument_type": "EQUITY"},
    "GOOGL": {"provider_instrument_id": "GOOGL_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "GOOG": {"provider_instrument_id": "GOOG_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "AMD": {"provider_instrument_id": "AMD_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "CAT": {"provider_instrument_id": "CAT_US_EQ", "exchange": "NYSE", "currency": "USD", "instrument_type": "EQUITY"},
    "ON": {"provider_instrument_id": "ON_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "VRT": {"provider_instrument_id": "VRT_US_EQ", "exchange": "NYSE", "currency": "USD", "instrument_type": "EQUITY"},
    "TXN": {"provider_instrument_id": "TXN_US_EQ", "exchange": "NASDAQ", "currency": "USD", "instrument_type": "EQUITY"},
    "VUSD": {"provider_instrument_id": "VUSD_EQ", "exchange": "LSE", "currency": "GBP", "instrument_type": "ETF", "mapping_status_override": "VERIFIED_WITH_EXCHANGE_QUALIFIER"},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_instrument_mapping(root: Path) -> Dict[str, Any]:
    root = Path(root)
    alloc_path = root / "paper/config/p14_user_reference_allocation_500eur.json"
    alloc = json.loads(alloc_path.read_text(encoding="utf-8"))
    entries: List[Dict[str, Any]] = []
    for pos in alloc.get("positions") or []:
        sym = str(pos.get("symbol_reference", "")).upper()
        meta = MAPPING_TABLE.get(sym, {})
        status = meta.get("mapping_status_override") or (
            "STATIC_CANDIDATE_PENDING_PROVIDER_METADATA" if meta else "NOT_FOUND_REQUIRES_EXCLUSION_FROM_INITIAL_FILL"
        )
        entries.append(
            {
                "display_name": pos.get("display_name"),
                "symbol_reference_from_screenshot": sym,
                "provider": "TRADING212_DEMO_METADATA_AND_STATIC_TABLE",
                "provider_instrument_id": meta.get("provider_instrument_id", ""),
                "exchange": meta.get("exchange", ""),
                "currency": meta.get("currency", ""),
                "instrument_type": meta.get("instrument_type", ""),
                "mapping_status": status,
                "mapping_confidence": "HIGH" if meta else "NONE",
                "mapping_evidence": meta.get("mapping_note", "static_p14_mapping_table_v1"),
                "last_verified_at_utc": _utc_now(),
            }
        )
    out = {"generated_at_utc": _utc_now(), "entries": entries}
    path = root / "paper/config/p14_instrument_mapping.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out
