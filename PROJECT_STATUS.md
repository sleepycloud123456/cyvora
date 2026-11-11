# Project status

Date: 2026-11-11.

## Current phase

Phase 7 — complete CYVORA Terminal. The definition of done for the pages below is met. Phase 8 has not started.

## Current milestone

Every sidebar page reads stored radar, paper, Shield, or simulation rows, or it says the row is missing. Portfolio math does not turn a missing mark into zero. The local analyst cannot authorize an order. No control can enable live trading.

## Completed work

- Phase 1 foundation, merged as PR #1.
- Phase 2 read-only GMGN client, merged as PR #2 (`4c48ad7`).
- Phase 3 radar cycle, merged as PR #3 (`e9ffb3c`).
- Phase 4 paper ledger, merged on `main` at `b4fcd8c`.
- Phase 5 Shield engine, merged on `main` at `b7cfd07`.
- Phase 6 simulation package, merged on `main` at `8de3e7e`.
- Phase 7 terminal pages, revision `0006_terminal`, authenticated `/terminal` routes, and the local stored-evidence analyst.

## In progress

Nothing inside Phase 7.

## Blockers

None for the terminal boundary. Live trading is still disabled. A paper approval, a profile, and an analyst finding do not enable it. The GMGN key is still not bound to a wallet. Holdings, swaps, and wallet activity stay refused. There is no Solana RPC client. Telegram delivery is not configured.

## Tests

Recorded on 2026-11-11 after the Phase 7 run:

- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv run mypy` passed.
- `uv run pytest` — 125 passed, 2 skipped. The skips are the opt-in GMGN and radar live smokes.
- `uv run python -m apps.desktop.main --smoke` printed `CYVORA_DESKTOP_SMOKE_OK` with database reachable and backend offline.
- Alembic upgrade applied `0006_terminal`. `uv run alembic current` is `0006_terminal (head)`.

No API key or database URL is printed.

## Known limitations

- Cloudflare still blocks the Python TLS stack for `openapi.gmgn.ai` on this PC. Live GMGN calls use Windows `curl.exe`. The rate limiter is unchanged.
- Nautilus 1.231.0 on this wheel has fixed precision 9. A wider price stays in CYVORA `Decimal` and is not rounded into a Nautilus price.
- A `CurrencyPair` is a synthetic spot instrument. It is not a Solana swap. `OrderSubmitted` inside the Nautilus proof is not a signed transaction, and that proof is not the CYVORA backtest. The CYVORA backtest goes through Shield.
- GMGN candle volume is not base size. A single liquidity figure is not a reserve pair. Those bars do not fill. Reserves from a later radar snapshot are not copied onto an earlier candle.
- The constant-product impact for a buy equals the fraction of quote reserve spent. It is not a measured Solana AMM fee. The fee is the configured schedule.
- Displayed depth is one price level. A wide spread is refused when it exceeds the impact cap. It is not tightened to zero.
- A planned stop is not a guaranteed exit. The broker submits a paper sell through Shield and fills it at the pool or book.
- Sharpe and Sortino are per observation and are omitted below 30 return observations. They are not annualized. The terminal uses the same rule on stored equity changes.
- Walk-forward windows each start from the same paper equity. They are not one continuous portfolio. Selected parameters are not deployed.
- The simulation strategies are momentum, breakout, and stored-signal follow. They do not read a wallet.
- Backtests use an isolated ledger. They do not change the operator paper book. The modeled paper route does.
- No Solana RPC, account inspection, or chain confirmation client is included.
- `2.0.0` final was not on PyPI on 2026-11-11. The `2.0.0rc*` builds are not installed.
- Wallet SOL and USD value are not available. Verified equity is the last Shield baseline.
- A missing open-position mark is not treated as zero. Mixed quotes are not summed.
- The latest radar cycle does not store a market-condition label.
- Smart-money accumulation and application-stopped notices have no stored source, so they are not emitted.
- Entry and exit markers are not drawn on candles. Buy and sell pressure is not a stored series. Liquidity history is stored and is not a separate chart.
- A profile signal threshold is recorded and is not applied to the score or to Shield.
- Telegram delivery is off. No bot token is loaded.
- No background worker supervisor is running. That belongs to Phase 8.
- `py -3.13` does not find the uv interpreter. Use `uv run`.

## Security

- Live mode names are rejected. A `paper_approved` decision does not enable them. The terminal has no control that can.
- `GMGN_PRIVATE_KEY` is not loaded. The paper path does not call `GMGNExecutionGateway` or a live Nautilus execution client.
- `/radar`, `/trading`, `/trading/simulation`, and `/terminal` require `CYVORA_API_TOKEN`. `/health` stays open and still returns status words only.
- `.env` is gitignored. The example file contains placeholders only.
- Simulation rows constrain `live_trading_enabled` to false. Run rows constrain `parameters_deployed` to false.
- Terminal profile, preference, and notification rows constrain live trading to false. Telegram delivery is constrained to false.
- Analyst findings set `authorizes_order` false. No external model is called.

## Exact next actions

1. Do not start Phase 8 until the user asks.
2. Do not add a signing key, an RPC provider, a swap, or a Telegram bot token. Wallet binding is a separate decision.
3. Phase 8, when requested, is long-running local operations and a cloud design. It is not live execution.

## Phase 7 checklist

| Done criterion | Result |
|---|---|
| Dashboard | Stored paper figures, with wallet SOL and USD explicitly unavailable. |
| Scanner and radar pages | Stored cycle, filter, sort, and watchlist. A score does not authorize an entry. |
| Token analysis, smart money, whales | Stored cycle rows and the candle chart. |
| Portfolio | Shield equity, marks, cost, and open paper positions. Missing marks stay missing. |
| Positions, trade history, strategies | Stored paper rows. Start and stop do not submit an order. |
| Risk management | Stored Shield book. Pause and resume go through Shield. |
| Backtesting and paper trading | Stored simulation reports. Parameters stay undeployed. |
| Analytics | Stored equity, drawdown, campaign results, and separate research books. |
| AI analyst | Local stored-evidence findings. Advisory only. |
| Notifications | Local notices, categories, quiet period, and dedup. Telegram stays off. |
| Settings | Mode display, locked live trading, locked manual orders, paper profiles. |
| Health | Existing probe plus stored-evidence freshness. No Phase 8 supervisor. |
| Paper only | Tests reject live and Telegram flags. Pause does not submit an order. |
| Phase 8 not started | No worker supervisor, backup, or cloud resource was added. |
