from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote_plus
from datetime import datetime, timedelta, timezone
import csv, html, json, math, os, threading, time, urllib.request, xml.etree.ElementTree as ET
import requestsfrom http.server import HTTPServer, BaseHTTPRequestHandler
import os
import json
import csv
import html
import time
import uuid
import threading
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse, quote_plus

import requests
import pytz

# ============================================================
# Market Watch REAL FINAL
# - 실계좌: 반자동(버튼 클릭 주문)
# - AI 가상계좌: 자동매매
# - 비상 자동매도: ENABLE_EMERGENCY_AUTO_SELL=true 일 때만
# - 날짜별/종목별 CSV 저장
# - 계좌번호/계좌ID는 절대 int 변환 금지
# ============================================================

KST = pytz.timezone("Asia/Seoul")
PORT = int(os.environ.get("PORT", "10000"))
BASE = os.environ.get("TOSS_BASE_URL", "https://openapi.tossinvest.com")

CLIENT_ID = os.environ.get("TOSS_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("TOSS_CLIENT_SECRET", "")
KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "").strip()
APP_URL = os.environ.get("APP_URL", "").strip()

ALLOW_REAL_ORDERS = os.environ.get("ALLOW_REAL_ORDERS", "false").lower() == "true"
ENABLE_EMERGENCY_AUTO_SELL = os.environ.get("ENABLE_EMERGENCY_AUTO_SELL", "false").lower() == "true"
ENABLE_NEWS = os.environ.get("ENABLE_NEWS", "true").lower() == "true"
REFRESH_SEC = int(os.environ.get("REFRESH_SEC", "60"))
NEWS_REFRESH_SEC = int(os.environ.get("NEWS_REFRESH_SEC", "600"))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))
MAX_BUY_RATIO = float(os.environ.get("MAX_BUY_RATIO", "0.70"))
LOG_ROOT = os.environ.get("LOG_ROOT", "logs")

# 26개 감시 종목
SYMBOLS = {
    "0193T0": "하이닉스 레버리지",
    "0197X0": "하이닉스 인버스",
    "000660": "SK하이닉스",
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
    "488080": "TIGER 반도체TOP10레버리지",
    "469150": "AI반도체",
    "0100K0": "방산 레버리지",
    "0080Y0": "조선 레버리지",
    "462330": "2차전지 레버리지",
    "0177X0": "로봇 휴머노이드",
    "445290": "로봇액티브",
    "433500": "원자력",
    "487240": "AI전력인프라",
    "418660": "나스닥100 레버리지",
    "465610": "미국빅테크TOP7 레버리지",
    "225040": "S&P500 레버리지",
    "0127R0": "AI클라우드",
}

# 실제 버튼/AI 가상에서 우선 후보로 쓰는 주력군. 화면에는 26개 전부 표시.
PRIMARY_TRADE_SYMBOLS = [
    "0193T0", "0197X0", "122630", "252670", "0193W0", "0193L0",
    "494310", "488080", "0100K0", "0080Y0", "462330",
    "418660", "465610", "225040"
]

NEWS_QUERIES = [
    "SK하이닉스", "삼성전자 반도체", "HBM 엔비디아", "코스피 반도체",
    "미국 증시 반도체", "환율 금리 전쟁", "반도체 규제", "AI 반도체",
]
GOOD_WORDS = ["상승", "호재", "계약", "수주", "실적", "급등", "목표가 상향", "엔비디아", "HBM", "강세", "반등"]
BAD_WORDS = ["하락", "악재", "규제", "제재", "전쟁", "금리", "환율 급등", "급락", "쇼크", "목표가 하향", "부진", "둔화"]

LOCK = threading.RLock()

S = {
    "token": None,
    "token_exp": 0,
    "account_id": "",
    "account_raw": None,
    "status": "시작 전",
    "updated": "",
    "errors": [],

    "prices": {},
    "prev_prices": {},
    "price_history": {},
    "high": {},
    "low": {},
    "wma": {},
    "scores": {},
    "signals": {},
    "emergency": {},

    "cash": 0,
    "total_value": 0,
    "profit_loss": 0,
    "profit_rate": 0.0,
    "holdings": [],
    "hold_qty": {},
    "sellable": {},

    "real_base": 0,
    "paper_start": 0,
    "paper_cash": 0,
    "paper_positions": {},  # sym -> {qty, avg}
    "paper_realized": 0,

    "market_score": 50,
    "market_mode": "UNKNOWN",
    "news_score": 0,
    "news_items": [],
    "last_news_ts": 0,

    "alerts": [],
    "last_alert": {},
    "real_orders": [],
    "paper_trades": [],
    "kakao_last": "",
}

# ============================================================
# 기본 유틸
# ============================================================

def now_kst():
    return datetime.now(KST)

def today_str():
    return now_kst().strftime("%Y-%m-%d")

def now_text():
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")

def now_hms():
    return now_kst().strftime("%H:%M:%S")

def safe(v):
    return html.escape(str(v))

def add_error(msg):
    with LOCK:
        S["errors"].insert(0, f"{now_text()} {msg}")
        S["errors"] = S["errors"][:30]
    print("[오류]", msg)

def to_float(v, default=0.0):
    try:
        if v is None:
            return default
        if isinstance(v, dict):
            for key in ["krw", "amount", "value"]:
                if key in v:
                    return to_float(v[key], default)
            return default
        return float(str(v).replace(",", "").replace("원", "").strip())
    except Exception:
        return default

def to_int_money(v, default=0):
    try:
        return int(round(to_float(v, default)))
    except Exception:
        return default

def fmt_won(v):
    try:
        return f"{int(round(float(v))):,}원"
    except Exception:
        return "-"

def fmt_pct(v):
    try:
        sign = "+" if float(v) >= 0 else ""
        return f"{sign}{float(v):.2f}%"
    except Exception:
        return "+0.00%"

def pct(a, b):
    try:
        if not b:
            return 0.0
        return (float(a) - float(b)) / float(b) * 100
    except Exception:
        return 0.0

def is_market_time():
    n = now_kst()
    return (n.hour > 8 or (n.hour == 8 and n.minute >= 50)) and n.hour < 16

def clean_filename(name):
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(name))[:80]

def day_dir():
    d = os.path.join(LOG_ROOT, today_str())
    os.makedirs(os.path.join(d, "symbols"), exist_ok=True)
    return d

def path_summary():
    return os.path.join(day_dir(), f"summary_{today_str()}.csv")

def path_paper():
    return os.path.join(day_dir(), f"paper_trades_{today_str()}.csv")

def path_real_orders():
    return os.path.join(day_dir(), f"real_orders_{today_str()}.csv")

def path_symbol(sym):
    name = clean_filename(SYMBOLS.get(sym, sym))
    return os.path.join(day_dir(), "symbols", f"{sym}_{name}.csv")

def write_csv_row(path, headers, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if new_file:
            w.writeheader()
        w.writerow({h: row.get(h, "") for h in headers})

STATE_PATH = os.environ.get("STATE_PATH", "state.json")

def save_state():
    try:
        with LOCK:
            state = {
                "real_base": S["real_base"],
                "paper_start": S["paper_start"],
                "paper_cash": S["paper_cash"],
                "paper_positions": S["paper_positions"],
                "paper_realized": S["paper_realized"],
            }
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        add_error(f"state 저장 실패: {e}")

def load_state():
    if not os.path.exists(STATE_PATH):
        return
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
        with LOCK:
            S["real_base"] = to_int_money(state.get("real_base", 0))
            S["paper_start"] = to_int_money(state.get("paper_start", 0))
            S["paper_cash"] = to_int_money(state.get("paper_cash", 0))
            S["paper_positions"] = state.get("paper_positions", {}) or {}
            S["paper_realized"] = to_int_money(state.get("paper_realized", 0))
    except Exception as e:
        add_error(f"state 로드 실패: {e}")

# ============================================================
# 카카오
# ============================================================

def add_alert(msg):
    with LOCK:
        S["alerts"].insert(0, {"time": now_hms(), "msg": msg})
        S["alerts"] = S["alerts"][:80]

def send_kakao(msg, link_url=None):
    add_alert(msg)
    if not KAKAO_TOKEN:
        with LOCK:
            S["kakao_last"] = f"{now_text()} KAKAO_TOKEN 없음"
        return False, "KAKAO_TOKEN 없음"
    if not link_url:
        link_url = APP_URL or "https://developers.kakao.com"
    template = {
        "object_type": "text",
        "text": msg[:950],
        "link": {"web_url": link_url, "mobile_web_url": link_url},
    }
    try:
        r = requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={
                "Authorization": "Bearer " + KAKAO_TOKEN,
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            },
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=8,
        )
        text = f"{now_text()} HTTP {r.status_code} {r.text[:300]}"
        with LOCK:
            S["kakao_last"] = text
        return r.status_code == 200, text
    except Exception as e:
        text = f"{now_text()} 카카오 예외 {e}"
        with LOCK:
            S["kakao_last"] = text
        add_error(text)
        return False, text

def check_kakao_token():
    if not KAKAO_TOKEN:
        return False, "KAKAO_TOKEN 없음"
    try:
        r = requests.get("https://kapi.kakao.com/v2/user/me", headers={"Authorization": "Bearer " + KAKAO_TOKEN}, timeout=8)
        return r.status_code == 200, f"HTTP {r.status_code}\n{r.text}"
    except Exception as e:
        return False, str(e)

def alert_once(key, msg, cooldown=None):
    cooldown = ALERT_COOLDOWN_SEC if cooldown is None else cooldown
    with LOCK:
        last = S["last_alert"].get(key, 0)
        if time.time() - last < cooldown:
            return False
        S["last_alert"][key] = time.time()
    send_kakao(msg, APP_URL)
    return True

# ============================================================
# 토스 API
# ============================================================

def get_token():
    if not CLIENT_ID or not CLIENT_SECRET:
        with LOCK:
            S["status"] = "토스 키 없음"
        return None
    try:
        r = requests.post(
            BASE + "/oauth2/token",
            data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
            timeout=10,
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code != 200:
            with LOCK:
                S["status"] = f"토큰 오류 {r.status_code}"
            add_error(f"토스 토큰 오류 {r.status_code}: {data}")
            return None
        token = data.get("access_token")
        exp = int(data.get("expires_in", 3600))
        with LOCK:
            S["token"] = token
            S["token_exp"] = time.time() + max(60, exp - 300)
            S["status"] = "토큰 정상"
        return token
    except Exception as e:
        add_error(f"토큰 예외: {e}")
        with LOCK:
            S["status"] = "토큰 예외"
        return None

def ensure_token():
    with LOCK:
        token = S["token"]
        exp = S["token_exp"]
    if not token or time.time() >= exp:
        return get_token()
    return token

def auth_headers(account=False):
    token = ensure_token() or ""
    h = {"Authorization": "Bearer " + token}
    # 계좌 ID/번호는 문자열 그대로. int 변환 절대 금지.
    with LOCK:
        account_id = S.get("account_id", "")
    if account and account_id:
        h["X-Tossinvest-Account"] = str(account_id)
    return h

def api_get(path, params=None, account=False, timeout=10):
    try:
        r = requests.get(BASE + path, headers=auth_headers(account), params=params or {}, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code >= 400:
            add_error(f"GET {path} {r.status_code}: {str(data)[:300]}")
        return r.status_code, data
    except Exception as e:
        add_error(f"GET {path} 예외: {e}")
        return 0, {"error": str(e)}

def api_post(path, body=None, account=False, timeout=10):
    try:
        h = auth_headers(account)
        h["Content-Type"] = "application/json"
        r = requests.post(BASE + path, headers=h, json=body or {}, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code >= 400:
            add_error(f"POST {path} {r.status_code}: {str(data)[:300]}")
        return r.status_code, data
    except Exception as e:
        add_error(f"POST {path} 예외: {e}")
        return 0, {"error": str(e)}

def pick_account_id(acc):
    # 어떤 필드가 오든 문자열 그대로 사용. 하이픈 계좌번호 int 변환 금지.
    for key in ["accountSeq", "accountId", "accountNo", "accountNumber", "id", "number"]:
        if acc.get(key) not in [None, ""]:
            return str(acc.get(key))
    return ""

def load_account():
    code, data = api_get("/api/v1/accounts", timeout=10)
    if code != 200:
        with LOCK:
            S["status"] = "계좌 조회 실패"
        return False
    result = data.get("result", data)
    accounts = result if isinstance(result, list) else result.get("accounts", []) if isinstance(result, dict) else []
    if not accounts:
        with LOCK:
            S["status"] = "계좌 없음"
            S["account_raw"] = data
        return False
    acc = accounts[0]
    account_id = pick_account_id(acc)
    with LOCK:
        S["account_id"] = account_id
        S["account_raw"] = acc
    return True

def load_buying_power():
    code, data = api_get("/api/v1/buying-power", params={"currency": "KRW"}, account=True, timeout=10)
    if code != 200:
        return False
    r = data.get("result", data)
    cash = 0
    if isinstance(r, dict):
        for key in ["cashBuyingPower", "buyingPower", "availableAmount", "cash", "orderableAmount"]:
            if key in r:
                cash = to_int_money(r.get(key))
                break
        if not cash:
            cash = to_int_money(r.get("amount", {}).get("krw", 0) if isinstance(r.get("amount"), dict) else r.get("amount", 0))
    with LOCK:
        S["cash"] = cash
    return True

def load_holdings():
    code, data = api_get("/api/v1/holdings", account=True, timeout=12)
    if code != 200:
        return False
    result = data.get("result", {})
    if not isinstance(result, dict):
        return False

    total_market = 0
    pl_amount = 0
    pl_rate = 0.0
    mv = result.get("marketValue", {})
    if isinstance(mv, dict):
        total_market = to_float(mv.get("amount", {}).get("krw", mv.get("amount", 0)))
    pl = result.get("profitLoss", {})
    if isinstance(pl, dict):
        pl_amount = to_float(pl.get("amount", {}).get("krw", pl.get("amount", 0)))
        pl_rate = to_float(pl.get("rate", 0)) * 100

    holdings = []
    hold_qty = {}
    for item in result.get("items", []) or []:
        sym = str(item.get("symbol", ""))
        name = item.get("name", SYMBOLS.get(sym, sym))
        qty = to_float(item.get("quantity", item.get("qty", 0)))
        last_price = to_float(item.get("lastPrice", item.get("price", 0)))
        avg = to_float(item.get("averagePurchasePrice", item.get("avgPrice", 0)))
        item_mv = item.get("marketValue", {})
        value = to_float(item_mv.get("amount", 0) if isinstance(item_mv, dict) else item_mv)
        item_pl = item.get("profitLoss", {})
        pl_amt = to_float(item_pl.get("amount", 0) if isinstance(item_pl, dict) else item_pl)
        pl_r = to_float(item_pl.get("rate", 0) if isinstance(item_pl, dict) else 0) * 100
        holdings.append({"symbol": sym, "name": name, "qty": qty, "last_price": last_price, "avg": avg, "value": value, "pl_amt": pl_amt, "pl_rate": pl_r})
        hold_qty[sym] = qty

    with LOCK:
        S["holdings"] = holdings
        S["hold_qty"] = hold_qty
        S["profit_loss"] = int(pl_amount)
        S["profit_rate"] = round(pl_rate, 2)
        S["total_value"] = int(S["cash"] + total_market)
    return True

def load_sellable_quantities():
    sellable = {}
    # 보유종목 전체 + 주력 종목
    with LOCK:
        targets = set(S["hold_qty"].keys()) | set(PRIMARY_TRADE_SYMBOLS)
    for sym in targets:
        code, data = api_get("/api/v1/sellable-quantity", params={"symbol": sym}, account=True, timeout=8)
        qty = 0
        if code == 200:
            r = data.get("result", data)
            if isinstance(r, dict):
                for key in ["sellableQuantity", "quantity", "qty"]:
                    if key in r:
                        qty = to_float(r.get(key))
                        break
        sellable[sym] = qty
    with LOCK:
        S["sellable"] = sellable
    return True

def refresh_account_all():
    with LOCK:
        has_account = bool(S["account_id"])
    if not has_account:
        load_account()
    load_buying_power()
    load_holdings()
    load_sellable_quantities()

# ============================================================
# 가격 / 지표 / 뉴스
# ============================================================

def load_prices():
    symbols = ",".join(SYMBOLS.keys())
    code, data = api_get("/api/v1/prices", params={"symbols": symbols}, timeout=15)
    if code != 200:
        with LOCK:
            S["status"] = "현재가 조회 실패"
        return False
    result = data.get("result", [])
    if isinstance(result, dict):
        result = result.get("prices", []) or result.get("items", []) or []
    count = 0
    with LOCK:
        for item in result:
            sym = str(item.get("symbol", ""))
            if sym not in SYMBOLS:
                continue
            price = to_float(item.get("lastPrice", item.get("price", item.get("close", 0))))
            if price <= 0:
                continue
            old = S["prices"].get(sym, price)
            S["prev_prices"][sym] = old
            S["prices"][sym] = price
            hist = S["price_history"].setdefault(sym, [])
            hist.append(price)
            if len(hist) > 240:
                del hist[:-240]
            S["high"][sym] = max(S["high"].get(sym, price), price)
            S["low"][sym] = min(S["low"].get(sym, price), price)
            count += 1
        S["updated"] = now_text()
        S["status"] = f"정상 {count}/{len(SYMBOLS)}"
    return count > 0

def calc_wma_values(values, n):
    if len(values) < n:
        return values[-1] if values else 0
    recent = values[-n:]
    weights = list(range(1, n + 1))
    return sum(v * w for v, w in zip(recent, weights)) / sum(weights)

def price_change_pct(sym):
    with LOCK:
        p = S["prices"].get(sym, 0)
        prev = S["prev_prices"].get(sym, p)
    return pct(p, prev)

def high_drop_pct(sym):
    with LOCK:
        p = S["prices"].get(sym, 0)
        h = S["high"].get(sym, p)
    return pct(p, h)

def low_rise_pct(sym):
    with LOCK:
        p = S["prices"].get(sym, 0)
        l = S["low"].get(sym, p)
    return pct(p, l)

def calc_indicators():
    with LOCK:
        for sym in SYMBOLS:
            hist = S["price_history"].get(sym, [])
            p = S["prices"].get(sym, 0)
            if not hist and p:
                hist = [p]
            w5 = calc_wma_values(hist, 5)
            w20 = calc_wma_values(hist, 20)
            w60 = calc_wma_values(hist, 60)
            # 가격조회만으로는 실제 거래량 불가할 수 있어 기본 1.0. candle 연동 실패해도 시스템이 죽지 않게 함.
            volume_ratio = S["wma"].get(sym, {}).get("volume_ratio", 1.0)
            S["wma"][sym] = {"wma5": round(w5, 2), "wma20": round(w20, 2), "wma60": round(w60, 2), "volume_ratio": volume_ratio}

def refresh_news(force=False):
    if not ENABLE_NEWS:
        with LOCK:
            S["news_score"] = 0
            S["news_items"] = []
        return
    with LOCK:
        last = S["last_news_ts"]
    if not force and time.time() - last < NEWS_REFRESH_SEC:
        return
    items = []
    score = 0
    try:
        for q in NEWS_QUERIES:
            url = "https://news.google.com/rss/search?q=" + quote_plus(q) + "&hl=ko&gl=KR&ceid=KR:ko"
            r = requests.get(url, timeout=8)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:3]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                if not title:
                    continue
                s = 0
                if any(w in title for w in GOOD_WORDS):
                    s += 2
                if any(w in title for w in BAD_WORDS):
                    s -= 3
                score += s
                items.append({"query": q, "title": title, "score": s, "link": link})
        score = max(-20, min(20, score))
        with LOCK:
            S["news_items"] = items[:20]
            S["news_score"] = score
            S["last_news_ts"] = time.time()
    except Exception as e:
        add_error(f"뉴스 조회 실패: {e}")

# ============================================================
# AI 판단 / 비상 / 가상매매
# ============================================================

def market_symbol_score(sym):
    with LOCK:
        p = S["prices"].get(sym, 0)
        wm = S["wma"].get(sym, {})
    if p <= 0:
        return 50
    score = 50
    w5, w20, w60 = wm.get("wma5", 0), wm.get("wma20", 0), wm.get("wma60", 0)
    if w5 and p > w5: score += 8
    if w5 and p < w5: score -= 8
    if w5 and w20 and w5 > w20: score += 8
    if w5 and w20 and w5 < w20: score -= 8
    if w20 and w60 and w20 > w60: score += 5
    if w20 and w60 and w20 < w60: score -= 5
    chg = price_change_pct(sym)
    if chg > 0: score += 5
    if chg < 0: score -= 5
    return max(0, min(100, int(score)))

def calc_market_score():
    # KODEX 레버리지/인버스, 코스닥 레버/인버스, 하이닉스 원주를 종합
    kospi_lev = market_symbol_score("122630")
    kospi_inv = market_symbol_score("252670")
    kosdaq_lev = market_symbol_score("233740")
    kosdaq_inv = market_symbol_score("251340")
    hynix = market_symbol_score("000660")
    score = int((kospi_lev + kosdaq_lev + hynix + (100 - kospi_inv) + (100 - kosdaq_inv)) / 5)
    mode = "강세" if score >= 65 else "중립" if score >= 45 else "약세"
    with LOCK:
        S["market_score"] = score
        S["market_mode"] = mode
    return score

def score_symbol(sym):
    with LOCK:
        price = S["prices"].get(sym, 0)
        wm = S["wma"].get(sym, {})
        news_score = S["news_score"]
        market_score = S["market_score"]
    if price <= 0:
        return 0
    score = 50
    w5, w20, w60 = wm.get("wma5", 0), wm.get("wma20", 0), wm.get("wma60", 0)
    vr = wm.get("volume_ratio", 1.0)
    chg = price_change_pct(sym)
    hdrop = high_drop_pct(sym)
    lrise = low_rise_pct(sym)

    if w5 and price > w5: score += 10
    if w5 and price < w5: score -= 10
    if w5 and w20 and w5 > w20: score += 12
    if w5 and w20 and w5 < w20: score -= 12
    if w20 and w60 and w20 > w60: score += 6
    if w20 and w60 and w20 < w60: score -= 6
    if chg > 0: score += 6
    if chg < 0: score -= 6
    if vr >= 1.8 and chg > 0: score += 8
    if vr >= 1.8 and chg < 0: score -= 10
    if hdrop <= -4.5: score -= 15
    elif hdrop <= -3.5: score -= 10
    elif hdrop <= -2.5: score -= 5
    if lrise >= 2.5 and chg > 0: score += 5

    # 시장/뉴스 보정: 레버리지형은 시장 강세 유리, 인버스형은 반대
    name = SYMBOLS.get(sym, "")
    is_inverse = "인버스" in name
    if is_inverse:
        score += int((50 - market_score) * 0.25)
        score -= int(news_score * 0.3)
    else:
        score += int((market_score - 50) * 0.25)
        score += int(news_score * 0.3)

    return max(0, min(100, int(score)))

def recommend_buy_ratio(score):
    if score >= 85: return min(MAX_BUY_RATIO, 0.70)
    if score >= 75: return min(MAX_BUY_RATIO, 0.50)
    if score >= 65: return min(MAX_BUY_RATIO, 0.30)
    return 0.0

def emergency_for(sym, score):
    hdrop = high_drop_pct(sym)
    with LOCK:
        vr = S["wma"].get(sym, {}).get("volume_ratio", 1.0)
        market_score = S["market_score"]
        news_score = S["news_score"]
    level = 0
    reason = ""
    sell_ratio = 0.0
    if hdrop <= -2.5:
        level = 1
        reason = f"고점대비 {hdrop:.2f}% 하락"
    if hdrop <= -3.5 and vr >= 1.8 and score <= 45:
        level = 2
        sell_ratio = 0.50
        reason = f"부분 비상: 고점대비 {hdrop:.2f}%, 거래량 {vr}배, AI {score}"
    if hdrop <= -4.5 and vr >= 1.8 and score <= 40 and (market_score <= 35 or news_score < 0):
        level = 3
        sell_ratio = 1.00
        reason = f"강한 비상: 고점대비 {hdrop:.2f}%, 거래량 {vr}배, AI {score}, 시장 {market_score}, 뉴스 {news_score}"
    return {"level": level, "reason": reason, "sell_ratio": sell_ratio}

def build_signal(sym):
    score = S["scores"].get(sym, 0)
    with LOCK:
        price = S["prices"].get(sym, 0)
        cash = S["cash"]
        hold = S["hold_qty"].get(sym, 0)
        sellable = S["sellable"].get(sym, hold)
    buy_ratio = recommend_buy_ratio(score)
    rec_buy_qty = int((cash * buy_ratio) // price) if price > 0 else 0
    em = emergency_for(sym, score)
    if em["level"] >= 3:
        label = "🚨 강한 비상"
    elif em["level"] == 2:
        label = "⚠️ 부분 비상"
    elif score >= 75:
        label = "진입 후보 ⭕"
    elif score >= 60:
        label = "보유/관찰 🟡"
    elif score >= 40:
        label = "관망 🔴"
    else:
        label = "약함/매도 후보 ⛔"
    rec_sell_qty = 0
    sell_ratio = 0.0
    if em["sell_ratio"]:
        sell_ratio = em["sell_ratio"]
        rec_sell_qty = int(sellable * sell_ratio)
    elif hold > 0 and score < 45:
        sell_ratio = 0.30
        rec_sell_qty = int(sellable * sell_ratio)
    elif hold > 0 and high_drop_pct(sym) <= -3:
        sell_ratio = 0.50
        rec_sell_qty = int(sellable * sell_ratio)
    return {
        "symbol": sym,
        "name": SYMBOLS.get(sym, sym),
        "price": price,
        "score": score,
        "label": label,
        "buy_ratio": buy_ratio,
        "rec_buy_qty": rec_buy_qty,
        "rec_buy_amount": int(rec_buy_qty * price),
        "sell_ratio": sell_ratio,
        "rec_sell_qty": rec_sell_qty,
        "hold_qty": hold,
        "sellable": sellable,
        "chg": round(price_change_pct(sym), 2),
        "hdrop": round(high_drop_pct(sym), 2),
        "lrise": round(low_rise_pct(sym), 2),
        "emergency_level": em["level"],
        "emergency_reason": em["reason"],
    }

def calc_all_signals():
    calc_indicators()
    calc_market_score()
    with LOCK:
        for sym in SYMBOLS:
            S["scores"][sym] = score_symbol(sym)
        for sym in SYMBOLS:
            sig = build_signal(sym)
            S["signals"][sym] = sig
            S["emergency"][sym] = {"level": sig["emergency_level"], "reason": sig["emergency_reason"]}

def paper_total_value():
    with LOCK:
        total = S["paper_cash"]
        positions = dict(S["paper_positions"])
        prices = dict(S["prices"])
    for sym, pos in positions.items():
        total += to_float(pos.get("qty")) * prices.get(sym, 0)
    return int(total)

def record_paper(action, sym, price, qty, reason):
    total = paper_total_value()
    with LOCK:
        row = {
            "time": now_text(), "action": action, "symbol": sym, "name": SYMBOLS.get(sym, sym),
            "price": price, "qty": qty, "paper_cash": S["paper_cash"],
            "paper_total": total, "paper_start": S["paper_start"],
            "profit": total - S["paper_start"],
            "profit_rate": pct(total, S["paper_start"]), "reason": reason,
        }
        S["paper_trades"].insert(0, row)
        S["paper_trades"] = S["paper_trades"][:80]
    headers = ["time", "action", "symbol", "name", "price", "qty", "paper_cash", "paper_total", "paper_start", "profit", "profit_rate", "reason"]
    write_csv_row(path_paper(), headers, row)
    save_state()

def paper_buy(sym, ratio, reason):
    with LOCK:
        price = S["prices"].get(sym, 0)
        cash = S["paper_cash"]
    if price <= 0 or cash <= 0:
        return False
    amount = cash * ratio
    qty = int(amount // price)
    if qty <= 0:
        return False
    cost = int(qty * price)
    with LOCK:
        pos = S["paper_positions"].get(sym, {"qty": 0, "avg": 0})
        old_qty = to_float(pos.get("qty", 0))
        old_avg = to_float(pos.get("avg", 0))
        new_qty = old_qty + qty
        new_avg = ((old_qty * old_avg) + cost) / new_qty if new_qty > 0 else price
        S["paper_cash"] -= cost
        S["paper_positions"][sym] = {"qty": new_qty, "avg": new_avg}
    record_paper("가상매수", sym, price, qty, reason)
    return True

def paper_sell(sym, sell_ratio, reason):
    with LOCK:
        pos = S["paper_positions"].get(sym)
        price = S["prices"].get(sym, 0)
    if not pos or price <= 0:
        return False
    qty_have = int(to_float(pos.get("qty", 0)))
    qty = qty_have if sell_ratio >= 1 else int(qty_have * sell_ratio)
    if qty <= 0:
        return False
    proceeds = int(qty * price)
    with LOCK:
        avg = to_float(pos.get("avg", 0))
        S["paper_cash"] += proceeds
        S["paper_realized"] += int((price - avg) * qty)
        remain = qty_have - qty
        if remain <= 0:
            S["paper_positions"].pop(sym, None)
        else:
            S["paper_positions"][sym] = {"qty": remain, "avg": avg}
    record_paper("가상매도", sym, price, qty, reason)
    return True

def paper_auto_step():
    with LOCK:
        if S["paper_start"] <= 0:
            return
        positions = dict(S["paper_positions"])
        signals = dict(S["signals"])
    # 보유 포지션 매도/비상 방어
    for sym in list(positions.keys()):
        sig = signals.get(sym, {})
        if sig.get("emergency_level", 0) >= 3:
            paper_sell(sym, 1.0, sig.get("emergency_reason", "강한 비상"))
        elif sig.get("emergency_level", 0) == 2:
            paper_sell(sym, 0.5, sig.get("emergency_reason", "부분 비상"))
        elif sig.get("score", 50) < 40 or sig.get("hdrop", 0) <= -3.5:
            paper_sell(sym, 0.5, "AI 약화/고점이탈")
    # 신규/전환 매수: 가장 강한 주력 후보
    with LOCK:
        has_position = bool(S["paper_positions"])
        cash = S["paper_cash"]
    if cash <= 0:
        return
    candidates = []
    for sym in PRIMARY_TRADE_SYMBOLS:
        sig = signals.get(sym, {})
        if sig.get("score", 0) >= 75 and sig.get("emergency_level", 0) == 0:
            candidates.append((sig.get("score", 0), sym, sig))
    if not candidates:
        return
    candidates.sort(reverse=True)
    best_score, best_sym, best_sig = candidates[0]
    # 포지션이 이미 있으면 추가 매수는 과하게 하지 않음
    if has_position and best_score < 85:
        return
    ratio = recommend_buy_ratio(best_score)
    if has_position:
        ratio = min(ratio, 0.25)
    paper_buy(best_sym, ratio, f"AI 자동 진입 score={best_score}")

def emergency_real_auto_sell_step():
    if not (ENABLE_EMERGENCY_AUTO_SELL and ALLOW_REAL_ORDERS):
        return
    with LOCK:
        holdings = list(S["holdings"])
        signals = dict(S["signals"])
    for h in holdings:
        sym = h.get("symbol")
        sig = signals.get(sym, {})
        level = sig.get("emergency_level", 0)
        if level < 2:
            continue
        sellable = int(S["sellable"].get(sym, h.get("qty", 0)))
        if sellable <= 0:
            continue
        ratio = 1.0 if level >= 3 else 0.5
        qty = sellable if ratio >= 1 else int(sellable * ratio)
        if qty <= 0:
            continue
        key = f"AUTOSELL_{sym}_{level}"
        with LOCK:
            last = S["last_alert"].get(key, 0)
            if time.time() - last < 1800:
                continue
            S["last_alert"][key] = time.time()
        result = place_order(sym, "SELL", qty, auto=True, reason=sig.get("emergency_reason", "비상 자동매도"))
        send_kakao(f"🚨 실계좌 비상 자동매도 실행\n{SYMBOLS.get(sym,sym)}\n수량: {qty}주\n결과: {result.get('message','')}", APP_URL)

def write_logs():
    headers_summary = ["time", "symbol", "name", "price", "score", "signal", "chg", "hdrop", "lrise", "market_score", "market_mode", "news_score", "rec_buy_qty", "rec_sell_qty", "emergency_level", "emergency_reason"]
    headers_symbol = ["time", "price", "high", "low", "wma5", "wma20", "wma60", "volume_ratio", "score", "signal", "chg", "hdrop", "lrise", "rec_buy_qty", "rec_sell_qty", "market_score", "news_score", "emergency_level", "emergency_reason"]
    with LOCK:
        snapshot = {sym: S["signals"].get(sym, {}) for sym in SYMBOLS}
        prices = dict(S["prices"])
        high = dict(S["high"])
        low = dict(S["low"])
        wmas = dict(S["wma"])
        market_score = S["market_score"]
        market_mode = S["market_mode"]
        news_score = S["news_score"]
    for sym, sig in snapshot.items():
        if prices.get(sym, 0) <= 0:
            continue
        row = {
            "time": now_text(), "symbol": sym, "name": SYMBOLS.get(sym, sym), "price": prices.get(sym, 0),
            "score": sig.get("score", 0), "signal": sig.get("label", ""), "chg": sig.get("chg", 0),
            "hdrop": sig.get("hdrop", 0), "lrise": sig.get("lrise", 0), "market_score": market_score,
            "market_mode": market_mode, "news_score": news_score, "rec_buy_qty": sig.get("rec_buy_qty", 0),
            "rec_sell_qty": sig.get("rec_sell_qty", 0), "emergency_level": sig.get("emergency_level", 0),
            "emergency_reason": sig.get("emergency_reason", ""),
        }
        write_csv_row(path_summary(), headers_summary, row)
        wm = wmas.get(sym, {})
        srow = dict(row)
        srow.update({"high": high.get(sym, 0), "low": low.get(sym, 0), "wma5": wm.get("wma5", 0), "wma20": wm.get("wma20", 0), "wma60": wm.get("wma60", 0), "volume_ratio": wm.get("volume_ratio", 1)})
        write_csv_row(path_symbol(sym), headers_symbol, srow)

# ============================================================
# 실계좌 주문
# ============================================================

def record_real_order(row):
    with LOCK:
        S["real_orders"].insert(0, row)
        S["real_orders"] = S["real_orders"][:80]
    headers = ["time", "auto", "side", "symbol", "name", "qty", "status", "message", "reason", "response"]
    write_csv_row(path_real_orders(), headers, row)

def place_order(sym, side, qty, auto=False, reason=""):
    if sym not in SYMBOLS:
        return {"ok": False, "message": "허용되지 않은 종목"}
    if side not in ["BUY", "SELL"]:
        return {"ok": False, "message": "BUY/SELL 오류"}
    qty = int(to_float(qty, 0))
    if qty <= 0:
        return {"ok": False, "message": "수량 0"}
    with LOCK:
        price = S["prices"].get(sym, 0)
        sellable = S["sellable"].get(sym, 0)
    if price <= 0:
        return {"ok": False, "message": "현재가 0: 주문 차단"}
    if side == "SELL" and sellable <= 0:
        return {"ok": False, "message": "매도가능수량 0: 주문 차단"}
    if side == "SELL" and qty > sellable:
        qty = int(sellable)
    if not ALLOW_REAL_ORDERS:
        row = {"time": now_text(), "auto": auto, "side": side, "symbol": sym, "name": SYMBOLS.get(sym, sym), "qty": qty, "status": "차단", "message": "ALLOW_REAL_ORDERS=false", "reason": reason, "response": ""}
        record_real_order(row)
        return {"ok": False, "message": "실주문 차단 상태(ALLOW_REAL_ORDERS=false)"}

    body = {
        "clientOrderId": f"mw-{sym}-{side}-{now_kst().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "symbol": sym,
        "side": side,
        "orderType": "MARKET",
        "quantity": str(qty),
    }
    code, data = api_post("/api/v1/orders", body=body, account=True, timeout=10)
    ok = code == 200
    msg = "성공" if ok else f"실패 HTTP {code}"
    row = {"time": now_text(), "auto": auto, "side": side, "symbol": sym, "name": SYMBOLS.get(sym, sym), "qty": qty, "status": "성공" if ok else "실패", "message": msg, "reason": reason, "response": json.dumps(data, ensure_ascii=False)[:500]}
    record_real_order(row)
    send_kakao(("✅" if ok else "⚠️") + f" 실계좌 {'자동' if auto else '반자동'} {side}\n{SYMBOLS.get(sym,sym)}\n수량: {qty}\n{msg}", APP_URL)
    refresh_account_all()
    return {"ok": ok, "message": msg, "data": data}

# ============================================================
# 루프
# ============================================================

def reset_daily_if_needed():
    n = now_kst()
    # 09:00 근처에 고점/저점 초기화. 하루 한 번만 대충 처리.
    key = f"DAILY_RESET_{today_str()}"
    with LOCK:
        if S["last_alert"].get(key):
            return
    if n.hour == 9 and n.minute <= 2:
        with LOCK:
            S["high"] = {}
            S["low"] = {}
            S["last_alert"][key] = time.time()
        send_kakao("🔔 장 시작: Market Watch 감시 시작", APP_URL)

def main_loop():
    load_state()
    get_token()
    refresh_account_all()
    refresh_news(force=True)
    counter = 0
    while True:
        try:
            reset_daily_if_needed()
            if is_market_time() or counter % 5 == 0:
                load_prices()
                calc_all_signals()
                refresh_news(force=False)
                calc_all_signals()
                paper_auto_step()
                emergency_real_auto_sell_step()
                write_logs()
                # 주요 신호 알림
                with LOCK:
                    signals = dict(S["signals"])
                for sym in PRIMARY_TRADE_SYMBOLS[:8]:
                    sig = signals.get(sym, {})
                    if sig.get("score", 0) >= 80 and sig.get("emergency_level", 0) == 0:
                        alert_once(f"ENTRY_{sym}", f"🟢 AI 진입 후보\n{SYMBOLS.get(sym,sym)}\n점수: {sig.get('score')}\n현재가: {fmt_won(sig.get('price'))}\n추천매수: {sig.get('rec_buy_qty')}주", ALERT_COOLDOWN_SEC)
                    if sig.get("emergency_level", 0) >= 2:
                        alert_once(f"EM_{sym}_{sig.get('emergency_level')}", f"🚨 비상 신호\n{SYMBOLS.get(sym,sym)}\n{sig.get('emergency_reason')}\n추천매도: {sig.get('rec_sell_qty')}주", ALERT_COOLDOWN_SEC)
            if counter % 5 == 0:
                refresh_account_all()
            ensure_token()
            counter += 1
        except Exception as e:
            add_error(f"루프 예외: {e}\n{traceback.format_exc()[:500]}")
        time.sleep(max(10, REFRESH_SEC))

# ============================================================
# 웹
# ============================================================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api":
            with LOCK:
                data = {k: S[k] for k in ["status", "updated", "account_id", "cash", "total_value", "profit_loss", "profit_rate", "real_base", "paper_start", "paper_cash", "paper_positions", "paper_realized", "market_score", "market_mode", "news_score", "news_items", "prices", "signals", "holdings", "sellable", "errors", "kakao_last"]}
                data["paper_total"] = paper_total_value()
                data["allow_real_orders"] = ALLOW_REAL_ORDERS
                data["enable_emergency_auto_sell"] = ENABLE_EMERGENCY_AUTO_SELL
            return self.json_response(data)
        if path == "/refresh":
            load_prices(); refresh_account_all(); refresh_news(force=True); calc_all_signals(); write_logs()
            return self.redirect("/")
        if path == "/check_kakao":
            ok, msg = check_kakao_token()
            return self.result_page("토큰 확인 성공" if ok else "토큰 확인 실패", msg)
        if path == "/test_kakao":
            ok, msg = send_kakao("✅ Market Watch 카카오 테스트\n" + now_text(), APP_URL)
            return self.result_page("카카오 전송 성공" if ok else "카카오 전송 실패", msg)
        if path == "/download_summary":
            return self.send_file(path_summary(), f"summary_{today_str()}.csv")
        if path == "/download_paper":
            return self.send_file(path_paper(), f"paper_trades_{today_str()}.csv")
        if path == "/download_real_orders":
            return self.send_file(path_real_orders(), f"real_orders_{today_str()}.csv")
        if path == "/symbols_csv":
            return self.symbols_csv_page()
        if path.startswith("/download_symbol/"):
            sym = path.split("/")[-1]
            return self.send_file(path_symbol(sym), os.path.basename(path_symbol(sym)))
        return self.dashboard()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        if path == "/reset_base":
            refresh_account_all()
            with LOCK:
                total = int(S["total_value"])
                if total <= 0:
                    return self.json_response({"ok": False, "message": "총자산 조회 실패/0원"})
                S["real_base"] = total
                S["paper_start"] = total
                S["paper_cash"] = total
                S["paper_positions"] = {}
                S["paper_realized"] = 0
            save_state()
            send_kakao(f"🔄 오늘 기준금/AI가상 리셋\n기준금: {fmt_won(total)}", APP_URL)
            return self.json_response({"ok": True, "base": total})
        if path == "/order":
            sym = str(body.get("symbol", ""))
            side = str(body.get("side", ""))
            qty = body.get("qty", 0)
            result = place_order(sym, side, qty, auto=False, reason="사용자 버튼")
            return self.json_response(result)
        return self.json_response({"ok": False, "message": "unknown path"})

    def dashboard(self):
        with LOCK:
            total = S["total_value"]
            cash = S["cash"]
            real_base = S["real_base"]
            paper_start = S["paper_start"]
            paper_cash = S["paper_cash"]
            market_score = S["market_score"]
            market_mode = S["market_mode"]
            news_score = S["news_score"]
            updated = S["updated"]
            status = S["status"]
            account_id = S["account_id"]
            kakao_last = S["kakao_last"]
            alerts = list(S["alerts"])
            errors = list(S["errors"])
            holdings = list(S["holdings"])
            news_items = list(S["news_items"])
            orders = list(S["real_orders"])
            paper_trades = list(S["paper_trades"])
        paper_total = paper_total_value()
        real_rate = pct(total, real_base) if real_base else 0
        paper_rate = pct(paper_total, paper_start) if paper_start else 0
        diff = paper_rate - real_rate
        rows = self.symbol_rows()
        holding_rows = self.holding_rows(holdings)
        news_rows = "".join(f"<div class='small'>[{n.get('score')}] {safe(n.get('title'))}</div>" for n in news_items[:10]) or "<div class='small'>뉴스 없음</div>"
        alert_rows = "".join(f"<tr><td>{safe(a['time'])}</td><td>{safe(a['msg']).replace(chr(10),'<br>')}</td></tr>" for a in alerts[:10]) or "<tr><td colspan='2'>없음</td></tr>"
        err_rows = "".join(f"<div class='small red'>{safe(e)}</div>" for e in errors[:5]) or "<div class='small'>오류 없음</div>"
        order_rows = "".join(f"<tr><td>{safe(o.get('time'))}</td><td>{safe(o.get('name'))} {safe(o.get('side'))} {safe(o.get('qty'))}주</td><td>{safe(o.get('status'))}</td></tr>" for o in orders[:8]) or "<tr><td colspan='3'>없음</td></tr>"
        paper_rows = "".join(f"<tr><td>{safe(p.get('time'))}</td><td>{safe(p.get('name'))} {safe(p.get('action'))} {safe(p.get('qty'))}주</td><td>{fmt_won(p.get('paper_total',0))}</td></tr>" for p in paper_trades[:8]) or "<tr><td colspan='3'>없음</td></tr>"
        html_doc = f"""
<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Market Watch REAL FINAL</title><meta http-equiv='refresh' content='60'>
<style>
body{{background:#05060a;color:#f4f4f5;font-family:Arial,sans-serif;margin:0;padding:18px}}h1{{margin:0 0 18px;font-size:28px}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}.card{{background:#141821;border:1px solid #252b3a;border-radius:14px;padding:18px;margin-bottom:12px}}
.big{{font-size:30px;font-weight:800;color:#ffe64d}}.mid{{font-size:20px;font-weight:700}}.small{{font-size:12px;color:#a9afbd;line-height:1.5}}.red{{color:#ff4d5e}}.blue{{color:#4d8cff}}.green{{color:#50e090}}.yellow{{color:#ffe64d}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:8px;border-bottom:1px solid #283040;vertical-align:top}}th{{color:#a9afbd;background:#171c27}}
button{{border:0;border-radius:8px;padding:9px 12px;margin:3px;font-weight:700;cursor:pointer}}.purple{{background:#7c3aed;color:white}}.gray{{background:#3a3a3a;color:white}}.buy{{background:#d71920;color:white}}.sell{{background:#1f64ff;color:white}}input{{background:#05060a;color:white;border:1px solid #3a3f52;border-radius:6px;padding:7px;width:80px}}
@media(max-width:1000px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>Market Watch REAL FINAL</h1>
<div class='grid'>
<div class='card'><h2>실계좌</h2><div class='big'>{fmt_won(total)}</div><p>기준금: {fmt_won(real_base) if real_base else '미설정'}</p><p>수익률: {fmt_pct(real_rate)}</p><p>매수가능: {fmt_won(cash)}</p><p>계좌: {safe(account_id) or '미확인'}</p><p>실주문: {'허용' if ALLOW_REAL_ORDERS else '차단'}</p><button class='purple' onclick='resetBase()'>오늘 기준금/AI가상 리셋</button></div>
<div class='card'><h2>AI 가상계좌</h2><div class='big'>{fmt_won(paper_total)}</div><p>시작금: {fmt_won(paper_start) if paper_start else '미설정'}</p><p>현금: {fmt_won(paper_cash)}</p><p>수익률: {fmt_pct(paper_rate)}</p><p>실계좌 대비: {diff:+.2f}%p</p></div>
<div class='card'><h2>시장/비상</h2><p class='green'>● {safe(market_mode)}</p><p>시장: {market_score}/100</p><p>뉴스: {news_score}</p><p>비상자동매도: {'ON' if ENABLE_EMERGENCY_AUTO_SELL else 'OFF'}</p><p>업데이트: {safe(updated)}</p><p class='small'>상태: {safe(status)}</p></div>
</div>
<div class='card'><h2>26종목 AI 판단</h2><table><tr><th>종목</th><th>현재가</th><th>AI</th><th>등락/고점</th><th>추천매수</th><th>추천매도</th><th>보유</th><th>실계좌</th></tr>{rows}</table></div>
<div class='grid'><div class='card'><h2>보유종목</h2><table><tr><th>종목</th><th>수량</th><th>현재가</th><th>수익률</th></tr>{holding_rows}</table></div><div class='card'><h2>뉴스</h2>{news_rows}</div><div class='card'><h2>테스트/저장</h2><button class='gray' onclick="location.href='/check_kakao'">카카오 토큰</button><button class='gray' onclick="location.href='/test_kakao'">카카오 테스트</button><button class='gray' onclick="location.href='/refresh'">즉시갱신</button><br><button class='gray' onclick="location.href='/download_summary'">오늘 요약 CSV</button><button class='gray' onclick="location.href='/download_paper'">AI 가상 CSV</button><button class='gray' onclick="location.href='/download_real_orders'">실계좌 주문 CSV</button><button class='gray' onclick="location.href='/symbols_csv'">종목별 CSV 목록</button><p class='small'>카카오: {safe(kakao_last)}</p>{err_rows}</div></div>
<div class='grid'><div class='card'><h2>카카오/신호</h2><table><tr><th>시간</th><th>내용</th></tr>{alert_rows}</table></div><div class='card'><h2>실계좌 주문</h2><table><tr><th>시간</th><th>주문</th><th>결과</th></tr>{order_rows}</table></div><div class='card'><h2>AI 가상매매</h2><table><tr><th>시간</th><th>매매</th><th>총자산</th></tr>{paper_rows}</table></div></div>
<script>
async function post(url, body){{let r=await fetch(url,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body||{{}})}});return await r.json();}}
async function resetBase(){{if(!confirm('현재 토스 총자산으로 실계좌 기준금과 AI 가상계좌를 리셋할까요?'))return;let d=await post('/reset_base',{{}});alert(JSON.stringify(d));location.reload();}}
async function order(sym, side, id){{let qty=document.getElementById(id).value;if(!qty||Number(qty)<=0){{alert('수량 0');return;}}if(!confirm(sym+' '+side+' '+qty+'주 주문 전송?'))return;let d=await post('/order',{{symbol:sym,side:side,qty:qty}});alert(JSON.stringify(d));location.reload();}}
function setQty(id, qty){{document.getElementById(id).value=qty;}}
</script></body></html>"""
        self.html_response(html_doc)

    def symbol_rows(self):
        with LOCK:
            signals = dict(S["signals"])
            prices = dict(S["prices"])
        rows = ""
        for sym, name in SYMBOLS.items():
            sig = signals.get(sym, {})
            price = prices.get(sym, 0)
            score = sig.get("score", 0)
            color = "red" if sig.get("chg",0) > 0 else "blue" if sig.get("chg",0) < 0 else ""
            qty_id = f"qty_{sym}"
            rec_buy = int(sig.get("rec_buy_qty", 0) or 0)
            rec_sell = int(sig.get("rec_sell_qty", 0) or 0)
            sellable = int(to_float(sig.get("sellable", 0)))
            em = sig.get("emergency_level", 0)
            label = safe(sig.get("label", "-"))
            if em:
                label += f"<br><span class='red small'>{safe(sig.get('emergency_reason',''))}</span>"
            rows += f"""<tr><td>{safe(name)}<br><span class='small'>{sym}</span></td><td>{fmt_won(price)}</td><td>{score}<br>{label}</td><td class='{color}'>{sig.get('chg',0)}%<br><span class='small'>고점 {sig.get('hdrop',0)}%</span></td><td>{rec_buy}주<br><span class='small'>{fmt_won(sig.get('rec_buy_amount',0))}</span></td><td>{rec_sell}주</td><td>{sellable}주</td><td><input id='{qty_id}' type='number' value='{rec_buy}' min='0'><br><button class='buy' onclick="order('{sym}','BUY','{qty_id}')">매수</button><button class='sell' onclick="order('{sym}','SELL','{qty_id}')">매도</button><button class='gray' onclick="setQty('{qty_id}',{sellable})">전량</button></td></tr>"""
        return rows

    def holding_rows(self, holdings):
        if not holdings:
            return "<tr><td colspan='4'>보유 없음</td></tr>"
        rows = ""
        for h in holdings:
            color = "red" if h.get("pl_rate",0)>=0 else "blue"
            rows += f"<tr><td>{safe(h.get('name'))}<br><span class='small'>{safe(h.get('symbol'))}</span></td><td>{int(to_float(h.get('qty')))}주</td><td>{fmt_won(h.get('last_price'))}</td><td class='{color}'>{fmt_pct(h.get('pl_rate'))}</td></tr>"
        return rows

    def symbols_csv_page(self):
        links = "".join(f"<li><a href='/download_symbol/{sym}'>{safe(name)} CSV</a></li>" for sym, name in SYMBOLS.items())
        self.html_response(f"<html><head><meta charset='utf-8'><style>body{{background:#05060a;color:white;font-family:Arial;padding:20px}}a{{color:#ffe64d}}</style></head><body><h1>종목별 CSV</h1><ul>{links}</ul><a href='/'>돌아가기</a></body></html>")

    def result_page(self, title, msg):
        self.html_response(f"<html><head><meta charset='utf-8'><style>body{{background:#05060a;color:white;font-family:Arial;padding:30px}}pre{{background:#000;color:#00ff66;padding:15px;white-space:pre-wrap}}a{{color:#ffe64d}}</style></head><body><h1>{safe(title)}</h1><pre>{safe(msg)}</pre><a href='/'>돌아가기</a></body></html>")

    def send_file(self, path, filename):
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f"attachment; filename={filename}")
        self.end_headers()
        if os.path.exists(path):
            with open(path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.wfile.write("no data".encode("utf-8"))

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

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    print("Market Watch REAL FINAL 시작", PORT)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


try:
    import pytz
    KST = pytz.timezone('Asia/Seoul')
except Exception:
    KST = timezone(timedelta(hours=9))

PORT = int(os.environ.get('PORT', '10000'))
TOSS_CLIENT_ID = os.environ.get('TOSS_CLIENT_ID', '').strip()
TOSS_CLIENT_SECRET = os.environ.get('TOSS_CLIENT_SECRET', '').strip()
TOSS_ACCOUNT = os.environ.get('TOSS_ACCOUNT', '').strip()
KAKAO_TOKEN = os.environ.get('KAKAO_TOKEN', '').strip()
APP_URL = os.environ.get('APP_URL', '').strip()
ALLOW_REAL_ORDERS = os.environ.get('ALLOW_REAL_ORDERS', 'false').lower() == 'true'
ENABLE_EMERGENCY_AUTO_SELL = os.environ.get('ENABLE_EMERGENCY_AUTO_SELL', 'false').lower() == 'true'
REFRESH_SEC = int(os.environ.get('REFRESH_SEC', '60'))
ENABLE_NEWS = os.environ.get('ENABLE_NEWS', 'true').lower() == 'true'
NEWS_REFRESH_SEC = int(os.environ.get('NEWS_REFRESH_SEC', '600'))
EMERGENCY_COOLDOWN_SEC = int(os.environ.get('EMERGENCY_COOLDOWN_SEC', '1800'))
LOG_ROOT = os.environ.get('LOG_ROOT', 'logs')
STATE_PATH = os.environ.get('STATE_PATH', 'state.json')

DEFAULT_SYMBOLS = [
    {'symbol':'0193T0','name':'하이닉스 레버리지','kind':'lever'},
    {'symbol':'0197X0','name':'하이닉스 인버스','kind':'inverse'},
    {'symbol':'000660','name':'SK하이닉스','kind':'stock'},
    {'symbol':'0193W0','name':'삼성전자 레버리지','kind':'lever'},
    {'symbol':'0193L0','name':'삼성전자 인버스','kind':'inverse'},
    {'symbol':'005930','name':'삼성전자','kind':'stock'},
    {'symbol':'122630','name':'KODEX 레버리지','kind':'market_lever'},
    {'symbol':'252670','name':'KODEX 인버스2X','kind':'market_inverse'},
    {'symbol':'069500','name':'KODEX 200','kind':'market'},
    {'symbol':'233740','name':'코스닥150 레버리지','kind':'kosdaq_lever'},
    {'symbol':'251340','name':'코스닥150 인버스','kind':'kosdaq_inverse'},
    {'symbol':'229200','name':'KODEX 코스닥150','kind':'kosdaq'},
    {'symbol':'494310','name':'반도체 레버리지','kind':'theme_lever'},
    {'symbol':'488080','name':'TIGER 반도체TOP10레버리지','kind':'theme_lever'},
    {'symbol':'469150','name':'AI반도체','kind':'theme'},
    {'symbol':'0100K0','name':'방산 레버리지','kind':'theme_lever'},
    {'symbol':'0080Y0','name':'조선 레버리지','kind':'theme_lever'},
    {'symbol':'462330','name':'2차전지 레버리지','kind':'theme_lever'},
    {'symbol':'0177X0','name':'로봇 휴머노이드','kind':'theme'},
    {'symbol':'445290','name':'로봇액티브','kind':'theme'},
    {'symbol':'433500','name':'원자력','kind':'theme'},
    {'symbol':'487240','name':'AI전력인프라','kind':'theme'},
    {'symbol':'418660','name':'나스닥100 레버리지','kind':'global_lever'},
    {'symbol':'465610','name':'미국빅테크TOP7 레버리지','kind':'global_lever'},
    {'symbol':'225040','name':'S&P500 레버리지','kind':'global_lever'},
    {'symbol':'0127R0','name':'AI클라우드','kind':'theme'},
]


def load_symbols():
    raw = os.environ.get('WATCH_SYMBOLS_JSON','').strip()
    if not raw: return DEFAULT_SYMBOLS
    try: return json.loads(raw)
    except Exception: return DEFAULT_SYMBOLS

SYMBOLS = load_symbols()
SMAP = {x['symbol']:x for x in SYMBOLS}
LOCK = threading.Lock()
STATE = {'real_base':None,'paper_start':None,'paper_cash':None,'paper_positions':{},'paper_realized':0.0,'last_emergency_sell':{},'last_kakao':'','last_error':''}
LATEST = {'updated_at':'','account_seq':None,'total_asset':0,'buying_power_krw':0,'holdings':[],'prices':{},'analysis':{},'market_score':50,'market_mode':'UNKNOWN','news_score':0,'news_items':[],'paper_total':0,'paper_return':0,'real_return':0,'emergency':{'level':0,'reason':''}}
TOKEN = {'value':'','expires_at':0}
NEWS = {'ts':0,'score':0,'items':[]}

def nk(): return datetime.now(KST)
def nts(): return nk().strftime('%Y-%m-%d %H:%M:%S')
def day(): return nk().strftime('%Y-%m-%d')
def esc(x): return html.escape(str(x))
def fnum(x,d=0.0):
    try: return float(str(x).replace(',',''))
    except Exception: return d
def inum(x,d=0):
    try: return int(math.floor(float(str(x).replace(',',''))))
    except Exception: return d
def won(x):
    try: return f"{int(round(float(x))):,}원"
    except Exception: return '0원'
def pct(x):
    try: return f"{float(x):+.2f}%"
    except Exception: return '+0.00%'
def mkdir(p): os.makedirs(p, exist_ok=True)
def daydir():
    p=os.path.join(LOG_ROOT,day()); mkdir(os.path.join(p,'symbols')); return p
def sfn(s): return ''.join(c if c.isalnum() or c in '_-.' else '_' for c in str(s))

def load_state():
    global STATE
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH,'r',encoding='utf-8') as f: STATE.update(json.load(f))
        except Exception: pass

def save_state():
    with open(STATE_PATH,'w',encoding='utf-8') as f: json.dump(STATE,f,ensure_ascii=False,indent=2)
load_state()

def append_csv(path, header, row):
    mkdir(os.path.dirname(path)); exists=os.path.exists(path)
    with open(path,'a',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f, fieldnames=header)
        if not exists: w.writeheader()
        w.writerow(row)

def log_summary(a):
    h=['time','symbol','name','price','ai_score','signal','buy_qty','sell_qty','market_mode','market_score','news_score','emergency_level','emergency_reason']
    append_csv(os.path.join(daydir(),f'summary_{day()}.csv'),h,a)

def log_symbol(a):
    h=['time','symbol','name','price','day_high','day_low','wma5','wma20','wma60','volume_ratio','change_pct','drop_from_high_pct','bounce_from_low_pct','ai_score','signal','market_score','news_score','emergency_level','emergency_reason','buy_ratio','buy_qty','sell_ratio','sell_qty','reason']
    name=sfn(a['name']); sym=sfn(a['symbol'])
    append_csv(os.path.join(daydir(),'symbols',f'{sym}_{name}.csv'),h,a)

def log_paper(row):
    h=['time','action','symbol','name','price','qty','cash','paper_total','realized_pnl','return_pct','reason']
    append_csv(os.path.join(daydir(),f'paper_trades_{day()}.csv'),h,row)

def log_real(row):
    h=['time','action','symbol','name','price','qty','result','order_id','message','reason']
    append_csv(os.path.join(daydir(),f'real_orders_{day()}.csv'),h,row)

class TossError(Exception): pass

def issue_token():
    if not TOSS_CLIENT_ID or not TOSS_CLIENT_SECRET: raise TossError('토스 환경변수 없음')
    r=requests.post('https://openapi.tossinvest.com/oauth2/token',data={'grant_type':'client_credentials','client_id':TOSS_CLIENT_ID,'client_secret':TOSS_CLIENT_SECRET},timeout=10)
    if r.status_code!=200: raise TossError(f'토스 토큰 실패 {r.status_code} {r.text}')
    j=r.json(); TOKEN['value']=j['access_token']; TOKEN['expires_at']=time.time()+int(j.get('expires_in',3600)); return TOKEN['value']

def headers(account=False):
    if not TOKEN['value'] or time.time()>TOKEN['expires_at']-60: issue_token()
    h={'Authorization':'Bearer '+TOKEN['value']}
    if account:
        seq=TOSS_ACCOUNT or LATEST.get('account_seq') or account_seq()
        h['X-Tossinvest-Account']=str(seq)
    return h

def g(path, params=None, account=False):
    r=requests.get('https://openapi.tossinvest.com'+path,params=params,headers=headers(account),timeout=10)
    if r.status_code!=200: raise TossError(f'GET {path} {r.status_code} {r.text}')
    return r.json().get('result')

def p(path, payload=None, account=False):
    r=requests.post('https://openapi.tossinvest.com'+path,json=payload or {},headers=headers(account),timeout=10)
    if r.status_code!=200: raise TossError(f'POST {path} {r.status_code} {r.text}')
    return r.json().get('result')

def account_seq():
    if TOSS_ACCOUNT:
        LATEST['account_seq']=int(TOSS_ACCOUNT); return int(TOSS_ACCOUNT)
    arr=g('/api/v1/accounts')
    if not arr: raise TossError('계좌 없음')
    LATEST['account_seq']=arr[0]['accountSeq']; return arr[0]['accountSeq']

def prices(symbols):
    out={}
    for i in range(0,len(symbols),190):
        arr=g('/api/v1/prices',{'symbols':','.join(symbols[i:i+190])}) or []
        for x in arr: out[x['symbol']]={'price':fnum(x.get('lastPrice')),'currency':x.get('currency'),'timestamp':x.get('timestamp')}
    return out

def candles(sym):
    r=g('/api/v1/candles',{'symbol':sym,'interval':'1m','count':80,'adjusted':'true'}) or {}
    arr=r.get('candles',[]); arr.sort(key=lambda x:x.get('timestamp','')); return arr

def holdings(): return g('/api/v1/holdings',account=True) or {}
def bp(cur='KRW'):
    try: return fnum((g('/api/v1/buying-power',{'currency':cur},account=True) or {}).get('cashBuyingPower'))
    except Exception: return 0
def fx():
    try: return fnum((g('/api/v1/exchange-rate',{'baseCurrency':'USD','quoteCurrency':'KRW'}) or {}).get('rate'))
    except Exception: return 0
def sellable(sym):
    try: return inum((g('/api/v1/sellable-quantity',{'symbol':sym},account=True) or {}).get('sellableQuantity'))
    except Exception: return 0

def order(sym,side,qty):
    if not ALLOW_REAL_ORDERS: raise TossError('ALLOW_REAL_ORDERS=false')
    if qty<=0: raise TossError('수량 0')
    payload={'clientOrderId':f'mw-{int(time.time())}-{sym}-{side}'[:36],'symbol':sym,'side':side,'orderType':'MARKET','quantity':str(int(qty))}
    return p('/api/v1/orders',payload,account=True)

def send_kakao(text):
    if not KAKAO_TOKEN: return False,'KAKAO_TOKEN 없음'
    tpl={'object_type':'text','text':text[:900],'link':{'web_url':APP_URL or 'https://developers.kakao.com','mobile_web_url':APP_URL or 'https://developers.kakao.com'}}
    try:
        r=requests.post('https://kapi.kakao.com/v2/api/talk/memo/default/send',headers={'Authorization':'Bearer '+KAKAO_TOKEN,'Content-Type':'application/x-www-form-urlencoded;charset=utf-8'},data={'template_object':json.dumps(tpl,ensure_ascii=False)},timeout=10)
        msg=f'HTTP {r.status_code} {r.text}'; STATE['last_kakao']=nts()+' '+msg; save_state(); return r.status_code==200,msg
    except Exception as e:
        STATE['last_kakao']=nts()+' '+str(e); save_state(); return False,str(e)

def check_kakao():
    r=requests.get('https://kapi.kakao.com/v2/user/me',headers={'Authorization':'Bearer '+KAKAO_TOKEN},timeout=10)
    return r.status_code==200,f'HTTP {r.status_code}\n{r.text}'

GOOD=['수주','실적','호실적','상향','HBM','엔비디아','AI','계약','강세','반등','최대','흑자']
BAD=['급락','하락','쇼크','부진','둔화','제재','규제','전쟁','금리','환율 급등','목표가 하향','적자','감산']
QUERIES=['SK하이닉스','삼성전자 반도체','HBM 엔비디아','코스피 반도체','미국 증시 반도체','환율 금리 전쟁']

def news_score():
    if not ENABLE_NEWS: return 0,[]
    if time.time()-NEWS['ts']<NEWS_REFRESH_SEC: return NEWS['score'],NEWS['items']
    score=0; items=[]
    for q in QUERIES:
        try:
            url='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=ko&gl=KR&ceid=KR:ko'
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            xml=urllib.request.urlopen(req,timeout=8).read(); root=ET.fromstring(xml)
            for it in root.findall('.//item')[:5]:
                title=it.findtext('title') or ''; low=title.lower(); s=0
                for w in GOOD:
                    if w.lower() in low: s+=1
                for w in BAD:
                    if w.lower() in low: s-=1
                score+=s; items.append({'query':q,'title':title,'score':s})
        except Exception: pass
    score=max(-20,min(20,score*2)); NEWS.update({'ts':time.time(),'score':score,'items':items[:12]}); return score,items[:12]

def wma(vals,n):
    vals=[fnum(x) for x in vals]
    if not vals: return 0
    if len(vals)<n: return vals[-1]
    r=vals[-n:]; ws=range(1,n+1); return sum(v*w for v,w in zip(r,ws))/sum(ws)

def metrics(cs, fallback=0):
    closes=[fnum(c.get('closePrice')) for c in cs]; highs=[fnum(c.get('highPrice')) for c in cs]; lows=[fnum(c.get('lowPrice')) for c in cs]; vols=[fnum(c.get('volume')) for c in cs]
    price=closes[-1] if closes else fallback; high=max(highs) if highs else price; low=min(lows) if lows else price
    avg=sum(vols[-21:-1])/max(1,len(vols[-21:-1])) if len(vols)>2 else (vols[-1] if vols else 0); cur=vols[-1] if vols else 0
    return {'price':price,'day_high':high,'day_low':low,'wma5':wma(closes,5),'wma20':wma(closes,20),'wma60':wma(closes,60),'volume_ratio':cur/avg if avg else 0,'change_pct':((closes[-1]-closes[-2])/closes[-2]*100) if len(closes)>1 and closes[-2] else 0,'drop_from_high_pct':((price-high)/high*100) if high else 0,'bounce_from_low_pct':((price-low)/low*100) if low else 0}

def market_score(ana, ns):
    score=50; lev=ana.get('122630',{}); inv=ana.get('252670',{})
    if lev.get('wma5',0)>lev.get('wma20',0)>lev.get('wma60',0): score+=15
    if lev.get('change_pct',0)>0: score+=5
    if inv.get('wma5',0)>inv.get('wma20',0): score-=12
    if inv.get('change_pct',0)>0: score-=5
    score+=max(-10,min(10,ns/2)); score=max(0,min(100,score))
    return score, '강세' if score>=70 else ('보통' if score>=55 else ('약세/관망' if score>=40 else '방어'))

def ai(sym,m,ms,ns):
    kind=SMAP.get(sym,{}).get('kind','stock'); score=50; rs=[]; price=m['price']; w5=m['wma5']; w20=m['wma20']; w60=m['wma60']; vol=m['volume_ratio']; chg=m['change_pct']; drop=m['drop_from_high_pct']; bounce=m['bounce_from_low_pct']
    if price>w5>w20: score+=18; rs.append('단기 상승 정렬')
    elif price>w5: score+=8; rs.append('단기선 회복')
    elif price<w5<w20: score-=18; rs.append('단기 하락 정렬')
    score += 8 if w20>w60 else -5
    if vol>=1.8 and chg>0: score+=8; rs.append('거래량 동반 상승')
    if vol>=1.8 and chg<0: score-=12; rs.append('거래량 동반 하락')
    if drop<=-3: score-=10; rs.append('고점 대비 급락')
    if bounce>=1.5 and price>w5: score+=5; rs.append('저점 반등')
    if 'inverse' in kind: score+=(50-ms)*0.35-ns*0.15
    else: score+=(ms-50)*0.35+ns*0.15
    score=max(0,min(100,score))
    if score>=85: return score,'강한 진입',0.70,' / '.join(rs[:4])
    if score>=75: return score,'진입 후보',0.50,' / '.join(rs[:4])
    if score>=65: return score,'소액 후보',0.30,' / '.join(rs[:4])
    if score<=40: return score,'매도/방어',0.0,' / '.join(rs[:4])
    return score,'관망',0.0,' / '.join(rs[:4])

def emergency(m,score,ms,ns):
    drop=m['drop_from_high_pct']; vol=m['volume_ratio']
    if drop<=-4.5 and vol>=1.8 and score<=40 and (ms<=35 or ns<=-8): return 3,f'강한 비상: 고점대비 {drop:.2f}%, 거래량 {vol:.2f}배, AI {score:.0f}'
    if drop<=-3.5 and vol>=1.8 and score<=45: return 2,f'부분 비상: 고점대비 {drop:.2f}%, 거래량 {vol:.2f}배, AI {score:.0f}'
    if drop<=-2.5: return 1,f'경고: 고점대비 {drop:.2f}%'
    return 0,''

def holdmap(h):
    out={}
    for x in h.get('items',[]): out[x['symbol']]={'qty':inum(x.get('quantity')),'name':x.get('name',x['symbol'])}
    return out

def total_asset(h,bkrw,busd,rate):
    mv=h.get('marketValue',{}).get('amount',{}) if h else {}; return bkrw + fnum(mv.get('krw')) + (busd+fnum(mv.get('usd')))*rate if rate else bkrw+fnum(mv.get('krw'))

def paper_total(pr):
    total=fnum(STATE.get('paper_cash'))
    for s,pos in STATE.get('paper_positions',{}).items(): total+=inum(pos.get('qty'))*pr.get(s,{}).get('price',0)
    return total

def paper_buy(sym,price,ratio,reason):
    if STATE.get('paper_cash') is None or price<=0 or ratio<=0: return
    cash=fnum(STATE['paper_cash']); qty=int((cash*ratio)//price)
    if qty<=0: return
    pos=STATE['paper_positions'].get(sym,{'qty':0,'avg':0}); oq=inum(pos['qty']); avg=fnum(pos['avg']); cost=qty*price; nq=oq+qty; navg=(oq*avg+cost)/nq
    STATE['paper_cash']=cash-cost; STATE['paper_positions'][sym]={'qty':nq,'avg':navg}; total=paper_total(LATEST['prices']); ret=(total-fnum(STATE['paper_start']))/fnum(STATE['paper_start'])*100 if STATE.get('paper_start') else 0
    log_paper({'time':nts(),'action':'가상매수','symbol':sym,'name':SMAP.get(sym,{}).get('name',sym),'price':price,'qty':qty,'cash':STATE['paper_cash'],'paper_total':total,'realized_pnl':STATE['paper_realized'],'return_pct':ret,'reason':reason})

def paper_sell(sym,price,ratio,reason):
    pos=STATE.get('paper_positions',{}).get(sym)
    if not pos or price<=0 or ratio<=0: return
    have=inum(pos['qty']); qty=have if ratio>=1 else max(1,int(have*ratio)); avg=fnum(pos['avg']); pnl=(price-avg)*qty
    STATE['paper_cash']=fnum(STATE['paper_cash'])+qty*price; STATE['paper_realized']=fnum(STATE['paper_realized'])+pnl
    if have-qty<=0: STATE['paper_positions'].pop(sym,None)
    else: STATE['paper_positions'][sym]={'qty':have-qty,'avg':avg}
    total=paper_total(LATEST['prices']); ret=(total-fnum(STATE['paper_start']))/fnum(STATE['paper_start'])*100 if STATE.get('paper_start') else 0
    log_paper({'time':nts(),'action':'가상매도','symbol':sym,'name':SMAP.get(sym,{}).get('name',sym),'price':price,'qty':qty,'cash':STATE['paper_cash'],'paper_total':total,'realized_pnl':STATE['paper_realized'],'return_pct':ret,'reason':reason})

def run_paper(ana):
    if STATE.get('paper_start') is None: return
    for s,a in ana.items():
        if s in STATE.get('paper_positions',{}):
            if a['emergency_level']>=3 or a['ai_score']<=40: paper_sell(s,a['price'],1.0,'AI 가상 방어/비상 매도')
            elif a['emergency_level']==2 or a['ai_score']<=45: paper_sell(s,a['price'],0.5,'AI 가상 분할매도')
    c=[a for a in ana.values() if a['buy_ratio']>0 and a['emergency_level']==0 and a['symbol'] not in STATE.get('paper_positions',{})]
    if c:
        b=sorted(c,key=lambda x:x['ai_score'],reverse=True)[0]; paper_buy(b['symbol'],b['price'],b['buy_ratio'],f"AI 가상 {b['signal']} {b['reason']}")

def update_once():
    try:
        account_seq(); syms=[x['symbol'] for x in SYMBOLS]; pr=prices(syms); h=holdings(); hm=holdmap(h); bkrw=bp('KRW'); busd=bp('USD'); rate=fx(); tot=total_asset(h,bkrw,busd,rate); ns,ni=news_score()
        raw={}
        for s in syms:
            try: raw[s]=metrics(candles(s),pr.get(s,{}).get('price',0))
            except Exception: raw[s]=metrics([],pr.get(s,{}).get('price',0))
        ms,mm=market_score(raw,ns); ana={}; maxem={'level':0,'reason':''}
        for s,m in raw.items():
            sc,sg,br,reason=ai(s,m,ms,ns); lev,er=emergency(m,sc,ms,ns); held=hm.get(s,{}).get('qty',0); se=sellable(s) if held>0 else 0
            price=m['price']; bq=int((bkrw*br)//price) if br and price>0 else 0
            sr=1.0 if lev>=3 or sc<=35 else (0.5 if lev==2 or sc<=45 else (0.3 if sc<=55 else 0.0)); sq=int(se*sr) if se else 0
            a={**m,'time':nts(),'symbol':s,'name':SMAP.get(s,{}).get('name',s),'ai_score':sc,'signal':sg,'market_score':ms,'news_score':ns,'emergency_level':lev,'emergency_reason':er,'buy_ratio':br,'buy_qty':bq,'sell_ratio':sr,'sell_qty':sq,'held_qty':held,'sellable_qty':se,'reason':reason}
            ana[s]=a; log_symbol(a); log_summary({k:a.get(k,'') for k in ['time','symbol','name','price','ai_score','signal','buy_qty','sell_qty','market_score','news_score','emergency_level','emergency_reason']}|{'market_mode':mm})
            if lev>maxem['level']: maxem={'level':lev,'reason':er}
        with LOCK:
            LATEST.update({'updated_at':nts(),'total_asset':tot,'buying_power_krw':bkrw,'holdings':h.get('items',[]),'prices':pr,'analysis':ana,'market_score':ms,'market_mode':mm,'news_score':ns,'news_items':ni,'emergency':maxem})
            LATEST['real_return']=(tot-fnum(STATE['real_base']))/fnum(STATE['real_base'])*100 if STATE.get('real_base') else 0
            LATEST['paper_total']=paper_total(pr); LATEST['paper_return']=(LATEST['paper_total']-fnum(STATE['paper_start']))/fnum(STATE['paper_start'])*100 if STATE.get('paper_start') else 0
            run_paper(ana); save_state()
        emergency_real_sell(ana)
    except Exception as e:
        STATE['last_error']=nts()+' '+str(e); save_state()

def emergency_real_sell(ana):
    if not (ALLOW_REAL_ORDERS and ENABLE_EMERGENCY_AUTO_SELL): return
    for s,a in ana.items():
        if a['emergency_level']<2 or a['sellable_qty']<=0 or a['price']<=0: continue
        if time.time()-STATE.get('last_emergency_sell',{}).get(s,0)<EMERGENCY_COOLDOWN_SEC: continue
        qty=a['sellable_qty'] if a['emergency_level']>=3 else max(1,int(a['sellable_qty']*0.5))
        try:
            r=order(s,'SELL',qty); STATE.setdefault('last_emergency_sell',{})[s]=time.time(); save_state(); send_kakao(f"🚨 비상 자동매도 실행\n{a['name']} {qty}주\n{a['emergency_reason']}"); log_real({'time':nts(),'action':'비상자동매도','symbol':s,'name':a['name'],'price':a['price'],'qty':qty,'result':'SUCCESS','order_id':r.get('orderId',''),'message':json.dumps(r,ensure_ascii=False),'reason':a['emergency_reason']})
        except Exception as e:
            send_kakao(f"🚨 비상 자동매도 실패\n{a['name']}\n{e}"); log_real({'time':nts(),'action':'비상자동매도','symbol':s,'name':a['name'],'price':a['price'],'qty':qty,'result':'FAIL','order_id':'','message':str(e),'reason':a['emergency_reason']})

def worker():
    while True:
        update_once(); time.sleep(max(10,REFRESH_SEC))

def page():
    em=LATEST['emergency']; cls='danger' if em['level']>=3 else ('warn' if em['level'] else 'ok')
    rows=''
    for a in sorted(LATEST['analysis'].values(),key=lambda x:x['ai_score'],reverse=True):
        rows+=f"""<tr class='{ 'dangerrow' if a['emergency_level']>=3 else ('warnrow' if a['emergency_level'] else '') }'><td><b>{esc(a['name'])}</b><br><small>{esc(a['symbol'])}</small></td><td>{won(a['price'])}<br><small>고점대비 {a['drop_from_high_pct']:.2f}%</small></td><td><b>{a['ai_score']:.0f}</b><br>{esc(a['signal'])}</td><td>{a['volume_ratio']:.2f}배</td><td>{int(a['buy_ratio']*100)}%<br>{a['buy_qty']:,}주</td><td>{int(a['sell_ratio']*100)}%<br>{a['sell_qty']:,}주</td><td>{a['held_qty']:,}주<br><small>매도가능 {a['sellable_qty']:,}</small></td><td>{esc(a['reason'])}<br><small>{esc(a['emergency_reason'])}</small></td><td><form method='post' action='/real_buy' onsubmit="return confirm('실계좌 매수 주문?')"><input type='hidden' name='symbol' value='{esc(a['symbol'])}'><input name='qty' value='{a['buy_qty']}'><button class='buy'>매수</button></form><form method='post' action='/real_sell' onsubmit="return confirm('실계좌 매도 주문?')"><input type='hidden' name='symbol' value='{esc(a['symbol'])}'><input name='qty' value='{a['sell_qty']}'><button class='sell'>매도</button></form></td></tr>"""
    news=''.join(f"<li>[{esc(x['query'])}] {esc(x['title'])} <b>{x['score']}</b></li>" for x in LATEST['news_items'][:10])
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='30'><title>Market Watch</title><style>body{{background:#08090d;color:white;font-family:Arial;padding:20px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card{{background:#141821;border:1px solid #2a2f3a;border-radius:14px;padding:18px;margin:12px 0}}.big{{font-size:30px;color:#ffe04a;font-weight:bold}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{border-bottom:1px solid #303642;padding:8px;vertical-align:top}}input{{width:70px;background:#0b0d12;color:white;border:1px solid #444;border-radius:6px;padding:5px}}button,.btn{{border:0;border-radius:8px;padding:8px 12px;margin:3px;color:white;text-decoration:none;background:#333;font-weight:bold}}.buy{{background:#e53e3e}}.sell{{background:#2563eb}}.purple{{background:#7c3aed}}.ok{{color:#47ff8a}}.warn{{color:#ffbf47}}.danger{{color:#ff4d4d}}.warnrow{{background:#251a08}}.dangerrow{{background:#2a0808}}small{{color:#aaa}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><h1>Market Watch 최종본</h1><div class='grid'><div class='card'><h2>실계좌</h2><div class='big'>{won(LATEST['total_asset'])}</div><p>기준금: {won(STATE['real_base']) if STATE.get('real_base') else '미설정'}</p><p>수익률: {pct(LATEST['real_return'])}</p><p>매수가능: {won(LATEST['buying_power_krw'])}</p><p>실주문: {'활성화' if ALLOW_REAL_ORDERS else '차단'}</p><form method='post' action='/reset_base' onsubmit="return confirm('현재 총자산으로 기준금과 AI가상 리셋?')"><button class='purple'>오늘 기준금/AI가상 리셋</button></form></div><div class='card'><h2>AI 가상계좌</h2><div class='big'>{won(LATEST['paper_total'])}</div><p>시작금: {won(STATE['paper_start']) if STATE.get('paper_start') else '미설정'}</p><p>현금: {won(STATE['paper_cash']) if STATE.get('paper_cash') is not None else '미설정'}</p><p>수익률: {pct(LATEST['paper_return'])}</p><p>실계좌 대비: {pct(LATEST['paper_return']-LATEST['real_return'])}p</p></div><div class='card'><h2>시장/비상</h2><p class='{cls}'>{'🚨 강한 비상' if em['level']>=3 else ('🟡 경고/부분비상' if em['level'] else '🟢 정상')}</p><p>{esc(em['reason'])}</p><p>시장: {esc(LATEST['market_mode'])} / {LATEST['market_score']:.0f}</p><p>뉴스: {LATEST['news_score']:.0f}</p><p>비상자동매도: {'ON' if ENABLE_EMERGENCY_AUTO_SELL else 'OFF'}</p><p>업데이트: {esc(LATEST['updated_at'])}</p></div></div><div class='card'><h2>종목별 AI 판단</h2><table><tr><th>종목</th><th>현재가</th><th>AI</th><th>거래량</th><th>추천매수</th><th>추천매도</th><th>보유</th><th>사유</th><th>실계좌</th></tr>{rows}</table></div><div class='grid'><div class='card'><h2>뉴스</h2><ul>{news}</ul></div><div class='card'><h2>테스트/저장</h2><p><a class='btn' href='/check_kakao'>카카오 토큰</a><a class='btn' href='/test_kakao'>카카오 테스트</a><a class='btn' href='/force_update'>즉시갱신</a></p><p><a class='btn' href='/download?type=summary'>오늘 요약 CSV</a><a class='btn' href='/download?type=paper'>AI 가상 CSV</a><a class='btn' href='/download?type=real'>실계좌 주문 CSV</a></p><p><a class='btn' href='/symbols_csv'>종목별 CSV 목록</a></p><p>카카오: {esc(STATE['last_kakao'])}</p><p>오류: <small>{esc(STATE['last_error'])}</small></p></div></div></body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u=urlparse(self.path); path=u.path; qs=parse_qs(u.query)
        if path=='/': return self.html(page())
        if path=='/force_update': update_once(); return self.redir('/')
        if path=='/check_kakao': ok,msg=check_kakao(); return self.result('토큰 확인 성공' if ok else '토큰 확인 실패',msg)
        if path=='/test_kakao': ok,msg=send_kakao('✅ Market Watch 카카오톡 테스트 성공\n'+nts()); return self.result('카카오 전송 성공' if ok else '카카오 전송 실패',msg)
        if path=='/download':
            typ=qs.get('type',['summary'])[0]; d=daydir(); fn=f"summary_{day()}.csv" if typ=='summary' else (f"paper_trades_{day()}.csv" if typ=='paper' else f"real_orders_{day()}.csv"); return self.file(os.path.join(d,fn))
        if path=='/symbols_csv':
            d=os.path.join(daydir(),'symbols'); mkdir(d); links=''.join(f"<li><a href='/symbol_file?name={quote_plus(fn)}'>{esc(fn)}</a></li>" for fn in sorted(os.listdir(d))); return self.html('<h1>종목별 CSV</h1><ul>'+links+"</ul><a href='/'>돌아가기</a>")
        if path=='/symbol_file': return self.file(os.path.join(daydir(),'symbols',os.path.basename(qs.get('name',[''])[0])))
        if path=='/api/state': return self.json({'latest':LATEST,'state':STATE})
        return self.result('404','없는 주소')
    def do_POST(self):
        path=urlparse(self.path).path; data=parse_qs(self.rfile.read(int(self.headers.get('Content-Length',0))).decode())
        if path=='/reset_base':
            update_once(); base=fnum(LATEST['total_asset']); STATE.update({'real_base':base,'paper_start':base,'paper_cash':base,'paper_positions':{},'paper_realized':0.0}); save_state(); log_paper({'time':nts(),'action':'AI가상리셋','symbol':'-','name':'-','price':0,'qty':0,'cash':base,'paper_total':base,'realized_pnl':0,'return_pct':0,'reason':'오늘 기준금/AI가상 리셋'}); send_kakao(f'✅ 오늘 기준금/AI가상 리셋\n기준금: {won(base)}\n{nts()}'); return self.redir('/')
        if path in ['/real_buy','/real_sell']:
            sym=data.get('symbol',[''])[0]; qty=inum(data.get('qty',['0'])[0]); side='BUY' if path.endswith('buy') else 'SELL'; a=LATEST['analysis'].get(sym,{}); name=SMAP.get(sym,{}).get('name',sym); price=a.get('price',0)
            try:
                if price<=0: raise TossError('현재가 0')
                r=order(sym,side,qty); msg=json.dumps(r,ensure_ascii=False); log_real({'time':nts(),'action':'실계좌매수' if side=='BUY' else '실계좌매도','symbol':sym,'name':name,'price':price,'qty':qty,'result':'SUCCESS','order_id':r.get('orderId',''),'message':msg,'reason':a.get('reason','')}); send_kakao(f"✅ 실계좌 {'매수' if side=='BUY' else '매도'} 주문\n{name}\n{qty}주"); return self.result('주문 성공',msg)
            except Exception as e:
                log_real({'time':nts(),'action':'실계좌매수' if side=='BUY' else '실계좌매도','symbol':sym,'name':name,'price':price,'qty':qty,'result':'FAIL','order_id':'','message':str(e),'reason':a.get('reason','')}); send_kakao(f"⚠️ 실계좌 주문 실패\n{name}\n{e}"); return self.result('주문 실패',str(e))
        return self.result('404','없는 POST')
    def html(self,s): self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers(); self.wfile.write(s.encode('utf-8'))
    def result(self,t,m): self.html(f"<html><meta charset='utf-8'><body style='background:#08090d;color:white;font-family:Arial;padding:30px'><h1>{esc(t)}</h1><pre style='background:#000;color:#00ff66;padding:15px;white-space:pre-wrap'>{esc(m)}</pre><a style='color:#ffe812;font-size:24px' href='/'>돌아가기</a></body></html>")
    def redir(self,p): self.send_response(302); self.send_header('Location',p); self.end_headers()
    def json(self,o): self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.end_headers(); self.wfile.write(json.dumps(o,ensure_ascii=False,default=str).encode())
    def file(self,p):
        if not os.path.exists(p): return self.result('파일 없음',p)
        self.send_response(200); self.send_header('Content-Type','text/csv; charset=utf-8'); self.send_header('Content-Disposition','attachment; filename='+os.path.basename(p)); self.end_headers(); self.wfile.write(open(p,'rb').read())
    def log_message(self,*args): pass

if __name__=='__main__':
    print('Market Watch start',PORT,'ALLOW_REAL_ORDERS',ALLOW_REAL_ORDERS,'EMERGENCY_AUTO_SELL',ENABLE_EMERGENCY_AUTO_SELL)
    threading.Thread(target=worker,daemon=True).start()
    HTTPServer(('0.0.0.0',PORT),H).serve_forever()
