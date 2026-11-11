# CYVORA Terminal

Date: 2026-11-11. The desktop reads stored radar, paper, Shield, and simulation rows. It does not add a wallet, a signer, or a live order. The surface is black with a purple accent. Live trading stays locked.

## Navigation

The window opens on an icon rail. The visible pages, in order, are Dashboard, Open Positions, Trade History, Paper Trading, Strategies, Backtesting, Risk Management, Analytics, Notifications, and System Health. Each icon has a tooltip with the page name. The active icon uses the purple accent.

`apps/desktop/navigation.py` keeps one catalog. Pages removed from the rail stay in that catalog with `shown` false: the six radar pages, Portfolio, CYVORA Intelligence, and Settings. Their widgets and data paths remain. Set `shown` to true to put a page back on the rail in list order.

The header shows the configured mode, `READ-ONLY` or `PAPER`, and the slogan TRADE BEYOND LIMITS. The mode badge tooltip states that live trading is locked. Changing the mode is still an environment change and a restart. Settings remains the page that stores profiles, notification preferences, pause, resume, the kill switch, and the session motion checkbox. It is not on the rail.

Long explanations sit behind a Details control. Empty books stay one short line. No page is filled with sample prices.

## Motion

The Dashboard draws a purple holographic wireframe: a projected sphere, a light cone, scanlines, a slow flicker, and a chromatic edge. Page changes fade and settle. Icons and cards pick up a purple glow on hover and when active. `CYVORA_UI_ANIMATIONS=false` stops the hologram timer, the page fade, and the glow animation at startup. The Settings page checkbox applies the same flag for the current session and does not write the environment. The colors stay either way. Restart the desktop after changing the environment flag.

## Pages

Every catalog page reads stored data or says that the data is missing. An empty book is an empty state. It is not filled with sample prices.

## Portfolio figures

Verified equity is the latest Shield UTC-day baseline. It is not a wallet SOL balance. USD value is not stored, so the card stays unavailable. Open cost is summed only when every open position uses one quote. Unrealized results use a stored radar ranking price, or, if that price is missing, the last stored candle close. The candle source is labeled as a mark and is not a fill. One missing mark keeps the total unrealized result missing. It is not stored as zero.

Available capital is the last verified equity minus the current marked value of open SOL positions. The two times can differ. Mixed quotes are not converted.

## Analytics

The equity curve and drawdown use stored baselines only. A missing day is not filled with zero. Sharpe and Sortino stay empty below 30 stored equity changes, the same rule as the backtest. Research comparisons stay on their own books. `parameters_deployed` remains false. Closed campaigns supply win rate, profit, holding time, strategy totals, and token totals. There is no per-strategy equity curve, so per-strategy drawdown is not stated.

## CYVORA Intelligence

The only provider is `stored-evidence`. It explains stored analyses, Shield posture, the paper book, and undeployed simulation rows. Every finding has `authorizes_order` false. No external model is called, and no market text is invented when the cycle is missing.

## Notifications

Notices are inserted from stored discoveries, confirmed paper orders, Shield decisions, emergencies, breach reasons, and the local status probe. The dedup key stops a repeat inside the configured interval. A quiet window withholds non-critical notices. Emergency, daily loss, drawdown, consecutive losses, database failure, API disconnection, and liquidity removal stay recorded. Smart-money accumulation and application-stopped have no stored source, so they are not emitted. Telegram delivery is constrained off. No bot token is loaded.

## Settings and controls

The configured mode is the header badge. The Settings page is off the rail and still holds the same controls. Changing `READ_ONLY` or `PAPER` is an environment change and a restart. There is no control that can set a live mode. Manual order entry is locked. Strategy start and stop call the existing paper registry and do not submit an order. Pause and resume call Shield. Resume is refused while a breach is latched or an emergency halt trigger is active. A pause does not submit an order. The motion checkbox changes only the desktop animation.

A trading profile stores a name, strategy ids, and an optional signal threshold from 0 to 1. The threshold is not applied to the radar score or to Shield. Global Shield limits remain the only trade-approval authority.

## Routes

`/terminal/snapshot`, `/terminal/profiles`, `/terminal/notifications/preferences`, and `/terminal/controls/pause` and `resume` require `CYVORA_API_TOKEN`. They bind with the rest of the API on loopback. A request that sets live trading or Telegram delivery is rejected.

## Charts that stay limited

Stored candles and the equity and drawdown series are drawn. Entry and exit markers are not drawn because paper orders are not aligned to candle indexes. Buy and sell pressure is not a stored series. RSI and MACD appear only when the radar stored those indicator names. Liquidity history remains in PostgreSQL and is not a separate chart.
