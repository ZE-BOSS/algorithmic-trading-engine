"""
Smart Money Concepts (SMC) Primitives - Optimized Version

Core SMC detection algorithms:
- Market Structure (swing highs/lows, HH/HL/LH/LL)
- Break of Structure (BOS)
- Change of Character (ChoCH)
- Order Blocks (OB)
- Fair Value Gaps (FVG)
- Liquidity Grabs
"""

from dataclasses import dataclass
from typing import List, Literal, Optional, Union
from enum import Enum
import pandas as pd
import numpy as np


# ============================================================
# ENUMS
# ============================================================

class SwingType(Enum):
    HIGH = "high"
    LOW = "low"


class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


# ============================================================
# DATACLASSES
# ============================================================

@dataclass
class SwingPoint:
    index: int
    timestamp: pd.Timestamp
    price: float
    swing_type: SwingType

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": str(self.timestamp),
            "price": self.price,
            "swing_type": self.swing_type.value,
        }


@dataclass
class MarketStructure:
    swings: List[SwingPoint]
    trend: TrendDirection
    last_swing_high: Optional[SwingPoint]
    last_swing_low: Optional[SwingPoint]

    def to_dict(self):
        return {
            "swings": [s.to_dict() for s in self.swings],
            "trend": self.trend.value,
            "last_swing_high": self.last_swing_high.to_dict() if self.last_swing_high else None,
            "last_swing_low": self.last_swing_low.to_dict() if self.last_swing_low else None,
        }


@dataclass
class OrderBlock:
    type: Literal["bullish", "bearish"]
    start_idx: int
    end_idx: int
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    price_top: float
    price_bottom: float
    strength: float

    def to_dict(self):
        return vars(self) | {
            "start_ts": str(self.start_ts),
            "end_ts": str(self.end_ts),
        }


@dataclass
class FairValueGap:
    type: Literal["bullish", "bearish"]
    start_idx: int
    end_idx: int
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    gap_top: float
    gap_bottom: float
    size_pips: float

    def to_dict(self):
        return vars(self) | {
            "start_ts": str(self.start_ts),
            "end_ts": str(self.end_ts),
        }
    
@dataclass
class LiquidityGrab:
    type: Literal["bullish", "bearish"]
    swing_idx: int
    grab_idx: int
    timestamp: pd.Timestamp
    swing_price: float
    grab_price: float
    reclaim_bars: int

    @property
    def end_idx(self):
        return self.grab_idx

    def to_dict(self):
        return vars(self) | {"timestamp": str(self.timestamp)}



# ============================================================
# CORE UTILS
# ============================================================

def calculate_atr(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    """Vectorized Average True Range (ATR) calculation."""
    high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
    prev_close = close.shift()
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


# ============================================================
# MARKET STRUCTURE
# ============================================================

def detect_market_structure(ohlc: pd.DataFrame, lookback: int = 10) -> MarketStructure:
    """Detect swing points and trend direction."""
    if len(ohlc) < lookback * 2 + 1:
        return MarketStructure([], TrendDirection.RANGING, None, None)

    highs, lows = ohlc["high"].values, ohlc["low"].values
    swings: List[SwingPoint] = []

    # Rolling extrema
    rolling_high = pd.Series(highs).rolling(lookback * 2 + 1, center=True).max()
    rolling_low = pd.Series(lows).rolling(lookback * 2 + 1, center=True).min()

    swing_highs = np.where((highs == rolling_high) & (highs > np.roll(highs, 1)) & (highs > np.roll(highs, -1)))[0]
    swing_lows = np.where((lows == rolling_low) & (lows < np.roll(lows, 1)) & (lows < np.roll(lows, -1)))[0]

    for i in swing_highs:
        swings.append(SwingPoint(i, ohlc.index[i], highs[i], SwingType.HIGH))
    for i in swing_lows:
        swings.append(SwingPoint(i, ohlc.index[i], lows[i], SwingType.LOW))

    swings.sort(key=lambda s: s.index)

    # Determine trend
    highs_seq = [s for s in swings if s.swing_type == SwingType.HIGH]
    lows_seq = [s for s in swings if s.swing_type == SwingType.LOW]
    trend = TrendDirection.RANGING

    if len(highs_seq) >= 2 and len(lows_seq) >= 2:
        if highs_seq[-1].price > highs_seq[-2].price and lows_seq[-1].price > lows_seq[-2].price:
            trend = TrendDirection.BULLISH
        elif highs_seq[-1].price < highs_seq[-2].price and lows_seq[-1].price < lows_seq[-2].price:
            trend = TrendDirection.BEARISH

    return MarketStructure(
        swings=swings,
        trend=trend,
        last_swing_high=highs_seq[-1] if highs_seq else None,
        last_swing_low=lows_seq[-1] if lows_seq else None,
    )


# ============================================================
# BOS / CHOCH
# ============================================================

def is_bos(ohlc: pd.DataFrame, swing: SwingPoint, bos_margin_atr: float = 0.5, atr_period: int = 14) -> bool:
    """Detect Break of Structure relative to a swing."""
    if len(ohlc) < atr_period:
        return False

    atr = calculate_atr(ohlc, atr_period).iloc[-1]
    atr = 0.0001 if pd.isna(atr) else atr
    margin = bos_margin_atr * atr
    close = ohlc["close"].iloc[-1]

    if swing.swing_type == SwingType.HIGH:
        return close > swing.price + margin
    return close < swing.price - margin


def detect_choch(
    ohlc: pd.DataFrame,
    ms_or_swings: Union[MarketStructure, List[SwingPoint]],
    bos_margin_atr: float = 0.5,
    atr_period: int = 14
) -> bool:
    """
    Detect Change of Character (ChoCH).

    Accepts either a MarketStructure instance or a list of SwingPoint (legacy/mistaken usage).
    If a list is provided, derive a minimal MarketStructure (trend + last swings) from it.
    """
    # If a list of swings was passed, construct a minimal MarketStructure
    if isinstance(ms_or_swings, list):
        swings_list: List[SwingPoint] = ms_or_swings
        # derive last highs and lows
        highs = [s for s in swings_list if s.swing_type == SwingType.HIGH]
        lows = [s for s in swings_list if s.swing_type == SwingType.LOW]
        trend = TrendDirection.RANGING
        if len(highs) >= 2 and len(lows) >= 2:
            if highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price:
                trend = TrendDirection.BULLISH
            elif highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price:
                trend = TrendDirection.BEARISH

        ms = MarketStructure(
            swings=swings_list,
            trend=trend,
            last_swing_high=highs[-1] if highs else None,
            last_swing_low=lows[-1] if lows else None
        )
    else:
        ms = ms_or_swings  # already MarketStructure

    # Now proceed as before
    if ms.trend == TrendDirection.RANGING:
        return False
    if ms.trend == TrendDirection.BULLISH and ms.last_swing_low:
        return is_bos(ohlc, ms.last_swing_low, bos_margin_atr, atr_period)
    if ms.trend == TrendDirection.BEARISH and ms.last_swing_high:
        return is_bos(ohlc, ms.last_swing_high, bos_margin_atr, atr_period)
    return False


# ============================================================
# ORDER BLOCKS  ✅ FIXED
# ============================================================

def find_order_blocks(ohlc: pd.DataFrame, params: dict) -> List[OrderBlock]:
    """Detect Order Blocks using impulsive moves."""
    min_bars = params.get("min_impulse_bars", 3)
    min_atr_mult = params.get("min_impulse_atr", 2.0)
    expansion_mult = params.get("ob_expansion_atr", 0.5)
    atr_period = params.get("atr_period", 14)
    max_age = params.get("max_age_bars", 100)
    strict = params.get("detection_method", "strict") == "strict"

    if len(ohlc) < atr_period + min_bars:
        return []

    atr = calculate_atr(ohlc, atr_period)
    bullish = ohlc["close"] > ohlc["open"]
    bearish = ~bullish
    order_blocks: List[OrderBlock] = []

    for i in range(atr_period, len(ohlc) - min_bars):
        current_atr = atr.iat[i]
        if np.isnan(current_atr):
            continue

        def add_block(block_type: str, ob_idx: int):
            expansion = expansion_mult * current_atr
            high, low, open_, close = ohlc.iloc[ob_idx][["high", "low", "open", "close"]]
            ob_top, ob_bottom = (
                (max(open_, close) + expansion, min(open_, close) - expansion)
                if strict else
                (high + expansion, low - expansion)
            )
            order_blocks.append(OrderBlock(
                type=block_type,
                start_idx=ob_idx,
                end_idx=i + min_bars - 1,
                start_ts=ohlc.index[ob_idx],
                end_ts=ohlc.index[i + min_bars - 1],
                price_top=ob_top,
                price_bottom=ob_bottom,
                strength=float(abs(ohlc["close"].iloc[i + min_bars - 1] - ohlc["open"].iloc[ob_idx]) / current_atr),
            ))

        # Bullish impulse
        if bullish.iloc[i:i + min_bars].all():
            if (ohlc["high"].iloc[i + min_bars - 1] - ohlc["low"].iloc[i]) >= min_atr_mult * current_atr:
                ob_series = bearish[:i][::-1]
                if ob_series.any():
                    ob_ts = ob_series.idxmax()  # this returns a timestamp
                    # convert timestamp to integer location (robust)
                    try:
                        ob_idx = ohlc.index.get_loc(ob_ts)
                    except Exception:
                        # fallback to positional approach if weird index types
                        ob_idx = int(ob_series.iloc[::-1].to_numpy().argmax())
                    if i - ob_idx <= max_age:
                        add_block("bullish", ob_idx)

        # Bearish impulse
        if bearish.iloc[i:i + min_bars].all():
            if (ohlc["high"].iloc[i] - ohlc["low"].iloc[i + min_bars - 1]) >= min_atr_mult * current_atr:
                ob_series = bullish[:i][::-1]
                if ob_series.any():
                    ob_ts = ob_series.idxmax()
                    try:
                        ob_idx = ohlc.index.get_loc(ob_ts)
                    except Exception:
                        ob_idx = int(ob_series.iloc[::-1].to_numpy().argmax())
                    if i - ob_idx <= max_age:
                        add_block("bearish", ob_idx)

    return order_blocks


# ============================================================
# FAIR VALUE GAPS
# ============================================================

def find_fvg(ohlc: pd.DataFrame, params: dict) -> List[FairValueGap]:
    """Detect Fair Value Gaps (3-candle imbalance)."""
    min_gap_atr = params.get("min_gap_atr", 0.5)
    expand_mult = params.get("fvg_expand_atr", 0.2)
    atr_period = params.get("atr_period", 14)

    if len(ohlc) < atr_period + 3:
        return []

    atr = calculate_atr(ohlc, atr_period)
    fvgs: List[FairValueGap] = []

    for i in range(atr_period, len(ohlc) - 2):
        current_atr = atr.iat[i]
        if np.isnan(current_atr):
            continue
        expand = expand_mult * current_atr
        min_gap = min_gap_atr * current_atr

        high_i, low_i2 = ohlc["high"].iat[i], ohlc["low"].iat[i + 2]
        low_i, high_i2 = ohlc["low"].iat[i], ohlc["high"].iat[i + 2]

        if high_i < low_i2 and (low_i2 - high_i) >= min_gap:
            fvgs.append(FairValueGap("bullish", i, i + 2, ohlc.index[i], ohlc.index[i + 2],
                                     low_i2 + expand, high_i - expand, (low_i2 - high_i) * 10000))
        elif low_i > high_i2 and (low_i - high_i2) >= min_gap:
            fvgs.append(FairValueGap("bearish", i, i + 2, ohlc.index[i], ohlc.index[i + 2],
                                     low_i + expand, high_i2 - expand, (low_i - high_i2) * 10000))

    return fvgs


# ============================================================
# LIQUIDITY GRABS
# ============================================================

def detect_liquidity_grab(
    ohlc: pd.DataFrame,
    swings: List[SwingPoint],
    liquidity_grab_atr: float = 1.0,
    grab_reclaim_bars: int = 3,
    atr_period: int = 14,
) -> List[LiquidityGrab]:
    """Detect liquidity grabs based on swing highs/lows."""
    if len(ohlc) < atr_period + grab_reclaim_bars:
        return []

    atr = calculate_atr(ohlc, atr_period)
    grabs: List[LiquidityGrab] = []

    for swing in swings:
        start = swing.index + 1
        end = min(start + 50, len(ohlc))
        for i in range(start, end):
            current_atr = atr.iat[i]
            if np.isnan(current_atr):
                continue
            thresh = liquidity_grab_atr * current_atr

            if swing.swing_type == SwingType.HIGH:
                if ohlc["high"].iat[i] > swing.price + thresh:
                    for j in range(i + 1, min(i + grab_reclaim_bars + 1, len(ohlc))):
                        if ohlc["close"].iat[j] < swing.price:
                            grabs.append(LiquidityGrab(
                                type="bearish",
                                swing_idx=swing.index,
                                grab_idx=i,
                                timestamp=ohlc.index[i],
                                swing_price=swing.price,
                                grab_price=ohlc["high"].iat[i],
                                reclaim_bars=j - i,
                            ))
                            break

            elif swing.swing_type == SwingType.LOW:
                if ohlc["low"].iat[i] < swing.price - thresh:
                    for j in range(i + 1, min(i + grab_reclaim_bars + 1, len(ohlc))):
                        if ohlc["close"].iat[j] > swing.price:
                            grabs.append(LiquidityGrab(
                                type="bullish",
                                swing_idx=swing.index,
                                grab_idx=i,
                                timestamp=ohlc.index[i],
                                swing_price=swing.price,
                                grab_price=ohlc["low"].iat[i],
                                reclaim_bars=j - i,
                            ))
                            break
    return grabs

