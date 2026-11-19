# Autonomous paper trader

Date: 2026-11-19. This loop is paper only. It does not sign, read a wallet, call a swap, or enable live trading.

## What it does

`python -m operations.startup --paper-trader` adds one worker, `paper_trader`, after the existing workers. The flag also turns on the read-only radar worker for that process, so GMGN is called once per tick by the existing cycle. Passing `--include-radar` as well does not add a second cycle.

Each pass:

1. The radar worker runs the existing GMGN cycle through `curl.exe` and the rate limiter. Defaults stay at two analysed tokens, weight budget 30, and a 120 second interval. Leave the desktop Live Scanner "Repeat on the configured interval" box off while this supervisor is running, so the desktop does not add a second GMGN cycle.
2. The trader reads that stored cycle. A candidate needs lifecycle `watch_suggested` or `ranked`, a score of at least `CYVORA_PAPER_MIN_SCORE` (default 65), fresh candles, security `APPROVED_FOR_FURTHER_ANALYSIS`, a positive price, and pool reserves stored from that cycle. A missing reserve is not treated as zero depth.
3. It sizes the buy from the virtual bankroll (`CYVORA_PAPER_BANKROLL_SOL`, default 10 SOL). One trade is at most `CYVORA_PAPER_PER_TRADE_FRACTION` (default 0.10). Open marks plus the new trade stay inside `CYVORA_PAPER_MAX_EXPOSURE_FRACTION` (default 0.40). At most `CYVORA_PAPER_MAX_ENTRIES_PER_CYCLE` new entries are sent (default 1).
4. The order goes through `PaperBroker`, the same path the historical strategy runner uses. Shield approves or denies it. `PaperExecutionGateway` stores the paper order, fill, and position. A score does not approve an order.
5. Open `radar-paper` positions are checked against a fresh pool. Take-profit, stop, trailing stop, and max hold come from the stored Shield plan. The entry stop distance is `CYVORA_PAPER_STOP_FRACTION` (default 0.10). Take-profit levels, the trailing stop, and the 24 hour max hold are the Shield defaults in `shield/limits.py`. A planned stop is not a guaranteed exit. The sell is another paper order.
6. If an open position was not in the fresh cycle, the trader may read `GET /v1/token/pool_info` for it, at most `CYVORA_PAPER_QUOTE_LIMIT` times (default 3). A quote older than `CYVORA_PAPER_QUOTE_MAX_AGE_SECONDS` (default 120) is not used.

The virtual bankroll is not a wallet balance. Cash for Shield is the bankroll minus open cost plus stored realized result. Equity is that cash plus the marked value of open positions. A missing mark omits the equity point. It is not stored as zero.

## Gates

The kill switch, an unreadable kill-switch row, and recovery `entries_blocked` refuse new paper orders, including exits. Shield's pause (`halt_entries`) refuses new entries and still allows an exit through Shield. Read-only mode stores no order. The trader starts the `radar-paper` strategy only for the duration of the pass and stops it again, so the historical runner does not treat it as a dataset strategy.

## Desktop

The dashboard shows the trader status, the kill-switch word, open positions with unrealized PnL from stored marks, recent paper trades, the virtual equity curve, and the decision log. A missing mark stays unavailable. The same view is on the authenticated terminal payload under `paper_trader`.

## Nautilus

NautilusTrader 1.231.0 fills stay inside the engine. A `CurrencyPair` fill has no Solana pool reserves and is not an operator paper order. The autonomous trader does not copy those fills into the CYVORA book. See `docs/trading/NAUTILUS_MAPPING.md`.

## Logon launch

The logon file is outside the repository:

`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CYVORA.cmd`

It starts the loopback API and the supervisor. It does not start the desktop. The supervisor line is:

```bat
start "CYVORA Supervisor" /min C:\Users\Anastasiya\.local\bin\uv.exe run python -m operations.startup --ticks 0 --interval-seconds 120 --paper-trader
```

`--paper-trader` is the opt-in. Removing it leaves radar offline and does not submit paper orders. The file is not committed.

## How to stop

- Close the minimized **CYVORA Supervisor** window, or end the `operations.startup` process. That stops new cycles. It does not flatten an open paper position.
- Engage the kill switch from Settings. New paper orders are refused. Live trading stays locked. Release it only with the confirmation already required by the readiness screen.
- Pause entries from Settings to stop new buys. An exit can still be submitted through Shield while the pause is on and the kill switch is released.
- The API and the desktop are separate processes. Closing them does not by itself stop the supervisor.
