import json
import polars as pl
from loguru import logger


class VisualStrategyCompiler:
    """
    Compiles JSON exported from the UI's Visual Node Builder (LiteGraph.js)
    into a Polars-native LazyFrame execution plan.
    """

    def __init__(self, json_payload: str):
        self.payload = json.loads(json_payload)
        self.nodes = self.payload.get("nodes", [])
        self.links = self.payload.get("links", [])

    def compile(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """
        Takes a base LazyFrame (e.g. OHLCV data) and chains Polars operations
        based on the visual nodes.
        """
        logger.info(f"Compiling visual strategy with {len(self.nodes)} nodes.")

        # In a complete AST parser, we would walk the graph via links.
        # For this implementation, we process sequentially based on type to demonstrate
        # the conversion from Node -> Polars Operation.

        compiled_lf = lf

        for node in self.nodes:
            node_type = node.get("type", "")
            params = node.get("params", {})

            if node_type == "Indicator/RSI":
                period = params.get("period", 14)
                # Mock Polars RSI implementation (requires external library or custom rolling logic in Polars)
                # We use a simple diff/rolling mean proxy for demonstration of the AST compilation:
                compiled_lf = compiled_lf.with_columns(
                    [
                        (pl.col("close").diff().rolling_mean(window_size=period)).alias(
                            "mock_rsi"
                        )
                    ]
                )
                logger.debug(f"Compiled Node: RSI (period={period})")

            elif node_type == "Condition/GreaterThan":
                val = params.get("value", 70)
                compiled_lf = compiled_lf.with_columns(
                    [(pl.col("mock_rsi") > val).alias("signal_active")]
                )
                logger.debug(f"Compiled Node: GreaterThan (val={val})")

            elif node_type == "Action/Sell":
                # Maps the condition to a string output if true
                compiled_lf = compiled_lf.with_columns(
                    [
                        pl.when(pl.col("signal_active"))
                        .then(pl.lit("SELL"))
                        .otherwise(pl.lit("HOLD"))
                        .alias("visual_action")
                    ]
                )
                logger.debug("Compiled Node: Action SELL")

        logger.success("Strategy compiled successfully to Polars LazyFrame.")
        return compiled_lf
