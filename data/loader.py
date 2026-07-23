"""
data/loader.py
==============
Loads, validates, cleans, and type-casts Binance kline (candlestick) CSV data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

#  Expected Binance kline columns 
BINANCE_KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]

# Columns to cast to float64 (Binance ships these as strings with 8 d.p.)
FLOAT_COLUMNS = [
    "open", "high", "low", "close",
    "volume", "quote_volume",
    "taker_buy_base_volume", "taker_buy_quote_volume",
]

# Columns to cast to int64
INT_COLUMNS = ["trades"]

# Columns we do not need — remove to keep memory clean
COLUMNS_TO_DROP = ["ignore", "close_time"]


@dataclass
class CleanDataset:
    """
    The validated, type-cast output of the loader.
    """

    df: pd.DataFrame
    timeframe: str
    source_path: Path
    n_rows: int
    date_start: pd.Timestamp
    date_end: pd.Timestamp
    missing_value_report: dict

    def summary(self) -> str:
        """Return a human-readable one-line summary of this dataset."""
        return (
            f"[{self.timeframe}] {self.n_rows} candles | "
            f"{self.date_start.date()} → {self.date_end.date()} | "
            f"source: {self.source_path.name}"
        )


def load_klines(
    filepath: Path | str,
    timeframe: str,
    tz: Optional[str] = "UTC",
) -> CleanDataset:
    """
    Load a Binance kline CSV into a clean, validated CleanDataset.

    Parameters
    ----------
    filepath : Path | str
        Path to the CSV file.
    timeframe : str
        Human-readable label for log output and downstream identification.
        e.g. "1h", "4h".
    tz : str, optional
        Timezone for the DatetimeIndex. Binance exports UTC. Default: "UTC".

    Returns
    -------
    CleanDataset
        Validated, type-cast dataset ready for strategy consumption.

    Raises
    ------
    FileNotFoundError
        If the CSV file does not exist at the given path.
    ValueError
        If the CSV does not match the expected Binance kline schema.
    """
    filepath = Path(filepath)
    logger.info("Loading %s kline data from: %s", timeframe, filepath)

    # 1. File existence check 
    if not filepath.exists():
        raise FileNotFoundError(
            f"Data file not found: {filepath}\n"
            "Ensure the CSV files are in the project root directory."
        )

    # 2. Load CSV 
    # We do NOT use dtype= here intentionally: we want to inspect the raw
    # data first, then cast deliberately. This catches unexpected schema changes.
    raw_df = pd.read_csv(filepath, header=0)
    logger.info("Raw load: %d rows, %d columns", len(raw_df), len(raw_df.columns))

    # 3. Schema validation 
    _validate_schema(raw_df, filepath)

    # 4. Type casting 
    df = _cast_types(raw_df, tz=tz)

    # 5. Drop unnecessary columns 
    cols_present = [c for c in COLUMNS_TO_DROP if c in df.columns]
    df = df.drop(columns=cols_present)

    # 6. Sort by time (defensive — Binance files are usually sorted) 
    df = df.sort_index()

    #  7. Duplicate index check 
    n_dupes = df.index.duplicated().sum()
    if n_dupes > 0:
        logger.warning(
            "Found %d duplicate timestamps in %s — keeping first occurrence.",
            n_dupes, filepath.name
        )
        df = df[~df.index.duplicated(keep="first")]

    # ── 8. Missing value audit
    missing = df.isnull().sum().to_dict()
    total_missing = sum(missing.values())
    if total_missing > 0:
        logger.warning(
            "Missing values detected in %s: %s",
            filepath.name,
            {k: v for k, v in missing.items() if v > 0},
        )
    else:
        logger.info("No missing values found in %s.", filepath.name)

    # 9. Derive buy pressure ratio (bonus column — useful for analysis) 
    # buy_pressure = taker_buy_base_volume / volume
    # Represents the fraction of volume initiated by aggressive buyers.
    # Values > 0.5 indicate buying pressure; < 0.5 indicate selling pressure.
    if "taker_buy_base_volume" in df.columns and "volume" in df.columns:
        df["buy_pressure"] = np.where(
            df["volume"] > 0,
            df["taker_buy_base_volume"] / df["volume"],
            np.nan,
        )

    # 10. Build CleanDataset 
    dataset = CleanDataset(
        df=df,
        timeframe=timeframe,
        source_path=filepath.resolve(),
        n_rows=len(df),
        date_start=df.index[0],
        date_end=df.index[-1],
        missing_value_report=missing,
    )

    logger.info("OK: %s", dataset.summary())
    _log_schema_info(df, timeframe)

    return dataset


def _validate_schema(df: pd.DataFrame, filepath: Path) -> None:
    """
    Verify the loaded DataFrame matches the expected Binance kline schema.

    This is defensive programming: if Binance changes their export format
    in a future API version, this catches it immediately with a clear message.
    """
    actual_cols = set(df.columns.str.lower())
    expected_cols = set(BINANCE_KLINE_COLUMNS)

    missing_cols = expected_cols - actual_cols
    if missing_cols:
        raise ValueError(
            f"Schema mismatch in {filepath.name}.\n"
            f"Expected columns: {sorted(expected_cols)}\n"
            f"Missing from file: {sorted(missing_cols)}\n"
            "This may indicate a non-standard or modified export."
        )

    logger.debug("Schema validation passed for %s.", filepath.name)


def _cast_types(df: pd.DataFrame, tz: Optional[str] = "UTC") -> pd.DataFrame:
    """
    Cast all columns to their correct Python/pandas types.

    Binance kline CSVs export:
      - Timestamps: strings like "2026-01-01 00:00:00"
      - Prices/volumes: strings like "87648.21000000" (8 decimal places)
      - trades: integer (sometimes read as float due to mixed types)
      - ignore: integer 0

    Why not use pd.read_csv(dtype=...)?
    Using dtype= can silently coerce errors. Explicit casting here lets us
    catch unexpected data and log a clear warning.
    """
    df = df.copy()

    #  Datetime index 
    # Use open_time as the index — it uniquely identifies each candle.
    # We parse it, localise to UTC, then set as index.
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.set_index("open_time")
    df.index.name = "open_time"

    # Parse close_time too (we'll drop it later, but it's useful for validation)
    if "close_time" in df.columns:
        df["close_time"] = pd.to_datetime(df["close_time"], utc=True)

    # Float columns 
    for col in FLOAT_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    # Integer columns
    for col in INT_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    return df


def _log_schema_info(df: pd.DataFrame, timeframe: str) -> None:
    """Log a structured summary of the loaded DataFrame for transparency."""
    logger.info(
        "[%s] DataFrame shape: %s | Price range: $%.2f – $%.2f | "
        "Avg daily volume: %.1f BTC",
        timeframe,
        df.shape,
        df["close"].min(),
        df["close"].max(),
        df["volume"].mean() * _candles_per_day(timeframe),
    )


def _candles_per_day(timeframe: str) -> int:
    """Return how many candles make up one calendar day for a given timeframe."""
    mapping = {"1h": 24, "4h": 6, "1d": 1, "15m": 96, "5m": 288}
    return mapping.get(timeframe, 1)
