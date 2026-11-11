# Nautilus health check

Date: 2026-11-11. Package: NautilusTrader 1.231.0. Mode under test: paper only. Live trading stayed off. No wallet, key, or signature was used.

The check is `trading/nautilus/health.py`. `uv run python -m trading.nautilus.health` printed ok for every step on this machine.

## What works

- The installed package imports, and the version is 1.231.0.
- A Nautilus backtest node starts with an empty paper venue named SOLANA, finishes one run, and shuts its engine down.
- The synthetic BONK/SOL pair loads into the engine. A paper buy of 10 fills, and one open position of 10 remains until the engine is disposed.
- A separate CYVORA paper round trip goes through Shield. A buy of 4 at 2 and a sell of 4 at 3 are confirmed. Realized PnL is 4. The flat position has no unrealized PnL.
- The same paper order, sent through the API with the local token, is stored as confirmed. The positions route shows quantity 2. The terminal snapshot shows one open position, live trading false, and no order authority.
- While the kill switch is engaged, a new paper order is refused and the book does not change. Sending the same idempotency key again returns the original order.
- A three-bar series in the stored-bar shape runs through Shield on an isolated paper ledger. Parameters are not deployed.
- The database schema is at Alembic revision `0008_readiness`, which is the head. The loaded kill-switch word is `released`. It was not engaged or released by this check.

## What was fixed

No defect turned up in the Nautilus paper path. The engine already disposed itself after the older proof, and that still holds for the node and the fill.

The code changes in this follow-up are the local security items, not a Nautilus bugfix. Authentication failures are reloaded after a restart. Detailed health requires the local token, and a request with no token only learns that the process is live. Those are described in `docs/security/SECURITY_REVIEW.md`.

## What is still limited

- Shield and Nautilus are not one pipeline. A Shield paper order is filled by the CYVORA simulator and stored in the CYVORA book. A Nautilus fill stays inside the backtest engine. The engine does not write PostgreSQL, and the paper gateway does not submit into Nautilus.
- The health round trip and the API view used an in-memory book. This run did not insert an operator paper order. PostgreSQL remains the store the API uses when a database is configured and the mode is paper.
- The loaded execution mode is `READ_ONLY`. In that mode the API refuses to store a paper order. The health check used an explicit paper mode in memory. The mode was not changed.
- No simulation dataset is stored in PostgreSQL, so the short backtest could not read one. It used three bars shaped like a stored series and did not save a run. An isolated backtest does not consult the kill switch and does not change the operator book.
- The live Nautilus trading node was not started. There is no live data client and no live execution client.
- The pair is a synthetic spot instrument. A fill is not a Solana swap and not a signed transaction.
- Prices wider than 9 decimal places are not loaded into this Nautilus wheel.
- `fsspec` stays at 2026.2.0 because NautilusTrader 1.231.0 requires that exact version. Moving it to the patched 2026.6.0 does not resolve. CYVORA does not call the affected filesystem API.
