# GMGN Agent API research

Verification date: 2026-11-11.

This file records what was read from official sources and what a live read-only call returned. It does not contain an API key, a wallet address, a balance, or a price.

## Sources

| Source | What it settled |
|---|---|
| https://docs.gmgn.ai/index/gmgn-agent-api | Product overview, IPv4-only note, query versus trading credentials, hosted-wallet description. |
| https://github.com/GMGNAI/gmgn-skills `main`, package `gmgn-cli` 1.7.1 | `src/client/OpenApiClient.ts`, `src/client/signer.ts`, `src/config.ts`, `src/commands/market.ts`, `skills/gmgn-market/SKILL.md`. |
| Live calls from this PC | HTTP 200 JSON from `https://openapi.gmgn.ai` through Windows `curl.exe`. Shapes are summarized below. |

The host in `src/config.ts` is `https://openapi.gmgn.ai`. CYVORA calls only that host. Callout and other GMGN products were not integrated.

## Authentication

Exist auth, used for the reads below, is three values:

- Header `X-APIKEY`.
- Query `timestamp`, Unix seconds. The signer comment says the server accepts about ±5 seconds.
- Query `client_id`, a UUID. The signer comment says a replay is rejected for about 7 seconds.

Signed auth adds `X-Signature` over `{sub_path}:{sorted_query}:{body}:{timestamp}`. Ed25519 signs the raw message. RSA uses PSS with SHA-256 and salt length 32. The private key is `GMGN_PRIVATE_KEY`, and it must match the public key uploaded at https://gmgn.ai/ai. CYVORA does not read that variable, does not sign, and does not send `X-Signature`.

The marketing page says query skills need the API key only, and trading needs the API key plus the signing private key. The same page says the hosted wallet does not store private keys locally. The CLI still requires the local signing key before a swap. Those two statements are both in the official material. This phase did not try a swap, so it does not decide which statement governs an existing embedded wallet.

## Rate limits

The market skill describes a leaky bucket. Refill rate and capacity are the same number:

| Plan | Rate and capacity |
|---|---|
| Free | 5 / 5 |
| Plus | 20 / 20 |
| Pro | 50 / 50 |

CYVORA defaults to `free` and does not buy a plan. A higher-tier key is paced at the free rate until `CYVORA_GMGN_PLAN` is set. That is slower than the paid quota, which is the safe direction.

Documented weights are in `integrations/gmgn/constants.py`. A 1-second candle is weight 3 and is described as Pro-only, with a shared global ceiling of 500 requests per second that this client cannot see. The skill's 1-second section names the failure `403 PRO_PLAN_REQUIRED`. The official client names `PLAN_UPGRADE_REQUIRED`. CYVORA handles `PLAN_UPGRADE_REQUIRED` and does not retry it. Which string the server sends was not observed, because this phase did not request a 1-second candle.

The client retries one rate-limit response only when the error is `RATE_LIMIT_EXCEEDED` or `RATE_LIMIT_BANNED` and the wait is at most 5 seconds plus a 1-second buffer. `RATE_LIMIT_BANNED_MAX` is not retried. The official client says a request during a cooldown extends the ban by 5 seconds, up to 5 minutes.

## Transport

IPv6 is documented as unsupported. On this PC, `httpx2` received a Cloudflare HTML 403, title "Attention Required! | Cloudflare", heading "Sorry, you have been blocked", for `https://openapi.gmgn.ai`. Changing the user agent did not change that result. The same read through `C:\Windows\System32\curl.exe` with `--ipv4` returned HTTP 200 `application/json`.

The Windows client therefore uses that curl binary. The API key is written only to a temporary config file, the process arguments are `--disable` and `--config`, and the file is removed before the call returns. `--disable` skips a user curlrc. `noproxy = "*"` ignores ambient proxy variables. Redirects are not followed. Other platforms still use `httpx2` bound to IPv4, which this PC showed is not enough to pass Cloudflare.

## Endpoints CYVORA can call

All of these are exist-auth routes that `OpenApiClient.ts` calls. Weights are the skill-page weights. Unit tests mock HTTP. The live column is this PC on 2026-11-11.

| Method and path | Weight | Live result | Schema notes |
|---|---:|---|---|
| `GET /v1/market/rank` | 3 | HTTP 200. Three Solana rows for `interval=1h` and `limit=3`. | `data` was a second envelope (`code`, `message`, `reason`, `data.rank`). The client unwraps that once. Omitting filters is not "no filter"; the skill says Solana defaults are `renounced` and `frozen`. |
| `GET /v1/token/info` | 1 | HTTP 200 for the first trending token. | Object. `price` is an object whose `price` is numeric and whose `volume_*` and `price_*` fields arrived as strings. `pool.fee_ratio` arrived as a number. |
| `GET /v1/token/security` | 1 | HTTP 200. | `open_source` was an int (`0` on the sample), not a string. `renounced_mint` and `renounced_freeze_account` were bools. `burn_status` was a 4-character string (`burn` on the sample). `is_honeypot` was null. `honeypot` was a separate int. |
| `GET /v1/token/pool_info` | 1 | HTTP 200. | Pool object. `liquidity` and reserves were numeric. Top-level `fee_ratio` was a 1-character string and is kept as an extra field. `price` was null on the sample. |
| `GET /v1/market/token_kline` | 2, or 3 for `1s` | HTTP 200. `data.list` length 1 after the timestamp fix. | The CLI accepts Unix seconds and multiplies by 1000. Sending seconds returned an empty list. Sending milliseconds returned one candle, which parsed into the documented candle fields. The skill table says `volume` is base-token size and `amount` is USD. An earlier note on the same page swaps those meanings. CYVORA keeps both and does not choose. |
| `POST /v1/trenches` | 2 | HTTP 200 for `new_creation` only. | Body `version=v2` matches the official client when only `new_creation` is requested. `limit: 3` still came back as 60 rows. CYVORA returns the first `limit` rows and still sends the documented limit. |
| `GET /v1/user/info` | 2 | HTTP 200. | Object with one observed key, `wallets`, a list of length 0. Wallet-object field names are unknown until a non-empty list is returned. |
| `GET /v1/market/token_top_holders` | 5 | Not called live. | Implemented and covered by the allowlist. Weight 5 was left out of the smoke to stay inside the free bucket. |
| `GET /v1/market/token_top_traders` | 5 | Not called live. | Same as holders. |
| `GET /v1/market/search` | 1 | Not called live. | Skill says `coins` and `wallets` are an additive passthrough. |
| `GET /v1/user/wallet_activity` | 3 | Not called live. | Needs a wallet address. This key has none. |
| `GET /v1/user/wallet_stats` | 3 | Not called live. | Same. |
| `POST /v1/user/wallet_profits` | 3 | Not called live. | Same. |
| `GET /v1/user/wallet_token_balance` | 2 | Not called live. | Same. The field table was not in the skill pages read here. The method returns the object unchanged. |
| `GET /v1/user/created_tokens` | 2 | Not called live. | Same. |

## Routes the official client has that CYVORA does not call

Present in `OpenApiClient.ts`, refused before any socket:

- `/v1/trade/swap`, `/v1/trade/multi_swap`, `/v1/trade/quote`, `/v1/trade/query_order`, `/v1/trade/gas_price`
- `/v1/trade/follow_wallet`, `/v1/trade/strategy/create`, `/v1/trade/strategy/cancel`, `/v1/trade/strategy/orders`
- `/v1/user/wallet_holdings` (signed)
- `/v1/cooking/create_token` (signed)

Any path under `/v1/trade/` is refused even if it is missing from that list. Quote and gas price are exist-auth in the official client. They are still refused here because this phase is market and token research, not a trade helper.

Verified in the official client and not wrapped, so no parser was invented:

- `POST /v1/market/token_signal`
- `POST /v1/market/hot_searches`
- `GET /v1/user/follow_tokens`, `follow_token_groups`, `kol`, `smartmoney`
- `GET /v1/cooking/statistics`
- `POST /v1/callout/get_record` and `POST /v1/callout/global` if present in a later revision of the file; they were not added here.

`OpenApiClient.ts` contains no WebSocket client and no `wss://` URL. The hot-search skill describes a `version` field as "Subscription version — persist it for WebSocket reconnect" and does not give a socket URL. A socket may exist. Its address and protocol were not found.

## Chains

The CLI validator lists `sol`, `bsc`, `base`, `eth`, `arbitrum`, `hyperevm`, `robinhood`, `arc`, `stable`, and `avalanche`. The marketing page's chain table on the same day listed SOL, BSC, and Base only. CYVORA accepts the CLI set and rejects other names. Live calls used `sol` only. Solana addresses are base58, 32–44 characters. EVM chains in the client (`bsc`, `base`, `eth`, `arbitrum`, `avalanche`) require `0x` plus 40 hex digits. The other chain address formats are not specified beyond a non-empty token without spaces.

## Embedded wallet

`GET /v1/user/info` was the compatibility probe. The body was `{"wallets": []}` after types and lengths were taken and values were dropped. This API key does not currently identify a bound wallet. Holdings require the signing key and are refused. No swap was sent, so it is unknown whether a locally generated signing key would operate the existing GMGN embedded wallet. No private key was requested or loaded.

## Unknown after this pass

- Wallet-object fields inside `user/info`, because the list was empty.
- Whether the embedded wallet can be bound without a signing key.
- The WebSocket URL and payload, if a socket exists.
- A data-freshness SLA. Responses carry timestamps such as `creation_timestamp` and `open_timestamp`. No staleness guarantee was documented.
- Which of the two `volume` / `amount` descriptions is right.
- Which plan-upgrade error string a 1-second candle returns.
- Why `pool_info.fee_ratio` was a 1-character string while the pool nested in `token/info` carried a numeric `fee_ratio`.
- Field tables for wallet token balance. The method does not invent them.
- Search, holders, traders, and the address-scoped wallet reads were not called live.

## How to repeat the live check

The default test run does not call GMGN. The smoke script does, and it exits 0 without a network call when `GMGN_API_KEY` is unset.

```powershell
uv run python scripts/gmgn_readonly_smoke.py
```

A single rank call is also available as `tests/integration/test_gmgn_live_smoke.py` when `CYVORA_GMGN_LIVE_SMOKE=1`. Without that variable, pytest skips it.
