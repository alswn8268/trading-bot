"""
FastAPI 서버 + WebSocket 실시간 대시보드
실행: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from bot import TradingBot
import database as db
import backtest as bt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

bot = TradingBot("config.yaml")
connected_ws: list[WebSocket] = []
bot_task: asyncio.Task | None = None


async def broadcast(data: dict):
    """연결된 모든 WebSocket에 데이터 전송"""
    dead = []
    for ws in connected_ws:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_ws.remove(ws)


async def ws_notify():
    await broadcast(bot.get_status())


bot._ws_callback = ws_notify


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 봇 자동 실행
    global bot_task
    bot_task = asyncio.create_task(bot.start())
    yield
    bot.stop()
    if bot_task:
        bot_task.cancel()


app = FastAPI(title="자동 매매봇 대시보드", lifespan=lifespan)


# ── REST API ─────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = Path("dashboard/index.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/status")
async def status():
    return JSONResponse(bot.get_status())


@app.post("/api/bot/start")
async def start_bot():
    global bot_task
    if not bot.running:
        bot_task = asyncio.create_task(bot.start())
        return {"ok": True, "message": "봇 시작됨"}
    return {"ok": False, "message": "이미 실행 중"}


@app.post("/api/bot/stop")
async def stop_bot():
    global bot_task
    bot.stop()
    if bot_task:
        bot_task.cancel()
        bot_task = None
    return {"ok": True, "message": "봇 중지됨"}


@app.post("/api/mode/{mode}")
async def set_mode(mode: str):
    if mode not in ("paper", "live"):
        return JSONResponse({"error": "모드는 paper 또는 live"}, status_code=400)
    bot.mode = mode
    return {"ok": True, "mode": mode}


@app.get("/api/signals")
async def get_signals():
    return {"signals": bot.signals}


@app.get("/api/logs")
async def get_logs():
    return {"logs": bot.logs}


@app.get("/api/positions")
async def get_positions():
    return {"positions": list(bot.positions.values())}


@app.get("/api/balance")
async def get_balance():
    """연결된 거래소의 실제 잔액 조회"""
    result = {}
    loop = asyncio.get_running_loop()
    if bot.upbit:
        try:
            bal = await loop.run_in_executor(None, bot.upbit.get_balance)
            result["upbit"] = bal
        except Exception as e:
            result["upbit"] = {"error": str(e)}
    if bot.binance:
        try:
            bal = await loop.run_in_executor(None, bot.binance.get_balance)
            result["binance"] = bal
        except Exception as e:
            result["binance"] = {"error": str(e)}
    return result


@app.post("/api/positions/reset")
async def reset_stats():
    """일일 손익·거래 통계 초기화"""
    bot.realized_pnl = 0.0
    bot.daily_pnl    = 0.0
    bot.trade_count  = 0
    return {"ok": True, "message": "통계 초기화됨"}


@app.put("/api/tasks/{idx}")
async def update_task(idx: int, body: dict):
    strategy_name = body.get("strategy", "")
    amount = float(body.get("amount", 5000))
    interval = body.get("interval", "15m")
    ok = bot.update_task(idx, strategy_name, amount, interval)
    if not ok:
        return JSONResponse({"error": "인덱스 범위 초과"}, status_code=400)
    return {"ok": True}


@app.get("/api/trades")
async def get_trades(limit: int = 200, action: str = None, symbol: str = None, since: str = None, mode: str = None):
    trades = db.get_trades(action=action, symbol=symbol, since_date=since, mode=mode, limit=limit)
    return {"trades": trades}


@app.get("/api/stats")
async def get_stats(since: str = None):
    """since: YYYY-MM-DD 형식, 없으면 전체"""
    stats = db.get_stats(since_date=since)
    return stats


@app.get("/api/daily-pnl")
async def get_daily_pnl(days: int = 30):
    return {"data": db.get_daily_pnl(days=days)}


@app.post("/api/backtest")
async def run_backtest(body: dict):
    """
    body: {
      symbol, exchange, strategy, strategy_params,
      initial_capital, fee_rate, max_loss_pct, take_profit_pct
    }
    백테스트는 실제 OHLCV 데이터를 사용 (봇의 _fetch_ohlcv 활용)
    """
    symbol   = body.get("symbol", "")
    exchange = body.get("exchange", "upbit")
    strategy = body.get("strategy", "")
    params   = body.get("strategy_params", {})

    # OHLCV 조회
    task = {
        "exchange": exchange,
        "symbol":   symbol,
        "interval": params.get("interval", "1d"),
    }
    loop = asyncio.get_running_loop()
    try:
        df = await bot._fetch_ohlcv(task)
    except Exception as e:
        return JSONResponse({"error": f"OHLCV 조회 실패: {e}"}, status_code=500)

    result = bt.run_backtest(
        df=df,
        symbol=symbol,
        strategy_name=strategy,
        strategy_params=params,
        initial_capital=float(body.get("initial_capital", 1_000_000)),
        fee_rate=float(body.get("fee_rate", 0.0005)),
        max_loss_pct=float(body.get("max_loss_pct", bot.risk["max_loss_pct"])),
        take_profit_pct=float(body.get("take_profit_pct", bot.risk["take_profit_pct"])),
    )
    return JSONResponse(result)


# ── WebSocket ────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_ws.append(websocket)
    # 연결 즉시 현재 상태 전송
    await websocket.send_json(bot.get_status())
    try:
        while True:
            await websocket.receive_text()  # 클라이언트 메시지 (ping 등)
    except WebSocketDisconnect:
        connected_ws.remove(websocket)


if __name__ == "__main__":
    import uvicorn
    cfg = bot.cfg.get("server", {})
    uvicorn.run("main:app", host=cfg.get("host", "0.0.0.0"),
                port=cfg.get("port", 8000), reload=False)
