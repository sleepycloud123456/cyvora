"""Historical series. A step can read a bar only at or before its decision time."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from domain.exceptions import TradingValidationError
from domain.simulation import HistoricalBar, HistoricalDataset, HistoricalSignal, UniverseMember
from trading.instruments import require_mint

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
_MAX_BARS = 400
_MAX_MINTS = 4
_MAX_SIGNALS = 50


def require_dataset(dataset: HistoricalDataset) -> HistoricalDataset:
    """Reject a series that is unlabeled, oversized, or timestamped without a zone."""

    if _ID.fullmatch(dataset.dataset_id) is None:
        raise TradingValidationError(
            "A dataset id must be 2 to 41 lowercase letters, digits, _ or -."
        )
    name = dataset.name.strip()
    if not name or len(name) > 64:
        raise TradingValidationError("A dataset name must be 1 to 64 characters.")
    source = dataset.source.strip()
    if not source or len(source) > 40:
        raise TradingValidationError("A dataset source must be 1 to 40 characters.")
    note = dataset.selection_note.strip()
    if len(note) < 12 or len(note) > 240:
        raise TradingValidationError("A selection note must be 12 to 240 characters.")
    if len(dataset.bars) > _MAX_BARS:
        raise TradingValidationError("A dataset can store at most 400 bars.")
    if len(dataset.signals) > _MAX_SIGNALS:
        raise TradingValidationError("A dataset can store at most 50 signals.")
    mints = {bar.mint for bar in dataset.bars}
    if len(mints) > _MAX_MINTS:
        raise TradingValidationError("A dataset can cover at most 4 mints.")
    seen: set[tuple[str, datetime]] = set()
    bars: list[HistoricalBar] = []
    for bar in dataset.bars:
        checked = _bar(bar)
        key = (checked.mint, checked.observed_at)
        if key in seen:
            raise TradingValidationError("A dataset cannot repeat a mint at the same time.")
        seen.add(key)
        bars.append(checked)
    signals = tuple(_signal(item) for item in dataset.signals)
    members = tuple(_member(item) for item in dataset.members)
    limitations = tuple(dict.fromkeys(dataset.limitations))
    return HistoricalDataset(
        dataset.dataset_id,
        name,
        source,
        note,
        tuple(sorted(bars, key=lambda item: (item.observed_at, item.mint))),
        signals,
        members,
        limitations,
    )


class HistoricalSeries:
    """Bars grouped by mint and ordered by time."""

    def __init__(self, dataset: HistoricalDataset) -> None:
        checked = require_dataset(dataset)
        self.dataset = checked
        grouped: dict[str, list[HistoricalBar]] = defaultdict(list)
        for bar in checked.bars:
            grouped[bar.mint].append(bar)
        self._bars = {mint: tuple(rows) for mint, rows in grouped.items()}
        self.timestamps = tuple(sorted({bar.observed_at for bar in checked.bars}))

    def mints(self) -> tuple[str, ...]:
        return tuple(sorted(self._bars))

    def bars(self, mint: str) -> tuple[HistoricalBar, ...]:
        return self._bars.get(mint, ())

    def visible(self, mint: str, when: datetime) -> tuple[HistoricalBar, ...]:
        """Return bars known at ``when``. Later bars are not included."""

        return tuple(bar for bar in self.bars(mint) if bar.observed_at <= when)

    def bar_at(self, mint: str, when: datetime) -> HistoricalBar | None:
        for bar in self.bars(mint):
            if bar.observed_at == when:
                return bar
        return None

    def first_in_window(self, mint: str, start: datetime, end: datetime) -> HistoricalBar | None:
        for bar in self.bars(mint):
            if bar.observed_at < start:
                continue
            if bar.observed_at > end:
                return None
            return bar
        return None

    def last_close(self, mint: str, when: datetime) -> Decimal | None:
        close: Decimal | None = None
        for bar in self.visible(mint, when):
            if bar.close is not None and bar.close > 0:
                close = bar.close
        return close

    def slice_between(self, start: datetime, end: datetime) -> HistoricalDataset:
        """Copy the dataset down to observations inside an inclusive window."""

        bars = tuple(bar for bar in self.dataset.bars if start <= bar.observed_at <= end)
        signals = tuple(item for item in self.dataset.signals if start <= item.observed_at <= end)
        return HistoricalDataset(
            self.dataset.dataset_id,
            self.dataset.name,
            self.dataset.source,
            self.dataset.selection_note,
            bars,
            signals,
            self.dataset.members,
            self.dataset.limitations,
        )


def missing_mints(dataset: HistoricalDataset) -> tuple[str, ...]:
    """Mints the universe listed that have no bars. They are not priced."""

    present = {bar.mint for bar in dataset.bars}
    missing = [member.mint for member in dataset.members if member.mint not in present]
    return tuple(dict.fromkeys(missing))


def bar_from_radar_candle(
    *,
    mint: str,
    symbol: str,
    candle_time: int | None,
    open_price: Decimal | None,
    high: Decimal | None,
    low: Decimal | None,
    close: Decimal | None,
    volume: Decimal | None,
    evidence: tuple[tuple[str, str], ...] = (),
    snapshot_at: datetime | None = None,
) -> tuple[HistoricalBar | None, tuple[str, ...]]:
    """Adapt one stored radar candle. Volume is not copied into base size.

    Reserves are copied only when the liquidity snapshot is known at or before
    the candle and both reserve fields were stored. A single liquidity figure
    does not become a pool.
    """

    limitations = ["gmgn_candle_volume_is_not_base_size", "candle_close_is_not_a_fill"]
    observed = _candle_time(candle_time)
    if observed is None:
        return None, (*limitations, "candle_time_missing")
    base = _evidence_decimal(evidence, "base_reserve")
    quote = _evidence_decimal(evidence, "quote_reserve")
    if base is None or quote is None or snapshot_at is None or snapshot_at > observed:
        base = None
        quote = None
        limitations.append("radar_liquidity_is_not_a_reserve_pair")
    else:
        limitations.append("reserves_come_from_a_stored_radar_snapshot")
    return (
        HistoricalBar(
            mint=require_mint(mint),
            symbol=symbol.strip() or "TOKEN",
            observed_at=observed,
            source="radar_candle",
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume_quote=volume,
            base_volume=None,
            base_reserve=base,
            quote_reserve=quote,
        ),
        tuple(limitations),
    )


def _bar(bar: HistoricalBar) -> HistoricalBar:
    mint = require_mint(bar.mint)
    _require_time(bar.observed_at)
    symbol = bar.symbol.strip()
    if not symbol or len(symbol) > 32:
        raise TradingValidationError("A bar symbol must be 1 to 32 characters.")
    source = bar.source.strip()
    if not source or len(source) > 40:
        raise TradingValidationError("A bar source must be 1 to 40 characters.")
    for value in (
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume_quote,
        bar.base_volume,
        bar.base_reserve,
        bar.quote_reserve,
        bar.bid,
        bar.ask,
        bar.bid_size,
        bar.ask_size,
        bar.volatility,
    ):
        if value is not None and (not value.is_finite() or value < 0):
            raise TradingValidationError("A bar amount must be finite and cannot be negative.")
    return HistoricalBar(
        mint=mint,
        symbol=symbol,
        observed_at=bar.observed_at,
        source=source,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume_quote=bar.volume_quote,
        base_volume=bar.base_volume,
        base_reserve=bar.base_reserve,
        quote_reserve=bar.quote_reserve,
        bid=bar.bid,
        ask=bar.ask,
        bid_size=bar.bid_size,
        ask_size=bar.ask_size,
        security=bar.security,
        creator=bar.creator,
        volatility=bar.volatility,
        token_age_seconds=bar.token_age_seconds,
        market_condition=bar.market_condition,
    )


def _signal(item: HistoricalSignal) -> HistoricalSignal:
    if item.name not in {"entry", "exit"}:
        raise TradingValidationError("A historical signal name must be entry or exit.")
    reference = item.reference.strip()
    if not reference or len(reference) > 40 or not reference.replace("_", "").isalnum():
        raise TradingValidationError("A signal reference must be 1 to 40 letters, digits, or _.")
    _require_time(item.observed_at)
    return HistoricalSignal(require_mint(item.mint), item.observed_at, item.name, reference)


def _member(item: UniverseMember) -> UniverseMember:
    reason = item.reason.strip()
    if not reason or len(reason) > 80:
        raise TradingValidationError("A universe reason must be 1 to 80 characters.")
    return UniverseMember(require_mint(item.mint), item.included, reason)


def _require_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TradingValidationError("A historical timestamp must include a timezone.")


def _candle_time(value: int | None) -> datetime | None:
    if value is None or isinstance(value, bool) or value <= 0:
        return None
    seconds = value // 1000 if value >= 100_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _evidence_decimal(evidence: tuple[tuple[str, str], ...], name: str) -> Decimal | None:
    for key, raw in evidence:
        if key != name:
            continue
        try:
            parsed = Decimal(raw)
        except InvalidOperation:
            return None
        if parsed.is_finite() and parsed > 0:
            return parsed
    return None
