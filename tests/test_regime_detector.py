import pytest
import polars as pl
from intelligence.regime_detector import RegimeDetector
from intelligence.backends import BaseInferenceBackend


class MockBackend(BaseInferenceBackend):
    async def fast_inference(self, data: pl.DataFrame) -> dict:
        return {"action": "hold", "confidence": 0.5}

    async def get_macro_context(self) -> str:
        return "mock context"


@pytest.fixture
def detector():
    return RegimeDetector(MockBackend())


def test_predict_next_regime_basic(detector):
    # Set up clear probabilities: RANGING -> TRENDING_UP is most likely
    detector.transition_counts[("RANGING", "TRENDING_UP")] = 10
    detector.transition_counts[("RANGING", "TRENDING_DOWN")] = 2
    detector.transition_counts[("RANGING", "RANGING")] = 5
    detector.transition_counts[("RANGING", "VOLATILE_CRASH")] = 1

    predicted = detector._predict_next_regime("RANGING")
    assert predicted == "TRENDING_UP"


def test_predict_next_regime_equal_probabilities(detector):
    # Laplace smoothing means all are 1 initially
    # If all are equal, max() will return the first one it encounters (implementation dependent)
    # But let's test that it returns one of the valid regimes
    predicted = detector._predict_next_regime("TRENDING_UP")
    assert predicted in detector.regimes


def test_predict_next_regime_another_scenario(detector):
    # Set up: VOLATILE_CRASH -> RANGING is most likely
    detector.transition_counts[("VOLATILE_CRASH", "TRENDING_UP")] = 1
    detector.transition_counts[("VOLATILE_CRASH", "TRENDING_DOWN")] = 1
    detector.transition_counts[("VOLATILE_CRASH", "RANGING")] = 20
    detector.transition_counts[("VOLATILE_CRASH", "VOLATILE_CRASH")] = 2

    predicted = detector._predict_next_regime("VOLATILE_CRASH")
    assert predicted == "RANGING"


@pytest.mark.asyncio
async def test_detect_regime_updates_transitions(detector):
    # Test that detect_regime correctly updates the transition matrix
    df_ranging = pl.LazyFrame({"price": [10.0, 10.1], "volume": [1.0, 1.0]})
    df_trending = pl.LazyFrame(
        {"price": [10.0, 30.0], "volume": [1.0, 1.0]}
    )  # price diff > 10

    # Initial state
    assert detector.last_regime is None
    initial_count = detector.transition_counts[("RANGING", "TRENDING_UP")]

    # First detection (sets last_regime)
    regime1 = await detector.detect_regime(df_ranging)
    assert regime1 == "RANGING"
    assert detector.last_regime == "RANGING"

    # Second detection (should update RANGING -> TRENDING_UP)
    regime2 = await detector.detect_regime(df_trending)
    assert regime2 == "TRENDING_UP"
    assert detector.last_regime == "TRENDING_UP"

    # Check that transition count increased by 1
    assert detector.transition_counts[("RANGING", "TRENDING_UP")] == initial_count + 1
