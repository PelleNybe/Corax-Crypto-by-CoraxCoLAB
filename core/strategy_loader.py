import importlib.util
import inspect
import os
import sys
from loguru import logger
from core.strategy import BaseStrategy
from core.config import settings


def load_strategy() -> BaseStrategy:
    """
    Dynamically loads the active strategy class based on ACTIVE_STRATEGY setting.
    It looks inside the 'strategies/' directory for matching class names.
    """
    strategy_name = settings.ACTIVE_STRATEGY
    logger.info(f"Loading dynamic strategy: {strategy_name}...")

    strategies_dir = os.path.join(os.getcwd(), "strategies")

    if not os.path.exists(strategies_dir):
        logger.warning(
            f"Strategies directory '{strategies_dir}' not found. Creating it."
        )
        os.makedirs(strategies_dir)
        raise ValueError(
            f"Strategies directory was missing. Please add your strategy files to {strategies_dir}"
        )

    # Iterate through all .py files in the strategies directory
    for filename in os.listdir(strategies_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            filepath = os.path.join(strategies_dir, filename)
            module_name = filename[:-3]

            try:
                # Use importlib.util for robust dynamic loading from absolute paths
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Find classes in the module that subclass BaseStrategy
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                        # Case-insensitive match or exact match depending on preference. Let's do exact match first.
                        if (
                            name.lower() == strategy_name.lower()
                            or name == strategy_name
                        ):
                            logger.success(
                                f"Successfully loaded strategy class '{name}' from '{filename}'"
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
