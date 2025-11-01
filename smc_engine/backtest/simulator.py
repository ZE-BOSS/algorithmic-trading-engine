"""
Order execution simulator with realistic market conditions.
"""

from typing import Literal
import random


class OrderSimulator:
    """
    Simulates realistic order execution, including:
    - Slippage (price impact)
    - Bid-ask spread
    - Commission per trade
    """

    def __init__(
        self,
        commission: float = 0.0001,  # e.g. 0.01% per trade
        slippage: float = 0.0001,    # average slippage fraction
        spread: float = 0.0002       # bid/ask spread fraction
    ):
        """
        Initialize order simulator.

        Args:
            commission: Commission rate per trade (fraction of trade value)
            slippage: Average slippage fraction (e.g., 0.0001 = 0.01%)
            spread: Average bid-ask spread fraction (e.g., 0.0002 = 0.02%)
        """
        self.commission = commission
        self.slippage = slippage
        self.spread = spread
        self._half_spread = spread / 2  # precompute for small optimization

    def simulate_fill(
        self,
        side: Literal["buy", "sell"],
        price: float,
        add_randomness: bool = True
    ) -> float:
        """
        Simulate order fill price given slippage and spread.

        Args:
            side: "buy" or "sell"
            price: Mid-market price at time of order
            add_randomness: Whether to randomize slippage slightly

        Returns:
            Simulated fill price (realistic executed price)
        """
        # Base slippage amount
        slippage = self.slippage

        # Optional random variation (simulate market noise)
        if add_randomness:
            slippage *= random.uniform(0.5, 1.5)

        # Apply directionally-correct slippage and spread
        if side == "buy":
            # Buyers pay slightly more due to spread and slippage
            fill_price = price + slippage + self._half_spread
        elif side == "sell":
            # Sellers receive slightly less due to spread and slippage
            fill_price = price - slippage - self._half_spread
        else:
            raise ValueError("Invalid order side: must be 'buy' or 'sell'")

        return fill_price

    def calculate_commission(self, price: float, size: float) -> float:
        """
        Calculate commission based on notional trade value.

        Args:
            price: Executed price per unit
            size: Trade size (units of asset)

        Returns:
            Commission amount (in quote currency)
        """
        return self.commission * price * size

    def simulate_trade_costs(
        self,
        side: Literal["buy", "sell"],
        price: float,
        size: float,
        add_randomness: bool = True
    ) -> dict:
        """
        Full trade simulation: fill price + commission.

        Args:
            side: Order side
            price: Requested price
            size: Position size
            add_randomness: Whether to randomize slippage

        Returns:
            dict: {
                'fill_price': float,
                'commission': float,
                'total_cost': float  # commission + slippage impact
            }
        """
        fill_price = self.simulate_fill(side, price, add_randomness)
        commission = self.calculate_commission(fill_price, size)

        # Total trade cost (difference vs ideal mid-price * size + commission)
        slippage_cost = abs(fill_price - price) * size
        total_cost = slippage_cost + commission

        return {
            "fill_price": fill_price,
            "commission": commission,
            "total_cost": total_cost
        }
