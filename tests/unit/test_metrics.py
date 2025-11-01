"""Unit tests for metrics calculation."""
import pytest
import pandas as pd
import numpy as np
from smc_engine.backtest.metrics import calculate_metrics


def test_calculate_metrics_basic():
    """Test basic metrics calculation."""
    # Create sample trades
    trades = pd.DataFrame({
        'pnl': [100, -50, 150, -30, 200],
        'entry_ts': pd.date_range('2020-01-01', periods=5, freq='D'),
        'exit_ts': pd.date_range('2020-01-02', periods=5, freq='D'),
        'cum_equity': [10100, 10050, 10200, 10170, 10370]
    })
    
    initial_balance = 10000
    
    metrics = calculate_metrics(trades, initial_balance)
    
    assert 'net_profit' in metrics
    assert 'total_trades' in metrics
    assert 'win_rate' in metrics
    assert 'profit_factor' in metrics
    assert 'sharpe_ratio' in metrics
    assert 'max_drawdown_pct' in metrics
    
    # Validate calculations
    assert metrics['net_profit'] == 370
    assert metrics['total_trades'] == 5
    assert metrics['win_rate'] == 60.0  # 3 wins out of 5
    assert metrics['profit_factor'] > 1.0


def test_calculate_metrics_all_wins():
    """Test metrics with all winning trades."""
    trades = pd.DataFrame({
        'pnl': [100, 50, 150, 30, 200],
        'entry_ts': pd.date_range('2020-01-01', periods=5, freq='D'),
        'exit_ts': pd.date_range('2020-01-02', periods=5, freq='D'),
        'cum_equity': [10100, 10150, 10300, 10330, 10530]
    })
    
    metrics = calculate_metrics(trades, 10000)
    
    assert metrics['win_rate'] == 100.0
    assert metrics['profit_factor'] == float('inf')  # No losses


def test_calculate_metrics_all_losses():
    """Test metrics with all losing trades."""
    trades = pd.DataFrame({
        'pnl': [-100, -50, -150, -30, -200],
        'entry_ts': pd.date_range('2020-01-01', periods=5, freq='D'),
        'exit_ts': pd.date_range('2020-01-02', periods=5, freq='D'),
        'cum_equity': [9900, 9850, 9700, 9670, 9470]
    })
    
    metrics = calculate_metrics(trades, 10000)
    
    assert metrics['win_rate'] == 0.0
    assert metrics['profit_factor'] == 0.0


def test_calculate_metrics_empty_trades():
    """Test metrics with no trades."""
    trades = pd.DataFrame(columns=['pnl', 'entry_ts', 'exit_ts', 'cum_equity'])
    
    metrics = calculate_metrics(trades, 10000)
    
    assert metrics['total_trades'] == 0
    assert metrics['net_profit'] == 0
    assert metrics['win_rate'] == 0
