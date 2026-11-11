# Changelog

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
