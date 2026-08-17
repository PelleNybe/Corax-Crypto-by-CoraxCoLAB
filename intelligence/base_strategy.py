import json
import os
from abc import ABC, abstractmethod
import polars as pl
from typing import Dict, Any
from loguru import logger


class CoraxStrategy(ABC):
    """
    Abstract Base Class for all Corax Crypto strategies.
    Strategies process Polars LazyFrames and return entry/exit conditions.
    """

    def __init__(self, name: str, params: Dict[str, Any] = None):
        self.name = name
        self.params = params or {}

    def load_optimized_parameters(
        self, config_path: str = "config/optimized_params.json"
    ) -> None:
        """
        Dynamically loads optimized parameters from a JSON file.
        Updates the internal `params` dictionary if successful.
        """
        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    all_params = json.load(f)

                # Look for parameters specific to this strategy by name
                if self.name in all_params:
                    strategy_params = all_params[self.name]
                    self.params.update(strategy_params)
                    logger.info(
                        f"Loaded optimized parameters for strategy '{self.name}': {strategy_params}"
                    )
                else:
                    logger.warning(
                        f"No specific parameters found for strategy '{self.name}' in {config_path}"
                    )
            else:
                logger.warning(
                    f"Parameter file {config_path} not found. Using default parameters."
                )
        except Exception as e:
            logger.error(f"Failed to load optimized parameters: {e}")

    @abstractmethod
    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Calculates and adds all necessary indicators to the DataFrame.
        Must return the modified LazyFrame.
        """
        raise NotImplementedError

    @abstractmethod
    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Evaluates conditions and populates 'buy' and 'sell' boolean signal columns.
        Must return the modified LazyFrame.
        """
        raise NotImplementedError
