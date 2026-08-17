import asyncio
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Request,
    HTTPException,
    Depends,
    status,
)
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from loguru import logger
import os
import time
from collections import defaultdict, deque
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import secrets
import re

from core.state import global_state
from core.config import settings

templates = Jinja2Templates(directory="ui")
app = FastAPI(title="Corax Crypto API", docs_url=None, redoc_url=None, openapi_url=None)

# API Key Authentication
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


# Simple in-memory rate limiting (max 100 req / minute per IP/key in this demo)
RATE_LIMIT = 100
RATE_LIMIT_WINDOW = 60
request_counts = defaultdict(deque)


async def verify_api_key(request: Request, api_key: str = Depends(api_key_header)):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Performance & Security Optimization:
    # Use O(1) deque popping from left instead of O(N) list comprehension
    client_queue = request_counts[client_ip]
    while client_queue and now - client_queue[0] >= RATE_LIMIT_WINDOW:
        client_queue.popleft()

    if len(request_counts[client_ip]) >= RATE_LIMIT:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

    request_counts[client_ip].append(now)

    # Security optimization: use secrets.compare_digest to prevent timing attacks
    # and explicitly verify api_key is not None before comparison.
    if api_key is None or not secrets.compare_digest(api_key, settings.API_SECRET_KEY):
        logger.warning(f"Unauthorized API access attempt with key: {api_key}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    return api_key


@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    nonce = secrets.token_hex(16)
    request.state.nonce = nonce
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'nonce-{nonce}' 'strict-dynamic'; style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' ws: wss: http: https:; img-src 'self' data: blob:; frame-ancestors 'none'; worker-src 'self' blob:;"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    return response


allowed_origins = [
    origin.strip()
    for origin in settings.API_ALLOWED_ORIGINS.split(",")
    if origin.strip()
]
if not allowed_origins:
    raise RuntimeError(
        "API_ALLOWED_ORIGINS must not be empty. Insecure CORS fallback to '*' is not allowed."
    )

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Serve static files for the HUD
# Get absolute path to the ui directory
ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")
app.mount("/static", StaticFiles(directory=ui_dir), name="static")


class TradeRequest(BaseModel):
    symbol: str
    side: str
    amount: float = Field(gt=0)
    order_type: str = "market"
    price: float = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str):
        v = v.lower()
        if v not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        return v

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str):
        if not re.match(r"^[A-Z0-9]+/[A-Z0-9]+$", v):
            raise ValueError("symbol must be valid format like BTC/USDT")
        return v


class CancelRequest(BaseModel):
    symbol: str
    order_id: str = None  # None implies CANCEL ALL


class ControlRequest(BaseModel):
    action: str

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str):
        if v not in ("pause", "resume", "kill_switch"):
            raise ValueError("action must be pause, resume, or kill_switch")
        return v


class PortfolioRequest(BaseModel):
    balance: float


class StrategyRequest(BaseModel):
    strategy: str


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Serves the main HUD HTML dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"api_key": settings.API_SECRET_KEY, "nonce": request.state.nonce},
    )


@app.post("/api/trade/place")
async def place_trade(
    request: Request, trade: TradeRequest, api_key: str = Depends(verify_api_key)
):
    """Manual trigger to place a trade via OrderManager."""
    order_manager = getattr(request.app.state, "order_manager", None)
    if not order_manager:
        raise HTTPException(status_code=503, detail="OrderManager not initialized")

    try:
        # Wrap manual trade logic, push directly into queue bypassing signal validation
        await order_manager.order_queue.put(
            (
                "CREATE",
                {
                    "symbol": trade.symbol,
                    "type": trade.order_type,
                    "side": trade.side,
                    "amount": trade.amount,
                    "price": trade.price,
                },
            )
        )
        logger.info(
            f"Manual {trade.side} order placed for {trade.amount} {trade.symbol}"
        )
        return {
            "status": "success",
            "message": f"Order queued: {trade.side} {trade.amount} {trade.symbol}",
        }
    except Exception as e:
        logger.error(f"Failed to place manual trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trade/cancel")
async def cancel_trade(
    request: Request, cancel: CancelRequest, api_key: str = Depends(verify_api_key)
):
    """Manual trigger to cancel orders."""
    order_manager = getattr(request.app.state, "order_manager", None)
    if not order_manager:
        raise HTTPException(status_code=503, detail="OrderManager not initialized")

    try:
        if cancel.order_id:
            await order_manager.order_queue.put(
                ("CANCEL", {"symbol": cancel.symbol, "order_id": cancel.order_id})
            )
            logger.info(f"Manual cancel placed for order {cancel.order_id}")
            return {
                "status": "success",
                "message": f"Cancel queued for {cancel.order_id}",
            }
        else:
            # Cancel ALL
            orders_to_cancel = list(order_manager.active_limit_orders.keys())
            for o_id in orders_to_cancel:
                await order_manager.order_queue.put(
                    ("CANCEL", {"order_id": o_id, "symbol": cancel.symbol})
                )
            logger.info(
                f"Manual CANCEL ALL placed for {cancel.symbol}. Cancelling {len(orders_to_cancel)} orders."
            )
            return {
                "status": "success",
                "message": f"Cancelled {len(orders_to_cancel)} orders for {cancel.symbol}",
            }
    except Exception as e:
        logger.error(f"Failed to cancel trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/ledger/reset")
async def reset_ledger(request: Request, api_key: str = Depends(verify_api_key)):
    """Resets the paper trading ledger back to its initial balance."""
    order_manager = getattr(request.app.state, "order_manager", None)
    if not order_manager:
        raise HTTPException(status_code=503, detail="OrderManager not initialized")

    if not order_manager.is_dry_run:
        raise HTTPException(
            status_code=400, detail="Ledger reset is only available in DRY_RUN_MODE."
        )

    try:
        # Reset the paper ledger
        order_manager.paper_ledger.reset_ledger()

        # Update the available balance in OrderManager to reflect the reset
        order_manager.available_balance = order_manager.paper_ledger.balance

        # We also need to update the global_state so the UI reflects the change immediately
        await global_state.update_balance(order_manager.available_balance)

        logger.info("Manual ledger reset triggered via API.")
        return {
            "status": "success",
            "message": f"Ledger reset to {order_manager.available_balance}",
        }
    except Exception as e:
        logger.error(f"Failed to reset ledger: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _handle_manual_trade(data: dict, order_manager):
    side = data.get("side")
    symbol = data.get("symbol", "BTC/USDT")
    size = data.get("size", 0.0)
    if order_manager and side and size > 0:
        await order_manager.order_queue.put(
            (
                "CREATE",
                {
                    "symbol": symbol,
                    "type": "market",
                    "side": side.lower(),
                    "amount": size,
                },
            )
        )
        logger.info(f"WS Manual Trade queued: {side} {size} {symbol}")


async def _handle_cancel_all(order_manager):
    if order_manager:
        orders_to_cancel = list(order_manager.active_limit_orders.keys())
        for o_id in orders_to_cancel:
            # Assume first symbol or passed symbol, for cancel_all we might not have a specific symbol
            await order_manager.order_queue.put(
                ("CANCEL", {"order_id": o_id, "symbol": "ALL"})
            )
        logger.info(
            f"WS Manual Cancel All queued. Cancelling {len(orders_to_cancel)} orders."
        )


@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        # Wait for the first authentication message
        auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        if auth_message.get("action") != "auth":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        api_key = auth_message.get("api_key")
        if api_key is None or not secrets.compare_digest(
            api_key, settings.API_SECRET_KEY
        ):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except (asyncio.TimeoutError, WebSocketDisconnect):
        logger.warning("WebSocket authentication timed out or disconnected.")
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception as close_error:
            logger.warning(
                f"Failed to close websocket on timeout/disconnect: {close_error}"
            )
        return
    except Exception as e:
        logger.error(f"WebSocket auth error: {e}")
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception as close_error:
            logger.warning(f"Failed to close websocket on auth error: {close_error}")
        return
    queue = await global_state.add_connection()

    async def receive_messages():
        try:
            while True:
                data = await websocket.receive_json()
                action = data.get("action")
                order_manager = websocket.app.state.order_manager

                if action == "manual_trade":
                    await _handle_manual_trade(data, order_manager)
                elif action == "cancel_all":
                    await _handle_cancel_all(order_manager)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected during receive.")
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")

    async def send_messages():
        try:
            if global_state.latest_signal:
                await websocket.send_json(
                    {
                        "type": "signal",
                        "data": global_state.latest_signal.model_dump(),
                        "regime": global_state.current_regime,
                    }
                )

            while True:
                data = await queue.get()
                await websocket.send_json(data)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected during send.")
        except Exception as e:
            logger.error(f"WebSocket send error: {e}")

    receive_task = asyncio.create_task(receive_messages())
    send_task = asyncio.create_task(send_messages())
    try:
        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("WebSocket task successfully cancelled.")
    except asyncio.CancelledError:
        receive_task.cancel()
        send_task.cancel()
        logger.info("WebSocket connection cancelled by server shutdown.")
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        await global_state.remove_connection(queue)
        logger.info("Client disconnected normally.")


@app.post("/api/v1/engine/control")
async def control_engine(
    request: Request, control: ControlRequest, api_key: str = Depends(verify_api_key)
):
    engine = getattr(request.app.state, "engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    if control.action == "pause":
        engine.is_paused = True
        logger.info("Engine PAUSED via API")
        return {"status": "success", "message": "Engine paused"}
    elif control.action == "resume":
        engine.is_paused = False
        logger.info("Engine RESUMED via API")
        return {"status": "success", "message": "Engine resumed"}
    elif control.action == "kill_switch":
        engine.risk_manager.kill_switch_active = True
        logger.warning("KILL SWITCH ACTIVATED via API")
        return {"status": "success", "message": "Kill switch activated"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action")


@app.post("/api/v1/portfolio")
async def update_portfolio(
    request: Request, payload: PortfolioRequest, api_key: str = Depends(verify_api_key)
):
    order_manager = getattr(request.app.state, "order_manager", None)
    if not order_manager:
        raise HTTPException(status_code=503, detail="OrderManager not initialized")

    if not order_manager.is_dry_run:
        raise HTTPException(
            status_code=400,
            detail="Portfolio adjustment only available in DRY_RUN_MODE",
        )

    try:
        # Update balance
        order_manager.paper_ledger.balance = payload.balance
        order_manager.available_balance = payload.balance
        await global_state.update_balance(payload.balance)
        logger.info(f"Portfolio balance adjusted to {payload.balance}")
        return {"status": "success", "message": f"Portfolio set to {payload.balance}"}
    except Exception as e:
        logger.error(f"Failed to adjust portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/strategy")
async def set_strategy(
    request: Request, payload: StrategyRequest, api_key: str = Depends(verify_api_key)
):
    engine = getattr(request.app.state, "engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        # Just update the string in config for now to show the change
        # In a full implementation, we'd hot-reload the strategy class
        from core.config import settings

        settings.ACTIVE_STRATEGY = payload.strategy
        logger.info(f"Strategy updated to {payload.strategy}")
        return {"status": "success", "message": f"Strategy set to {payload.strategy}"}
    except Exception as e:
        logger.error(f"Failed to set strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/strategy/visual")
async def save_visual_strategy(
    request: Request, api_key: str = Depends(verify_api_key)
):
    try:
        payload = await request.json()
        import json
        import os
        from core.config import settings

        os.makedirs(os.path.dirname(settings.VISUAL_STRATEGY_PATH), exist_ok=True)
        with open(settings.VISUAL_STRATEGY_PATH, "w") as f:
            json.dump(payload, f, indent=2)

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to save visual strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/backtest")
async def run_backtest(
    request: Request, payload: dict, api_key: str = Depends(verify_api_key)
):
    """
    Triggers a vectorized backtest for a given strategy over a specific data file.
    Expects payload: {"strategy": "SmaCrossover", "data_path": "data/market_ticks.parquet"}
    """
    from core.strategy_loader import load_strategy
    from core.backtester_v2 import VectorizedBacktester
    from core.config import settings
    import pathlib

    strategy_name = payload.get("strategy", settings.ACTIVE_STRATEGY)
    data_path = payload.get("data_path", "data/market_ticks.parquet")

    # Security Enhancement: Prevent Path Traversal
    base_dir = pathlib.Path("data").resolve()
    target_path = pathlib.Path(data_path).resolve()
    if not target_path.is_relative_to(base_dir):
        logger.warning(f"Path traversal attempt detected: {data_path}")
        raise HTTPException(
            status_code=400,
            detail="Invalid data_path. Must be within the data directory.",
        )

    try:
        # Temporarily override settings to load the requested strategy
        original_strategy = settings.ACTIVE_STRATEGY
        settings.ACTIVE_STRATEGY = strategy_name
        strategy_instance = load_strategy()
        settings.ACTIVE_STRATEGY = original_strategy

        backtester = VectorizedBacktester(strategy=strategy_instance)
        metrics = await backtester.run(data_path)

        return {"status": "success", "metrics": metrics}
    except Exception as e:
        logger.error(f"Failed to run backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/health")
async def health_check(request: Request, api_key: str = Depends(verify_api_key)):
    engine = getattr(request.app.state, "engine", None)
    order_manager = getattr(request.app.state, "order_manager", None)

    status = "healthy"
    details = {}

    if engine:
        details["engine_paused"] = engine.is_paused
        details["kill_switch"] = engine.risk_manager.kill_switch_active
    else:
        status = "degraded"

    if order_manager:
        details["order_queue_size"] = order_manager.order_queue.qsize()
        details["available_balance"] = order_manager.available_balance
        details["dry_run"] = order_manager.is_dry_run
    else:
        status = "degraded"

    details["connections"] = len(global_state.active_connections)

    return {"status": status, "metrics": details}


@app.get("/api/v1/settings")
async def get_settings(api_key: str = Depends(verify_api_key)):
    from core.config import settings

    # Return a safe subset of settings
    safe_settings = {
        "DRY_RUN_MODE": settings.DRY_RUN_MODE,
        "CORAX_ENV": settings.CORAX_ENV,
        "ACTIVE_STRATEGY": settings.ACTIVE_STRATEGY,
        "EXCHANGE_ID": settings.EXCHANGE_ID,
        "MAX_RISK_PER_TRADE_PCT": settings.MAX_RISK_PER_TRADE_PCT,
        "DAILY_DRAWDOWN_LIMIT_PCT": settings.DAILY_DRAWDOWN_LIMIT_PCT,
    }
    return safe_settings


@app.post("/api/v1/settings")
async def update_settings(request: Request, api_key: str = Depends(verify_api_key)):
    try:
        payload = await request.json()
        from core.config import settings

        allowed_keys = {
            "MAX_RISK_PER_TRADE_PCT": float,
            "DAILY_DRAWDOWN_LIMIT_PCT": float,
            "ACTIVE_STRATEGY": str,
        }

        updated = 0
        for k, v in payload.items():
            if k in allowed_keys and hasattr(settings, k):
                try:
                    typed_v = allowed_keys[k](v)
                    setattr(settings, k, typed_v)
                    updated += 1
                except (ValueError, TypeError):
                    logger.warning(f"Invalid value for {k}: {v}")

        if updated > 0:
            logger.info(f"Settings updated via API: {payload}")
            return {"status": "success", "updated_keys": updated}
        else:
            return {"status": "success", "message": "No valid keys to update"}

    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
