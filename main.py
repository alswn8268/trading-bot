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


@app.post("/api/positions/reset")
async def reset_stats():
    """일일 손익·거래 통계 초기화"""
    bot.realized_pnl = 0.0
    bot.daily_pnl    = 0.0
    bot.trade_count  = 0
    return {"ok": True, "message": "통계 초기화됨"}


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
