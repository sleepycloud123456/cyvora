# Cost estimate

Date: 2026-11-10. Nothing in this file was purchased, deployed, or subscribed. Figures are planning bands for a later decision, not quotes.

## Phase 1, this PC

| Item | Monthly cost | State |
|---|---:|---|
| Windows desktop, uv, Python, PySide6, FastAPI, local git | €0 | In use |
| PostgreSQL on this PC | €0 software cost | Not installed |
| Docker Desktop | €0 for this use, if installed later | Not installed |
| Cloud hosts, managed Postgres, paid RPC, paid AI, GMGN fees | €0 | Not activated |

The infrastructure spend for the running Phase 1 system is €0. Electricity for the PC is not estimated.

## Later options, not selected

The monthly budget in the product prompt is €20–50. These bands are here so a later phase can stay inside it. They are not approval to buy anything.

| Item | Planning band | Notes |
|---|---|---|
| Local PostgreSQL | €0 | The default. Backup disk is the operator's own disk. |
| Managed PostgreSQL | Often a large share of €20–50 for a small instance | Adds a network exposure decision the local server does not have. |
| Small VPS for a future worker | Often about €5–15 | Only relevant after the local system is proven. A Windows desktop would remain the control panel. |
| Solana RPC | Public endpoints are rate limited. A dedicated endpoint is commonly a paid plan. | Not selected. Phase 1 does not call an RPC. |
| GMGN API | Unknown until the official pricing and the embedded-wallet terms are read in Phase 2 | Do not assume the API is free. |
| Telegram bot API | €0 for the bot platform itself | Not implemented. |
| AI analysis | Depends on the provider and volume | No provider is wired. Prompts must not include secrets. |
| NautilusTrader library | €0 license fee | LGPL-3.0-or-later. Not installed. |
| Market-data history storage | Grows with candle retention | Keep it local until the volume is measured. |

## Required versus optional

- Required for the current phase: the existing PC. €0.
- Required before migrations can be applied: a local PostgreSQL install. €0 of software.
- Optional and currently unjustified: VPS, managed database, paid RPC, paid AI, and any GMGN paid tier.

## Scaling limit of the local setup

One Windows PC can run the terminal, the API, and PostgreSQL together while the data volume is small. The limit that matters first is API rate limits and disk, not a second server. Moving the worker to a VPS would be a new security design (authentication, bind address, secret storage) and needs a separate approval.
