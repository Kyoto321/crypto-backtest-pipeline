"""
strategy/positions.py
=====================
Converts raw crossover signals into trade records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """
    A single completed round-trip trade (entry + exit).
    """

    trade_id: int
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    holding_bars: int
    return_pct: float
    exit_reason: str

    @property
    def is_winner(self) -> bool:
        return self.return_pct > 0

    @property
    def profit_loss_usd(self) -> float:
        """Absolute P&L assuming $1 per unit (multiply by capital externally)."""
        return self.return_pct / 100.0


def extract_trades(signals_df: pd.DataFrame, timeframe: str) -> List[TradeRecord]:
    """
    Extract individual trade records from the signals DataFrame.

    Parameters
    ----------
    signals_df : pd.DataFrame
        Output of strategy.signals.generate_crossover_signals().
        Must contain columns: position, close, signal_shifted.
    timeframe : str
        Used for log messages only.

    Returns
    -------
    List[TradeRecord]
        Chronologically ordered list of completed trades.
    """
    trades: List[TradeRecord] = []
    trade_id = 0

    in_trade: bool = False
    entry_time: Optional[pd.Timestamp] = None
    entry_price: Optional[float] = None
    entry_bar_idx: Optional[int] = None

    position = signals_df["position"]
    close = signals_df["close"]

    for bar_idx, (timestamp, pos) in enumerate(position.items()):

        if not in_trade and pos == 1.0:
            # ── ENTRY ──────────────────────────────────────────────────────────
            in_trade = True
            entry_time = timestamp
            entry_price = close[timestamp]
            entry_bar_idx = bar_idx

        elif in_trade and pos == 0.0:
            # ── EXIT (signal-driven) ───────────────────────────────────────────
            exit_time = timestamp
            exit_price = close[timestamp]
            holding_bars = bar_idx - entry_bar_idx
            return_pct = (exit_price - entry_price) / entry_price * 100

            trade_id += 1
            trades.append(TradeRecord(
                trade_id=trade_id,
                entry_time=entry_time,
                exit_time=exit_time,
                entry_price=entry_price,
                exit_price=exit_price,
                holding_bars=holding_bars,
                return_pct=return_pct,
                exit_reason="DEATH_CROSS",
            ))

            in_trade = False
            entry_time = None
            entry_price = None
            entry_bar_idx = None

    # ── Handle open trade at end of data ──────────────────────────────────────
    if in_trade and entry_time is not None:
        last_timestamp = signals_df.index[-1]
        exit_price = close[last_timestamp]
        holding_bars = len(signals_df) - 1 - entry_bar_idx
        return_pct = (exit_price - entry_price) / entry_price * 100

        trade_id += 1
        trades.append(TradeRecord(
            trade_id=trade_id,
            entry_time=entry_time,
            exit_time=last_timestamp,
            entry_price=entry_price,
            exit_price=exit_price,
            holding_bars=holding_bars,
            return_pct=return_pct,
            exit_reason="END_OF_DATA",
        ))
        logger.info(
            "[%s] Trade #%d still open at end of data — closed at last bar ($%.2f).",
            timeframe, trade_id, exit_price,
        )

    logger.info(
        "[%s] Extracted %d completed trade(s).", timeframe, len(trades)
    )
    return trades
