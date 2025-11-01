"""Unit tests for strategy module."""
import pytest
import pandas as pd
from smc_engine.core.strategy import SMCStrategy


def test_smc_strategy_initialization(sample_params):
    """Test SMC strategy initialization."""
    strategy = SMCStrategy(sample_params)
    
    assert strategy.params == sample_params
    assert hasattr(strategy, 'generate_signals')


def test_smc_strategy_param_validation(sample_params):
    """Test parameter validation."""
    strategy = SMCStrategy(sample_params)
    
    # Should not raise
    strategy.validate_params()
    
    # Test invalid params
    invalid_params = sample_params.copy()
    invalid_params['risk_per_trade'] = 1.5  # > 1.0
    
    with pytest.raises(ValueError):
        invalid_strategy = SMCStrategy(invalid_params)
        invalid_strategy.validate_params()


def test_smc_strategy_default_param_space():
    """Test default parameter space."""
    strategy = SMCStrategy({})
    param_space = strategy.default_param_space()
    
    assert isinstance(param_space, dict)
    assert 'swing_lookback' in param_space
    assert 'risk_per_trade' in param_space


def test_generate_signals(trending_ohlc, sample_params):
    """Test signal generation."""
    strategy = SMCStrategy(sample_params)
    signals = strategy.generate_signals(trending_ohlc)
    
    assert isinstance(signals, pd.DataFrame)
    assert 'signal' in signals.columns
    assert 'price' in signals.columns
    assert 'stop' in signals.columns
    assert 'tp' in signals.columns
    
    # Signals should be valid
    assert signals['signal'].isin(['buy', 'sell', 'none']).all()
    
    # Prices should be positive
    buy_signals = signals[signals['signal'] == 'buy']
    if len(buy_signals) > 0:
        assert (buy_signals['price'] > 0).all()
        assert (buy_signals['stop'] > 0).all()
        assert (buy_signals['tp'] > 0).all()


def test_signal_logic_consistency(trending_ohlc, sample_params):
    """Test that signals are logically consistent."""
    strategy = SMCStrategy(sample_params)
    signals = strategy.generate_signals(trending_ohlc)
    
    # For buy signals, TP should be above entry and SL below
    buy_signals = signals[signals['signal'] == 'buy']
    for _, signal in buy_signals.iterrows():
        assert signal['tp'] > signal['price'], "TP should be above entry for buy"
        assert signal['stop'] < signal['price'], "SL should be below entry for buy"
    
    # For sell signals, TP should be below entry and SL above
    sell_signals = signals[signals['signal'] == 'sell']
    for _, signal in sell_signals.iterrows():
        assert signal['tp'] < signal['price'], "TP should be below entry for sell"
        assert signal['stop'] > signal['price'], "SL should be above entry for sell"
