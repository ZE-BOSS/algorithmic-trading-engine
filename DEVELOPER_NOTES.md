# Developer Notes: SMC Trading Engine Implementation

## Overview

This document describes the implementation details of the Smart Money Concepts (SMC) trading engine, including the rationale behind detection algorithms, parameter defaults, and tuning recommendations.

## SMC Detection Algorithms

### 1. Market Structure (Swing Detection)

**Implementation:**
We use a symmetric lookback window approach where a bar `i` is considered a swing high if `high[i]` equals the maximum of `high[i-n:i+n+1]`, and similarly for swing lows.

**Rationale:**
- Simple and deterministic
- Configurable sensitivity via `swing_lookback` parameter
- Avoids repainting (uses only past data)

**Default:** `swing_lookback = 10`
- Works well for H1-H4 timeframes
- Lower values (5-7) for faster timeframes (M5-M15)
- Higher values (15-20) for daily/weekly charts

**Tuning:**
- Increase for cleaner structure on noisy data
- Decrease for more responsive signals
- Validate against visual chart analysis

### 2. Break of Structure (BOS)

**Implementation:**
A BOS occurs when price closes beyond a previous swing level by a margin defined as:
\`\`\`
margin = bos_atr_margin × ATR(atr_period)
\`\`\`

For bullish BOS:
\`\`\`
close > last_swing_high + margin
\`\`\`

**Rationale:**
- ATR-based margin adapts to volatility
- Prevents false signals from minor breaches
- Confirms momentum continuation

**Defaults:**
- `bos_atr_margin = 0.5` (moderate confirmation)
- `atr_period = 14` (standard ATR period)

**Tuning:**
- Increase margin (0.7-1.0) in choppy markets
- Decrease margin (0.3-0.4) in trending markets
- Consider `bos_margin_pct` for fixed percentage (0.001 = 10 pips on EURUSD)

### 3. Order Blocks (OB)

**Implementation:**
Order blocks are detected using a two-phase algorithm:

**Phase 1: Identify Impulsive Move**
- Find sequence of ≥ `ob_min_impulse_bars` consecutive directional candles
- Total move must exceed `ob_min_impulse_atr × ATR`
- Direction determined by close-to-close comparison

**Phase 2: Mark Order Block**
- Last opposite-colored candle before impulse = OB
- Use candle body (open-close) or full range (high-low)
- Expand zone by `ob_expansion_atr × ATR`

**Rationale:**
- Institutional orders create impulsive moves
- Last opposite candle represents accumulation/distribution zone
- Expansion accounts for wick reactions

**Defaults:**
- `ob_min_impulse_bars = 3` (minimum for valid impulse)
- `ob_min_impulse_atr = 1.5` (significant move)
- `ob_expansion_atr = 0.2` (small buffer)
- `ob_detection_method = 'strict'` (body-based)

**Tuning:**
- Strict method: fewer, higher-quality OBs
- Relaxed method: more OBs, includes full candle range
- Increase `min_impulse_atr` to filter weak OBs
- Decrease for more signals (risk: lower quality)

**Strength Metric:**
\`\`\`python
strength = impulse_size_pips × (1 + num_touches × 0.1) / (age_bars + 1)
\`\`\`
- Larger impulses = stronger OB
- Multiple touches = validated zone
- Recent OBs weighted higher

### 4. Fair Value Gaps (FVG)

**Implementation:**
Two detection methods provided:

**Method A: Imbalance (Default)**
For each 3-candle sequence (i, i+1, i+2):
- Bullish FVG: `candle[i].high < candle[i+2].low`
- Bearish FVG: `candle[i].low > candle[i+2].high`
- Gap must exceed `fvg_min_gap_atr × ATR`

**Method B: Wick**
- Detects gaps between wicks during rapid moves
- More sensitive, finds smaller imbalances
- Useful for scalping strategies

**Rationale:**
- FVGs represent inefficient price discovery
- Price often returns to fill gaps
- Imbalance method is more conservative

**Defaults:**
- `fvg_method = 'imbalance'` (standard SMC)
- `fvg_min_gap_atr = 0.3` (filters noise)
- `fvg_expand_atr = 0.1` (small expansion)

**Tuning:**
- Increase `min_gap_atr` (0.4-0.6) to reduce false signals
- Use 'wick' method for scalping (M5-M15)
- Set `expand_atr = 0` for precise zones
- Higher timeframes: increase thresholds

### 5. Liquidity Grabs

**Implementation:**
A liquidity grab is detected when:
1. Candle wick extends beyond swing level by `liquidity_grab_atr × ATR`
2. Price reclaims structure within `liquidity_reclaim_bars` candles
3. Reclaim = close back inside structure

**Rationale:**
- Stop hunts create wicks beyond obvious levels
- Quick reversal indicates trapped traders
- High-probability reversal zones

**Defaults:**
- `liquidity_grab_atr = 1.0` (significant extension)
- `liquidity_reclaim_bars = 3` (quick reversal)

**Tuning:**
- Increase threshold (1.2-1.5) for cleaner signals
- Decrease (0.7-0.9) for more opportunities
- Adjust reclaim bars based on timeframe:
  - M5-M15: 2-3 bars
  - H1-H4: 3-5 bars
  - Daily: 5-10 bars

### 6. Change of Character (ChoCH)

**Implementation:**
ChoCH is the first BOS in the opposite direction of the prevailing trend:
1. Determine trend from swing pattern (HH/HL vs LH/LL)
2. Detect BOS against trend
3. Confirm swing pattern flip

**Rationale:**
- Early trend reversal signal
- More aggressive than waiting for full reversal
- Requires confirmation to avoid false signals

**Default:** `choch_enabled = true`

**Tuning:**
- Disable for trend-following only strategies
- Combine with other confirmations (OB, FVG)
- Use higher timeframe ChoCH for direction

## Strategy Logic (SMCStrategy)

### Signal Generation Flow

1. **Calculate Indicators**
   - ATR for volatility-based thresholds
   - Market structure (swings)

2. **Detect SMC Primitives**
   - Order blocks
   - Fair value gaps
   - Liquidity grabs
   - BOS/ChoCH

3. **Generate Entry Signals**
   - Bullish: Price in bullish OB + bullish BOS + optional FVG
   - Bearish: Price in bearish OB + bearish BOS + optional FVG
   - Liquidity grab as confirmation

4. **Calculate Stop Loss**
   - Below/above OB zone
   - Minimum: `atr_sl_multiplier × ATR`
   - Maximum: 2% of account (configurable)

5. **Calculate Take Profit**
   - `TP = Entry + (Entry - SL) × risk_reward_ratio`
   - Minimum RR: `min_rr_ratio` (default 1.5)

6. **Position Sizing**
   - Risk per trade: `risk_per_trade × account_balance`
   - Lot size: `risk_amount / (SL_distance × pip_value)`

### Parameter Interactions

**Conservative Setup (Lower Risk, Fewer Trades):**
\`\`\`json
{
  "swing_lookback": 15,
  "bos_atr_margin": 0.8,
  "ob_min_impulse_atr": 2.0,
  "fvg_min_gap_atr": 0.5,
  "liquidity_grab_atr": 1.2,
  "risk_per_trade": 0.01,
  "risk_reward_ratio": 2.5
}
\`\`\`

**Aggressive Setup (Higher Risk, More Trades):**
\`\`\`json
{
  "swing_lookback": 7,
  "bos_atr_margin": 0.3,
  "ob_min_impulse_atr": 1.0,
  "fvg_min_gap_atr": 0.2,
  "liquidity_grab_atr": 0.7,
  "risk_per_trade": 0.025,
  "risk_reward_ratio": 1.5
}
\`\`\`

## Backtesting Implementation

### Order Simulation

**Entry Execution:**
- Market orders: filled at next bar open + slippage
- Slippage model: `slippage_pct × ATR` (default 0.5 pips)
- Spread applied: `entry_price + spread` (buy), `entry_price - spread` (sell)

**Exit Execution:**
- Check SL/TP hit during bar (high/low)
- If both hit same bar: SL takes precedence (conservative)
- Exit at SL/TP price (no slippage on limits)

**Fees:**
- Commission: `commission_pct × position_value`
- Applied on entry and exit
- Default: 0.0001 (1 pip round-turn on EURUSD)

### Realism Considerations

**What's Included:**
- Spreads, commissions, slippage
- Bar-by-bar simulation (no lookahead)
- Position sizing constraints
- Margin requirements

**What's Not Included:**
- Intrabar price movement (assumes worst case)
- Requotes and rejections
- Slippage during news events
- Broker-specific execution quirks

**Recommendation:**
- Backtest results are optimistic
- Apply 20-30% haircut to metrics
- Validate with forward testing (dry-run)

## Optimization Strategy

### Objective Selection

**Sharpe Ratio (Recommended):**
- Balances return and risk
- Penalizes volatility
- Good for comparing strategies

**Net Profit:**
- Maximizes absolute returns
- May overfit to large moves
- Use with drawdown constraint

**Calmar Ratio:**
- Return / Max Drawdown
- Good for risk-averse traders
- Emphasizes capital preservation

**Profit Factor:**
- Gross Profit / Gross Loss
- Requires minimum trades constraint
- Can be gamed with few large wins

### Constraints

Always apply constraints to prevent overfitting:

\`\`\`python
constraints = {
    "max_drawdown_pct": 20,  # Max 20% drawdown
    "min_trades": 50,         # Minimum sample size
    "min_win_rate": 40        # At least 40% winners
}
\`\`\`

### Search Methods

**Grid Search:**
- Use for ≤ 4 parameters with small ranges
- Exhaustive but slow
- Good for final refinement

**Random Search:**
- Good baseline for large spaces
- 100-200 trials usually sufficient
- No optimization bias

**Optuna (Bayesian):**
- Most efficient for large spaces
- Learns from previous trials
- 200-500 trials recommended
- Use TPESampler for best results

### Avoiding Overfitting

1. **Walk-Forward Analysis:**
   - Optimize on training period
   - Test on out-of-sample period
   - Re-optimize periodically

2. **Parameter Stability:**
   - Best params should be robust
   - Small changes shouldn't drastically affect results
   - Check parameter sensitivity

3. **Multiple Objectives:**
   - Don't optimize single metric
   - Consider Sharpe, drawdown, win rate together
   - Use Pareto front analysis

4. **Realistic Constraints:**
   - Minimum trades (50-100)
   - Maximum drawdown (15-25%)
   - Minimum win rate (35-40%)

## Market-Specific Tuning

### Forex (EURUSD, GBPUSD, etc.)

**Characteristics:**
- High liquidity, tight spreads
- Trending during sessions
- Range-bound between sessions

**Recommended Settings:**
- Timeframe: H1-H4
- `swing_lookback`: 10-15
- `risk_per_trade`: 0.01-0.02
- Focus on session opens (London, NY)

### Indices (S&P500, NASDAQ, etc.)

**Characteristics:**
- Strong trends
- Gap openings
- High volatility

**Recommended Settings:**
- Timeframe: H1-Daily
- `swing_lookback`: 15-20
- `ob_min_impulse_atr`: 2.0-2.5
- Avoid overnight positions (gap risk)

### Commodities (Gold, Oil, etc.)

**Characteristics:**
- News-driven
- Wide spreads
- Strong momentum

**Recommended Settings:**
- Timeframe: H4-Daily
- `bos_atr_margin`: 0.7-1.0
- `risk_per_trade`: 0.015-0.025
- Increase slippage assumptions

### Crypto (BTC, ETH, etc.)

**Characteristics:**
- 24/7 trading
- Extreme volatility
- Wide spreads on some exchanges

**Recommended Settings:**
- Timeframe: H1-H4
- `atr_period`: 20-30 (longer for stability)
- `risk_per_trade`: 0.01-0.015 (lower due to volatility)
- Increase commission assumptions

## Live Trading Considerations

### Pre-Flight Checklist

Before enabling live trading:

1. **Backtest Validation:**
   - ≥ 100 trades in backtest
   - Sharpe > 1.0
   - Max drawdown < 20%
   - Win rate > 40%

2. **Forward Test (Dry-Run):**
   - Run 1-3 months in dry-run mode
   - Verify signal generation
   - Check execution timing
   - Monitor for errors

3. **Risk Management:**
   - Set `MAX_DAILY_LOSS_PCT` (3-5%)
   - Limit `MAX_OPEN_TRADES` (1-3)
   - Start with minimum position size
   - Have stop-loss on every trade

4. **Monitoring:**
   - Check logs daily
   - Review trades weekly
   - Monitor drawdown
   - Be ready to intervene

### Common Issues

**Signals Not Generating:**
- Check data feed (MT5 connection)
- Verify symbol name matches broker
- Ensure sufficient historical bars
- Review parameter thresholds

**Orders Rejected:**
- Check margin/balance
- Verify lot size (min/max)
- Ensure symbol is tradeable
- Check trading hours

**Unexpected Behavior:**
- Review `actions_log` table
- Check for errors in logs
- Verify parameter file loaded correctly
- Test in dry-run mode first

## Performance Expectations

### Realistic Targets

**Good Strategy:**
- Sharpe Ratio: 1.0-2.0
- Annual Return: 15-30%
- Max Drawdown: 10-20%
- Win Rate: 40-55%
- Profit Factor: 1.5-2.5

**Excellent Strategy:**
- Sharpe Ratio: > 2.0
- Annual Return: > 30%
- Max Drawdown: < 15%
- Win Rate: > 55%
- Profit Factor: > 2.5

**Warning Signs:**
- Win rate > 70% (likely overfitting)
- Profit factor > 4.0 (too good to be true)
- Max drawdown < 5% (insufficient data or overfitting)
- Sharpe > 3.0 (unrealistic for live trading)

### Degradation Factors

Expect live performance to be 20-40% worse than backtest due to:
- Execution delays
- Slippage variability
- Spread widening
- Psychological factors
- Market regime changes

## Conclusion

This SMC implementation provides a solid foundation for algorithmic trading. Key success factors:

1. **Understand the primitives** - Know what each SMC concept represents
2. **Start conservative** - Use default parameters, then optimize carefully
3. **Validate thoroughly** - Backtest → Optimize → Forward test → Live
4. **Manage risk** - Never risk more than you can afford to lose
5. **Monitor continuously** - Markets change, strategies must adapt

Remember: **No strategy works forever. Continuous monitoring and adaptation are essential.**

## References

- Smart Money Concepts: Institutional order flow analysis
- ATR (Average True Range): Wilder, J. (1978)
- Optuna: Akiba et al. (2019)
- Backtesting best practices: Prado, M. (2018)

---

**Questions or Issues?**
Open an issue on GitHub or consult the README for usage examples.
