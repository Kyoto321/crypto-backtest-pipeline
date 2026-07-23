"""
strategy/config.py
==================
Centralised configuration for the moving average crossover strategy.

Design decision: All strategy parameters live here as a typed dataclass.
This means:
  1. No magic numbers scattered across the codebase.
  2. You can instantiate different configs for different experiments.
  3. In an interview, you can point to one file and explain every choice.

Why these specific MA lengths?
  - 1h (20/50): On a 24/7 crypto market, 20 hours ≈ ~1 trading day of context.
    50 hours ≈ ~2 trading days. These provide meaningful short-term momentum
    signal without being so short they fire on noise.

  - 4h (12/26): These mirror the standard MACD defaults (12, 26). At 4h bars,
    12 bars = 48h = 2 days, 26 bars = 104h = ~4.3 days. This is a well-tested
    configuration in swing trading literature and provides a defensible baseline.

  - Both can be overridden via the dataclass at runtime — no hardcoding.
"""

from dataclasses import dataclass, field
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Raw data paths
DATA_DIR = PROJECT_ROOT  # CSVs live at the project root

DATA_FILES = {
    "1h": DATA_DIR / "BTCUSDT-klines-1h-2026-01-01_2026-07-16.csv",
    "4h": DATA_DIR / "BTCUSDT-klines-4h-2026-01-01_2026-07-16.csv",
}

# Output directories
OUTPUT_DIR = PROJECT_ROOT / "outputs"
CHARTS_DIR = OUTPUT_DIR / "charts"
LOGS_DIR = OUTPUT_DIR / "logs"
REPORTS_DIR = OUTPUT_DIR / "reports"


@dataclass
class StrategyConfig:
    """
    All parameters governing one run of the moving average crossover strategy.

    Attributes
    ----------
    timeframe : str
        Human-readable label for the data timeframe, e.g. "1h" or "4h".
        Used for chart titles, log filenames, and report sections.

    fast_window : int
        Number of candles for the fast (short) moving average.
        Detects recent price momentum.

    slow_window : int
        Number of candles for the slow (long) moving average.
        Represents the longer-term trend.

    initial_capital : float
        Starting portfolio value in USDT.
        Used for absolute P&L calculations in the trade log.

    drawdown_alert_threshold : float
        When the running drawdown from peak exceeds this fraction (e.g. 0.15
        = 15%), a DrawdownAlertEvent is dispatched by the notification system.

    risk_threshold_pct : float
        Maximum allowed drawdown before a RiskThresholdBreached event fires.
        In a live system this could halt trading. Here it logs prominently.

    candles_per_year : int
        Number of candles in one calendar year for this timeframe.
        Used to annualise Sharpe ratio and volatility correctly.
        1h: 24 * 365 = 8_760
        4h:  6 * 365 = 2_190
    """

    timeframe: str
    fast_window: int
    slow_window: int
    initial_capital: float = 100_000.0
    drawdown_alert_threshold: float = 0.10   # 10% drawdown → warning alert
    risk_threshold_pct: float = 0.20          # 20% drawdown → risk breach event
    candles_per_year: int = 8_760             # default: 1h (overridden for 4h)

    def __post_init__(self) -> None:
        """Validate parameters after construction — fail fast, fail loud."""
        if self.fast_window >= self.slow_window:
            raise ValueError(
                f"fast_window ({self.fast_window}) must be strictly less than "
                f"slow_window ({self.slow_window}). "
                "A 'fast' MA must react more quickly than the 'slow' MA."
            )
        if self.fast_window < 2:
            raise ValueError("fast_window must be >= 2 to compute a meaningful MA.")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be a positive value.")

    @property
    def label(self) -> str:
        """Short human-readable label, e.g. '1h MA(20/50)'."""
        return f"{self.timeframe} MA({self.fast_window}/{self.slow_window})"


# Preset configs (used by main.py) 

CONFIG_1H = StrategyConfig(
    timeframe="1h",
    fast_window=20,
    slow_window=50,
    initial_capital=100_000.0,
    drawdown_alert_threshold=0.10,
    risk_threshold_pct=0.20,
    candles_per_year=8_760,  # 24 hours × 365 days
)

CONFIG_4H = StrategyConfig(
    timeframe="4h",
    fast_window=12,
    slow_window=26,
    initial_capital=100_000.0,
    drawdown_alert_threshold=0.10,
    risk_threshold_pct=0.20,
    candles_per_year=2_190,  # 6 candles/day × 365 days
)

ALL_CONFIGS = [CONFIG_1H, CONFIG_4H]
