# Project status

Date: 2026-11-11.

## Current phase

Phase 6 — backtesting and paper trading. The definition of done for the simulation boundary below is met. Phase 7 has not started.

## Current milestone

Backtests, walk-forward runs, and strategy comparisons are simulation-only. The paper broker prices fills from a constant-product pool or one displayed book level, then submits every priced order through Shield. A paper approval still cannot enable a live order. Candle close is a mark, not a fill. A missing pool impact is not stored as zero.

## Completed work

- Phase 1 foundation, merged as PR #1.
- Phase 2 read-only GMGN client, merged as PR #2 (`4c48ad7`).
- Phase 3 radar cycle, merged as PR #3 (`e9ffb3c`).
- Phase 4 paper ledger, merged on `main` at `b4fcd8c`.
- Phase 5 Shield engine, merged on `main` at `b7cfd07`.
- Phase 6 simulation package in `backtesting/`, revision `0005_simulation`, authenticated `/trading/simulation` routes, and the Backtesting and Paper Trading pages.

## In progress

Nothing inside Phase 6.

## Blockers

None for the simulation boundary. Live trading is still disabled. Shield approval does not enable it. The GMGN key is still not bound to a wallet. Holdings, swaps, and wallet activity stay refused. There is no Solana RPC client.

## Tests

Recorded on 2026-11-11 after the Phase 6 run:

- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed (186 files).
- `uv run mypy` passed (138 source files).
- `uv run pytest` — 114 passed, 2 skipped. The skips are the opt-in GMGN and radar live smokes.
- `uv run python -m apps.desktop.main --smoke` returned `CYVORA_DESKTOP_SMOKE_OK` in `READ-ONLY`, with the database reachable and the backend offline.
- `uv run alembic upgrade head` applied `0005_simulation`. `uv run alembic current` is `0005_simulation (head)`.

No API key or database URL is printed.

## Known limitations

- Cloudflare still blocks the Python TLS stack for `openapi.gmgn.ai` on this PC. Live GMGN calls use Windows `curl.exe`. The rate limiter is unchanged.
- Nautilus 1.231.0 on this wheel has fixed precision 9. A wider price stays in CYVORA `Decimal` and is not rounded into a Nautilus price.
- A `CurrencyPair` is a synthetic spot instrument. It is not a Solana swap. `OrderSubmitted` inside the Nautilus proof is not a signed transaction, and that proof is not the CYVORA backtest. The CYVORA backtest goes through Shield.
- GMGN candle volume is not base size. A single liquidity figure is not a reserve pair. Those bars do not fill. Reserves from a later radar snapshot are not copied onto an earlier candle.
- The constant-product impact for a buy equals the fraction of quote reserve spent. It is not a measured Solana AMM fee. The fee is the configured schedule.
- Displayed depth is one price level. A wide spread is refused when it exceeds the impact cap. It is not tightened to zero.
- A planned stop is not a guaranteed exit. The broker submits a paper sell through Shield and fills it at the pool or book.
- Sharpe and Sortino are per-bar and are omitted below 30 return observations. They are not annualized.
- Walk-forward windows each start from the same paper equity. They are not one continuous portfolio. Selected parameters are not deployed.
- The simulation strategies are momentum, breakout, and stored-signal follow. They do not read a wallet.
- Backtests use an isolated ledger. They do not change the operator paper book. The modeled paper route does.
- No Solana RPC, account inspection, or chain confirmation client is included.
- `2.0.0` final was not on PyPI on 2026-11-11. The `2.0.0rc*` builds are not installed.
- Pages other than Dashboard, System Health, the six radar pages, Open Positions, Trade History, Strategies, Risk Management, Backtesting, and Paper Trading are placeholders.
- `py -3.13` does not find the uv interpreter. Use `uv run`.

## Security

- Live mode names are rejected. A `paper_approved` decision does not enable them.
- `GMGN_PRIVATE_KEY` is not loaded. The paper path does not call `GMGNExecutionGateway` or a live Nautilus execution client.
- `/radar`, `/trading`, and `/trading/simulation` require `CYVORA_API_TOKEN`. `/health` stays open and still returns status words only.
- `.env` is gitignored. The example file contains placeholders only.
- Simulation rows constrain `live_trading_enabled` to false. Run rows constrain `parameters_deployed` to false.

## Exact next actions

1. Do not start Phase 7 until the user asks.
2. Do not add a signing key, an RPC provider, or a swap. Wallet binding is a separate decision.
3. Phase 7, when requested, is the remaining terminal pages. It is not live execution.

## Phase 6 checklist

| Done criterion | Result |
|---|---|
| Historical data | Datasets store bars, signals, and the universe, including mints with no bars. Radar candles adapt without treating volume as base size. |
| Backtesting engine | One isolated paper book walks bars in time. The strategy cannot see a later bar. |
| Paper broker | Priced orders go through Shield. Unpriced bars are refused before a fill is invented. |
| Execution simulation | Fills, size caps, Shield denials, stale windows, and insufficient liquidity are represented. |
| Cost model | The fee is an explicit schedule. A missing schedule is not a zero fee. |
| Slippage model | Adverse quote distance from spot or mid to the modeled execution price. |
| Liquidity model | Constant-product reserves, or one displayed book level. Missing reserves are not zero impact. |
| Strategy comparison | Momentum and breakout run on separate books. The result is not a combined portfolio and is not deployed. |
| Walk-forward | Parameters are chosen on the train window only. A failed train rule takes no test trades. |
| Performance reports | Return, profit, win rate, drawdown, fees, holding time, exposure, and contribution. Sharpe and Sortino wait for 30 returns. |
| Paper only | Tests show the backtest stays simulated and live submission still raises. |
| Phase 7 not started | Portfolio, Analytics, and the other unfinished pages stay placeholders. |
