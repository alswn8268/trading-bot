"""
한국투자증권 (KIS) Open API 연동
공식 문서: https://apiportal.koreainvestment.com
"""
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


class KISExchange:
    REAL_BASE = "https://openapi.koreainvestment.com:9443"
    PAPER_BASE = "https://openapivts.koreainvestment.com:29443"

    def __init__(self, app_key: str, app_secret: str, account_no: str, is_paper: bool = True):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no      # "12345678-01" 형식
        self.is_paper = is_paper
        self.base_url = self.PAPER_BASE if is_paper else self.REAL_BASE
        self.access_token: Optional[str] = None
        self.token_expired: Optional[datetime] = None

    # ── 인증 ───────────────────────────────────────────
    def get_token(self) -> str:
        """OAuth2 액세스 토큰 발급"""
        if self.access_token and self.token_expired and datetime.now() < self.token_expired:
            return self.access_token

        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = requests.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.token_expired = datetime.now() + timedelta(hours=23)
        return self.access_token

    def _headers(self, tr_id: str) -> dict:
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.get_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    # ── 시세 조회 ───────────────────────────────────────
    def get_price(self, symbol: str) -> dict:
        """현재가 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol}
        resp = requests.get(url, headers=self._headers("FHKST01010100"), params=params)
        resp.raise_for_status()
        data = resp.json()["output"]
        return {
            "symbol": symbol,
            "price": float(data["stck_prpr"]),
            "change_pct": float(data["prdy_ctrt"]),
            "volume": int(data["acml_vol"]),
            "name": data.get("hts_kor_isnm", symbol),
        }

    def get_ohlcv(self, symbol: str, period: str = "D", count: int = 100) -> pd.DataFrame:
        """일/주/월봉 조회 (period: D/W/M)"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": symbol,
            "fid_input_date_1": start_date,
            "fid_input_date_2": end_date,
            "fid_period_div_code": period,
            "fid_org_adj_prc": "0",
        }
        resp = requests.get(url, headers=self._headers("FHKST03010100"), params=params)
        resp.raise_for_status()
        rows = resp.json().get("output2", [])
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df = df.rename(columns={
            "stck_bsop_date": "date",
            "stck_oprc": "open",
            "stck_hgpr": "high",
            "stck_lwpr": "low",
            "stck_clpr": "close",
            "acml_vol": "volume",
        })
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        return df.tail(count)

    # ── 주문 ───────────────────────────────────────────
    def _order(self, symbol: str, qty: int, price: int, order_type: str, tr_id: str) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        acno, acprd = self.account_no.split("-")
        body = {
            "CANO": acno,
            "ACNT_PRDT_CD": acprd,
            "PDNO": symbol,
            "ORD_DVSN": "01" if price == 0 else "00",  # 01=시장가, 00=지정가
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        resp = requests.post(url, headers=self._headers(tr_id), json=body)
        resp.raise_for_status()
        return resp.json()

    def buy(self, symbol: str, qty: int, price: int = 0) -> dict:
        """매수 주문 (price=0이면 시장가)"""
        tr_id = "VTTC0802U" if self.is_paper else "TTTC0802U"
        return self._order(symbol, qty, price, "buy", tr_id)

    def sell(self, symbol: str, qty: int, price: int = 0) -> dict:
        """매도 주문 (price=0이면 시장가)"""
        tr_id = "VTTC0801U" if self.is_paper else "TTTC0801U"
        return self._order(symbol, qty, price, "sell", tr_id)

    def get_balance(self) -> dict:
        """계좌 잔고 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        acno, acprd = self.account_no.split("-")
        tr_id = "VTTC8434R" if self.is_paper else "TTTC8434R"
        params = {
            "CANO": acno,
            "ACNT_PRDT_CD": acprd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        resp = requests.get(url, headers=self._headers(tr_id), params=params)
        resp.raise_for_status()
        result = resp.json()
        return {
            "cash": int(result["output2"][0]["dnca_tot_amt"]),
            "total_eval": int(result["output2"][0]["tot_evlu_amt"]),
            "positions": [
                {
                    "symbol": p["pdno"],
                    "name": p["prdt_name"],
                    "qty": int(p["hldg_qty"]),
                    "avg_price": float(p["pchs_avg_pric"]),
                    "current_price": float(p["prpr"]),
                    "pnl_pct": float(p["evlu_pfls_rt"]),
                }
                for p in result.get("output1", [])
            ],
        }
