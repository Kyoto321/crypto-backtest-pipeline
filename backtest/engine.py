"""
backtest/engine.py
==================
Fully vectorised portfolio simulation.

Computes equity curves, drawdowns, and performance metrics by multiplying 
shifted positions by bar-by-bar market returns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.config import StrategyConfig

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """
    All outputs of a single backtest run.

    Structured as a dataclass so downstream modules (charts, metrics, report)
    each grab only the fields they need.
    """

    # Time series 
    equity_curve: pd.Series        # Portfolio value over time (in USDT)
    benchmark_curve: pd.Series     # Buy & Hold value over time (in USDT)
    strategy_returns: pd.Series    # Bar-by-bar strategy returns (fractional)
    benchmark_returns: pd.Series   # Bar-by-bar buy & hold returns (fractional)
    drawdown_series: pd.Series     # Running drawdown from peak (fraction, ≤ 0)
    position_series: pd.Series     # 1 = in market, 0 = flat

    # Strategy summary stats 
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    volatility_ann_pct: float
    time_in_market_pct: float

    # Buy & Hold summary stats 
    bh_total_return_pct: float
    bh_annualized_return_pct: float
    bh_sharpe_ratio: float
    bh_max_drawdown_pct: float
    bh_volatility_ann_pct: float

    # Config reference 
    config: StrategyConfig


def run_backtest(
    signals_df: pd.DataFrame,
    config: StrategyConfig,
) -> BacktestResult:
    """
    Simulate portfolio performance given a signals DataFrame.

    Parameters
    ----------
    signals_df : pd.DataFrame
        Output of strategy.signals.generate_crossover_signals().
        Must contain: close, position.
    config : StrategyConfig
        Provides initial_capital, timeframe, candles_per_year.

    Returns
    -------
    BacktestResult
        Complete simulation output including equity curves and summary metrics.
    """
    logger.info("Running backtest for [%s]...", config.timeframe)

    close = signals_df["close"]
    position = signals_df["position"]

    # Compute the raw bar-by-bar market returns.
    close_returns = close.pct_change().fillna(0.0)

    # Apply the current position to each bar's market return.
    strategy_returns = position * close_returns

    # Build the equity curves from cumulative growth.
    equity_curve = config.initial_capital * (1 + strategy_returns).cumprod()

    # Use the same market returns for the buy-and-hold baseline.
    benchmark_returns = close_returns
    benchmark_curve = config.initial_capital * (1 + benchmark_returns).cumprod()

    # Track drawdowns from each curve's rolling peak.
    drawdown_series = _compute_drawdown(equity_curve)
    bh_drawdown_series = _compute_drawdown(benchmark_curve)

    # Compute the summary statistics.
    n_candles = len(strategy_returns)
    cpyr = config.candles_per_year  # Candles Per Year for annualisation

    # Strategy stats
    total_return_pct = (equity_curve.iloc[-1] / config.initial_capital - 1) * 100
    ann_return_pct = _annualise_return(total_return_pct, n_candles, cpyr)
    sharpe = _compute_sharpe(strategy_returns, cpyr)
    max_dd_pct = drawdown_series.min() * 100  # already negative fraction
    vol_ann_pct = _annualise_volatility(strategy_returns, cpyr)
    time_in_market_pct = position.mean() * 100

    # Buy & Hold stats
    bh_total_return_pct = (benchmark_curve.iloc[-1] / config.initial_capital - 1) * 100
    bh_ann_return_pct = _annualise_return(bh_total_return_pct, n_candles, cpyr)
    bh_sharpe = _compute_sharpe(benchmark_returns, cpyr)
    bh_max_dd_pct = bh_drawdown_series.min() * 100
    bh_vol_ann_pct = _annualise_volatility(benchmark_returns, cpyr)

    # Log the key performance metrics.
    logger.info(
        "[%s] Strategy: Return=%.1f%% | Sharpe=%.2f | MaxDD=%.1f%% | "
        "Vol=%.1f%% | Time-in-market=%.1f%%",
        config.timeframe, total_return_pct, sharpe, max_dd_pct,
        vol_ann_pct, time_in_market_pct,
    )
    logger.info(
        "[%s] Buy&Hold: Return=%.1f%% | Sharpe=%.2f | MaxDD=%.1f%% | Vol=%.1f%%",
        config.timeframe, bh_total_return_pct, bh_sharpe,
        bh_max_dd_pct, bh_vol_ann_pct,
    )

    return BacktestResult(
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        drawdown_series=drawdown_series,
        position_series=position,
        total_return_pct=total_return_pct,
        annualized_return_pct=ann_return_pct,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd_pct,
        volatility_ann_pct=vol_ann_pct,
        time_in_market_pct=time_in_market_pct,
        bh_total_return_pct=bh_total_return_pct,
        bh_annualized_return_pct=bh_ann_return_pct,
        bh_sharpe_ratio=bh_sharpe,
        bh_max_drawdown_pct=bh_max_dd_pct,
        bh_volatility_ann_pct=bh_vol_ann_pct,
        config=config,
    )


# Helper functions 

def _compute_drawdown(equity: pd.Series) -> pd.Series:
    """
    Compute the running percentage drawdown from the rolling peak.
    Returns a Series of values ≤ 0.0.
    """
    rolling_peak = equity.cummax()
    drawdown = (equity - rolling_peak) / rolling_peak
    return drawdown


def _compute_sharpe(returns: pd.Series, candles_per_year: int) -> float:
    """
    Compute the annualised Sharpe ratio (assuming a 0% risk-free rate).
    """
    if returns.std() == 0 or len(returns) == 0:
        return 0.0
    mean_ret = returns.mean()
    std_ret = returns.std()
    return float((mean_ret / std_ret) * np.sqrt(candles_per_year))


def _annualise_return(total_return_pct: float, n_candles: int, cpyr: int) -> float:
    """
    Annualise a total return using the compound annual growth rate formula.

    CAGR = (1 + total_return) ^ (cpyr / n_candles) - 1

    This converts a 6-month return to its annual equivalent for fair
    comparison between datasets of different lengths.
    """
    if n_candles == 0:
        return 0.0
    years = n_candles / cpyr
    if years == 0:
        return 0.0
    total_return = total_return_pct / 100.0
    cagr = (1 + total_return) ** (1 / years) - 1
    return cagr * 100.0


def _annualise_volatility(returns: pd.Series, candles_per_year: int) -> float:
    """
    Annualise return volatility (standard deviation × sqrt(cpyr)).

    Returns the annualised volatility as a percentage.
    """
    return float(returns.std() * np.sqrt(candles_per_year) * 100)
