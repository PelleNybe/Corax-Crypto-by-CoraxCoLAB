import json
import os
import time
import random
import asyncio
from typing import Dict, Any, List, Tuple, Type
import polars as pl
from loguru import logger

from core.strategy import BaseStrategy
from intelligence.metrics import calculate_sharpe_ratio, calculate_max_drawdown


class CoraxOptimizer:
    """
    High-Speed Genetic Hyper-Optimization Engine.
    Leverages Polars for rapid vectorized evaluation of strategy parameters over historical data.
    """

    def __init__(
        self,
        population_size: int = 20,
        generations: int = 10,
        mutation_rate: float = 0.1,
        elite_size: int = 2,
    ):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elite_size = elite_size

        # Ensure config directory exists
        os.makedirs("config", exist_ok=True)

    def _generate_initial_population(
        self, param_space: Dict[str, Tuple[float, float, str]]
    ) -> List[Dict[str, Any]]:
        """
        Generates an initial population of random parameter sets within defined bounds.
        param_space format: {'param_name': (min_val, max_val, 'type')}
        where 'type' can be 'float' or 'int'.
        """
        population = []
        for _ in range(self.population_size):
            individual = {}
            for param, (min_val, max_val, p_type) in param_space.items():
                if p_type == "int":
                    individual[param] = random.randint(int(min_val), int(max_val))
                else:
                    individual[param] = random.uniform(min_val, max_val)
            population.append(individual)
        return population

    def _mutate(
        self,
        individual: Dict[str, Any],
        param_space: Dict[str, Tuple[float, float, str]],
    ) -> Dict[str, Any]:
        """Mutates an individual's parameters based on the mutation rate."""
        mutated = individual.copy()
        for param, (min_val, max_val, p_type) in param_space.items():
            if random.random() < self.mutation_rate:
                if p_type == "int":
                    mutated[param] = random.randint(int(min_val), int(max_val))
                else:
                    mutated[param] = random.uniform(min_val, max_val)
        return mutated

    def _crossover(
        self, parent1: Dict[str, Any], parent2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Creates a child by randomly combining parameters from two parents."""
        child = {}
        for param in parent1.keys():
            if random.random() < 0.5:
                child[param] = parent1[param]
            else:
                child[param] = parent2[param]
        return child

    async def _evaluate_fitness(
        self, strategy_class: Type[BaseStrategy], params: Dict[str, Any], data_path: str
    ) -> float:
        """
        Evaluates the fitness of a parameter set by running a rapid vectorized backtest.
        Fitness function prioritizes Sharpe Ratio and penalizes Drawdown.
        """
        strategy = strategy_class()
        # Inject parameters into the strategy instance dynamically
        for key, value in params.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)

        try:
            lazy_df = pl.scan_parquet(data_path)

            # Apply strategy logic directly (Vectorized!)
            df_with_indicators = strategy.populate_indicators(lazy_df)
            df_with_signals = strategy.populate_signals(df_with_indicators)

            # Execute on signals vectorially to calculate returns
            df = await asyncio.to_thread(df_with_signals.collect)

            if (
                "buy" not in df.columns
                or "sell" not in df.columns
                or "price" not in df.columns
            ):
                return -9999.0

            # Pure Polars vectorized backtest PnL logic
            df = df.with_columns(
                [
                    pl.col("buy").cast(pl.Int8).alias("signal_buy"),
                    pl.col("sell").cast(pl.Int8).alias("signal_sell"),
                ]
            )

            # Create a combined signal: 1 for buy, -1 for sell, 0 otherwise
            df = df.with_columns(
                pl.when(pl.col("signal_buy") == 1)
                .then(1)
                .when(pl.col("signal_sell") == 1)
                .then(-1)
                .otherwise(0)
                .alias("raw_signal")
            )

            # We only change state when we get a buy or sell signal
            # Use forward fill to maintain the last active position (1 or 0)
            df = df.with_columns(
                pl.col("raw_signal")
                .replace(0, None)
                .forward_fill()
                .fill_null(0)
                .alias("position")
            )

            # Position is only long (1) or flat (0). We don't short here.
            df = df.with_columns(
                pl.when(pl.col("position") == -1)
                .then(0)
                .otherwise(pl.col("position"))
                .alias("position")
            )

            # Calculate returns based on position
            df = df.with_columns(
                (pl.col("price").pct_change() * pl.col("position").shift(1))
                .fill_null(0)
                .alias("strategy_return")
            )

            returns = df["strategy_return"]

            if len(returns) == 0 or (returns == 0).all():
                return -100.0  # No trades

            equity_curve = (1 + returns).cum_prod() * 10000.0

            sharpe = calculate_sharpe_ratio(returns)
            max_dd = calculate_max_drawdown(equity_curve)

            # Fitness function: High Sharpe, Low Drawdown
            fitness = sharpe - (max_dd * 2.0)

            # Penalize if it never trades or trades too rarely
            trades_count = df.filter(pl.col("raw_signal") != 0).height
            if trades_count < 5:
                fitness -= 100.0

            return float(fitness)

        except Exception as e:
            logger.error(f"Error during fitness evaluation: {e}")
            return -9999.0

    async def optimize(
        self,
        strategy_class: Type[BaseStrategy],
        param_space: Dict[str, Tuple[float, float, str]],
        data_path: str,
        save_path: str = "config/optimized_params.json",
    ):
        """
        Runs the Genetic Algorithm to find optimal parameters.
        """
        logger.info(f"Starting Hyper-Optimization for {strategy_class.__name__}...")
        start_time = time.time()

        population = self._generate_initial_population(param_space)
        best_individual = None
        best_fitness = -float("inf")

        for generation in range(self.generations):
            logger.info(f"Generation {generation + 1}/{self.generations}")

            # Evaluate fitness for all individuals (can be parallelized)
            tasks = [
                self._evaluate_fitness(strategy_class, individual, data_path)
                for individual in population
            ]
            results = await asyncio.gather(*tasks)
            fitness_scores = list(zip(population, results))

            # Sort by fitness descending
            fitness_scores.sort(key=lambda x: x[1], reverse=True)

            # Track overall best
            current_best, current_best_fitness = fitness_scores[0]
            if current_best_fitness > best_fitness:
                best_fitness = current_best_fitness
                best_individual = current_best.copy()
                logger.info(
                    f"  New Best Fitness: {best_fitness:.4f} | Params: {best_individual}"
                )

            # Next generation selection (Elitism)
            next_population = [ind for ind, _ in fitness_scores[: self.elite_size]]

            # Fill the rest of the population
            while len(next_population) < self.population_size:
                # Tournament selection
                tournament = random.sample(fitness_scores, 3)
                parent1 = max(tournament, key=lambda x: x[1])[0]

                tournament = random.sample(fitness_scores, 3)
                parent2 = max(tournament, key=lambda x: x[1])[0]

                # Crossover & Mutate
                child = self._crossover(parent1, parent2)
                child = self._mutate(child, param_space)
                next_population.append(child)

            population = next_population

        logger.info(f"Optimization Complete in {time.time() - start_time:.2f}s")
        logger.info(f"Optimal Parameters: {best_individual}")
        logger.info(f"Best Fitness Score: {best_fitness:.4f}")

        # Save results
        self._save_optimized_parameters(
            strategy_class.__name__, best_individual, save_path
        )

        return best_individual

    def _save_optimized_parameters(
        self, strategy_name: str, params: Dict[str, Any], path: str
    ):
        """Saves the best parameters to the JSON config file."""
        try:
            data = {}
            if os.path.exists(path):
                with open(path, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}

            data[strategy_name] = params

            with open(path, "w") as f:
                json.dump(data, f, indent=4)

            logger.info(f"Saved optimized parameters to {path}")
        except Exception as e:
            logger.error(f"Failed to save parameters: {e}")
