import polars as pl
import numpy as np


def calculate_sharpe_ratio(returns: pl.Series, risk_free_rate: float = 0.0) -> float:
    """Calculates the annualized Sharpe Ratio based on trade returns."""
    if len(returns) == 0:
        return 0.0
    # Assuming returns are fractional (e.g., 0.01 for 1%)
    mean_return = returns.mean()
    std_return = returns.std()

    if std_return == 0:
        return 0.0

    # Assuming average of 252 trading days per year for traditional, or 365 for crypto.
    # We'll use 365 for crypto context.
    annualized_factor = np.sqrt(365)

    sharpe = (mean_return - risk_free_rate) / std_return * annualized_factor
    return sharpe


def calculate_max_drawdown(equity_curve: pl.Series) -> float:
    """Calculates the maximum drawdown percentage from an equity curve."""
    if len(equity_curve) == 0:
        return 0.0

    # Calculate running maximum
    running_max = equity_curve.cum_max()

    # Calculate drawdown
    drawdown = (equity_curve - running_max) / running_max

    # Return max absolute drawdown (min value)
    return abs(drawdown.min())


def calculate_win_loss_ratio(returns: pl.Series) -> float:
    """Calculates the Win/Loss Ratio."""
    if len(returns) == 0:
        return 0.0

    wins = returns.filter(returns > 0).len()
    losses = returns.filter(returns <= 0).len()

    if losses == 0:
        return float("inf") if wins > 0 else 0.0

    return wins / losses
