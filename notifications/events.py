"""
notifications/events.py
=======================
Typed event definitions for the notification system.

Design pattern: Events as dataclasses
--------------------------------------
Each event type is a Python dataclass. This gives us:
  1. Type safety — you cannot accidentally emit a BuySignalEvent without
     specifying the required price and timestamp fields.
  2. Serialisability — dataclasses trivially convert to dict/JSON for
     Slack/Discord/webhook payloads.
  3. Discoverability — all event types are listed in one file. A new
     engineer can understand the entire system's event vocabulary here.

This pattern is used in production event-driven systems (Kafka topics,
EventBridge schemas, etc.) under names like "domain events" or "event contracts".

"Simulate the output — you don't need to connect to anything real.
 But design it as if you were going to wire it up to Slack tomorrow."
 — Assessment brief
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class EventType(str, Enum):
    """Enumeration of all event types the system can emit."""
    STRATEGY_STARTED = "STRATEGY_STARTED"
    STRATEGY_FINISHED = "STRATEGY_FINISHED"
    BUY_SIGNAL = "BUY_SIGNAL"
    SELL_SIGNAL = "SELL_SIGNAL"
    TRADE_CLOSED = "TRADE_CLOSED"
    DRAWDOWN_ALERT = "DRAWDOWN_ALERT"
    RISK_THRESHOLD_BREACHED = "RISK_THRESHOLD_BREACHED"


@dataclass
class BaseEvent:
    """
    Base class for all events.

    Every event carries a timestamp and event_type so handlers can
    route and log events without inspecting their specific fields.
    """
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dict (suitable for JSON serialisation)."""
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["timestamp"] = self.timestamp.isoformat() + "Z"
        return d

    def to_slack_payload(self) -> Dict[str, Any]:
        """
        Format as a Slack Block Kit message payload.

        This is what you would POST to a Slack Incoming Webhook URL.
        Replace SLACK_WEBHOOK_URL environment variable with the real URL
        and add: requests.post(SLACK_WEBHOOK_URL, json=self.to_slack_payload())
        """
        raise NotImplementedError("Each event subclass defines its own Slack format.")


@dataclass
class StrategyStartedEvent(BaseEvent):
    """Fired once when the backtest pipeline begins."""
    event_type: EventType = field(default=EventType.STRATEGY_STARTED, init=False)
    timeframe: str = ""
    strategy_label: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 0.0

    def to_slack_payload(self) -> Dict[str, Any]:
        return {
            "text": f"*Strategy Started* — {self.strategy_label}",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Strategy Backtest Started*\n"
                        f"*Strategy:* `{self.strategy_label}`\n"
                        f"*Timeframe:* {self.timeframe}\n"
                        f"*Period:* {self.start_date} → {self.end_date}\n"
                        f"*Capital:* ${self.initial_capital:,.0f}"
                    ),
                },
            }],
        }


@dataclass
class StrategyFinishedEvent(BaseEvent):
    """Fired once when the backtest pipeline completes."""
    event_type: EventType = field(default=EventType.STRATEGY_FINISHED, init=False)
    timeframe: str = ""
    strategy_label: str = ""
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    n_trades: int = 0

    def to_slack_payload(self) -> Dict[str, Any]:
        status_text = "[PROFIT]" if self.total_return_pct > 0 else "[LOSS]"
        return {
            "text": f"{status_text} Strategy Finished — {self.strategy_label}",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{status_text} *Strategy Backtest Complete*\n"
                        f"*Strategy:* `{self.strategy_label}`\n"
                        f"*Total Return:* `{self.total_return_pct:+.1f}%`\n"
                        f"*Sharpe Ratio:* `{self.sharpe_ratio:.2f}`\n"
                        f"*Max Drawdown:* `{self.max_drawdown_pct:.1f}%`\n"
                        f"*Total Trades:* `{self.n_trades}`"
                    ),
                },
            }],
        }


@dataclass
class BuySignalEvent(BaseEvent):
    """Fired when a golden cross (buy signal) is detected."""
    event_type: EventType = field(default=EventType.BUY_SIGNAL, init=False)
    timeframe: str = ""
    timestamp_candle: Optional[str] = None
    entry_price: float = 0.0
    fast_ma: float = 0.0
    slow_ma: float = 0.0

    def to_slack_payload(self) -> Dict[str, Any]:
        return {
            "text": f"BUY Signal — BTC/USDT [{self.timeframe}] @ ${self.entry_price:,.0f}",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*BUY Signal — Golden Cross*\n"
                        f"*Asset:* BTC/USDT | *Timeframe:* {self.timeframe}\n"
                        f"*Entry Price:* `${self.entry_price:,.2f}`\n"
                        f"*Fast MA:* `${self.fast_ma:,.2f}` | *Slow MA:* `${self.slow_ma:,.2f}`\n"
                        f"*Bar Time:* {self.timestamp_candle}"
                    ),
                },
            }],
        }


@dataclass
class SellSignalEvent(BaseEvent):
    """Fired when a death cross (sell signal) is detected."""
    event_type: EventType = field(default=EventType.SELL_SIGNAL, init=False)
    timeframe: str = ""
    timestamp_candle: Optional[str] = None
    exit_price: float = 0.0
    fast_ma: float = 0.0
    slow_ma: float = 0.0

    def to_slack_payload(self) -> Dict[str, Any]:
        return {
            "text": f"SELL Signal — BTC/USDT [{self.timeframe}] @ ${self.exit_price:,.0f}",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*SELL Signal — Death Cross*\n"
                        f"*Asset:* BTC/USDT | *Timeframe:* {self.timeframe}\n"
                        f"*Exit Price:* `${self.exit_price:,.2f}`\n"
                        f"*Fast MA:* `${self.fast_ma:,.2f}` | *Slow MA:* `${self.slow_ma:,.2f}`\n"
                        f"*Bar Time:* {self.timestamp_candle}"
                    ),
                },
            }],
        }


@dataclass
class TradeClosedEvent(BaseEvent):
    """Fired when a complete round-trip trade (entry + exit) is logged."""
    event_type: EventType = field(default=EventType.TRADE_CLOSED, init=False)
    timeframe: str = ""
    trade_id: int = 0
    return_pct: float = 0.0
    profit_loss_usd: float = 0.0
    holding_hours: int = 0
    exit_reason: str = ""

    def to_slack_payload(self) -> Dict[str, Any]:
        outcome = "PROFIT" if self.return_pct > 0 else "LOSS"
        return {
            "text": f"Trade #{self.trade_id} closed: {self.return_pct:+.2f}%",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Trade #{self.trade_id} Closed — {outcome}*\n"
                        f"*Return:* `{self.return_pct:+.2f}%` | "
                        f"*P&L:* `${self.profit_loss_usd:+,.2f}`\n"
                        f"*Held for:* {self.holding_hours}h | "
                        f"*Exit reason:* `{self.exit_reason}`"
                    ),
                },
            }],
        }


@dataclass
class DrawdownAlertEvent(BaseEvent):
    """Fired when portfolio drawdown exceeds the warning threshold."""
    event_type: EventType = field(default=EventType.DRAWDOWN_ALERT, init=False)
    timeframe: str = ""
    current_drawdown_pct: float = 0.0
    threshold_pct: float = 0.0

    def to_slack_payload(self) -> Dict[str, Any]:
        return {
            "text": f"Drawdown Alert [{self.timeframe}]: {self.current_drawdown_pct:.1f}%",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Drawdown Alert*\n"
                        f"*Timeframe:* {self.timeframe}\n"
                        f"*Current Drawdown:* `{self.current_drawdown_pct:.1f}%`\n"
                        f"*Alert Threshold:* `{self.threshold_pct:.1f}%`"
                    ),
                },
            }],
        }


@dataclass
class RiskThresholdBreachedEvent(BaseEvent):
    """Fired when portfolio drawdown exceeds the risk limit. Critical alert."""
    event_type: EventType = field(default=EventType.RISK_THRESHOLD_BREACHED, init=False)
    timeframe: str = ""
    current_drawdown_pct: float = 0.0
    risk_threshold_pct: float = 0.0

    def to_slack_payload(self) -> Dict[str, Any]:
        return {
            "text": f"RISK BREACH [{self.timeframe}]: Drawdown {self.current_drawdown_pct:.1f}% exceeds limit",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*RISK THRESHOLD BREACHED*\n"
                        f"*Timeframe:* {self.timeframe}\n"
                        f"*Current Drawdown:* `{self.current_drawdown_pct:.1f}%`\n"
                        f"*Risk Limit:* `{self.risk_threshold_pct:.1f}%`\n"
                        f"*Action required:* Review position and consider halting."
                    ),
                },
            }],
        }
