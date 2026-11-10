# Project status

Date: 2026-11-11.

## Current phase

Phase 2 — GMGN read-only integration. The definition of done for this phase is met. Phase 3 has not started.

## Current milestone

CYVORA can read GMGN market and token data with the local API key, and it refuses every trade and signing route. PostgreSQL 17 is installed and the Phase 1 migration is applied.

## Completed work

- Phase 1 foundation, merged as PR #1. The checkout this phase started from was `main` at `bc12d05`.
- Confirmed PostgreSQL 17.11 is the Windows service `postgresql-x64-17` (Running, Automatic). `psql` is not on `PATH`. The client is `C:\Program Files\PostgreSQL\17\bin\psql.exe`. Alembic current and head are both `0001_application_metadata`.
- Investigated the GMGN Agent API from the official docs and `GMGNAI/gmgn-skills` `main` (`gmgn-cli` 1.7.1). Findings are in `docs/integrations/GMGN_API_RESEARCH.md`.
- Added `integrations/gmgn`: exist-auth reads, a free-plan rate limiter, response models, and an execution gateway that only refuses.
- Live Windows calls go through `C:\Windows\System32\curl.exe` because Cloudflare blocked `httpx2` with an HTML 403. The API key stays in a temporary config file, not on the command line.
- Health and the terminal show `gmgn=configured` or `not_configured`. They do not call GMGN and they do not show prices.

## In progress

Nothing inside Phase 2.

## Blockers

None for Phase 2. The GMGN key is not bound to a wallet: `GET /v1/user/info` returned a `wallets` list of length 0. Portfolio monitoring and swaps stay unavailable until that is resolved without loading a private key.

## Tests

Final run on 2026-11-11, after the live parser fixes:

- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — 91 files already formatted.
- `uv run mypy` — no issues in 57 source files.
- `uv run pytest -rs` — 53 passed, 1 skipped.
- Skip: `tests/integration/test_gmgn_live_smoke.py` unless `CYVORA_GMGN_LIVE_SMOKE=1`.
- Desktop smoke: `CYVORA_DESKTOP_SMOKE_OK python=3.13.18 mode=READ-ONLY database=reachable backend=offline gmgn=configured`.
- Live smoke: `uv run python scripts/gmgn_readonly_smoke.py` printed `GMGN_SMOKE_OK`.

The live smoke made seven documented reads. All seven returned HTTP 200. Connection state was `reachable`, `success_count=7`, `failure_count=0`. The rank list had 3 rows. Token info, security, and pool parsed. Kline `data.list` had 1 candle after `from` and `to` were sent as milliseconds. New launches were capped to the requested 3. `user/info` was a `wallets` list of length 0, with values removed. No API key, address, or balance was printed.

## Known limitations

- Cloudflare blocks the Python TLS stack for `openapi.gmgn.ai` on this PC. Live calls depend on Windows `curl.exe`.
- The Solana trending call omits filters, so GMGN's default `renounced` and `frozen` filters apply.
- `POST /v1/trenches` with `limit: 3` returned 60 rows. The service keeps the first `limit` rows.
- The market skill contradicts itself on whether `volume` or `amount` is USD. Both fields are stored and neither is labeled as the dollar total.
- `GET /v1/user/info` did not identify the existing GMGN embedded wallet. Signed holdings and every `/v1/trade/` path are refused.
- Holders, traders, search, and address-scoped wallet reads are implemented and mock-tested. They were not part of the live smoke.
- The terminal still uses placeholders for every page except Dashboard and System Health. Those pages do not show market numbers.
- NautilusTrader is not a dependency. The stable candidate remains 1.231.0.
- `py -3.13` does not find the uv interpreter. Use `uv run`.
- WSL2 still cannot start until virtualization is enabled. It is not required.

## Security

- Live mode names are rejected.
- `GMGN_PRIVATE_KEY` is not loaded. Logs and errors redact `GMGN_API_KEY` and the database password.
- `.env` is gitignored. The example file contains the name `GMGN_API_KEY` and the placeholder `CHANGE_ME`.

## Exact next actions

1. Do not start Phase 3 until the user asks.
2. Do not add a signing key or call a swap to "finish" wallet binding. That needs a separate decision.
3. Phase 3, when requested, is Radar and token intelligence. It is not trading.

## Phase 2 checklist

| Done criterion | Result |
|---|---|
| Official API access verified | Live HTTP 200 reads. Research doc records the shapes. |
| Credential requirements verified without collecting a new secret | API key for reads. Signing key for swaps and holdings. The signing key was not collected. |
| GMGN client | `integrations/gmgn` |
| Market, trending, token, security, and price reads | Live smoke, with the limits above. |
| Wallet monitoring where authorized | Account probe only. No wallet is bound. Holdings refused. |
| Embedded-wallet compatibility | Not bound to this key. Execution not attempted. |
| Connection monitoring and errors | In-process state on the client. Health shows configuration only. |
| Mock tests | Unit and security tests. Live test skips by default. |
| No swaps or transactions | Trade routes refused before HTTP. |
| Phase 3 not started | No Radar, scoring, history store, or watchlist. |
