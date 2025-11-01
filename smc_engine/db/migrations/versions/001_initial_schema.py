"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Strategies table
    op.create_table(
        'strategies',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text),
        sa.Column('code_hash', sa.String(64)),
        sa.Column('default_params', JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    
    # Strategy parameters table
    op.create_table(
        'strategy_parameters',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('strategy_id', UUID(as_uuid=True), sa.ForeignKey('strategies.id'), nullable=False),
        sa.Column('label', sa.String(100)),
        sa.Column('params', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_strategy_parameters_strategy_id', 'strategy_parameters', ['strategy_id'])
    
    # Backtests table
    op.create_table(
        'backtests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('strategy_id', UUID(as_uuid=True), sa.ForeignKey('strategies.id'), nullable=False),
        sa.Column('params_id', UUID(as_uuid=True), sa.ForeignKey('strategy_parameters.id')),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('start_date', sa.DateTime, nullable=False),
        sa.Column('end_date', sa.DateTime, nullable=False),
        sa.Column('initial_balance', sa.Float, nullable=False),
        sa.Column('final_balance', sa.Float),
        sa.Column('metrics', JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_backtests_strategy_id', 'backtests', ['strategy_id'])
    op.create_index('ix_backtests_created_at', 'backtests', ['created_at'])
    
    # Backtest trades table
    op.create_table(
        'backtest_trades',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('backtest_id', UUID(as_uuid=True), sa.ForeignKey('backtests.id'), nullable=False),
        sa.Column('trade_index', sa.Integer, nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('size', sa.Float, nullable=False),
        sa.Column('entry_ts', sa.DateTime, nullable=False),
        sa.Column('exit_ts', sa.DateTime),
        sa.Column('entry_price', sa.Float, nullable=False),
        sa.Column('exit_price', sa.Float),
        sa.Column('stop_loss', sa.Float),
        sa.Column('take_profit', sa.Float),
        sa.Column('pnl', sa.Float),
        sa.Column('fees', sa.Float, server_default='0'),
        sa.Column('cum_equity', sa.Float),
        sa.Column('exit_reason', sa.String(50)),
        sa.Column('meta', JSONB, server_default='{}'),
    )
    op.create_index('ix_backtest_trades_backtest_id', 'backtest_trades', ['backtest_id'])
    op.create_index('ix_backtest_trades_entry_ts', 'backtest_trades', ['entry_ts'])
    
    # Optimization runs table
    op.create_table(
        'optimization_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('strategy_id', UUID(as_uuid=True), sa.ForeignKey('strategies.id'), nullable=False),
        sa.Column('param_space', JSONB, nullable=False),
        sa.Column('objective', sa.String(50), nullable=False),
        sa.Column('method', sa.String(20), nullable=False),
        sa.Column('best_params_id', UUID(as_uuid=True), sa.ForeignKey('strategy_parameters.id')),
        sa.Column('best_value', sa.Float),
        sa.Column('n_trials', sa.Integer),
        sa.Column('started_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime),
        sa.Column('metrics_summary', JSONB, server_default='{}'),
    )
    op.create_index('ix_optimization_runs_strategy_id', 'optimization_runs', ['strategy_id'])
    
    # Optimization trials table
    op.create_table(
        'optimization_trials',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('optimization_id', UUID(as_uuid=True), sa.ForeignKey('optimization_runs.id'), nullable=False),
        sa.Column('trial_number', sa.Integer, nullable=False),
        sa.Column('trial_params', JSONB, nullable=False),
        sa.Column('metrics', JSONB, nullable=False),
        sa.Column('value', sa.Float, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_optimization_trials_optimization_id', 'optimization_trials', ['optimization_id'])
    op.create_index('ix_optimization_trials_value', 'optimization_trials', ['value'])
    
    # Live trades table
    op.create_table(
        'live_trades',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('strategy_id', UUID(as_uuid=True), sa.ForeignKey('strategies.id'), nullable=False),
        sa.Column('ticket', sa.String(50)),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('size', sa.Float, nullable=False),
        sa.Column('entry_ts', sa.DateTime, nullable=False),
        sa.Column('exit_ts', sa.DateTime),
        sa.Column('entry_price', sa.Float, nullable=False),
        sa.Column('exit_price', sa.Float),
        sa.Column('pnl', sa.Float),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('raw_mt5_response', JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_live_trades_strategy_id', 'live_trades', ['strategy_id'])
    op.create_index('ix_live_trades_status', 'live_trades', ['status'])
    
    # Actions log table
    op.create_table(
        'actions_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('timestamp', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('payload', JSONB, nullable=False, server_default='{}'),
        sa.Column('result', JSONB, server_default='{}'),
    )
    op.create_index('ix_actions_log_timestamp', 'actions_log', ['timestamp'])
    op.create_index('ix_actions_log_action_type', 'actions_log', ['action_type'])


def downgrade() -> None:
    op.drop_table('actions_log')
    op.drop_table('live_trades')
    op.drop_table('optimization_trials')
    op.drop_table('optimization_runs')
    op.drop_table('backtest_trades')
    op.drop_table('backtests')
    op.drop_table('strategy_parameters')
    op.drop_table('strategies')
