"""
Market data provider - unified interface for CSV, DB, and MT5 data.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal
import logging

from .mt5_manager import MT5Manager

logger = logging.getLogger(__name__)


class MarketDataProvider:
    """
    Unified market data provider.
    
    Supports:
    - CSV files
    - Database queries
    - MT5 live data
    """
    
    def __init__(self, source: Literal['csv', 'db', 'mt5'] = 'csv'):
        """
        Initialize market data provider.
        
        Args:
            source: Data source type
        """
        self.source = source
        self.mt5_manager = None
        
        if source == 'mt5':
            self.mt5_manager = MT5Manager(dry_run=False)
    
    def get_data(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        csv_path: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get OHLC data from configured source.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start: Start datetime
            end: End datetime
            csv_path: Path to CSV file (for csv source)
        
        Returns:
            DataFrame with OHLC data and datetime index
        """
        if self.source == 'csv':
            return self._load_from_csv(csv_path)
        
        elif self.source == 'mt5':
            if self.mt5_manager is None:
                raise RuntimeError(f"MT5 manager not initialized: ")
            
            if not self.mt5_manager.connected:
                self.mt5_manager.connect()
            
            return self.mt5_manager.get_historical(symbol, timeframe, start, end)
        
        elif self.source == 'db':
            # Placeholder for database query
            raise NotImplementedError("Database source not yet implemented")
        
        else:
            raise ValueError(f"Unknown source: {self.source}")
    
    def _load_from_csv(self, csv_path: str) -> pd.DataFrame:
        """
        Load OHLC data from CSV file.
        
        Expected CSV format:
        - Columns: time, open, high, low, close, volume
        - time column should be parseable as datetime
        
        Args:
            csv_path: Path to CSV file
        
        Returns:
            DataFrame with OHLC data
        """
        if not csv_path:
            raise ValueError("csv_path required for CSV source")
        
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        df = pd.read_csv(csv_path)
        
        # Ensure required columns
        required = ['time', 'open', 'high', 'low', 'close']
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Parse time column
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        
        # Ensure timezone awareness
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        
        logger.info(f"Loaded {len(df)} bars from {csv_path}")
        
        return df
