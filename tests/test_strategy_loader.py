import pytest
from core.strategy_loader import load_strategy
from core.strategy import BaseStrategy


def test_load_strategy_missing_dir(mocker, tmp_path):
    # Mock Path.cwd() to return a temporary directory
    mocker.patch("core.strategy_loader.Path.cwd", return_value=tmp_path)

    # Verify that the strategies directory does not exist initially
    strategies_dir = tmp_path / "strategies"
    assert not strategies_dir.exists()

    # Call load_strategy and expect a ValueError
    with pytest.raises(ValueError, match="Strategies directory was missing"):
        load_strategy()

    # Verify that the directory was created
    assert strategies_dir.exists()
    assert strategies_dir.is_dir()


def test_load_strategy_success(mocker, tmp_path):
    # Mock settings.ACTIVE_STRATEGY
    mocker.patch("core.strategy_loader.settings.ACTIVE_STRATEGY", "TestStrategy")
    mocker.patch("core.strategy_loader.Path.cwd", return_value=tmp_path)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir(parents=True)

    # Create a mock strategy file
    strategy_file = strategies_dir / "test_strategy.py"
    strategy_file.write_text("""
from core.strategy import BaseStrategy

class TestStrategy(BaseStrategy):
    def populate_indicators(self, dataframe):
        pass

    def populate_signals(self, dataframe):
        pass
    """)

    # Mock importlib.import_module
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "strategies.test_strategy", strategy_file
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["strategies.test_strategy"] = module
    spec.loader.exec_module(module)

    mocker.patch("core.strategy_loader.importlib.import_module", return_value=module)

    strategy = load_strategy()
    assert isinstance(strategy, BaseStrategy)
    assert strategy.__class__.__name__ == "TestStrategy"


def test_load_strategy_not_found(mocker, tmp_path):
    # Mock settings.ACTIVE_STRATEGY
    mocker.patch("core.strategy_loader.settings.ACTIVE_STRATEGY", "NonExistentStrategy")
    mocker.patch("core.strategy_loader.Path.cwd", return_value=tmp_path)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir(parents=True)

    # Create a mock strategy file
    strategy_file = strategies_dir / "test_strategy.py"
    strategy_file.write_text("""
from core.strategy import BaseStrategy

class TestStrategy(BaseStrategy):
    def populate_indicators(self, dataframe):
        pass

    def populate_signals(self, dataframe):
        pass
    """)

    # Mock importlib.import_module
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "strategies.test_strategy", strategy_file
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["strategies.test_strategy"] = module
    spec.loader.exec_module(module)

    mocker.patch("core.strategy_loader.importlib.import_module", return_value=module)

    with pytest.raises(
        ValueError, match="Strategy class 'NonExistentStrategy' not found."
    ):
        load_strategy()


def test_load_strategy_import_error(mocker, tmp_path):
    # Mock settings.ACTIVE_STRATEGY
    mocker.patch("core.strategy_loader.settings.ACTIVE_STRATEGY", "TestStrategy")
    mocker.patch("core.strategy_loader.Path.cwd", return_value=tmp_path)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir(parents=True)

    # Create a mock strategy file
    strategy_file = strategies_dir / "test_strategy.py"
    strategy_file.write_text("invalid python code")

    # Mock importlib.import_module to raise an exception
    mocker.patch(
        "core.strategy_loader.importlib.import_module",
        side_effect=ImportError("Mocked import error"),
    )

    with pytest.raises(ValueError, match="Strategy class 'TestStrategy' not found."):
        load_strategy()


def test_load_strategy_ignore_dunder_files(mocker, tmp_path):
    # Mock settings.ACTIVE_STRATEGY
    mocker.patch("core.strategy_loader.settings.ACTIVE_STRATEGY", "TestStrategy")
    mocker.patch("core.strategy_loader.Path.cwd", return_value=tmp_path)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir(parents=True)

    # Create a dunder file that should be ignored
    strategy_file = strategies_dir / "__init__.py"
    strategy_file.write_text("")

    mock_import = mocker.patch("core.strategy_loader.importlib.import_module")

    with pytest.raises(ValueError, match="Strategy class 'TestStrategy' not found."):
        load_strategy()

    mock_import.assert_not_called()
