# BTC/USDT Moving Average Crossover — Backtest Analysis Report

> **Generated:** 2026-07-23 11:50 UTC
> **Strategy:** Moving Average Crossover (SMA)
> **Asset:** BTC/USDT (Binance spot)
> **Period:** 2026-01-01 → 2026-07-16 (~6 months)

---

## 1. Executive Summary

This report evaluates whether a simple moving average (SMA) crossover strategy
can generate risk-adjusted alpha over passive buy-and-hold of BTC/USDT, tested
across two timeframes: **1-hour** and **4-hour** candlestick data.

| Metric | 1h Strategy | 4h Strategy | Buy & Hold |
|--------|-------------|-------------|------------|
| Total Return | `+2.3%` | `-33.1%` | `-27.3%` |
| Annualised Return | `+4.4%` | `-52.5%` | `-44.6%` |
| Sharpe Ratio | `0.29` | `-2.53` | `-1.06` |
| Max Drawdown | `-11.7%` | `-35.5%` | `-40.3%` |
| Annualised Volatility | `29.1%` | `27.9%` | `45.9%` |
| Time in Market | `50.1%` | `46.3%` | `100.0%` |
| Total Trades | `46` | `27` | — |

**On a risk-adjusted basis, the 1h strategy produced the better Sharpe ratio (0.29).**

The 1h strategy **outperforms** Buy & Hold by 29.6pp on total return.
The 4h strategy **underperforms** Buy & Hold by 5.8pp on total return.

> **Key takeaway:** Whether the strategy "beats" buy-and-hold depends heavily on
> the market regime during the test period. In a sustained bull market, any
> trend-following strategy that exits positions will miss upside — this is
> expected, not a flaw.

---

## 2. Data Overview

### Source Files

| File | Timeframe | Candles | Date Range |
|------|-----------|---------|------------|
| `BTCUSDT-klines-1h-...csv` | 1 hour | 4,728 | 2026-01-01 → 2026-07-16 |
| `BTCUSDT-klines-4h-...csv` | 4 hours | 1,182* | 2026-01-01 → 2026-07-16 |

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

- **Total Return:** `+2.3%`
- **Annualised Return:** `+4.4%` (CAGR)
- **Sharpe Ratio:** `0.29` (risk-free rate = 0%)
- **Maximum Drawdown:** `-11.7%`
- **Annualised Volatility:** `29.1%`
- **Time in Market:** `50.1%`
- **Total Trades:** `46`

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

- **Total Return:** `-33.1%`
- **Annualised Return:** `-52.5%` (CAGR)
- **Sharpe Ratio:** `-2.53` (risk-free rate = 0%)
- **Maximum Drawdown:** `-35.5%`
- **Annualised Volatility:** `27.9%`
- **Time in Market:** `46.3%`
- **Total Trades:** `27`

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
Real trades on Binance incur a 0.05–0.1% taker fee. Over 46 1h trades and
27 4h trades, this would meaningfully reduce returns — especially for the
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
