"""
notifications/system.py
=======================
Event dispatcher — the notification system's runtime core.

Architecture: Observer / Event Bus
------------------------------------
The NotificationDispatcher acts as a central hub:

  - Emitters  (strategy, backtest) → dispatch(event) → Dispatcher
  - Dispatcher → registered handlers → ConsoleHandler, SlackHandler, etc.

This means:
  - The strategy engine doesn't know or care who's listening.
  - You can add a new channel (Discord, PagerDuty, email) by registering
    one new handler — zero changes to strategy code.
  - In tests, you inject a MockHandler to capture events without side effects.

Simulated output
----------------
In this backtest context, events are:
  1. Logged to the console (visible when running main.py).
  2. Written to a JSONL event log file (outputs/logs/events_<timeframe>.jsonl).
  3. Printed as Slack-formatted text (shows what the Slack message would look like).

To go live: set SLACK_WEBHOOK_URL env var and uncomment the HTTP request.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Type

from notifications.events import (
    BaseEvent,
    BuySignalEvent,
    DrawdownAlertEvent,
    EventType,
    RiskThresholdBreachedEvent,
    SellSignalEvent,
    StrategyFinishedEvent,
    StrategyStartedEvent,
    TradeClosedEvent,
)
from strategy.config import LOGS_DIR

logger = logging.getLogger(__name__)

# Base interface for notification handlers.
class NotificationHandler(ABC):
    """
    Abstract base class for all notification handlers.

    To create a new channel (e.g. Discord, email), subclass this and
    implement handle(). Register it with NotificationDispatcher.register().
    """

    @abstractmethod
    def handle(self, event: BaseEvent) -> None:
        """Process an incoming event."""
        ...


# Concrete handlers for console, file, and simulated Slack output.
class ConsoleHandler(NotificationHandler):
    """Prints events to stdout using structured log format."""

    def handle(self, event: BaseEvent) -> None:
        level_map = {
            EventType.BUY_SIGNAL: "INFO",
            EventType.SELL_SIGNAL: "INFO",
            EventType.TRADE_CLOSED: "INFO",
            EventType.DRAWDOWN_ALERT: "WARNING",
            EventType.RISK_THRESHOLD_BREACHED: "CRITICAL",
            EventType.STRATEGY_STARTED: "INFO",
            EventType.STRATEGY_FINISHED: "INFO",
        }
        level = level_map.get(event.event_type, "INFO")
        logger.log(
            getattr(logging, level),
            "[NOTIFICATION][%s] %s",
            event.event_type.value,
            self._format_message(event),
        )

    def _format_message(self, event: BaseEvent) -> str:
        if isinstance(event, BuySignalEvent):
            return f"BUY @ ${event.entry_price:,.2f} [{event.timeframe}]"
        if isinstance(event, SellSignalEvent):
            return f"SELL @ ${event.exit_price:,.2f} [{event.timeframe}]"
        if isinstance(event, TradeClosedEvent):
            return (
                f"Trade #{event.trade_id} closed | "
                f"Return: {event.return_pct:+.2f}% | "
                f"P&L: ${event.profit_loss_usd:+,.2f}"
            )
        if isinstance(event, DrawdownAlertEvent):
            return f"Drawdown {event.current_drawdown_pct:.1f}% exceeds {event.threshold_pct:.1f}% threshold"
        if isinstance(event, RiskThresholdBreachedEvent):
            return f"RISK BREACH: Drawdown {event.current_drawdown_pct:.1f}% > {event.risk_threshold_pct:.1f}% limit"
        if isinstance(event, StrategyStartedEvent):
            return f"Backtest started: {event.strategy_label} | Capital: ${event.initial_capital:,.0f}"
        if isinstance(event, StrategyFinishedEvent):
            return f"Backtest complete: {event.strategy_label} | Return: {event.total_return_pct:+.1f}%"
        return str(event.to_dict())


class JsonlFileHandler(NotificationHandler):
    """
    Writes every event as a JSON line to a .jsonl log file.

    JSONL (JSON Lines) is machine-readable and easily parsed by
    log aggregators like Datadog, Splunk, or AWS CloudWatch.
    """

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        filepath.parent.mkdir(parents=True, exist_ok=True)

    def handle(self, event: BaseEvent) -> None:
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")


class SlackSimulatorHandler(NotificationHandler):
    """
    Simulates Slack notifications by printing the formatted payload.

    In production, replace the print statement with:
        import os, requests
        webhook_url = os.environ["SLACK_WEBHOOK_URL"]
        requests.post(webhook_url, json=event.to_slack_payload())
    """

    def handle(self, event: BaseEvent) -> None:
        payload = event.to_slack_payload()
        # Replace this with an HTTP call in production.
        logger.debug("[SLACK SIMULATED] %s", payload.get("text", ""))


# Dispatcher for routing events to all handlers.

class NotificationDispatcher:
    """
    Central event bus.

    Usage
    -----
    dispatcher = NotificationDispatcher()
    dispatcher.register(ConsoleHandler())
    dispatcher.register(JsonlFileHandler(Path("outputs/logs/events.jsonl")))

    dispatcher.dispatch(BuySignalEvent(timeframe="1h", entry_price=87000))
    """

    def __init__(self) -> None:
        self._handlers: List[NotificationHandler] = []
        self._event_count: int = 0

    def register(self, handler: NotificationHandler) -> "NotificationDispatcher":
        """Register a handler. Returns self for method chaining."""
        self._handlers.append(handler)
        logger.debug("Registered handler: %s", type(handler).__name__)
        return self

    def dispatch(self, event: BaseEvent) -> None:
        """
        Dispatch an event to all registered handlers.

        Each handler is called independently — a failure in one handler
        does not prevent others from receiving the event.
        """
        self._event_count += 1
        for handler in self._handlers:
            try:
                handler.handle(event)
            except Exception as exc:
                logger.error(
                    "Handler %s failed on event %s: %s",
                    type(handler).__name__, event.event_type.value, exc,
                    exc_info=True,
                )

    @property
    def event_count(self) -> int:
        return self._event_count


def build_dispatcher(timeframe: str) -> NotificationDispatcher:
    """
    Factory function: build a pre-configured dispatcher for a given timeframe.

    Registers:
      - ConsoleHandler (human-readable terminal output)
      - JsonlFileHandler (structured machine-readable log)
      - SlackSimulatorHandler (shows Slack payload format)
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    event_log_path = LOGS_DIR / f"events_{timeframe}.jsonl"

    dispatcher = NotificationDispatcher()
    dispatcher.register(ConsoleHandler())
    dispatcher.register(JsonlFileHandler(event_log_path))
    dispatcher.register(SlackSimulatorHandler())

    logger.info(
        "[%s] Notification dispatcher ready | Event log: %s",
        timeframe, event_log_path,
    )
    return dispatcher


def emit_trade_events(
    signals_df,
    trades: list,
    result,
    dispatcher: NotificationDispatcher,
) -> None:
    """
    Replay all strategy events in chronological order.

    This function walks through the backtest results and fires the
    appropriate event for each meaningful moment: signals, trades,
    and risk breaches.

    In a live system this would be called in real-time as each candle closes.
    In backtesting we replay it post-hoc to demonstrate the event stream.
    """
    cfg = result.config
    tf = cfg.timeframe

    # Emit the start event.
    dispatcher.dispatch(StrategyStartedEvent(
        timeframe=tf,
        strategy_label=cfg.label,
        start_date=str(signals_df.index[0].date()),
        end_date=str(signals_df.index[-1].date()),
        initial_capital=cfg.initial_capital,
    ))

    # Emit buy, sell, and trade-closed events.
    for trade in trades:
        # BUY signal
        entry_row = signals_df.loc[trade.entry_time] if trade.entry_time in signals_df.index else None
        if entry_row is not None:
            dispatcher.dispatch(BuySignalEvent(
                timeframe=tf,
                timestamp_candle=str(trade.entry_time),
                entry_price=trade.entry_price,
                fast_ma=float(entry_row.get("fast_ma", 0)),
                slow_ma=float(entry_row.get("slow_ma", 0)),
            ))

        # SELL signal (only if it was a signal-driven exit)
        if trade.exit_reason == "DEATH_CROSS":
            exit_row = signals_df.loc[trade.exit_time] if trade.exit_time in signals_df.index else None
            if exit_row is not None:
                dispatcher.dispatch(SellSignalEvent(
                    timeframe=tf,
                    timestamp_candle=str(trade.exit_time),
                    exit_price=trade.exit_price,
                    fast_ma=float(exit_row.get("fast_ma", 0)),
                    slow_ma=float(exit_row.get("slow_ma", 0)),
                ))

        # Trade closed
        candle_hours = {"1h": 1, "4h": 4}.get(tf, 1)
        pnl_fraction = trade.return_pct / 100.0
        dispatcher.dispatch(TradeClosedEvent(
            timeframe=tf,
            trade_id=trade.trade_id,
            return_pct=trade.return_pct,
            profit_loss_usd=cfg.initial_capital * pnl_fraction,
            holding_hours=trade.holding_bars * candle_hours,
            exit_reason=trade.exit_reason,
        ))

    # Emit drawdown alerts when thresholds are breached.
    dd_series = result.drawdown_series * 100
    alert_threshold = -cfg.drawdown_alert_threshold * 100
    risk_threshold = -cfg.risk_threshold_pct * 100
    alert_fired = False
    risk_fired = False

    for ts, dd in dd_series.items():
        if dd <= risk_threshold and not risk_fired:
            dispatcher.dispatch(RiskThresholdBreachedEvent(
                timeframe=tf,
                current_drawdown_pct=abs(dd),
                risk_threshold_pct=abs(risk_threshold),
            ))
            risk_fired = True
            alert_fired = True  # risk breach implies alert already passed

        elif dd <= alert_threshold and not alert_fired:
            dispatcher.dispatch(DrawdownAlertEvent(
                timeframe=tf,
                current_drawdown_pct=abs(dd),
                threshold_pct=abs(alert_threshold),
            ))
            alert_fired = True

    # Emit the final strategy event.
    dispatcher.dispatch(StrategyFinishedEvent(
        timeframe=tf,
        strategy_label=cfg.label,
        total_return_pct=result.total_return_pct,
        sharpe_ratio=result.sharpe_ratio,
        max_drawdown_pct=result.max_drawdown_pct,
        n_trades=len(trades),
    ))

    logger.info(
        "[%s] Event replay complete — %d events dispatched.",
        tf, dispatcher.event_count,
    )
