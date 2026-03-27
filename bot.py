"""
자동 매매봇 핵심 엔진
- 전략 신호 수신 → 리스크 체크 → 주문 실행 → 상태 기록
"""
import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional
import yaml

from exchanges import KISExchange, UpbitExchange, BinanceExchange
from strategies import get_strategy
from strategies.base import Signal

logger = logging.getLogger("bot")


class TradingBot:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)

        self.mode = self.cfg["mode"]          # paper | live
        self.risk = self.cfg["risk"]
        self.running = False
        self.logs: list[dict] = []            # 최근 로그 (웹소켓 전송용)
        self.signals: list[dict] = []         # 최근 신호
        self.daily_pnl = 0.0
        self._ws_callback: Optional[Callable] = None  # 대시보드 WebSocket 콜백

        self._init_exchanges()
        self._init_strategies()
        logger.info(f"봇 초기화 완료 | 모드: {self.mode.upper()}")

    def _init_exchanges(self):
        """거래소 연결"""
        self.kis: Optional[KISExchange] = None
        self.upbit: Optional[UpbitExchange] = None
        self.binance: Optional[BinanceExchange] = None

        kc = self.cfg.get("kis", {})
        if kc.get("app_key") and kc["app_key"] != "YOUR_KIS_APP_KEY":
            self.kis = KISExchange(kc["app_key"], kc["app_secret"],
                                   kc["account_no"], kc.get("is_paper", True))
            logger.info("KIS 연결됨")

        uc = self.cfg.get("upbit", {})
        if uc.get("access_key") and uc["access_key"] != "YOUR_UPBIT_ACCESS_KEY":
            self.upbit = UpbitExchange(uc["access_key"], uc["secret_key"])
            logger.info("Upbit 연결됨")

        bc = self.cfg.get("binance", {})
        if bc.get("api_key") and bc["api_key"] != "YOUR_BINANCE_API_KEY":
            self.binance = BinanceExchange(bc["api_key"], bc["api_secret"],
                                           bc.get("testnet", True))
            logger.info("Binance 연결됨")

    def _init_strategies(self):
        """전략 초기화"""
        self.tasks: list[dict] = []
        strat_params = self.cfg.get("strategies", {})

        for item in self.cfg["trading"].get("stocks", []):
            s_name = item["strategy"]
            params = strat_params.get(s_name, {})
            self.tasks.append({
                "exchange": "kis", "symbol": item["symbol"],
                "amount": item["amount"],
                "strategy": get_strategy(s_name, item["symbol"], params),
                "interval": params.get("interval", "1d"),
            })

        for item in self.cfg["trading"].get("upbit_coins", []):
            s_name = item["strategy"]
            params = strat_params.get(s_name, {})
            self.tasks.append({
                "exchange": "upbit", "symbol": item["symbol"],
                "amount": item["amount"],
                "strategy": get_strategy(s_name, item["symbol"], params),
                "interval": params.get("interval", "1h"),
            })

        for item in self.cfg["trading"].get("binance_coins", []):
            s_name = item["strategy"]
            params = strat_params.get(s_name, {})
            self.tasks.append({
                "exchange": "binance", "symbol": item["symbol"],
                "amount": item["amount"],
                "strategy": get_strategy(s_name, item["symbol"], params),
                "interval": params.get("interval", "1d"),
            })

        logger.info(f"전략 {len(self.tasks)}개 로드됨")

    # ── 전략 실행 ───────────────────────────────────────
    async def run_cycle(self):
        """단일 분석 사이클 실행"""
        for task in self.tasks:
            try:
                signal = await self._analyze_task(task)
                await self._process_signal(signal, task)
            except Exception as e:
                self._log("ERROR", task["symbol"], f"오류: {e}")

    async def _analyze_task(self, task: dict) -> Signal:
        exchange = task["exchange"]
        symbol = task["symbol"]
        interval = task["interval"]

        loop = asyncio.get_event_loop()

        if exchange == "kis" and self.kis:
            period_map = {"1d": "D", "1w": "W", "1m": "M"}
            period = period_map.get(interval, "D")
            df = await loop.run_in_executor(None, self.kis.get_ohlcv, symbol, period, 100)
        elif exchange == "upbit" and self.upbit:
            interval_map = {"1d": "days", "1h": "minutes/60", "15m": "minutes/15"}
            iv = interval_map.get(interval, "days")
            df = await loop.run_in_executor(None, self.upbit.get_ohlcv, symbol, iv, 200)
        elif exchange == "binance" and self.binance:
            df = await loop.run_in_executor(None, self.binance.get_ohlcv, symbol, interval, 200)
        else:
            # 거래소 미연결: 더미 데이터로 홀드 반환
            import pandas as pd, numpy as np
            dates = pd.date_range(end=datetime.now(), periods=50)
            close = pd.Series(np.random.randn(50).cumsum() + 100)
            df = pd.DataFrame({"date": dates, "open": close, "high": close * 1.01,
                                "low": close * 0.99, "close": close, "volume": 1000})

        return task["strategy"].analyze(df)

    async def _process_signal(self, signal: Signal, task: dict):
        self.signals.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "exchange": task["exchange"].upper(),
            "symbol": signal.symbol,
            "action": signal.action,
            "price": signal.price,
            "reason": signal.reason,
            "confidence": f"{signal.confidence*100:.0f}%",
        })
        self.signals = self.signals[:50]  # 최근 50개 유지

        if signal.action == "HOLD":
            return

        # 일일 손실 한도 체크
        if self.daily_pnl < -self.risk["daily_loss_limit"]:
            self._log("WARN", signal.symbol, f"일일 손실 한도 초과 ({self.daily_pnl:.2f}%), 주문 건너뜀")
            return

        self._log(signal.action, signal.symbol,
                  f"{signal.action} @ {signal.price:,.0f} | {signal.reason} | 신뢰도 {signal.confidence:.0%}")

        # 모의 모드: 실제 주문 X
        if self.mode == "paper":
            self._log("PAPER", signal.symbol, f"[모의] {signal.action} 신호 발생 (실제 주문 안 함)")
            await self._notify_ws()
            return

        # 실거래 주문
        try:
            await self._execute_order(signal, task)
        except Exception as e:
            self._log("ERROR", signal.symbol, f"주문 실패: {e}")

        await self._notify_ws()

    async def _execute_order(self, signal: Signal, task: dict):
        exchange = task["exchange"]
        amount = task["amount"]
        loop = asyncio.get_event_loop()

        if exchange == "kis" and self.kis:
            qty = max(1, int(amount / signal.price))
            if signal.action == "BUY":
                await loop.run_in_executor(None, self.kis.buy, signal.symbol, qty)
            else:
                await loop.run_in_executor(None, self.kis.sell, signal.symbol, qty)

        elif exchange == "upbit" and self.upbit:
            if signal.action == "BUY":
                await loop.run_in_executor(None, self.upbit.buy_market, signal.symbol, amount)
            else:
                qty = amount / signal.price
                await loop.run_in_executor(None, self.upbit.sell_market, signal.symbol, qty)

        elif exchange == "binance" and self.binance:
            if signal.action == "BUY":
                await loop.run_in_executor(None, self.binance.buy_market, signal.symbol, amount)
            else:
                qty = amount / signal.price
                await loop.run_in_executor(None, self.binance.sell_market, signal.symbol, qty)

    # ── 메인 루프 ────────────────────────────────────────
    async def start(self):
        self.running = True
        self._log("INFO", "시스템", f"봇 시작 | 모드: {self.mode.upper()} | 전략 {len(self.tasks)}개")
        while self.running:
            await self.run_cycle()
            await self._notify_ws()
            await asyncio.sleep(60)  # 1분마다 사이클

    def stop(self):
        self.running = False
        self._log("INFO", "시스템", "봇 중지됨")

    # ── 유틸 ──────────────────────────────────────────────
    def _log(self, level: str, symbol: str, msg: str):
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "symbol": symbol,
            "message": msg,
        }
        self.logs.insert(0, entry)
        self.logs = self.logs[:200]
        logger.info(f"[{level}] {symbol}: {msg}")

    async def _notify_ws(self):
        if self._ws_callback:
            await self._ws_callback()

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "mode": self.mode,
            "task_count": len(self.tasks),
            "daily_pnl": self.daily_pnl,
            "logs": self.logs[:30],
            "signals": self.signals[:20],
            "exchanges": {
                "kis": self.kis is not None,
                "upbit": self.upbit is not None,
                "binance": self.binance is not None,
            }
        }
