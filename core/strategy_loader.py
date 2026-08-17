import importlib
import inspect
from pathlib import Path

from loguru import logger

from core.config import settings
from core.strategy import BaseStrategy


def load_strategy() -> BaseStrategy:
    """
    Dynamically loads the active strategy class based on ACTIVE_STRATEGY setting.
    It looks inside the 'strategies/' directory for matching class names.
    """
    strategy_name = settings.ACTIVE_STRATEGY
    logger.info(f"Loading dynamic strategy: {strategy_name}...")

    strategies_dir = Path.cwd() / "strategies"

    if not strategies_dir.exists():
        logger.warning(
            f"Strategies directory '{strategies_dir}' not found. Creating it."
        )
        strategies_dir.mkdir(parents=True, exist_ok=True)
        raise ValueError(
            f"Strategies directory was missing. Please add your strategy files to {strategies_dir}"
        )

    # Iterate through all .py files in the strategies directory
    for filepath in strategies_dir.glob("*.py"):
        if filepath.name.startswith("__"):
            continue

        module_name = filepath.stem

        try:
            module = importlib.import_module(f"strategies.{module_name}")

            # Find classes in the module that subclass BaseStrategy
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, BaseStrategy) or obj is BaseStrategy:
                    continue

                # Case-insensitive match or exact match depending on preference. Let's do exact match first.
                if name.lower() == strategy_name.lower() or name == strategy_name:
                    logger.success(
                        f"Successfully loaded strategy class '{name}' from '{filepath.name}'"
                    )
                    return obj()
        except Exception as e:
            logger.error(
                f"Failed to inspect module '{module_name}' at '{filepath}': {e}"
            )

    logger.error(
        f"Strategy '{strategy_name}' could not be found in the 'strategies/' directory."
    )
    raise ValueError(f"Strategy class '{strategy_name}' not found.")
