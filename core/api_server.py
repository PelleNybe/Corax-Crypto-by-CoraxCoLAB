import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from loguru import logger
import os
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import secrets

from core.state import global_state

templates = Jinja2Templates(directory="ui")
app = FastAPI(title="Corax Crypto API", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    nonce = secrets.token_hex(16)
    request.state.nonce = nonce
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'nonce-{nonce}' 'strict-dynamic'; style-src 'self' 'nonce-{nonce}'; connect-src 'self' ws: wss:; img-src 'self' data: blob:; frame-ancestors 'none';"
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files for the HUD
# Get absolute path to the ui directory
ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")
app.mount("/static", StaticFiles(directory=ui_dir), name="static")


class TradeRequest(BaseModel):
    symbol: str
    side: str  # 'buy' or 'sell'
    amount: float
    order_type: str = "market"
    price: float = None


class CancelRequest(BaseModel):
    symbol: str
    order_id: str = None  # None implies CANCEL ALL


class ControlRequest(BaseModel):
    action: str  # 'pause', 'resume', 'kill_switch'


class PortfolioRequest(BaseModel):
    balance: float


class StrategyRequest(BaseModel):
    strategy: str


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Serves the main HUD HTML dashboard."""
    return templates.TemplateResponse(request, "index.html", {"request": request, "nonce": request.state.nonce})


@app.post("/api/trade/place")
async def place_trade(request: Request, trade: TradeRequest):
    """Manual trigger to place a trade via OrderManager."""
    order_manager = request.app.state.order_manager
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
async def cancel_trade(request: Request, cancel: CancelRequest):
    """Manual trigger to cancel orders."""
    order_manager = request.app.state.order_manager
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
async def reset_ledger(request: Request):
    """Resets the paper trading ledger back to its initial balance."""
    order_manager = request.app.state.order_manager
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


@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue = await global_state.add_connection()

    async def receive_messages():
        try:
            while True:
                data = await websocket.receive_json()
                action = data.get("action")
                order_manager = websocket.app.state.order_manager

                if action == "manual_trade":
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

                elif action == "cancel_all":
                    if order_manager:
                        orders_to_cancel = list(
                            order_manager.active_limit_orders.keys()
                        )
                        for o_id in orders_to_cancel:
                            # Assume first symbol or passed symbol, for cancel_all we might not have a specific symbol
                            await order_manager.order_queue.put(
                                ("CANCEL", {"order_id": o_id, "symbol": "ALL"})
                            )
                        logger.info(
                            f"WS Manual Cancel All queued. Cancelling {len(orders_to_cancel)} orders."
                        )
        except WebSocketDisconnect:
            pass
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
            pass
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
                pass
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
async def control_engine(request: Request, control: ControlRequest):
    engine = request.app.state.engine
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
async def update_portfolio(request: Request, payload: PortfolioRequest):
    order_manager = request.app.state.order_manager
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
async def set_strategy(request: Request, payload: StrategyRequest):
    engine = request.app.state.engine
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


@app.get("/api/v1/health")
async def health_check(request: Request):
    engine = request.app.state.engine
    order_manager = request.app.state.order_manager

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
async def get_settings():
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
async def update_settings(request: Request):
    try:
        data = await request.json()
        from core.config import settings

        # Update settings dynamically
        if "MAX_RISK_PER_TRADE_PCT" in data:
            settings.MAX_RISK_PER_TRADE_PCT = float(data["MAX_RISK_PER_TRADE_PCT"])
        if "DAILY_DRAWDOWN_LIMIT_PCT" in data:
            settings.DAILY_DRAWDOWN_LIMIT_PCT = float(data["DAILY_DRAWDOWN_LIMIT_PCT"])

        logger.info(f"Settings updated via API: {data}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
