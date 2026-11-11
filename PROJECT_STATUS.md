# Project status

Date: 2026-11-11.

## Current phase

Phase 5 — CYVORA Shield risk engine. The definition of done for this phase is met for the paper boundary below. Phase 6 has not started.

## Current milestone

Shield is the only component that can approve a paper order. Approval means the local simulator may run. It does not enable a live order. A caller cannot approve an order by setting a flag. Risk, allocation, reserve, liquidity, correlation, daily loss, drawdown, consecutive-loss, stop, take-profit, trailing-stop, and emergency checks are deterministic and stored in PostgreSQL.

## Completed work

- Phase 1 foundation, merged as PR #1.
- Phase 2 read-only GMGN client, merged as PR #2 (`4c48ad7`).
- Phase 3 radar cycle, merged as PR #3 (`e9ffb3c`).
- Phase 4 paper ledger, merged on `main` at `b4fcd8c`.
- Phase 5 Shield engine in `shield/`, revision `0004_shield_risk_engine`, paper-gateway decisions, authenticated `/trading/shield` routes, and the Risk Management page.

## In progress

Nothing inside Phase 5.

## Blockers

None for the paper risk boundary. Live trading is still disabled. Shield approval does not enable it. The GMGN key is still not bound to a wallet. Holdings, swaps, and wallet activity stay refused. There is no Solana RPC client. Shield does not submit stop or take-profit orders by itself.

## Tests

Final run on 2026-11-11:

- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — 161 files already formatted.
- `uv run mypy` — no issues in 117 source files.
- `uv run pytest -rs` — 103 passed, 2 skipped.
- Skips: `tests/integration/test_gmgn_live_smoke.py` unless `CYVORA_GMGN_LIVE_SMOKE=1`, and `tests/integration/test_radar_live.py` unless `CYVORA_RADAR_LIVE=1`.
- Desktop smoke: `CYVORA_DESKTOP_SMOKE_OK python=3.13.18 mode=READ-ONLY database=reachable backend=offline gmgn=configured`.
- Alembic on this machine: `0003_trading_infrastructure` upgraded to `0004_shield_risk_engine`.

No API key or database URL is printed.

## Known limitations

- Cloudflare still blocks the Python TLS stack for `openapi.gmgn.ai` on this PC. Live GMGN calls use Windows `curl.exe`. The rate limiter is unchanged.
- Nautilus 1.231.0 on this wheel has fixed precision 9. A wider price stays in CYVORA `Decimal` and is not rounded into a Nautilus price.
- A `CurrencyPair` is a synthetic spot instrument. It is not a Solana swap. `OrderSubmitted` inside the backtest is not a signed transaction.
- GMGN candles do not become bid/ask quotes. Candle volume is not treated as a base size.
- Paper slippage and fees are amounts the caller supplies. There is no pool-impact, latency, or cost model. A missing price impact is not treated as zero.
- A planned stop is not a guaranteed exit. Shield records the plan and does not send the exit.
- The strategy registry does not generate signals. The API sets `RUNNING` strategies to `STOPPED` on startup. The desktop does not start them.
- No Solana RPC, account inspection, or chain confirmation client is included.
- `2.0.0` final was not on PyPI on 2026-11-11. The `2.0.0rc*` builds are not installed.
- Pages other than Dashboard, System Health, the six radar pages, Open Positions, Trade History, Strategies, and Risk Management are placeholders.
- `py -3.13` does not find the uv interpreter. Use `uv run`.

## Security

- Live mode names are rejected. A `paper_approved` decision does not enable them.
- `GMGN_PRIVATE_KEY` is not loaded. The paper path does not call `GMGNExecutionGateway` or a live Nautilus execution client.
- `/radar` and `/trading` require `CYVORA_API_TOKEN`. `/health` stays open and still returns status words only.
- `.env` is gitignored. The example file contains placeholders only.

## Exact next actions

1. Do not start Phase 6 until the user asks.
2. Do not add a signing key, an RPC provider, or a swap. Wallet binding is a separate decision.
3. Phase 6, when requested, is backtesting and a richer paper broker. It is not live execution.

## Phase 5 checklist

| Done criterion | Result |
|---|---|
| Position sizing | Planned-loss quantity from equity, stop distance, fees, and optional confidence. The order is denied above the cap, not resized. |
| Risk per trade | 1% of verified equity. A tight stop cannot outrun a supplied volatility distance. |
| Stop-loss engine | Explicit stop, optional volatility widening, and a stored plan. The stop is not an automatic order. |
| Take-profit engine | 30/50/100/200 percent levels. Planned quantity cannot exceed the position. |
| Trailing stops | Activation, upward-only updates, break-even, and a minimum interval. |
| Daily loss | 5% from the persisted UTC-day baseline. A restart does not mint a new baseline. |
| Drawdown | 15% from the persisted high-water mark. A restart does not reset it. |
| Consecutive losses | Three losing campaigns. Partial exits count once, when the position is flat. |
| Correlation | Shared supplied tags. Missing tags do not become a zero correlation. |
| Allocation | 70% deployed and 10% SOL reserve, including pending buys, without double-counting a position. |
| Liquidity | 2% of supplied pool liquidity. Missing liquidity denies the entry. |
| Emergency stop | Named triggers from supplied evidence. No order is created by the detector. |
| Paper only | Tests show `paper_approved` stays simulated and live submission still raises. |
| Phase 6 not started | No backtest engine, walk-forward runner, or auto-executing paper broker. |
