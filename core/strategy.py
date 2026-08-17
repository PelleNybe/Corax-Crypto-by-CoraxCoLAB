from abc import ABC, abstractmethod
import polars as pl


class BaseStrategy(ABC):
    """
    Abstract Base Class for all Modular Corax Crypto strategies.
    Inspired by Freqtrade architecture, processes Polars LazyFrames.
    """

    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__

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
