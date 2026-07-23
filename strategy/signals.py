"""
strategy/signals.py
===================
Moving average crossover signal generation.

Detects SMA crossovers and shifts signals by 1 bar to prevent look-ahead bias.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import pandas as pd

from strategy.config import StrategyConfig

logger = logging.getLogger(__name__)


def compute_moving_averages(
    close: pd.Series,
    fast_window: int,
    slow_window: int,
) -> Tuple[pd.Series, pd.Series]:
    """
    Compute simple moving averages (SMA) for fast and slow windows.

    ----------
    close : pd.Series
        Close price series with a DatetimeIndex.
    fast_window : int
        Lookback window for the fast (short) MA.
    slow_window : int
        Lookback window for the slow (long) MA.

    Returns
    -------
    Tuple[pd.Series, pd.Series]
        (fast_ma, slow_ma) — both aligned to the input index.
        NaN values at the start (before the window is filled) are preserved.
    """
    fast_ma = close.rolling(window=fast_window, min_periods=fast_window).mean()
    slow_ma = close.rolling(window=slow_window, min_periods=slow_window).mean()

    n_valid = (~slow_ma.isna()).sum()
    logger.debug(
        "MAs computed: fast=%d, slow=%d | Valid signal bars: %d / %d",
        fast_window, slow_window, n_valid, len(close)
    )

    return fast_ma, slow_ma


def generate_crossover_signals(
    close: pd.Series,
    config: StrategyConfig,
) -> pd.DataFrame:
    """
    Generate BUY/SELL signals from moving average crossovers.
    Golden Cross (+1): Fast MA crosses above Slow MA.
    Death Cross (-1): Fast MA crosses below Slow MA.

    ----------
    close : pd.Series
        Close price series with DatetimeIndex.
    config : StrategyConfig
        Strategy parameters (fast_window, slow_window, timeframe label).

    Returns
    -------
    pd.DataFrame
        Columns:
          close         — original close price
          fast_ma       — fast moving average
          slow_ma       — slow moving average
          fast_above    — bool: fast MA is above slow MA at this bar
          signal        — raw signal: +1 (golden cross), -1 (death cross), 0
          signal_shifted— signal shifted forward 1 bar (look-ahead prevention)
          position      — 1 (in market), 0 (flat) — lagged by 1 bar
    """
    logger.info(
        "Generating MA crossover signals [%s]: fast=%d, slow=%d",
        config.timeframe, config.fast_window, config.slow_window
    )

    fast_ma, slow_ma = compute_moving_averages(
        close, config.fast_window, config.slow_window
    )

    # Track when the fast MA crosses the slow MA.
    fast_above = fast_ma > slow_ma

    # Mark golden and death crosses.
    signal = pd.Series(0, index=close.index, dtype=int)
    golden_cross = fast_above & ~fast_above.shift(1, fill_value=False)  # False→True
    death_cross = ~fast_above & fast_above.shift(1, fill_value=False)   # True→False

    signal[golden_cross] = 1
    signal[death_cross] = -1

    # Shift signals one bar forward to avoid look-ahead bias.
    signal_shifted = signal.shift(1).fillna(0).astype(int)

    # Derive the position state from the shifted signal.
    raw_position = pd.Series(np.nan, index=close.index)
    raw_position[signal_shifted == 1] = 1.0   # BUY → enter long
    raw_position[signal_shifted == -1] = 0.0  # SELL → go flat

    # Hold the position until a new signal arrives.
    position = raw_position.ffill().fillna(0.0)

    # Keep the position flat during the warm-up period.
    warmup_mask = slow_ma.isna()
    position[warmup_mask] = 0.0
    signal[warmup_mask] = 0
    signal_shifted[warmup_mask] = 0

    # Assemble the final signal DataFrame.
    signals_df = pd.DataFrame(
        {
            "close": close,
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
            "fast_above": fast_above,
            "signal": signal,
            "signal_shifted": signal_shifted,
            "position": position,
        }
    )

    n_buy_signals = (signal == 1).sum()
    n_sell_signals = (signal == -1).sum()
    time_in_market = position.mean() * 100

    logger.info(
        "[%s] Signals: %d BUY, %d SELL | Time in market: %.1f%%",
        config.timeframe, n_buy_signals, n_sell_signals, time_in_market
    )

    return signals_df
