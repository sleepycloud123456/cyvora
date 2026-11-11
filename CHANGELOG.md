# Changelog

## 0.7.0 — 2026-11-11 — Phase 7

- Completed the terminal pages that were still placeholders: Portfolio, Analytics, CYVORA Intelligence, Notifications, and Settings. The dashboard reads the stored paper book.
- Portfolio figures use Shield baselines and stored radar marks. A missing mark is not zero. Wallet SOL and USD stay unavailable.
- Added a local stored-evidence analyst. Findings are advisory and cannot authorize an order. No external model is called.
- Stored local notifications with categories, a quiet period, and dedup. Telegram delivery stays off because no bot token is loaded.
- Added paper profiles and Shield pause/resume. A profile threshold is not applied. No control can enable live trading.
- Stored the new rows in PostgreSQL revision `0006_terminal`.

## 0.6.0 — 2026-11-11 — Phase 6

- Added a simulation-only backtest, walk-forward runner, and strategy comparison. Reports record research limits and do not deploy parameters.
- Added constant-product and displayed-depth fills, an explicit fee schedule, and an execution-delay window. Candle close is a mark, not a fill. A missing impact is not stored as zero.
- Routed every priced paper order through Shield. Stops, take-profits, and time exits are new paper orders. A planned stop is not the fill price.
- Stored datasets, runs, and fill assumptions in PostgreSQL revision `0005_simulation`. The Backtesting and Paper Trading pages read those rows.
- Left GMGN on the existing curl transport and rate limiter. No RPC, wallet, signer, or Phase 7 page was added.

## 0.5.0 — 2026-11-11 — Phase 5

- Added the deterministic Shield engine: position size, stops, take-profits, trailing stops, allocation, SOL reserve, liquidity, correlation, daily loss, drawdown, consecutive-loss campaigns, and emergency classification.
- Wired Shield into the paper gateway. A stored decision is `paper_approved` or `denied`. A caller cannot approve an order, and a paper approval cannot submit a live order.
- Stored the risk book in PostgreSQL revision `0004_shield_risk_engine`. The Risk Management page reads that book. Notices stay local.
- Left GMGN on the existing curl transport and rate limiter. No RPC, wallet, signer, or Phase 6 broker was added.

## 0.4.0 — 2026-11-11 — Phase 4

- Added NautilusTrader 1.231.0 and an offline proof for Solana instrument precision, quotes, trades, bars, a full fill, an IOC partial, and a denied buy.
- Added a paper gateway, order states, position accounting, reconciliation, and a strategy registry. Live submission stays refused. Shield stays `not_authorized`.
- Stored the ledger in PostgreSQL revision `0003_trading_infrastructure` and showed it on authenticated `/trading` routes and the terminal ledger pages.
- Left GMGN on the existing curl transport and rate limiter. No RPC, wallet, or signer was added.

## 0.3.0 — 2026-11-11 — Phase 3

- Added a read-only radar cycle: trending and new-launch discovery, security, liquidity, indicators, smart-money and whale tag counts, and a documented score.
- Stored each cycle in PostgreSQL revision `0002_radar_intelligence`. Later cycles insert history. They do not overwrite it.
- Added authenticated loopback `/radar` routes and terminal pages that show the stored cycle or an empty state.
- Scores do not authorize an entry. Live trading, signing, and NautilusTrader stay out.
- Stopped the GMGN rate limiter from spinning when a float clock cannot move by the computed wait.

## 0.2.0 — 2026-11-11 — Phase 2

- Added a read-only GMGN client for documented market, token, discovery, and account calls.
- Refused trade routes, signing, and wallet holdings. Live trading stays disabled.
- Recorded the official API, the live response shapes, and the empty embedded-wallet probe.
- Noted that PostgreSQL 17 is installed and the first migration is applied.

## 0.1.0 — 2026-11-10 — Phase 1

- Established the Windows development foundation on Python 3.13 with a uv lockfile.
- Added fail-closed settings, structured logging, a loopback health API, and the first PostgreSQL migration.
- Added the CYVORA Terminal shell with branded navigation and explicit placeholders.
- Recorded NautilusTrader, PostgreSQL, Docker, and WSL2 limits. Live trading is not implemented.
