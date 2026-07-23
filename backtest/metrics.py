"""
backtest/metrics.py
===================
Aggregates trade-level statistics from a list of TradeRecords.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

from strategy.positions import TradeRecord

logger = logging.getLogger(__name__)


@dataclass
class TradeStatistics:
    """
    Aggregated statistics across all completed trades.
    """

    n_trades: int
    n_winners: int
    n_losers: int
    win_rate_pct: float
    avg_return_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    payoff_ratio: float
    best_trade_pct: float
    worst_trade_pct: float
    avg_holding_bars: float
    total_return_pct: float


def compute_trade_statistics(
    trades: List[TradeRecord],
    timeframe: str,
) -> TradeStatistics:
    """
    Compute aggregated statistics over a list of completed trades.

    Parameters
    ----------
    trades : List[TradeRecord]
        Output of strategy.positions.extract_trades().
    timeframe : str
        Used for log messages only.

    Returns
    -------
    TradeStatistics
        Summary statistics over all trades.
    """
    if not trades:
        logger.warning("[%s] No trades found — returning empty statistics.", timeframe)
        return TradeStatistics(
            n_trades=0, n_winners=0, n_losers=0,
            win_rate_pct=0.0, avg_return_pct=0.0,
            avg_win_pct=0.0, avg_loss_pct=0.0,
            payoff_ratio=0.0, best_trade_pct=0.0,
            worst_trade_pct=0.0, avg_holding_bars=0.0,
            total_return_pct=0.0,
        )

    returns = [t.return_pct for t in trades]
    winners = [r for r in returns if r > 0]
    losers = [r for r in returns if r <= 0]

    avg_win = float(np.mean(winners)) if winners else 0.0
    avg_loss = float(np.mean(losers)) if losers else 0.0

    # Compare average wins to average losses.
    payoff_ratio = abs(avg_win) / abs(avg_loss) if avg_loss != 0 else float("inf")

    # Use compounded growth for a realistic total return.
    total_return = (
        np.prod([1 + r / 100.0 for r in returns]) - 1
    ) * 100

    stats = TradeStatistics(
        n_trades=len(trades),
        n_winners=len(winners),
        n_losers=len(losers),
        win_rate_pct=len(winners) / len(trades) * 100,
        avg_return_pct=float(np.mean(returns)),
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        payoff_ratio=payoff_ratio,
        best_trade_pct=max(returns),
        worst_trade_pct=min(returns),
        avg_holding_bars=float(np.mean([t.holding_bars for t in trades])),
        total_return_pct=float(total_return),
    )

    logger.info(
        "[%s] Trade stats: %d trades | Win rate: %.1f%% | "
        "Avg win: %.1f%% | Avg loss: %.1f%% | Payoff ratio: %.2f",
        timeframe,
        stats.n_trades, stats.win_rate_pct,
        stats.avg_win_pct, stats.avg_loss_pct, stats.payoff_ratio,
    )

    return stats
