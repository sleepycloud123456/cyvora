# Project status

Date: 2026-11-11.

## Current phase

Phase 3 — CYVORA Radar and intelligence. The definition of done for this phase is met. Phase 4 has not started.

## Current milestone

CYVORA can discover Solana tokens from GMGN, score them with a documented read-only rubric, and store the cycle in PostgreSQL. The terminal and the loopback API show that store. A score does not authorize an order.

## Completed work

- Phase 1 foundation, merged as PR #1.
- Phase 2 read-only GMGN client, merged as PR #2 (`4c48ad7`).
- Phase 3 radar cycle in `intelligence/`, revision `0002_radar_intelligence`, authenticated `/radar` routes, and terminal pages for the scanner, trending, launches, analysis, smart money, and whales.
- Alembic head on this machine is `0002_radar_intelligence`.
- One live read-only cycle was stored as cycle 1. See Tests.

## In progress

Nothing inside Phase 3.

## Blockers

None for Phase 3. The GMGN key is still not bound to a wallet. Holdings, swaps, and wallet activity stay refused.

## Tests

Final run on 2026-11-11, after the rate-limiter fix and the live cycle:

- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — 120 files already formatted.
- `uv run mypy` — no issues in 81 source files.
- `uv run pytest -rs` — 69 passed, 2 skipped.
- Skips: `tests/integration/test_gmgn_live_smoke.py` unless `CYVORA_GMGN_LIVE_SMOKE=1`, and `tests/integration/test_radar_live.py` unless `CYVORA_RADAR_LIVE=1`.
- Desktop smoke: `CYVORA_DESKTOP_SMOKE_OK python=3.13.18 mode=READ-ONLY database=reachable backend=offline gmgn=configured`.
- Live cycle: `uv run python scripts/radar_cycle.py` printed `RADAR_CYCLE_OK`, `cycle_id=1`, `status=partial`, `weight_used=30`, `requests=13`, `trending=3`, `launches=3`, `analysed=1`, `rate_limit_hits=7`, `error_code=none`, `entry=not_authorized`. The stored row was symbol Rockstar, decision CAUTION, score 60.85, security CAUTION, liquidity observed, smart money observed, whales observed. No API key or database URL was printed.

The partial status is the free-plan bucket. Holder and trader reads are weight 5, the same as the free capacity. After the first token's core reads, GMGN returned rate-limit errors and the rest of that cycle failed the same way. The cycle now stops sending after the first rate-limit response. That behavior is covered by `test_cycle_stops_sending_after_a_rate_limit`. The stored cycle 1 was made before that stop, so its note lists seven rate-limit failures.

## Known limitations

- Cloudflare still blocks the Python TLS stack for `openapi.gmgn.ai` on this PC. Live calls use Windows `curl.exe`.
- The free plan is 5 tokens of capacity refilled at 5 per second. A weight-5 holder or trader read needs a full bucket. The cycle gives those reads up only while budget remains, and it stops the cycle if the server rate-limits.
- The local limiter stops after five waits when the clock does not move. A float Unix timestamp cannot represent a sub-ulp sleep, which previously hung the mocked cycle.
- Smart money is GMGN wallet-tag counts. `/v1/user/smartmoney` is not called. Whale rows are tag counts and holder concentration, not a trade feed.
- Price impact is not computed. The quote route stays refused. `burn_status` is not treated as locked liquidity. Unknown security is not safe.
- The liquidity number is scored with fixed bands. Phase 2 did not prove the unit is USD. Rank changes are used by sign only.
- The terminal repeat checkbox waits the configured interval (default 120 seconds, longer after a partial cycle). Nothing starts a cycle by itself.
- Pages other than Dashboard, System Health, and the six radar pages are placeholders.
- NautilusTrader is not a dependency. The stable candidate remains 1.231.0.
- `py -3.13` does not find the uv interpreter. Use `uv run`.

## Security

- Live mode names are rejected. Radar `entry_consideration` is `not_authorized`.
- `GMGN_PRIVATE_KEY` is not loaded. Logs and errors redact `GMGN_API_KEY` and the database password.
- `/radar` requires `CYVORA_API_TOKEN`. `/health` stays open and still returns status words only.
- `.env` is gitignored. The example file contains placeholders only.

## Exact next actions

1. Do not start Phase 4 until the user asks.
2. Do not add a signing key or call a swap. Wallet binding is a separate decision.
3. Phase 4, when requested, is simulation trading infrastructure. It is not live execution.

## Phase 3 checklist

| Done criterion | Result |
|---|---|
| Trending and new-launch discovery | Live cycle: 3 trending, 3 launches. Routes are the Phase 2 rank and trenches reads. |
| Security, liquidity, indicators | Stored on the analysed token. Rubric in `docs/intelligence/SCORING.md`. |
| Smart money and whales | Tag counts and holder concentration from the same reads. No copied trades. |
| Opportunity score and rank | Deterministic weighted score. Entry stays `not_authorized`. |
| Historical storage | Revision `0002_radar_intelligence` applied. Rows are inserts. |
| Watchlists | API and terminal can add and deactivate a watch. Removal keeps the row. |
| Terminal and API read the store | Scanner and the other radar pages show the stored cycle or an empty state. `/radar` is authenticated. |
| No swaps or transactions | Trade routes refused before HTTP. Intelligence source has no trade path. |
| Phase 4 not started | NautilusTrader is not installed. No strategy or order package. |
