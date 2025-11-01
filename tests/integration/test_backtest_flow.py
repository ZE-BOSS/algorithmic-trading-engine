"""Integration test for complete backtest flow."""
import pytest
import pandas as pd
from datetime import datetime

from smc_engine.core.strategy import SMCStrategy
from smc_engine.backtest.backtester import Backtester


def test_full_backtest_flow(trending_ohlc, sample_params):
    """Test complete backtest from data to results."""
    # Initialize strategy
    strategy = SMCStrategy(sample_params)
    
    # Initialize backtester
    backtester = Backtester(
        strategy=strategy,
        initial_balance=10000.0,
        commission=0.0001,
        slippage=0.00005,
        spread=0.00002
    )
    
    # Run backtest
    result = backtester.run(trending_ohlc)
    
    # Validate result structure
    assert 'trades' in result
    assert 'metrics' in result
    assert 'equity_curve' in result
    
    # Validate trades
    trades = result['trades']
    assert isinstance(trades, pd.DataFrame)
    
    if len(trades) > 0:
        required_columns = ['entry_ts', 'exit_ts', 'side', 'entry_price', 
                          'exit_price', 'pnl', 'cum_equity']
        for col in required_columns:
            assert col in trades.columns
    
    # Validate metrics
    metrics = result['metrics']
    assert 'net_profit' in metrics
    assert 'total_trades' in metrics
    assert 'win_rate' in metrics
    assert 'sharpe_ratio' in metrics
    assert 'max_drawdown_pct' in metrics
    
    # Validate equity curve
    equity = result['equity_curve']
    assert isinstance(equity, pd.Series)
    assert len(equity) > 0
    assert equity.iloc[0] == 10000.0  # Initial balance


def test_backtest_with_different_params(trending_ohlc):
    """Test backtest with various parameter sets."""
    param_sets = [
        {'swing_lookback': 5, 'risk_per_trade': 0.01, 'atr_period': 10},
        {'swing_lookback': 15, 'risk_per_trade': 0.02, 'atr_period': 20},
        {'swing_lookback': 10, 'risk_per_trade': 0.015, 'atr_period': 14},
    ]
    
    results = []
    
    for params in param_sets:
        strategy = SMCStrategy(params)
        backtester = Backtester(strategy=strategy, initial_balance=10000.0)
        result = backtester.run(trending_ohlc)
        results.append(result['metrics'])
    
    # All should complete without error
    assert len(results) == 3
    
    # Each should have valid metrics
    for metrics in results:
        assert 'net_profit' in metrics
        assert 'total_trades' in metrics


def test_backtest_reproducibility(trending_ohlc, sample_params):
    """Test that backtests are reproducible."""
    strategy = SMCStrategy(sample_params)
    backtester = Backtester(strategy=strategy, initial_balance=10000.0)
    
    # Run twice
    result1 = backtester.run(trending_ohlc)
    result2 = backtester.run(trending_ohlc)
    
    # Results should be identical
    assert result1['metrics']['net_profit'] == result2['metrics']['net_profit']
    assert result1['metrics']['total_trades'] == result2['metrics']['total_trades']
    assert len(result1['trades']) == len(result2['trades'])
