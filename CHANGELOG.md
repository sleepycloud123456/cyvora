# Changelog

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
