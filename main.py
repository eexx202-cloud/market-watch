from http.server import HTTPServer, BaseHTTPRequestHandler
mport requests
import json
import threading
import time
import csv
import uuid
import html
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import pytz


# ============================================================
# 설정
# ============================================================

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]

KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "")
APP_URL = os.environ.get("APP_URL", "")  # 예: https://xxxx.onrender.com
PORT = int(os.environ.get("PORT", 10000))

BASE = "https://openapi.tossinvest.com"
KST = pytz.timezone("Asia/Seoul")

CSV_PATH = os.environ.get("CSV_PATH", "data.csv")

# 기본 추천 비중
MAX_BUY_RATIO = float(os.environ.get("MAX_BUY_RATIO", "0.7"))  # 최대 70%
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))  # 5분


# ============================================================
# 감시 종목
# ============================================================

MAIN = {
    "0193T0": "하이닉스 레버리지",
    "0197X0": "하이닉스 인버스",
    "000660": "SK하이닉스",
}

WATCH = {
    "0193W0": "삼성전자 레버리지",
    "0193L0": "삼성전자 인버스",
    "005930": "삼성전자",

    "122630": "KODEX 레버리지",
    "252670": "KODEX 인버스2X",
    "069500": "KODEX 200",

    "233740": "코스닥150 레버리지",
    "251340": "코스닥150 인버스",
    "229200": "KODEX 코스닥150",

    "494310": "반도체 레버리지",
    "488080": "TIGER 반도체TOP10",
    "469150": "AI반도체",

    "0100K0": "방산 레버리지",
    "0080Y0": "조선 레버리지",
    "462330": "2차전지 레버리지",

    "0177X0": "로봇 휴머노이드",
    "445290": "로봇액티브",
    "433500": "원자력",
    "487240": "AI전력인프라",

    "418660": "나스닥100 레버리지",
    "465610": "미국빅테크TOP7",
    "225040": "S&P500 레버리지",
}

ALL = {**MAIN, **WATCH}

TRADE_SYMBOLS = ["0193T0", "0197X0"]


# ============================================================
# 상태
# ============================================================

S = {
    "token": None,
    "token_exp": 0,
    "account_seq": None,

    "status": "시작 중",
    "updated": "없음",

    "prices": {},
    "prev_prices": {},
    "high": {},
    "low": {},

    "candles": {},
    "wma": {},
    "scores": {},
    "signals": {},

    "cash": 0,
    "total_value": 0,
    "profit_loss": 0,
    "profit_rate": 0,
    "holdings": [],
    "sellable": {},

    "alerts": [],
    "last_alert": {},

    "orders": [],
}


# ============================================================
# 유틸
# ============================================================

def now_kst():
    return datetime.now(KST)


def now_text():
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")


def to_float(v, default=0.0):
    try:
        if v is None:
            return default
        return float(str(v).replace(",", ""))
    except Exception:
        return default


def to_int(v, default=0):
    try:
        return int(float(str(v).replace(",", "")))
    except Exception:
        return default


def fmt_won(v):
    try:
        return f"{int(float(v)):,}원"
    except Exception:
        return "-"


def safe(v):
    return html.escape(str(v))


def is_market_time():
    n = now_kst()
    return (n.hour > 8 and n.hour < 16)


def init_csv():
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([
                "time",
                "symbol",
                "name",
                "price",
                "high",
                "low",
                "wma5",
                "wma20",
                "wma60",
                "score",
                "signal",
            ])


def append_csv(sym):
    try:
        name = ALL.get(sym, sym)
        price = S["prices"].get(sym, 0)
        high = S["high"].get(sym, price)
        low = S["low"].get(sym, price)
        wma = S["wma"].get(sym, {})
        score = S["scores"].get(sym, 0)
        signal = S["signals"].get(sym, {}).get("label", "")

        with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([
                now_text(),
                sym,
                name,
                price,
                high,
                low,
                wma.get("wma5", 0),
                wma.get("wma20", 0),
                wma.get("wma60", 0),
                score,
                signal,
            ])
    except Exception as e:
        print("CSV 저장 오류:", e)


# ============================================================
# 토스 API
# ============================================================

def get_token():
    try:
        r = requests.post(
            BASE + "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            timeout=10,
        )

        data = r.json()

        if r.status_code != 200:
            S["status"] = "토큰 오류: " + str(data)
            print("토큰 오류:", data)
            return None

        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))

        S["token"] = token
        S["token_exp"] = time.time() + max(60, expires_in - 300)
        S["status"] = "토큰 정상"

        print("토큰 발급 성공")
        return token

    except Exception as e:
        S["status"] = "토큰 예외: " + str(e)
        print("토큰 예외:", e)
        return None


def ensure_token():
    if not S["token"] or time.time() >= S["token_exp"]:
        return get_token()
    return S["token"]


def auth_headers():
    token = ensure_token()
    return {
        "Authorization": "Bearer " + str(token)
    }


def account_headers():
    h = auth_headers()
    if S["account_seq"] is not None:
        h["X-Tossinvest-Account"] = str(S["account_seq"])
    return h


def api_get(path, params=None, account=False, timeout=10):
    headers = account_headers() if account else auth_headers()
    r = requests.get(BASE + path, headers=headers, params=params or {}, timeout=timeout)

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.status_code >= 400:
        print("GET 오류", path, r.status_code, data)

    return r.status_code, data


def api_post(path, body=None, account=False, timeout=10):
    headers = account_headers() if account else auth_headers()
    headers["Content-Type"] = "application/json"

    r = requests.post(BASE + path, headers=headers, json=body or {}, timeout=timeout)

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.status_code >= 400:
        print("POST 오류", path, r.status_code, data)

    return r.status_code, data


# ============================================================
# 계좌 / 자산
# ============================================================

def load_account_seq():
    code, data = api_get("/api/v1/accounts")

    if code != 200:
        S["status"] = "계좌 조회 오류"
        return False

    accounts = data.get("result", [])
    if not accounts:
        S["status"] = "계좌 없음"
        return False

    S["account_seq"] = accounts[0].get("accountSeq")
    print("계좌 선택:", S["account_seq"])
    return True


def load_buying_power():
    code, data = api_get(
        "/api/v1/buying-power",
        params={"currency": "KRW"},
        account=True,
    )

    if code != 200:
        return False

    result = data.get("result", {})
    S["cash"] = to_int(result.get("cashBuyingPower", 0))
    return True


def load_holdings():
    code, data = api_get("/api/v1/holdings", account=True)

    if code != 200:
        return False

    result = data.get("result", {})

    market_value = result.get("marketValue", {})
    profit_loss = result.get("profitLoss", {})

    total_market = to_float(market_value.get("amount", {}).get("krw", 0))
    pl_amount = to_float(profit_loss.get("amount", {}).get("krw", 0))
    pl_rate = to_float(profit_loss.get("rate", 0)) * 100

    holdings = []

    for item in result.get("items", []):
        sym = item.get("symbol", "")
        name = item.get("name", sym)

        qty = to_float(item.get("quantity", 0))
        last_price = to_float(item.get("lastPrice", 0))
        avg = to_float(item.get("averagePurchasePrice", 0))

        mv = item.get("marketValue", {})
        pl = item.get("profitLoss", {})

        value = to_float(mv.get("amount", 0))
        pl_amt = to_float(pl.get("amount", 0))
        pl_r = to_float(pl.get("rate", 0)) * 100

        holdings.append({
            "symbol": sym,
            "name": name,
            "qty": qty,
            "last_price": last_price,
            "avg": avg,
            "value": value,
            "pl_amt": pl_amt,
            "pl_rate": pl_r,
        })

    S["holdings"] = holdings
    S["profit_loss"] = int(pl_amount)
    S["profit_rate"] = round(pl_rate, 2)
    S["total_value"] = int(S["cash"] + total_market)

    return True


def load_sellable_quantities():
    for sym in TRADE_SYMBOLS:
        code, data = api_get(
            "/api/v1/sellable-quantity",
            params={"symbol": sym},
            account=True,
        )

        if code == 200:
            result = data.get("result", {})
            S["sellable"][sym] = to_float(result.get("sellableQuantity", 0))
        else:
            S["sellable"][sym] = 0


def refresh_account_all():
    if S["account_seq"] is None:
        load_account_seq()

    if S["account_seq"] is not None:
        load_buying_power()
        load_holdings()
        load_sellable_quantities()


# ============================================================
# 현재가 / 캔들 / WMA
# ============================================================

def load_prices():
    try:
        symbols = ",".join(ALL.keys())

        code, data = api_get(
            "/api/v1/prices",
            params={"symbols": symbols},
            timeout=15,
        )

        if code != 200:
            S["status"] = "현재가 오류"
            return False

        cnt = 0

        for item in data.get("result", []):
            sym = item.get("symbol", "")
            price = to_float(item.get("lastPrice", 0))

            if not sym or price <= 0:
                continue

            old = S["prices"].get(sym, price)

            S["prev_prices"][sym] = old
            S["prices"][sym] = price

            if sym not in S["high"]:
                S["high"][sym] = price
                S["low"][sym] = price
            else:
                S["high"][sym] = max(S["high"][sym], price)
                S["low"][sym] = min(S["low"][sym], price)

            cnt += 1

        S["updated"] = now_kst().strftime("%H:%M:%S")
        S["status"] = f"정상 ({cnt}/{len(ALL)})"

        return True

    except Exception as e:
        S["status"] = "현재가 예외: " + str(e)
        print("현재가 예외:", e)
        return False


def load_candles(sym, count=120):
    code, data = api_get(
        "/api/v1/candles",
        params={
            "symbol": sym,
            "interval": "1m",
            "count": min(count, 200),
            "adjusted": "true",
        },
        timeout=10,
    )

    if code != 200:
        return False

    result = data.get("result", {})
    candles = result.get("candles", [])

    parsed = []
    for c in candles:
        parsed.append({
            "timestamp": c.get("timestamp"),
            "open": to_float(c.get("openPrice")),
            "high": to_float(c.get("highPrice")),
            "low": to_float(c.get("lowPrice")),
            "close": to_float(c.get("closePrice")),
            "volume": to_float(c.get("volume")),
        })

    # 시간 오름차순
    parsed.sort(key=lambda x: x["timestamp"] or "")

    S["candles"][sym] = parsed
    calc_wma(sym)

    return True


def wma(values, n):
    if len(values) < n:
        return 0

    recent = values[-n:]
    weights = list(range(1, n + 1))
    return sum(v * w for v, w in zip(recent, weights)) / sum(weights)


def calc_wma(sym):
    candles = S["candles"].get(sym, [])
    closes = [c["close"] for c in candles if c["close"] > 0]

    if not closes:
        S["wma"][sym] = {
            "wma5": 0,
            "wma20": 0,
            "wma60": 0,
            "volume_ratio": 1,
        }
        return

    vols = [c["volume"] for c in candles if c["volume"] >= 0]

    v_recent = vols[-1] if vols else 0
    v_avg20 = sum(vols[-20:]) / len(vols[-20:]) if len(vols) >= 1 else 0
    volume_ratio = (v_recent / v_avg20) if v_avg20 > 0 else 1

    S["wma"][sym] = {
        "wma5": round(wma(closes, 5), 2),
        "wma20": round(wma(closes, 20), 2),
        "wma60": round(wma(closes, 60), 2),
        "volume_ratio": round(volume_ratio, 2),
    }


def refresh_candles_main():
    for sym in ["0193T0", "0197X0", "000660"]:
        load_candles(sym)


# ============================================================
# AI 점수
# ============================================================

def price_change_pct(sym):
    p = S["prices"].get(sym, 0)
    prev = S["prev_prices"].get(sym, p)
    if prev <= 0:
        return 0
    return (p - prev) / prev * 100


def high_drop_pct(sym):
    p = S["prices"].get(sym, 0)
    h = S["high"].get(sym, p)
    if h <= 0:
        return 0
    return (p - h) / h * 100


def low_rise_pct(sym):
    p = S["prices"].get(sym, 0)
    l = S["low"].get(sym, p)
    if l <= 0:
        return 0
    return (p - l) / l * 100


def calc_symbol_score(sym):
    price = S["prices"].get(sym, 0)
    if price <= 0:
        return 0

    wm = S["wma"].get(sym, {})
    w5 = wm.get("wma5", 0)
    w20 = wm.get("wma20", 0)
    w60 = wm.get("wma60", 0)
    vr = wm.get("volume_ratio", 1)

    chg = price_change_pct(sym)
    hdrop = high_drop_pct(sym)
    lrise = low_rise_pct(sym)

    score = 50

    # 현재가와 WMA 위치
    if w5 > 0 and price > w5:
        score += 12
    elif w5 > 0 and price < w5:
        score -= 12

    if w5 > 0 and w20 > 0 and w5 > w20:
        score += 14
    elif w5 > 0 and w20 > 0 and w5 < w20:
        score -= 14

    if w20 > 0 and w60 > 0 and w20 > w60:
        score += 8
    elif w20 > 0 and w60 > 0 and w20 < w60:
        score -= 8

    # 직전 가격 변화
    if chg > 0:
        score += 8
    elif chg < 0:
        score -= 8

    # 거래량
    if vr >= 1.5 and chg > 0:
        score += 8
    elif vr >= 1.5 and chg < 0:
        score -= 8

    # 고점 대비
    if hdrop <= -5:
        score -= 15
    elif hdrop <= -3:
        score -= 8

    # 저점 대비 반등
    if lrise >= 3 and chg > 0:
        score += 8

    return max(0, min(100, int(score)))


def calc_scores():
    lev = "0193T0"
    inv = "0197X0"
    hynix = "000660"

    lev_score = calc_symbol_score(lev)
    inv_score = calc_symbol_score(inv)

    # 원주 방향 보정
    hynix_chg = price_change_pct(hynix)

    if hynix_chg > 0:
        lev_score += 8
        inv_score -= 8
    elif hynix_chg < 0:
        lev_score -= 8
        inv_score += 8

    S["scores"][lev] = max(0, min(100, int(lev_score)))
    S["scores"][inv] = max(0, min(100, int(inv_score)))

    build_signals()


def signal_from_score(sym):
    score = S["scores"].get(sym, 0)
    hdrop = high_drop_pct(sym)

    if score >= 75:
        return "진입 ⭕"
    if score >= 60:
        return "보유/관찰 🟡"
    if score >= 40:
        return "관망 🔴"

    if hdrop <= -3:
        return "매도 후보 ⛔"

    return "약함 🔴"


def recommend_ratio(score):
    if score >= 85:
        return 0.70
    if score >= 75:
        return 0.50
    if score >= 65:
        return 0.30
    return 0.0


def recommend_qty(sym):
    price = S["prices"].get(sym, 0)
    if price <= 0:
        return 0

    score = S["scores"].get(sym, 0)
    ratio = min(MAX_BUY_RATIO, recommend_ratio(score))

    amount = S["cash"] * ratio
    qty = int(amount // price)

    return max(0, qty)


def build_signals():
    for sym in TRADE_SYMBOLS:
        score = S["scores"].get(sym, 0)
        ratio = recommend_ratio(score)
        qty = recommend_qty(sym)

        S["signals"][sym] = {
            "label": signal_from_score(sym),
            "score": score,
            "ratio": ratio,
            "qty": qty,
            "hdrop": round(high_drop_pct(sym), 2),
            "lrise": round(low_rise_pct(sym), 2),
            "chg": round(price_change_pct(sym), 2),
        }


# ============================================================
# 카카오 알림
# ============================================================

def send_kakao(msg, link_url=None):
    print("[카카오]", msg)

    S["alerts"].insert(0, {
        "time": now_kst().strftime("%H:%M:%S"),
        "msg": msg,
    })
    S["alerts"] = S["alerts"][:50]

    if not KAKAO_TOKEN:
        return

    if not link_url:
        link_url = APP_URL or "https://developers.tossinvest.com/docs"

    template = {
        "object_type": "text",
        "text": msg,
        "link": {
            "web_url": link_url,
            "mobile_web_url": link_url,
        },
    }

    try:
        r = requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": "Bearer " + KAKAO_TOKEN},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=5,
        )

        if r.status_code >= 400:
            print("카카오 오류:", r.status_code, r.text)

    except Exception as e:
        print("카카오 예외:", e)


def maybe_alert():
    if not is_market_time():
        return

    lev = "0193T0"
    inv = "0197X0"

    lev_sig = S["signals"].get(lev, {})
    inv_sig = S["signals"].get(inv, {})

    lev_score = lev_sig.get("score", 0)
    inv_score = inv_sig.get("score", 0)

    # 레버리지 강한 진입
    if lev_score >= 75 and lev_score >= inv_score + 15:
        alert_key = "LEV_ENTRY"
        msg = make_signal_message(lev, "🟢 레버리지 진입 후보")
        send_alert_once(alert_key, msg)

    # 인버스 강한 후보
    if inv_score >= 75 and inv_score >= lev_score + 15:
        alert_key = "INV_ENTRY"
        msg = make_signal_message(inv, "🔵 인버스 진입 후보")
        send_alert_once(alert_key, msg)

    # 레버리지 매도 후보
    if lev_score <= 40 and high_drop_pct(lev) <= -3:
        alert_key = "LEV_SELL"
        msg = make_signal_message(lev, "⛔ 레버리지 매도 후보")
        send_alert_once(alert_key, msg)


def send_alert_once(key, msg):
    last = S["last_alert"].get(key, 0)
    if time.time() - last < ALERT_COOLDOWN_SEC:
        return

    S["last_alert"][key] = time.time()
    send_kakao(msg, APP_URL)


def make_signal_message(sym, title):
    name = ALL.get(sym, sym)
    price = S["prices"].get(sym, 0)
    sig = S["signals"].get(sym, {})
    wm = S["wma"].get(sym, {})

    qty = sig.get("qty", 0)
    ratio = int(sig.get("ratio", 0) * 100)

    return (
        f"{title}\n"
        f"{name}\n"
        f"현재가: {fmt_won(price)}\n"
        f"AI 점수: {sig.get('score', 0)}\n"
        f"신호: {sig.get('label', '-')}\n"
        f"추천비중: {ratio}%\n"
        f"추천수량: {qty}주\n"
        f"고점대비: {sig.get('hdrop', 0)}%\n"
        f"WMA5: {fmt_won(wm.get('wma5', 0))}\n"
        f"WMA20: {fmt_won(wm.get('wma20', 0))}\n"
        f"WMA60: {fmt_won(wm.get('wma60', 0))}\n"
        f"\n최종 결정은 직접 버튼 클릭"
    )


# ============================================================
# 반자동 주문 버튼
# ============================================================

def place_order_manual(sym, side, qty):
    """
    반자동 주문.
    AI가 자동 실행하지 않음.
    사용자가 대시보드 버튼을 직접 눌렀을 때만 실행.
    """

    qty = int(qty)
    if qty <= 0:
        return {
            "ok": False,
            "message": "수량이 0입니다.",
        }

    client_order_id = f"semi-{sym}-{side}-{now_kst().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    body = {
        "clientOrderId": client_order_id,
        "symbol": sym,
        "side": side,
        "orderType": "MARKET",
        "quantity": str(qty),
    }

    code, data = api_post(
        "/api/v1/orders",
        body=body,
        account=True,
        timeout=10,
    )

    name = ALL.get(sym, sym)
    side_kr = "매수" if side == "BUY" else "매도"

    S["orders"].insert(0, {
        "time": now_kst().strftime("%H:%M:%S"),
        "symbol": sym,
        "name": name,
        "side": side_kr,
        "qty": qty,
        "status": "성공" if code == 200 else "실패",
        "response": data,
    })
    S["orders"] = S["orders"][:30]

    if code == 200:
        send_kakao(
            f"✅ 반자동 {side_kr} 주문 전송\n"
            f"{name}\n"
            f"수량: {qty}주\n"
            f"clientOrderId: {client_order_id}"
        )
        refresh_account_all()
        return {"ok": True, "data": data}

    send_kakao(
        f"⚠️ 반자동 {side_kr} 주문 실패\n"
        f"{name}\n"
        f"수량: {qty}주\n"
        f"응답: {json.dumps(data, ensure_ascii=False)[:500]}"
    )
    return {"ok": False, "data": data}


# ============================================================
# 메인 루프
# ============================================================

def loop():
    init_csv()
    get_token()
    refresh_account_all()

    counter = 0

    while True:
        try:
            n = now_kst()

            # 09:00 장 시작 초기화
            if n.hour == 9 and n.minute == 0:
                S["high"] = {}
                S["low"] = {}
                S["last_alert"] = {}
                send_kakao("🔔 장 시작\n반자동 관제센터 감시 시작", APP_URL)

            # 장중 가격 / 캔들 / 점수
            if 8 <= n.hour < 16:
                load_prices()

                # 캔들은 너무 자주 때리지 않게 2분마다
                if counter % 2 == 0:
                    refresh_candles_main()

                calc_scores()

                for sym in TRADE_SYMBOLS:
                    append_csv(sym)

                maybe_alert()

            # 계좌는 5분마다
            if counter % 5 == 0:
                refresh_account_all()

            # 토큰은 만료 전 자동 갱신
            ensure_token()

            counter += 1
            time.sleep(60)

        except Exception as e:
            print("루프 오류:", e)
            S["status"] = "루프 오류: " + str(e)
            time.sleep(60)


# ============================================================
# 웹 대시보드
# ============================================================

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api":
            self.json_response({
                "status": S["status"],
                "updated": S["updated"],
                "cash": S["cash"],
                "total_value": S["total_value"],
                "profit_loss": S["profit_loss"],
                "profit_rate": S["profit_rate"],
                "prices": S["prices"],
                "wma": S["wma"],
                "scores": S["scores"],
                "signals": S["signals"],
                "holdings": S["holdings"],
                "sellable": S["sellable"],
            })
            return

        if path == "/refresh":
            load_prices()
            refresh_candles_main()
            calc_scores()
            refresh_account_all()
            self.redirect("/")
            return

        if path == "/test_kakao":
            send_kakao("✅ 카카오 알림 테스트 성공\n" + now_text(), APP_URL)
            self.html_response("<h2>카카오 테스트 전송 완료</h2><a href='/'>돌아가기</a>")
            return

        if path == "/download_csv":
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=data.csv")
            self.end_headers()

            if os.path.exists(CSV_PATH):
                with open(CSV_PATH, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write("no data".encode("utf-8"))
            return

        self.render_dashboard()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""

        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}

        if path == "/order":
            sym = body.get("symbol")
            side = body.get("side")
            qty = to_int(body.get("qty", 0))

            if sym not in TRADE_SYMBOLS:
                self.json_response({"ok": False, "message": "허용되지 않은 종목"})
                return

            if side not in ["BUY", "SELL"]:
                self.json_response({"ok": False, "message": "BUY 또는 SELL만 가능"})
                return

            result = place_order_manual(sym, side, qty)
            self.json_response(result)
            return

        self.json_response({"ok": False, "message": "unknown path"})

    def render_dashboard(self):
        lev = "0193T0"
        inv = "0197X0"
        hynix = "000660"

        lev_card = self.signal_card(lev, "red")
        inv_card = self.signal_card(inv, "blue")
        hynix_card = self.basic_card(hynix)

        holdings_rows = self.holdings_rows()
        stock_rows = self.stock_rows()
        alert_rows = self.alert_rows()
        order_rows = self.order_rows()

        html_doc = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>80억 프로젝트 반자동 관제센터</title>
<meta http-equiv="refresh" content="60">
<style>
* {{
    box-sizing: border-box;
}}
body {{
    margin: 0;
    padding: 10px;
    background: #05060a;
    color: #f3f4f8;
    font-family: Arial, sans-serif;
    font-size: 13px;
}}
h1 {{
    margin: 6px 0 2px;
    text-align: center;
    color: #ffffff;
    font-size: 22px;
}}
.sub {{
    text-align: center;
    color: #777;
    font-size: 11px;
    margin-bottom: 10px;
}}
.grid {{
    display: grid;
    grid-template-columns: 1.1fr 1.5fr 1fr;
    gap: 10px;
}}
.card {{
    background: #11131c;
    border: 1px solid #222635;
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 10px;
}}
.card h2 {{
    margin: 0 0 8px;
    font-size: 15px;
    color: #aaa;
}}
.big {{
    font-size: 25px;
    font-weight: bold;
}}
.mid {{
    font-size: 18px;
    font-weight: bold;
}}
.small {{
    font-size: 11px;
    color: #888;
}}
.red {{
    color: #ff4d4d;
}}
.blue {{
    color: #4d8cff;
}}
.green {{
    color: #4dff88;
}}
.yellow {{
    color: #ffd84d;
}}
.gray {{
    color: #888;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}}
th {{
    text-align: left;
    color: #888;
    background: #161927;
    padding: 6px;
    border-bottom: 1px solid #252a3a;
}}
td {{
    padding: 6px;
    border-bottom: 1px solid #1d2030;
}}
button {{
    border: none;
    border-radius: 7px;
    padding: 8px 12px;
    margin: 3px;
    font-weight: bold;
    cursor: pointer;
}}
.buy {{
    background: #d71920;
    color: white;
}}
.sell {{
    background: #1f64ff;
    color: white;
}}
.graybtn {{
    background: #333;
    color: white;
}}
.gold {{
    background: #ffd84d;
    color: black;
}}
input {{
    background: #05060a;
    color: white;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 7px;
    width: 80px;
}}
.section {{
    margin-top: 8px;
}}
.progress {{
    width: 100%;
    height: 8px;
    background: #222;
    border-radius: 10px;
    overflow: hidden;
    margin: 6px 0;
}}
.bar {{
    height: 100%;
    background: #ffd84d;
}}
@media (max-width: 900px) {{
    .grid {{
        grid-template-columns: 1fr;
    }}
}}
</style>
</head>
<body>

<h1>80억 프로젝트 반자동 관제센터</h1>
<div class="sub">
    업데이트 {safe(S["updated"])} | 상태 {safe(S["status"])} | 계좌 {safe(S["account_seq"])}
</div>

<div class="grid">

    <div>
        <div class="card">
            <h2>계좌</h2>
            <div class="small">총자산</div>
            <div class="big yellow">{fmt_won(S["total_value"])}</div>
            <br>
            <div class="small">매수가능금액</div>
            <div class="mid">{fmt_won(S["cash"])}</div>
            <br>
            <div class="small">평가손익</div>
            <div class="mid {'red' if S["profit_loss"] >= 0 else 'blue'}">{fmt_won(S["profit_loss"])}</div>
            <div class="{'red' if S["profit_rate"] >= 0 else 'blue'}">{S["profit_rate"]}%</div>
            <br>
            <button class="graybtn" onclick="location.href='/refresh'">새로고침</button>
            <button class="graybtn" onclick="location.href='/test_kakao'">카카오 테스트</button>
            <button class="gold" onclick="location.href='/download_csv'">CSV 다운로드</button>
        </div>

        <div class="card">
            <h2>보유종목</h2>
            <table>
                <tr>
                    <th>종목</th>
                    <th>수량</th>
                    <th>현재가</th>
                    <th>수익률</th>
                </tr>
                {holdings_rows}
            </table>
        </div>
    </div>

    <div>
        {lev_card}
        {inv_card}
        {hynix_card}

        <div class="card">
            <h2>26종목 현황</h2>
            <table>
                <tr>
                    <th>종목</th>
                    <th>현재가</th>
                    <th>등락</th>
                    <th>고점대비</th>
                    <th>점수</th>
                </tr>
                {stock_rows}
            </table>
        </div>
    </div>

    <div>
        <div class="card">
            <h2>카카오 / 신호 기록</h2>
            <table>
                <tr>
                    <th>시간</th>
                    <th>내용</th>
                </tr>
                {alert_rows}
            </table>
        </div>

        <div class="card">
            <h2>반자동 주문 기록</h2>
            <table>
                <tr>
                    <th>시간</th>
                    <th>주문</th>
                    <th>결과</th>
                </tr>
                {order_rows}
            </table>
        </div>
    </div>

</div>

<script>
async function order(symbol, side, qtyId) {{
    const qty = document.getElementById(qtyId).value;
    const sideText = side === "BUY" ? "매수" : "매도";

    if (!qty || Number(qty) <= 0) {{
        alert("수량이 0입니다.");
        return;
    }}

    const ok = confirm(symbol + " " + qty + "주 " + sideText + " 주문을 전송할까요?");
    if (!ok) return;

    const res = await fetch("/order", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{
            symbol: symbol,
            side: side,
            qty: qty
        }})
    }});

    const data = await res.json();

    if (data.ok) {{
        alert("주문 전송 완료");
        location.reload();
    }} else {{
        alert("주문 실패: " + JSON.stringify(data));
    }}
}}

function setQty(id, qty) {{
    document.getElementById(id).value = qty;
}}
</script>

</body>
</html>
"""
        self.html_response(html_doc)

    def signal_card(self, sym, color):
        name = ALL.get(sym, sym)
        price = S["prices"].get(sym, 0)
        score = S["scores"].get(sym, 0)
        sig = S["signals"].get(sym, {})
        wm = S["wma"].get(sym, {})
        sellable = int(S["sellable"].get(sym, 0))

        rec_qty = int(sig.get("qty", 0))
        ratio = int(sig.get("ratio", 0) * 100)
        qty_id = f"qty_{sym}"

        return f"""
<div class="card">
    <h2>{safe(name)}</h2>
    <div class="big {color}">{fmt_won(price)}</div>
    <div class="small">신호</div>
    <div class="mid">{safe(sig.get("label", "-"))}</div>

    <div class="small">AI 점수 {score}</div>
    <div class="progress"><div class="bar" style="width:{score}%"></div></div>

    <table>
        <tr><td>WMA5</td><td>{fmt_won(wm.get("wma5", 0))}</td></tr>
        <tr><td>WMA20</td><td>{fmt_won(wm.get("wma20", 0))}</td></tr>
        <tr><td>WMA60</td><td>{fmt_won(wm.get("wma60", 0))}</td></tr>
        <tr><td>등락</td><td>{sig.get("chg", 0)}%</td></tr>
        <tr><td>고점대비</td><td>{sig.get("hdrop", 0)}%</td></tr>
        <tr><td>추천비중</td><td>{ratio}%</td></tr>
        <tr><td>추천수량</td><td>{rec_qty}주</td></tr>
        <tr><td>매도가능</td><td>{sellable}주</td></tr>
    </table>

    <div class="section">
        <input id="{qty_id}" type="number" value="{rec_qty}" min="0">
        <button class="buy" onclick="order('{sym}', 'BUY', '{qty_id}')">매수</button>
        <button class="sell" onclick="order('{sym}', 'SELL', '{qty_id}')">매도</button>
        <button class="graybtn" onclick="setQty('{qty_id}', {sellable})">전량</button>
    </div>
</div>
"""

    def basic_card(self, sym):
        name = ALL.get(sym, sym)
        price = S["prices"].get(sym, 0)
        chg = price_change_pct(sym)
        wm = S["wma"].get(sym, {})

        return f"""
<div class="card">
    <h2>{safe(name)}</h2>
    <div class="big">{fmt_won(price)}</div>
    <div class="small">등락 {round(chg, 2)}%</div>
    <table>
        <tr><td>WMA5</td><td>{fmt_won(wm.get("wma5", 0))}</td></tr>
        <tr><td>WMA20</td><td>{fmt_won(wm.get("wma20", 0))}</td></tr>
        <tr><td>WMA60</td><td>{fmt_won(wm.get("wma60", 0))}</td></tr>
    </table>
</div>
"""

    def holdings_rows(self):
        if not S["holdings"]:
            return "<tr><td colspan='4' class='gray'>보유 없음</td></tr>"

        rows = ""
        for h in S["holdings"]:
            color = "red" if h["pl_rate"] >= 0 else "blue"
            rows += f"""
<tr>
    <td>{safe(h["name"])}<br><span class="small">{safe(h["symbol"])}</span></td>
    <td>{int(h["qty"])}주</td>
    <td>{fmt_won(h["last_price"])}</td>
    <td class="{color}">{round(h["pl_rate"], 2)}%</td>
</tr>
"""
        return rows

    def stock_rows(self):
        rows = ""
        for sym, name in ALL.items():
            price = S["prices"].get(sym, 0)
            chg = price_change_pct(sym)
            hdrop = high_drop_pct(sym)
            score = S["scores"].get(sym, "")
            color = "red" if chg > 0 else "blue" if chg < 0 else "gray"

            rows += f"""
<tr>
    <td>{safe(name)}<br><span class="small">{safe(sym)}</span></td>
    <td>{fmt_won(price)}</td>
    <td class="{color}">{round(chg, 2)}%</td>
    <td>{round(hdrop, 2)}%</td>
    <td>{score}</td>
</tr>
"""
        return rows

    def alert_rows(self):
        if not S["alerts"]:
            return "<tr><td colspan='2' class='gray'>없음</td></tr>"

        rows = ""
        for a in S["alerts"][:15]:
            rows += f"""
<tr>
    <td class="small">{safe(a["time"])}</td>
    <td>{safe(a["msg"]).replace(chr(10), "<br>")}</td>
</tr>
"""
        return rows

    def order_rows(self):
        if not S["orders"]:
            return "<tr><td colspan='3' class='gray'>없음</td></tr>"

        rows = ""
        for o in S["orders"][:15]:
            color = "green" if o["status"] == "성공" else "red"
            rows += f"""
<tr>
    <td class="small">{safe(o["time"])}</td>
    <td>{safe(o["name"])} {safe(o["side"])} {safe(o["qty"])}주</td>
    <td class="{color}">{safe(o["status"])}</td>
</tr>
"""
        return rows

    def html_response(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    print("반자동 관제센터 시작:", PORT)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
