"""
바이낸스 (Binance) API 연동
공식 문서: https://binance-docs.github.io/apidocs/
"""
import hmac
import hashlib
import time
import requests
import pandas as pd
from typing import Optional


class BinanceExchange:
    REAL_BASE = "https://api.binance.com"
    TEST_BASE = "https://testnet.binance.vision"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.base_url = self.TEST_BASE if testnet else self.REAL_BASE

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        sig = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        params["signature"] = sig
        return params

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    # ── 시세 ───────────────────────────────────────────
    def get_price(self, symbol: str) -> dict:
        """현재가 조회"""
        resp = requests.get(f"{self.base_url}/api/v3/ticker/24hr",
                            params={"symbol": symbol})
        resp.raise_for_status()
        d = resp.json()
        return {
            "symbol": symbol,
            "price": float(d["lastPrice"]),
            "change_pct": float(d["priceChangePercent"]),
            "volume": float(d["volume"]),
            "high_24h": float(d["highPrice"]),
            "low_24h": float(d["lowPrice"]),
        }

    def get_ohlcv(self, symbol: str, interval: str = "1d", count: int = 200) -> pd.DataFrame:
        """캔들 조회 (interval: 1m/5m/15m/1h/4h/1d/1w)"""
        resp = requests.get(f"{self.base_url}/api/v3/klines",
                            params={"symbol": symbol, "interval": interval, "limit": count})
        resp.raise_for_status()
        rows = resp.json()
        df = pd.DataFrame(rows, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        df["date"] = pd.to_datetime(df["open_time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])
        return df[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)

    # ── 주문 ───────────────────────────────────────────
    def buy_market(self, symbol: str, usdt_amount: float) -> dict:
        """시장가 매수 (USDT 금액 기준)"""
        params = self._sign({
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": usdt_amount,
        })
        resp = requests.post(f"{self.base_url}/api/v3/order",
                             headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def sell_market(self, symbol: str, quantity: float) -> dict:
        """시장가 매도 (코인 수량 기준)"""
        params = self._sign({
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": quantity,
        })
        resp = requests.post(f"{self.base_url}/api/v3/order",
                             headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_balance(self) -> dict:
        """잔고 조회"""
        params = self._sign({})
        resp = requests.get(f"{self.base_url}/api/v3/account",
                            headers=self._headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        usdt = 0
        positions = []
        for b in data["balances"]:
            free = float(b["free"])
            if free == 0:
                continue
            if b["asset"] == "USDT":
                usdt = free
            else:
                sym = f"{b['asset']}USDT"
                try:
                    cur = self.get_price(sym)
                    cur_price = cur["price"]
                except Exception:
                    cur_price = 0
                positions.append({
                    "symbol": sym,
                    "name": b["asset"],
                    "qty": free,
                    "current_price": cur_price,
                    "pnl_pct": 0,  # 평균단가 별도 조회 필요
                })
        return {"cash": usdt, "positions": positions}
