"""Pytest configuration and fixtures."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from smc_engine.db.models import Base


@pytest.fixture
def sample_ohlc():
    """Generate sample OHLC data for testing."""
    np.random.seed(42)
    n = 500
    dates = pd.date_range(start='2020-01-01', periods=n, freq='H')
    
    # Generate realistic price data
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0005)
    high = close + np.abs(np.random.randn(n) * 0.0003)
    low = close - np.abs(np.random.randn(n) * 0.0003)
    open_price = close + np.random.randn(n) * 0.0002
    volume = np.random.randint(100, 1000, n)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    return df


@pytest.fixture
def trending_ohlc():
    """Generate trending OHLC data with clear structure."""
    np.random.seed(42)
    n = 200
    dates = pd.date_range(start='2020-01-01', periods=n, freq='H')
    
    # Create uptrend with pullbacks
    trend = np.linspace(1.1000, 1.1200, n)
    noise = np.random.randn(n) * 0.0002
    close = trend + noise
    
    high = close + np.abs(np.random.randn(n) * 0.0003)
    low = close - np.abs(np.random.randn(n) * 0.0003)
    open_price = close + np.random.randn(n) * 0.0001
    volume = np.random.randint(100, 1000, n)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    return df


@pytest.fixture
def test_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


@pytest.fixture
def sample_params():
    """Sample strategy parameters."""
    return {
        'swing_lookback': 10,
        'bos_atr_margin': 0.5,
        'ob_min_impulse_bars': 3,
        'ob_min_impulse_atr': 1.5,
        'fvg_min_gap_atr': 0.3,
        'fvg_method': 'imbalance',
        'liquidity_grab_atr': 1.0,
        'liquidity_reclaim_bars': 3,
        'risk_per_trade': 0.02,
        'risk_reward_ratio': 2.0,
        'atr_period': 14,
        'atr_sl_multiplier': 1.5
    }
