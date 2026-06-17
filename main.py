from http.server import HTTPServer, BaseHTTPRequestHandler
import os, requests, json, time
from datetime import datetime, timedelta
import threading

# 환경변수
CLIENT_ID     = os.environ.get("TOSS_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("TOSS_CLIENT_SECRET", "")
ACCOUNT       = os.environ.get("TOSS_ACCOUNT", "")

# 종목 코드
KODEX_LEV  = "122630"  # KODEX 레버리지 (신호용)
HYNIX_LEV  = "0193T0" # KODEX SK하이닉스단일종목레버리지 (매수용)

# 전략 설정
LEV_GAP_THRESHOLD = 1.0   # 레버리지 갭 +1% 이상이면 매수
MONTHLY_ADD       = 300000 # 매달 16일 30만원 추가
MONTHLY_ADD_DAY   = 16     # 추가 투입일

# 토스증권 API
TOSS_BASE = "https://openapi.tossinvest.com"

_token = None
_token_expires = 0

def get_token():
    global _token, _token_expires
    if _token and time.time() < _token_expires:
        return _token
    r = requests.post(f"{TOSS_BASE}/api/v2/oauth2/token", json={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    })
    data = r.json()
    _token = data.get("access_token")
    _token_expires = time.time() + data.get("expires_in", 3600) - 60
    return _token

def auth_headers():
    return {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json"
    }

def acct_headers():
    return {**auth_headers(), "X-Tossinvest-Account": ACCOUNT}

def get_price(code):
    r = requests.get(f"{TOSS_BASE}/api/v2/quotes/price",
                     params={"symbol": code}, headers=auth_headers())
    return r.json()

def get_prev_close(code):
    r = requests.get(f"{TOSS_BASE}/api/v2/quotes/candles/days",
                     params={"symbol": code, "count": 2}, headers=auth_headers())
    candles = r.json().get("candles", [])
    if len(candles) >= 2:
        return float(candles[-2].get("closePrice", 0))
    return 0

def get_balance():
    r = requests.get(f"{TOSS_BASE}/api/v2/accounts/balance", headers=acct_headers())
    return r.json()

def get_positions():
    r = requests.get(f"{TOSS_BASE}/api/v2/accounts/positions", headers=acct_headers())
    return r.json()

def buy_market(code, amount):
    price_data = get_price(code)
    current_price = float(price_data.get("price", 0))
    if current_price <= 0:
        return {"error": "현재가 조회 실패"}
    qty = int(amount / current_price)
    if qty <= 0:
        return {"error": "수량 부족"}
    r = requests.post(f"{TOSS_BASE}/api/v2/orders", json={
        "symbol": code,
        "side": "BUY",
        "orderType": "MARKET",
        "quantity": qty
    }, headers=acct_headers())
    return r.json()

def sell_all(code):
    positions = get_positions()
    qty = 0
    for p in positions.get("positions", []):
        if p.get("symbol") == code:
            qty = int(p.get("quantity", 0))
            break
    if qty <= 0:
        return {"error": "보유 수량 없음"}
    r = requests.post(f"{TOSS_BASE}/api/v2/orders", json={
        "symbol": code,
        "side": "SELL",
        "orderType": "MARKET",
        "quantity": qty
    }, headers=acct_headers())
    return r.json()

def get_kospi_ma60():
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11",
            params={"interval": "1d", "range": "90d"},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
        )
        closes = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c]
        if len(closes) >= 60:
            ma60 = sum(closes[-60:]) / 60
            return closes[-1], ma60
    except:
        pass
    return None, None

trade_log = []

def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{now}] {msg}"
    print(entry)
    trade_log.append(entry)
    if len(trade_log) > 200:
        trade_log.pop(0)

def check_and_trade():
    log("=== 매수 조건 확인 시작 ===")

    # 코스피 MA60 확인
    kp_current, kp_ma60 = get_kospi_ma60()
    if kp_current and kp_ma60:
        if kp_current < kp_ma60:
            log(f"🔴 코스피 MA60 아래 ({kp_current:.0f} < {kp_ma60:.0f}) → 패스")
            return
        log(f"✅ 코스피 MA60 위 ({kp_current:.0f} > {kp_ma60:.0f})")

    # 레버리지 갭 확인
    prev_close = get_prev_close(KODEX_LEV)
    current    = get_price(KODEX_LEV)
    open_price = float(current.get("openPrice", 0))

    if prev_close <= 0 or open_price <= 0:
        log("❌ 레버리지 가격 조회 실패 → 패스")
        return

    gap = (open_price - prev_close) / prev_close * 100
    log(f"레버리지 갭: {gap:+.2f}%")

    if gap < LEV_GAP_THRESHOLD:
        log(f"🔵 갭 {gap:+.1f}% < {LEV_GAP_THRESHOLD}% → 패스")
        return

    log(f"🟢 갭 {gap:+.1f}% ≥ {LEV_GAP_THRESHOLD}% → 매수")

    balance = get_balance()
    cash = float(balance.get("availableCash", 0))
    log(f"가용 현금: {cash:,.0f}원")

    if cash < 10000:
        log("❌ 잔고 부족")
        return

    result = buy_market(HYNIX_LEV, cash)
    log(f"✅ 매수 완료: {result}")

def sell_position():
    log("=== 3:20 전량 매도 ===")
    result = sell_all(HYNIX_LEV)
    log(f"매도 결과: {result}")

def scheduler():
    while True:
        now = datetime.now()
        h, m, d = now.hour, now.minute, now.day

        if h == 9 and m == 5:
            try: check_and_trade()
            except Exception as e: log(f"❌ 매수 오류: {e}")
            time.sleep(60)

        elif h == 15 and m == 20:
            try: sell_position()
            except Exception as e: log(f"❌ 매도 오류: {e}")
            time.sleep(60)

        elif d == MONTHLY_ADD_DAY and h == 9 and m == 0:
            log(f"💰 오늘 월급날! 토스증권 계좌에 {MONTHLY_ADD:,}원 입금하세요!")
            time.sleep(60)

        else:
            time.sleep(30)

threading.Thread(target=scheduler, daemon=True).start()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_str = "\n".join(trade_log[-50:]) if trade_log else "아직 거래 없음"
        html = f"""<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<title>80억 프로젝트</title>
<style>
body{{font-family:sans-serif;background:#0a0d14;color:#e2e8f0;padding:20px}}
h1{{color:#6366f1}}
.card{{background:#0f1520;border:1px solid #1e2535;border-radius:8px;padding:15px;margin:10px 0}}
pre{{font-size:12px;white-space:pre-wrap;color:#94a3b8}}
</style></head><body>
<h1>🚀 80억 프로젝트 — 자동매매</h1>
<div class="card">
  <b>현재 시간:</b> {now}<br><br>
  <b>전략:</b> 레버리지 갭 +1% 이상 → 하이닉스단일레버 매수<br>
  <b>매수:</b> 매일 오전 9:05 자동<br>
  <b>매도:</b> 매일 오후 3:20 자동<br>
  <b>추가투입:</b> 매달 16일 알림<br>
  <b>코스피 필터:</b> MA60 위에 있을 때만 매수
</div>
<div class="card">
  <b>📋 거래 로그</b>
  <pre>{log_str}</pre>
</div>
</body></html>"""
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

port = int(os.environ.get("PORT", 10000))
log(f"🚀 80억 프로젝트 서버 시작 (포트:{port})")
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
