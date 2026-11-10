# Phase 2 plan

GMGN read-only integration. Results are in `PROJECT_STATUS.md` and `docs/integrations/GMGN_API_RESEARCH.md`.

## Decisions before coding

- Read the official Agent API docs and `GMGNAI/gmgn-skills` before naming an endpoint.
- Load the existing `GMGN_API_KEY` line. Do not rename it. Accept `CYVORA_GMGN_API_KEY` as an alias.
- Do not read `GMGN_PRIVATE_KEY`, do not sign, and do not call a trade or holdings route.
- Keep live trading disabled. Health must not call GMGN, because a health poll would spend the rate limit.
- Pace at the free bucket unless the operator sets a plan they already have. Do not buy a plan.
- Mock HTTP in unit tests. A live call is opt-in and must skip when the key is absent.

## Implementation

1. Settings for the key, plan, and timeout, with redaction in logs and dumps.
2. Allowlisted client, exist-auth headers, leaky-bucket limiter, and response models.
3. Market, token, discovery, and wallet services, plus an execution gateway that only refuses.
4. Windows transport through `System32\curl.exe`, after `httpx2` was blocked by Cloudflare on this PC.
5. Desktop and health show whether a key is configured. They do not show prices or balances.
6. Mock tests, a source scan that rejects signing, and `scripts/gmgn_readonly_smoke.py`.

## Verification

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy`
- `uv run pytest`
- `uv run python -m apps.desktop.main --smoke`
- `uv run python scripts/gmgn_readonly_smoke.py` against the local key.

## Out of scope

Radar, scoring, historical storage, watchlists, paper trading, Solana RPC, swaps, and any wallet-mutating call.
