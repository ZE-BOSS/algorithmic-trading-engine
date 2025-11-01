"""
Strategy parameter optimization using grid search, random search, and Optuna.
"""

import optuna
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

from ..core.strategy import Strategy
from ..backtest.backtester import Backtester
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of parameter optimization."""
    best_params: Dict[str, Any]
    best_score: float
    all_trials: pd.DataFrame
    top_n_params: List[Dict[str, Any]]
    study: Optional[optuna.Study] = None


class Optimizer:
    """
    Parameter optimization engine.
    
    Supports:
    - Grid search (exhaustive)
    - Random search (sampling)
    - Bayesian optimization (Optuna/TPE)
    """
    
    def __init__(
        self,
        strategy_class: type,
        param_space: Dict[str, Any],
        ohlc: pd.DataFrame,
        objective: str = 'sharpe',
        constraints: Optional[Dict[str, Any]] = None,
        initial_balance: float = 10000.0
    ):
        """
        Initialize optimizer.
        
        Args:
            strategy_class: Strategy class to optimize
            param_space: Parameter space definition
            ohlc: Historical data for backtesting
            objective: Optimization objective ('sharpe', 'net_profit', 'calmar', etc.)
            constraints: Constraints dict (e.g., {'max_drawdown_pct': 20})
            initial_balance: Starting balance for backtests
        """
        self.strategy_class = strategy_class
        self.param_space = param_space
        self.ohlc = ohlc
        self.objective = objective
        self.constraints = constraints or {}
        self.initial_balance = initial_balance
        
        self.trials_data = []
    
    def optimize(
        self,
        method: str = 'optuna',
        n_trials: int = 100,
        n_jobs: int = 1,
        random_seed: int = 42
    ) -> OptimizationResult:
        """
        Run parameter optimization.
        
        Args:
            method: 'grid', 'random', or 'optuna'
            n_trials: Number of trials (for random/optuna)
            n_jobs: Number of parallel jobs
            random_seed: Random seed for reproducibility
        
        Returns:
            OptimizationResult with best parameters and trial data
        """
        logger.info(f"Starting optimization: method={method}, trials={n_trials}")
        
        if method == 'grid':
            return self._grid_search()
        elif method == 'random':
            return self._random_search(n_trials, random_seed)
        elif method == 'optuna':
            return self._optuna_search(n_trials, random_seed)
        else:
            raise ValueError(f"Unknown optimization method: {method}")
    
    def _grid_search(self) -> OptimizationResult:
        """
        Exhaustive grid search over parameter space.
        
        Warning: Can be very slow for large parameter spaces.
        """
        logger.info("Running grid search...")
        
        # Generate all parameter combinations
        param_combinations = self._generate_grid()
        
        logger.info(f"Testing {len(param_combinations)} parameter combinations")
        
        # Evaluate each combination
        for i, params in enumerate(param_combinations):
            score, metrics = self._evaluate_params(params)
            
            self.trials_data.append({
                'trial': i,
                'params': params,
                'score': score,
                'metrics': metrics
            })
            
            if (i + 1) % 10 == 0:
                logger.info(f"Completed {i + 1}/{len(param_combinations)} trials")
        
        return self._compile_results()
    
    def _random_search(self, n_trials: int, seed: int) -> OptimizationResult:
        """Random sampling of parameter space."""
        logger.info(f"Running random search with {n_trials} trials...")
        
        np.random.seed(seed)
        
        for i in range(n_trials):
            params = self._sample_params()
            score, metrics = self._evaluate_params(params)
            
            self.trials_data.append({
                'trial': i,
                'params': params,
                'score': score,
                'metrics': metrics
            })
            
            if (i + 1) % 10 == 0:
                logger.info(f"Completed {i + 1}/{n_trials} trials, best score: {max(t['score'] for t in self.trials_data):.4f}")
        
        return self._compile_results()
    
    def _optuna_search(self, n_trials: int, seed: int) -> OptimizationResult:
        """Bayesian optimization using Optuna."""
        logger.info(f"Running Optuna optimization with {n_trials} trials...")
        
        # Create Optuna study
        study = optuna.create_study(
            direction='maximize',
            sampler=optuna.samplers.TPESampler(seed=seed),
            storage=settings.optuna_storage,
            study_name=f"smc_optimization_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            load_if_exists=False
        )
        
        # Define objective function
        def objective(trial: optuna.Trial) -> float:
            params = {}
            
            for param_name, param_config in self.param_space.items():
                if param_config['type'] == 'int':
                    params[param_name] = trial.suggest_int(
                        param_name,
                        param_config['low'],
                        param_config['high']
                    )
                elif param_config['type'] == 'float':
                    params[param_name] = trial.suggest_float(
                        param_name,
                        param_config['low'],
                        param_config['high']
                    )
                elif param_config['type'] == 'categorical':
                    params[param_name] = trial.suggest_categorical(
                        param_name,
                        param_config['choices']
                    )
            
            score, metrics = self._evaluate_params(params)
            
            # Check constraints
            if not self._check_constraints(metrics):
                return -1e10  # Penalize constraint violations
            
            self.trials_data.append({
                'trial': trial.number,
                'params': params,
                'score': score,
                'metrics': metrics
            })
            
            return score
        
        # Run optimization
        study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
        
        logger.info(f"Optimization complete. Best score: {study.best_value:.4f}")
        
        result = self._compile_results()
        result.study = study
        
        return result
    
    def _evaluate_params(self, params: Dict[str, Any]) -> tuple:
        """
        Evaluate a parameter set by running backtest.
        
        Args:
            params: Strategy parameters
        
        Returns:
            Tuple of (score, metrics_dict)
        """
        try:
            # Create strategy instance
            strategy = self.strategy_class(params)
            
            # Run backtest
            backtester = Backtester(
                strategy=strategy,
                initial_balance=self.initial_balance
            )
            
            result = backtester.run(self.ohlc)
            metrics = result['metrics']
            
            # Calculate objective score
            if self.objective == 'sharpe':
                score = metrics.sharpe_ratio
            elif self.objective == 'net_profit':
                score = metrics.net_profit
            elif self.objective == 'calmar':
                score = metrics.calmar_ratio
            elif self.objective == 'profit_factor':
                score = metrics.profit_factor
            else:
                score = metrics.sharpe_ratio
            
            # Check constraints
            if not self._check_constraints(metrics):
                score = -1e10
            
            return score, metrics.to_dict()
        
        except Exception as e:
            logger.error(f"Error evaluating params: {e}")
            return -1e10, {}
    
    def _check_constraints(self, metrics) -> bool:
        """Check if metrics satisfy constraints."""
        for constraint_name, constraint_value in self.constraints.items():
            if hasattr(metrics, constraint_name):
                metric_value = getattr(metrics, constraint_name)
                
                # Assume constraint is maximum value
                if abs(metric_value) > abs(constraint_value):
                    return False
        
        return True
    
    def _generate_grid(self) -> List[Dict[str, Any]]:
        """Generate all parameter combinations for grid search."""
        import itertools
        
        param_names = []
        param_values = []
        
        for name, config in self.param_space.items():
            param_names.append(name)
            
            if config['type'] == 'int':
                values = list(range(config['low'], config['high'] + 1))
            elif config['type'] == 'float':
                # Sample 5 points in range
                values = np.linspace(config['low'], config['high'], 5).tolist()
            elif config['type'] == 'categorical':
                values = config['choices']
            
            param_values.append(values)
        
        # Generate all combinations
        combinations = list(itertools.product(*param_values))
        
        return [dict(zip(param_names, combo)) for combo in combinations]
    
    def _sample_params(self) -> Dict[str, Any]:
        """Sample random parameters from space."""
        params = {}
        
        for name, config in self.param_space.items():
            if config['type'] == 'int':
                params[name] = np.random.randint(config['low'], config['high'] + 1)
            elif config['type'] == 'float':
                params[name] = np.random.uniform(config['low'], config['high'])
            elif config['type'] == 'categorical':
                params[name] = np.random.choice(config['choices'])
        
        return params
    
    def _compile_results(self) -> OptimizationResult:
        """Compile optimization results."""
        if not self.trials_data:
            raise ValueError("No trials data available")
        
        # Convert to DataFrame
        trials_df = pd.DataFrame(self.trials_data)
        
        # Sort by score
        trials_df = trials_df.sort_values('score', ascending=False)
        
        # Get best parameters
        best_trial = trials_df.iloc[0]
        best_params = best_trial['params']
        best_score = best_trial['score']
        
        # Get top N parameter sets
        top_n = min(10, len(trials_df))
        top_n_params = trials_df.head(top_n)['params'].tolist()
        
        logger.info(f"Best parameters: {best_params}")
        logger.info(f"Best score: {best_score:.4f}")
        
        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            all_trials=trials_df,
            top_n_params=top_n_params
        )
