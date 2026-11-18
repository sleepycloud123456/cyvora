"""Honest historical import. Candle volume is stored as volume and not as depth."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from backtesting.history import _candle_time
from domain.exceptions import TradingValidationError
from domain.simulation import HistoricalBar, HistoricalDataset, UniverseMember
from domain.trading import MarketQuote
from integrations.gmgn.models import Candle
from integrations.solana.adapter import adapt_gmgn_candle, adapt_observation
from trading.instruments import require_mint

_COLUMNS = (
    "mint",
    "symbol",
    "observed_at",
    "source",
    "open",
    "high",
    "low",
    "close",
    "volume_quote",
    "base_volume",
    "base_reserve",
    "quote_reserve",
    "bid",
    "ask",
    "bid_size",
    "ask_size",
)
_MONEY = frozenset(_COLUMNS) - {"mint", "symbol", "observed_at", "source"}
_SECRET_WORDS = ("private", "seed", "password", "api_key", "secret", "mnemonic")
_VOLUME_NOTE = "candle_volume_is_not_executable_depth"
_CLOSE_NOTE = "candle_close_is_not_a_fill"


def dataset_from_csv(
    text: str,
    *,
    dataset_id: str,
    name: str,
    selection_note: str,
    source: str = "csv_import",
) -> HistoricalDataset:
    """Build a dataset from CSV text. A ``volume`` column is quote volume only."""

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise TradingValidationError("A CSV import needs a header row.")
    headers = [item.strip() for item in reader.fieldnames if item is not None]
    _reject_headers(headers)
    limitations = [_VOLUME_NOTE, _CLOSE_NOTE]
    volume_alias = "volume" in headers and "volume_quote" not in headers
    if volume_alias:
        limitations.append("csv_volume_was_stored_as_quote_volume")
    if "volume" in headers and "volume_quote" in headers:
        limitations.append("extra_volume_column_was_not_used_as_depth")
    bars = [
        _row_bar(row, headers, volume_alias=volume_alias, default_source=source) for row in reader
    ]
    return _dataset(dataset_id, name, source, selection_note, bars, limitations)


def dataset_from_parquet(
    payload: bytes,
    *,
    dataset_id: str,
    name: str,
    selection_note: str,
    source: str = "parquet_import",
) -> HistoricalDataset:
    """Build a dataset from a Parquet file. Binary-float money columns are rejected."""

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise TradingValidationError(
            "Parquet import needs pyarrow, which is not installed."
        ) from exc
    if not payload:
        raise TradingValidationError("The Parquet payload is empty.")
    try:
        table = pq.read_table(io.BytesIO(payload))
    except Exception as exc:
        raise TradingValidationError(
            f"The Parquet payload could not be read ({type(exc).__name__})."
        ) from None
    headers = [str(item) for item in table.column_names]
    _reject_headers(headers)
    for column_name in headers:
        if column_name in _MONEY or column_name == "volume":
            _reject_float(table.column(column_name).type, column_name)
    limitations = [_VOLUME_NOTE, _CLOSE_NOTE]
    volume_alias = "volume" in headers and "volume_quote" not in headers
    if volume_alias:
        limitations.append("parquet_volume_was_stored_as_quote_volume")
    if "volume" in headers and "volume_quote" in headers:
        limitations.append("extra_volume_column_was_not_used_as_depth")
    bars: list[HistoricalBar] = []
    for index in range(table.num_rows):
        row = {column_name: _cell(table.column(column_name), index) for column_name in headers}
        bars.append(_row_bar(row, headers, volume_alias=volume_alias, default_source=source))
    return _dataset(dataset_id, name, source, selection_note, bars, limitations)


def dataset_from_gmgn_candles(
    candles: list[Candle] | tuple[Candle, ...],
    *,
    mint: str,
    symbol: str,
    dataset_id: str,
    name: str,
    selection_note: str,
    supplied: bool,
) -> HistoricalDataset:
    """Map read-only GMGN candles. Volume stays volume. Reserves stay empty.

    ``supplied`` is true when the caller already held the candles. A live
    collection sets it false. Neither path copies volume into depth.
    """

    limitations = [
        _VOLUME_NOTE,
        _CLOSE_NOTE,
        "gmgn_candle_volume_is_not_base_size",
        "gmgn_kline_has_no_reserve_pair",
    ]
    if supplied:
        limitations.append("candles_were_supplied_with_the_request")
    else:
        limitations.append("candles_were_read_from_gmgn_kline")
    checked = require_mint(mint)
    label = symbol.strip() or "TOKEN"
    bars: list[HistoricalBar] = []
    for candle in candles:
        observed = _candle_time(candle.time)
        if observed is None:
            limitations.append("candle_time_missing")
            continue
        quote = adapt_gmgn_candle(checked, candle, observed)
        bars.append(bar_from_quote(quote, symbol=label))
    return _dataset(dataset_id, name, "gmgn_kline", selection_note, bars, limitations)


def dataset_from_observations(
    observations: list[MarketQuote] | tuple[MarketQuote, ...],
    *,
    dataset_id: str,
    name: str,
    selection_note: str,
    symbol: str,
) -> HistoricalDataset:
    """Map adapter quotes the caller already has. This does not call an RPC."""

    limitations = [
        _VOLUME_NOTE,
        _CLOSE_NOTE,
        "adapter_quotes_were_supplied",
        "a_single_liquidity_figure_is_not_a_reserve_pair",
    ]
    label = symbol.strip() or "TOKEN"
    bars = [bar_from_quote(item, symbol=label) for item in observations]
    return _dataset(dataset_id, name, "solana_adapter", selection_note, bars, limitations)


def observation_from_parts(
    mint: str,
    observed_at: datetime,
    *,
    source: str,
    bid: Decimal | None = None,
    ask: Decimal | None = None,
    bid_size: Decimal | None = None,
    ask_size: Decimal | None = None,
    last_price: Decimal | None = None,
    volume: Decimal | None = None,
    open_price: Decimal | None = None,
    high: Decimal | None = None,
    low: Decimal | None = None,
    close: Decimal | None = None,
    size_is_base: bool = False,
) -> MarketQuote:
    """Adapt one supplied observation. Volume is not written into the book."""

    return adapt_observation(
        mint,
        observed_at,
        source=source,
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        last_price=last_price,
        volume=volume,
        open_price=open_price,
        high=high,
        low=low,
        close=close,
        size_is_base=size_is_base,
    )


def bar_from_quote(quote: MarketQuote, *, symbol: str) -> HistoricalBar:
    """Copy a market quote onto a bar. Volume never becomes a reserve or a size."""

    if quote.size_is_base:
        base_volume = quote.last_size if quote.last_size is not None else quote.volume
        volume_quote = None
    else:
        base_volume = None
        volume_quote = quote.volume
    close = quote.close if quote.close is not None else quote.last_price
    return HistoricalBar(
        mint=quote.mint,
        symbol=symbol[:32] or "TOKEN",
        observed_at=quote.observed_at,
        source=quote.source[:40],
        open=quote.open,
        high=quote.high,
        low=quote.low,
        close=close,
        volume_quote=volume_quote,
        base_volume=base_volume,
        base_reserve=None,
        quote_reserve=None,
        bid=quote.bid,
        ask=quote.ask,
        bid_size=quote.bid_size,
        ask_size=quote.ask_size,
    )


def _dataset(
    dataset_id: str,
    name: str,
    source: str,
    selection_note: str,
    bars: list[HistoricalBar],
    limitations: list[str],
) -> HistoricalDataset:
    mints = list(dict.fromkeys(bar.mint for bar in bars))
    members = tuple(UniverseMember(mint, True, "Present in the imported rows.") for mint in mints)
    return HistoricalDataset(
        dataset_id=dataset_id,
        name=name,
        source=source,
        selection_note=selection_note,
        bars=tuple(bars),
        signals=(),
        members=members,
        limitations=tuple(dict.fromkeys(limitations)),
    )


def _row_bar(
    row: dict[str, str | None],
    headers: list[str],
    *,
    volume_alias: bool,
    default_source: str,
) -> HistoricalBar:
    mint = _text(row.get("mint"))
    if mint is None:
        raise TradingValidationError("Each imported row needs a mint.")
    symbol = _text(row.get("symbol")) or "TOKEN"
    observed = _moment(_text(row.get("observed_at")))
    source = _text(row.get("source")) or default_source
    volume_quote = _money(row.get("volume_quote"))
    if volume_alias:
        volume_quote = _money(row.get("volume"))
    return HistoricalBar(
        mint=mint,
        symbol=symbol,
        observed_at=observed,
        source=source,
        open=_money(row.get("open")),
        high=_money(row.get("high")),
        low=_money(row.get("low")),
        close=_money(row.get("close")),
        volume_quote=volume_quote,
        base_volume=_money(row.get("base_volume")),
        base_reserve=_money(row.get("base_reserve")),
        quote_reserve=_money(row.get("quote_reserve")),
        bid=_money(row.get("bid")),
        ask=_money(row.get("ask")),
        bid_size=_money(row.get("bid_size")),
        ask_size=_money(row.get("ask_size")),
    )


def _reject_headers(headers: list[str]) -> None:
    if "mint" not in headers or "observed_at" not in headers:
        raise TradingValidationError("An import needs mint and observed_at columns.")
    for header in headers:
        lowered = header.lower()
        if any(word in lowered for word in _SECRET_WORDS):
            raise TradingValidationError("An import column cannot be named like a secret.")


def _reject_float(arrow_type: object, column_name: str) -> None:
    import pyarrow as pa

    if pa.types.is_floating(arrow_type):
        raise TradingValidationError(
            f"Parquet column {column_name} is a binary float. Money columns must be strings "
            "or decimals."
        )


def _cell(column: object, index: int) -> str | None:
    value = column[index].as_py()  # type: ignore[index]
    if value is None:
        return None
    if isinstance(value, bool):
        raise TradingValidationError("A parquet boolean is not a market value.")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    raise TradingValidationError("A parquet value must be a string, integer, or decimal.")


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _money(value: str | None) -> Decimal | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise TradingValidationError("An imported amount must be a decimal string.") from exc
    if not parsed.is_finite() or parsed < 0:
        raise TradingValidationError("An imported amount must be finite and cannot be negative.")
    return parsed


def _moment(value: str | None) -> datetime:
    if value is None:
        raise TradingValidationError("Each imported row needs observed_at.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TradingValidationError("observed_at must be ISO-8601.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TradingValidationError("observed_at must include a timezone.")
    return parsed
