"""
High-level orchestrator for backtest, optimize, and live trading workflows.

This module coordinates:
- Backtesting
- Optimization
- Live trading
- Database persistence

Improvements:
- Added database persistence helpers:
    - _save_backtest_to_db(...)
    - _save_optimization_to_db(...)
- Improved run_live_trading(...) loop with safety checks, polling, and graceful shutdown.
- Thorough logging and error handling.
"""

import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import json

from .core.strategy import SMCStrategy
from .data.marketdata import MarketDataProvider
from .backtest.backtester import Backtester
from .optimize.optimizer import Optimizer
from .data.mt5_manager import MT5Manager
from .db.db import get_session
from .db.models import (
    Strategy as StrategyModel,
    StrategyParameter as StrategyParameterModel,
    Backtest as BacktestModel,
    BacktestTrade as BacktestTradeModel,
    OptimizationRun as OptimizationRunModel,
    OptimizationTrial as OptimizationTrialModel,
    LiveTrade as LiveTradeModel,
)
from .config import settings

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    High-level orchestrator for trading workflows.

    Responsibilities:
    - Run backtests and persist results
    - Run optimizations and persist runs/trials
    - Run live trading loop (dry-run or real) with safety checks
    """

    def __init__(self):
        """Initialize orchestrator with a default CSV market data provider."""
        self.market_data = MarketDataProvider(source="csv")

    def _to_jsonable(self, obj):
        if isinstance(obj, dict):
            return {k: self._to_jsonable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._to_jsonable(v) for v in obj]
        elif hasattr(obj, "__dict__"):
            return self._to_jsonable(vars(obj))
        elif isinstance(obj, (np.floating, np.integer)):
            return obj.item()
        elif isinstance(obj, (datetime,)):
            return obj.isoformat()
        else:
            return obj
    
    def to_safe_json(self, data):
        return json.loads(json.dumps(self._to_jsonable(data)))

    # ---------------------------
    # Live trading
    # ---------------------------
    def run_live_trading(
        self,
        strategy_name: str,
        params: Dict[str, Any],
        symbol: str,
        timeframe: str,
        mode: str = 'dryrun'
    ):
        """
        Run live trading loop.

        Behavior:
        - Connects to MT5 via MT5Manager
        - Polls for the latest bars periodically (settings.live_trade_poll_interval)
        - Uses SMCStrategy.generate_signals() on the most recent data window
        - Applies safety checks and places orders (or simulates them in dry-run)
        - Logs each action and returns on KeyboardInterrupt

        Notes:
        - This loop is intentionally simple and poll-based (no websocket/tick subscription).
        - For low-latency automated execution, consider event-driven architecture.
        """
        logger.info(f"Starting live trading: {strategy_name}, mode={mode}")

        # Safety: ensure live mode allowed in settings
        if mode == 'live' and not settings.live_trading:
            logger.error("Live trading disabled in settings. Set LIVE_TRADING=true to enable.")
            return

        # Create MT5 manager and connect
        dry_run = (mode == 'dryrun')
        mt5_manager = MT5Manager(dry_run=dry_run)

        if not mt5_manager.connect():
            logger.error("Failed to connect to MT5")
            return

        # Create strategy instance
        if strategy_name.lower() == 'smc':
            strategy = SMCStrategy(params)
        else:
            logger.error(f"Unknown strategy: {strategy_name}")
            return

        poll_interval = getattr(settings, "live_trade_poll_interval", 30)
        lookback_bars = max(params.get('lookback', params.get('swing_lookback', 50)),
                            params.get('atr_period', 14)) + 10

        logger.info(f"Live trading loop started (poll every {poll_interval}s). Lookback bars: {lookback_bars}")
        logger.info("Press Ctrl+C to stop live trading.")

        try:
            while True:
                # 1) Fetch recent OHLC bars (we fetch a bit more than lookback)
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(hours=max(lookback_bars, 24))  # conservative window
                try:
                    ohlc = self.market_data.get_data(
                        symbol=symbol,
                        timeframe=timeframe,
                        start=start_time,
                        end=end_time
                    )
                except Exception as e:
                    logger.exception(f"Failed to fetch market data in live loop: {e}")
                    time.sleep(poll_interval)
                    continue

                if ohlc is None or len(ohlc) < lookback_bars:
                    logger.warning("Not enough bars to generate signals; waiting.")
                    time.sleep(poll_interval)
                    continue

                # 2) Generate signals
                try:
                    signals_df = strategy.generate_signals(ohlc.tail(lookback_bars))
                except Exception as e:
                    logger.exception(f"Strategy signal generation failed: {e}")
                    time.sleep(poll_interval)
                    continue

                if signals_df is None or signals_df.empty:
                    logger.debug("No signals this tick.")
                    time.sleep(poll_interval)
                    continue

                # Only consider most recent signals (one per bar; process newest rows)
                for _, sig in signals_df.sort_values('ts').iterrows():
                    ts = sig['ts']
                    signal = sig['signal']
                    price = float(sig['price'])
                    sl = float(sig['stop']) if sig.get('stop') is not None else None
                    tp = float(sig['tp']) if sig.get('tp') is not None else None

                    logger.info(f"Signal at {ts}: {signal} {symbol} @ {price} (sl={sl}, tp={tp})")

                    # 3) Safety check (account-level)
                    if not mt5_manager._check_trading_allowed():
                        logger.warning("Trading not allowed by safety checks. Skipping signal.")
                        continue

                    # 4) Place or simulate order
                    res = mt5_manager.place_order(
                        symbol=symbol,
                        side=signal,
                        volume=params.get('trade_volume', params.get('volume', 0.01)),
                        price=None,  # market price unless limit is wanted
                        sl=sl,
                        tp=tp,
                        order_type='market',
                        comment=f"SMC live {mode}"
                    )

                    if not res.success:
                        logger.warning(f"Order failed / simulated failure: {res.message}")
                    else:
                        logger.info(f"Order executed: ticket={res.ticket}, price={res.price}, volume={res.volume}")
                        # Optionally persist the live trade to DB (simple example):
                        try:
                            with get_session() as session:
                                lt = LiveTradeModel(
                                    strategy_id=None,  # Fill if you have strategy row id
                                    ticket=res.ticket,
                                    symbol=symbol,
                                    side=signal,
                                    entry_ts=datetime.utcnow(),
                                    exit_ts=None,
                                    entry_price=res.price,
                                    exit_price=None,
                                    volume=res.volume,
                                    pnl=None,
                                    status='open' if mode == 'live' else 'simulated',
                                    raw_mt5_response=res.raw_response
                                )
                                session.add(lt)
                                session.commit()
                                logger.debug("Persisted LiveTrade to DB (simulated/open).")
                        except Exception:
                            logger.exception("Failed to persist LiveTrade to DB.")

                # sleep until next poll
                time.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info("Live trading stopped by user (KeyboardInterrupt).")

        except Exception as e:
            logger.exception(f"Unhandled exception in live trading loop: {e}")

        finally:
            mt5_manager.disconnect()
            logger.info("Live trading: disconnected and exiting loop.")


    # ---------------------------
    # Backtest / Optimize methods
    # ---------------------------
    def run_backtest(
        self,
        strategy_name: str,
        params: Dict[str, Any],
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        initial_balance: float = 10000.0,
        csv_path: Optional[str] = None,
        save_to_db: bool = True,
        source: str = "csv"
    ) -> Dict[str, Any]:
        """
        Run a backtest and optionally persist results to the database.

        Returns:
            result dict produced by Backtester.run(...)
        """
        logger.info(f"Running backtest: {strategy_name} on {symbol} {timeframe}")

        # Update source
        self.market_data = MarketDataProvider(source)

        # Load data
        ohlc = self.market_data.get_data(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            csv_path=csv_path
        )

        logger.info(f"Loaded {len(ohlc)} bars")

        # Create strategy
        if strategy_name.lower() == "smc":
            strategy = SMCStrategy(params)
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        # Run backtest
        backtester = Backtester(strategy=strategy, initial_balance=initial_balance)
        result = backtester.run(ohlc)

        print(backtester.report())

        start_ts = datetime.fromisoformat(str(start)) if isinstance(start, str) else start
        end_ts = datetime.fromisoformat(str(end)) if isinstance(end, str) else end

        # Save to database
        backtest_id = None
        if save_to_db:
            try:
                backtest_id = self._save_backtest_to_db(
                    strategy_name=strategy_name,
                    params=params,
                    symbol=symbol,
                    timeframe=timeframe,
                    start=start_ts,
                    end=end_ts,
                    initial_balance=initial_balance,
                    result=result,
                )
            except Exception as e:
                logger.exception(f"Failed to persist backtest: {e}")

        # Return structured output
        result_dict = vars(result) if hasattr(result, "__dict__") else result
        result_dict["backtest_id"] = backtest_id
        return result_dict

    def run_optimization(
        self,
        strategy_name: str,
        param_space: Dict[str, Any],
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        objective: str = "sharpe",
        method: str = "optuna",
        source: str = "csv",
        n_trials: int = 100,
        csv_path: Optional[str] = None,
        save_to_db: bool = True,
    ) -> Dict[str, Any]:
        """
        Run parameter optimization and optionally save run + trials to DB.

        Returns:
            A dictionary summarizing optimization results.
        """
        logger.info(f"Running optimization: {strategy_name}, method={method}, trials={n_trials}")

        self.market_data = MarketDataProvider(source)

        # Load data
        ohlc = self.market_data.get_data(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            csv_path=csv_path,
        )

        # Create optimizer
        if strategy_name.lower() == "smc":
            strategy_class = SMCStrategy
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        optimizer = Optimizer(
            strategy_class=strategy_class,
            param_space=param_space,
            ohlc=ohlc,
            objective=objective,
        )

        result = optimizer.optimize(method=method, n_trials=n_trials)

        # Print summary
        print(f"\n=== Optimization Results ===")
        print(f"Best Score: {result.best_score:.4f}")
        print(f"Best Parameters:")
        for key, value in result.best_params.items():
            print(f"  {key}: {value}")

        print(f"\nTop 5 Parameter Sets:")
        for i, params in enumerate(result.top_n_params[:5], 1):
            print(f"{i}. {params}")

        if save_to_db:
            try:
                self._save_optimization_to_db(
                    strategy_name=strategy_name,
                    param_space=param_space,
                    objective=objective,
                    method=method,
                    result=result,
                )
            except Exception as e:
                logger.exception(f"Failed to persist optimization run: {e}")

        return {
            "best_params": result.best_params,
            "best_score": result.best_score,
            "all_trials": result.all_trials,
            "top_n_params": result.top_n_params,
        }

    # ---------------------------
    # Database persistence helpers
    # ---------------------------
    def _save_backtest_to_db(
        self,
        strategy_name: str,
        params: Dict[str, Any],
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        initial_balance: float,
        result: Any,
    ) -> Optional[str]:
        """
        Persist backtest results to the database.

        Handles both object-based and dictionary-based result structures.
        """
        logger.info("Persisting backtest to DB...")
        session_ctx = get_session()

        with session_ctx as session:
            try:
                # Normalize result
                result_dict = vars(result) if hasattr(result, "__dict__") else result
                metrics_obj = result_dict.get("metrics", {})
                metrics = self.to_safe_json(metrics_obj)

                final_balance = (
                    result_dict.get("final_balance")
                    or (metrics.get("final_balance") if isinstance(metrics, dict) else None)
                )

                # Strategy
                strategy_row = session.query(StrategyModel).filter_by(name=strategy_name).first()
                if not strategy_row:
                    strategy_row = StrategyModel(
                        name=strategy_name,
                        description=f"Auto-created strategy {strategy_name}",
                        default_params=params,
                    )
                    session.add(strategy_row)
                    session.flush()

                # StrategyParameter
                param_row = StrategyParameterModel(
                    strategy_id=strategy_row.id,
                    params=params,
                    label=f"backtest-{datetime.utcnow().isoformat()}",
                )
                session.add(param_row)
                session.flush()

                # Backtest
                backtest_row = BacktestModel(
                    strategy_id=strategy_row.id,
                    params_id=param_row.id,
                    symbol=symbol,
                    timeframe=timeframe,
                    start_ts=start,
                    end_ts=end,
                    initial_balance=initial_balance,
                    final_balance=final_balance or 0.0,
                    metrics=metrics or result_dict,
                )
                session.add(backtest_row)
                session.flush()

                # Trades
                trades = result_dict.get("trades") or getattr(result, "trades", [])
                for t in trades:
                    tdata = vars(t) if hasattr(t, "__dict__") else t
                    trade = BacktestTradeModel(
                        backtest_id=backtest_row.id,
                        trade_index=int(tdata.get("trade_index", 0)),
                        entry_ts=tdata.get("entry_ts") or tdata.get("entry_time"),
                        exit_ts=tdata.get("exit_ts") or tdata.get("exit_time"),
                        side=tdata.get("side", "buy"),
                        entry_price=float(tdata.get("entry_price", 0)),
                        exit_price=float(tdata.get("exit_price", 0)),
                        volume=float(tdata.get("volume", 0)),
                        pnl=float(tdata.get("pnl", 0)),
                        fees=float(tdata.get("fees", 0)),
                        cum_equity=float(tdata.get("cum_equity", 0)),
                        exit_reason=tdata.get("exit_reason"),
                        extra=tdata.get("extra"),
                    )
                    session.add(trade)

                session.commit()
                logger.info(f"Backtest persisted: id={backtest_row.id}, trades={len(trades)}")
                return backtest_row.id

            except Exception as e:
                session.rollback()
                logger.exception(f"Failed to persist backtest: {e}")
                raise

    def _save_optimization_to_db(
        self,
        strategy_name: str,
        param_space: Dict[str, Any],
        objective: str,
        method: str,
        result: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Persist optimization run and trials.
        Handles both class-based and dict-based result objects.
        """
        import pandas as pd
        import uuid

        logger.info("Persisting optimization run to DB...")
        session_ctx = get_session()

        with session_ctx as session:
            try:
                # Ensure strategy exists
                strategy_row = session.query(StrategyModel).filter_by(name=strategy_name).first()
                if not strategy_row:
                    strategy_row = StrategyModel(
                        name=strategy_name,
                        description=f"Auto-created strategy {strategy_name}",
                        default_params={},
                    )
                    session.add(strategy_row)
                    session.flush()

                # --- Safe access helper ---
                def get_attr(obj, name, default=None):
                    return getattr(obj, name, default) if hasattr(obj, name) else default

                # Extract safely from both object or dict
                best_score = get_attr(result, "best_score", 0.0)
                metrics_summary = get_attr(result, "metrics_summary", None)
                best_params = get_attr(result, "best_params", None)
                all_trials = get_attr(result, "all_trials", None)

                # --- Handle DataFrame ---
                if isinstance(all_trials, pd.DataFrame):
                    all_trials = all_trials.to_dict(orient="records")
                elif not all_trials:
                    all_trials = []

                # Create optimization run record
                run_id = str(uuid.uuid4())
                run_row = OptimizationRunModel(
                    id=run_id,
                    strategy_id=strategy_row.id,
                    param_space=param_space,
                    objective=objective,
                    method=method,
                    best_score=float(best_score or 0.0),
                    metrics_summary=metrics_summary,
                )
                session.add(run_row)
                session.flush()

                # Save best parameters
                if best_params:
                    param_row = StrategyParameterModel(
                        strategy_id=strategy_row.id,
                        params=best_params,
                        label=f"opt-best-{datetime.utcnow().isoformat()}",
                    )
                    session.add(param_row)
                    session.flush()
                    run_row.best_params_id = param_row.id
                    session.add(run_row)

                # Persist all trials
                for trial in all_trials:
                    if hasattr(trial, "__dict__"):
                        trial = vars(trial)
                    trial_row = OptimizationTrialModel(
                        optimization_id=run_row.id,
                        trial_number=int(trial.get("trial_number", 0)),
                        trial_params=trial.get("params", {}),
                        metrics=trial.get("metrics", {}),
                        score=float(trial.get("value", trial.get("score", 0))),
                    )
                    session.add(trial_row)

                session.commit()
                logger.info(f"Optimization run persisted successfully: id={run_id}")

                # Return dict to satisfy main.py expectations
                return {"run_id": run_id}

            except Exception as e:
                session.rollback()
                logger.exception(f"Failed to persist optimization run: {e}")
                raise
