"""Dataset quality. Candle volume is never counted as executable depth."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median

from domain.simulation import DatasetQuality, HistoricalBar, HistoricalDataset, QualityFinding

_FINDING_CAP = 40
_VOLUME_LIMITATION = "candle_volume_is_not_executable_depth"
_CLOSE_LIMITATION = "candle_close_is_not_a_fill"


def bar_fill_kind(bar: HistoricalBar) -> str:
    """Return ``reserve``, ``depth``, or ``none``.

    Quote volume does not make a bar fillable. A close does not either.
    """

    if _positive(bar.base_reserve) and _positive(bar.quote_reserve):
        return "reserve"
    if (
        _positive(bar.bid)
        and _positive(bar.ask)
        and _positive(bar.bid_size)
        and _positive(bar.ask_size)
    ):
        return "depth"
    return "none"


def validate_quality(
    dataset: HistoricalDataset,
    *,
    checked_at: datetime,
    expected_interval_seconds: int | None = None,
    stale_after_seconds: int = 900,
    outlier_return: Decimal = Decimal(5),
) -> DatasetQuality:
    """Measure gaps, staleness, outliers, and fill availability.

    The report does not drop bars and does not turn volume into a pool.
    """

    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        from domain.exceptions import TradingValidationError

        raise TradingValidationError("A quality check needs a timezone-aware time.")
    if stale_after_seconds < 1:
        from domain.exceptions import TradingValidationError

        raise TradingValidationError("The staleness window must be at least one second.")
    if outlier_return <= 0 or not outlier_return.is_finite():
        from domain.exceptions import TradingValidationError

        raise TradingValidationError("The outlier return must be a positive finite decimal.")
    if expected_interval_seconds is not None and expected_interval_seconds < 1:
        from domain.exceptions import TradingValidationError

        raise TradingValidationError("The expected bar interval must be at least one second.")

    findings: list[QualityFinding] = []
    grouped: dict[str, list[HistoricalBar]] = {}
    for bar in dataset.bars:
        grouped.setdefault(bar.mint, []).append(bar)
    gap_count = 0
    outlier_count = 0
    reserve_count = 0
    depth_count = 0
    volume_only = 0
    inferred = expected_interval_seconds is None
    for mint, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: item.observed_at)
        interval = expected_interval_seconds
        if interval is None:
            interval = _infer_interval(ordered)
        if interval is None:
            inferred = True
        else:
            inferred = inferred and expected_interval_seconds is None
            gap_count += _gaps(mint, ordered, interval, findings)
        outlier_count += _outliers(mint, ordered, outlier_return, findings)
        for bar in ordered:
            kind = bar_fill_kind(bar)
            if kind == "reserve":
                reserve_count += 1
            elif kind == "depth":
                depth_count += 1
            elif bar.volume_quote is not None:
                volume_only += 1
                _add(
                    findings,
                    QualityFinding(
                        "not_fillable",
                        mint,
                        bar.observed_at,
                        "Quote volume is stored and is not executable depth.",
                    ),
                )
    last = max((bar.observed_at for bar in dataset.bars), default=None)
    stale = last is not None and checked_at - last > timedelta(seconds=stale_after_seconds)
    if stale and last is not None:
        _add(
            findings,
            QualityFinding(
                "stale",
                "",
                last,
                "The last bar is older than the staleness window at the check time.",
            ),
        )
    limitations = [_VOLUME_LIMITATION, _CLOSE_LIMITATION]
    if inferred and expected_interval_seconds is None and dataset.bars:
        limitations.append("bar_interval_was_inferred_when_a_median_existed")
    if volume_only:
        limitations.append("volume_only_bars_cannot_fill")
    if not dataset.bars:
        limitations.append("no_bars")
    return DatasetQuality(
        dataset_id=dataset.dataset_id,
        checked_at=checked_at,
        bar_count=len(dataset.bars),
        mint_count=len(grouped),
        gap_count=gap_count,
        stale=stale,
        outlier_count=outlier_count,
        fillable_bar_count=reserve_count + depth_count,
        reserve_bar_count=reserve_count,
        depth_bar_count=depth_count,
        volume_only_bar_count=volume_only,
        limitations=tuple(dict.fromkeys(limitations)),
        findings=tuple(findings[:_FINDING_CAP]),
        live_trading_enabled=False,
    )


def _positive(value: Decimal | None) -> bool:
    return value is not None and value.is_finite() and value > 0


def _infer_interval(rows: list[HistoricalBar]) -> int | None:
    if len(rows) < 3:
        return None
    deltas = [
        (later.observed_at - earlier.observed_at).total_seconds()
        for earlier, later in zip(rows, rows[1:], strict=False)
    ]
    positive = [item for item in deltas if item > 0]
    if len(positive) < 2:
        return None
    chosen = int(median(positive))
    return chosen if chosen >= 1 else None


def _gaps(
    mint: str,
    rows: list[HistoricalBar],
    interval: int,
    findings: list[QualityFinding],
) -> int:
    count = 0
    limit = interval * 1.5
    for earlier, later in zip(rows, rows[1:], strict=False):
        delta = (later.observed_at - earlier.observed_at).total_seconds()
        if delta > limit:
            count += 1
            _add(
                findings,
                QualityFinding(
                    "gap",
                    mint,
                    later.observed_at,
                    f"The gap is {int(delta)} seconds against an interval of {interval}.",
                ),
            )
    return count


def _outliers(
    mint: str,
    rows: list[HistoricalBar],
    outlier_return: Decimal,
    findings: list[QualityFinding],
) -> int:
    count = 0
    previous: Decimal | None = None
    for bar in rows:
        if _inconsistent(bar):
            count += 1
            _add(
                findings,
                QualityFinding(
                    "outlier",
                    mint,
                    bar.observed_at,
                    "The high, low, and close are inconsistent.",
                ),
            )
        close = bar.close
        if previous is not None and close is not None and previous > 0 and close > 0:
            change = abs(close - previous) / previous
            if change > outlier_return:
                count += 1
                _add(
                    findings,
                    QualityFinding(
                        "outlier",
                        mint,
                        bar.observed_at,
                        "The close-to-close move exceeds the outlier return.",
                    ),
                )
        if close is not None and close > 0:
            previous = close
    return count


def _inconsistent(bar: HistoricalBar) -> bool:
    if bar.high is not None and bar.low is not None and bar.high < bar.low:
        return True
    if bar.close is None or bar.high is None or bar.low is None:
        return False
    return bar.close > bar.high or bar.close < bar.low


def _add(findings: list[QualityFinding], finding: QualityFinding) -> None:
    if len(findings) < _FINDING_CAP:
        findings.append(finding)
