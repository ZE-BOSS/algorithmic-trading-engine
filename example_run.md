# Example Workflow: Complete SMC Trading Pipeline

This document demonstrates a complete workflow from backtesting through optimization to live trading with the SMC Trading Engine.

## Prerequisites

\`\`\`bash
# Ensure environment is set up
docker-compose up -d
docker-compose exec app alembic upgrade head

# Or for local installation
source venv/bin/activate
alembic upgrade head
\`\`\`

## Step 1: Initial Backtest

First, run a backtest with default parameters to establish a baseline.

\`\`\`bash
python -m smc_engine.main backtest \
  --strategy smc \
  --symbol EURUSD \
  --timeframe H1 \
  --start 2020-01-01 \
  --end 2022-12-31 \
  --params configs/smc_params.json \
  --initial_balance 10000 \
  --data_source csv \
  --csv_path sample_data/EURUSD_H1_sample.csv \
  --verbose
\`\`\`

**Expected Output:**
\`\`\`
2024-01-15 10:30:15 - INFO - Starting backtest...
2024-01-15 10:30:20 - INFO - Backtest completed. Backtest ID: 550e8400-e29b-41d4-a716-446655440000
2024-01-15 10:30:20 - INFO - Net Profit: $1,250.00
2024-01-15 10:30:20 - INFO - Sharpe Ratio: 1.45
2024-01-15 10:30:20 - INFO - Max Drawdown: 12.30%
2024-01-15 10:30:20 - INFO - Win Rate: 52.00%
2024-01-15 10:30:20 - INFO - Total Trades: 87
\`\`\`

**Analysis:**
- Positive net profit ✓
- Sharpe > 1.0 ✓
- Drawdown < 20% ✓
- Sufficient trades (>50) ✓
- **Conclusion:** Strategy shows promise, proceed to optimization

## Step 2: Parameter Optimization

Now optimize parameters to find better configurations.

\`\`\`bash
python -m smc_engine.main optimize \
  --strategy smc \
  --symbol EURUSD \
  --timeframe H1 \
  --start 2020-01-01 \
  --end 2022-12-31 \
  --param_space configs/param_space.json \
  --objective sharpe_ratio \
  --trials 200 \
  --method optuna \
  --constraints '{"max_drawdown_pct": 20, "min_trades": 50}' \
  --data_source csv \
  --csv_path sample_data/EURUSD_H1_sample.csv \
  --verbose
\`\`\`

**Expected Output:**
\`\`\`
2024-01-15 10:35:00 - INFO - Starting optimization...
2024-01-15 10:35:05 - INFO - Trial 1/200: sharpe_ratio=1.23
2024-01-15 10:35:10 - INFO - Trial 2/200: sharpe_ratio=1.67
...
2024-01-15 11:15:30 - INFO - Trial 200/200: sharpe_ratio=1.89
2024-01-15 11:15:35 - INFO - Optimization completed. Run ID: 660e8400-e29b-41d4-a716-446655440001
2024-01-15 11:15:35 - INFO - Best sharpe_ratio: 2.15
2024-01-15 11:15:35 - INFO - Best parameters:
2024-01-15 11:15:35 - INFO -   swing_lookback: 12
2024-01-15 11:15:35 - INFO -   bos_atr_margin: 0.6
2024-01-15 11:15:35 - INFO -   ob_min_impulse_bars: 3
2024-01-15 11:15:35 - INFO -   ob_min_impulse_atr: 1.8
2024-01-15 11:15:35 - INFO -   fvg_min_gap_atr: 0.4
2024-01-15 11:15:35 - INFO -   liquidity_grab_atr: 1.1
2024-01-15 11:15:35 - INFO -   risk_per_trade: 0.018
2024-01-15 11:15:35 - INFO -   risk_reward_ratio: 2.2
2024-01-15 11:15:35 - INFO -   atr_period: 14
2024-01-15 11:15:35 - INFO -   atr_sl_multiplier: 1.6

2024-01-15 11:15:35 - INFO - Top 5 parameter sets:
2024-01-15 11:15:35 - INFO - 1. sharpe_ratio=2.15, params={...}
2024-01-15 11:15:35 - INFO - 2. sharpe_ratio=2.08, params={...}
2024-01-15 11:15:35 - INFO - 3. sharpe_ratio=2.01, params={...}
2024-01-15 11:15:35 - INFO - 4. sharpe_ratio=1.97, params={...}
2024-01-15 11:15:35 - INFO - 5. sharpe_ratio=1.94, params={...}
\`\`\`

**Analysis:**
- Sharpe improved from 1.45 to 2.15 (48% improvement)
- Parameters are reasonable (not extreme values)
- Multiple good parameter sets found (robust)
- **Conclusion:** Optimization successful, save best parameters

## Step 3: Save Optimized Parameters

Create a new parameter file with the best parameters:

\`\`\`bash
cat > configs/smc_params_optimized.json << EOF
{
  "swing_lookback": 12,
  "bos_atr_margin": 0.6,
  "bos_margin_pct": 0.001,
  "choch_enabled": true,
  "ob_min_impulse_bars": 3,
  "ob_min_impulse_atr": 1.8,
  "ob_expansion_atr": 0.2,
  "ob_detection_method": "strict",
  "fvg_min_gap_atr": 0.4,
  "fvg_expand_atr": 0.1,
  "fvg_method": "imbalance",
  "liquidity_grab_atr": 1.1,
  "liquidity_reclaim_bars": 3,
  "risk_per_trade": 0.018,
  "risk_reward_ratio": 2.2,
  "atr_period": 14,
  "atr_sl_multiplier": 1.6,
  "max_open_trades": 1,
  "use_order_blocks": true,
  "use_fvg": true,
  "use_liquidity_grabs": true,
  "min_rr_ratio": 1.5
}
EOF
\`\`\`

## Step 4: Validate on Out-of-Sample Data

Test optimized parameters on unseen data (2023):

\`\`\`bash
python -m smc_engine.main backtest \
  --strategy smc \
  --symbol EURUSD \
  --timeframe H1 \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --params configs/smc_params_optimized.json \
  --initial_balance 10000 \
  --data_source csv \
  --csv_path sample_data/EURUSD_H1_2023.csv \
  --verbose
\`\`\`

**Expected Output:**
\`\`\`
2024-01-15 11:20:00 - INFO - Backtest completed. Backtest ID: 770e8400-e29b-41d4-a716-446655440002
2024-01-15 11:20:00 - INFO - Net Profit: $1,850.00
2024-01-15 11:20:00 - INFO - Sharpe Ratio: 1.92
2024-01-15 11:20:00 - INFO - Max Drawdown: 14.50%
2024-01-15 11:20:00 - INFO - Win Rate: 54.00%
2024-01-15 11:20:00 - INFO - Total Trades: 73
\`\`\`

**Analysis:**
- Out-of-sample Sharpe (1.92) close to in-sample (2.15) ✓
- Performance degradation ~11% (acceptable) ✓
- No overfitting detected ✓
- **Conclusion:** Parameters are robust, proceed to forward testing

## Step 5: Forward Test (Dry-Run Mode)

Test in real-time without placing actual orders:

\`\`\`bash
# Set MT5 credentials
export MT5_LOGIN=your_login
export MT5_PASSWORD=your_password
export MT5_SERVER=your_broker_server

# Run dry-run
python -m smc_engine.main live \
  --strategy smc \
  --symbol EURUSD \
  --timeframe M15 \
  --params configs/smc_params_optimized.json \
  --mode dryrun \
  --verbose
\`\`\`

**Expected Output:**
\`\`\`
2024-01-15 11:25:00 - INFO - Starting live trading in DRYRUN mode...
2024-01-15 11:25:05 - INFO - MT5 connected successfully
2024-01-15 11:25:05 - INFO - Account: 12345678, Balance: $10,000.00
2024-01-15 11:25:05 - INFO - Monitoring EURUSD M15...
2024-01-15 11:30:00 - INFO - New bar: 2024-01-15 11:30:00
2024-01-15 11:30:02 - INFO - Analyzing market structure...
2024-01-15 11:30:03 - INFO - No signals generated
2024-01-15 11:45:00 - INFO - New bar: 2024-01-15 11:45:00
2024-01-15 11:45:02 - INFO - BUY signal detected at 1.0950
2024-01-15 11:45:02 - INFO - [DRY-RUN] Would place order: BUY 0.10 lots, SL=1.0920, TP=1.1016
2024-01-15 11:45:02 - INFO - Simulated order placed, ticket=DRY-001
...
\`\`\`

**Monitoring:**
- Let run for 1-4 weeks
- Check signal quality
- Verify execution logic
- Monitor for errors
- Review simulated trades in database

## Step 6: Analyze Dry-Run Results

After dry-run period, analyze results:

\`\`\`python
# Query database for dry-run trades
from smc_engine.db.db import get_db
from smc_engine.db.models import LiveTrade
import pandas as pd

db = next(get_db())
trades = db.query(LiveTrade).filter(
    LiveTrade.status.in_(['closed', 'simulated'])
).all()

# Convert to DataFrame
df = pd.DataFrame([{
    'entry_ts': t.entry_ts,
    'exit_ts': t.exit_ts,
    'side': t.side,
    'entry_price': t.entry_price,
    'exit_price': t.exit_price,
    'pnl': t.pnl
} for t in trades])

# Calculate metrics
print(f"Total Trades: {len(df)}")
print(f"Win Rate: {(df['pnl'] > 0).mean() * 100:.2f}%")
print(f"Total PnL: ${df['pnl'].sum():.2f}")
print(f"Avg Win: ${df[df['pnl'] > 0]['pnl'].mean():.2f}")
print(f"Avg Loss: ${df[df['pnl'] < 0]['pnl'].mean():.2f}")
\`\`\`

**Expected Output:**
\`\`\`
Total Trades: 23
Win Rate: 52.17%
Total PnL: $387.50
Avg Win: $65.30
Avg Loss: -$42.80
\`\`\`

**Analysis:**
- Win rate consistent with backtest ✓
- PnL positive ✓
- No execution errors ✓
- **Conclusion:** Ready for live trading (if comfortable with risk)

## Step 7: Enable Live Trading (Optional)

**⚠️ WARNING: This involves real money. Only proceed if you:**
- Fully understand the risks
- Have tested thoroughly
- Can afford to lose the capital
- Have reviewed all safety settings

\`\`\`bash
# Enable live trading
export LIVE_TRADING=true
export MAX_DAILY_LOSS_PCT=5.0
export MAX_OPEN_TRADES=1

# Start live trading
python -m smc_engine.main live \
  --strategy smc \
  --symbol EURUSD \
  --timeframe M15 \
  --params configs/smc_params_optimized.json \
  --mode live \
  --verbose
\`\`\`

**You will be prompted:**
\`\`\`
============================================================
LIVE TRADING MODE ENABLED - REAL MONEY AT RISK
============================================================
Type 'YES' to confirm live trading: 
\`\`\`

Type `YES` to proceed.

**Expected Output:**
\`\`\`
2024-01-15 12:00:00 - INFO - Starting live trading in LIVE mode...
2024-01-15 12:00:05 - INFO - MT5 connected successfully
2024-01-15 12:00:05 - INFO - Account: 12345678, Balance: $10,000.00
2024-01-15 12:00:05 - INFO - Safety checks: PASSED
2024-01-15 12:00:05 - INFO - Max daily loss: $500.00 (5.0%)
2024-01-15 12:00:05 - INFO - Max open trades: 1
2024-01-15 12:00:05 - INFO - Monitoring EURUSD M15...
2024-01-15 12:15:00 - INFO - New bar: 2024-01-15 12:15:00
2024-01-15 12:15:02 - INFO - BUY signal detected at 1.0955
2024-01-15 12:15:03 - INFO - Placing LIVE order: BUY 0.10 lots, SL=1.0925, TP=1.1021
2024-01-15 12:15:04 - INFO - Order placed successfully, ticket=123456789
2024-01-15 12:15:04 - INFO - Position opened: BUY 0.10 EURUSD @ 1.0955
...
\`\`\`

## Step 8: Monitor Live Trading

**Daily Checklist:**
1. Check logs for errors
2. Review open positions
3. Monitor drawdown
4. Verify trades match expectations
5. Check account balance

**Weekly Review:**
\`\`\`python
# Generate weekly report
from smc_engine.backtest.metrics import calculate_metrics
from smc_engine.db.db import get_db
from smc_engine.db.models import LiveTrade
import pandas as pd
from datetime import datetime, timedelta

db = next(get_db())
week_ago = datetime.now() - timedelta(days=7)

trades = db.query(LiveTrade).filter(
    LiveTrade.entry_ts >= week_ago,
    LiveTrade.status == 'closed'
).all()

df = pd.DataFrame([{
    'pnl': t.pnl,
    'entry_ts': t.entry_ts,
    'exit_ts': t.exit_ts,
    'cum_equity': 10000 + sum([t2.pnl for t2 in trades[:i+1]])
} for i, t in enumerate(trades)])

metrics = calculate_metrics(df, 10000)
print(f"Weekly Performance:")
print(f"  Trades: {metrics['total_trades']}")
print(f"  Net PnL: ${metrics['net_profit']:.2f}")
print(f"  Win Rate: {metrics['win_rate']:.2f}%")
print(f"  Sharpe: {metrics['sharpe_ratio']:.2f}")
\`\`\`

## Step 9: Periodic Re-Optimization

Markets change, so re-optimize quarterly:

\`\`\`bash
# Every 3 months, re-run optimization on recent data
python -m smc_engine.main optimize \
  --strategy smc \
  --symbol EURUSD \
  --timeframe H1 \
  --start 2023-10-01 \
  --end 2024-01-15 \
  --param_space configs/param_space.json \
  --objective sharpe_ratio \
  --trials 200 \
  --method optuna \
  --constraints '{"max_drawdown_pct": 20, "min_trades": 30}' \
  --data_source mt5
\`\`\`

Compare new best parameters with current. If significantly different:
1. Backtest new parameters on recent data
2. Forward test in dry-run
3. Gradually transition to new parameters

## Troubleshooting

### No Signals Generated

**Check:**
\`\`\`python
# Verify data is loading
from smc_engine.data.mt5_manager import MT5Manager

manager = MT5Manager()
manager.connect()
data = manager.get_historical('EURUSD', 'M15', '2024-01-15', '2024-01-16')
print(f"Bars loaded: {len(data)}")
print(data.head())
\`\`\`

**Solution:**
- Ensure MT5 is running
- Verify symbol name
- Check timeframe format
- Review parameter thresholds (may be too strict)

### Orders Rejected

**Check:**
\`\`\`python
# Verify account status
info = manager.get_account_info()
print(f"Balance: {info['balance']}")
print(f"Margin Free: {info['margin_free']}")
print(f"Trade Allowed: {info['trade_allowed']}")
\`\`\`

**Solution:**
- Check margin/balance
- Verify lot size (min/max)
- Ensure symbol is tradeable
- Check trading hours

### Performance Degradation

**Check:**
- Market regime change (trending → ranging)
- Increased volatility
- Spread widening
- Execution delays

**Solution:**
- Re-optimize on recent data
- Adjust parameters for current conditions
- Consider pausing during high volatility
- Review and adjust risk management

## Summary

This workflow demonstrates:
1. ✅ Baseline backtest
2. ✅ Parameter optimization
3. ✅ Out-of-sample validation
4. ✅ Forward testing (dry-run)
5. ✅ Live trading deployment
6. ✅ Ongoing monitoring
7. ✅ Periodic re-optimization

**Key Takeaways:**
- Never skip validation steps
- Start with dry-run mode
- Monitor continuously
- Re-optimize regularly
- Manage risk conservatively

**Remember:** Past performance does not guarantee future results. Always trade responsibly.
