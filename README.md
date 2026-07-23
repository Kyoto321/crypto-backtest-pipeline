# Ark Capital — Data Engineering Assessment

**Candidate:** Senior Quantitative Developer / Data Engineer

A production-ready backtesting engine for a moving average crossover strategy on BTC/USDT. This project implements a full quantitative research pipeline from raw data ingestion to automated narrative reporting and event-driven notifications.

---

## Executive Summary

This system tests a Simple Moving Average (SMA) crossover strategy on two different timeframes (1-hour and 4-hour) across 6 months of Binance spot data. 

* **The 1h strategy** (MA 20/50) produced a positive return (**+2.3%**) but suffered from high trade frequency and whipsaw effects.
* **The 4h strategy** (MA 12/26) smoothed out the noise but resulted in a significant loss (**-33.1%**) due to delayed exits during the sharp bearish regime of Q2 2026.
* **Neither strategy beat Buy & Hold** during the bull run phase, which is an expected characteristic of trend-following systems (they sacrifice some upside for downside protection).

Read the automatically generated **[Narrative Analysis Report](outputs/reports/analysis_report.md)** for a deep dive into the performance differences.

---

## Architecture & Clean Code Philosophy

This project was built following strict **Clean Architecture** principles, treating backtesting code with the same rigor as live trading systems:

1. **State Isolation**: `pandas` DataFrames are strictly typed and contained. The strategy logic never mutates the raw data.
2. **Dataclass Contracts**: All data flowing between the Data, Strategy, and Backtest layers is strongly typed using Python `dataclasses` (e.g., `TradeRecord`, `BacktestResult`).
3. **Zero Look-Ahead Bias**: The signal generator enforces a strict 1-bar shift. Signals generated on the close of bar $t$ are executed at the open of bar $t+1$.
4. **Event-Driven Notifications**: The `notifications/` package implements an Observer pattern (Event Bus) that dispatches structured payloads to simulate real-time Slack/Discord webhooks without tightly coupling alerting logic to the strategy.

---

##  Quick Start

### 1. Requirements

* Python 3.10+ (tested on Python 3.14)
* Windows / Linux / macOS

### 2. Installation

Clone the repository and set up a Python virtual environment:

```bash
# Create a virtual environment
python -m venv venv

# Activate it (Windows)
venv\Scripts\activate
# Activate it (macOS/Linux)
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Pipeline

The entire system is orchestrated by a single entry point:

```bash
python main.py
```

### 4. Outputs Generated

Running `main.py` will process both datasets and generate the following artifacts in the `outputs/` directory:

* **Interactive Charts** (`outputs/charts/*.html`): Plotly HTML charts allowing you to zoom in on specific trades and verify signal logic.
* **Trade Logs** (`outputs/logs/*.csv`): A precise, row-by-row accounting of every trade, holding period, and P&L.
* **Event Stream** (`outputs/logs/*.jsonl`): A machine-readable log of all real-time events that fired during the simulation.
* **Analysis Report** (`outputs/reports/analysis_report.md`): An automated markdown report interpreting the results for non-technical stakeholders.

---

## Project Structure

```text
ark_data_assessment/
├── main.py                     # Central pipeline orchestrator
├── requirements.txt            # Dependency definitions
│
├── backtest/                   # Execution and metrics
│   ├── engine.py               # Vectorised portfolio simulation
│   └── metrics.py              # Drawdown, Sharpe, win rate calculations
│
├── data/                       # Ingestion and quality
│   ├── loader.py               # Pandas schema mapping and type casting
│   └── validator.py            # OHLC consistency and gap detection
│
├── notifications/              # Alerting and event bus
│   ├── events.py               # Typed event definitions (Slack payloads)
│   └── system.py               # Event dispatcher and handlers
│
├── reporting/                  # Output generation
│   ├── charts.py               # Plotly interactive visualisations
│   ├── report.py               # Automated Markdown report generator
│   └── trade_log.py            # P&L accounting CSV builder
│
└── strategy/                   # Financial logic
    ├── config.py               # Centralised parameters
    ├── positions.py            # Trade extraction logic
    └── signals.py              # MA Crossover logic (no look-ahead bias)
```

---

## Sample Console Output

```
=================================================================
  Ark Capital -- Moving Average Crossover Backtest
=================================================================
2026-07-21 12:00:00 [INFO ] data.loader — Loading 1h kline data...
...
2026-07-21 12:00:02 [INFO ] notifications.system — [NOTIFICATION][TRADE_CLOSED] Trade #43 closed | Return: +4.80% | P&L: $+4,801.39
2026-07-21 12:00:02 [WARNING] notifications.system — [NOTIFICATION][DRAWDOWN_ALERT] Drawdown 11.6% exceeds 10.0% threshold
...
=================================================================
                        BACKTEST SUMMARY
=================================================================
  Metric                                        1h           4h
-----------------------------------------------------------------
  Strategy Total Return                       2.3%       -33.1%
  Buy & Hold Total Return                   -27.3%       -27.3%
  Strategy Sharpe Ratio                       0.29        -2.53
  Max Drawdown                              -11.7%       -35.5%
  Total Trades                                  46           27
=================================================================
```

---

## Next Steps for Production

If this were moving toward live trading, the following engineering tasks would be prioritized:

1. **Transaction Cost Modeling**: Implement tiered fee structures (Maker/Taker) to accurately penalize the high-frequency 1h strategy.
2. **Walk-Forward Optimization**: Build a hyperparameter tuning grid that optimizes MA windows out-of-sample to prevent curve fitting.
3. **Real-time Data Adapters**: Replace the static CSV loader with a `ccxt` WebSocket adapter to stream live Binance klines directly into the signal engine.
