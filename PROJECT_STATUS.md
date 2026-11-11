# Project status

Date: 2026-11-11.

## Current phase

Phase 4 — CYVORA Core trading infrastructure. The definition of done for this phase is met for the simulation boundary below. Phase 5 has not started.

## Current milestone

CYVORA can store an explicit paper order, account for the resulting position, reconcile it, and register a strategy slot. NautilusTrader 1.231.0 can represent a Solana mint as a synthetic spot pair when the scale fits in 9 decimals, and its backtest engine can fill, partially fill, or deny that order offline. A score still does not authorize an order. A paper confirmation is not a chain confirmation.

## Completed work

- Phase 1 foundation, merged as PR #1.
- Phase 2 read-only GMGN client, merged as PR #2 (`4c48ad7`).
- Phase 3 radar cycle, merged as PR #3 (`e9ffb3c`).
- Phase 4 paper ledger in `trading/`, revision `0003_trading_infrastructure`, authenticated `/trading` routes, and terminal pages for positions, trade history, and strategies.
- NautilusTrader 1.231.0 installed with uv. The mapping and the offline proof are in `docs/trading/NAUTILUS_MAPPING.md`.

## In progress

Nothing inside Phase 4.

## Blockers

None for the paper boundary. Live trading is still disabled. The GMGN key is still not bound to a wallet. Holdings, swaps, and wallet activity stay refused. There is no Solana RPC client.

## Tests

Final run on 2026-11-11:

- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — 148 files already formatted.
- `uv run mypy` — no issues in 106 source files.
- `uv run pytest -rs` — 87 passed, 2 skipped.
- Skips: `tests/integration/test_gmgn_live_smoke.py` unless `CYVORA_GMGN_LIVE_SMOKE=1`, and `tests/integration/test_radar_live.py` unless `CYVORA_RADAR_LIVE=1`.
- Desktop smoke: `CYVORA_DESKTOP_SMOKE_OK python=3.13.18 mode=READ-ONLY database=reachable backend=offline gmgn=configured`.
- Alembic on this machine: `0002_radar_intelligence` upgraded to `0003_trading_infrastructure`.

The Nautilus proof asserts `FILLED` for the full book, `CANCELED` with filled `5.000000` for the IOC partial, and `DENIED` with filled `0.000000` when cash is `0.000000001` SOL. No API key or database URL is printed.

## Known limitations

- Cloudflare still blocks the Python TLS stack for `openapi.gmgn.ai` on this PC. Live GMGN calls use Windows `curl.exe`. The rate limiter is unchanged.
- Nautilus 1.231.0 on this wheel has fixed precision 9. A wider price stays in CYVORA `Decimal` and is not rounded into a Nautilus price.
- A `CurrencyPair` is a synthetic spot instrument. It is not a Solana swap. `OrderSubmitted` inside the backtest is not a signed transaction.
- GMGN candles do not become bid/ask quotes. Candle volume is not treated as a base size.
- Paper slippage and fees are amounts the caller supplies. There is no pool-impact, latency, or cost model.
- Shield is not implemented. Every paper order stores `shield_decision = not_authorized`.
- The strategy registry does not generate signals. The API sets `RUNNING` strategies to `STOPPED` on startup. The desktop does not start them.
- No Solana RPC, account inspection, or chain confirmation client is included.
- `2.0.0` final was not on PyPI on 2026-11-11. The `2.0.0rc*` builds are not installed.
- Pages other than Dashboard, System Health, the six radar pages, Open Positions, Trade History, and Strategies are placeholders.
- `py -3.13` does not find the uv interpreter. Use `uv run`.

## Security

- Live mode names are rejected. Paper confirmation does not enable them.
- `GMGN_PRIVATE_KEY` is not loaded. The paper path does not call `GMGNExecutionGateway` or a live Nautilus execution client.
- `/radar` and `/trading` require `CYVORA_API_TOKEN`. `/health` stays open and still returns status words only.
- `.env` is gitignored. The example file contains placeholders only.

## Exact next actions

1. Do not start Phase 5 until the user asks.
2. Do not add a signing key, an RPC provider, or a swap. Wallet binding is a separate decision.
3. Phase 5, when requested, is the Shield risk engine. It is not live execution.

## Phase 4 checklist

| Done criterion | Result |
|---|---|
| NautilusTrader integration verified | 1.231.0 imports on this Windows 11 PC. Three offline backtest cases pass. |
| Instrument definitions | Mint, symbol, and scales. Projection stops above 9 decimals. |
| Solana data adapters | Supplied observations and GMGN candles become contracts. No RPC. |
| Market-data contracts | Missing bid, ask, and size stay missing. |
| Execution gateway interface | Paper submit, read-only refusal, and live refusal. |
| Order state management | Paper path plus `UNKNOWN` from reconciliation. Live states are rejected. |
| Position accounting | Decimal average, cost, realized result, and optional unrealized mark. |
| Strategy manager | Register, start, stop, and route an explicit intent. No signal logic. |
| Execution reconciliation | Match, conflict, or unknown. A mismatch does not retry or rewrite the position. |
| Simulation only | Tests show paper mode cannot submit a real transaction. |
| Phase 5 not started | No Shield engine, no position sizing, and no emergency stop. |
