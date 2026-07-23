"""
data/validator.py
=================
Additional data quality checks beyond basic schema validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

import pandas as pd
import numpy as np

from data.loader import CleanDataset

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """
    Results of all data quality checks.
    """

    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.passed = False
        logger.error("DATA ERROR: %s", msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning("DATA WARNING: %s", msg)

    def log_summary(self) -> None:
        status = "PASSED" if self.passed else "FAILED"
        logger.info(
            "Validation [%s] — %d error(s), %d warning(s)",
            status, len(self.errors), len(self.warnings)
        )


def validate_dataset(dataset: CleanDataset) -> ValidationReport:
    """
    Run all quality checks on a CleanDataset.

    Parameters
    ----------
    dataset : CleanDataset
        Output of data.loader.load_klines()

    Returns
    -------
    ValidationReport
        Structured report with errors and warnings.
    """
    report = ValidationReport()
    df = dataset.df
    tf = dataset.timeframe

    logger.info("Running data validation for [%s]...", tf)

    _check_monotonic_index(df, tf, report)
    _check_ohlc_logic(df, tf, report)
    _check_zero_volume(df, tf, report)
    _check_price_spikes(df, tf, report)
    _check_sufficient_data(df, tf, report)
    _check_expected_frequency(df, tf, report)

    report.log_summary()
    return report


def _check_monotonic_index(
    df: pd.DataFrame, tf: str, report: ValidationReport
) -> None:
    """Verify timestamps are strictly monotonically increasing."""
    if not df.index.is_monotonic_increasing:
        report.add_error(
            f"[{tf}] Timestamps are not monotonically increasing. "
            "This would cause incorrect MA calculations and must be fixed."
        )


def _check_ohlc_logic(
    df: pd.DataFrame, tf: str, report: ValidationReport
) -> None:
    """
    Verify OHLC relationships are physically valid.
    High must be >= Open, Close, Low.
    Low must be <= Open, Close, High.
    """
    invalid_high = (df["high"] < df[["open", "close", "low"]].max(axis=1)).sum()
    invalid_low = (df["low"] > df[["open", "close", "high"]].min(axis=1)).sum()

    if invalid_high > 0:
        report.add_error(
            f"[{tf}] {invalid_high} candles have high < max(open, close, low). "
            "This is physically impossible and suggests data corruption."
        )
    if invalid_low > 0:
        report.add_error(
            f"[{tf}] {invalid_low} candles have low > min(open, close, high). "
            "This is physically impossible and suggests data corruption."
        )


def _check_zero_volume(
    df: pd.DataFrame, tf: str, report: ValidationReport
) -> None:
    """Detect zero-volume candles (may indicate exchange outage or stale data)."""
    zero_vol = (df["volume"] == 0).sum()
    if zero_vol > 0:
        pct = zero_vol / len(df) * 100
        report.add_warning(
            f"[{tf}] {zero_vol} candles ({pct:.1f}%) have zero volume. "
            "These may represent exchange downtime and could affect signal quality."
        )


def _check_price_spikes(
    df: pd.DataFrame, tf: str, report: ValidationReport
) -> None:
    """
    Flag candles where the close-to-close return exceeds 30%.
    Legitimate for crypto but worth flagging — may be flash crash / spike.
    """
    returns = df["close"].pct_change().abs()
    spikes = (returns > 0.30).sum()
    if spikes > 0:
        spike_dates = df.index[returns > 0.30].tolist()
        report.add_warning(
            f"[{tf}] {spikes} candle(s) show >30% close-to-close move: "
            f"{[str(d.date()) for d in spike_dates[:3]]}{'...' if spikes > 3 else ''}. "
            "Verify these are real market events, not data errors."
        )


def _check_sufficient_data(
    df: pd.DataFrame, tf: str, report: ValidationReport
) -> None:
    """
    Verify there are enough candles to compute the slow MA.
    We need at least slow_window + 1 rows to generate even a single signal.
    Using a generous minimum of 100 candles.
    """
    min_required = 100
    if len(df) < min_required:
        report.add_error(
            f"[{tf}] Only {len(df)} candles loaded — need at least {min_required}. "
            "Cannot generate reliable signals with this few data points."
        )


def _check_expected_frequency(
    df: pd.DataFrame, tf: str, report: ValidationReport
) -> None:
    """
    Check that the median gap between candles matches the expected timeframe.
    A large deviation suggests missing candles or data gaps.
    """
    expected_hours = {"1h": 1, "4h": 4, "1d": 24}.get(tf)
    if expected_hours is None:
        return  # Unknown timeframe — skip this check

    time_diffs = df.index.to_series().diff().dt.total_seconds() / 3600
    median_gap = time_diffs.median()
    max_gap = time_diffs.max()

    if abs(median_gap - expected_hours) > 0.01:
        report.add_warning(
            f"[{tf}] Median candle gap is {median_gap:.2f}h, expected {expected_hours}h. "
            "There may be missing candles."
        )

    if max_gap > expected_hours * 3:
        report.add_warning(
            f"[{tf}] Largest gap between candles is {max_gap:.1f}h "
            f"({max_gap/expected_hours:.1f}× the expected interval). "
            "There is a significant data gap in the series — likely an exchange outage."
        )
