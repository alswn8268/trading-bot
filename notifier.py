"""
알림 모듈 — Discord webhook + 카카오톡 나에게 보내기
- Discord: embed 메시지 (BUY=초록, SELL=빨강, 기타=파랑)
- KakaoTalk: 카카오 나에게 보내기 REST API
- Notifier: 두 채널을 묶는 통합 클래스
"""
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


# ── 색상 상수 ────────────────────────────────────────────
COLOR_BUY    = 0x2ECC71   # 초록
COLOR_SELL   = 0xE74C3C   # 빨강
COLOR_INFO   = 0x3498DB   # 파랑
COLOR_WARN   = 0xF39C12   # 노랑


def _action_color(action: str) -> int:
    return {
        "BUY":  COLOR_BUY,
        "SELL": COLOR_SELL,
    }.get(action.upper(), COLOR_INFO)


# ──────────────────────────────────────────────────────────
# Discord
# ──────────────────────────────────────────────────────────
class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url.strip() if webhook_url else ""

    def _send(self, embeds: list) -> bool:
        if not self.webhook_url:
            return False
        try:
            resp = requests.post(
                self.webhook_url,
                json={"embeds": embeds},
                timeout=5,
            )
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"[Discord] 전송 실패: {e}")
            return False

    def send_signal(self, action: str, symbol: str, price: float,
                    reason: str, confidence: float, exchange: str = "") -> bool:
        action_label = {"BUY": "📈 매수", "SELL": "📉 매도"}.get(action.upper(), f"⏸ {action}")
        embed = {
            "title": f"{action_label}  |  {symbol}",
            "description": reason,
            "color": _action_color(action),
            "fields": [
                {"name": "가격",       "value": f"{price:,.2f}",        "inline": True},
                {"name": "신뢰도",     "value": f"{confidence*100:.0f}%", "inline": True},
                {"name": "거래소",     "value": exchange or "—",         "inline": True},
            ],
            "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        }
        return self._send([embed])

    def send_risk_exit(self, symbol: str, price: float, reason: str, exchange: str = "") -> bool:
        embed = {
            "title": f"⚠️ 리스크 청산  |  {symbol}",
            "description": reason,
            "color": COLOR_WARN,
            "fields": [
                {"name": "청산가",  "value": f"{price:,.2f}", "inline": True},
                {"name": "거래소", "value": exchange or "—",  "inline": True},
            ],
            "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        }
        return self._send([embed])

    def send_bot_start(self, mode: str, task_count: int) -> bool:
        embed = {
            "title": "🚀 매매봇 시작",
            "color": COLOR_INFO,
            "fields": [
                {"name": "모드",       "value": mode,           "inline": True},
                {"name": "전략 수",    "value": str(task_count), "inline": True},
            ],
            "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        }
        return self._send([embed])

    def send_bot_stop(self, reason: str = "수동 중지") -> bool:
        embed = {
            "title": "🛑 매매봇 중지",
            "description": reason,
            "color": COLOR_SELL,
            "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        }
        return self._send([embed])

    def send_daily_summary(self, daily_pnl: float, trade_count: int,
                           win_rate: float, positions: int) -> bool:
        pnl_str = f"{daily_pnl:+,.2f}"
        color   = COLOR_BUY if daily_pnl >= 0 else COLOR_SELL
        embed = {
            "title": "📊 일일 결산",
            "color": color,
            "fields": [
                {"name": "일일 손익",    "value": pnl_str,             "inline": True},
                {"name": "거래 횟수",    "value": str(trade_count),     "inline": True},
                {"name": "승률",         "value": f"{win_rate:.1f}%",   "inline": True},
                {"name": "보유 포지션",  "value": str(positions),       "inline": True},
            ],
            "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        }
        return self._send([embed])


# ──────────────────────────────────────────────────────────
# KakaoTalk  (나에게 보내기 REST API)
# ──────────────────────────────────────────────────────────
_KAKAO_ME_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class KakaoNotifier:
    def __init__(self, access_token: str):
        self.access_token = access_token.strip() if access_token else ""

    def _send(self, text: str) -> bool:
        if not self.access_token:
            return False
        template = {
            "object_type": "text",
            "text": text[:200],   # 최대 200자
            "link": {"web_url": "", "mobile_web_url": ""},
        }
        try:
            resp = requests.post(
                _KAKAO_ME_URL,
                headers={"Authorization": f"Bearer {self.access_token}"},
                data={"template_object": json.dumps(template)},
                timeout=5,
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get("result_code") == 0
            logger.warning(f"[KakaoTalk] HTTP {resp.status_code}: {resp.text[:100]}")
            return False
        except Exception as e:
            logger.warning(f"[KakaoTalk] 전송 실패: {e}")
            return False

    def send_signal(self, action: str, symbol: str, price: float,
                    reason: str, confidence: float, exchange: str = "") -> bool:
        icon = "📈" if action.upper() == "BUY" else "📉"
        text = (
            f"{icon} [{action}] {symbol}\n"
            f"가격: {price:,.2f}  신뢰도: {confidence*100:.0f}%\n"
            f"{reason}"
        )
        return self._send(text)

    def send_risk_exit(self, symbol: str, price: float, reason: str, exchange: str = "") -> bool:
        return self._send(f"⚠️ [리스크 청산] {symbol}\n청산가: {price:,.2f}\n{reason}")

    def send_bot_start(self, mode: str, task_count: int) -> bool:
        return self._send(f"🚀 매매봇 시작\n모드: {mode}  전략 수: {task_count}")

    def send_bot_stop(self, reason: str = "수동 중지") -> bool:
        return self._send(f"🛑 매매봇 중지\n사유: {reason}")

    def send_daily_summary(self, daily_pnl: float, trade_count: int,
                           win_rate: float, positions: int) -> bool:
        pnl_str = f"{daily_pnl:+,.2f}"
        return self._send(
            f"📊 일일 결산\n"
            f"손익: {pnl_str}  거래: {trade_count}회\n"
            f"승률: {win_rate:.1f}%  보유: {positions}종목"
        )


# ──────────────────────────────────────────────────────────
# 통합 Notifier
# ──────────────────────────────────────────────────────────
class Notifier:
    """Discord + KakaoTalk 통합 알림 클래스"""

    def __init__(self, config: dict):
        """
        config 예시 (config.yaml notifications 섹션):
          discord_webhook: "https://discord.com/api/webhooks/..."
          kakao_token: "YOUR_KAKAO_ACCESS_TOKEN"
          min_confidence: 0.5   # 이 미만 신뢰도 신호는 무시
          on_buy: true
          on_sell: true
          on_risk: true
          on_start_stop: true
          daily_summary: true
        """
        self.discord = DiscordNotifier(config.get("discord_webhook", ""))
        self.kakao   = KakaoNotifier(config.get("kakao_token", ""))
        self.min_confidence  = float(config.get("min_confidence", 0.5))
        self.on_buy          = bool(config.get("on_buy", True))
        self.on_sell         = bool(config.get("on_sell", True))
        self.on_risk         = bool(config.get("on_risk", True))
        self.on_start_stop   = bool(config.get("on_start_stop", True))
        self.daily_summary   = bool(config.get("daily_summary", True))

        channels = []
        if self.discord.webhook_url:
            channels.append("Discord")
        if self.kakao.access_token:
            channels.append("KakaoTalk")
        if channels:
            logger.info(f"[Notifier] 활성 채널: {', '.join(channels)}")
        else:
            logger.info("[Notifier] 알림 채널 없음 (config.yaml에 설정 필요)")

    def _both(self, method: str, *args, **kwargs):
        """Discord + KakaoTalk 동시 전송"""
        d = getattr(self.discord, method)(*args, **kwargs)
        k = getattr(self.kakao,   method)(*args, **kwargs)
        return d or k

    def on_signal(self, action: str, symbol: str, price: float,
                  reason: str, confidence: float, exchange: str = ""):
        if action.upper() == "BUY"  and not self.on_buy:  return
        if action.upper() == "SELL" and not self.on_sell: return
        if confidence < self.min_confidence:              return
        self._both("send_signal", action, symbol, price, reason, confidence, exchange)

    def on_risk_exit(self, symbol: str, price: float, reason: str, exchange: str = ""):
        if not self.on_risk:
            return
        self._both("send_risk_exit", symbol, price, reason, exchange)

    def on_bot_start(self, mode: str, task_count: int):
        if not self.on_start_stop:
            return
        self._both("send_bot_start", mode, task_count)

    def on_bot_stop(self, reason: str = "수동 중지"):
        if not self.on_start_stop:
            return
        self._both("send_bot_stop", reason)

    def on_daily_summary(self, daily_pnl: float, trade_count: int,
                         win_rate: float, positions: int):
        if not self.daily_summary:
            return
        self._both("send_daily_summary", daily_pnl, trade_count, win_rate, positions)


# 알림 없이 조용히 동작하는 더미 (설정 없을 때 사용)
class NullNotifier:
    def on_signal(self, *a, **kw): pass
    def on_risk_exit(self, *a, **kw): pass
    def on_bot_start(self, *a, **kw): pass
    def on_bot_stop(self, *a, **kw): pass
    def on_daily_summary(self, *a, **kw): pass


def create_notifier(cfg: dict):
    """config.yaml 전체를 받아 Notifier 또는 NullNotifier 반환"""
    n_cfg = cfg.get("notifications", {})
    has_discord = bool(n_cfg.get("discord_webhook", "").strip())
    has_kakao   = bool(n_cfg.get("kakao_token",     "").strip())
    if has_discord or has_kakao:
        return Notifier(n_cfg)
    return NullNotifier()
