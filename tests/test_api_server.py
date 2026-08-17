import os

os.environ["EXCHANGE_API_KEY"] = "test"
os.environ["EXCHANGE_API_SECRET"] = "test"
os.environ["LLM_API_KEY"] = "test"
os.environ["CORAX_MODE"] = "testnet"

import pytest
from fastapi import Request, Response
from starlette.websockets import WebSocketDisconnect


@pytest.mark.asyncio
async def test_csp_header_middleware():
    from core.api_server import add_csp_header

    scope = {"type": "http", "method": "GET", "path": "/api/v1/health", "headers": []}
    request = Request(scope)

    async def mock_call_next(req):
        return Response(content="test")

    response = await add_csp_header(request, mock_call_next)

    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]

    assert "unsafe-eval" not in csp
    assert "unsafe-inline" not in csp

    assert "strict-dynamic" in csp
    assert "nonce-" in csp
    assert "default-src 'self'" in csp


@pytest.mark.asyncio
async def test_update_settings_vulnerability():
    from core.api_server import update_settings
    from core.config import settings

    # We'll use a built-in key that shouldn't be updated by settings
    original_env = settings.CORAX_ENV

    class MockRequest:
        async def json(self):
            return {
                "MAX_RISK_PER_TRADE_PCT": 0.05,
                "CORAX_ENV": "should_not_update",
                "ACTIVE_STRATEGY": "NewStrategy",
            }

    request = MockRequest()
    await update_settings(request)

    # Allowed keys should be updated
    assert settings.MAX_RISK_PER_TRADE_PCT == 0.05
    assert settings.ACTIVE_STRATEGY == "NewStrategy"

    # Unallowed keys should NOT be updated
    assert settings.CORAX_ENV == original_env


@pytest.mark.asyncio
async def test_auth_middleware():
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    client = TestClient(app)

    # Test an endpoint without the API key
    delattr(app.state, "engine") if hasattr(app.state, "engine") else None
    response = client.post("/api/v1/engine/control", json={"action": "pause"})
    assert response.status_code == 403

    # Test GET without API key
    response = client.get("/api/v1/health")
    assert response.status_code == 403

    response = client.get("/api/v1/settings")
    assert response.status_code == 403

    # Test with correct API key
    # (assuming engine is not initialized in the test environment, we should get 503 instead of 403)
    delattr(app.state, "engine") if hasattr(app.state, "engine") else None
    response = client.post(
        "/api/v1/engine/control",
        json={"action": "pause"},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert (
        response.status_code == 503
    )  # Or 422 if payload is wrong, or 200, but NOT 403


@pytest.mark.asyncio
async def test_websocket_auth():
    from fastapi.testclient import TestClient
    from core.api_server import app

    client = TestClient(app)

    # Test without auth
    try:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json({"action": "auth", "api_key": None})
            websocket.receive_json()
            assert False, "Should have been disconnected"
    except WebSocketDisconnect as e:
        assert e.code == 1008

    # Test with wrong auth
    try:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json({"action": "auth", "api_key": "wrong_key"})
            websocket.receive_json()
            assert False, "Should have been disconnected"
    except WebSocketDisconnect as e:
        assert e.code == 1008


@pytest.mark.asyncio
async def test_place_trade_success(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings
    import asyncio

    # Setup mock OrderManager
    class MockOrderManager:
        def __init__(self):
            self.order_queue = asyncio.Queue()

    mock_order_manager = MockOrderManager()

    # We must patch put to be an AsyncMock to easily inspect it if we wanted,
    # but we can also just use the real asyncio.Queue and check its contents
    mocker.patch.object(
        mock_order_manager.order_queue, "put", new_callable=mocker.AsyncMock
    )

    app.state.order_manager = mock_order_manager
    client = TestClient(app)

    payload = {
        "symbol": "BTC/USDT",
        "side": "buy",
        "amount": 0.1,
        "order_type": "limit",
        "price": 50000.0,
    }

    response = client.post(
        "/api/trade/place",
        json=payload,
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify the message was placed in the queue
    mock_order_manager.order_queue.put.assert_called_once_with(
        (
            "CREATE",
            {
                "symbol": "BTC/USDT",
                "type": "limit",
                "side": "buy",
                "amount": 0.1,
                "price": 50000.0,
            },
        )
    )


@pytest.mark.asyncio
async def test_place_trade_no_order_manager():
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    # Ensure order_manager is not initialized
    delattr(app.state, "order_manager") if hasattr(app.state, "order_manager") else None
    client = TestClient(app)

    payload = {
        "symbol": "BTC/USDT",
        "side": "buy",
        "amount": 0.1,
        "order_type": "market",
    }

    response = client.post(
        "/api/trade/place",
        json=payload,
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 503
    assert "OrderManager not initialized" in response.json()["detail"]


@pytest.mark.asyncio
async def test_place_trade_exception(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings
    import asyncio

    # Setup mock OrderManager
    class MockOrderManager:
        def __init__(self):
            self.order_queue = asyncio.Queue()

    mock_order_manager = MockOrderManager()

    # Patch put to raise an exception
    mocker.patch.object(
        mock_order_manager.order_queue, "put", side_effect=Exception("Test Exception")
    )

    app.state.order_manager = mock_order_manager
    client = TestClient(app)

    payload = {
        "symbol": "BTC/USDT",
        "side": "buy",
        "amount": 0.1,
        "order_type": "limit",
        "price": 50000.0,
    }

    response = client.post(
        "/api/trade/place",
        json=payload,
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 500
    assert "Test Exception" in response.json()["detail"]


@pytest.mark.asyncio
async def test_health_check_healthy(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings
    import asyncio

    class MockRiskManager:
        def __init__(self):
            self.kill_switch_active = False

    class MockEngine:
        def __init__(self):
            self.is_paused = False
            self.risk_manager = MockRiskManager()

    class MockOrderManager:
        def __init__(self):
            self.order_queue = asyncio.Queue()
            self.available_balance = 1000.0
            self.is_dry_run = True

    app.state.engine = MockEngine()
    app.state.order_manager = MockOrderManager()

    # ensure global_state.active_connections is a known state if possible
    # it's usually a set or dict

    client = TestClient(app)

    response = client.get(
        "/api/v1/health",
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["metrics"]["engine_paused"] is False
    assert data["metrics"]["kill_switch"] is False
    assert data["metrics"]["order_queue_size"] == 0
    assert data["metrics"]["available_balance"] == 1000.0
    assert data["metrics"]["dry_run"] is True
    assert "connections" in data["metrics"]


@pytest.mark.asyncio
async def test_health_check_degraded_no_engine():
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings
    import asyncio

    class MockOrderManager:
        def __init__(self):
            self.order_queue = asyncio.Queue()
            self.available_balance = 1000.0
            self.is_dry_run = True

    delattr(app.state, "engine") if hasattr(app.state, "engine") else None
    app.state.order_manager = MockOrderManager()

    client = TestClient(app)

    response = client.get(
        "/api/v1/health",
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert "engine_paused" not in data["metrics"]
    assert data["metrics"]["order_queue_size"] == 0


@pytest.mark.asyncio
async def test_health_check_degraded_no_order_manager():
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockRiskManager:
        def __init__(self):
            self.kill_switch_active = False

    class MockEngine:
        def __init__(self):
            self.is_paused = False
            self.risk_manager = MockRiskManager()

    app.state.engine = MockEngine()
    delattr(app.state, "order_manager") if hasattr(app.state, "order_manager") else None

    client = TestClient(app)

    response = client.get(
        "/api/v1/health",
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["metrics"]["engine_paused"] is False
    assert "order_queue_size" not in data["metrics"]


@pytest.mark.asyncio
async def test_health_check_degraded_both_missing():
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    delattr(app.state, "engine") if hasattr(app.state, "engine") else None
    delattr(app.state, "order_manager") if hasattr(app.state, "order_manager") else None

    client = TestClient(app)

    response = client.get(
        "/api/v1/health",
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert "engine_paused" not in data["metrics"]
    assert "order_queue_size" not in data["metrics"]


def test_set_strategy_success(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    # Tests for line 367-385
    class MockEngine:
        pass

    app.state.engine = MockEngine()
    client = TestClient(app)

    payload = {"strategy": "TestStrategy"}
    response = client.post(
        "/api/v1/strategy", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["message"] == "Strategy set to TestStrategy"
    assert settings.ACTIVE_STRATEGY == "TestStrategy"


def test_set_strategy_no_engine(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    app.state.engine = None
    client = TestClient(app)

    payload = {"strategy": "TestStrategy"}
    response = client.post(
        "/api/v1/strategy", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Engine not initialized"


def test_set_strategy_exception(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockEngine:
        pass

    app.state.engine = MockEngine()
    client = TestClient(app)

    # Force an exception by breaking something
    mocker.patch(
        "core.api_server.logger.info", side_effect=Exception("Test strategy error")
    )

    payload = {"strategy": "TestStrategy"}
    response = client.post(
        "/api/v1/strategy", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 500
    assert "Test strategy error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_run_backtest_success(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    # Tests for line 388-416
    client = TestClient(app)

    class MockBacktester:
        def __init__(self, strategy=None):
            pass

        async def run(self, data_path):
            return {"profit": 100}

    mocker.patch("core.strategy_loader.load_strategy", return_value="mocked_strategy")
    mocker.patch(
        "core.backtester_v2.VectorizedBacktester", return_value=MockBacktester()
    )

    payload = {"strategy": "TestStrategy", "data_path": "data/test.parquet"}
    response = client.post(
        "/api/v1/backtest", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["metrics"]["profit"] == 100


@pytest.mark.asyncio
async def test_run_backtest_exception(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    client = TestClient(app)

    mocker.patch(
        "core.strategy_loader.load_strategy", side_effect=Exception("Backtest error")
    )

    payload = {"strategy": "TestStrategy"}
    response = client.post(
        "/api/v1/backtest", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 500
    assert "Backtest error" in response.json()["detail"]


def test_get_settings(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    client = TestClient(app)
    response = client.get(
        "/api/v1/settings", headers={"X-API-Key": settings.API_SECRET_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert "DRY_RUN_MODE" in data
    assert "CORAX_ENV" in data
    assert "ACTIVE_STRATEGY" in data


def test_update_settings_success(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    client = TestClient(app)

    payload = {"MAX_RISK_PER_TRADE_PCT": 2.5}
    response = client.post(
        "/api/v1/settings", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["updated_keys"] == 1
    assert settings.MAX_RISK_PER_TRADE_PCT == 2.5


def test_update_settings_invalid_type(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    client = TestClient(app)

    payload = {"MAX_RISK_PER_TRADE_PCT": "not_a_float"}
    response = client.post(
        "/api/v1/settings", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["message"] == "No valid keys to update"


@pytest.mark.asyncio
async def test_update_portfolio_success(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockPaperLedger:
        balance = 1000.0

    class MockOrderManager:
        is_dry_run = True
        paper_ledger = MockPaperLedger()
        available_balance = 1000.0

    app.state.order_manager = MockOrderManager()

    client = TestClient(app)
    payload = {"balance": 2000.0}

    response = client.post(
        "/api/v1/portfolio",
        json=payload,
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert app.state.order_manager.paper_ledger.balance == 2000.0
    assert app.state.order_manager.available_balance == 2000.0


@pytest.mark.asyncio
async def test_update_portfolio_no_order_manager(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    app.state.order_manager = None
    client = TestClient(app)

    response = client.post(
        "/api/v1/portfolio",
        json={"balance": 2000.0},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_update_portfolio_not_dry_run(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockOrderManager:
        is_dry_run = False

    app.state.order_manager = MockOrderManager()
    client = TestClient(app)

    response = client.post(
        "/api/v1/portfolio",
        json={"balance": 2000.0},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_control_engine_success(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockRiskManager:
        kill_switch_active = False

    class MockEngine:
        is_paused = False
        risk_manager = MockRiskManager()

    app.state.engine = MockEngine()
    client = TestClient(app)

    # Test pause
    response = client.post(
        "/api/v1/engine/control",
        json={"action": "pause"},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 200
    assert app.state.engine.is_paused

    # Test resume
    response = client.post(
        "/api/v1/engine/control",
        json={"action": "resume"},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 200
    assert not app.state.engine.is_paused

    # Test kill_switch
    response = client.post(
        "/api/v1/engine/control",
        json={"action": "kill_switch"},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 200
    assert app.state.engine.risk_manager.kill_switch_active


@pytest.mark.asyncio
async def test_control_engine_invalid_action(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockEngine:
        pass

    app.state.engine = MockEngine()
    client = TestClient(app)

    response = client.post(
        "/api/v1/engine/control",
        json={"action": "invalid"},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_control_engine_no_engine(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    app.state.engine = None
    client = TestClient(app)

    response = client.post(
        "/api/v1/engine/control",
        json={"action": "pause"},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_update_portfolio_exception(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockPaperLedger:
        balance = 1000.0

    class MockOrderManager:
        is_dry_run = True
        paper_ledger = MockPaperLedger()
        available_balance = 1000.0

    app.state.order_manager = MockOrderManager()

    mocker.patch(
        "core.api_server.global_state.update_balance",
        side_effect=Exception("Database error"),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/portfolio",
        json={"balance": 2000.0},
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )

    assert response.status_code == 500
    assert "Database error" in response.json()["detail"]


def test_update_settings_exception_2(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    client = TestClient(app)

    # Mock settings to throw exception on hasattr
    mocker.patch("core.api_server.hasattr", side_effect=Exception("Unknown Error"))

    payload = {"MAX_RISK_PER_TRADE_PCT": 2.5}
    response = client.post(
        "/api/v1/settings", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 500
    assert "Unknown Error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_trade_success(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings
    import asyncio

    class MockOrderManager:
        order_queue = asyncio.Queue()
        active_limit_orders = {"order1": {}, "order2": {}}

    app.state.order_manager = MockOrderManager()

    client = TestClient(app)

    # Cancel single
    payload = {"symbol": "BTC/USDT", "order_id": "order1"}
    response = client.post(
        "/api/trade/cancel",
        json=payload,
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "order1" in response.json()["message"]

    # Cancel all
    payload = {"symbol": "BTC/USDT"}
    response = client.post(
        "/api/trade/cancel",
        json=payload,
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "2" in response.json()["message"]


@pytest.mark.asyncio
async def test_cancel_trade_no_order_manager(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    app.state.order_manager = None
    client = TestClient(app)

    payload = {"symbol": "BTC/USDT", "order_id": "order1"}
    response = client.post(
        "/api/trade/cancel",
        json=payload,
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_cancel_trade_exception(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings
    import asyncio

    class MockOrderManager:
        order_queue = asyncio.Queue()
        active_limit_orders = {}

    app.state.order_manager = MockOrderManager()

    mocker.patch.object(
        app.state.order_manager.order_queue, "put", side_effect=Exception("Queue error")
    )

    client = TestClient(app)

    payload = {"symbol": "BTC/USDT", "order_id": "order1"}
    response = client.post(
        "/api/trade/cancel",
        json=payload,
        headers={"X-API-Key": settings.API_SECRET_KEY},
    )
    assert response.status_code == 500
    assert "Queue error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reset_ledger_success(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockPaperLedger:
        balance = 1000.0

        def reset_ledger(self):
            self.balance = 5000.0

    class MockOrderManager:
        is_dry_run = True
        paper_ledger = MockPaperLedger()
        available_balance = 1000.0

    app.state.order_manager = MockOrderManager()

    client = TestClient(app)

    response = client.post(
        "/api/v1/ledger/reset", headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "5000.0" in response.json()["message"]
    assert app.state.order_manager.available_balance == 5000.0


@pytest.mark.asyncio
async def test_reset_ledger_no_order_manager(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    app.state.order_manager = None
    client = TestClient(app)

    response = client.post(
        "/api/v1/ledger/reset", headers={"X-API-Key": settings.API_SECRET_KEY}
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_reset_ledger_not_dry_run(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockOrderManager:
        is_dry_run = False

    app.state.order_manager = MockOrderManager()
    client = TestClient(app)

    response = client.post(
        "/api/v1/ledger/reset", headers={"X-API-Key": settings.API_SECRET_KEY}
    )
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_reset_ledger_exception(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    class MockPaperLedger:
        def reset_ledger(self):
            raise Exception("Reset error")

    class MockOrderManager:
        is_dry_run = True
        paper_ledger = MockPaperLedger()

    app.state.order_manager = MockOrderManager()
    client = TestClient(app)

    response = client.post(
        "/api/v1/ledger/reset", headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 500
    assert "Reset error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_handle_manual_trade(mocker):
    from core.api_server import _handle_manual_trade
    import asyncio

    class MockOrderManager:
        order_queue = asyncio.Queue()

    order_manager = MockOrderManager()

    # Valid trade
    await _handle_manual_trade(
        {"side": "BUY", "size": 1.0, "symbol": "BTC/USDT"}, order_manager
    )
    action, order_data = await order_manager.order_queue.get()
    assert action == "CREATE"
    assert order_data["side"] == "buy"
    assert order_data["amount"] == 1.0

    # Invalid size
    await _handle_manual_trade(
        {"side": "SELL", "size": -1.0, "symbol": "BTC/USDT"}, order_manager
    )
    assert order_manager.order_queue.empty()

    # Missing side
    await _handle_manual_trade({"size": 1.0, "symbol": "BTC/USDT"}, order_manager)
    assert order_manager.order_queue.empty()


@pytest.mark.asyncio
async def test_handle_cancel_all(mocker):
    from core.api_server import _handle_cancel_all
    import asyncio

    class MockOrderManager:
        order_queue = asyncio.Queue()
        active_limit_orders = {"order1": {}, "order2": {}}

    order_manager = MockOrderManager()
    await _handle_cancel_all(order_manager)

    assert order_manager.order_queue.qsize() == 2

    # Check if empty doesn't fail
    order_manager2 = None
    await _handle_cancel_all(order_manager2)


@pytest.mark.asyncio
async def test_websocket_endpoint_full(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    # We mock out receive_messages and send_messages to cover lines in websocket_endpoint
    # Or just use the test client websocket feature

    # Let's mock secrets.compare_digest for coverage of the 1008 case
    mocker.patch("core.api_server.secrets.compare_digest", return_value=False)
    client = TestClient(app)

    from fastapi import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json({"action": "auth", "api_key": "wrong"})
            websocket.receive_json()

    # Now a valid connection
    mocker.patch("core.api_server.secrets.compare_digest", return_value=True)

    class MockOrderManager:
        pass

    app.state.order_manager = MockOrderManager()

    with client.websocket_connect("/ws/stream") as websocket:
        websocket.send_json({"action": "auth", "api_key": settings.API_SECRET_KEY})

        websocket.send_json(
            {"action": "manual_trade", "side": "BUY", "size": 1.0, "symbol": "BTC/USDT"}
        )
        websocket.send_json({"action": "cancel_all"})


@pytest.mark.asyncio
async def test_run_backtest_path_traversal(mocker):
    from fastapi.testclient import TestClient
    from core.api_server import app
    from core.config import settings

    client = TestClient(app)

    payload = {"strategy": "SmaCrossover", "data_path": "../../../etc/passwd"}
    response = client.post(
        "/api/v1/backtest", json=payload, headers={"X-API-Key": settings.API_SECRET_KEY}
    )

    assert response.status_code == 400
    assert "Invalid data_path" in response.json()["detail"]
