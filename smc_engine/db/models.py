"""
SQLAlchemy database models for SMC trading engine.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()


def generate_uuid():
    """Generate UUID string."""
    return str(uuid.uuid4())


class Strategy(Base):
    """Strategy definitions."""
    __tablename__ = 'strategies'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text)
    code_hash = Column(String)
    default_params = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    parameters = relationship("StrategyParameter", back_populates="strategy")
    backtests = relationship("Backtest", back_populates="strategy")
    optimization_runs = relationship("OptimizationRun", back_populates="strategy")
    live_trades = relationship("LiveTrade", back_populates="strategy")


class StrategyParameter(Base):
    """Strategy parameter sets."""
    __tablename__ = 'strategy_parameters'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    strategy_id = Column(String, ForeignKey('strategies.id'))
    params = Column(JSON, nullable=False)
    label = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="parameters")
    backtests = relationship("Backtest", back_populates="params")


class Backtest(Base):
    """Backtest runs."""
    __tablename__ = 'backtests'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    strategy_id = Column(String, ForeignKey('strategies.id'))
    params_id = Column(String, ForeignKey('strategy_parameters.id'))
    
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    start_ts = Column(DateTime, nullable=False)
    end_ts = Column(DateTime, nullable=False)
    
    initial_balance = Column(Float, nullable=False)
    final_balance = Column(Float)
    
    metrics = Column(JSON)  # All performance metrics
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="backtests")
    params = relationship("StrategyParameter", back_populates="backtests")
    trades = relationship("BacktestTrade", back_populates="backtest")


class BacktestTrade(Base):
    """Individual trades from backtests."""
    __tablename__ = 'backtest_trades'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    backtest_id = Column(String, ForeignKey('backtests.id'))
    
    trade_index = Column(Integer, nullable=False)
    entry_ts = Column(DateTime, nullable=False)
    exit_ts = Column(DateTime, nullable=False)
    side = Column(String, nullable=False)
    
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    
    pnl = Column(Float, nullable=False)
    fees = Column(Float, nullable=False)
    cum_equity = Column(Float, nullable=False)
    
    exit_reason = Column(String)
    extra = Column(JSON)  # Additional metadata
    
    # Relationships
    backtest = relationship("Backtest", back_populates="trades")


class OptimizationRun(Base):
    """Optimization runs."""
    __tablename__ = 'optimization_runs'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    strategy_id = Column(String, ForeignKey('strategies.id'))
    
    param_space = Column(JSON, nullable=False)
    objective = Column(String, nullable=False)
    method = Column(String)  # grid, random, optuna
    
    best_params_id = Column(String, ForeignKey('strategy_parameters.id'), nullable=True)
    best_score = Column(Float)
    
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    
    metrics_summary = Column(JSON)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="optimization_runs")
    trials = relationship("OptimizationTrial", back_populates="optimization_run")


class OptimizationTrial(Base):
    """Individual optimization trials."""
    __tablename__ = 'optimization_trials'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    optimization_id = Column(String, ForeignKey('optimization_runs.id'))
    
    trial_number = Column(Integer, nullable=False)
    trial_params = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=False)
    score = Column(Float, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    optimization_run = relationship("OptimizationRun", back_populates="trials")


class LiveTrade(Base):
    """Live trading executions."""
    __tablename__ = 'live_trades'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    strategy_id = Column(String, ForeignKey('strategies.id'))
    
    ticket = Column(Integer)  # MT5 ticket number
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    
    entry_ts = Column(DateTime, nullable=False)
    exit_ts = Column(DateTime)
    
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float)
    volume = Column(Float, nullable=False)
    
    pnl = Column(Float)
    status = Column(String, nullable=False)  # open, closed, cancelled
    
    raw_mt5_response = Column(JSON)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="live_trades")


class ActionLog(Base):
    """Action and event log."""
    __tablename__ = 'actions_log'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    action_type = Column(String, nullable=False)
    payload = Column(JSON)
    result = Column(JSON)
