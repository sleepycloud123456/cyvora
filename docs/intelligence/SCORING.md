# Radar scoring

Date: 2026-11-11.

The score is a research rank. It is deterministic for the same inputs. It does not authorize an entry, a paper order, or a live order. `entry_consideration` is always `not_authorized`.

## Weights

Missing components are left out of the weighted average. They are not scored as zero and they are not treated as safe. A component whose quality is `conflicting` is also left out.

| Component | Weight | Source |
|---|---:|---|
| Security | 22 | `GET /v1/token/security`, with holder rates from token info when present |
| Liquidity | 16 | The lowest liquidity figure among pool info, token info, and the discovery row |
| Momentum | 14 | Close-to-close return, RSI(14), and MACD histogram when the candle window is long enough |
| Volume | 12 | Recent-versus-prior acceleration of candle `volume` and `amount` |
| Smart money | 12 | GMGN wallet-tag counts on token info. Not a copied trade |
| Breakout | 8 | Last close versus the prior high, with volume expansion when both series exist |
| Holder distribution | 6 | Top-10 rate, largest returned holder, and the whale-wallet tag count |
| Market | 5 | Share of non-zero rank changes that are positive, when at least three exist |
| Execution feasibility | 5 | Security and liquidity gates only. Sell simulation is not run |

The weights sum to 100. A token that appears in both the trending list and the new-launch list receives 5 points before the caps below. That bonus is recorded as `confirmation_bonus`.

## Caps

| Decision | Cap |
|---|---:|
| `REJECTED` | 25 |
| `HIGH_RISK` | 45 |
| `UNKNOWN` | 55 |

`APPROVED_FOR_FURTHER_ANALYSIS` and `CAUTION` are not capped. A total of at least 65 with `APPROVED_FOR_FURTHER_ANALYSIS` is stored as lifecycle `watch_suggested`. The watch note says the threshold was met and that this is not an entry. `REJECTED` is lifecycle `rejected`. `UNKNOWN` is lifecycle `blocked_unknown`. Everything else that was scored is `ranked`.

## Security

Categories are `APPROVED_FOR_FURTHER_ANALYSIS`, `CAUTION`, `HIGH_RISK`, `REJECTED`, and `UNKNOWN`.

- A missing security payload is `UNKNOWN`. Unknown is not safe.
- `is_honeypot` true is `REJECTED` with score 0. A missing honeypot flag is not read as false.
- The separate integer `honeypot` field seen on 2026-11-11 is stored as unverified. It does not approve or reject by itself.
- Approval requires renounced mint, renounced freeze, honeypot false, wash-trading false, both taxes present and at most 0.10, rug ratio present and at most 0.5, sniper count 0, top-10 and creator rates present, and at least 70 security points.
- Active mint authority, active freeze authority, wash trading, rug ratio above 0.5, or fewer than 40 points is `HIGH_RISK`.
- `burn_status` is recorded. It is not proof that liquidity is locked.

Tax figures are penalized above 0.10 whether GMGN sent a fraction or a percent, because the scale was not documented.

## Liquidity

The bands apply to the provider's liquidity number. Phase 2 did not prove that number is USD.

| Figure | Points |
|---|---:|
| below 0 | 0 |
| below 1,000 | 15 |
| below 5,000 | 35 |
| below 20,000 | 55 |
| below 100,000 | 75 |
| 100,000 or more | 90 |

Figures that differ by more than 25% are `conflicting`, and 10 points are removed. The lowest figure is kept. A move of at least 10% versus the previous stored snapshot adds 5 points when it rises and removes 10 when it falls. No figure is status `unknown` and is left out of the average.

Price impact is `not_computed`. The quote route is refused, and reserve units were not verified.

## What the indicators do not do

RSI, MACD, volatility, and breakout strength need their windows. A short candle list is `missing` or `partial`, not a neutral 50. Stale candles halve the momentum and breakout points. Buy/sell pressure is recorded as `missing` because a verified pressure field was not selected. Whale transactions are not read. Smart-money purchases are not copied.

Sell feasibility says it was not simulated. Quote and swap routes stay refused.
