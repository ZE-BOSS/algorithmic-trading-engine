"""
Signal generation helpers and utilities.
"""

import pandas as pd
from typing import Dict, Any


def filter_signals(
    signals: pd.DataFrame,
    min_risk_reward: float = 1.5,
    max_signals_per_day: int = 3
) -> pd.DataFrame:
    """
    Filter signals based on quality criteria.
    
    Args:
        signals: DataFrame with trading signals
        min_risk_reward: Minimum risk-reward ratio
        max_signals_per_day: Maximum signals per day
    
    Returns:
        Filtered DataFrame
    """
    if signals.empty:
        return signals
    
    # Filter by risk-reward
    signals = signals.copy()
    signals['risk'] = abs(signals['price'] - signals['stop'])
    signals['reward'] = abs(signals['tp'] - signals['price'])
    signals['rr_ratio'] = signals['reward'] / signals['risk']
    
    signals = signals[signals['rr_ratio'] >= min_risk_reward]
    
    # Limit signals per day
    signals['date'] = pd.to_datetime(signals['ts']).dt.date
    signals = signals.groupby('date').head(max_signals_per_day)
    
    return signals.drop(columns=['risk', 'reward', 'rr_ratio', 'date'])


def combine_signals(
    *signal_dfs: pd.DataFrame,
    method: str = 'union'
) -> pd.DataFrame:
    """
    Combine multiple signal DataFrames.
    
    Args:
        signal_dfs: Variable number of signal DataFrames
        method: 'union' (all signals) or 'intersection' (only common)
    
    Returns:
        Combined DataFrame
    """
    if not signal_dfs:
        return pd.DataFrame(columns=['ts', 'signal', 'price', 'stop', 'tp', 'meta'])
    
    if method == 'union':
        return pd.concat(signal_dfs, ignore_index=True).sort_values('ts')
    
    elif method == 'intersection':
        # Find common timestamps
        common_ts = set(signal_dfs[0]['ts'])
        for df in signal_dfs[1:]:
            common_ts &= set(df['ts'])
        
        result = signal_dfs[0][signal_dfs[0]['ts'].isin(common_ts)]
        return result.sort_values('ts')
    
    else:
        raise ValueError(f"Unknown method: {method}")
