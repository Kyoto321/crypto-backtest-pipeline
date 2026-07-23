"""
reporting/trade_log.py
======================
Generates a structured, human-readable trade-by-trade P&L log.

Export format: CSV (easy to open in Excel/Sheets for the reviewer)

Design decision: calculate P&L in dollar terms
-----------------------------------------------
Raw percentage returns are hard to interpret in isolation.
By combining them with the initial capital, we give the reviewer
absolute dollar figures — much more concrete when evaluating
"did this strategy make money?"

We also compute holding duration in hours (not just bars) so
the log is useful across both 1h and 4h timeframes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd

from strategy.positions import TradeRecord
from strategy.config import StrategyConfig, LOGS_DIR

logger = logging.getLogger(__name__)


def build_trade_log_dataframe(
    trades: List[TradeRecord],
    config: StrategyConfig,
    candle_hours: int,
) -> pd.DataFrame:
    """
    Convert a list of TradeRecord objects to a structured DataFrame.

    Parameters
    ----------
    trades : List[TradeRecord]
        Completed trades from strategy.positions.extract_trades().
    config : StrategyConfig
        Provides initial_capital and timeframe label.
    candle_hours : int
        Number of hours in one candle (1 for 1h, 4 for 4h).

    Returns
    -------
    pd.DataFrame
        One row per trade with all relevant columns.
    """
    if not trades:
        logger.warning("[%s] No trades to log.", config.timeframe)
        return pd.DataFrame()

    records = []
    cumulative_capital = config.initial_capital

    for trade in trades:
        # Dollar P&L based on cumulative capital at time of entry
        pnl_usd = cumulative_capital * (trade.return_pct / 100.0)
        exit_capital = cumulative_capital + pnl_usd
        holding_hours = trade.holding_bars * candle_hours

        records.append({
            "trade_id": trade.trade_id,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "entry_price_usd": round(trade.entry_price, 2),
            "exit_price_usd": round(trade.exit_price, 2),
            "holding_bars": trade.holding_bars,
            "holding_hours": holding_hours,
            "holding_days": round(holding_hours / 24, 1),
            "return_pct": round(trade.return_pct, 4),
            "profit_loss_usd": round(pnl_usd, 2),
            "capital_after_trade_usd": round(exit_capital, 2),
            "outcome": "WIN" if trade.return_pct > 0 else "LOSS",
            "exit_reason": trade.exit_reason,
        })

        cumulative_capital = exit_capital  # compound the returns

    df = pd.DataFrame(records)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])

    logger.info(
        "[%s] Trade log built: %d trades | Final capital: $%s",
        config.timeframe, len(df), f"{cumulative_capital:,.2f}",
    )
    return df


def export_trade_log(
    trades: List[TradeRecord],
    config: StrategyConfig,
    candle_hours: int,
) -> Path:
    """
    Build and export the trade log to CSV.

    Parameters
    ----------
    trades : List[TradeRecord]
        Completed trades.
    config : StrategyConfig
        Strategy configuration.
    candle_hours : int
        Hours per candle (1 or 4).

    Returns
    -------
    Path
        Path to the exported CSV file.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    df = build_trade_log_dataframe(trades, config, candle_hours)

    if df.empty:
        logger.warning("[%s] Empty trade log — no CSV written.", config.timeframe)
        return LOGS_DIR / f"trade_log_{config.timeframe}_EMPTY.csv"

    output_path = LOGS_DIR / f"trade_log_{config.timeframe}.csv"
    df.to_csv(output_path, index=False)
    logger.info("Trade log exported: %s", output_path)

    return output_path
