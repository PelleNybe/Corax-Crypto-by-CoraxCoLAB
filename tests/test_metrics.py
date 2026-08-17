import polars as pl
import numpy as np
from intelligence.metrics import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_loss_ratio,
)


def test_calculate_sharpe_ratio_empty():
    returns = pl.Series([])
    assert calculate_sharpe_ratio(returns) == 0.0


def test_calculate_sharpe_ratio_zero_std():
    returns = pl.Series([0.01, 0.01, 0.01])
    assert calculate_sharpe_ratio(returns) == 0.0


def test_calculate_sharpe_ratio_normal():
    returns = pl.Series([0.01, 0.02, -0.01, 0.03, -0.02])
    # mean = 0.006, std = 0.02073644135332772
    # factor = sqrt(365) = 19.1049731745428
    # sharpe = (0.006 - 0) / 0.02073644135332772 * 19.1049731745428 = 5.527864045
    result = calculate_sharpe_ratio(returns)
    assert isinstance(result, float)
    assert result > 0.0


def test_calculate_sharpe_ratio_with_risk_free_rate():
    returns = pl.Series([0.01, 0.02, -0.01, 0.03, -0.02])
    result_no_rfr = calculate_sharpe_ratio(returns, risk_free_rate=0.0)
    result_with_rfr = calculate_sharpe_ratio(returns, risk_free_rate=0.01)
    assert result_with_rfr < result_no_rfr


def test_calculate_max_drawdown_empty():
    equity_curve = pl.Series([])
    assert calculate_max_drawdown(equity_curve) == 0.0


def test_calculate_max_drawdown_no_drawdown():
    equity_curve = pl.Series([100.0, 105.0, 110.0, 120.0])
    assert calculate_max_drawdown(equity_curve) == 0.0


def test_calculate_max_drawdown_with_drawdown():
    # Peak is 120, trough is 90
    # Drawdown = (90 - 120) / 120 = -30 / 120 = -0.25 -> abs = 0.25
    equity_curve = pl.Series([100.0, 120.0, 110.0, 90.0, 105.0])
    result = calculate_max_drawdown(equity_curve)
    assert np.isclose(result, 0.25)


def test_calculate_win_loss_ratio_empty():
    returns = pl.Series([])
    assert calculate_win_loss_ratio(returns) == 0.0


def test_calculate_win_loss_ratio_no_losses():
    returns = pl.Series([0.01, 0.02, 0.03])
    assert calculate_win_loss_ratio(returns) == float("inf")


def test_calculate_win_loss_ratio_no_wins():
    returns = pl.Series([-0.01, -0.02, -0.03])
    assert calculate_win_loss_ratio(returns) == 0.0


def test_calculate_win_loss_ratio_mixed():
    returns = pl.Series([0.01, -0.01, 0.02, -0.02, 0.03])
    # 3 wins, 2 losses -> ratio = 1.5
    assert calculate_win_loss_ratio(returns) == 1.5
