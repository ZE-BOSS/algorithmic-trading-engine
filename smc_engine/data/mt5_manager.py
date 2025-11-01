"""
MetaTrader5 integration for live trading and historical data.
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Literal
import logging
from dataclasses import dataclass

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Result of an order placement."""
    success: bool
    ticket: Optional[int]
    price: Optional[float]
    volume: float
    message: str
    raw_response: Optional[Dict[str, Any]] = None


class MT5Manager:
    """
    MetaTrader5 connection and trading manager.
    
    Provides:
    - Connection management
    - Historical data retrieval
    - Order placement and management
    - Account information
    - Dry-run simulation mode
    """
    
    def __init__(self, dry_run: bool = True):
        """
        Initialize MT5 manager.
        
        Args:
            dry_run: If True, simulate orders without actual execution
        """
        self.dry_run = dry_run
        self.connected = False
        self.account_info = None
        
        if not dry_run and not settings.validate_mt5_config():
            logger.warning("MT5 configuration incomplete. Running in dry-run mode.")
            self.dry_run = True

    def resolve_symbol(self, symbol):
        """Try to find the actual broker symbol (handles suffixes like EURUSDm)."""
        all_symbols = mt5.symbols_get()
        if not all_symbols:
            return symbol
        for s in all_symbols:
            if s.name.startswith(symbol):
                return s.name
        return symbol
    
    def connect(self) -> bool:
        """
        Connect to MetaTrader5 terminal.
        
        Returns:
            True if connection successful, False otherwise
        
        Raises:
            RuntimeError: If MT5 package not installed or connection fails
        """
        if self.dry_run:
            logger.info("MT5Manager in dry-run mode - no actual connection")
            self.connected = True
            return True
        
        try:
            # Initialize MT5
            if not mt5.initialize():
                error = mt5.last_error()
                raise RuntimeError(f"MT5 initialization failed: {error}")
            
            # Login to account
            if not mt5.login(
                login=settings.mt5_login,
                password=settings.mt5_password,
                server=settings.mt5_server
            ):
                error = mt5.last_error()
                raise RuntimeError(f"MT5 login failed: {error}")
            
            # Get account info
            account = mt5.account_info()
            if account is None:
                raise RuntimeError("Failed to get account info")
            
            self.account_info = account._asdict()
            self.connected = True
            
            logger.info(f"Connected to MT5 account {settings.mt5_login}")
            logger.info(f"Balance: {self.account_info['balance']}, "
                       f"Equity: {self.account_info['equity']}")
            
            return True
        
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from MetaTrader5."""
        if not self.dry_run and self.connected:
            mt5.shutdown()
            logger.info("Disconnected from MT5")
        
        self.connected = False
    
    def get_historical(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame:
        """
        Retrieve historical OHLC data.
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            timeframe: Timeframe ('M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1')
            start: Start datetime (timezone-aware)
            end: End datetime (timezone-aware)
        
        Returns:
            DataFrame with columns: ['time', 'open', 'high', 'low', 'close', 'volume']
            Index is datetime
        
        Raises:
            ValueError: If symbol or timeframe invalid
            RuntimeError: If data retrieval fails
        """
        if self.dry_run:
            logger.warning("Dry-run mode: returning empty DataFrame")
            return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        if not self.connected:
            raise RuntimeError("Not connected to MT5")
        
        # Map timeframe string to MT5 constant
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
        }
        
        if timeframe not in timeframe_map:
            raise ValueError(f"Invalid timeframe: {timeframe}")
        
        tf = timeframe_map[timeframe]

        symbolm = self.resolve_symbol(symbol)

        mt5.symbol_select(symbolm, True)

        if isinstance(start, str):
            try:
                start = datetime.fromisoformat(start)
            except ValueError:
                start = datetime.strptime(start, "%Y-%m-%d")
        if isinstance(end, str):
            try:
                end = datetime.fromisoformat(end)
            except ValueError:
                end = datetime.strptime(end, "%Y-%m-%d")

        logger.warning(f'mt5 parameters: (symbol: {symbolm}, timeframe: {tf}, start: {start}, end: {end})')
        
        # Get rates
        rates = mt5.copy_rates_range(symbolm, tf, start, end)
        
        if rates is None or len(rates) == 0:
            error = mt5.last_error()
            raise RuntimeError(f"Failed to get historical data: {error}")
        
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        # Ensure timezone awareness
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        
        logger.info(f"Retrieved {len(df)} bars for {symbol} {timeframe}")
        
        return df
    
    def place_order(
        self,
        symbol: str,
        side: Literal['buy', 'sell'],
        volume: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        order_type: Literal['market', 'limit'] = 'market',
        comment: str = "SMC Engine"
    ) -> OrderResult:
        """
        Place a trading order.
        
        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            volume: Order volume (lots)
            price: Limit price (for limit orders)
            sl: Stop loss price
            tp: Take profit price
            order_type: 'market' or 'limit'
            comment: Order comment
        
        Returns:
            OrderResult with execution details
        """
        # Safety checks
        if not self._check_trading_allowed():
            return OrderResult(
                success=False,
                ticket=None,
                price=None,
                volume=volume,
                message="Trading not allowed (safety checks failed)"
            )
        
        if self.dry_run:
            # Simulate order
            return self.simulate_order(symbol, side, volume, price, sl, tp, order_type)
        
        if not self.connected:
            return OrderResult(
                success=False,
                ticket=None,
                price=None,
                volume=volume,
                message="Not connected to MT5"
            )
        
        # Prepare order request
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return OrderResult(
                success=False,
                ticket=None,
                price=None,
                volume=volume,
                message=f"Symbol {symbol} not found"
            )
        
        # Get current price if not provided
        if price is None:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return OrderResult(
                    success=False,
                    ticket=None,
                    price=None,
                    volume=volume,
                    message="Failed to get current price"
                )
            price = tick.ask if side == 'buy' else tick.bid
        
        # Determine order type
        if order_type == 'market':
            mt5_order_type = mt5.ORDER_TYPE_BUY if side == 'buy' else mt5.ORDER_TYPE_SELL
        else:
            mt5_order_type = mt5.ORDER_TYPE_BUY_LIMIT if side == 'buy' else mt5.ORDER_TYPE_SELL_LIMIT
        
        # Create order request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_order_type,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp
        
        # Send order
        result = mt5.order_send(request)
        
        if result is None:
            return OrderResult(
                success=False,
                ticket=None,
                price=None,
                volume=volume,
                message="Order send failed"
            )
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success=False,
                ticket=None,
                price=None,
                volume=volume,
                message=f"Order failed: {result.comment}",
                raw_response=result._asdict()
            )
        
        logger.info(f"Order placed: {side} {volume} {symbol} @ {result.price}")
        
        return OrderResult(
            success=True,
            ticket=result.order,
            price=result.price,
            volume=volume,
            message="Order executed successfully",
            raw_response=result._asdict()
        )
    
    def simulate_order(
        self,
        symbol: str,
        side: Literal['buy', 'sell'],
        volume: float,
        price: Optional[float],
        sl: Optional[float],
        tp: Optional[float],
        order_type: str
    ) -> OrderResult:
        """
        Simulate order execution (dry-run mode).
        
        Returns expected fill price and simulated ticket.
        """
        import random
        
        # Simulate price if not provided
        if price is None:
            price = 1.1000  # Dummy price
        
        # Simulate slippage
        slippage_pips = random.uniform(-2, 2) / 10000
        fill_price = price + slippage_pips
        
        # Generate fake ticket
        ticket = random.randint(100000, 999999)
        
        logger.info(f"[DRY-RUN] Order simulated: {side} {volume} {symbol} @ {fill_price}")
        
        return OrderResult(
            success=True,
            ticket=ticket,
            price=fill_price,
            volume=volume,
            message="Order simulated (dry-run mode)"
        )
    
    def close_position(self, ticket: Optional[int] = None, symbol: Optional[str] = None) -> OrderResult:
        """
        Close an open position.
        
        Args:
            ticket: Position ticket to close
            symbol: Symbol to close all positions for
        
        Returns:
            OrderResult with closure details
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Position close simulated: ticket={ticket}, symbol={symbol}")
            return OrderResult(
                success=True,
                ticket=ticket,
                price=None,
                volume=0.0,
                message="Position close simulated (dry-run mode)"
            )
        
        if not self.connected:
            return OrderResult(
                success=False,
                ticket=None,
                price=None,
                volume=0.0,
                message="Not connected to MT5"
            )
        
        # Implementation would use mt5.Close or mt5.positions_get
        # For brevity, returning placeholder
        logger.warning("close_position not fully implemented")
        return OrderResult(
            success=False,
            ticket=None,
            price=None,
            volume=0.0,
            message="Not implemented"
        )
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current account information.
        
        Returns:
            Dictionary with account details or None
        """
        if self.dry_run:
            return {
                'balance': 10000.0,
                'equity': 10000.0,
                'margin': 0.0,
                'free_margin': 10000.0,
                'leverage': 100
            }
        
        if not self.connected:
            return None
        
        account = mt5.account_info()
        if account is None:
            return None
        
        return account._asdict()
    
    def _check_trading_allowed(self) -> bool:
        """
        Check if trading is allowed based on safety rules.
        
        Returns:
            True if trading allowed, False otherwise
        """
        if not settings.live_trading and not self.dry_run:
            logger.warning("Live trading disabled in settings")
            return False
        
        # Check account info
        account = self.get_account_info()
        if account is None:
            return False
        
        # Check margin
        if account['margin'] > account['equity'] * 0.8:
            logger.warning("Margin usage too high")
            return False
        
        # Additional checks can be added here
        # - Daily loss limit
        # - Max open trades
        # - News times
        
        return True
