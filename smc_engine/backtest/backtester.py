"""
Backtesting engine with realistic order simulation.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import logging

from ..core.strategy import Strategy
from .simulator import OrderSimulator
from .metrics import calculate_metrics, MetricsResult

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a completed trade."""
    index: int
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    fees: float
    cum_equity: float
    exit_reason: str
    meta: Dict[str, Any]
    # additional per-trade reporting fields
    entry_balance: float = 0.0
    exit_balance: float = 0.0
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    max_drawdown_at_exit: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        d = asdict(self)
        d['entry_ts'] = str(self.entry_ts)
        d['exit_ts'] = str(self.exit_ts)
        return d


class Backtester:
    """
    Backtesting engine for trading strategies.

    Features:
    - Realistic order simulation with slippage and spread
    - Position sizing based on risk fraction (if position_size <= 1.0)
    - Stop loss and take profit management
    - Per-trade and aggregate metrics
    - Equity curve tracking
    """

    def __init__(
        self,
        strategy: Strategy,
        initial_balance: float = 10000.0,
        commission: float = 0.0001,
        slippage: float = 0.0001,
        spread: float = 0.0002,
        position_size: float = 0.01,
        max_positions: int = 1,
        instrument_multiplier: float = 100000.0
    ):
        self.strategy = strategy
        self.initial_balance = float(initial_balance)
        self.commission = float(commission)
        self.slippage = float(slippage)
        self.spread = float(spread)
        self.position_size = float(position_size)
        self.max_positions = int(max_positions)
        self.instrument_multiplier = float(instrument_multiplier)

        self.simulator = OrderSimulator(commission, slippage, spread)

        self.balance = float(initial_balance)
        self.equity = float(initial_balance)
        self.trades: List[Trade] = []
        self.open_positions: List[Dict[str, Any]] = []
        self.equity_curve_points: List[Dict[str, Any]] = []

    # ------------------------------------------------------------
    # Main backtest loop
    # ------------------------------------------------------------
    def run(self, ohlc: pd.DataFrame) -> Dict[str, Any]:
        logger.info(f"Starting backtest on {len(ohlc)} bars")

        signals = self.strategy.generate_signals(ohlc)
        if signals is None or (hasattr(signals, "empty") and signals.empty):
            return self._empty_result()

        self.balance = self.initial_balance
        self.trades = []
        self.open_positions = []
        self.equity_curve_points = []

        signals_by_ts = {}
        if isinstance(signals, pd.DataFrame):
            for _, row in signals.iterrows():
                ts = pd.to_datetime(row["ts"])
                signals_by_ts.setdefault(ts, []).append(row)

        for i in range(len(ohlc)):
            bar = ohlc.iloc[i]
            ts = ohlc.index[i]

            # exits first
            self._check_exits(bar, ts)

            # entries
            if len(self.open_positions) < self.max_positions:
                if pd.to_datetime(ts) in signals_by_ts:
                    for row in signals_by_ts[pd.to_datetime(ts)]:
                        if len(self.open_positions) >= self.max_positions:
                            break
                        self._enter_position(row, bar, ts)

            # update equity
            self.equity = self.balance + self._calculate_open_pnl(bar)
            self.equity_curve_points.append({"time": ts, "equity": self.equity})

            if self.balance <= 0 or self.equity <= 0:
                logger.warning("Account depleted — ending early.")
                break

        # force close all
        if self.open_positions:
            final_bar = ohlc.iloc[-1]
            final_ts = ohlc.index[-1]
            for pos in self.open_positions[:]:
                self._exit_position(pos, final_bar, final_ts, "end_of_data")

        equity_df = pd.DataFrame(self.equity_curve_points).set_index("time")
        equity_series = equity_df["equity"] if "equity" in equity_df else pd.Series(dtype=float)
        metrics = self._calculate_metrics(ohlc, equity_series)

        return {"trades": self.trades, "metrics": metrics, "equity_curve": equity_df}

    # ------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------
    def _enter_position(self, signal: pd.Series, bar: pd.Series, ts: pd.Timestamp):
        side = signal["signal"]
        entry_price = float(signal["price"])
        stop_loss = float(signal["stop"])
        take_profit = float(signal["tp"])
        meta = signal.get("meta", {})

        # simulate fill realistically
        fill_price = self.simulator.simulate_fill(side, entry_price)

        stop_distance = abs(fill_price - stop_loss)
        if stop_distance <= 0:
            return

        if self.position_size <= 1.0:
            risk_amount = self.balance * self.position_size
            risk_per_unit = stop_distance * self.instrument_multiplier
            if risk_per_unit <= 0:
                return
            size = risk_amount / risk_per_unit
        else:
            size = float(self.position_size)
            risk_amount = stop_distance * size * self.instrument_multiplier

        if not np.isfinite(size) or size <= 0:
            return

        commission_cost = self.simulator.calculate_commission(fill_price, size)
        self.balance -= commission_cost

        position = {
            "side": side,
            "entry_ts": ts,
            "entry_price": fill_price,
            "size": size,
            "stop": stop_loss,
            "tp": take_profit,
            "commission": commission_cost,
            "meta": meta,
            "instrument_multiplier": self.instrument_multiplier,
            "risk_amount": risk_amount,
            "risk_pct": (risk_amount / max(self.balance, 1e-12)) if self.balance > 0 else 0.0
        }

        self.open_positions.append(position)

    def _exit_position(self, position: Dict[str, Any], bar: pd.Series, ts: pd.Timestamp, reason: str):
        side = position["side"]
        entry_price = position["entry_price"]
        size = float(position["size"])
        entry_ts = position["entry_ts"]
        entry_balance = float(self.balance + self._calculate_open_pnl(bar))

        if reason == "stop_loss":
            exit_price = float(position["stop"])
        elif reason == "take_profit":
            exit_price = float(position["tp"])
        else:
            exit_price = self.simulator.simulate_fill("sell" if side == "buy" else "buy", float(bar["close"]))

        if side == "buy":
            pnl = (exit_price - entry_price) * size * position.get("instrument_multiplier", self.instrument_multiplier)
        else:
            pnl = (entry_price - exit_price) * size * position.get("instrument_multiplier", self.instrument_multiplier)

        exit_commission = self.simulator.calculate_commission(exit_price, size)
        pnl -= exit_commission

        self.balance += pnl
        total_fees = position.get("commission", 0.0) + exit_commission

        max_dd_at_exit = 0.0
        if self.equity_curve_points:
            es = pd.Series([p["equity"] for p in self.equity_curve_points], index=[p["time"] for p in self.equity_curve_points])
            running_max = es.cummax()
            dd = es - running_max
            max_dd_at_exit = float(dd.min()) if len(dd) > 0 else 0.0

        trade = Trade(
            index=len(self.trades),
            entry_ts=entry_ts,
            exit_ts=ts,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=float(pnl),
            fees=float(total_fees),
            cum_equity=float(self.balance),
            exit_reason=reason,
            meta=position.get("meta", {}),
            entry_balance=float(position.get("entry_balance", entry_balance)),
            exit_balance=float(self.balance),
            risk_amount=float(position.get("risk_amount", 0.0)),
            risk_pct=float(position.get("risk_pct", 0.0)),
            max_drawdown_at_exit=abs(max_dd_at_exit)
        )

        self.trades.append(trade)
        try:
            self.open_positions.remove(position)
        except ValueError:
            pass

    # ------------------------------------------------------------
    # Supporting methods
    # ------------------------------------------------------------
    def _check_exits(self, bar: pd.Series, ts: pd.Timestamp):
        for pos in self.open_positions[:]:
            side = pos["side"]
            if side == "buy" and bar["low"] <= pos["stop"]:
                self._exit_position(pos, bar, ts, "stop_loss")
            elif side == "sell" and bar["high"] >= pos["stop"]:
                self._exit_position(pos, bar, ts, "stop_loss")
            elif side == "buy" and bar["high"] >= pos["tp"]:
                self._exit_position(pos, bar, ts, "take_profit")
            elif side == "sell" and bar["low"] <= pos["tp"]:
                self._exit_position(pos, bar, ts, "take_profit")

    def _calculate_open_pnl(self, bar: pd.Series) -> float:
        total_pnl = 0.0
        for pos in self.open_positions:
            current_price = float(bar["close"])
            entry_price = pos["entry_price"]
            size = float(pos["size"])
            multiplier = pos.get("instrument_multiplier", self.instrument_multiplier)
            if pos["side"] == "buy":
                pnl = (current_price - entry_price) * size * multiplier
            else:
                pnl = (entry_price - current_price) * size * multiplier
            total_pnl += pnl
        return float(total_pnl)

    def _calculate_metrics(self, ohlc: pd.DataFrame, equity_series: pd.Series) -> MetricsResult:
        if not self.trades:
            return MetricsResult(
                net_profit=0.0, total_return_pct=0.0,
                max_drawdown_pct=0.0, max_drawdown_abs=0.0,
                sharpe_ratio=0.0, calmar_ratio=0.0,
                win_rate=0.0, profit_factor=0.0, expectancy=0.0,
                total_trades=0, winning_trades=0, losing_trades=0,
                avg_win=0.0, avg_loss=0.0, largest_win=0.0,
                largest_loss=0.0, monthly_returns=[], final_equity=self.balance
            )

        trades_df = pd.DataFrame([t.to_dict() for t in self.trades])
        if isinstance(equity_series, pd.Series) and not equity_series.empty:
            es = equity_series
        else:
            es = pd.Series([t.cum_equity for t in self.trades], index=[pd.to_datetime(t.exit_ts) for t in self.trades])

        return calculate_metrics(trades_df, es, self.initial_balance)

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "trades": [],
            "metrics": MetricsResult(
                net_profit=0.0, total_return_pct=0.0,
                max_drawdown_pct=0.0, max_drawdown_abs=0.0,
                sharpe_ratio=0.0, calmar_ratio=0.0,
                win_rate=0.0, profit_factor=0.0, expectancy=0.0,
                total_trades=0, winning_trades=0, losing_trades=0,
                avg_win=0.0, avg_loss=0.0, largest_win=0.0,
                largest_loss=0.0, monthly_returns=[], final_equity=self.initial_balance
            ),
            "equity_curve": pd.DataFrame(columns=["equity"])
        }

    def report(self) -> str:
        """Generate a text report of backtest results."""
        if not self.trades:
            return "No trades executed."

        metrics = self._calculate_metrics(None, pd.Series([t.cum_equity for t in self.trades], index=[pd.to_datetime(t.exit_ts) for t in self.trades]))

        report = f"""
            === Backtest Report ===
            Initial Balance: ${self.initial_balance:,.2f}
            Final Equity: ${self.balance:,.2f}
            Net Profit: ${metrics.net_profit:,.2f}
            Total Return: {metrics.total_return_pct:.2f}%

            Risk Metrics:
            Max Drawdown: {metrics.max_drawdown_pct:.2f}% (${metrics.max_drawdown_abs:,.2f})
            Sharpe Ratio: {metrics.sharpe_ratio:.2f}
            Calmar Ratio: {metrics.calmar_ratio:.2f}

            Trade Statistics:
            Total Trades: {metrics.total_trades}
            Winning Trades: {metrics.winning_trades}
            Losing Trades: {metrics.losing_trades}
            Win Rate: {metrics.win_rate:.2f}%
            Profit Factor: {metrics.profit_factor:.2f}
            Expectancy: ${metrics.expectancy:.2f}

            Average Win: ${metrics.avg_win:.2f}
            Average Loss: ${metrics.avg_loss:.2f}
            Largest Win: ${metrics.largest_win:.2f}
            Largest Loss: ${metrics.largest_loss:.2f}
        """

        return report
