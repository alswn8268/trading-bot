"""
업비트 (Upbit) API 연동
공식 문서: https://docs.upbit.com
"""
import jwt
import uuid
import hashlib
import requests
import pandas as pd
from datetime import datetime
from urllib.parse import urlencode
from typing import Optional


class UpbitExchange:
    BASE = "https://api.upbit.com/v1"

    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key

    def _auth_header(self, query: dict = None) -> dict:
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if query:
            query_str = urlencode(query).encode()
            m = hashlib.sha512()
            m.update(query_str)
            payload["query_hash"] = m.hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    # ── 시세 ───────────────────────────────────────────
    def get_price(self, symbol: str) -> dict:
        """현재가 (예: KRW-BTC)"""
        resp = requests.get(f"{self.BASE}/ticker", params={"markets": symbol})
        resp.raise_for_status()
        d = resp.json()[0]
        return {
            "symbol": symbol,
            "price": d["trade_price"],
            "change_pct": d["signed_change_rate"] * 100,
            "volume": d["acc_trade_volume_24h"],
            "high_24h": d["high_price"],
            "low_24h": d["low_price"],
        }

    def get_ohlcv(self, symbol: str, interval: str = "days", count: int = 200) -> pd.DataFrame:
        """
        캔들 조회
        interval: minutes/1, minutes/3, minutes/5, minutes/15, minutes/60,
                  days, weeks, months
        """
        url_map = {
            "1m": "minutes/1", "3m": "minutes/3", "5m": "minutes/5",
            "15m": "minutes/15", "1h": "minutes/60",
            "1d": "days", "1w": "weeks",
        }
        interval = url_map.get(interval, interval)
        url = f"{self.BASE}/candles/{interval}"
        params = {"market": symbol, "count": min(count, 200)}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        rows = resp.json()
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            "candle_date_time_kst": "date",
            "opening_price": "open",
            "high_price": "high",
            "low_price": "low",
            "trade_price": "close",
            "candle_acc_trade_volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df = df.sort_values("date").reset_index(drop=True)
        return df

    # ── 주문 ───────────────────────────────────────────
    def buy_market(self, symbol: str, amount_krw: float) -> dict:
        """시장가 매수 (KRW 금액 기준)"""
        params = {"market": symbol, "side": "bid", "price": str(int(amount_krw)),
                  "ord_type": "price"}
        resp = requests.post(f"{self.BASE}/orders",
                             json=params, headers=self._auth_header(params))
        if not resp.ok:
            raise Exception(f"{resp.status_code} {resp.json()}")
        return resp.json()

    def sell_market(self, symbol: str, volume: float) -> dict:
        """시장가 매도 — 실제 잔고 확인 후 매도"""
        currency = symbol.split("-")[1]  # "KRW-BTC" → "BTC"
        # 실제 보유 수량 조회
        try:
            accounts = requests.get(f"{self.BASE}/accounts",
                                    headers=self._auth_header()).json()
            held = next((float(a["balance"]) for a in accounts
                         if a["currency"] == currency), 0.0)
        except Exception:
            held = volume  # 조회 실패 시 원래 수량으로 시도

        if held <= 0:
            raise ValueError(f"{symbol} 잔고 없음 — 매도 스킵")

        sell_volume = min(volume, held)  # 보유량 초과 방지
        params = {"market": symbol, "side": "ask", "volume": str(sell_volume),
                  "ord_type": "market"}
        resp = requests.post(f"{self.BASE}/orders",
                             json=params, headers=self._auth_header(params))
        resp.raise_for_status()
        return resp.json()

    def get_balance(self) -> dict:
        """보유 자산 조회"""
        resp = requests.get(f"{self.BASE}/accounts", headers=self._auth_header())
        resp.raise_for_status()
        accounts = resp.json()
        cash = 0
        positions = []
        for acc in accounts:
            if acc["currency"] == "KRW":
                cash = float(acc["balance"])
            else:
                avg = float(acc["avg_buy_price"])
                qty = float(acc["balance"])
                try:
                    cur = self.get_price(f"KRW-{acc['currency']}")
                    cur_price = cur["price"]
                    pnl_pct = (cur_price - avg) / avg * 100 if avg else 0
                except Exception:
                    cur_price = avg
                    pnl_pct = 0
                positions.append({
                    "symbol": f"KRW-{acc['currency']}",
                    "name": acc["currency"],
                    "qty": qty,
                    "avg_price": avg,
                    "current_price": cur_price,
                    "pnl_pct": pnl_pct,
                })
        return {"cash": cash, "positions": positions}
