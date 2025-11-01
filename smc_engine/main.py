"""
CLI entry point for SMC Trading Engine.
Provides commands: backtest, optimize, live
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
import logging

from smc_engine.config import Settings
from smc_engine.orchestrator import Orchestrator
from smc_engine.db.db import init_db

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('smc_engine.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def load_json_file(filepath: str) -> dict:
    """Load JSON configuration file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        sys.exit(1)


def cmd_backtest(args):
    """Run backtest command."""
    logger.info("Starting backtest...")
    
    # Load parameters
    params = load_json_file(args.params) if args.params else {}
    
    # Initialize orchestrator
    orchestrator = Orchestrator()
    
    # Run backtest
    result = orchestrator.run_backtest(
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        initial_balance=args.initial_balance,
        params=params,
        source=args.data_source,
        csv_path=args.csv_path
    )
    
    # Handle MetricsResult object safely
    metrics = getattr(result, "metrics", None)

    if metrics:
        logger.info(f"Net Profit: ${metrics.net_profit:.2f}")
        logger.info(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        logger.info(f"Max Drawdown: {metrics.max_drawdown_pct:.2f}%")
        logger.info(f"Win Rate: {metrics.win_rate:.2f}%")
        logger.info(f"Total Trades: {metrics.total_trades}")
    else:
        logger.warning("No metrics found in result.")

    # Optional backtest_id if returned separately
    backtest_id = getattr(result, "backtest_id", None)
    if backtest_id:
        logger.info(f"Backtest completed. Backtest ID: {backtest_id}")
    else:
        logger.info("Backtest completed (not persisted or no ID returned).")

    
    return result


def cmd_optimize(args):
    """Run optimization command."""
    logger.info("Starting optimization...")
    
    # Load parameter space
    param_space = load_json_file(args.param_space)
    
    # Initialize orchestrator
    orchestrator = Orchestrator()
    
    # Run optimization
    result = orchestrator.run_optimization(
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        param_space=param_space,
        objective=args.objective,
        n_trials=args.trials,
        method=args.method,
        source=args.data_source,
        csv_path=args.csv_path
    )
    
    # Handle result from _save_optimization_to_db (could be str or dict-like)
    if isinstance(result, dict):
        run_id = result.get("run_id")
        best_value = result.get("best_value", 0.0)
        best_params = result.get("best_params", {})
        top_trials = result.get("top_trials", [])
    else:
        # Fallback in case it's not a dict (e.g., just the run_id string)
        run_id = str(result)
        best_value = getattr(result, "best_score", 0.0)
        best_params = getattr(result, "best_params", {})
        top_trials = getattr(result, "top_trials", [])

    logger.info(f"Optimization completed. Run ID: {run_id}")
    logger.info(f"Best {args.objective}: {best_value:.4f}")
    logger.info("Best parameters:")
    for key, value in (best_params or {}).items():
        logger.info(f"  {key}: {value}")

    if top_trials:
        logger.info("\nTop 5 parameter sets:")
        for i, trial in enumerate(top_trials[:5], 1):
            val = trial.get("value", trial.get("score", 0.0))
            params = trial.get("params", {})
            logger.info(f"{i}. {args.objective}={val:.4f}, params={params}")
    else:
        logger.info("No trial data available.")

    return {
        "run_id": run_id,
        "best_value": best_value,
        "best_params": best_params,
        "top_trials": top_trials,
    }


def cmd_live(args):
    """Run live trading command."""
    settings = Settings()
    
    # Safety check
    if args.mode == 'live' and not settings.LIVE_TRADING_ENABLED:
        logger.error("Live trading is disabled. Set LIVE_TRADING=true in .env to enable.")
        logger.error("Use --mode dryrun for simulation without real orders.")
        sys.exit(1)
    
    if args.mode == 'live':
        logger.warning("=" * 60)
        logger.warning("LIVE TRADING MODE ENABLED - REAL MONEY AT RISK")
        logger.warning("=" * 60)
        response = input("Type 'YES' to confirm live trading: ")
        if response != 'YES':
            logger.info("Live trading cancelled.")
            sys.exit(0)
    
    logger.info(f"Starting live trading in {args.mode.upper()} mode...")
    
    # Load parameters
    params = load_json_file(args.params) if args.params else {}
    
    # Initialize orchestrator
    orchestrator = Orchestrator()
    
    # Run live trading
    orchestrator.run_live(
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
        params=params,
        mode=args.mode
    )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='SMC Trading Engine - Backtest, Optimize, and Live Trade',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Backtest command
    backtest_parser = subparsers.add_parser('backtest', help='Run backtest')
    backtest_parser.add_argument('--strategy', default='smc', help='Strategy name (default: smc)')
    backtest_parser.add_argument('--symbol', required=True, help='Trading symbol (e.g., EURUSD)')
    backtest_parser.add_argument('--timeframe', required=True, help='Timeframe (e.g., H1, M15)')
    backtest_parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    backtest_parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    backtest_parser.add_argument('--params', help='Path to parameters JSON file')
    backtest_parser.add_argument('--initial_balance', type=float, default=10000.0, help='Initial balance')
    backtest_parser.add_argument('--data_source', default='csv', choices=['csv', 'mt5'], help='Data source')
    backtest_parser.add_argument('--csv_path', help='Path to CSV file (if data_source=csv)')
    
    # Optimize command
    optimize_parser = subparsers.add_parser('optimize', help='Run optimization')
    optimize_parser.add_argument('--strategy', default='smc', help='Strategy name (default: smc)')
    optimize_parser.add_argument('--symbol', required=True, help='Trading symbol')
    optimize_parser.add_argument('--timeframe', required=True, help='Timeframe')
    optimize_parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    optimize_parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    optimize_parser.add_argument('--param_space', required=True, help='Path to parameter space JSON')
    optimize_parser.add_argument('--objective', default='sharpe_ratio', help='Optimization objective')
    optimize_parser.add_argument('--trials', type=int, default=100, help='Number of trials')
    optimize_parser.add_argument('--method', default='optuna', choices=['grid', 'random', 'optuna'], help='Optimization method')
    optimize_parser.add_argument('--initial_balance', type=float, default=10000.0, help='Initial balance')
    optimize_parser.add_argument('--constraints', help='JSON string of constraints (e.g., {"max_drawdown_pct": 20})')
    optimize_parser.add_argument('--data_source', default='csv', choices=['csv', 'mt5'], help='Data source')
    optimize_parser.add_argument('--csv_path', help='Path to CSV file')
    
    # Live command
    live_parser = subparsers.add_parser('live', help='Run live trading')
    live_parser.add_argument('--strategy', default='smc', help='Strategy name')
    live_parser.add_argument('--symbol', required=True, help='Trading symbol')
    live_parser.add_argument('--timeframe', required=True, help='Timeframe')
    live_parser.add_argument('--params', help='Path to parameters JSON file')
    live_parser.add_argument('--mode', required=True, choices=['dryrun', 'live'], help='Trading mode')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Initialize database
    init_db()
    
    # Execute command
    try:
        if args.command == 'backtest':
            cmd_backtest(args)
        elif args.command == 'optimize':
            cmd_optimize(args)
        elif args.command == 'live':
            cmd_live(args)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Error executing {args.command}: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
