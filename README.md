# SMC Trading Engine

A production-quality Python trading system implementing Smart Money Concepts (SMC) with backtesting, optimization, and live trading capabilities via MetaTrader5.

## Features

- **Smart Money Concepts Implementation**
  - Order Blocks (OB) detection with configurable methods
  - Fair Value Gaps (FVG) - imbalance and wick methods
  - Break of Structure (BOS) detection
  - Change of Character (ChoCH) identification
  - Liquidity Grab detection
  - Market Structure analysis (swing highs/lows)

- **Backtesting Engine**
  - Realistic simulation with spreads, commissions, slippage
  - Per-trade logging with detailed metrics
  - Equity curve generation
  - Monthly/annual returns analysis
  - Risk metrics (Sharpe, Calmar, Max Drawdown)

- **Optimization Framework**
  - Grid search for small parameter spaces
  - Random search for exploration
  - Optuna (Bayesian) optimization for large spaces
  - Configurable objectives and constraints
  - Trial persistence to database

- **Live Trading**
  - MetaTrader5 integration
  - Dry-run mode for safe testing
  - Position management and monitoring
  - Safety guards (max drawdown, daily loss limits)
  - Complete audit trail in database

## Architecture

\`\`\`
smc_engine/
├── core/              # Strategy and SMC primitives
├── data/              # MT5 integration and data management
├── backtest/          # Backtesting engine and metrics
├── optimize/          # Parameter optimization
├── db/                # Database models and migrations
└── orchestrator.py    # High-level workflow coordination
\`\`\`

## Installation

### Using Docker (Recommended)

\`\`\`bash
# Clone the repository
git clone <repo-url>
cd smc_engine

# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env

# Start services
docker-compose up -d

# Run migrations
docker-compose exec app alembic upgrade head
\`\`\`

### Local Installation

\`\`\`bash
# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup database
cp .env.example .env
# Edit .env with your DATABASE_URL

# Run migrations
alembic upgrade head
\`\`\`

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

\`\`\`env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/smc_trading

# MetaTrader5 (for live trading)
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=your_broker_server

# Safety
LIVE_TRADING=false  # Set to 'true' to enable real trading
MAX_DAILY_LOSS_PCT=5.0
MAX_OPEN_TRADES=3

# Logging
LOG_LEVEL=INFO
\`\`\`

### Strategy Parameters

Edit `configs/smc_params.json` to configure strategy behavior:

\`\`\`json
{
  "swing_lookback": 10,
  "bos_atr_margin": 0.5,
  "ob_min_impulse_bars": 3,
  "fvg_min_gap_atr": 0.3,
  "risk_per_trade": 0.02,
  "risk_reward_ratio": 2.0
}
\`\`\`

## Usage

### 1. Backtest

Run a backtest on historical data:

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
  --csv_path sample_data/EURUSD_H1_sample.csv
\`\`\`

**Output:**
- Backtest ID saved to database
- Per-trade logs in `backtest_trades` table
- Aggregated metrics (Sharpe, drawdown, win rate, etc.)
- Equity curve data

### 2. Optimize

Search for optimal parameters:

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
  --data_source csv \
  --csv_path sample_data/EURUSD_H1_sample.csv
\`\`\`

**Methods:**
- `grid` - Exhaustive search (small spaces only)
- `random` - Random sampling
- `optuna` - Bayesian optimization (recommended)

**Objectives:**
- `sharpe_ratio` - Risk-adjusted returns
- `net_profit` - Total profit
- `calmar_ratio` - Return/max drawdown
- `profit_factor` - Gross profit/gross loss

**Constraints:**
\`\`\`bash
--constraints '{"max_drawdown_pct": 20, "min_trades": 50}'
\`\`\`

### 3. Live Trading

#### Dry-Run Mode (Recommended First)

Test strategy in real-time without placing orders:

\`\`\`bash
export MT5_LOGIN=your_login
export MT5_PASSWORD=your_password
export MT5_SERVER=your_server

python -m smc_engine.main live \
  --strategy smc \
  --symbol EURUSD \
  --timeframe M15 \
  --params configs/smc_params.json \
  --mode dryrun
\`\`\`

#### Live Mode (Real Trading)

**⚠️ WARNING: Real money at risk!**

\`\`\`bash
# Enable live trading in .env
export LIVE_TRADING=true

python -m smc_engine.main live \
  --strategy smc \
  --symbol EURUSD \
  --timeframe M15 \
  --params configs/smc_params.json \
  --mode live
\`\`\`

You will be prompted to type 'YES' to confirm.

## Testing

### Run All Tests

\`\`\`bash
pytest tests/ -v
\`\`\`

### Run Specific Test Suites

\`\`\`bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Specific test file
pytest tests/unit/test_smc_primitives.py -v
\`\`\`

### Test Coverage

\`\`\`bash
pytest --cov=smc_engine --cov-report=html tests/
\`\`\`

## Database Schema

### Key Tables

- **strategies** - Strategy definitions and default parameters
- **backtests** - Backtest runs and aggregated metrics
- **backtest_trades** - Individual trade records
- **optimization_runs** - Optimization sessions
- **optimization_trials** - Individual parameter trials
- **live_trades** - Live trading activity
- **actions_log** - Audit trail of all system actions

### Migrations

\`\`\`bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
\`\`\`

## SMC Primitives Documentation

### Order Blocks (OB)

Order blocks represent institutional buying/selling zones. Detection algorithm:

1. Identify impulsive move: ≥ `min_impulse_bars` consecutive directional candles
2. Total move must exceed `min_impulse_atr` × ATR
3. Last opposite candle before impulse = order block
4. Expand zone by `ob_expansion_atr` × ATR

**Parameters:**
- `ob_min_impulse_bars` (2-5): Minimum consecutive candles
- `ob_min_impulse_atr` (1.0-2.5): Minimum move size
- `ob_expansion_atr` (0.1-0.5): Zone expansion
- `ob_detection_method` ('strict'|'relaxed'): Detection sensitivity

### Fair Value Gaps (FVG)

Price imbalances indicating inefficient trading. Two methods:

**Imbalance Method (Default):**
- 3-candle pattern: candle[i].high < candle[i+2].low (bullish)
- Gap must exceed `fvg_min_gap_atr` × ATR
- Expand by `fvg_expand_atr` × ATR

**Wick Method:**
- Detects gaps between wicks during rapid moves
- More sensitive, finds smaller imbalances

**Parameters:**
- `fvg_method` ('imbalance'|'wick'): Detection method
- `fvg_min_gap_atr` (0.2-0.6): Minimum gap size
- `fvg_expand_atr` (0.0-0.3): Gap expansion

### Break of Structure (BOS)

Price breaking previous swing high/low, indicating trend continuation.

**Detection:**
- Bullish BOS: close > last_swing_high + (`bos_atr_margin` × ATR)
- Bearish BOS: close < last_swing_low - (`bos_atr_margin` × ATR)

**Parameters:**
- `bos_atr_margin` (0.3-1.0): Margin above/below swing
- `bos_margin_pct` (0.0005-0.002): Percentage margin (alternative)

### Change of Character (ChoCH)

First BOS in opposite direction, signaling potential trend reversal.

**Detection:**
- Identify current trend direction
- Detect first valid BOS against trend
- Confirm with swing pattern flip (HH/HL → LH/LL)

**Parameters:**
- `choch_enabled` (true|false): Enable ChoCH detection

### Liquidity Grabs

Wick beyond swing level that quickly reverses, indicating stop hunt.

**Detection:**
1. Wick extends beyond swing by `liquidity_grab_atr` × ATR
2. Price reclaims structure within `liquidity_reclaim_bars` candles
3. Indicates potential reversal zone

**Parameters:**
- `liquidity_grab_atr` (0.5-1.5): Extension threshold
- `liquidity_reclaim_bars` (2-5): Reclaim window

### Market Structure

Swing high/low detection using configurable lookback.

**Detection:**
- Swing high: high[i] = max(high[i-n:i+n+1])
- Swing low: low[i] = min(low[i-n:i+n+1])

**Parameters:**
- `swing_lookback` (5-20): Lookback period

## Performance Metrics

### Risk-Adjusted Returns

- **Sharpe Ratio**: (Return - RiskFree) / StdDev
- **Calmar Ratio**: Annual Return / Max Drawdown
- **Sortino Ratio**: Return / Downside Deviation

### Trade Statistics

- **Win Rate**: Winning trades / Total trades
- **Profit Factor**: Gross Profit / Gross Loss
- **Expectancy**: Average win × win_rate - Average loss × loss_rate
- **Average R-Multiple**: Average profit/loss in R units

### Drawdown Analysis

- **Max Drawdown**: Largest peak-to-trough decline
- **Max Drawdown %**: Drawdown as percentage of peak
- **Drawdown Duration**: Time to recover from drawdown

## Safety Features

### Live Trading Guards

1. **Dry-Run Default**: Must explicitly enable live trading
2. **Confirmation Prompt**: Type 'YES' to confirm real trading
3. **Daily Loss Limit**: Stop trading if loss exceeds threshold
4. **Max Open Trades**: Limit concurrent positions
5. **Margin Check**: Verify sufficient margin before orders
6. **Trading Hours**: Optional time-based restrictions

### Risk Management

- **Position Sizing**: Fixed lot, % equity, or Kelly criterion
- **Stop Loss**: Always enforced, ATR-based
- **Take Profit**: Risk-reward ratio based
- **Max Risk Per Trade**: Configurable (default 2%)

## Troubleshooting

### MT5 Connection Issues

\`\`\`python
# Test MT5 connection
from smc_engine.data.mt5_manager import MT5Manager

manager = MT5Manager()
manager.connect()
print(manager.get_account_info())
\`\`\`

**Common Issues:**
- MT5 not installed: Install MetaTrader5 terminal
- Login failed: Check credentials in .env
- Symbol not found: Verify symbol name with broker

### Database Connection

\`\`\`bash
# Test database connection
python -c "from smc_engine.db.db import get_db; next(get_db())"
\`\`\`

### Backtest No Trades

**Possible Causes:**
1. Parameters too strict (no signals generated)
2. Insufficient data (not enough bars for indicators)
3. Timeframe mismatch

**Solutions:**
- Relax parameters (lower thresholds)
- Use longer data period
- Check data quality (gaps, errors)

## Development

### Project Structure

\`\`\`
smc_engine/
├── __init__.py
├── config.py              # Pydantic settings
├── main.py                # CLI entry point
├── orchestrator.py        # Workflow coordination
├── core/
│   ├── strategy.py        # Strategy base + SMC implementation
│   ├── signals.py         # Signal generation helpers
│   └── smc_primitives.py  # SMC detection algorithms
├── data/
│   ├── mt5_manager.py     # MT5 integration
│   └── marketdata.py      # Data fetching
├── backtest/
│   ├── backtester.py      # Backtest engine
│   ├── simulator.py       # Order simulation
│   └── metrics.py         # Performance metrics
├── optimize/
│   └── optimizer.py       # Parameter optimization
└── db/
    ├── models.py          # SQLAlchemy models
    ├── db.py              # Database session
    └── migrations/        # Alembic migrations
\`\`\`

### Adding New Strategies

1. Inherit from `Strategy` base class
2. Implement `generate_signals()` method
3. Define `default_param_space()`
4. Add validation in `validate_params()`

\`\`\`python
from smc_engine.core.strategy import Strategy

class MyStrategy(Strategy):
    def generate_signals(self, ohlc):
        # Your logic here
        return signals_df
    
    def default_param_space(self):
        return {
            'param1': {'type': 'int', 'low': 1, 'high': 10},
            'param2': {'type': 'float', 'low': 0.1, 'high': 1.0}
        }
\`\`\`

### Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Ensure all tests pass (`pytest tests/`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open Pull Request

## License

MIT License - see LICENSE file for details

## Disclaimer

**This software is for educational purposes only. Trading involves substantial risk of loss. Past performance does not guarantee future results. The authors are not responsible for any financial losses incurred through use of this software.**

## Support

- Documentation: See `DEVELOPER_NOTES.md` for implementation details
- Issues: Open an issue on GitHub
- Examples: See `example_run.md` for complete workflow

## Roadmap

- [ ] Multi-symbol portfolio backtesting
- [ ] Web UI for monitoring and control
- [ ] Real-time visualization of SMC levels
- [ ] Telegram/Slack notifications
- [ ] Additional optimization algorithms
- [ ] Machine learning integration
- [ ] Alternative data sources (Binance, Interactive Brokers)
