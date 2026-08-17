import asyncio
import random
from typing import Dict, List, Optional
from loguru import logger
from pydantic import BaseModel


class DNA(BaseModel):
    params: Dict[str, float]
    fitness: float = 0.0


class DarwinEngine:
    """
    Corax Darwin Engine: Continuous Genetic Algorithm (GA) Optimizer.
    Runs continuously in the background, evolving strategy parameters over live data.
    When a significantly better DNA strain is discovered, it supports hot-reloading
    into the active engine.
    """

    def __init__(
        self,
        population_size: int = 50,
        mutation_rate: float = 0.1,
        survival_rate: float = 0.2,
    ):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.survival_rate = survival_rate
        self.population: List[DNA] = []
        self.generation = 0
        self.best_dna: Optional[DNA] = None
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    def initialize_population(self, param_space: Dict[str, tuple]):
        """Creates the initial random generation based on param bounds."""
        self.population = []
        for _ in range(self.population_size):
            params = {}
            for k, (low, high) in param_space.items():
                params[k] = random.uniform(low, high)
            self.population.append(DNA(params=params))
        logger.info(
            f"🧬 Darwin Engine initialized with population size {self.population_size}"
        )

    async def evaluate_fitness(self, backtest_func) -> None:
        """Evaluates fitness for the entire population using an async backtest function."""
        tasks = []
        for dna in self.population:
            # We assume backtest_func takes params and returns a fitness score
            tasks.append(backtest_func(dna.params))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                self.population[idx].fitness = -9999.0
            else:
                self.population[idx].fitness = result

        # Sort by best fitness (descending)
        self.population.sort(key=lambda x: x.fitness, reverse=True)

        if not self.best_dna or self.population[0].fitness > self.best_dna.fitness:
            self.best_dna = DNA(
                params=self.population[0].params.copy(),
                fitness=self.population[0].fitness,
            )
            logger.success(
                f"🧬 Generation {self.generation}: New Apex DNA Discovered! Fitness: {self.best_dna.fitness:.4f}"
            )

    def evolve_population(self, param_space: Dict[str, tuple]):
        """Creates the next generation via selection, crossover, and mutation."""
        survivors_count = int(self.population_size * self.survival_rate)
        survivors = self.population[:survivors_count]

        next_gen = survivors.copy()

        while len(next_gen) < self.population_size:
            # Selection (Tournament)
            p1 = random.choice(survivors)
            p2 = random.choice(survivors)

            # Crossover
            child_params = {}
            for k in param_space.keys():
                child_params[k] = (
                    p1.params[k] if random.random() < 0.5 else p2.params[k]
                )

                # Mutation
                if random.random() < self.mutation_rate:
                    low, high = param_space[k]
                    # Mutate by pushing slightly towards a random bound
                    mutation_shift = random.uniform(-0.1, 0.1) * (high - low)
                    child_params[k] = max(
                        low, min(high, child_params[k] + mutation_shift)
                    )

            next_gen.append(DNA(params=child_params))

        self.population = next_gen
        self.generation += 1

    async def start_evolution_loop(self, param_space: Dict[str, tuple], backtest_func):
        """Continuously evolves populations in the background."""
        self.is_running = True
        if not self.population:
            self.initialize_population(param_space)

        logger.info("🧬 Starting continuous Darwin Evolution loop...")

        try:
            while self.is_running:
                await self.evaluate_fitness(backtest_func)
                self.evolve_population(param_space)
                # Yield to the event loop so trading isn't blocked
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("🧬 Darwin Engine loop cancelled.")

    def stop(self):
        self.is_running = False
