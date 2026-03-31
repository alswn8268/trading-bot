"""
SQLite 매매 기록 DB
- trades 테이블: 개별 체결 내역
- 통계 조회: 승률, 총 손익, 평균 수익/손실
"""
import sqlite3
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """테이블 생성 (없을 때만)"""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                exchange    TEXT    NOT NULL,
                symbol      TEXT    NOT NULL,
                action      TEXT    NOT NULL,   -- BUY | SELL
                price       REAL    NOT NULL,
                amount      REAL    NOT NULL,   -- 수량 또는 금액
                pnl         REAL    DEFAULT 0,  -- 실현 손익 (SELL일 때만)
                reason      TEXT,
                confidence  REAL    DEFAULT 0,
                mode        TEXT    DEFAULT 'paper'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_ts
            ON trades(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_symbol
            ON trades(exchange, symbol)
        """)
    logger.info(f"[DB] 초기화 완료: {DB_PATH}")


def record_trade(
    exchange: str,
    symbol: str,
    action: str,
    price: float,
    amount: float,
    pnl: float = 0.0,
    reason: str = "",
    confidence: float = 0.0,
    mode: str = "paper",
):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO trades
               (timestamp, exchange, symbol, action, price, amount, pnl, reason, confidence, mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, exchange, symbol, action.upper(), price, amount, pnl, reason, confidence, mode),
        )
    logger.debug(f"[DB] 기록: {action} {symbol} @ {price:,.2f}  pnl={pnl:+.2f}")


def get_trades(
    exchange: Optional[str] = None,
    symbol: Optional[str] = None,
    action: Optional[str] = None,
    since_date: Optional[str] = None,   # "YYYY-MM-DD"
    mode: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    conditions, params = [], []
    if exchange:
        conditions.append("exchange = ?"); params.append(exchange)
    if symbol:
        conditions.append("symbol = ?"); params.append(symbol)
    if action:
        conditions.append("action = ?"); params.append(action.upper())
    if since_date:
        conditions.append("timestamp >= ?"); params.append(since_date)
    if mode:
        conditions.append("mode = ?"); params.append(mode.lower())

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql   = f"SELECT * FROM trades {where} ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_stats(since_date: Optional[str] = None) -> dict:
    """
    Returns:
        total_trades, win_trades, loss_trades, win_rate,
        total_pnl, avg_win, avg_loss, profit_factor
    """
    conditions, params = ["action = 'SELL'"], []
    if since_date:
        conditions.append("timestamp >= ?"); params.append(since_date)
    where = "WHERE " + " AND ".join(conditions)

    with _get_conn() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) as n, SUM(pnl) as total FROM trades {where}",
            params,
        ).fetchone()
        wins = conn.execute(
            f"SELECT COUNT(*) as n, AVG(pnl) as avg FROM trades {where} AND pnl > 0",
            params,
        ).fetchone()
        losses = conn.execute(
            f"SELECT COUNT(*) as n, AVG(pnl) as avg FROM trades {where} AND pnl <= 0",
            params,
        ).fetchone()

    total  = row["n"] or 0
    win_n  = wins["n"] or 0
    loss_n = losses["n"] or 0
    avg_win  = wins["avg"]   or 0.0
    avg_loss = losses["avg"] or 0.0

    win_rate = (win_n / total * 100) if total > 0 else 0.0
    profit_factor = (
        abs(avg_win * win_n / (avg_loss * loss_n))
        if avg_loss != 0 and loss_n > 0
        else 0.0
    )

    return {
        "total_trades":   total,
        "win_trades":     win_n,
        "loss_trades":    loss_n,
        "win_rate":       round(win_rate, 1),
        "total_pnl":      round(row["total"] or 0.0, 2),
        "avg_win":        round(avg_win,  2),
        "avg_loss":       round(avg_loss, 2),
        "profit_factor":  round(profit_factor, 2),
    }


def get_daily_pnl(days: int = 30) -> list[dict]:
    """최근 N일 일별 손익 반환 (대시보드 차트용)"""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT DATE(timestamp) as day, SUM(pnl) as pnl
               FROM trades
               WHERE action = 'SELL'
                 AND timestamp >= DATE('now', ?)
               GROUP BY day
               ORDER BY day""",
            (f"-{days} days",),
        ).fetchall()
    return [{"date": r["day"], "pnl": round(r["pnl"], 2)} for r in rows]
