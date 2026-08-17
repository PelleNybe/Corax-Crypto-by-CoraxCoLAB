import asyncio
import os
import ccxt.async_support as ccxt
import polars as pl
from loguru import logger
from datetime import datetime


class HistoricalDataDownloader:
    """
    Asynchronous historical data downloader for building the Polars Data Lake.
    Fetches OHLCV data from exchanges and strictly saves to Partitioned Parquet format.
    """

    def __init__(self, exchange_id: str = "binance"):
        self.exchange_id = exchange_id
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class({"enableRateLimit": True})
        except AttributeError:
            raise ValueError(f"Exchange {self.exchange_id} is not supported by CCXT.")

        self.data_dir = "data/historical"
        os.makedirs(self.data_dir, exist_ok=True)

        self.schema = {
            "timestamp": pl.Int64,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "symbol": pl.String,
        }

    async def download_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since_iso: str = None,
        limit: int = 1000,
    ):
        """
        Downloads historical OHLCV data for a symbol and timeframe.
        Saves directly to a Parquet file named by symbol and timeframe.
        """
        logger.info(
            f"Initiating historical download for {symbol} ({timeframe}) on {self.exchange_id}"
        )

        since_ms = None
        if since_iso:
            try:
                dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
                since_ms = int(dt.timestamp() * 1000)
            except ValueError:
                logger.error(
                    "Invalid since_iso format. Use ISO-8601 e.g., '2023-01-01T00:00:00Z'"
                )
                return

        all_ohlcv = []

        try:
            while True:
                logger.debug(
                    f"Fetching {symbol} from {since_ms if since_ms else 'beginning'}..."
                )
                ohlcv = await self.exchange.fetch_ohlcv(
                    symbol, timeframe, since=since_ms, limit=limit
                )

                if not ohlcv:
                    break

                # Filter out incomplete candles (latest)
                # Ensure we only append new data
                if all_ohlcv and ohlcv[0][0] <= all_ohlcv[-1][0]:
                    ohlcv = [row for row in ohlcv if row[0] > all_ohlcv[-1][0]]

                if not ohlcv:
                    break

                all_ohlcv.extend(ohlcv)

                # Update since_ms for next pagination
                since_ms = ohlcv[-1][0] + 1

                # Optional: break early if we just want one chunk for testing
                if (
                    limit and len(all_ohlcv) >= limit * 5
                ):  # Just a safeguard for infinite loops
                    break

                await asyncio.sleep(self.exchange.rateLimit / 1000)

        except Exception as e:
            logger.error(f"Error fetching data: {e}")
        finally:
            await self.exchange.close()

        if not all_ohlcv:
            logger.warning(f"No data fetched for {symbol}.")
            return

        logger.info(
            f"Fetched {len(all_ohlcv)} rows. Converting to Polars LazyFrame and saving to Parquet."
        )

        # Structure the data directly using Polars for high performance
        df = (
            pl.DataFrame(
                all_ohlcv,
                schema=["timestamp", "open", "high", "low", "close", "volume"],
                orient="row",
            )
            .with_columns(pl.lit(symbol).alias("symbol"))
            .cast(self.schema)
        )

        # Save partitioned by symbol and timeframe
        safe_symbol = symbol.replace("/", "_")
        file_path = os.path.join(self.data_dir, f"{safe_symbol}_{timeframe}.parquet")

        try:
            df.write_parquet(file_path)
            logger.success(f"Successfully saved {df.height} rows to {file_path}")
        except Exception as e:
            logger.error(f"Failed to write Parquet: {e}")


if __name__ == "__main__":
    # Example usage
    downloader = HistoricalDataDownloader(exchange_id="binance")
    asyncio.run(
        downloader.download_ohlcv("BTC/USDT", "1h", "2023-01-01T00:00:00Z", limit=500)
    )
