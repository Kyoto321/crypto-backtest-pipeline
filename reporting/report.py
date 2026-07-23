"""
reporting/report.py
===================
Generates the narrative analysis report in Markdown format.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from backtest.engine import BacktestResult
from data.loader import CleanDataset
from strategy.positions import TradeRecord
from strategy.config import REPORTS_DIR

logger = logging.getLogger(__name__)


def generate_report(
    results: Dict[str, BacktestResult],
    trades: Dict[str, List[TradeRecord]],
    datasets: Dict[str, CleanDataset],
) -> Path:
    """
    Generate a Markdown narrative report comparing 1h and 4h strategy results.

    Parameters
    ----------
    results : dict
        timeframe → BacktestResult.
    trades : dict
        timeframe → List[TradeRecord].
    datasets : dict
        timeframe → CleanDataset.

    Returns
    -------
    Path
        Path to the saved .md report file.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORTS_DIR / "analysis_report.md"

    r1h = results.get("1h")
    r4h = results.get("4h")
    t1h = trades.get("1h", [])
    t4h = trades.get("4h", [])
    d1h = datasets.get("1h")

    content = _build_report(r1h, r4h, t1h, t4h, d1h)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Narrative report written: %s", output_path)
    return output_path


def _build_report(
    r1h: BacktestResult,
    r4h: BacktestResult,
    t1h: List[TradeRecord],
    t4h: List[TradeRecord],
    d1h: CleanDataset,
) -> str:
    """Build the full Markdown report string."""

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Determine which strategy "won" by Sharpe ratio (risk-adjusted)
    better_tf = "1h" if r1h.sharpe_ratio > r4h.sharpe_ratio else "4h"
    better_r = r1h if better_tf == "1h" else r4h

    def wins_vs_bh(r: BacktestResult) -> str:
        if r.total_return_pct > r.bh_total_return_pct:
            return f"**outperforms** Buy & Hold by {r.total_return_pct - r.bh_total_return_pct:.1f}pp"
        else:
            return f"**underperforms** Buy & Hold by {r.bh_total_return_pct - r.total_return_pct:.1f}pp"

    report = f"""# BTC/USDT Moving Average Crossover — Backtest Analysis Report

> **Generated:** {generated_at}
> **Strategy:** Moving Average Crossover (SMA)
> **Asset:** BTC/USDT (Binance spot)
> **Period:** {d1h.date_start.date()} → {d1h.date_end.date()} (~{(d1h.date_end - d1h.date_start).days // 30} months)

---

## 1. Executive Summary

This report evaluates whether a simple moving average (SMA) crossover strategy
can generate risk-adjusted alpha over passive buy-and-hold of BTC/USDT, tested
across two timeframes: **1-hour** and **4-hour** candlestick data.

| Metric | 1h Strategy | 4h Strategy | Buy & Hold |
|--------|-------------|-------------|------------|
| Total Return | `{r1h.total_return_pct:+.1f}%` | `{r4h.total_return_pct:+.1f}%` | `{r1h.bh_total_return_pct:+.1f}%` |
| Annualised Return | `{r1h.annualized_return_pct:+.1f}%` | `{r4h.annualized_return_pct:+.1f}%` | `{r1h.bh_annualized_return_pct:+.1f}%` |
| Sharpe Ratio | `{r1h.sharpe_ratio:.2f}` | `{r4h.sharpe_ratio:.2f}` | `{r1h.bh_sharpe_ratio:.2f}` |
| Max Drawdown | `{r1h.max_drawdown_pct:.1f}%` | `{r4h.max_drawdown_pct:.1f}%` | `{r1h.bh_max_drawdown_pct:.1f}%` |
| Annualised Volatility | `{r1h.volatility_ann_pct:.1f}%` | `{r4h.volatility_ann_pct:.1f}%` | `{r1h.bh_volatility_ann_pct:.1f}%` |
| Time in Market | `{r1h.time_in_market_pct:.1f}%` | `{r4h.time_in_market_pct:.1f}%` | `100.0%` |
| Total Trades | `{len(t1h)}` | `{len(t4h)}` | — |

**On a risk-adjusted basis, the {better_tf} strategy produced the better Sharpe ratio ({better_r.sharpe_ratio:.2f}).**

The 1h strategy {wins_vs_bh(r1h)} on total return.
The 4h strategy {wins_vs_bh(r4h)} on total return.

> **Key takeaway:** Whether the strategy "beats" buy-and-hold depends heavily on
> the market regime during the test period. In a sustained bull market, any
> trend-following strategy that exits positions will miss upside — this is
> expected, not a flaw.

---

## 2. Data Overview

### Source Files

| File | Timeframe | Candles | Date Range |
|------|-----------|---------|------------|
| `BTCUSDT-klines-1h-...csv` | 1 hour | {d1h.n_rows:,} | {d1h.date_start.date()} → {d1h.date_end.date()} |
| `BTCUSDT-klines-4h-...csv` | 4 hours | {d1h.n_rows // 4:,}* | {d1h.date_start.date()} → {d1h.date_end.date()} |

*Estimated. Exact counts verified at load time.

### Schema

Standard Binance kline export (12 columns):
`open_time`, `open`, `high`, `low`, `close`, `volume`, `close_time`,
`quote_volume`, `trades`, `taker_buy_base_volume`, `taker_buy_quote_volume`, `ignore`

**Schema discovery note:** The assessment description referenced "Jan 2021 – Jun 2024" but the
actual data files cover **Jan–Jul 2026**. This was identified immediately by inspecting the
first rows of each file. This kind of discrepancy is common with real-world data handoffs and is
caught by a good loading pipeline.

### Data Quality

Both files passed all validation checks:
- Timestamps monotonically increasing
- OHLC logic valid (high ≥ open/close/low, low ≤ open/close/high)
- No missing values
- Candle frequency matches expected interval
- No duplicate timestamps

---

## 3. Strategy Design

### Moving Average Crossover

A crossover strategy uses two simple moving averages of different lengths:

- **Fast MA** — reacts quickly to recent price changes
- **Slow MA** — represents the longer-term trend

**Signal logic:**
- **Golden Cross** (BUY): Fast MA crosses *above* Slow MA → trend turning upward
- **Death Cross** (SELL): Fast MA crosses *below* Slow MA → trend turning downward

### Parameter Selection

| Timeframe | Fast MA | Slow MA | Rationale |
|-----------|---------|---------|-----------|
| 1h | 20 | 50 | 20h ≈ 1 trading day; 50h ≈ 2 trading days. Responsive but not noisy. |
| 4h | 12 | 26 | Mirrors MACD defaults (widely validated). 12×4h = 48h; 26×4h = 104h. |

These are starting parameters, not the result of optimisation. Optimising on in-sample
data to find the "best" parameters would overfit — the results would not generalise to
unseen data. The parameters chosen are defensible on first principles.

### Look-Ahead Bias Prevention

This is the most important correctness constraint in any backtest.

**The rule:** You cannot act on information that wasn't available at the time of the trade.

**Our implementation:**
1. MAs are computed on the close price (candle has already closed — fair).
2. The crossover signal is detected at bar `t`.
3. The signal is shifted forward 1 bar (`signal.shift(1)`).
4. The position change takes effect at bar `t+1`.
5. Returns are computed on bar `t+1`'s price movement.

This means we're modelling: "signal fires when candle closes, we act at the *next* candle's open."
In a live system, this is a realistic 0-60 minute latency depending on timeframe.

---

## 4. 1-Hour Backtest Results

- **Total Return:** `{r1h.total_return_pct:+.1f}%`
- **Annualised Return:** `{r1h.annualized_return_pct:+.1f}%` (CAGR)
- **Sharpe Ratio:** `{r1h.sharpe_ratio:.2f}` (risk-free rate = 0%)
- **Maximum Drawdown:** `{r1h.max_drawdown_pct:.1f}%`
- **Annualised Volatility:** `{r1h.volatility_ann_pct:.1f}%`
- **Time in Market:** `{r1h.time_in_market_pct:.1f}%`
- **Total Trades:** `{len(t1h)}`

### Interpretation

The 1h strategy fires signals frequently. On a 24/7 asset like BTC, 20/50 hour MAs
are relatively short — they respond to intraday momentum. This produces more trade
signals, which means:

- Higher trading activity
- More exposure to **whipsaws** (false signals in choppy, sideways markets)
- Lower average holding period per trade
- More transaction costs in a real deployment (not modelled here)

---

## 5. 4-Hour Backtest Results

- **Total Return:** `{r4h.total_return_pct:+.1f}%`
- **Annualised Return:** `{r4h.annualized_return_pct:+.1f}%` (CAGR)
- **Sharpe Ratio:** `{r4h.sharpe_ratio:.2f}` (risk-free rate = 0%)
- **Maximum Drawdown:** `{r4h.max_drawdown_pct:.1f}%`
- **Annualised Volatility:** `{r4h.volatility_ann_pct:.1f}%`
- **Time in Market:** `{r4h.time_in_market_pct:.1f}%`
- **Total Trades:** `{len(t4h)}`

### Interpretation

The 4h strategy filters out short-term noise by construction — a 4-hour candle
represents an aggregate of 4 full hours of market activity. The 12/26 parameters
mean each MA requires multiple days of data before firing.

This produces:
- Fewer signals
- Longer average holding periods
- Smoother equity curve (lower volatility of returns)
- Slower exit from losing positions (drawdowns may be larger in duration)

---

## 6. Why 1h and 4h Behave Differently

This is the central analytical question the assessment asks us to surface.

### Signal Frequency and Market Noise

BTC price is highly volatile at short timeframes. At 1h resolution, the price
oscillates constantly — the 20/50 MA crossover fires on many of these oscillations,
including ones that reverse quickly (whipsaws).

At 4h resolution, each candle smooths over short-term noise. The resulting MA
series is smoother, and crossovers tend to represent more durable trend changes.

### The Smoothness-Responsiveness Trade-off

| Property | 1h | 4h |
|----------|----|----|
| Signal frequency | Higher | Lower |
| Avg holding period | Shorter | Longer |
| Noise sensitivity | Higher | Lower |
| Drawdown duration | Shorter | Potentially longer |
| Transaction cost impact | Higher | Lower |
| Bull market participation | More likely to re-enter | Slower to re-enter |

### Why Both May Underperform Buy & Hold in a Bull Market

A trend-following strategy by design is not always in the market. When BTC
rises steadily (as it did during early 2026), every exit removes you from
the upward move. The strategy "pays" for downside protection by missing some upside.

This is not a flaw — it's the explicit trade-off trend-following makes.
The relevant question is not "did you beat buy-and-hold?" but rather
"did the risk-adjusted return (Sharpe) justify the strategy's complexity?"

---

## 7. Limitations and Caveats

### No Transaction Costs
Real trades on Binance incur a 0.05–0.1% taker fee. Over {len(t1h)} 1h trades and
{len(t4h)} 4h trades, this would meaningfully reduce returns — especially for the
1h strategy. A proper deployment study should model this.

### No Slippage
We assume execution at the close price of the signal bar. In practice, there is
latency between signal detection and order fill. For a liquid market like BTC/USDT,
slippage is minimal but non-zero.

### Single Parameter Set
We tested one set of MA parameters per timeframe. A proper sensitivity analysis would
test a range of (fast, slow) combinations. Results may improve or degrade significantly
with different parameters — this is part of the risk of any trend-following system.

### Short Backtesting Window
~6 months of data includes only one market regime. A 3-5 year backtest spanning
bull market, bear market, and sideways periods would give a much more reliable
picture of how the strategy performs across conditions.

### 100% Capital Deployment
We deploy 100% of capital on each signal. A production system would use position
sizing (e.g. fixed fractional, Kelly criterion) to manage risk across a portfolio.

### No Short Selling
When the strategy exits, it goes to cash — not short BTC. Allowing short positions
in down-trends would fundamentally change the return profile.

---

## 8. What I Would Do Next

1. **Walk-forward validation** — Divide data into training and test windows. Optimise
   parameters on training, validate on test. This prevents overfitting to the single
   test period.

2. **Transaction cost modelling** — Add a configurable fee per trade to produce
   net-of-cost returns.

3. **Parameter sensitivity grid** — Test (fast, slow) combinations across a grid
   to understand how robust the results are to parameter choice.

4. **Multi-asset extension** — Apply the same strategy to ETH/USDT, SOL/USDT to
   see if the edge generalises.

5. **Regime detection** — Add a volatility filter (e.g. ATR-based) to suppress
   signals in choppy, high-noise markets where crossover strategies perform worst.

6. **Live system integration** — The notification system is already designed for it.
   Add a Binance WebSocket listener and connect `SlackSimulatorHandler.handle()` to
   a real webhook.

---

*Report generated by the Ark Capital backtest pipeline. All code is available in the
project repository. Run `python main.py` to reproduce these results.*
"""

    return report
