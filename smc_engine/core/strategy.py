"""
Strategy base class and optimized Smart Money Concepts (SMC) implementation.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
import pandas as pd
import numpy as np

from .smc_primitives import (
    detect_market_structure,
    find_order_blocks,
    find_fvg,
    detect_choch,
    detect_liquidity_grab,
    calculate_atr,
)


# ================================================================
# Base Strategy Interface
# ================================================================

class Strategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(self, params: Dict[str, Any]):
        self.params = params
        self.validate_params()

    @abstractmethod
    def generate_signals(self, ohlc: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame of signals."""
        pass

    @abstractmethod
    def default_param_space(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def validate_params(self):
        pass


# ================================================================
# Smart Money Concepts Strategy
# ================================================================

class SMCStrategy(Strategy):
    """
    Smart Money Concepts (SMC) trading strategy.

    Process overview:
        1. Detect rolling market structure and trend
        2. Identify order blocks and fair value gaps (zones)
        3. Detect BOS / ChoCH and liquidity grabs
        4. Generate entries on retracements into OB/FVG 
           confirmed by structure shifts or liquidity sweeps
        5. Use adaptive stop loss and target placement
    """

    def __init__(self, params: Dict[str, Any]):
        super().__init__(params)

    # ------------------------------------------------------------
    # Parameter validation
    # ------------------------------------------------------------

    def validate_params(self):
        required = ["lookback", "risk_reward", "atr_period"]
        for p in required:
            if p not in self.params:
                raise ValueError(f"Missing required parameter: {p}")
        if self.params["lookback"] < 10:
            raise ValueError("lookback must be >= 10")
        if self.params["risk_reward"] <= 0:
            raise ValueError("risk_reward must be > 0")

    # ------------------------------------------------------------
    # Default parameter search space
    # ------------------------------------------------------------

    def default_param_space(self) -> Dict[str, Any]:
        return {
            "lookback": {"type": "int", "low": 20, "high": 100},
            "min_impulse_bars": {"type": "int", "low": 2, "high": 5},
            "min_impulse_atr": {"type": "float", "low": 1.0, "high": 3.0},
            "ob_expansion_atr": {"type": "float", "low": 0.2, "high": 1.0},
            "min_gap_atr": {"type": "float", "low": 0.3, "high": 1.0},
            "bos_margin_atr": {"type": "float", "low": 0.3, "high": 1.0},
            "liquidity_grab_atr": {"type": "float", "low": 0.5, "high": 2.0},
            "risk_reward": {"type": "float", "low": 1.5, "high": 3.0},
            "atr_period": {"type": "int", "low": 10, "high": 20},
            "use_order_blocks": {"type": "categorical", "choices": [True, False]},
            "use_fvg": {"type": "categorical", "choices": [True, False]},
            "use_liquidity_grabs": {"type": "categorical", "choices": [True, False]},
        }

    # ------------------------------------------------------------
    # Generate trading signals
    # ------------------------------------------------------------

    def generate_signals(self, ohlc: pd.DataFrame) -> pd.DataFrame:
        """
        Generate SMC-based trading signals.
        """

        signals = []
        min_bars = max(self.params["lookback"], self.params["atr_period"]) + 10
        if len(ohlc) < min_bars:
            return pd.DataFrame(columns=["ts", "signal", "price", "stop", "tp", "meta"])

        # --- Precompute data ---------------------------------------------------
        atr = calculate_atr(ohlc, self.params["atr_period"])

        order_blocks = (
            find_order_blocks(ohlc, self.params)
            if self.params.get("use_order_blocks", True)
            else []
        )
        fvgs = (
            find_fvg(ohlc, self.params)
            if self.params.get("use_fvg", True)
            else []
        )

        # optional: detect all liquidity grabs once (structure-based)
        liquidity_grabs = (
            detect_liquidity_grab(
                ohlc,
                detect_market_structure(ohlc, self.params["lookback"]).swings,
                self.params.get("liquidity_grab_atr", 1.0),
                grab_reclaim_bars=3,
                atr_period=self.params["atr_period"],
            )
            if self.params.get("use_liquidity_grabs", True)
            else []
        )

        last_signal_bar = -9999  # avoid duplicate entries
        cool_off = 5

        # --- Main signal loop -------------------------------------------------
        for i in range(min_bars, len(ohlc)):
            if i - last_signal_bar < cool_off:
                continue

            df_slice = ohlc.iloc[: i + 1]
            price = df_slice["close"].iloc[-1]
            high = df_slice["high"].iloc[-1]
            low = df_slice["low"].iloc[-1]
            atr_now = atr.iloc[i]
            if pd.isna(atr_now):
                continue

            # Rolling structure
            ms = detect_market_structure(df_slice, self.params["lookback"])
            trend = ms.trend.value

            # Confirm structural shift
            choch = detect_choch(df_slice, ms.swings)

            # Active liquidity grab at this bar?
            recent_grab = next(
                (g for g in liquidity_grabs if g.end_idx == i), None
            ) if liquidity_grabs else None

            # ==================== BULLISH CONTEXT ============================
            if trend in ["bullish", "ranging"]:
                # Confluence: structure shift or liquidity grab
                bullish_confirm = (
                    (choch.is_bullish if hasattr(choch, "is_bullish") else False)
                    or (recent_grab and recent_grab.type == "bullish")
                )
                if not bullish_confirm:
                    continue

                # look for nearest active bullish OB / FVG zone
                for ob in order_blocks:
                    if ob.type != "bullish" or ob.end_idx >= i:
                        continue
                    if ob.price_bottom <= low <= ob.price_top:
                        entry = price
                        stop = min(ob.price_bottom, low) - 0.3 * atr_now
                        risk = entry - stop
                        tp = entry + risk * self.params["risk_reward"]

                        signals.append(
                            {
                                "ts": df_slice.index[-1],
                                "signal": "buy",
                                "price": entry,
                                "stop": stop,
                                "tp": tp,
                                "meta": {
                                    "reason": "OB+ChoCH/LQ",
                                    "trend": trend,
                                    "ob_strength": getattr(ob, "strength", None),
                                },
                            }
                        )
                        last_signal_bar = i
                        break

                # FVG confluence (if price within gap and bullish confirmed)
                for fvg in fvgs:
                    if fvg.type != "bullish" or fvg.end_idx >= i:
                        continue
                    if fvg.gap_bottom <= low <= fvg.gap_top:
                        entry = price
                        stop = fvg.gap_bottom - 0.3 * atr_now
                        risk = entry - stop
                        tp = entry + risk * self.params["risk_reward"]

                        signals.append(
                            {
                                "ts": df_slice.index[-1],
                                "signal": "buy",
                                "price": entry,
                                "stop": stop,
                                "tp": tp,
                                "meta": {
                                    "reason": "FVG+ChoCH/LQ",
                                    "trend": trend,
                                    "fvg_size": getattr(fvg, "size_pips", None),
                                },
                            }
                        )
                        last_signal_bar = i
                        break

            # ==================== BEARISH CONTEXT ============================
            if trend in ["bearish", "ranging"]:
                bearish_confirm = (
                    (choch.is_bearish if hasattr(choch, "is_bearish") else False)
                    or (recent_grab and recent_grab.type == "bearish")
                )
                if not bearish_confirm:
                    continue

                for ob in order_blocks:
                    if ob.type != "bearish" or ob.end_idx >= i:
                        continue
                    if ob.price_bottom <= high <= ob.price_top:
                        entry = price
                        stop = max(ob.price_top, high) + 0.3 * atr_now
                        risk = stop - entry
                        tp = entry - risk * self.params["risk_reward"]

                        signals.append(
                            {
                                "ts": df_slice.index[-1],
                                "signal": "sell",
                                "price": entry,
                                "stop": stop,
                                "tp": tp,
                                "meta": {
                                    "reason": "OB+ChoCH/LQ",
                                    "trend": trend,
                                    "ob_strength": getattr(ob, "strength", None),
                                },
                            }
                        )
                        last_signal_bar = i
                        break

                for fvg in fvgs:
                    if fvg.type != "bearish" or fvg.end_idx >= i:
                        continue
                    if fvg.gap_bottom <= high <= fvg.gap_top:
                        entry = price
                        stop = fvg.gap_top + 0.3 * atr_now
                        risk = stop - entry
                        tp = entry - risk * self.params["risk_reward"]

                        signals.append(
                            {
                                "ts": df_slice.index[-1],
                                "signal": "sell",
                                "price": entry,
                                "stop": stop,
                                "tp": tp,
                                "meta": {
                                    "reason": "FVG+ChoCH/LQ",
                                    "trend": trend,
                                    "fvg_size": getattr(fvg, "size_pips", None),
                                },
                            }
                        )
                        last_signal_bar = i
                        break

        # ------------------------------------------------------------
        # Convert signals to DataFrame
        # ------------------------------------------------------------
        if not signals:
            return pd.DataFrame(columns=["ts", "signal", "price", "stop", "tp", "meta"])

        return pd.DataFrame(signals)
