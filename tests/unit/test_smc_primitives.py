"""Unit tests for SMC primitives."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from smc_engine.core.smc_primitives import (
    detect_market_structure,
    is_bos,
    detect_choch,
    find_order_blocks,
    find_fvg,
    detect_liquidity_grab,
    calculate_atr
)


def test_calculate_atr(sample_ohlc):
    """Test ATR calculation."""
    atr = calculate_atr(sample_ohlc, period=14)
    
    assert len(atr) == len(sample_ohlc)
    assert not atr.isna().all()
    assert (atr >= 0).all()


def test_detect_market_structure(trending_ohlc):
    """Test market structure detection."""
    structure = detect_market_structure(trending_ohlc, lookback=10)
    
    assert structure is not None
    assert hasattr(structure, 'swing_highs')
    assert hasattr(structure, 'swing_lows')
    assert len(structure.swing_highs) > 0
    assert len(structure.swing_lows) > 0
    
    # Check swing highs are actually local maxima
    for idx, price in structure.swing_highs:
        window_start = max(0, idx - 10)
        window_end = min(len(trending_ohlc), idx + 11)
        window_highs = trending_ohlc['high'].iloc[window_start:window_end]
        assert price >= window_highs.max() * 0.9999  # Allow small floating point error


def test_is_bos_bullish(trending_ohlc):
    """Test bullish Break of Structure detection."""
    structure = detect_market_structure(trending_ohlc, lookback=10)
    atr = calculate_atr(trending_ohlc, period=14)
    
    # Find a point where price breaks above previous swing high
    if len(structure.swing_highs) >= 2:
        last_swing = structure.swing_highs[-2]
        
        # Check for BOS after the swing
        for i in range(last_swing[0] + 1, len(trending_ohlc)):
            bos = is_bos(
                trending_ohlc.iloc[:i+1],
                last_swing,
                atr.iloc[i],
                direction='bullish',
                atr_margin=0.5
            )
            if bos:
                assert trending_ohlc['close'].iloc[i] > last_swing[1]
                break


def test_find_order_blocks(trending_ohlc):
    """Test order block detection."""
    atr = calculate_atr(trending_ohlc, period=14)
    
    params = {
        'min_impulse_bars': 3,
        'min_impulse_atr': 1.5,
        'ob_expansion_atr': 0.2
    }
    
    order_blocks = find_order_blocks(trending_ohlc, atr, params)
    
    assert isinstance(order_blocks, list)
    
    # If order blocks found, validate structure
    for ob in order_blocks:
        assert ob.type in ['bullish', 'bearish']
        assert ob.price_top >= ob.price_bottom
        assert ob.start_idx < ob.end_idx
        assert ob.strength > 0


def test_find_fvg_imbalance(sample_ohlc):
    """Test Fair Value Gap detection using imbalance method."""
    atr = calculate_atr(sample_ohlc, period=14)
    
    params = {
        'method': 'imbalance',
        'min_gap_atr': 0.3,
        'expand_atr': 0.1
    }
    
    fvgs = find_fvg(sample_ohlc, atr, params)
    
    assert isinstance(fvgs, list)
    
    # Validate FVG structure
    for fvg in fvgs:
        assert fvg.type in ['bullish', 'bearish']
        assert fvg.top > fvg.bottom
        assert 0 <= fvg.index < len(sample_ohlc)


def test_find_fvg_wick(sample_ohlc):
    """Test Fair Value Gap detection using wick method."""
    atr = calculate_atr(sample_ohlc, period=14)
    
    params = {
        'method': 'wick',
        'min_gap_atr': 0.5,
        'expand_atr': 0.0
    }
    
    fvgs = find_fvg(sample_ohlc, atr, params)
    
    assert isinstance(fvgs, list)


def test_detect_liquidity_grab(trending_ohlc):
    """Test liquidity grab detection."""
    structure = detect_market_structure(trending_ohlc, lookback=10)
    atr = calculate_atr(trending_ohlc, period=14)
    
    # Test at various points
    for i in range(50, len(trending_ohlc)):
        grab = detect_liquidity_grab(
            trending_ohlc.iloc[:i+1],
            structure.swing_highs + structure.swing_lows,
            atr.iloc[i],
            threshold_atr=1.0,
            reclaim_bars=3
        )
        
        # If grab detected, it should be boolean
        assert isinstance(grab, bool)


def test_order_block_serialization(trending_ohlc):
    """Test order block to_dict serialization."""
    atr = calculate_atr(trending_ohlc, period=14)
    
    params = {
        'min_impulse_bars': 3,
        'min_impulse_atr': 1.5,
        'ob_expansion_atr': 0.2
    }
    
    order_blocks = find_order_blocks(trending_ohlc, atr, params)
    
    for ob in order_blocks:
        ob_dict = ob.to_dict()
        assert isinstance(ob_dict, dict)
        assert 'type' in ob_dict
        assert 'price_top' in ob_dict
        assert 'price_bottom' in ob_dict
        assert 'strength' in ob_dict


def test_fvg_serialization(sample_ohlc):
    """Test FVG to_dict serialization."""
    atr = calculate_atr(sample_ohlc, period=14)
    
    params = {
        'method': 'imbalance',
        'min_gap_atr': 0.3,
        'expand_atr': 0.1
    }
    
    fvgs = find_fvg(sample_ohlc, atr, params)
    
    for fvg in fvgs:
        fvg_dict = fvg.to_dict()
        assert isinstance(fvg_dict, dict)
        assert 'type' in fvg_dict
        assert 'top' in fvg_dict
        assert 'bottom' in fvg_dict
