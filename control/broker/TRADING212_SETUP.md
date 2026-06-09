# Trading 212 broker integration

Read-only API connectivity for Invest / Stocks ISA accounts.

## Setup

1. In Trading 212: **Settings → API (Beta) → Generate API key**
   - Start with **Demo** account keys recommended.
   - Permissions: at minimum **account data**; add **orders** only when ready for live routing.

2. Copy `.env.trading212.example` → `.env` (repo root, gitignored).

3. Fill in:
   ```env
   TRADING212_API_KEY=your_key
   TRADING212_API_SECRET=your_secret
   TRADING212_ENV=demo
   TRADING212_READ_ONLY=1
   TRADING212_ALLOW_LIVE_ORDERS=0
   ```

4. Verify connection:
   ```powershell
   .venv\Scripts\python.exe tools\setup_trading212_connection.py
   ```

Status written to `control/p13_broker_readiness/trading212_connection.json`.

## Safety defaults

| Setting | Default | Meaning |
|---------|---------|---------|
| `TRADING212_ENV` | `demo` | Demo API host, not live account |
| `TRADING212_READ_ONLY` | `1` | No POST / orders |
| `TRADING212_ALLOW_LIVE_ORDERS` | `0` | Blocks market order submission |
| Kill switch | **active** | Fail-closed until explicitly cleared |

Live order routing also requires `REAL_ORDER_ROUTING_ENABLED` policy change in code review — not enabled by this integration alone.

## Code

- `research/p13/brokers/trading212_client.py` — HTTP client
- `research/p13/brokers/trading212_adapter.py` — broker adapter
- `tools/setup_trading212_connection.py` — connectivity check
