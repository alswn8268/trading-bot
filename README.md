# 🤖 자동 매매봇

국내 주식(한국투자증권) + 암호화폐(업비트/바이낸스) 자동 매매봇
실시간 웹 대시보드 포함

---

## 📁 파일 구조

```
trading_bot/
├── main.py               # FastAPI 서버 (웹 대시보드 + WebSocket)
├── bot.py                # 봇 핵심 엔진
├── config.yaml           # ⚠️ API 키 및 설정 (이 파일만 수정하면 됨)
├── requirements.txt      # 의존성 패키지
├── exchanges/
│   ├── kis.py            # 한국투자증권 KIS API
│   ├── upbit.py          # 업비트 API
│   └── binance_ex.py     # 바이낸스 API
├── strategies/
│   ├── ma_crossover.py   # 이동평균 골든/데드크로스
│   ├── rsi_strategy.py   # RSI 과매수/과매도
│   └── bollinger.py      # 볼린저 밴드
└── dashboard/
    └── index.html        # 웹 대시보드 UI
```

---

## 🚀 설치 및 실행

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. API 키 설정
`config.yaml`을 열고 API 키를 입력하세요:

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

### 3. 봇 실행
```bash
python main.py
# 또는
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. 대시보드 접속
브라우저에서 `http://localhost:8000` 접속

---

## ⚙️ 전략 설명

| 전략 | 키워드 | 설명 |
|------|--------|------|
| **이동평균 크로스** | `ma_crossover` | 단기 MA가 장기 MA를 상향 돌파 시 매수 (골든크로스) |
| **RSI** | `rsi` | RSI 30 이하 과매도 구간 매수, 70 이상 과매수 구간 매도 |
| **볼린저 밴드** | `bollinger` | 하단 밴드 터치 시 매수, 상단 밴드 터치 시 매도 |

---

## 🛡️ 리스크 관리

`config.yaml`의 `risk` 섹션:

```yaml
risk:
  max_loss_pct: 3.0       # 종목당 손절 기준 (%)
  take_profit_pct: 5.0    # 익절 기준 (%)
  max_positions: 5        # 최대 동시 보유 종목
  daily_loss_limit: 2.0   # 일일 손실 한도 (초과 시 봇 자동 중단)
```

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
   - `config.yaml`을 git에 올리지 마세요
   - `.gitignore`에 추가 필수

---

## 🔑 API 키 발급 방법

### 한국투자증권 KIS
1. https://apiportal.koreainvestment.com 접속
2. 회원가입 후 앱 등록
3. 모의투자: `https://openapivts.koreainvestment.com:29443`

### 업비트
1. https://upbit.com → 마이페이지 → Open API 관리
2. 주문/잔고 권한 체크 후 발급

### 바이낸스
1. https://testnet.binance.vision (테스트넷)
2. https://www.binance.com → API Management (실거래)
