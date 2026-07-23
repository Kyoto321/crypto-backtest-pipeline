"""
main.py
=======
Orchestrator for the Ark Capital backtest pipeline.

Coordinates data loading, signal generation, backtesting, and reporting.
Run with: python main.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make the project root importable when running from any directory.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Use UTF-8 output for Windows console compatibility.
if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── Imports ──────────────────────────────────────────────────────────────────
from strategy.config import ALL_CONFIGS, DATA_FILES, OUTPUT_DIR, CONFIG_1H, CONFIG_4H
from data.loader import load_klines
from data.validator import validate_dataset
from strategy.signals import generate_crossover_signals
from strategy.positions import extract_trades
from backtest.engine import run_backtest
from backtest.metrics import compute_trade_statistics
from reporting.trade_log import export_trade_log
from reporting.charts import (
    plot_price_and_signals,
    plot_equity_curve,
    plot_drawdown,
    plot_comparison,
)
from reporting.report import generate_report
from notifications.system import build_dispatcher, emit_trade_events


def setup_logging() -> None:
    """
    Configure logging to stdout with INFO level.
    """
    import os
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)-5s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Suppress noisy third-party loggers
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """Execute the full backtest pipeline for all configured timeframes."""

    setup_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 65)
    logger.info("  Ark Capital -- Moving Average Crossover Backtest")
    logger.info("=" * 65)

    results = {}   # timeframe → BacktestResult
    all_trades = {}  # timeframe → List[TradeRecord]
    all_signals = {}  # timeframe → signals_df

    # Stage 1: Load and validate both datasets.
    datasets = {}
    for cfg in ALL_CONFIGS:
        tf = cfg.timeframe
        data_path = DATA_FILES[tf]

        logger.info("-" * 50)
        logger.info("Loading [%s] dataset...", tf)
        dataset = load_klines(filepath=data_path, timeframe=tf)
        validation = validate_dataset(dataset)

        if not validation.passed:
            logger.error(
                "Data validation FAILED for [%s]. Errors: %s",
                tf, validation.errors
            )
            sys.exit(1)

        datasets[tf] = dataset

    # Stage 2: Run the strategy for each timeframe.
    for cfg in ALL_CONFIGS:
        tf = cfg.timeframe
        dataset = datasets[tf]

        logger.info("─" * 50)
        logger.info("Running pipeline for [%s]...", tf)

        # 2a. Signal generation
        signals_df = generate_crossover_signals(
            close=dataset.df["close"],
            config=cfg,
        )
        all_signals[tf] = signals_df

        # 2b. Trade extraction
        trades = extract_trades(signals_df, timeframe=tf)
        all_trades[tf] = trades

        # 2c. Backtest simulation
        result = run_backtest(signals_df=signals_df, config=cfg)
        results[tf] = result

        # 2d. Trade statistics
        stats = compute_trade_statistics(trades, timeframe=tf)

        # 2e. Trade log export
        candle_hours = {"1h": 1, "4h": 4}[tf]
        trade_log_path = export_trade_log(
            trades=trades,
            config=cfg,
            candle_hours=candle_hours,
        )
        logger.info("Trade log → %s", trade_log_path)

        # 2f. Charts
        logger.info("Generating charts for [%s]...", tf)
        plot_price_and_signals(signals_df, trades, result)
        plot_equity_curve(result)
        plot_drawdown(result)

        # 2g. Notification events
        dispatcher = build_dispatcher(tf)
        emit_trade_events(signals_df, trades, result, dispatcher)

    # Stage 3: Build the comparison chart.
    logger.info("─" * 50)
    logger.info("Generating timeframe comparison chart...")
    plot_comparison(results["1h"], results["4h"])

    # Stage 4: Generate the narrative report.
    logger.info("Generating narrative report...")
    report_path = generate_report(
        results=results,
        trades=all_trades,
        datasets=datasets,
    )
    logger.info("Report → %s", report_path)

    # Stage 5: Print the console summary.
    _print_summary(results, all_trades)

    logger.info("=" * 65)
    logger.info("  Pipeline complete. Outputs in: %s", OUTPUT_DIR)
    logger.info("=" * 65)


def _print_summary(results: dict, all_trades: dict) -> None:
    """Print a clean summary comparison table to the console."""
    print("\n")
    print("=" * 65)
    print(f"  {'BACKTEST SUMMARY':^61}")
    print("=" * 65)

    headers = f"  {'Metric':<35} {'1h':>12} {'4h':>12}"
    print(headers)
    print("-" * 65)

    r1 = results["1h"]
    r4 = results["4h"]
    t1 = all_trades["1h"]
    t4 = all_trades["4h"]

    def row(label, v1, v4, fmt="{:.1f}%"):
        print(f"  {label:<35} {fmt.format(v1):>12} {fmt.format(v4):>12}")

    row("Strategy Total Return",       r1.total_return_pct,      r4.total_return_pct)
    row("Strategy Annualised Return",  r1.annualized_return_pct, r4.annualized_return_pct)
    row("Buy & Hold Total Return",     r1.bh_total_return_pct,   r4.bh_total_return_pct)
    row("Strategy Sharpe Ratio",       r1.sharpe_ratio,          r4.sharpe_ratio, fmt="{:.2f}")
    row("Buy & Hold Sharpe Ratio",     r1.bh_sharpe_ratio,       r4.bh_sharpe_ratio, fmt="{:.2f}")
    row("Max Drawdown",                r1.max_drawdown_pct,      r4.max_drawdown_pct)
    row("Annualised Volatility",       r1.volatility_ann_pct,    r4.volatility_ann_pct)
    row("Time In Market",              r1.time_in_market_pct,    r4.time_in_market_pct)
    row("Total Trades",                len(t1),                  len(t4), fmt="{:.0f}")

    print("=" * 65)
    print()


if __name__ == "__main__":
    run_pipeline()
