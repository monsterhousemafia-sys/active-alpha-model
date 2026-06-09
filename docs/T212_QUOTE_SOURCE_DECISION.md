# T212 Quote Source Decision (Phase 0)

**Generated:** 2026-06-02T16:53:17+00:00  
**Credential profile:** CONFIRMED_EXECUTION  

## Spike results

| Fetch | Status |
|-------|--------|
| `GET /equity/metadata/instruments` | OK |
| `GET /equity/positions` | OK |

- Instruments total (parsed): **15609**
- Champion tickers matched: **13** / 13
- Open positions: **0**

## Official API (v0)

- Documented read paths: `/equity/metadata/instruments`, `/equity/positions`, `/equity/account/cash`.
- **No** documented REST endpoint for live bid/ask quotes for arbitrary tickers.
- Stop-order docs reference **Last Traded Price (LTP)** internally, not exposed as a standalone quote API.

## Recommendation

**Held positions:** `T212_POSITIONS_CURRENT_PRICE_FOR_HELD`  
**Pre-buy champion wave:** `T212_METADATA_NO_PRICE_USE_YAHOO_VALIDATED`  

- Instruments usable for live quote (spike): **False**
- Positions usable for live quote: **False**

### Notes

- Instrument-Metadaten für Champion-Ticker vorhanden, aber kein klares Live-Preisfeld — Felder in Sample prüfen.
- metadata/instruments: nur Ticker/ISIN/Währung — alle 13 Champion-Ticker verifiziert, kein Live-Preis.
- Offizielle Public API v0 dokumentiert kein REST /equity/quote; Stop-Orders referenzieren LTP intern.
- metadata/instruments Rate-Limit: 1 req / 50s — Cache Pflicht.

## Price-like fields in instruments payload

- `[0].maxOpenQuantity` → sample `34899.0`
- `[1].maxOpenQuantity` → sample `54071.0`
- `[2].maxOpenQuantity` → sample `34585.0`

## Positions pricing summary

```json
[]
```

## Artifacts

- `evidence/t212_instruments_sample.json`
- `evidence/t212_positions_sample.json`
- `evidence/t212_phase0_spike_summary.json`

## Next (Phase 1)

Implement `t212_instrument_quotes.py` per pre-buy recommendation above; cache instruments 50s+; never size orders from Yahoo caps when T212 or validated price exists.

