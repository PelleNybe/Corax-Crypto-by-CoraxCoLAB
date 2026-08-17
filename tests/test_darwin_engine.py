import pytest
from intelligence.darwin_engine import DarwinEngine


@pytest.mark.asyncio
async def test_darwin_engine_initialization():
    engine = DarwinEngine(population_size=10)
    param_space = {"sma_fast": (10, 20), "sma_slow": (21, 50)}
    engine.initialize_population(param_space)

    assert len(engine.population) == 10
    for dna in engine.population:
        assert 10 <= dna.params["sma_fast"] <= 20
        assert 21 <= dna.params["sma_slow"] <= 50


@pytest.mark.asyncio
async def test_darwin_engine_evaluation():
    engine = DarwinEngine(population_size=5)
    param_space = {"x": (0, 10)}
    engine.initialize_population(param_space)

    # Dummy fitness function that rewards values closer to 7.0
    async def mock_backtest(params):
        return -abs(params["x"] - 7.0)

    await engine.evaluate_fitness(mock_backtest)

    # Since it's sorted, the first one should be the closest to 7.0 (highest fitness)
    assert engine.population[0].fitness >= engine.population[-1].fitness
    assert engine.best_dna is not None


@pytest.mark.asyncio
async def test_darwin_engine_evolution():
    engine = DarwinEngine(population_size=10, survival_rate=0.2)
    param_space = {"x": (0, 10)}
    engine.initialize_population(param_space)

    # Assign artificial fitness to ensure deterministic sorting
    for i, dna in enumerate(engine.population):
        dna.fitness = i * 10.0

    engine.population.sort(key=lambda x: x.fitness, reverse=True)
    best_initial_params = engine.population[0].params.copy()

    engine.evolve_population(param_space)

    # Population size should remain constant
    assert len(engine.population) == 10
    assert engine.generation == 1

    # The top survivors should have been carried over directly
    assert engine.population[0].params == best_initial_params
