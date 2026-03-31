# 자동 매매봇 (AI Trading Bot)

국내 주식(한국투자증권) + 암호화폐(업비트/바이낸스) 자동 매매봇
실시간 웹 대시보드 · Discord/카카오톡 알림 · Claude AI 종합 분석 · 백테스트 엔진 포함

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| **백엔드** | Python 3.11, FastAPI, asyncio, WebSocket |
| **AI 분석** | Anthropic Claude API (claude-haiku / claude-opus) |
| **데이터베이스** | SQLite (aiosqlite 없이 동기, thread-safe) |
| **거래소 연동** | 업비트 REST API (JWT 인증), 한국투자증권 KIS API, 바이낸스 API |
| **기술적 분석** | RSI, MACD, 볼린저 밴드, 이동평균, 변동성 돌파 |
| **알림** | Discord Webhook, 카카오 나에게 보내기 |
| **프론트엔드** | Vanilla JS, WebSocket, Chart.js, Pretendard 폰트 |
| **배포** | uvicorn ASGI 서버 |

---

## 주요 기능

- **다중 전략 동시 실행** — MA 크로스, RSI, 볼린저, 변동성 돌파, MACD, **AI(Claude) 전략**
- **Claude AI 종합 분석** — RSI·MACD·볼린저·이동평균을 Claude API에 전달해 BUY/SELL/HOLD 신호 생성
- **실시간 대시보드** — WebSocket으로 포지션·신호·로그를 실시간 업데이트
- **손절/익절 자동 실행** — 전략 신호보다 먼저 리스크 체크 후 자동 청산
- **백테스트 엔진** — 실제 OHLCV 데이터 기반 슬라이딩 윈도우, 수수료/MDD 계산
- **매매 기록 DB** — SQLite에 전 거래 저장, 필터링·통계 조회
- **알림** — 매수/매도/손절 발동·봇 시작 중지를 Discord·카카오톡으로 전송
- **모의/실거래 전환** — 대시보드 또는 API로 즉시 전환

---

## 파일 구조

```
trading_bot/
├── main.py               # FastAPI 서버 (대시보드 + WebSocket + REST API)
├── bot.py                # 봇 핵심 엔진 (포지션·손절/익절·알림·DB)
├── notifier.py           # Discord + 카카오 나에게 보내기 알림
├── database.py           # SQLite 매매 기록 (거래 내역·통계·일별 손익)
├── backtest.py           # 백테스트 엔진 (슬라이딩 윈도우·수수료·MDD)
├── config.yaml           # API 키 및 설정 (이 파일만 수정하면 됨)
├── requirements.txt      # 의존성 패키지
├── data/
│   └── trades.db         # 자동 생성 — 매매 기록 SQLite DB
├── exchanges/
│   ├── kis.py            # 한국투자증권 KIS API
│   ├── upbit.py          # 업비트 API
│   └── binance_ex.py     # 바이낸스 API
├── strategies/
│   ├── base.py           # 전략 베이스 클래스 (Signal, BaseStrategy)
│   ├── ma_crossover.py   # 이동평균 골든/데드크로스
│   ├── rsi_strategy.py   # RSI 과매수/과매도
│   ├── bollinger.py      # 볼린저 밴드
│   ├── volatility_breakout.py  # 변동성 돌파 (코인 단타)
│   ├── macd_strategy.py  # MACD 히스토그램 크로스
│   └── ai_strategy.py    # Claude AI 종합 분석 전략
└── dashboard/
    └── index.html        # 웹 대시보드 UI (Vanilla JS + WebSocket)
```

---

## 설치 및 실행

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
upbit:
  access_key: "업비트 액세스키"
  secret_key: "업비트 시크릿키"

# AI 전략 사용 시
strategies:
  ai:
    api_key: "YOUR_ANTHROPIC_API_KEY"  # console.anthropic.com 에서 발급
```

### 4. 봇 실행
```bash
python main.py
```

### 5. 대시보드 접속
브라우저에서 `http://localhost:18880` 접속

---

## 전략 설명

| 전략 | 키워드 | 권장 대상 | 설명 |
|------|--------|-----------|------|
| **이동평균 크로스** | `ma_crossover` | 국내주식 | 단기 MA가 장기 MA를 상향 돌파 시 매수 |
| **RSI** | `rsi` | 코인/주식 | RSI 30↓ 과매도 매수, 70↑ 과매수 매도 |
| **볼린저 밴드** | `bollinger` | 코인/주식 | 하단 밴드 터치 매수, 상단 밴드 터치 매도 |
| **변동성 돌파** | `volatility_breakout` | 코인 단타 | 오늘 시가 + 전일 범위 × k 돌파 시 매수 |
| **MACD** | `macd` | 코인/주식 | 히스토그램 음→양 교차 매수, 양→음 교차 매도 |
| **AI (Claude)** | `ai` | 코인/주식 | RSI·MACD·볼린저·MA를 Claude API로 종합 분석 |

### AI 전략 사용법

`config.yaml`에서 `upbit_coins`의 strategy를 `"ai"`로 설정:

```yaml
upbit_coins:
  - symbol: "KRW-BTC"
    strategy: "ai"
    amount: 5000

strategies:
  ai:
    api_key: "sk-ant-..."          # Anthropic API 키
    model: "claude-haiku-4-5-20251001"  # 빠르고 저렴
    interval: "1h"
```

Claude는 다음 지표를 종합해 분석합니다:
- RSI(14), MACD(12/26/9), 볼린저 밴드(20,2σ)
- MA(5·20·60), 거래량 비교, 최근 5개 봉 OHLCV

---

## 알림 설정 (Discord / 카카오톡)

```yaml
notifications:
  discord_webhook: "https://discord.com/api/webhooks/..."
  kakao_token: "카카오 나에게 보내기 access_token"
  min_confidence: 0.5   # 이 미만 신뢰도 신호 무시
  on_buy: true
  on_sell: true
  on_risk: true         # 손절/익절 발동 알림
  on_start_stop: true   # 봇 시작/중지 알림
```

---

## 백테스트

대시보드 백테스트 패널 또는 REST API로 실행:

```bash
curl -X POST http://localhost:18880/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "KRW-BTC",
    "exchange": "upbit",
    "strategy": "volatility_breakout",
    "strategy_params": {"k": 0.5, "use_ma_filter": true, "interval": "1d"},
    "initial_capital": 1000000
  }'
```

반환 통계: 총 수익률 · 승률 · 최대 낙폭(MDD) · Profit Factor · 평균 수익/손실

---

## 리스크 관리

```yaml
risk:
  max_loss_pct: 3.0       # 종목당 손절 기준 (%)
  take_profit_pct: 5.0    # 익절 기준 (%)
  max_positions: 5        # 최대 동시 보유 종목
  daily_loss_limit: 2.0   # 일일 손실 한도 (초과 시 신규 주문 차단)
```

손절/익절은 전략 신호보다 **먼저** 체크되어 자동 실행됩니다.

---

## REST API 엔드포인트

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

## 주의사항

1. **반드시 모의투자(PAPER 모드)로 먼저 테스트**
   - `config.yaml`의 `mode: "paper"` 유지

2. **실거래 전환 시** (`mode: "live"`)
   - 소액으로 시작, `daily_loss_limit` 낮게 설정

3. **API 키 보안**
   - `config.yaml`은 절대 git에 올리지 마세요
   - `.gitignore`에 `config.yaml` 추가 필수

---

## API 키 발급

| 서비스 | 발급 경로 |
|--------|----------|
| **업비트** | upbit.com → 마이페이지 → Open API 관리 |
| **한국투자증권** | apiportal.koreainvestment.com → 앱 등록 |
| **바이낸스** | binance.com → API Management (테스트넷: testnet.binance.vision) |
| **Anthropic (AI)** | console.anthropic.com → API Keys |
| **Discord** | 채널 설정 → 연동 → 웹후크 → 새 웹후크 |
| **카카오** | developers.kakao.com → 나에게 보내기 |
