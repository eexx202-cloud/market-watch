from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests
import json
import threading
import time
import csv
import uuid
import html
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse, quote

import pytz


# ============================================================
# 설정
# ============================================================

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]
KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "")

BASE = RE_WEIGHT", "
    "122630": "KODEX 레버리지",
    "252670": "KODEX 인버스2X",
    "069500": "KODEX 200",
    "233740": "코스닥150 레버리지",
    "251340": "코스닥150 인버스",
    "229200": "KO

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

ALL = {**MAIN, **MARKET, **WATCH}

LEV = "0193T0"
INV = "0197X0"
HYNIX = "000660"
TRADE_SYMBOLS = [LEV, INV]


# ============================================================
# 뉴스 키워드
# ============================================================

POSITIVE_NEWS_KEYWORDS = [
    "HBM", "엔비디아", "AI", "공급", "계약", "수주", "실적 호조",
    "목표가 상향", "상향", "증설", "흑자", "최대 실적",
    "반도체 회복", "수출 증가", "강세", "급등", "호재",
    "서프라이즈", "증가", "회복", "랠리", "투자 확대"
]

NEGATIVE_NEWS_KEYWORDS = [
    "급락", "하락", "약세", "실적 부진", "목표가 하향", "하향",
    "전쟁", "제재", "규제", "금리 상승", "환율 급등",
    "반도체 둔화", "수출 감소", "감산", "적자", "악재",
    "불확실성", "매도", "쇼크", "침체", "우려", "리스크",
    "관세", "제한", "공급과잉"
]

NEWS_QUERIES = [
    "SK하이닉스",
    "삼성전자 반도체",
    "HBM 엔비디아",
    "코스피 반도체",
    "미국 증시 반도체",
    "환율 금리 전쟁"
]


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

    "market_score": {
        "kospi": 0,
        "kosdaq": 0,
        "total": 0,
        "label": "대기",
    },

    "news": {
        "updated": "없음",
        "items": [],
        "score": 0,
        "label": "뉴스 대기",
        "positive": [],
        "negative": [],
    },

    "cash": 0,
    "total_value": 0,
    "profit_loss": 0,
    "profit_rate": 0,
    "real_base_cash": REAL_BASE_CASH,
    "holdings": [],
    "sellable": {},

    "alerts": [],
    "last_alert": {},

    "orders": [],

    "paper": {
        "start_cash": PAPER_START_CASH,
        "cash": PAPER_START_CASH,
        "position": None,
        "trades": [],
        "realized_pl": 0,
        "asset": PAPER_START_CASH,
        "profit_rate": 0,
        "last_action": "없음",
        "month_target": PAPER_MONTH_TARGET,
        "target_reached": False,
        "last_exit_symbol": None,
        "last_exit_time": None,
        "last_exit_reason": "",
    },
}


# ============================================================
# 유틸
# ============================================================

def now_kst():
    return datetime.now(KST)


def now_text():
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")


def now_short():
    return now_kst().strftime("%H:%M:%S")


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


def is_market_watch_time():
    n = now_kst()
    return 8 <= n.hour < 16


def init_csv():
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([
                "time", "symbol", "name", "price", "high", "low",
                "wma5", "wma20", "wma60", "volume_ratio",
                "score", "signal", "market_score", "market_label",
                "news_score", "news_label"
            ])

    if not os.path.exists(PAPER_CSV_PATH):
        with open(PAPER_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([
                "time", "action", "symbol", "name", "price", "qty",
                "cash", "asset", "realized_pl", "profit_rate", "reason"
            ])


def append_market_csv(sym):
    try:
        name = ALL.get(sym, sym)
        price = S["prices"].get(sym, 0)
        high = S["high"].get(sym, price)
        low = S["low"].get(sym, price)
        wm = S["wma"].get(sym, {})
        score = S["scores"].get(sym, 0)
        signal = S["signals"].get(sym, {}).get("label", "")

        with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([
                now_text(),
                sym,
                name,
                price,
                high,
                low,
                wm.get("wma5", 0),
                wm.get("wma20", 0),
                wm.get("wma60", 0),
                wm.get("volume_ratio", 0),
                score,
                signal,
                S["market_score"].get("total", 0),
                S["market_score"].get("label", ""),
                S["news"].get("score", 0),
                S["news"].get("label", ""),
            ])
    except Exception as e:
        print("CSV 저장 오류:", e)


def append_paper_csv(action, sym, price, qty, reason):
    try:
        p = S["paper"]
        with open(PAPER_CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([
                now_text(),
                action,
                sym,
                ALL.get(sym, sym),
                price,
                qty,
                p["cash"],
                p["asset"],
                p["realized_pl"],
                p["profit_rate"],
                reason,
            ])
    except Exception as e:
        print("가상매매 CSV 오류:", e)


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
            S["status"] = "토큰 오류"
            print("토큰 오류:", data)
            return None

        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))

        S["token"] = token
        S["token_exp"] = time.time() + max(60, expires_in - 300)
        S["status"] = "토큰 정상"
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
    return {"Authorization": "Bearer " + str(token)}


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
        print("GET 오류:", path, r.status_code, data)

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
        print("POST 오류:", path, r.status_code, data)

    return r.status_code, data


# ============================================================
# 계좌 / 자산
# ============================================================

def load_account_seq():
    code, data = api_get("/api/v1/accounts")

    if code != 200:
        S["status"] = "계좌 목록 오류"
        return False

    accounts = data.get("result", [])
    if not accounts:
        S["status"] = "계좌 없음"
        return False

    S["account_seq"] = accounts[0].get("accountSeq")
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
            S["sellable"][sym] = to_float(data.get("result", {}).get("sellableQuantity", 0))
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

        S["updated"] = now_short()
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
    vols = [c["volume"] for c in candles if c["volume"] >= 0]

    if not closes:
        S["wma"][sym] = {
            "wma5": 0,
            "wma20": 0,
            "wma60": 0,
            "volume_ratio": 1,
        }
        return

    v_recent = vols[-1] if vols else 0
    v_avg20 = sum(vols[-20:]) / len(vols[-20:]) if vols else 0
    volume_ratio = (v_recent / v_avg20) if v_avg20 > 0 else 1

    S["wma"][sym] = {
        "wma5": round(wma(closes, 5), 2),
        "wma20": round(wma(closes, 20), 2),
        "wma60": round(wma(closes, 60), 2),
        "volume_ratio": round(volume_ratio, 2),
    }


def refresh_candles():
    target = [
        LEV, INV, HYNIX,
        "005930",
        "122630", "252670", "069500",
        "233740", "251340", "229200",
    ]

    for sym in target:
        load_candles(sym)


# ============================================================
# 뉴스
# ============================================================

def fetch_google_news_titles(query, limit=5):
    try:
        url = (
            "https://news.google.com/rss/search?q="
            + quote(query)
            + "&hl=ko&gl=KR&ceid=KR:ko"
        )

        r = requests.get(url, timeout=7)
        if r.status_code != 200:
            return []

        root = ET.fromstring(r.text)
        titles = []

        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            if title:
                titles.append(title)

            if len(titles) >= limit:
                break

        return titles

    except Exception as e:
        print("뉴스 조회 오류:", e)
        return []


def analyze_news_keywords():
    if not ENABLE_NEWS:
        return

    all_titles = []

    for q in NEWS_QUERIES:
        titles = fetch_google_news_titles(q, limit=4)
        all_titles.extend(titles)

    positives = []
    negatives = []

    for title in all_titles:
        clean = title.strip()

        for kw in POSITIVE_NEWS_KEYWORDS:
            if kw.lower() in clean.lower():
                positives.append(clean)
                break

        for kw in NEGATIVE_NEWS_KEYWORDS:
            if kw.lower() in clean.lower():
                negatives.append(clean)
                break

    positives = list(dict.fromkeys(positives))[:8]
    negatives = list(dict.fromkeys(negatives))[:8]

    score = 0
    score += min(18, len(positives) * NEWS_SCORE_WEIGHT)
    score -= min(18, len(negatives) * NEWS_SCORE_WEIGHT)

    if score >= 10:
        label = "뉴스 호재 우세"
    elif score <= -10:
        label = "뉴스 악재 우세"
    else:
        label = "뉴스 중립"

    S["news"] = {
        "updated": now_short(),
        "items": all_titles[:20],
        "score": score,
        "label": label,
        "positive": positives,
        "negative": negatives,
    }


# ============================================================
# 점수 계산
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


def volume_ratio(sym):
    return S["wma"].get(sym, {}).get("volume_ratio", 1)


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

    if chg > 0:
        score += 8
    elif chg < 0:
        score -= 8

    if vr >= VOLUME_SURGE and chg > 0:
        score += 10
    elif vr >= VOLUME_SURGE and chg < 0:
        score -= 12

    if vr <= VOLUME_DRY and hdrop < -1:
        score -= 6

    if hdrop <= -5:
        score -= 15
    elif hdrop <= -3:
        score -= 8

    if lrise >= 3 and chg > 0 and vr >= VOLUME_REBUY:
        score += 10

    return max(0, min(100, int(score)))


def calc_market_direction():
    kospi_base = calc_symbol_score("069500")
    kospi_lev = calc_symbol_score("122630")
    kospi_inv = calc_symbol_score("252670")

    kosdaq_base = calc_symbol_score("229200")
    kosdaq_lev = calc_symbol_score("233740")
    kosdaq_inv = calc_symbol_score("251340")

    kospi_score = int(((kospi_base + kospi_lev) / 2) - (kospi_inv - 50) * 0.4)
    kosdaq_score = int(((kosdaq_base + kosdaq_lev) / 2) - (kosdaq_inv - 50) * 0.4)

    total = int((kospi_score + kosdaq_score) / 2)

    if total >= 65:
        label = "상승장"
    elif total <= 40:
        label = "하락장"
    else:
        label = "혼조/관망"

    S["market_score"] = {
        "kospi": max(0, min(100, kospi_score)),
        "kosdaq": max(0, min(100, kosdaq_score)),
        "total": max(0, min(100, total)),
        "label": label,
    }


def calc_scores():
    calc_market_direction()

    lev_score = calc_symbol_score(LEV)
    inv_score = calc_symbol_score(INV)

    hynix_chg = price_change_pct(HYNIX)
    market_total = S["market_score"]["total"]
    news_score = S["news"].get("score", 0)

    if hynix_chg > 0:
        lev_score += 8
        inv_score -= 8
    elif hynix_chg < 0:
        lev_score -= 8
        inv_score += 8

    if market_total >= 65:
        lev_score += 8
        inv_score -= 8
    elif market_total <= 40:
        lev_score -= 8
        inv_score += 8

    if news_score > 0:
        lev_score += news_score
        inv_score -= int(news_score * 0.5)
    elif news_score < 0:
        lev_score += news_score
        inv_score += abs(news_score)

    S["scores"][LEV] = max(0, min(100, int(lev_score)))
    S["scores"][INV] = max(0, min(100, int(inv_score)))

    build_signals()


def bad_news_risk_detected(sym):
    chg = price_change_pct(sym)
    hdrop = high_drop_pct(sym)
    vr = volume_ratio(sym)
    news_score = S["news"].get("score", 0)

    if chg <= -1.0 and hdrop <= -3.0 and vr >= VOLUME_SURGE:
        return True

    if news_score <= -10 and hdrop <= -2.0:
        return True

    return False


def signal_from_score(sym):
    score = S["scores"].get(sym, 0)
    hdrop = high_drop_pct(sym)
    vr = volume_ratio(sym)

    if bad_news_risk_detected(sym):
        return "악재성 급락 의심 ⚠️"

    if score >= 80:
        return "강한 진입 ⭕"
    if score >= 70:
        return "진입 후보 ⭕"
    if score >= 60:
        return "보유/관찰 🟡"
    if score >= 40:
        return "관망 🔴"

    if hdrop <= -3 or vr >= VOLUME_SURGE:
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
            "volume_ratio": round(volume_ratio(sym), 2),
        }


def can_rebuy_after_pullback(sym):
    price = S["prices"].get(sym, 0)
    wm = S["wma"].get(sym, {})
    w5 = wm.get("wma5", 0)
    w20 = wm.get("wma20", 0)
    vr = wm.get("volume_ratio", 1)
    lrise = low_rise_pct(sym)
    hdrop = high_drop_pct(sym)

    if price <= 0:
        return False

    if vr < VOLUME_REBUY:
        return False

    if hdrop > -0.5 and lrise > 5:
        return False

    if w5 > 0 and price > w5 and lrise >= 1.0:
        return True

    if w5 > 0 and w20 > 0 and w5 > w20 and vr >= VOLUME_REBUY:
        return True

    return False


def paper_month_target_reached():
    return S["paper"]["realized_pl"] >= S["paper"]["month_target"]


# ============================================================
# 카카오
# ============================================================

def send_kakao(msg, link_url=None):
    print("[카카오]", msg)

    S["alerts"].insert(0, {
        "time": now_short(),
        "msg": msg,
    })
    S["alerts"] = S["alerts"][:80]

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
        f"시장: {S['market_score']['label']} / {S['market_score']['total']}점\n"
        f"뉴스: {S['news']['label']} / {S['news']['score']}점\n"
        f"거래량비율: {sig.get('volume_ratio', 0)}배\n"
        f"추천비중: {ratio}%\n"
        f"추천수량: {qty}주\n"
        f"고점대비: {sig.get('hdrop', 0)}%\n"
        f"WMA5: {fmt_won(wm.get('wma5', 0))}\n"
        f"WMA20: {fmt_won(wm.get('wma20', 0))}\n"
        f"WMA60: {fmt_won(wm.get('wma60', 0))}\n"
        f"\n실계좌 주문은 직접 버튼 클릭"
    )


def maybe_alert():
    if not is_market_watch_time():
        return

    lev_score = S["scores"].get(LEV, 0)
    inv_score = S["scores"].get(INV, 0)

    if bad_news_risk_detected(LEV):
        send_alert_once(
            "BAD_NEWS_RISK_LEV",
            make_signal_message(LEV, "⚠️ 레버리지 악재성 급락 의심")
        )

    if bad_news_risk_detected(INV):
        send_alert_once(
            "BAD_NEWS_RISK_INV",
            make_signal_message(INV, "⚠️ 인버스 급등/시장 급락 의심")
        )

    if lev_score >= 75 and lev_score >= inv_score + 15:
        send_alert_once("LEV_ENTRY", make_signal_message(LEV, "🟢 레버리지 진입 후보"))

    if inv_score >= 75 and inv_score >= lev_score + 15:
        send_alert_once("INV_ENTRY", make_signal_message(INV, "🔵 인버스 진입 후보"))

    if lev_score <= 40 and high_drop_pct(LEV) <= -3:
        send_alert_once("LEV_SELL", make_signal_message(LEV, "⛔ 레버리지 매도 후보"))

    for sym in TRADE_SYMBOLS:
        vr = volume_ratio(sym)
        hdrop = high_drop_pct(sym)
        score = S["scores"].get(sym, 0)

        if vr >= VOLUME_SURGE and hdrop <= -1.0 and score < 65:
            send_alert_once(
                "VOLUME_PROFIT_TAKE_" + sym,
                make_signal_message(sym, "💰 거래량 급증 후 고점 이탈: 분할익절 검토")
            )


# ============================================================
# 실계좌 반자동 주문
# ============================================================

def place_order_manual(sym, side, qty):
    if not ENABLE_REAL_ORDER:
        return {"ok": False, "message": "실계좌 주문이 비활성화되어 있습니다."}

    qty = int(qty)

    if qty <= 0:
        return {"ok": False, "message": "수량이 0입니다."}

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
        "time": now_short(),
        "symbol": sym,
        "name": name,
        "side": side_kr,
        "qty": qty,
        "status": "성공" if code == 200 else "실패",
        "response": data,
    })
    S["orders"] = S["orders"][:50]

    if code == 200:
        send_kakao(
            f"✅ 실계좌 반자동 {side_kr} 주문 전송\n"
            f"{name}\n"
            f"수량: {qty}주\n"
            f"clientOrderId: {client_order_id}"
        )
        refresh_account_all()
        return {"ok": True, "data": data}

    send_kakao(
        f"⚠️ 실계좌 반자동 {side_kr} 주문 실패\n"
        f"{name}\n"
        f"수량: {qty}주\n"
        f"응답: {json.dumps(data, ensure_ascii=False)[:500]}"
    )
    return {"ok": False, "data": data}


# ============================================================
# AI 가상매매
# ============================================================

def paper_position_value():
    p = S["paper"]
    pos = p["position"]

    if not pos:
        return 0

    price = S["prices"].get(pos["symbol"], 0)
    return price * pos["qty"]


def update_paper_asset():
    p = S["paper"]
    p["asset"] = p["cash"] + paper_position_value()
    p["profit_rate"] = ((p["asset"] - p["start_cash"]) / p["start_cash"] * 100) if p["start_cash"] > 0 else 0
    p["target_reached"] = p["realized_pl"] >= p["month_target"]


def paper_buy(sym, ratio, reason):
    p = S["paper"]

    if p["position"]:
        return False

    price = S["prices"].get(sym, 0)
    if price <= 0:
        return False

    buy_amount = p["asset"] * ratio
    buy_amount = min(buy_amount, p["cash"])

    qty = int(buy_amount // price)
    if qty <= 0:
        return False

    cost = qty * price
    p["cash"] -= cost

    p["position"] = {
        "symbol": sym,
        "name": ALL.get(sym, sym),
        "qty": qty,
        "buy_price": price,
        "buy_time": now_text(),
        "high_after_buy": price,
    }

    update_paper_asset()

    msg = (
        f"🤖 AI 가상매수\n"
        f"{ALL.get(sym, sym)}\n"
        f"가격: {fmt_won(price)}\n"
        f"수량: {qty}주\n"
        f"사유: {reason}\n"
        f"가상자산: {fmt_won(p['asset'])}"
    )

    p["last_action"] = f"{now_short()} 가상매수 {ALL.get(sym, sym)}"
    p["trades"].insert(0, {
        "time": now_short(),
        "action": "가상매수",
        "symbol": sym,
        "name": ALL.get(sym, sym),
        "price": price,
        "qty": qty,
        "pl": 0,
        "reason": reason,
    })
    p["trades"] = p["trades"][:100]

    append_paper_csv("BUY", sym, price, qty, reason)
    send_kakao(msg, APP_URL)

    return True


def paper_sell(reason):
    p = S["paper"]
    pos = p["position"]

    if not pos:
        return False

    sym = pos["symbol"]
    price = S["prices"].get(sym, 0)

    if price <= 0:
        return False

    qty = pos["qty"]
    sell_amount = qty * price
    buy_amount = qty * pos["buy_price"]
    pl = sell_amount - buy_amount

    p["cash"] += sell_amount
    p["realized_pl"] += pl

    p["last_exit_symbol"] = sym
    p["last_exit_time"] = now_text()
    p["last_exit_reason"] = reason
    p["position"] = None

    update_paper_asset()

    msg = (
        f"🤖 AI 가상매도\n"
        f"{ALL.get(sym, sym)}\n"
        f"가격: {fmt_won(price)}\n"
        f"수량: {qty}주\n"
        f"손익: {fmt_won(pl)}\n"
        f"누적실현손익: {fmt_won(p['realized_pl'])}\n"
        f"사유: {reason}\n"
        f"가상자산: {fmt_won(p['asset'])}\n"
        f"수익률: {p['profit_rate']:.2f}%"
    )

    p["last_action"] = f"{now_short()} 가상매도 {ALL.get(sym, sym)}"
    p["trades"].insert(0, {
        "time": now_short(),
        "action": "가상매도",
        "symbol": sym,
        "name": ALL.get(sym, sym),
        "price": price,
        "qty": qty,
        "pl": pl,
        "reason": reason,
    })
    p["trades"] = p["trades"][:100]

    append_paper_csv("SELL", sym, price, qty, reason)
    send_kakao(msg, APP_URL)

    return True


def paper_switch(new_sym, reason):
    p = S["paper"]
    pos = p["position"]

    if pos and pos["symbol"] == new_sym:
        return False

    if pos:
        paper_sell("전환 매도: " + reason)

    score = S["scores"].get(new_sym, 0)
    ratio = recommend_ratio(score)
    if ratio <= 0:
        ratio = 0.5

    return paper_buy(new_sym, ratio, "전환 매수: " + reason)


def run_paper_ai():
    if not is_market_watch_time():
        update_paper_asset()
        return

    p = S["paper"]
    update_paper_asset()

    lev_score = S["scores"].get(LEV, 0)
    inv_score = S["scores"].get(INV, 0)

    pos = p["position"]

    if paper_month_target_reached() and not pos:
        p["last_action"] = "월 목표 달성, 신규 가상매수 중단"
        return

    if pos:
        cur_price = S["prices"].get(pos["symbol"], 0)
        if cur_price > pos.get("high_after_buy", 0):
            pos["high_after_buy"] = cur_price

    if not pos:
        if lev_score >= 75 and lev_score >= inv_score + 15 and can_rebuy_after_pullback(LEV):
            paper_buy(LEV, recommend_ratio(lev_score), "레버리지 점수 우세 + 거래량/뉴스 확인")
            return

        if inv_score >= 75 and inv_score >= lev_score + 15 and can_rebuy_after_pullback(INV):
            paper_buy(INV, recommend_ratio(inv_score), "인버스 점수 우세 + 거래량/뉴스 확인")
            return

        return

    sym = pos["symbol"]
    other = INV if sym == LEV else LEV
    sym_score = S["scores"].get(sym, 0)
    other_score = S["scores"].get(other, 0)

    cur_price = S["prices"].get(sym, 0)
    buy_price = pos["buy_price"]
    high_after = pos.get("high_after_buy", buy_price)

    profit = (cur_price - buy_price) / buy_price * 100 if buy_price > 0 else 0
    drop_from_high = (cur_price - high_after) / high_after * 100 if high_after > 0 else 0
    vr = volume_ratio(sym)

    if bad_news_risk_detected(sym):
        paper_sell("뉴스/거래량 기준 악재성 급락")
        return

    if profit <= -2.0:
        paper_sell("손절 -2% 도달")
        return

    if drop_from_high <= -3.0:
        paper_sell("가상 고점 대비 -3%")
        return

    if profit >= 1.5 and vr >= VOLUME_SURGE and drop_from_high <= -1.0:
        paper_sell("수익 구간 거래량 급증 후 고점 이탈")
        return

    if profit >= 1.0 and vr <= VOLUME_DRY and sym_score < 60:
        paper_sell("급등 후 거래량 감소 + 점수 약화")
        return

    if sym_score <= 40:
        paper_sell("보유 종목 AI 점수 40 이하")
        return

    if other_score >= 78 and other_score >= sym_score + 20 and can_rebuy_after_pullback(other):
        paper_switch(other, "반대 방향 점수 우세 + 거래량/뉴스 확인")
        return

    if profit >= 2.0 and sym_score < 60:
        paper_sell("수익 +2% 이상 후 점수 약화")
        return


def reset_paper():
    S["paper"] = {
        "start_cash": PAPER_START_CASH,
        "cash": PAPER_START_CASH,
        "position": None,
        "trades": [],
        "realized_pl": 0,
        "asset": PAPER_START_CASH,
        "profit_rate": 0,
        "last_action": "리셋",
        "month_target": PAPER_MONTH_TARGET,
        "target_reached": False,
        "last_exit_symbol": None,
        "last_exit_time": None,
        "last_exit_reason": "",
    }
    send_kakao(f"🔄 AI 가상매매 리셋\n시작금: {fmt_won(PAPER_START_CASH)}", APP_URL)


# ============================================================
# 메인 루프
# ============================================================

def loop():
    init_csv()
    get_token()
    refresh_account_all()

    counter = 0
    last_news_time = 0

    while True:
        try:
            n = now_kst()

            if n.hour == 9 and n.minute == 0:
                S["high"] = {}
                S["low"] = {}
                S["last_alert"] = {}
                send_kakao("🔔 장 시작\n반자동 관제센터 + 뉴스/거래량 강화 AI 가상매매 시작", APP_URL)

            if is_market_watch_time():
                load_prices()

                if counter % 2 == 0:
                    refresh_candles()

                if ENABLE_NEWS and time.time() - last_news_time >= NEWS_REFRESH_SEC:
                    analyze_news_keywords()
                    last_news_time = time.time()

                calc_scores()

                for sym in TRADE_SYMBOLS:
                    append_market_csv(sym)

                maybe_alert()
                run_paper_ai()
            else:
                load_prices()

                if ENABLE_NEWS and time.time() - last_news_time >= NEWS_REFRESH_SEC:
                    analyze_news_keywords()
                    last_news_time = time.time()

                update_paper_asset()

            if counter % 5 == 0:
                refresh_account_all()

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
                "market_score": S["market_score"],
                "news": S["news"],
                "paper": S["paper"],
            })
            return

        if path == "/refresh":
            load_prices()
            refresh_candles()
            analyze_news_keywords()
            calc_scores()
            refresh_account_all()
            update_paper_asset()
            self.redirect("/")
            return

        if path == "/test_kakao":
            send_kakao("✅ 카카오 알림 테스트 성공\n" + now_text(), APP_URL)
            self.html_response("<h2>카카오 테스트 전송 완료</h2><a href='/'>돌아가기</a>")
            return

        if path == "/test_entry":
            send_kakao(make_signal_message(LEV, "🟢 테스트 레버리지 진입 후보"), APP_URL)
            self.html_response("<h2>진입 테스트 전송 완료</h2><a href='/'>돌아가기</a>")
            return

        if path == "/test_sell":
            send_kakao(make_signal_message(LEV, "⛔ 테스트 레버리지 매도 후보"), APP_URL)
            self.html_response("<h2>매도 테스트 전송 완료</h2><a href='/'>돌아가기</a>")
            return

        if path == "/download_csv":
            self.download_file(CSV_PATH, "data.csv")
            return

        if path == "/download_paper":
            self.download_file(PAPER_CSV_PATH, "paper_trades.csv")
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

        if path == "/paper_reset":
            reset_paper()
            self.json_response({"ok": True})
            return

        if path == "/paper_buy":
            sym = body.get("symbol")
            ratio = to_float(body.get("ratio", 0.5))
            ok = paper_buy(sym, ratio, "수동 가상매수")
            self.json_response({"ok": ok})
            return

        if path == "/paper_sell":
            ok = paper_sell("수동 가상매도")
            self.json_response({"ok": ok})
            return

        self.json_response({"ok": False, "message": "unknown path"})

    def render_dashboard(self):
        html_doc = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>80억 프로젝트 반자동 관제센터</title>
<meta http-equiv="refresh" content="60">
<style>
* {{ box-sizing: border-box; }}
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
    grid-template-columns: 1.05fr 1.5fr 1.1fr;
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
.big {{ font-size: 25px; font-weight: bold; }}
.mid {{ font-size: 18px; font-weight: bold; }}
.small {{ font-size: 11px; color: #888; }}
.red {{ color: #ff4d4d; }}
.blue {{ color: #4d8cff; }}
.green {{ color: #4dff88; }}
.yellow {{ color: #ffd84d; }}
.gray {{ color: #888; }}
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
.buy {{ background: #d71920; color: white; }}
.sell {{ background: #1f64ff; color: white; }}
.graybtn {{ background: #333; color: white; }}
.gold {{ background: #ffd84d; color: black; }}
.paperbtn {{ background: #7b3ff2; color: white; }}
input {{
    background: #05060a;
    color: white;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 7px;
    width: 80px;
}}
.progress {{
    width: 100%;
    height: 8px;
    background: #222;
    border-radius: 10px;
    overflow: hidden;
    margin: 6px 0;
}}
.bar {{ height: 100%; background: #ffd84d; }}
@media (max-width: 900px) {{
    .grid {{ grid-template-columns: 1fr; }}
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
        {self.account_card()}
        {self.paper_card()}
        {self.holdings_card()}
    </div>

    <div>
        {self.market_card()}
        {self.signal_card(LEV, "red")}
        {self.signal_card(INV, "blue")}
        {self.basic_card(HYNIX)}
        {self.stock_table()}
    </div>

    <div>
        {self.test_card()}
        {self.news_card()}
        {self.alert_card()}
        {self.order_card()}
        {self.paper_trade_card()}
    </div>
</div>

<script>
async function postJson(path, body) {{
    const res = await fetch(path, {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify(body || {{}})
    }});
    return await res.json();
}}

async function order(symbol, side, qtyId) {{
    const qty = document.getElementById(qtyId).value;
    const sideText = side === "BUY" ? "매수" : "매도";

    if (!qty || Number(qty) <= 0) {{
        alert("수량이 0입니다.");
        return;
    }}

    if (!confirm(symbol + " " + qty + "주 실계좌 " + sideText + " 주문 전송?")) return;

    const data = await postJson("/order", {{symbol: symbol, side: side, qty: qty}});

    if (data.ok) {{
        alert("주문 전송 완료");
        location.reload();
    }} else {{
        alert("주문 실패: " + JSON.stringify(data));
    }}
}}

async function paperBuy(symbol) {{
    const data = await postJson("/paper_buy", {{symbol: symbol, ratio: 0.5}});
    alert(data.ok ? "가상매수 완료" : "가상매수 실패");
    location.reload();
}}

async function paperSell() {{
    const data = await postJson("/paper_sell", {{}});
    alert(data.ok ? "가상매도 완료" : "가상매도 실패");
    location.reload();
}}

async function paperReset() {{
    if (!confirm("AI 가상매매를 2,000만원으로 리셋할까요?")) return;
    await postJson("/paper_reset", {{}});
    location.reload();
}}

function setQty(id, qty) {{
    document.getElementById(id).value = qty;
}}
</script>

</body>
</html>
"""
        self.html_response(html_doc)

    def account_card(self):
        real_rate = ((S["total_value"] - S["real_base_cash"]) / S["real_base_cash"] * 100) if S["real_base_cash"] > 0 else 0

        return f"""
<div class="card">
    <h2>실계좌</h2>
    <div class="small">실제 기준금</div>
    <div class="mid yellow">{fmt_won(S["real_base_cash"])}</div>
    <br>
    <div class="small">총자산</div>
    <div class="big yellow">{fmt_won(S["total_value"])}</div>
    <div class="small">기준금 대비 {real_rate:.2f}%</div>
    <br>
    <div class="small">매수가능금액</div>
    <div class="mid">{fmt_won(S["cash"])}</div>
    <br>
    <div class="small">평가손익</div>
    <div class="mid {'red' if S["profit_loss"] >= 0 else 'blue'}">{fmt_won(S["profit_loss"])}</div>
    <div class="{'red' if S["profit_rate"] >= 0 else 'blue'}">{S["profit_rate"]}%</div>
    <br>
    <div class="small">실주문 상태</div>
    <div class="{'green' if ENABLE_REAL_ORDER else 'red'}">{'활성화' if ENABLE_REAL_ORDER else '비활성화'}</div>
</div>
"""

    def paper_card(self):
        p = S["paper"]
        pos = p["position"]
        pos_text = "없음"

        if pos:
            cur = S["prices"].get(pos["symbol"], 0)
            profit = (cur - pos["buy_price"]) * pos["qty"]
            profit_rate = ((cur - pos["buy_price"]) / pos["buy_price"] * 100) if pos["buy_price"] > 0 else 0
            pos_text = (
                f"{safe(pos['name'])}<br>"
                f"{int(pos['qty'])}주 / 매수가 {fmt_won(pos['buy_price'])}<br>"
                f"평가손익 <span class='{'red' if profit >= 0 else 'blue'}'>{fmt_won(profit)} / {profit_rate:.2f}%</span>"
            )

        real_compare = ((S["total_value"] - S["real_base_cash"]) / S["real_base_cash"] * 100) if S["real_base_cash"] > 0 else 0
        diff = p["profit_rate"] - real_compare

        return f"""
<div class="card">
    <h2>AI 가상매매</h2>
    <div class="small">가상 시작금</div>
    <div class="mid yellow">{fmt_won(p["start_cash"])}</div>
    <br>
    <div class="small">가상 총자산</div>
    <div class="big {'red' if p["asset"] >= p["start_cash"] else 'blue'}">{fmt_won(p["asset"])}</div>
    <div class="{'red' if p["profit_rate"] >= 0 else 'blue'}">{p["profit_rate"]:.2f}%</div>
    <br>
    <div class="small">누적 실현손익 / 월 목표</div>
    <div>{fmt_won(p["realized_pl"])} / {fmt_won(p["month_target"])}</div>
    <div class="{'green' if p["target_reached"] else 'gray'}">{'월 목표 달성' if p["target_reached"] else '월 목표 미달성'}</div>
    <br>
    <div class="small">실제 대비 차이</div>
    <div class="mid {'red' if diff >= 0 else 'blue'}">{diff:.2f}%p</div>
    <br>
    <div class="small">가상 보유</div>
    <div>{pos_text}</div>
    <br>
    <div class="small">마지막 행동</div>
    <div>{safe(p["last_action"])}</div>
    <br>
    <button class="paperbtn" onclick="paperBuy('{LEV}')">가상 레버 매수</button>
    <button class="paperbtn" onclick="paperBuy('{INV}')">가상 인버스 매수</button>
    <button class="sell" onclick="paperSell()">가상 매도</button>
    <button class="graybtn" onclick="paperReset()">가상 리셋</button>
</div>
"""

    def holdings_card(self):
        rows = ""

        if not S["holdings"]:
            rows = "<tr><td colspan='4' class='gray'>보유 없음</td></tr>"
        else:
            for h in S["holdings"]:
                color = "red" if h["pl_rate"] >= 0 else "blue"
                rows += f"""
<tr>
    <td>{safe(h["name"])}<br><span class="small">{safe(h["symbol"])}</span></td>
    <td>{int(h["qty"])}주</td>
    <td>{fmt_won(h["last_price"])}</td>
    <td class="{color}">{h["pl_rate"]:.2f}%</td>
</tr>
"""

        return f"""
<div class="card">
    <h2>보유종목</h2>
    <table>
        <tr><th>종목</th><th>수량</th><th>현재가</th><th>수익률</th></tr>
        {rows}
    </table>
</div>
"""

    def market_card(self):
        ms = S["market_score"]

        return f"""
<div class="card">
    <h2>시장 방향</h2>
    <div class="big yellow">{safe(ms["label"])}</div>
    <div class="small">종합 시장 점수 {ms["total"]}</div>
    <div class="progress"><div class="bar" style="width:{ms["total"]}%"></div></div>
    <table>
        <tr><td>코스피 대용</td><td>{ms["kospi"]}점</td></tr>
        <tr><td>코스닥 대용</td><td>{ms["kosdaq"]}점</td></tr>
        <tr><td>KODEX 200</td><td>{fmt_won(S["prices"].get("069500", 0))}</td></tr>
        <tr><td>KODEX 레버리지</td><td>{fmt_won(S["prices"].get("122630", 0))}</td></tr>
        <tr><td>KODEX 인버스2X</td><td>{fmt_won(S["prices"].get("252670", 0))}</td></tr>
    </table>
</div>
"""

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
        <tr><td>거래량비율</td><td>{sig.get("volume_ratio", 0)}배</td></tr>
        <tr><td>고점대비</td><td>{sig.get("hdrop", 0)}%</td></tr>
        <tr><td>저점대비</td><td>{sig.get("lrise", 0)}%</td></tr>
        <tr><td>추천비중</td><td>{ratio}%</td></tr>
        <tr><td>추천수량</td><td>{rec_qty}주</td></tr>
        <tr><td>매도가능</td><td>{sellable}주</td></tr>
    </table>

    <div>
        <input id="{qty_id}" type="number" value="{rec_qty}" min="0">
        <button class="buy" onclick="order('{sym}', 'BUY', '{qty_id}')">실계좌 매수</button>
        <button class="sell" onclick="order('{sym}', 'SELL', '{qty_id}')">실계좌 매도</button>
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
    <div class="small">등락 {chg:.2f}%</div>
    <table>
        <tr><td>WMA5</td><td>{fmt_won(wm.get("wma5", 0))}</td></tr>
        <tr><td>WMA20</td><td>{fmt_won(wm.get("wma20", 0))}</td></tr>
        <tr><td>WMA60</td><td>{fmt_won(wm.get("wma60", 0))}</td></tr>
        <tr><td>거래량비율</td><td>{wm.get("volume_ratio", 1)}배</td></tr>
    </table>
</div>
"""

    def stock_table(self):
        rows = ""

        for sym, name in ALL.items():
            price = S["prices"].get(sym, 0)
            chg = price_change_pct(sym)
            hdrop = high_drop_pct(sym)
            score = S["scores"].get(sym, "")
            vr = volume_ratio(sym)
            color = "red" if chg > 0 else "blue" if chg < 0 else "gray"

            rows += f"""
<tr>
    <td>{safe(name)}<br><span class="small">{safe(sym)}</span></td>
    <td>{fmt_won(price)}</td>
    <td class="{color}">{chg:.2f}%</td>
    <td>{vr:.2f}배</td>
    <td>{hdrop:.2f}%</td>
    <td>{score}</td>
</tr>
"""

        return f"""
<div class="card">
    <h2>전체 종목 현황</h2>
    <table>
        <tr><th>종목</th><th>현재가</th><th>등락</th><th>거래량</th><th>고점대비</th><th>점수</th></tr>
        {rows}
    </table>
</div>
"""

    def news_card(self):
        news = S.get("news", {})
        pos_rows = ""
        neg_rows = ""

        for t in news.get("positive", [])[:5]:
            pos_rows += f"<tr><td class='red'>호재</td><td>{safe(t)}</td></tr>"

        for t in news.get("negative", [])[:5]:
            neg_rows += f"<tr><td class='blue'>악재</td><td>{safe(t)}</td></tr>"

        if not pos_rows:
            pos_rows = "<tr><td colspan='2' class='gray'>호재 뉴스 없음</td></tr>"

        if not neg_rows:
            neg_rows = "<tr><td colspan='2' class='gray'>악재 뉴스 없음</td></tr>"

        return f"""
<div class="card">
    <h2>뉴스 키워드</h2>
    <div class="mid yellow">{safe(news.get("label", "뉴스 대기"))}</div>
    <div class="small">뉴스 점수 {news.get("score", 0)} / 업데이트 {safe(news.get("updated", "없음"))}</div>
    <br>
    <table>
        <tr><th>구분</th><th>제목</th></tr>
        {pos_rows}
        {neg_rows}
    </table>
</div>
"""

    def test_card(self):
        return """
<div class="card">
    <h2>테스트</h2>
    <button class="graybtn" onclick="location.href='/refresh'">새로고침</button>
    <button class="graybtn" onclick="location.href='/test_kakao'">카카오 테스트</button>
    <button class="buy" onclick="location.href='/test_entry'">진입 알림 테스트</button>
    <button class="sell" onclick="location.href='/test_sell'">매도 알림 테스트</button>
    <button class="gold" onclick="location.href='/download_csv'">가격 CSV</button>
    <button class="gold" onclick="location.href='/download_paper'">가상매매 CSV</button>
</div>
"""

    def alert_card(self):
        rows = ""

        if not S["alerts"]:
            rows = "<tr><td colspan='2' class='gray'>없음</td></tr>"
        else:
            for a in S["alerts"][:20]:
                rows += f"""
<tr>
    <td class="small">{safe(a["time"])}</td>
    <td>{safe(a["msg"]).replace(chr(10), "<br>")}</td>
</tr>
"""

        return f"""
<div class="card">
    <h2>카카오 / 신호 기록</h2>
    <table><tr><th>시간</th><th>내용</th></tr>{rows}</table>
</div>
"""

    def order_card(self):
        rows = ""

        if not S["orders"]:
            rows = "<tr><td colspan='3' class='gray'>없음</td></tr>"
        else:
            for o in S["orders"][:20]:
                color = "green" if o["status"] == "성공" else "red"
                rows += f"""
<tr>
    <td class="small">{safe(o["time"])}</td>
    <td>{safe(o["name"])} {safe(o["side"])} {safe(o["qty"])}주</td>
    <td class="{color}">{safe(o["status"])}</td>
</tr>
"""

        return f"""
<div class="card">
    <h2>실계좌 반자동 주문 기록</h2>
    <table><tr><th>시간</th><th>주문</th><th>결과</th></tr>{rows}</table>
</div>
"""

    def paper_trade_card(self):
        rows = ""

        trades = S["paper"]["trades"]

        if not trades:
            rows = "<tr><td colspan='4' class='gray'>없음</td></tr>"
        else:
            for t in trades[:20]:
                color = "red" if t["pl"] >= 0 else "blue"
                rows += f"""
<tr>
    <td class="small">{safe(t["time"])}</td>
    <td>{safe(t["action"])}</td>
    <td>{safe(t["name"])} {safe(t["qty"])}주</td>
    <td class="{color}">{fmt_won(t["pl"])}</td>
</tr>
"""

        return f"""
<div class="card">
    <h2>AI 가상매매 기록</h2>
    <table><tr><th>시간</th><th>행동</th><th>종목</th><th>손익</th></tr>{rows}</table>
</div>
"""

    def download_file(self, path, filename):
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


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    print("반자동 관제센터 + 뉴스/거래량 강화 AI 가상매매 시작:", PORT)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
