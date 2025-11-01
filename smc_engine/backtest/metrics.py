"""
Performance metrics calculation.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List


@dataclass
class MetricsResult:
    """Container for backtest performance metrics."""
    net_profit: float
    total_return_pct: float
    max_drawdown_pct: float
    max_drawdown_abs: float
    sharpe_ratio: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    expectancy: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    monthly_returns: List[float]
    final_equity: float

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'net_profit': self.net_profit,
            'total_return_pct': self.total_return_pct,
            'max_drawdown_pct': self.max_drawdown_pct,
            'max_drawdown_abs': self.max_drawdown_abs,
            'sharpe_ratio': self.sharpe_ratio,
            'calmar_ratio': self.calmar_ratio,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'expectancy': self.expectancy,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'monthly_returns': self.monthly_returns,
            'final_equity': self.final_equity
        }


def calculate_metrics(
    trades_df: pd.DataFrame,
    equity_series: pd.Series,
    initial_balance: float
) -> MetricsResult:
    """
    Calculate comprehensive performance metrics.

    Args:
        trades_df: DataFrame with trade data. Expected columns include 'pnl', 'exit_ts' (timestamp).
        equity_series: Series indexed by timestamp with equity values over time (monotonic time index).
        initial_balance: Starting balance

    Returns:
        MetricsResult with all metrics
    """
    # Normalize inputs
    if equity_series is None or len(equity_series) == 0:
        final_equity = initial_balance
    else:
        # equity_series might be a DataFrame column or Series; ensure Series
        equity_series = pd.Series(equity_series).dropna()
        final_equity = float(equity_series.iloc[-1]) if len(equity_series) > 0 else initial_balance

    if trades_df is None or trades_df.empty:
        return MetricsResult(
            net_profit=final_equity - initial_balance,
            total_return_pct=((final_equity - initial_balance) / initial_balance * 100 if initial_balance != 0 else 0.0),
            max_drawdown_pct=0.0,
            max_drawdown_abs=0.0,
            sharpe_ratio=0.0,
            calmar_ratio=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            expectancy=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_win=0.0,
            avg_loss=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            monthly_returns=[],
            final_equity=final_equity
        )

    # Ensure exit_ts is datetime
    if 'exit_ts' in trades_df.columns:
        trades_df = trades_df.copy()
        trades_df['exit_ts'] = pd.to_datetime(trades_df['exit_ts'])

    # Basic trade counts
    total_trades = int(len(trades_df))
    wins = trades_df[trades_df['pnl'] > 0]['pnl'] if 'pnl' in trades_df.columns else pd.Series(dtype=float)
    losses = trades_df[trades_df['pnl'] < 0]['pnl'] if 'pnl' in trades_df.columns else pd.Series(dtype=float)
    winning_trades = int(len(wins))
    losing_trades = int(len(losses))
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

    # P&L metrics
    net_profit = float(trades_df['pnl'].sum()) if 'pnl' in trades_df.columns else final_equity - initial_balance
    total_return_pct = ((final_equity - initial_balance) / initial_balance * 100) if initial_balance != 0 else 0.0

    avg_win = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.mean()) if not losses.empty else 0.0
    largest_win = float(wins.max()) if not wins.empty else 0.0
    largest_loss = float(losses.min()) if not losses.empty else 0.0

    gross_profit = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = float(abs(losses.sum())) if not losses.empty else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (np.inf if gross_profit > 0 else 0.0)

    expectancy = float(trades_df['pnl'].mean()) if 'pnl' in trades_df.columns and total_trades > 0 else 0.0

    # Drawdown (using equity_series if available)
    max_drawdown_abs = 0.0
    max_drawdown_pct = 0.0
    sharpe_ratio = 0.0
    calmar_ratio = 0.0

    if equity_series is not None and len(equity_series) > 0:
        es = pd.Series(equity_series).astype(float)
        es.index = pd.to_datetime(es.index)
        running_max = es.cummax()
        drawdown = es - running_max
        max_drawdown_abs = float(drawdown.min()) if len(drawdown) > 0 else 0.0
        peak_val = running_max.max() if len(running_max) > 0 else initial_balance
        max_drawdown_pct = (abs(max_drawdown_abs) / peak_val * 100) if peak_val != 0 else 0.0

        # Compute returns for Sharpe: prefer daily returns if we have intraday series
        # Resample to daily last equity
        try:
            daily = es.resample('D').last().dropna()
            if len(daily) >= 2:
                daily_ret = daily.pct_change().dropna()
                if daily_ret.std() > 0:
                    sharpe_ratio = float((daily_ret.mean() / daily_ret.std()) * np.sqrt(252))
                else:
                    sharpe_ratio = 0.0
            else:
                # Fallback to using series percent change
                ret = es.pct_change().dropna()
                if len(ret) > 1 and ret.std() > 0:
                    sharpe_ratio = float((ret.mean() / ret.std()) * np.sqrt(252))
                else:
                    sharpe_ratio = 0.0
        except Exception:
            sharpe_ratio = 0.0

    # Calmar ratio: annualized return / max drawdown %
    calmar_ratio = (total_return_pct / max_drawdown_pct) if max_drawdown_pct != 0 else 0.0

    # Monthly returns (based on trades exits)
    monthly_returns = []
    if 'exit_ts' in trades_df.columns and 'pnl' in trades_df.columns:
        trades_df['month'] = trades_df['exit_ts'].dt.to_period('M')
        monthly_pnl = trades_df.groupby('month')['pnl'].sum()
        monthly_returns = ((monthly_pnl / initial_balance) * 100).tolist()

    return MetricsResult(
        net_profit=net_profit,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        max_drawdown_abs=abs(max_drawdown_abs),
        sharpe_ratio=sharpe_ratio,
        calmar_ratio=calmar_ratio,
        win_rate=win_rate,
        profit_factor=profit_factor if np.isfinite(profit_factor) else 0.0,
        expectancy=expectancy,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        avg_win=avg_win,
        avg_loss=avg_loss,
        largest_win=largest_win,
        largest_loss=largest_loss,
        monthly_returns=monthly_returns,
        final_equity=final_equity
    )
