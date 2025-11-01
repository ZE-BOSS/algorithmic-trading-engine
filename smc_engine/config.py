"""
Configuration management using Pydantic settings.
Loads from environment variables and .env files.
"""

from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Database
    database_url: str = Field(
        default="sqlite:///./smc_trading.db",
        description="Database connection URL"
    )
    
    # MetaTrader5
    mt5_login: Optional[int] = Field(default=None, description="MT5 account login")
    mt5_password: Optional[str] = Field(default=None, description="MT5 account password")
    mt5_server: Optional[str] = Field(default=None, description="MT5 server name")
    
    # Trading Safety
    live_trading: bool = Field(default=False, description="Enable live trading (default: dry-run)")
    max_daily_loss_pct: float = Field(default=5.0, description="Maximum daily loss percentage")
    max_open_trades: int = Field(default=3, description="Maximum concurrent open trades")
    max_trade_risk_pct: float = Field(default=2.0, description="Maximum risk per trade")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: str = Field(default="logs/smc_engine.log", description="Log file path")
    
    # Optimization
    optuna_storage: str = Field(
        default="sqlite:///./optuna_studies.db",
        description="Optuna storage URL"
    )
    
    @field_validator("live_trading", mode="before")
    @classmethod
    def parse_live_trading(cls, v):
        """Parse live_trading from string or bool."""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)
    
    def validate_mt5_config(self) -> bool:
        """Check if MT5 configuration is complete."""
        return all([
            self.mt5_login,
            self.mt5_password,
            self.mt5_server
        ])


# Global settings instance
settings = Settings()
