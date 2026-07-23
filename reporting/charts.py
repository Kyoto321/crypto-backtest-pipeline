"""
reporting/charts.py
===================
Publication-quality charts for the backtest results using Plotly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Thread
from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtest.engine import BacktestResult
from strategy.positions import TradeRecord
from strategy.config import CHARTS_DIR

logger = logging.getLogger(__name__)

# Design tokens
THEME = {
    "bg": "#0d1117",          # Deep navy background (GitHub dark)
    "paper": "#161b22",       # Slightly lighter panel
    "grid": "#21262d",        # Subtle grid lines
    "text": "#c9d1d9",        # Soft white text
    "accent": "#58a6ff",      # Blue — fast MA, strategy equity
    "accent2": "#f78166",     # Orange-red — slow MA, buy & hold
    "green": "#3fb950",       # Signal: buy / winner
    "red": "#f85149",         # Signal: sell / loser
    "yellow": "#d29922",      # Drawdown highlight
    "purple": "#bc8cff",      # Position shading
    "font_family": "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
    "font_size": 12,
}

LAYOUT_DEFAULTS = dict(
    template="plotly_dark",
    paper_bgcolor=THEME["paper"],
    plot_bgcolor=THEME["bg"],
    font=dict(family=THEME["font_family"], size=THEME["font_size"], color=THEME["text"]),
    legend=dict(
        bgcolor=THEME["paper"],
        bordercolor=THEME["grid"],
        borderwidth=1,
        x=0.01, y=0.99,
        xanchor="left", yanchor="top",
    ),
    margin=dict(l=60, r=40, t=60, b=50),
    hovermode="x unified",
)


def ensure_output_dir() -> Path:
    """Create charts output directory if it doesn't exist."""
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    return CHARTS_DIR


def _save_figure(fig: go.Figure, filename: str, width: int = 1400, height: int = 700, png_export_timeout: float = 5.0) -> None:
    """Save a Plotly figure as HTML and attempt PNG export without blocking the pipeline."""
    out_dir = ensure_output_dir()
    html_path = out_dir / f"{filename}.html"
    png_path = out_dir / f"{filename}.png"

    fig.write_html(str(html_path))
    logger.info("Chart saved: %s", html_path)

    def _write_png() -> None:
        try:
            fig.write_image(str(png_path), width=width, height=height, scale=2)
            logger.info("Chart saved: %s", png_path)
        except Exception as exc:
            logger.warning("PNG export skipped: %s", exc)

    thread = Thread(target=_write_png, daemon=True)
    thread.start()
    thread.join(timeout=png_export_timeout)

    if thread.is_alive():
        logger.warning("PNG export timed out after %.1fs; continuing without PNG", png_export_timeout)


# Chart 1: Price + Moving Averages + Signals 

def plot_price_and_signals(
    signals_df: pd.DataFrame,
    trades: List[TradeRecord],
    result: BacktestResult,
) -> go.Figure:
    """
    Chart 1: Close price, fast/slow MAs, and entry/exit signal markers.
    """
    cfg = result.config
    tf = cfg.timeframe

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        subplot_titles=[
            f"BTC/USDT {tf} — Price & MA({cfg.fast_window}/{cfg.slow_window}) Crossover",
            "Position (1 = Long, 0 = Flat)",
        ],
        vertical_spacing=0.06,
    )

    # Price line 
    fig.add_trace(go.Scatter(
        x=signals_df.index, y=signals_df["close"],
        name="Close Price",
        line=dict(color=THEME["text"], width=1.2),
        hovertemplate="$%{y:,.0f}<extra>Close</extra>",
    ), row=1, col=1)

    # Fast MA
    fig.add_trace(go.Scatter(
        x=signals_df.index, y=signals_df["fast_ma"],
        name=f"Fast MA ({cfg.fast_window})",
        line=dict(color=THEME["accent"], width=1.5, dash="solid"),
        hovertemplate="$%{y:,.0f}<extra>Fast MA</extra>",
    ), row=1, col=1)

    # Slow MA
    fig.add_trace(go.Scatter(
        x=signals_df.index, y=signals_df["slow_ma"],
        name=f"Slow MA ({cfg.slow_window})",
        line=dict(color=THEME["accent2"], width=1.5, dash="dot"),
        hovertemplate="$%{y:,.0f}<extra>Slow MA</extra>",
    ), row=1, col=1)

    # Buy signals (entry markers) 
    buy_times = [t.entry_time for t in trades]
    buy_prices = [signals_df["close"].get(t, None) for t in buy_times]
    buy_prices_valid = [p for p in buy_prices if p is not None]
    buy_times_valid = [t for t, p in zip(buy_times, buy_prices) if p is not None]

    if buy_times_valid:
        fig.add_trace(go.Scatter(
            x=[str(t) for t in buy_times_valid], y=buy_prices_valid,
            name="BUY Entry",
            mode="markers",
            marker=dict(
                symbol="triangle-up",
                size=12,
                color=THEME["green"],
                line=dict(color=THEME["bg"], width=1),
            ),
            hovertemplate="BUY @ $%{y:,.0f}<extra>Entry</extra>",
        ), row=1, col=1)

    # Sell signals (exit markers)
    sell_times = [t.exit_time for t in trades if t.exit_reason == "DEATH_CROSS"]
    sell_prices = [signals_df["close"].get(t, None) for t in sell_times]
    sell_prices_valid = [p for p in sell_prices if p is not None]
    sell_times_valid = [t for t, p in zip(sell_times, sell_prices) if p is not None]

    if sell_times_valid:
        fig.add_trace(go.Scatter(
            x=[str(t) for t in sell_times_valid], y=sell_prices_valid,
            name="SELL Exit",
            mode="markers",
            marker=dict(
                symbol="triangle-down",
                size=12,
                color=THEME["red"],
                line=dict(color=THEME["bg"], width=1),
            ),
            hovertemplate="SELL @ $%{y:,.0f}<extra>Exit</extra>",
        ), row=1, col=1)

    # Position chart (row 2) 
    fig.add_trace(go.Scatter(
        x=signals_df.index,
        y=result.position_series,
        name="Position",
        fill="tozeroy",
        fillcolor=f"rgba(88, 166, 255, 0.15)",
        line=dict(color=THEME["accent"], width=1),
        hovertemplate="%{y}<extra>Position</extra>",
    ), row=2, col=1)

    # Layout 
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        height=700,
        title=dict(
            text=f"Moving Average Crossover — {cfg.label}",
            x=0.5, xanchor="center",
            font=dict(size=16, color=THEME["text"]),
        ),
    )
    fig.update_yaxes(
        tickprefix="$", tickformat=",.0f", row=1, col=1,
        gridcolor=THEME["grid"], zerolinecolor=THEME["grid"],
    )
    fig.update_yaxes(
        tickvals=[0, 1], ticktext=["Flat", "Long"],
        row=2, col=1, gridcolor=THEME["grid"],
    )
    fig.update_xaxes(gridcolor=THEME["grid"])

    filename = f"chart1_price_signals_{tf}"
    _save_figure(fig, filename)
    return fig


# Chart 2: Equity Curve — Strategy vs Buy & Hold

def plot_equity_curve(result: BacktestResult) -> go.Figure:
    """
    Chart 2: Portfolio growth — strategy vs buy & hold baseline.
    """
    cfg = result.config
    tf = cfg.timeframe

    # Normalise to 1.0 at start for cleaner comparison
    strat_norm = result.equity_curve / result.equity_curve.iloc[0]
    bh_norm = result.benchmark_curve / result.benchmark_curve.iloc[0]

    fig = go.Figure()

    # Strategy equity
    fig.add_trace(go.Scatter(
        x=strat_norm.index, y=strat_norm,
        name=f"Strategy ({cfg.label})",
        line=dict(color=THEME["accent"], width=2),
        hovertemplate="×%{y:.3f}<extra>Strategy</extra>",
    ))

    # Buy & Hold equity 
    fig.add_trace(go.Scatter(
        x=bh_norm.index, y=bh_norm,
        name="Buy & Hold (BTC)",
        line=dict(color=THEME["accent2"], width=2, dash="dash"),
        hovertemplate="×%{y:.3f}<extra>Buy & Hold</extra>",
    ))

    # Shade "strategy wins" vs "buy&hold wins" regions 
    x_shade = strat_norm.index.astype(str).tolist() + strat_norm.index.astype(str).tolist()[::-1]
    fig.add_trace(go.Scatter(
        x=x_shade,
        y=strat_norm.tolist() + bh_norm.tolist()[::-1],
        fill="toself",
        fillcolor="rgba(63, 185, 80, 0.07)",
        line=dict(color="rgba(0,0,0,0)"),
        name="Outperformance Region",
        showlegend=False,
        hoverinfo="skip",
    ))

    # Annotate max drawdown point 
    dd_min_idx = result.drawdown_series.idxmin()
    dd_min_val = strat_norm[dd_min_idx]
    fig.add_annotation(
        x=dd_min_idx, y=dd_min_val,
        text=f"Max DD: {result.max_drawdown_pct:.1f}%",
        showarrow=True, arrowhead=2,
        arrowcolor=THEME["yellow"],
        font=dict(color=THEME["yellow"], size=11),
        bgcolor=THEME["paper"],
        bordercolor=THEME["yellow"],
    )

    # Layout
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        height=550,
        title=dict(
            text=f"Equity Curve — Strategy vs Buy & Hold [{tf}]",
            x=0.5, xanchor="center",
            font=dict(size=16, color=THEME["text"]),
        ),
        yaxis=dict(
            tickformat=".2f",
            title="Growth Multiple (1.0 = start)",
            gridcolor=THEME["grid"],
        ),
        xaxis=dict(gridcolor=THEME["grid"]),
    )

    filename = f"chart2_equity_curve_{tf}"
    _save_figure(fig, filename)
    return fig


# Chart 3: Drawdown
def plot_drawdown(result: BacktestResult) -> go.Figure:
    """
    Chart 3: Running drawdown from peak (the 'pain chart').
    """
    cfg = result.config
    tf = cfg.timeframe

    dd_pct = result.drawdown_series * 100

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dd_pct.index, y=dd_pct,
        name="Strategy Drawdown",
        fill="tozeroy",
        fillcolor="rgba(248, 81, 73, 0.25)",
        line=dict(color=THEME["red"], width=1.5),
        hovertemplate="%{y:.1f}%<extra>Drawdown</extra>",
    ))

    # Max drawdown line
    fig.add_hline(
        y=result.max_drawdown_pct,
        line=dict(color=THEME["yellow"], dash="dash", width=1),
        annotation_text=f"Max DD: {result.max_drawdown_pct:.1f}%",
        annotation_position="right",
        annotation_font=dict(color=THEME["yellow"]),
    )

    # Alert threshold line
    alert_level = -cfg.drawdown_alert_threshold * 100
    fig.add_hline(
        y=alert_level,
        line=dict(color=THEME["accent2"], dash="dot", width=1),
        annotation_text=f"Alert threshold: {alert_level:.0f}%",
        annotation_position="right",
        annotation_font=dict(color=THEME["accent2"]),
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        height=380,
        title=dict(
            text=f"Running Drawdown from Peak [{tf}]",
            x=0.5, xanchor="center",
            font=dict(size=16, color=THEME["text"]),
        ),
        yaxis=dict(
            ticksuffix="%",
            title="Drawdown from Peak",
            gridcolor=THEME["grid"],
        ),
        xaxis=dict(gridcolor=THEME["grid"]),
    )

    filename = f"chart3_drawdown_{tf}"
    _save_figure(fig, filename)
    return fig


# Chart 4: Timeframe Comparison 

def plot_comparison(
    result_1h: BacktestResult,
    result_4h: BacktestResult,
) -> go.Figure:
    """
    Chart 4: Side-by-side equity curves for 1h vs 4h strategy.
    """
    fig = go.Figure()

    # Normalise all series to 1.0 at start
    s1h = result_1h.equity_curve / result_1h.equity_curve.iloc[0]
    s4h = result_4h.equity_curve / result_4h.equity_curve.iloc[0]
    bh = result_1h.benchmark_curve / result_1h.benchmark_curve.iloc[0]

    fig.add_trace(go.Scatter(
        x=s1h.index, y=s1h,
        name=f"1h Strategy (MA {result_1h.config.fast_window}/{result_1h.config.slow_window})",
        line=dict(color=THEME["accent"], width=2),
    ))

    fig.add_trace(go.Scatter(
        x=s4h.index, y=s4h,
        name=f"4h Strategy (MA {result_4h.config.fast_window}/{result_4h.config.slow_window})",
        line=dict(color=THEME["purple"], width=2),
    ))

    fig.add_trace(go.Scatter(
        x=bh.index, y=bh,
        name="Buy & Hold (BTC) — shared baseline",
        line=dict(color=THEME["accent2"], width=2, dash="dash"),
    ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        height=500,
        title=dict(
            text="1h vs 4h Strategy — Equity Curve Comparison",
            x=0.5, xanchor="center",
            font=dict(size=16, color=THEME["text"]),
        ),
        yaxis=dict(
            tickformat=".2f",
            title="Growth Multiple (1.0 = start)",
            gridcolor=THEME["grid"],
        ),
        xaxis=dict(gridcolor=THEME["grid"]),
    )

    filename = "chart4_timeframe_comparison"
    _save_figure(fig, filename)
    return fig
