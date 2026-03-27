# 🤖 자동 매매봇

국내 주식(한국투자증권) + 암호화폐(업비트/바이낸스) 자동 매매봇
실시간 웹 대시보드 · Discord/카카오톡 알림 · 백테스트 엔진 포함

---

## 📁 파일 구조

```
trading_bot/
├── main.py               # FastAPI 서버 (웹 대시보드 + WebSocket + REST API)
├── bot.py                # 봇 핵심 엔진 (포지션 추적 · 손절/익절 · 알림/DB 연동)
├── notifier.py           # Discord webhook + 카카오 나에게 보내기 알림
├── database.py           # SQLite 매매 기록 (거래 내역 · 통계 · 일별 손익)
├── backtest.py           # 백테스트 엔진 (슬라이딩 윈도우 · 수수료 · MDD 계산)
├── config.yaml           # ⚠️ API 키 및 설정 (이 파일만 수정하면 됨)
├── requirements.txt      # 의존성 패키지
├── data/
│   └── trades.db         # 자동 생성 — 매매 기록 SQLite DB
├── exchanges/
│   ├── kis.py            # 한국투자증권 KIS API
│   ├── upbit.py          # 업비트 API
│   └── binance_ex.py     # 바이낸스 API
├── strategies/
│   ├── ma_crossover.py   # 이동평균 골든/데드크로스
│   ├── rsi_strategy.py   # RSI 과매수/과매도
│   ├── bollinger.py      # 볼린저 밴드
│   ├── volatility_breakout.py  # 변동성 돌파 (코인 단타)
│   └── macd_strategy.py  # MACD 히스토그램 크로스
└── dashboard/
    └── index.html        # 웹 대시보드 UI
```

---

## 🚀 설치 및 실행

### 1. Python 버전 확인 (3.11 이상 필요)
```bash
python --version
```

### 2. 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. API 키 설정
`config.yaml`을 열고 사용할 거래소의 API 키를 입력하세요.
키를 입력하지 않은 거래소는 자동으로 비활성화됩니다.

```yaml
kis:
  app_key: "발급받은 앱키"
  app_secret: "발급받은 앱시크릿"
  account_no: "계좌번호-상품코드"  # 예: 12345678-01

upbit:
  access_key: "업비트 액세스키"
  secret_key: "업비트 시크릿키"

binance:
  api_key: "바이낸스 API키"
  api_secret: "바이낸스 시크릿키"
```

### 4. 봇 실행
```bash
python main.py
# 또는
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 5. 대시보드 접속
브라우저에서 `http://localhost:8000` 접속

---

## ⚙️ 전략 설명

| 전략 | 키워드 | 권장 대상 | 설명 |
|------|--------|-----------|------|
| **이동평균 크로스** | `ma_crossover` | 국내주식 | 단기 MA가 장기 MA를 상향 돌파 시 매수 (골든크로스) |
| **RSI** | `rsi` | 코인/주식 | RSI 30 이하 과매도 구간 매수, 70 이상 과매수 구간 매도 |
| **볼린저 밴드** | `bollinger` | 코인/주식 | 하단 밴드 터치 시 매수, 상단 밴드 터치 시 매도 |
| **변동성 돌파** | `volatility_breakout` | 코인 단타 | 오늘 시가 + 전일 범위 × k 돌파 시 매수, 익일 시가 청산 |
| **MACD** | `macd` | 코인/주식 | MACD 히스토그램 음→양 교차 매수, 양→음 교차 매도 |

---

## 📲 알림 설정 (Discord / 카카오톡)

`config.yaml`의 `notifications` 섹션에 입력하면 자동으로 활성화됩니다.

```yaml
notifications:
  discord_webhook: "https://discord.com/api/webhooks/..."
  kakao_token: "카카오 나에게 보내기 access_token"
  min_confidence: 0.5   # 이 미만 신뢰도 신호는 무시
  on_buy: true
  on_sell: true
  on_risk: true         # 손절/익절 발동 알림
  on_start_stop: true   # 봇 시작/중지 알림
  daily_summary: true
```

**Discord 웹훅 발급:** Discord 채널 설정 → 연동 → 웹후크 → 새 웹후크
**카카오 토큰 발급:** [카카오 개발자 콘솔](https://developers.kakao.com) → 내 애플리케이션 → 나에게 보내기

---

## 🔬 백테스트

대시보드 오른쪽 패널의 **백테스트** 카드에서 바로 실행할 수 있습니다.
또는 REST API로 직접 호출:

```bash
curl -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "KRW-BTC",
    "exchange": "upbit",
    "strategy": "volatility_breakout",
    "strategy_params": {"k": 0.5, "use_ma_filter": true, "interval": "1d"},
    "initial_capital": 1000000
  }'
```

**반환 통계:** 총 수익률 · 승률 · 최대 낙폭(MDD) · Profit Factor · 평균 수익/손실

---

## 🛡️ 리스크 관리

`config.yaml`의 `risk` 섹션:

```yaml
risk:
  max_loss_pct: 3.0       # 종목당 손절 기준 (%)
  take_profit_pct: 5.0    # 익절 기준 (%)
  max_positions: 5        # 최대 동시 보유 종목
  daily_loss_limit: 2.0   # 일일 손실 한도 (초과 시 신규 주문 차단)
```

손절/익절은 전략 신호보다 **먼저** 체크되어 자동 실행됩니다.

---

## 📊 REST API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/status` | 봇 전체 상태 |
| POST | `/api/bot/start` | 봇 시작 |
| POST | `/api/bot/stop` | 봇 중지 |
| POST | `/api/mode/{paper\|live}` | 모드 전환 |
| GET | `/api/signals` | 최근 신호 목록 |
| GET | `/api/positions` | 현재 포지션 |
| GET | `/api/trades` | 거래 기록 (limit, action, symbol 필터) |
| GET | `/api/stats` | 승률·Profit Factor 등 통계 |
| GET | `/api/daily-pnl` | 일별 손익 (최근 N일) |
| POST | `/api/backtest` | 백테스트 실행 |
| POST | `/api/positions/reset` | 일일 통계 초기화 |

---

## ⚠️ 중요 주의사항

1. **반드시 모의투자(PAPER 모드)로 먼저 테스트하세요**
   - `config.yaml`의 `mode: "paper"` 유지
   - KIS: `is_paper: true`, Binance: `testnet: true`

2. **실거래 전환 시** (`mode: "live"`)
   - 소액으로 시작
   - `daily_loss_limit`을 작게 설정
   - 24시간 모니터링 권장

3. **API 키 보안**
   - `config.yaml`을 절대 git에 올리지 마세요
   - `.gitignore`에 `config.yaml` 추가 필수

---

## 🔑 API 키 발급 방법

### 한국투자증권 KIS
1. https://apiportal.koreainvestment.com 접속
2. 회원가입 후 앱 등록
3. 모의투자 엔드포인트: `https://openapivts.koreainvestment.com:29443`

### 업비트
1. https://upbit.com → 마이페이지 → Open API 관리
2. 주문/잔고 권한 체크 후 발급

### 바이낸스
1. 테스트넷: https://testnet.binance.vision
2. 실거래: https://www.binance.com → API Management
