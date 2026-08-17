import json
import os
import polars as pl
from loguru import logger
from core.strategy import BaseStrategy
from core.config import settings


class VisualStrategy(BaseStrategy):
    """
    Dynamically compiles a JSON Node Graph (from the UI) into Polars expressions.
    """

    def __init__(self, name="VisualStrategy"):
        super().__init__(name)
        self.graph = None
        self._load_graph()

    def _load_graph(self):
        path = settings.VISUAL_STRATEGY_PATH
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    self.graph = json.load(f)
                logger.info("Visual Strategy Graph loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load visual strategy graph: {e}")
                self.graph = None
        else:
            logger.warning(
                f"Visual strategy graph not found at {path}. Operating as HOLD."
            )

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        if not self.graph:
            return df

        columns_to_add = []

        # Parse indicator nodes
        for node in self.graph.get("nodes", []):
            node_type = node.get("type")
            node_id = str(node.get("id"))

            if node_type == "math/sma":
                # Find the period from properties
                period = node.get("properties", {}).get("period", 14)
                # Ensure price exists, default to 'price' for this simple implementation
                # The output name matches the node ID so other nodes can reference it
                col_expr = (
                    pl.col("price")
                    .rolling_mean(window_size=period)
                    .alias(f"node_{node_id}")
                )
                columns_to_add.append(col_expr)

            # A full implementation would map RSI, MACD, etc. to Polars calculations

        if columns_to_add:
            df = df.with_columns(columns_to_add)

        return df

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        if not self.graph:
            df = df.with_columns(
                [pl.lit(False).alias("buy"), pl.lit(False).alias("sell")]
            )
            return df

        # We compile the graph to find the output node
        # For this prototype, we'll look for a 'logic/compare' node linked to 'output/buy'
        buy_expr = pl.lit(False)
        sell_expr = pl.lit(False)

        # Simplified interpreter just to prove parity
        for node in self.graph.get("nodes", []):
            if node.get("type") == "logic/compare":
                props = node.get("properties", {})
                op = props.get("op", ">")
                val1 = props.get("val1", "price")  # or node_x
                val2 = props.get("val2", 0)  # or node_y

                # Resolve val1
                expr1 = pl.col(val1) if isinstance(val1, str) else pl.lit(val1)
                expr2 = pl.col(val2) if isinstance(val2, str) else pl.lit(val2)

                if op == ">":
                    cond = expr1 > expr2
                elif op == "<":
                    cond = expr1 < expr2
                else:
                    cond = pl.lit(False)

                # Cross condition (shift 1)
                if op == ">":
                    cross_cond = cond & (expr1.shift(1) <= expr2.shift(1))
                else:
                    cross_cond = cond & (expr1.shift(1) >= expr2.shift(1))

                # Check links
                links = self.graph.get("links", [])
                node_id = node.get("id")

                # Which output is this connected to?
                for link in links:
                    if link[1] == node_id:  # Connected from this node
                        target_id = link[3]
                        # Find target node
                        target_node = next(
                            (n for n in self.graph["nodes"] if n["id"] == target_id),
                            None,
                        )
                        if target_node and target_node.get("type") == "output/signal":
                            if (
                                target_node.get("properties", {}).get("signal_type")
                                == "buy"
                            ):
                                buy_expr = cross_cond.fill_null(False)
                            else:
                                sell_expr = cross_cond.fill_null(False)

        df = df.with_columns([buy_expr.alias("buy"), sell_expr.alias("sell")])

        return df
