import logging
logging.basicConfig(level=logging.INFO)

from data.loader import load_dataset
from data.validator import validate_dataset
from strategy.config import TIMEFRAME_CONFIGS
from strategy.signals import generate_signals
from strategy.positions import extract_trades
from backtest.engine import run_backtest
from reporting.charts import plot_price_and_signals, plot_equity_curve, plot_drawdown

cfg = TIMEFRAME_CONFIGS['1h']
raw = load_dataset('BTCUSDT-klines-1h-2026-01-01_2026-07-16.csv', timeframe='1h')
validated = validate_dataset(raw, timeframe='1h')
signals_df = generate_signals(validated, cfg)
trades = extract_trades(signals_df)
result = run_backtest(signals_df, trades, cfg)

print('calling plot_price_and_signals')
plot_price_and_signals(signals_df, trades, result)
print('plot1 done')
plot_equity_curve(result)
print('plot2 done')
plot_drawdown(result)
print('plot3 done')
